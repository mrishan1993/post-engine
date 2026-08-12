from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.artifacts.registry import get_artifact_registry
from amp_platform.events import EventType, get_bus
from db.models import (
    PromptPackage,
    PromptSpec,
    VideoArtifact,
    VideoGenerationJob,
    VideoGenerationRequest,
)
from generation_engine.performance import record_outcome
from prompt_engine.compiler import compile_package
from prompt_engine.schemas import CanonicalGenerationSpec
from video_generation_engine.duration import resolve_duration
from video_generation_engine.package_adapter import from_prompt_package, to_provider_request
from video_generation_engine.providers.base import PermanentVideoError, TransientVideoError
from video_generation_engine.providers import get_video_provider
from video_generation_engine.references import validate_and_prepare_references
from video_generation_engine.router import route_video_provider, video_fallback_chain
from video_generation_engine.schemas import (
    CharacterRefMode,
    DurationStrategy,
    ProviderStrategy,
    VideoPromptPackage,
)
from video_generation_engine.state import transition
from video_generation_engine.validation import sha256_file, validate_video_artifact

MAX_ATTEMPTS = 3


class VideoJobExecutor:
    def __init__(self, session: Session):
        self.session = session

    def process_request(self, request_id: str) -> VideoGenerationRequest:
        req = self.session.get(VideoGenerationRequest, request_id)
        if not req:
            raise ValueError(f"request {request_id} not found")
        jobs = list(
            self.session.scalars(
                select(VideoGenerationJob)
                .where(VideoGenerationJob.request_id == request_id)
                .order_by(VideoGenerationJob.variant_number)
            ).all()
        )
        get_bus().publish(
            EventType.VIDEO_GENERATION_STARTED,
            {"request_id": request_id, "job_count": len(jobs)},
            producer="video-generation-engine",
        )
        for job in jobs:
            if job.status in {"completed", "cancelled", "failed_permanently"}:
                continue
            if job.depends_on:
                ready = True
                for dep in job.depends_on:
                    d = self.session.get(VideoGenerationJob, dep)
                    if not d or d.status != "completed":
                        ready = False
                        break
                if not ready:
                    continue
            self.process_job(job.id)
        self._refresh_request(req)
        return req

    def process_job(self, job_id: str) -> VideoGenerationJob:
        job = self.session.get(VideoGenerationJob, job_id)
        if not job:
            raise ValueError(f"job {job_id} not found")
        req = self.session.get(VideoGenerationRequest, job.request_id)
        assert req is not None
        t0 = time.time()
        try:
            package = self._load_video_package(req, job)
            job.status = transition(job.status, "validating")
            if not package.prompt.positive and not (
                package.provider_prompt.get("parameters") or {}
            ).get("text"):
                raise PermanentVideoError("invalid_request: empty positive prompt")

            job.status = transition(job.status, "routing")
            strategy = ProviderStrategy.model_validate(req.provider_strategy or {})
            provider_name = job.provider
            scores = None
            if not provider_name:
                provider_name, scores = route_video_provider(self.session, package, strategy)
                job.provider = provider_name
            job.generation_parameters = {
                **(job.generation_parameters or {}),
                "routing_score": scores,
            }

            artifact = self._run_with_fallback(job, req, package, strategy, t0)
            if artifact:
                get_bus().publish(
                    EventType.VIDEO_TECHNICAL_QA_COMPLETED,
                    {
                        "job_id": job.id,
                        "artifact_id": artifact.id,
                        "ok": bool((artifact.technical_qa or {}).get("ok")),
                    },
                    producer="video-generation-engine",
                )
            self.session.flush()
            return job
        except Exception as exc:  # noqa: BLE001
            job.status = "failed_permanently"
            job.error = {"message": str(exc), "type": type(exc).__name__}
            job.completed_at = datetime.now(timezone.utc)
            self.session.flush()
            get_bus().publish(
                EventType.VIDEO_GENERATION_FAILED,
                {"job_id": job.id, "error": job.error},
                producer="video-generation-engine",
            )
            return job

    def _run_with_fallback(
        self,
        job: VideoGenerationJob,
        req: VideoGenerationRequest,
        package: VideoPromptPackage,
        strategy: ProviderStrategy,
        t0: float,
    ) -> VideoArtifact | None:
        providers = [job.provider] + video_fallback_chain(strategy, job.provider or "")
        seen: set[str] = set()
        chain = [p for p in providers if p and p not in seen and not seen.add(p)]  # type: ignore[func-returns-value]
        # fix unique preserve
        chain = []
        seen = set()
        for p in providers:
            if p and p not in seen:
                seen.add(p)
                chain.append(p)

        last_error = None
        for i, provider_name in enumerate(chain):
            if i > 0:
                job.status = "fallback"
                job.fallback_count = int(job.fallback_count or 0) + 1
                get_bus().publish(
                    EventType.VIDEO_GENERATION_FALLBACK,
                    {
                        "job_id": job.id,
                        "from_provider": job.provider,
                        "to_provider": provider_name,
                    },
                    producer="video-generation-engine",
                )
                package = self._recompile_package(req, job, package, provider_name)
                job.provider = provider_name
                job.status = transition("fallback", "routing")

            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    job.attempt = attempt
                    return self._execute_once(job, req, package, provider_name, t0)
                except TransientVideoError as exc:
                    last_error = {"message": str(exc), "retryable": True, "attempt": attempt}
                    job.error = last_error
                    job.status = "retry"
                    get_bus().publish(
                        EventType.VIDEO_GENERATION_RETRIED,
                        {"job_id": job.id, "attempt": attempt, "provider": provider_name},
                        producer="video-generation-engine",
                    )
                    if attempt >= MAX_ATTEMPTS:
                        break
                    job.status = transition("retry", "routing")
                except PermanentVideoError as exc:
                    last_error = {"message": str(exc), "retryable": False}
                    job.error = last_error
                    break

        job.status = "failed_permanently"
        job.error = last_error or {"message": "all providers failed"}
        job.completed_at = datetime.now(timezone.utc)
        record_outcome(
            self.session,
            provider=job.provider or "unknown",
            model=job.model,
            modality="video",
            success=False,
            latency_ms=int((time.time() - t0) * 1000),
            cost=float(job.actual_cost or 0),
            used_fallback=bool(job.fallback_count),
        )
        get_bus().publish(
            EventType.VIDEO_GENERATION_FAILED,
            {"job_id": job.id, "error": job.error},
            producer="video-generation-engine",
        )
        self.session.flush()
        return None

    def _execute_once(
        self,
        job: VideoGenerationJob,
        req: VideoGenerationRequest,
        package: VideoPromptPackage,
        provider_name: str,
        t0: float,
    ) -> VideoArtifact:
        provider = get_video_provider(provider_name)
        caps = provider.get_capabilities()
        job.provider = provider_name
        job.model = str(caps.get("model") or provider_name)

        # Duration strategy (explicit)
        strategy = (req.duration_strategy or "nearest")  # type: ignore[assignment]
        dur_info = resolve_duration(
            package.generation.duration_sec,
            provider_name,
            strategy=strategy,  # type: ignore[arg-type]
        )
        package = package.model_copy(deep=True)
        package.generation.duration_sec = float(dur_info["resolved"])
        job.generation_parameters = {
            **(job.generation_parameters or {}),
            "duration_resolution": dur_info,
        }

        # Budget
        est = provider.estimate_cost(
            to_provider_request(package, prepared_refs=[])
        )
        job.estimated_cost = est
        max_cost = float((req.budget or {}).get("max_cost_usd") or 999)
        spent = self._spent(req.id)
        if spent + est > max_cost:
            raise PermanentVideoError(
                f"budget exceeded: spent={spent} + est={est} > {max_cost}"
            )

        job.status = transition(job.status if job.status != "retry" else "routing", "preparing_references")
        limits = caps.get("limits") or {}
        prepared, ref_issues = validate_and_prepare_references(
            self.session,
            package,
            provider=provider_name,
            character_mode=(req.lineage or {}).get("character_reference")
            or "character_reference_optional",  # type: ignore[arg-type]
            max_references=int(limits.get("max_references") or 4),
        )
        if ref_issues and "character_reference_required" in str(ref_issues):
            raise PermanentVideoError("; ".join(ref_issues))
        prepared = provider.prepare_references(prepared)

        provider_req = to_provider_request(package, prepared_refs=prepared)
        issues = provider.validate_request(provider_req)
        if issues:
            raise PermanentVideoError("invalid_request: " + "; ".join(issues))

        job.status = transition(job.status, "submitting")
        result = provider.submit(provider_req, seed=job.seed)
        job.provider_job_id = result.provider_job_id
        get_bus().publish(
            EventType.VIDEO_GENERATION_SUBMITTED,
            {
                "job_id": job.id,
                "provider": provider_name,
                "provider_job_id": result.provider_job_id,
            },
            producer="video-generation-engine",
        )

        job.status = transition(job.status, "processing")
        get_bus().publish(
            EventType.VIDEO_GENERATION_PROCESSING,
            {"job_id": job.id, "provider": provider_name},
            producer="video-generation-engine",
        )

        status = provider.get_status(result.provider_job_id)
        if status.status == "failed":
            msg = (status.error or {}).get("message") or "provider failed"
            if any(k in msg for k in ("timeout", "429", "5xx", "network")):
                raise TransientVideoError(msg)
            raise PermanentVideoError(msg)
        if status.status != "completed" or not status.result_uri:
            raise TransientVideoError("timeout: result not ready")

        job.status = transition(job.status, "downloading")
        downloaded = provider.download_result(result.provider_job_id)
        uri = downloaded.result_uri or status.result_uri

        job.status = transition(job.status, "validating_artifact")
        qa = validate_video_artifact(
            uri,
            expected_duration=package.generation.duration_sec,
            expected_aspect=package.generation.aspect_ratio,
            expected_resolution=package.generation.resolution,
            expected_fps=package.generation.fps,
        )
        if not qa.ok:
            raise PermanentVideoError(f"artifact validation failed: {qa.notes}")

        digest, size = sha256_file(uri)
        probed = qa.probed or {}
        job.actual_cost = downloaded.actual_cost if downloaded.actual_cost is not None else est
        job.latency_ms = int((time.time() - t0) * 1000)
        job.status = transition(job.status, "completed")
        job.completed_at = datetime.now(timezone.utc)
        job.error = None

        lineage = {
            **(req.lineage or {}),
            "video_request_id": req.id,
            "video_job_id": job.id,
            "prompt_package_id": package.prompt_package_id,
            "canonical_spec_id": package.canonical_spec_id,
            "storyboard_shot_id": package.storyboard_shot_id or req.storyboard_shot_id,
            "provider": provider_name,
            "model": job.model,
            "seed": job.seed,
            "duration_resolution": dur_info,
        }
        artifact = VideoArtifact(
            id=str(uuid4()),
            generation_job_id=job.id,
            storage_uri=uri,
            mime_type="video/mp4",
            width=probed.get("width"),
            height=probed.get("height"),
            duration_sec=probed.get("duration_sec") or package.generation.duration_sec,
            fps=probed.get("fps") or package.generation.fps,
            file_size_bytes=size,
            sha256=digest,
            technical_qa=qa.model_dump(),
            provider=provider_name,
            model=job.model,
            prompt_package_id=package.prompt_package_id,
            lineage=lineage,
        )
        self.session.add(artifact)
        self.session.flush()

        get_artifact_registry().register(
            type="video",
            uri=uri,
            source_service="video-generation-engine",
            metadata={"artifact_id": artifact.id, "job_id": job.id, "sha256": digest},
        )
        record_outcome(
            self.session,
            provider=provider_name,
            model=job.model,
            modality="video",
            success=True,
            latency_ms=job.latency_ms,
            cost=float(job.actual_cost or 0),
            used_fallback=bool(job.fallback_count),
            qa_score=1.0,
        )
        get_bus().publish(
            EventType.VIDEO_GENERATION_COMPLETED,
            {
                "request_id": req.id,
                "job_id": job.id,
                "artifact_id": artifact.id,
                "provider": provider_name,
                "duration_sec": float(artifact.duration_sec or 0),
                "cost": float(job.actual_cost or 0),
            },
            producer="video-generation-engine",
        )
        get_bus().publish(
            EventType.VIDEO_ARTIFACT_CREATED,
            {
                "request_id": req.id,
                "job_id": job.id,
                "artifact_id": artifact.id,
                "provider": provider_name,
                "duration_sec": float(artifact.duration_sec or 0),
                "storage_uri": uri,
                "width": artifact.width,
                "height": artifact.height,
            },
            producer="video-generation-engine",
        )
        self.session.flush()
        return artifact

    def _load_video_package(
        self, req: VideoGenerationRequest, job: VideoGenerationJob
    ) -> VideoPromptPackage:
        if req.video_prompt_package:
            return VideoPromptPackage.model_validate(req.video_prompt_package)
        pid = job.prompt_package_id or req.prompt_package_id
        pkg = self.session.get(PromptPackage, pid)
        if not pkg:
            raise PermanentVideoError(f"prompt package {pid} not found")
        return from_prompt_package(pkg)

    def _recompile_package(
        self,
        req: VideoGenerationRequest,
        job: VideoGenerationJob,
        package: VideoPromptPackage,
        provider: str,
    ) -> VideoPromptPackage:
        """Fallback: recompile via Prompt Engine for new provider — never reuse foreign prompt."""
        if not package.canonical_spec_id and not package.prompt_package_id:
            return package
        spec_id = package.canonical_spec_id
        if not spec_id and package.prompt_package_id:
            old = self.session.get(PromptPackage, package.prompt_package_id)
            spec_id = old.prompt_spec_id if old else None
        if not spec_id:
            return package
        spec_row = self.session.get(PromptSpec, spec_id)
        if not spec_row:
            return package
        # Map provider_a/b to prompt adapters veo/runway for compilation flavor
        adapter_name = {"provider_a": "veo", "provider_b": "runway"}.get(provider, "veo")
        cgs = CanonicalGenerationSpec.model_validate(spec_row.canonical_spec)
        _, doc = compile_package(cgs, provider=adapter_name)
        new_pkg = PromptPackage(
            id=str(uuid4()),
            prompt_spec_id=spec_row.id,
            provider=adapter_name,
            model=doc.model,
            modality="video",
            provider_prompt=doc.model_dump(),
            version=1,
            lineage={
                **(package.lineage or {}),
                "fallback_for_video_provider": provider,
                "from_prompt_package": package.prompt_package_id,
            },
            status="compiled",
        )
        self.session.add(new_pkg)
        self.session.flush()
        job.prompt_package_id = new_pkg.id
        adapted = from_prompt_package(new_pkg)
        # Preserve resolved duration/aspect from current package
        adapted.generation.duration_sec = package.generation.duration_sec
        adapted.generation.aspect_ratio = package.generation.aspect_ratio
        adapted.generation.resolution = package.generation.resolution
        adapted.generation.fps = package.generation.fps
        adapted.generation.mode = package.generation.mode
        adapted.references = package.references
        adapted.frames = package.frames
        adapted.continuity = package.continuity
        return adapted

    def _spent(self, request_id: str) -> float:
        jobs = list(
            self.session.scalars(
                select(VideoGenerationJob).where(VideoGenerationJob.request_id == request_id)
            ).all()
        )
        return sum(float(j.actual_cost or 0) for j in jobs if j.actual_cost)

    def _refresh_request(self, req: VideoGenerationRequest) -> None:
        jobs = list(
            self.session.scalars(
                select(VideoGenerationJob).where(VideoGenerationJob.request_id == req.id)
            ).all()
        )
        statuses = {j.status for j in jobs}
        if statuses and statuses <= {"completed"}:
            req.status = "completed"
            req.completed_at = datetime.now(timezone.utc)
        elif "failed_permanently" in statuses and not (statuses & {"completed", "processing", "queued"}):
            req.status = "failed"
            req.completed_at = datetime.now(timezone.utc)
        elif statuses & {"processing", "submitting", "downloading", "validating_artifact"}:
            req.status = "processing"
        self.session.flush()


def allocate_video_variants(
    *,
    count: int,
    strategy: str,
    primary: str,
    fallbacks: list[str],
) -> list[dict[str, Any]]:
    plan = []
    for i in range(1, count + 1):
        if strategy == "mixed" and i > 1 and fallbacks:
            provider = fallbacks[(i - 2) % len(fallbacks)]
        else:
            provider = primary
        plan.append({"variant_number": i, "provider": provider, "seed": random.randint(1, 1_000_000)})
    return plan
