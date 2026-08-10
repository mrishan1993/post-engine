from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from db.models import Story, Storyboard, StoryboardAsset, StoryboardScene, StoryboardShot
from prediction.probability import predict_opportunity
from story_engine.schemas import StoryBlueprint
from storyboard_engine.assets import attach_resolved_requirements, resolve_assets_for_storyboard
from storyboard_engine.critic import critique_storyboard, evaluate_quality, revise_storyboard
from storyboard_engine.generator import build_storyboard
from storyboard_engine.schemas import StoryboardDocument, StoryboardRequest


class StoryboardService:
    def __init__(self, session: Session):
        self.session = session

    def generate(self, request: StoryboardRequest | dict[str, Any]) -> Storyboard:
        req = (
            request
            if isinstance(request, StoryboardRequest)
            else StoryboardRequest.model_validate(request)
        )
        story, blueprint = self._load_story_blueprint(req)
        if story and not req.character_ids and story.character_ids:
            req.character_ids = list(story.character_ids)
        if story and not req.predicted_retention:
            snap = story.prediction_snapshot or {}
            req.predicted_retention = snap.get("predicted_retention")
            req.virality_probability = snap.get("virality_probability") or snap.get(
                "story_probability_hint"
            )
        if story and not req.platform:
            req.platform = story.platform or req.platform
        req.story_id = req.story_id or (story.id if story else None)

        location_hint = None
        if "school" in (blueprint.logline or "").lower():
            location_hint = "Haunted School"

        char_ctx, resolved, asset_avail = resolve_assets_for_storyboard(
            self.session,
            req,
            location_name=location_hint,
            emotion=(blueprint.hook.emotion if blueprint.hook else None),
        )
        doc = build_storyboard(
            blueprint, req, character_context=char_ctx, resolved_assets=resolved
        )
        attach_resolved_requirements(doc, resolved)

        doc, critic, quality = self._critique_revise_loop(
            doc, req, asset_availability=asset_avail, max_revisions=req.max_revisions
        )
        pred_hint = self._probability_hint(req, blueprint, doc, quality.overall)

        if not story:
            raise ValueError("story_id is required and must reference an existing story")
        version = self._next_version(story.id)
        board = Storyboard(
            id=str(uuid4()),
            story_id=story.id,
            version=version,
            platform=req.platform,
            duration_sec=doc.duration_sec,
            global_direction=doc.global_direction.model_dump(),
            document=doc.model_dump(by_alias=True),
            quality_score=quality.overall,
            status="scored",
            critic_result=critic.model_dump(),
            prediction_snapshot={
                "storyboard_probability_hint": pred_hint,
                "predicted_retention": req.predicted_retention,
                "virality_probability": req.virality_probability,
            },
            story_version=story.current_version,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.session.add(board)
        self.session.flush()
        self._persist_children(board, doc)
        get_bus().publish(
            EventType.STORYBOARD_CREATED,
            {
                "storyboard_id": board.id,
                "story_id": board.story_id,
                "version": board.version,
                "scene_count": len(doc.scenes),
                "shot_count": sum(len(s.shots) for s in doc.scenes),
                "duration_sec": float(doc.duration_sec),
                "quality_score": float(quality.overall),
            },
            producer="storyboard-engine",
        )
        return board

    def revise(self, storyboard_id: str, *, max_revisions: int = 1) -> Storyboard:
        board = self.session.get(Storyboard, storyboard_id)
        if not board:
            raise ValueError(f"storyboard {storyboard_id} not found")
        doc = StoryboardDocument.model_validate(board.document)
        req = StoryboardRequest(
            story_id=board.story_id,
            platform=board.platform or "instagram_reels",
            max_revisions=max_revisions,
            predicted_retention=(board.prediction_snapshot or {}).get("predicted_retention"),
        )
        doc, critic, quality = self._critique_revise_loop(
            doc,
            req,
            asset_availability=float(
                (doc.quality.asset_availability if doc.quality else 0.8) or 0.8
            ),
            max_revisions=max_revisions,
        )
        # Immutable versions: create new row
        new_version = int(board.version) + 1
        new_board = Storyboard(
            id=str(uuid4()),
            story_id=board.story_id,
            version=new_version,
            platform=board.platform,
            duration_sec=doc.duration_sec,
            global_direction=doc.global_direction.model_dump(),
            document=doc.model_dump(by_alias=True),
            quality_score=quality.overall,
            status="scored",
            critic_result=critic.model_dump(),
            prediction_snapshot=board.prediction_snapshot,
            story_version=board.story_version,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.session.add(new_board)
        self.session.flush()
        self._persist_children(new_board, doc)
        return new_board

    def approve(self, storyboard_id: str) -> Storyboard:
        board = self.session.get(Storyboard, storyboard_id)
        if not board:
            raise ValueError(f"storyboard {storyboard_id} not found")
        board.status = "approved"
        board.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        get_bus().publish(
            EventType.STORYBOARD_APPROVED,
            {
                "storyboard_id": board.id,
                "story_id": board.story_id,
                "version": board.version,
                "quality_score": float(board.quality_score or 0),
            },
            producer="storyboard-engine",
        )
        return board

    def get(self, storyboard_id: str) -> Storyboard | None:
        return self.session.get(Storyboard, storyboard_id)

    def list_for_story(self, story_id: str) -> list[Storyboard]:
        return list(
            self.session.scalars(
                select(Storyboard)
                .where(Storyboard.story_id == story_id)
                .order_by(Storyboard.version.desc())
            ).all()
        )

    def _load_story_blueprint(
        self, req: StoryboardRequest
    ) -> tuple[Story | None, StoryBlueprint]:
        story = self.session.get(Story, req.story_id) if req.story_id else None
        if req.blueprint:
            return story, StoryBlueprint.model_validate(req.blueprint)
        if not story:
            raise ValueError("Provide story_id or blueprint")
        return story, StoryBlueprint.model_validate(story.blueprint)

    def _next_version(self, story_id: str) -> int:
        rows = list(
            self.session.scalars(select(Storyboard).where(Storyboard.story_id == story_id)).all()
        )
        if not rows:
            return 1
        return max(int(r.version) for r in rows) + 1

    def _persist_children(self, board: Storyboard, doc: StoryboardDocument) -> None:
        for sc in doc.scenes:
            scene_row = StoryboardScene(
                id=sc.id,
                storyboard_id=board.id,
                sequence_number=sc.sequence,
                start_time_sec=sc.start_time_sec,
                end_time_sec=sc.end_time_sec,
                narrative_function=sc.narrative_function,
                emotional_state=sc.emotional_state,
                scene_config=sc.model_dump(by_alias=True),
            )
            self.session.add(scene_row)
            self.session.flush()
            for sh in sc.shots:
                shot_row = StoryboardShot(
                    id=sh.id,
                    scene_id=scene_row.id,
                    sequence_number=sh.sequence,
                    start_time_sec=sh.start_time_sec,
                    end_time_sec=sh.end_time_sec,
                    shot_config=sh.model_dump(by_alias=True),
                    generation_config=sh.generation.model_dump(),
                )
                self.session.add(shot_row)
        self.session.flush()

        # Asset requirement rows (resolved IDs when present)
        for role, values in [
            ("character", doc.asset_requirements.characters),
            ("location", doc.asset_requirements.locations),
            ("prop", doc.asset_requirements.props),
            ("style", doc.asset_requirements.styles),
        ]:
            for val in values:
                asset_id = val if isinstance(val, str) and len(val) >= 32 else None
                # UUIDs from asset engine are 36 chars; names are not asset ids
                if val and len(str(val)) == 36 and str(val).count("-") == 4:
                    asset_id = str(val)
                else:
                    asset_id = None
                    # Prefer resolved map
                    resolved = doc.resolved_assets or {}
                    if role == "character" and (resolved.get("character") or {}).get("id"):
                        asset_id = resolved["character"]["id"]
                    elif role == "location" and (resolved.get("location") or {}).get("id"):
                        asset_id = resolved["location"]["id"]
                    elif role == "style" and (resolved.get("style") or {}).get("id"):
                        asset_id = resolved["style"]["id"]
                self.session.add(
                    StoryboardAsset(
                        id=str(uuid4()),
                        storyboard_id=board.id,
                        shot_id=None,
                        asset_id=asset_id,
                        asset_role=role,
                        required=True,
                    )
                )
        self.session.flush()

    def _critique_revise_loop(
        self,
        doc: StoryboardDocument,
        req: StoryboardRequest,
        *,
        asset_availability: float,
        max_revisions: int,
    ) -> tuple[StoryboardDocument, Any, Any]:
        critic = critique_storyboard(doc, req)
        quality = evaluate_quality(doc, req, asset_availability=asset_availability)
        doc.quality = quality
        doc.critic = critic

        revisions = 0
        while revisions < max_revisions and (
            quality.overall < 0.8 or critic.suggested_fixes or not critic.hook_visual_interest
        ):
            doc = revise_storyboard(doc, critic, req)
            critic = critique_storyboard(doc, req)
            quality = evaluate_quality(doc, req, asset_availability=asset_availability)
            doc.quality = quality
            doc.critic = critic
            revisions += 1
        return doc, critic, quality

    def _probability_hint(
        self,
        req: StoryboardRequest,
        blueprint: StoryBlueprint,
        doc: StoryboardDocument,
        quality: float,
    ) -> float:
        try:
            result = predict_opportunity(
                opportunity={
                    "trend": blueprint.title,
                    "emotion": blueprint.hook.emotion or "curiosity",
                    "hook": blueprint.hook.hook_text,
                    "hook_type": blueprint.hook.type,
                    "story_pattern": blueprint.template,
                    "platforms": [req.platform],
                    "confidence": req.virality_probability or 0.7,
                    "visual_novelty": doc.pacing.visual_novelty,
                    "cut_rate": doc.pacing.cuts_per_10_sec / 10.0,
                },
                score_breakdown={
                    "virality": req.virality_probability or 0.7,
                    "novelty": doc.pacing.visual_novelty,
                    "growth": 0.7,
                    "competition": 0.5,
                    "character_fit": 0.85,
                    "audience_fit": 0.75,
                    "brand_fit": 0.75,
                },
                platform=req.platform,
            )
            pacing_bonus = 0.05 if doc.pacing.motion_density >= 0.4 else 0.0
            interrupt_bonus = 0.03 if doc.pattern_interrupts else 0.0
            return round(
                min(
                    0.99,
                    0.45 * result.virality_probability
                    + 0.45 * quality
                    + pacing_bonus
                    + interrupt_bonus,
                ),
                4,
            )
        except Exception:  # noqa: BLE001
            return round(quality, 4)


def generate_storyboard(
    session: Session, request: StoryboardRequest | dict[str, Any]
) -> Storyboard:
    return StoryboardService(session).generate(request)
