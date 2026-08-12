from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from db.models import (
    PromptPackage,
    Storyboard,
    VideoArtifact,
    VideoGenerationJob,
    VideoGenerationRequest,
)
from video_generation_engine.executor import VideoJobExecutor, allocate_video_variants
from video_generation_engine.package_adapter import from_prompt_package
from video_generation_engine.router import route_video_provider, video_fallback_chain
from video_generation_engine.schemas import ProviderStrategy, VideoGenerationRequestIn, VideoPromptPackage


class VideoGenerationService:
    def __init__(self, session: Session):
        self.session = session

    def create(self, request: VideoGenerationRequestIn | dict[str, Any]) -> VideoGenerationRequest:
        req_in = (
            request
            if isinstance(request, VideoGenerationRequestIn)
            else VideoGenerationRequestIn.model_validate(request)
        )

        if req_in.idempotency_key:
            existing = self.session.scalar(
                select(VideoGenerationRequest).where(
                    VideoGenerationRequest.idempotency_key == req_in.idempotency_key
                )
            )
            if existing:
                return existing

        package_row, video_pkg = self._resolve_packages(req_in)
        strategy = req_in.provider_strategy
        provider, scores = route_video_provider(self.session, video_pkg, strategy)

        variant_count = int((req_in.variants or {}).get("count") or 1)
        variant_count = max(1, min(variant_count, 8))
        # Budget pre-check for variants
        from video_generation_engine.providers import get_video_provider
        from video_generation_engine.package_adapter import to_provider_request

        est = get_video_provider(provider).estimate_cost(
            to_provider_request(video_pkg, prepared_refs=[])
        )
        max_cost = float((req_in.budget or {}).get("max_cost_usd") or 3.0)
        if est * variant_count > max_cost:
            variant_count = max(1, int(max_cost // max(est, 0.01)))

        lineage = {
            **video_pkg.lineage,
            "prompt_package_id": package_row.id,
            "canonical_spec_id": video_pkg.canonical_spec_id or package_row.prompt_spec_id,
            "storyboard_id": req_in.storyboard_id or video_pkg.lineage.get("storyboard_id"),
            "storyboard_shot_id": req_in.storyboard_shot_id
            or video_pkg.storyboard_shot_id
            or video_pkg.lineage.get("storyboard_shot_id"),
            "character_reference": req_in.character_reference,
        }

        vreq = VideoGenerationRequest(
            id=str(uuid4()),
            storyboard_shot_id=lineage.get("storyboard_shot_id"),
            storyboard_id=lineage.get("storyboard_id"),
            prompt_package_id=package_row.id,
            provider_strategy=strategy.model_dump(),
            variant_count=variant_count,
            budget=req_in.budget,
            quality=req_in.quality,
            priority=req_in.priority,
            status="queued",
            idempotency_key=req_in.idempotency_key,
            video_prompt_package=video_pkg.model_dump(),
            duration_strategy=req_in.duration_strategy,
            continuity=video_pkg.continuity,
            lineage=lineage,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(vreq)
        self.session.flush()

        get_bus().publish(
            EventType.VIDEO_GENERATION_REQUESTED,
            {
                "request_id": vreq.id,
                "prompt_package_id": package_row.id,
                "variants": variant_count,
                "storyboard_shot_id": vreq.storyboard_shot_id,
            },
            producer="video-generation-engine",
        )

        fb = video_fallback_chain(strategy, provider)
        plan = allocate_video_variants(
            count=variant_count,
            strategy=str((req_in.variants or {}).get("strategy") or "mixed"),
            primary=provider,
            fallbacks=fb,
        )
        jobs = []
        for item in plan:
            job = VideoGenerationJob(
                id=str(uuid4()),
                request_id=vreq.id,
                variant_number=item["variant_number"],
                provider=item["provider"],
                status="queued",
                seed=item["seed"],
                prompt_package_id=package_row.id,
                estimated_cost=est,
                generation_parameters={"routing_score": scores},
                depends_on=list(req_in.depends_on_job_ids),
                created_at=datetime.now(timezone.utc),
            )
            self.session.add(job)
            jobs.append(job)
        self.session.flush()

        get_bus().publish(
            EventType.VIDEO_GENERATION_QUEUED,
            {"request_id": vreq.id, "jobs": [j.id for j in jobs]},
            producer="video-generation-engine",
        )

        if req_in.process:
            VideoJobExecutor(self.session).process_request(vreq.id)
            self.session.refresh(vreq)
        return vreq

    def process(self, request_id: str) -> VideoGenerationRequest:
        return VideoJobExecutor(self.session).process_request(request_id)

    def get_request(self, request_id: str) -> VideoGenerationRequest | None:
        return self.session.get(VideoGenerationRequest, request_id)

    def get_job(self, job_id: str) -> VideoGenerationJob | None:
        return self.session.get(VideoGenerationJob, job_id)

    def list_jobs(self, request_id: str) -> list[VideoGenerationJob]:
        return list(
            self.session.scalars(
                select(VideoGenerationJob)
                .where(VideoGenerationJob.request_id == request_id)
                .order_by(VideoGenerationJob.variant_number)
            ).all()
        )

    def list_artifacts(self, request_id: str) -> list[VideoArtifact]:
        jobs = self.list_jobs(request_id)
        if not jobs:
            return []
        return list(
            self.session.scalars(
                select(VideoArtifact).where(
                    VideoArtifact.generation_job_id.in_([j.id for j in jobs])
                )
            ).all()
        )

    def cancel_job(self, job_id: str) -> VideoGenerationJob:
        job = self.session.get(VideoGenerationJob, job_id)
        if not job:
            raise ValueError("job not found")
        if job.status in {"queued", "validating", "routing", "preparing_references"}:
            job.status = "cancelled"
            self.session.flush()
        return job

    def retry_job(self, job_id: str) -> VideoGenerationJob:
        job = self.session.get(VideoGenerationJob, job_id)
        if not job:
            raise ValueError("job not found")
        job.status = "queued"
        job.error = None
        job.attempt = 0
        self.session.flush()
        return VideoJobExecutor(self.session).process_job(job.id)

    def _resolve_packages(
        self, req_in: VideoGenerationRequestIn
    ) -> tuple[PromptPackage, VideoPromptPackage]:
        if req_in.video_prompt_package and not req_in.prompt_package_id:
            vpkg = (
                req_in.video_prompt_package
                if isinstance(req_in.video_prompt_package, VideoPromptPackage)
                else VideoPromptPackage.model_validate(req_in.video_prompt_package)
            )
            if not vpkg.prompt_package_id:
                raise ValueError("video_prompt_package requires prompt_package_id for lineage")
            pkg = self.session.get(PromptPackage, vpkg.prompt_package_id)
            if not pkg:
                raise ValueError("prompt package not found")
            return pkg, vpkg

        if req_in.prompt_package_id:
            pkg = self.session.get(PromptPackage, req_in.prompt_package_id)
            if not pkg:
                rows = list(
                    self.session.scalars(
                        select(PromptPackage).where(
                            PromptPackage.id.startswith(req_in.prompt_package_id)
                        )
                    ).all()
                )
                if len(rows) != 1:
                    raise ValueError("prompt package not found")
                pkg = rows[0]
            return pkg, from_prompt_package(pkg)

        if req_in.storyboard_id:
            from prompt_engine.schemas import CompileRequest
            from prompt_engine.service import PromptService

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
            preferred = req_in.provider_strategy.preferred or req_in.provider_strategy.locked
            # Map video providers → prompt adapters for first compile
            adapter = {"provider_a": "veo", "provider_b": "runway"}.get(preferred or "", "veo")
            packages = PromptService(self.session).compile(
                CompileRequest(
                    storyboard_id=board.id,
                    storyboard_shot_id=req_in.storyboard_shot_id,
                    modality="video",
                    provider=adapter,
                    compile_all_shots=False,
                )
            )
            if not packages:
                raise ValueError("failed to compile video prompt package")
            return packages[0], from_prompt_package(packages[0])

        raise ValueError("prompt_package_id, storyboard_id, or video_prompt_package required")


def create_video_generation(
    session: Session, request: VideoGenerationRequestIn | dict[str, Any]
) -> VideoGenerationRequest:
    return VideoGenerationService(session).create(request)
