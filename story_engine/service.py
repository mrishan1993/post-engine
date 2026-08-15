from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from asset_engine.characters import CharacterRegistry
from db.models import Story, StoryVersion
from prediction.probability import predict_opportunity
from story_engine.critic import critique_blueprint, evaluate_quality, revise_blueprint
from story_engine.generator import build_blueprint
from story_engine.patterns import ensure_default_patterns, find_matching_pattern
from story_engine.schemas import StoryBlueprint, StoryRequest


class StoryService:
    def __init__(self, session: Session):
        self.session = session

    def generate(self, request: StoryRequest | dict[str, Any]) -> list[Story]:
        req = request if isinstance(request, StoryRequest) else StoryRequest.model_validate(request)
        ensure_default_patterns(self.session)
        char_ctx, character_fit = self._load_character_context(req)
        pattern = find_matching_pattern(self.session, req.story_type)

        stories: list[Story] = []
        for i in range(max(1, min(req.candidate_count, 5))):
            blueprint = build_blueprint(
                req,
                character_context=char_ctx,
                variant=i,
                pattern={"structure": pattern.structure} if pattern else None,
            )
            blueprint, critic, quality = self._critique_revise_loop(
                blueprint, req, character_fit=character_fit, max_revisions=req.max_revisions
            )
            # Probability soft-score on narrative features (does not invent metrics)
            pred_score = self._probability_hint(req, blueprint, quality.overall)

            story = Story(
                id=str(uuid4()),
                title=blueprint.title,
                logline=blueprint.logline,
                story_type=req.story_type or blueprint.template,
                status="scored",
                target_duration_sec=req.creative_direction.target_duration_sec,
                blueprint=blueprint.model_dump(),
                quality_score=quality.overall,
                originality_score=quality.originality,
                current_version=1,
                opportunity_id=req.opportunity_id,
                content_brief_id=req.content_brief_id,
                character_ids=[
                    c.character_id
                    for c in req.characters
                    if c.character_id
                ]
                or ([char_ctx["id"]] if char_ctx.get("id") else []),
                platform=req.content_opportunity.platform,
                prediction_snapshot={
                    **req.prediction.model_dump(),
                    "story_probability_hint": pred_score,
                },
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            self.session.add(story)
            self.session.flush()
            self.session.add(
                StoryVersion(
                    id=str(uuid4()),
                    story_id=story.id,
                    version=1,
                    blueprint=blueprint.model_dump(),
                    critic_result=critic.model_dump(),
                    quality_score=quality.overall,
                )
            )
            self.session.flush()
            get_bus().publish(
                EventType.STORY_CREATED,
                {
                    "story_id": story.id,
                    "title": story.title,
                    "quality_score": float(quality.overall),
                    "platform": story.platform,
                    "candidate_index": i,
                },
                producer="story-engine",
            )
            stories.append(story)

        stories.sort(key=lambda s: float(s.quality_score or 0), reverse=True)
        return stories

    def revise(self, story_id: str, *, max_revisions: int = 1) -> Story:
        story = self.session.get(Story, story_id)
        if not story:
            raise ValueError(f"story {story_id} not found")
        req = StoryRequest(
            content_opportunity={
                "topic": story.story_type or "story",
                "platform": story.platform or "instagram_reels",
                "emotion": (story.blueprint or {}).get("hook", {}).get("emotion") or "curiosity",
            },
            creative_direction={
                "target_duration_sec": story.target_duration_sec or 30,
                "format": (story.blueprint or {}).get("format", {}).get("type") or "POV",
            },
            prediction=story.prediction_snapshot or {},
        )
        blueprint = StoryBlueprint.model_validate(story.blueprint)
        char_fit = float((blueprint.quality.character_fit if blueprint.quality else 0.9) or 0.9)
        blueprint, critic, quality = self._critique_revise_loop(
            blueprint, req, character_fit=char_fit, max_revisions=max_revisions
        )
        new_ver = int(story.current_version) + 1
        story.blueprint = blueprint.model_dump()
        story.quality_score = quality.overall
        story.current_version = new_ver
        story.updated_at = datetime.now(timezone.utc)
        self.session.add(
            StoryVersion(
                id=str(uuid4()),
                story_id=story.id,
                version=new_ver,
                blueprint=blueprint.model_dump(),
                critic_result=critic.model_dump(),
                quality_score=quality.overall,
            )
        )
        self.session.flush()
        return story

    def approve(self, story_id: str) -> Story:
        story = self.session.get(Story, story_id)
        if not story:
            raise ValueError(f"story {story_id} not found")
        story.status = "approved"
        story.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        get_bus().publish(
            EventType.STORY_APPROVED,
            {"story_id": story.id, "quality_score": float(story.quality_score or 0)},
            producer="story-engine",
        )
        return story

    def compare(self, story_ids: list[str]) -> list[Story]:
        rows = list(
            self.session.scalars(select(Story).where(Story.id.in_(story_ids))).all()
        )
        rows.sort(key=lambda s: float(s.quality_score or 0), reverse=True)
        return rows

    def select_winner(self, stories: list[Story]) -> Story:
        if not stories:
            raise ValueError("no stories to select")
        # Combine quality with probability hint
        def key(s: Story) -> float:
            hint = float((s.prediction_snapshot or {}).get("story_probability_hint") or 0.5)
            return 0.65 * float(s.quality_score or 0) + 0.35 * hint

        winner = max(stories, key=key)
        for s in stories:
            if s.id != winner.id and s.status == "scored":
                s.status = "rejected"
        winner.status = "approved"
        self.session.flush()
        return winner

    def _critique_revise_loop(
        self,
        blueprint: StoryBlueprint,
        req: StoryRequest,
        *,
        character_fit: float,
        max_revisions: int,
    ) -> tuple[StoryBlueprint, Any, Any]:
        critic = critique_blueprint(blueprint, req)
        quality = evaluate_quality(blueprint, req, character_fit=character_fit)
        blueprint.quality = quality
        blueprint.critic = critic.model_dump()

        revisions = 0
        while (
            revisions < max_revisions
            and (not critic.would_keep_watching or quality.overall < 0.75 or critic.suggested_fixes)
        ):
            blueprint = revise_blueprint(blueprint, critic, req)
            critic = critique_blueprint(blueprint, req)
            quality = evaluate_quality(blueprint, req, character_fit=character_fit)
            blueprint.quality = quality
            blueprint.critic = critic.model_dump()
            revisions += 1
        return blueprint, critic, quality

    def _load_character_context(self, req: StoryRequest) -> tuple[dict[str, Any], float]:
        reg = CharacterRegistry(self.session)
        char = None
        for c in req.characters:
            if c.character_id:
                char = reg.get(c.character_id)
            elif c.character_slug:
                char = reg.by_slug(c.character_slug)
            if char:
                break
        if not char:
            return {"name": "the protagonist", "traits": []}, 0.7
        data = dict(char.canonical_data or {})
        data["id"] = char.id
        data["slug"] = char.slug
        data["name"] = char.name
        data["traits"] = (data.get("personality") or {}).get("traits") or []
        fit = 0.96 if char.status in {"active", "approved"} else 0.8
        # Soft enrich from Universe Intelligence when character belongs to a universe
        if char.universe_id:
            try:
                from universe_engine.schemas import AssembleContextRequest
                from universe_engine.service import UniverseService

                ctx = UniverseService(self.session).assemble_context(
                    AssembleContextRequest(
                        universe_id=char.universe_id,
                        character_ids=[char.id],
                        premise=(req.content_opportunity.topic if req.content_opportunity else None),
                        memory_limit=5,
                    )
                )
                data["universe_context"] = {
                    "memories": ctx.memories,
                    "open_threads": ctx.open_threads,
                    "canon_constraints": ctx.canon_constraints[:8],
                    "relationship_context": ctx.relationship_context,
                    "current_state": (ctx.character_context[0].get("current_state") if ctx.character_context else {}),
                    "visual_context": ctx.visual_context.get(char.slug),
                    "voice_context": ctx.voice_context.get(char.slug),
                }
            except Exception:  # noqa: BLE001
                pass
        return data, fit

    def _probability_hint(
        self, req: StoryRequest, blueprint: StoryBlueprint, quality: float
    ) -> float:
        try:
            result = predict_opportunity(
                opportunity={
                    "trend": req.content_opportunity.topic,
                    "emotion": req.content_opportunity.emotion,
                    "hook": blueprint.hook.hook_text,
                    "hook_type": blueprint.hook.type,
                    "story_pattern": blueprint.template,
                    "lifecycle": req.content_opportunity.trend_stage,
                    "platforms": [req.content_opportunity.platform],
                    "confidence": req.prediction.virality_probability,
                },
                score_breakdown={
                    "virality": req.prediction.virality_probability,
                    "novelty": 0.7,
                    "growth": 0.7,
                    "competition": 0.5,
                    "character_fit": (blueprint.quality.character_fit if blueprint.quality else 0.8),
                    "audience_fit": 0.75,
                    "brand_fit": 0.75,
                },
                lifecycle_stage=req.content_opportunity.trend_stage,
                vertical_slug=None,
            )
            return round(0.5 * result.virality_probability + 0.5 * quality, 4)
        except Exception:  # noqa: BLE001
            return round(quality, 4)


def generate_stories(session: Session, request: StoryRequest | dict[str, Any]) -> list[Story]:
    return StoryService(session).generate(request)
