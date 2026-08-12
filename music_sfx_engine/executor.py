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
from db.models import AudioArtifact, MusicGenerationJob, MusicGenerationRequest, PromptPackage
from generation_engine.performance import record_outcome
from music_sfx_engine.package_adapter import from_prompt_package, music_spec_to_provider_request
from music_sfx_engine.providers import get_music_provider
from music_sfx_engine.providers.base import PermanentMusicError, TransientMusicError
from music_sfx_engine.router import music_fallback_chain, route_music_provider
from music_sfx_engine.schemas import AudioBlueprint, MusicSpecification, ProviderStrategy
from music_sfx_engine.state import transition
from music_sfx_engine.validation import sha256_file, validate_audio_artifact

MAX_ATTEMPTS = 3


class MusicJobExecutor:
    def __init__(self, session: Session):
        self.session = session

    def process_request(self, request_id: str) -> MusicGenerationRequest:
        req = self.session.get(MusicGenerationRequest, request_id)
        if not req:
            raise ValueError(f"request {request_id} not found")
        jobs = list(
            self.session.scalars(
                select(MusicGenerationJob)
                .where(MusicGenerationJob.request_id == request_id)
                .order_by(MusicGenerationJob.variant_number)
            ).all()
        )
        get_bus().publish(
            EventType.MUSIC_GENERATION_STARTED,
            {"request_id": request_id, "job_count": len(jobs)},
            producer="music-sfx-engine",
        )
        for job in jobs:
            if job.status in {"completed", "cancelled", "failed_permanently"}:
                continue
            self.process_job(job.id)
        self._refresh_request(req)
        return req

    def process_job(self, job_id: str) -> MusicGenerationJob:
        job = self.session.get(MusicGenerationJob, job_id)
        if not job:
            raise ValueError(f"job {job_id} not found")
        req = self.session.get(MusicGenerationRequest, job.request_id)
        assert req is not None
        t0 = time.time()
        try:
            spec = self._load_spec(req)
            job.status = transition(job.status, "validating")
            if not spec.genre or spec.duration_sec <= 0:
                raise PermanentMusicError("invalid_request: incomplete music specification")

            job.status = transition(job.status, "routing")
            strategy = ProviderStrategy.model_validate(req.provider_strategy or {})
            provider_name = job.provider
            scores = None
            if not provider_name:
                provider_name, scores = route_music_provider(self.session, spec, strategy)
                job.provider = provider_name
            job.parameters = {**(job.parameters or {}), "routing_score": scores}

            artifact = self._run_with_fallback(job, req, spec, strategy, t0)
            if artifact:
                get_bus().publish(
                    EventType.AUDIO_QUALITY_VALIDATED,
                    {
                        "job_id": job.id,
                        "artifact_id": artifact.id,
                        "ok": bool((artifact.technical_qa or {}).get("ok")),
                        "technical_score": (artifact.technical_qa or {}).get("technical_score"),
                    },
                    producer="music-sfx-engine",
                )
            self.session.flush()
            return job
        except Exception as exc:  # noqa: BLE001
            job.status = "failed_permanently"
            job.error = {"message": str(exc), "type": type(exc).__name__}
            job.completed_at = datetime.now(timezone.utc)
            self.session.flush()
            get_bus().publish(
                EventType.MUSIC_GENERATION_FAILED,
                {"job_id": job.id, "error": job.error},
                producer="music-sfx-engine",
            )
            return job

    def _run_with_fallback(
        self,
        job: MusicGenerationJob,
        req: MusicGenerationRequest,
        spec: MusicSpecification,
        strategy: ProviderStrategy,
        t0: float,
    ) -> AudioArtifact | None:
        providers = [job.provider] + music_fallback_chain(strategy, job.provider or "")
        chain: list[str] = []
        seen: set[str] = set()
        for p in providers:
            if p and p not in seen:
                seen.add(p)
                chain.append(p)

        last_error = None
        for i, provider_name in enumerate(chain):
            if i > 0:
                est = get_music_provider(provider_name).estimate_cost(
                    music_spec_to_provider_request(spec)
                )
                max_cost = float((req.budget or {}).get("max_cost_usd") or 999)
                spent = self._spent(req.id)
                if spent + est > max_cost:
                    last_error = {
                        "message": f"fallback {provider_name} exceeds budget",
                        "retryable": False,
                    }
                    continue
                job.status = "fallback"
                job.fallback_count = int(job.fallback_count or 0) + 1
                get_bus().publish(
                    EventType.MUSIC_GENERATION_FALLBACK,
                    {
                        "job_id": job.id,
                        "from_provider": job.provider,
                        "to_provider": provider_name,
                    },
                    producer="music-sfx-engine",
                )
                job.provider = provider_name
                job.status = transition("fallback", "routing")

            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    job.attempt = attempt
                    return self._execute_once(job, req, spec, provider_name, t0)
                except TransientMusicError as exc:
                    last_error = {"message": str(exc), "retryable": True, "attempt": attempt}
                    job.error = last_error
                    job.status = "retry"
                    if attempt >= MAX_ATTEMPTS:
                        break
                    job.status = transition("retry", "routing")
                except PermanentMusicError as exc:
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
            modality="music",
            success=False,
            latency_ms=int((time.time() - t0) * 1000),
            cost=float(job.actual_cost or 0),
            used_fallback=bool(job.fallback_count),
        )
        get_bus().publish(
            EventType.MUSIC_GENERATION_FAILED,
            {"job_id": job.id, "error": job.error},
            producer="music-sfx-engine",
        )
        self.session.flush()
        return None

    def _execute_once(
        self,
        job: MusicGenerationJob,
        req: MusicGenerationRequest,
        spec: MusicSpecification,
        provider_name: str,
        t0: float,
    ) -> AudioArtifact:
        provider = get_music_provider(provider_name)
        caps = provider.get_capabilities()
        job.provider = provider_name
        job.model = str(caps.get("model") or provider_name)

        provider_req = music_spec_to_provider_request(spec)
        est = provider.estimate_cost(provider_req)
        job.estimated_cost = est
        max_cost = float((req.budget or {}).get("max_cost_usd") or 999)
        spent = self._spent(req.id)
        if spent + est > max_cost:
            raise PermanentMusicError(
                f"budget exceeded: spent={spent} + est={est} > {max_cost}"
            )

        issues = provider.validate_request(provider_req)
        if issues:
            raise PermanentMusicError("invalid_request: " + "; ".join(issues))

        job.status = transition(
            job.status if job.status != "retry" else "routing", "submitting"
        )
        result = provider.submit(provider_req, seed=job.seed)
        job.provider_job_id = result.provider_job_id

        job.status = transition(job.status, "processing")
        status = provider.get_status(result.provider_job_id)
        if status.status == "failed":
            msg = (status.error or {}).get("message") or "provider failed"
            if any(k in msg for k in ("timeout", "429", "5xx", "network")):
                raise TransientMusicError(msg)
            raise PermanentMusicError(msg)
        if status.status != "completed" or not status.result_uri:
            raise TransientMusicError("timeout: result not ready")

        job.status = transition(job.status, "downloading")
        downloaded = provider.get_result(result.provider_job_id)
        uri = downloaded.result_uri or status.result_uri

        job.status = transition(job.status, "validating_artifact")
        qa = validate_audio_artifact(uri, expected_duration=spec.duration_sec)
        min_score = float((req.quality or {}).get("minimum_score") or 0.0)
        if not qa.ok or qa.technical_score < min_score:
            raise PermanentMusicError(
                f"artifact validation failed: score={qa.technical_score} notes={qa.notes}"
            )

        digest, size = sha256_file(uri)
        probed = qa.probed or {}
        job.actual_cost = downloaded.actual_cost if downloaded.actual_cost is not None else est
        job.latency_ms = int((time.time() - t0) * 1000)
        job.status = transition(job.status, "completed")
        job.completed_at = datetime.now(timezone.utc)
        job.error = None

        artifact = AudioArtifact(
            id=str(uuid4()),
            generation_job_id=job.id,
            artifact_type="music",
            storage_uri=uri,
            mime_type="audio/wav",
            duration_sec=probed.get("duration_sec") or spec.duration_sec,
            sample_rate=probed.get("sample_rate") or 44100,
            channels=probed.get("channels") or 2,
            loudness_lufs=probed.get("loudness_lufs"),
            true_peak_db=probed.get("true_peak_db"),
            file_size_bytes=size,
            sha256=digest,
            technical_qa=qa.model_dump(),
            provider=provider_name,
            model=job.model,
            prompt_package_id=job.prompt_package_id or req.prompt_package_id,
            metadata_json={
                "beat_grid": probed.get("beat_grid") or [],
                "segments": spec.segments,
                "genre": spec.genre,
                "tempo_bpm": spec.tempo_bpm,
                "purpose": spec.purpose,
            },
            lineage={
                **(req.lineage or {}),
                "music_request_id": req.id,
                "music_job_id": job.id,
                "provider": provider_name,
                "model": job.model,
                "seed": job.seed,
            },
        )
        self.session.add(artifact)
        self.session.flush()

        get_artifact_registry().register(
            type="audio",
            uri=uri,
            source_service="music-sfx-engine",
            metadata={"artifact_id": artifact.id, "job_id": job.id, "sha256": digest},
        )
        record_outcome(
            self.session,
            provider=provider_name,
            model=job.model,
            modality="music",
            success=True,
            latency_ms=job.latency_ms,
            cost=float(job.actual_cost or 0),
            used_fallback=bool(job.fallback_count),
            qa_score=float(qa.technical_score),
        )
        get_bus().publish(
            EventType.MUSIC_GENERATION_COMPLETED,
            {
                "request_id": req.id,
                "job_id": job.id,
                "artifact_id": artifact.id,
                "provider": provider_name,
                "duration_sec": float(artifact.duration_sec or 0),
                "cost": float(job.actual_cost or 0),
            },
            producer="music-sfx-engine",
        )
        get_bus().publish(
            EventType.MUSIC_ARTIFACT_CREATED,
            {
                "request_id": req.id,
                "job_id": job.id,
                "artifact_id": artifact.id,
                "provider": provider_name,
                "storage_uri": uri,
                "duration_sec": float(artifact.duration_sec or 0),
            },
            producer="music-sfx-engine",
        )
        self.session.flush()
        return artifact

    def _load_spec(self, req: MusicGenerationRequest) -> MusicSpecification:
        if req.music_spec:
            return MusicSpecification.model_validate(req.music_spec)
        bp = AudioBlueprint.model_validate(req.audio_blueprint)
        if bp.music_spec:
            return bp.music_spec
        if req.prompt_package_id:
            pkg = self.session.get(PromptPackage, req.prompt_package_id)
            if pkg:
                return from_prompt_package(pkg)
        raise PermanentMusicError("music specification missing")

    def _spent(self, request_id: str) -> float:
        jobs = list(
            self.session.scalars(
                select(MusicGenerationJob).where(MusicGenerationJob.request_id == request_id)
            ).all()
        )
        return sum(float(j.actual_cost or 0) for j in jobs if j.actual_cost)

    def _refresh_request(self, req: MusicGenerationRequest) -> None:
        jobs = list(
            self.session.scalars(
                select(MusicGenerationJob).where(MusicGenerationJob.request_id == req.id)
            ).all()
        )
        statuses = {j.status for j in jobs}
        if statuses and statuses <= {"completed"}:
            req.status = "completed"
            req.completed_at = datetime.now(timezone.utc)
        elif "failed_permanently" in statuses and not (
            statuses & {"completed", "processing", "queued"}
        ):
            req.status = "failed"
            req.completed_at = datetime.now(timezone.utc)
        elif statuses & {"processing", "submitting", "downloading", "validating_artifact"}:
            req.status = "processing"
        self.session.flush()


def allocate_music_variants(
    *,
    count: int,
    strategy: str,
    primary: str,
    fallbacks: list[str],
) -> list[dict[str, Any]]:
    plan = []
    for i in range(1, count + 1):
        provider = primary
        if strategy in {"different_provider", "mixed"} and i > 1 and fallbacks:
            provider = fallbacks[(i - 2) % len(fallbacks)]
        plan.append(
            {"variant_number": i, "provider": provider, "seed": random.randint(1, 1_000_000)}
        )
    return plan
