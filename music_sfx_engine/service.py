from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from db.models import (
    AudioArtifact,
    AudioTimelineRow,
    MusicGenerationJob,
    MusicGenerationRequest,
    PromptPackage,
    Story,
    Storyboard,
)
from music_sfx_engine.blueprint import build_audio_blueprint
from music_sfx_engine.executor import MusicJobExecutor, allocate_music_variants
from music_sfx_engine.package_adapter import from_prompt_package, music_spec_to_provider_request
from music_sfx_engine.providers import get_music_provider
from music_sfx_engine.router import music_fallback_chain, route_music_provider
from music_sfx_engine.schemas import (
    AudioBlueprint,
    MusicGenerationRequestIn,
    MusicSpecification,
    ProviderStrategy,
)
from music_sfx_engine.sfx_library import resolve_sfx, search_sfx, seed_sfx_library
from music_sfx_engine.timing import build_audio_timeline


class MusicSfxService:
    def __init__(self, session: Session):
        self.session = session

    def create(self, request: MusicGenerationRequestIn | dict[str, Any]) -> MusicGenerationRequest:
        req_in = (
            request
            if isinstance(request, MusicGenerationRequestIn)
            else MusicGenerationRequestIn.model_validate(request)
        )

        if req_in.idempotency_key:
            existing = self.session.scalar(
                select(MusicGenerationRequest).where(
                    MusicGenerationRequest.idempotency_key == req_in.idempotency_key
                )
            )
            if existing:
                return existing

        blueprint, story_id, storyboard_id, package_id = self._resolve_inputs(req_in)
        music_spec = blueprint.music_spec or MusicSpecification(duration_sec=blueprint.total_duration_sec)

        strategy = req_in.provider_strategy
        provider, scores = route_music_provider(self.session, music_spec, strategy)

        variant_count = int((req_in.variants or {}).get("count") or 1)
        variant_count = max(1, min(variant_count, 6))
        est = get_music_provider(provider).estimate_cost(music_spec_to_provider_request(music_spec))
        max_cost = float((req_in.budget or {}).get("max_cost_usd") or 1.5)
        if est * variant_count > max_cost:
            variant_count = max(1, int(max_cost // max(est, 0.01)))

        lineage = {
            **blueprint.lineage,
            "story_id": story_id,
            "storyboard_id": storyboard_id,
            "prompt_package_id": package_id,
        }

        mreq = MusicGenerationRequest(
            id=str(uuid4()),
            content_id=req_in.content_id,
            story_id=story_id,
            storyboard_id=storyboard_id,
            prompt_package_id=package_id,
            audio_blueprint=blueprint.model_dump(),
            music_spec=music_spec.model_dump(),
            provider_strategy=strategy.model_dump(),
            variant_count=variant_count,
            budget=req_in.budget,
            quality=req_in.quality,
            priority=req_in.priority,
            status="queued",
            idempotency_key=req_in.idempotency_key,
            lineage=lineage,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(mreq)
        self.session.flush()

        get_bus().publish(
            EventType.MUSIC_GENERATION_REQUESTED,
            {
                "request_id": mreq.id,
                "storyboard_id": storyboard_id,
                "variants": variant_count,
                "duration_sec": blueprint.total_duration_sec,
            },
            producer="music-sfx-engine",
        )

        fb = music_fallback_chain(strategy, provider)
        plan = allocate_music_variants(
            count=variant_count,
            strategy=str((req_in.variants or {}).get("strategy") or "different_seed"),
            primary=provider,
            fallbacks=fb,
        )
        for item in plan:
            job = MusicGenerationJob(
                id=str(uuid4()),
                request_id=mreq.id,
                variant_number=item["variant_number"],
                provider=item["provider"],
                status="queued",
                seed=item["seed"],
                prompt_package_id=package_id,
                estimated_cost=est,
                parameters={"routing_score": scores},
                created_at=datetime.now(timezone.utc),
            )
            self.session.add(job)
        self.session.flush()

        if req_in.process:
            MusicJobExecutor(self.session).process_request(mreq.id)
            self.session.refresh(mreq)

        sfx_arts: list[AudioArtifact] = []
        if req_in.resolve_sfx:
            items = (blueprint.sfx or {}).get("items") or []
            get_bus().publish(
                EventType.SFX_REQUESTED,
                {"request_id": mreq.id, "count": len(items)},
                producer="music-sfx-engine",
            )
            sfx_arts = resolve_sfx(self.session, items)

        if req_in.build_timeline and mreq.status == "completed":
            music_arts = self.list_music_artifacts(mreq.id)
            music_id = music_arts[0].id if music_arts else None
            self.create_timeline(
                music_request_id=mreq.id,
                storyboard_id=storyboard_id,
                music_artifact_id=music_id,
                sfx_artifacts=sfx_arts,
                blueprint=blueprint,
            )

        return mreq

    def create_timeline(
        self,
        *,
        music_request_id: str | None = None,
        storyboard_id: str | None = None,
        music_artifact_id: str | None = None,
        sfx_artifacts: list[AudioArtifact] | None = None,
        blueprint: AudioBlueprint | None = None,
        platform: str = "instagram_reels",
    ) -> AudioTimelineRow:
        if blueprint is None and music_request_id:
            req = self.session.get(MusicGenerationRequest, music_request_id)
            if not req:
                raise ValueError("music request not found")
            blueprint = AudioBlueprint.model_validate(req.audio_blueprint)
            storyboard_id = storyboard_id or req.storyboard_id

        if blueprint is None:
            raise ValueError("blueprint required")

        sfx_payload = []
        for a in sfx_artifacts or []:
            sfx_payload.append(
                {
                    "id": a.id,
                    "duration_sec": float(a.duration_sec or 1),
                    "metadata": a.metadata_json or {},
                }
            )

        timeline = build_audio_timeline(
            blueprint=blueprint,
            music_artifact_id=music_artifact_id,
            sfx_artifacts=sfx_payload,
            platform=platform,
        )
        row = AudioTimelineRow(
            id=str(uuid4()),
            storyboard_id=storyboard_id,
            music_request_id=music_request_id,
            duration_sec=timeline.duration_sec,
            tracks=[t.model_dump() for t in timeline.tracks],
            beat_grid=timeline.beat_grid,
            voice_windows=timeline.voice_windows,
            ducking=timeline.ducking,
            loudness_profile=timeline.loudness_profile,
            status="ready",
            lineage={"storyboard_id": storyboard_id, "music_request_id": music_request_id},
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(row)
        self.session.flush()
        get_bus().publish(
            EventType.AUDIO_TIMELINE_CREATED,
            {
                "timeline_id": row.id,
                "storyboard_id": storyboard_id,
                "music_request_id": music_request_id,
                "track_count": len(row.tracks or []),
                "duration_sec": float(row.duration_sec),
            },
            producer="music-sfx-engine",
        )
        return row

    def process(self, request_id: str) -> MusicGenerationRequest:
        return MusicJobExecutor(self.session).process_request(request_id)

    def get_request(self, request_id: str) -> MusicGenerationRequest | None:
        return self.session.get(MusicGenerationRequest, request_id)

    def list_jobs(self, request_id: str) -> list[MusicGenerationJob]:
        return list(
            self.session.scalars(
                select(MusicGenerationJob)
                .where(MusicGenerationJob.request_id == request_id)
                .order_by(MusicGenerationJob.variant_number)
            ).all()
        )

    def list_music_artifacts(self, request_id: str) -> list[AudioArtifact]:
        jobs = self.list_jobs(request_id)
        if not jobs:
            return []
        return list(
            self.session.scalars(
                select(AudioArtifact).where(
                    AudioArtifact.generation_job_id.in_([j.id for j in jobs]),
                    AudioArtifact.artifact_type == "music",
                )
            ).all()
        )

    def list_sfx_for_request(self, request_id: str) -> list[AudioArtifact]:
        req = self.get_request(request_id)
        if not req:
            return []
        # SFX created in same session after music; filter by start_sec metadata near request time
        # Prefer artifacts linked via timeline
        tl = self.session.scalar(
            select(AudioTimelineRow)
            .where(AudioTimelineRow.music_request_id == request_id)
            .order_by(AudioTimelineRow.created_at.desc())
        )
        if not tl:
            return []
        ids = [
            t.get("artifact_id")
            for t in (tl.tracks or [])
            if t.get("type") == "sfx" and t.get("artifact_id")
        ]
        if not ids:
            return []
        return list(
            self.session.scalars(select(AudioArtifact).where(AudioArtifact.id.in_(ids))).all()
        )

    def get_timeline(self, timeline_id: str) -> AudioTimelineRow | None:
        row = self.session.get(AudioTimelineRow, timeline_id)
        if row:
            return row
        rows = list(
            self.session.scalars(
                select(AudioTimelineRow).where(AudioTimelineRow.id.startswith(timeline_id))
            ).all()
        )
        return rows[0] if len(rows) == 1 else None

    def search_sfx_library(
        self,
        *,
        query: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
    ) -> list[Any]:
        seed_sfx_library(self.session)
        return search_sfx(self.session, query=query, category=category, tags=tags)

    def regenerate(self, request_id: str) -> MusicGenerationRequest:
        old = self.get_request(request_id)
        if not old:
            raise ValueError("request not found")
        return self.create(
            MusicGenerationRequestIn(
                story_id=old.story_id,
                storyboard_id=old.storyboard_id,
                prompt_package_id=old.prompt_package_id,
                audio_blueprint=old.audio_blueprint,
                provider_strategy=ProviderStrategy.model_validate(old.provider_strategy or {}),
                variants={"count": old.variant_count},
                budget=old.budget or {},
                quality=old.quality or {},
                priority=old.priority,  # type: ignore[arg-type]
                process=True,
                build_timeline=True,
                resolve_sfx=True,
            )
        )

    def _resolve_inputs(
        self, req_in: MusicGenerationRequestIn
    ) -> tuple[AudioBlueprint, str | None, str | None, str | None]:
        story = None
        board = None
        package_id = req_in.prompt_package_id

        if req_in.storyboard_id:
            board = self.session.get(Storyboard, req_in.storyboard_id)
            if not board:
                rows = list(
                    self.session.scalars(
                        select(Storyboard).where(Storyboard.id.startswith(req_in.storyboard_id))
                    ).all()
                )
                if len(rows) != 1:
                    raise ValueError("storyboard not found")
                board = rows[0]

        if req_in.story_id:
            story = self.session.get(Story, req_in.story_id)
            if not story:
                rows = list(
                    self.session.scalars(
                        select(Story).where(Story.id.startswith(req_in.story_id))
                    ).all()
                )
                if len(rows) != 1:
                    raise ValueError("story not found")
                story = rows[0]

        if board and not story:
            story = self.session.get(Story, board.story_id)

        if req_in.audio_blueprint:
            bp = (
                req_in.audio_blueprint
                if isinstance(req_in.audio_blueprint, AudioBlueprint)
                else AudioBlueprint.model_validate(req_in.audio_blueprint)
            )
            return bp, (story.id if story else None), (board.id if board else None), package_id

        if board or story:
            doc = dict(board.document or {}) if board else {}
            if board:
                doc.setdefault("id", board.id)
                doc.setdefault("story_id", board.story_id)
                doc.setdefault("total_duration_sec", float(board.duration_sec or 0) or None)
            story_bp = dict(story.blueprint or {}) if story else {}
            if story:
                story_bp.setdefault("id", story.id)
                story_bp.setdefault("target_duration_sec", story.target_duration_sec)
            bp = build_audio_blueprint(
                storyboard_doc=doc,
                story_blueprint=story_bp,
                total_duration_sec=float(board.duration_sec) if board and board.duration_sec else None,
            )
            if package_id is None and board:
                # optional: compile suno package for lineage
                from prompt_engine.schemas import CompileRequest
                from prompt_engine.service import PromptService

                try:
                    packages = PromptService(self.session).compile(
                        CompileRequest(
                            storyboard_id=board.id,
                            modality="music",
                            provider="suno",
                            compile_all_shots=False,
                        )
                    )
                    if packages:
                        package_id = packages[0].id
                        # Prefer blueprint duration/mood; keep package for lineage only
                except Exception:  # noqa: BLE001
                    package_id = None
            return bp, (story.id if story else None), (board.id if board else None), package_id

        if package_id:
            pkg = self.session.get(PromptPackage, package_id)
            if not pkg:
                raise ValueError("prompt package not found")
            spec = from_prompt_package(pkg)
            bp = AudioBlueprint(
                total_duration_sec=spec.duration_sec,
                music={"required": True},
                ambience={"required": True},
                sfx={"required": False, "items": []},
                music_spec=spec,
                lineage={"prompt_package_id": pkg.id},
            )
            return bp, None, None, pkg.id

        raise ValueError("storyboard_id, story_id, audio_blueprint, or prompt_package_id required")


def create_music_generation(
    session: Session, request: MusicGenerationRequestIn | dict[str, Any]
) -> MusicGenerationRequest:
    return MusicSfxService(session).create(request)
