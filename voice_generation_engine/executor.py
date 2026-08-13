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
from db.models import VoiceArtifact, VoiceGenerationJob, VoiceGenerationRequest, VoiceProfile
from generation_engine.performance import record_outcome
from voice_generation_engine.registry import ensure_provider_mappings, get_voice_profile, provider_voice_id
from voice_generation_engine.providers import get_voice_provider
from voice_generation_engine.providers.base import PermanentVoiceError, TransientVoiceError
from voice_generation_engine.router import route_voice_provider, voice_fallback_chain
from voice_generation_engine.schemas import (
    VARIANT_EMOTION_DELTAS,
    VARIANT_RATE_DELTAS,
    ProviderStrategy,
    VoiceSpecification,
)
from voice_generation_engine.spec_builder import apply_pronunciations
from voice_generation_engine.state import transition
from voice_generation_engine.timing import voice_spec_to_provider_request
from voice_generation_engine.validation import script_hash, sha256_file, validate_voice_artifact

MAX_ATTEMPTS = 3


class VoiceJobExecutor:
    def __init__(self, session: Session):
        self.session = session

    def process_request(self, request_id: str) -> VoiceGenerationRequest:
        req = self.session.get(VoiceGenerationRequest, request_id)
        if not req:
            raise ValueError(f"request {request_id} not found")
        jobs = list(
            self.session.scalars(
                select(VoiceGenerationJob)
                .where(VoiceGenerationJob.request_id == request_id)
                .order_by(VoiceGenerationJob.variant_number)
            ).all()
        )
        get_bus().publish(
            EventType.VOICE_GENERATION_STARTED,
            {"request_id": request_id, "job_count": len(jobs)},
            producer="voice-generation-engine",
        )
        for job in jobs:
            if job.status in {"completed", "cancelled", "failed_permanently"}:
                continue
            self.process_job(job.id)
        self._refresh_request(req)
        return req

    def process_job(self, job_id: str) -> VoiceGenerationJob:
        job = self.session.get(VoiceGenerationJob, job_id)
        if not job:
            raise ValueError(f"job {job_id} not found")
        req = self.session.get(VoiceGenerationRequest, job.request_id)
        assert req is not None
        t0 = time.time()
        try:
            spec = self._load_spec(req, job)
            job.status = transition(job.status, "validating")
            if not spec.text.strip():
                raise PermanentVoiceError("invalid_request: empty script")

            profile = None
            if spec.voice_profile_id:
                profile = get_voice_profile(self.session, spec.voice_profile_id)
                if profile:
                    ensure_provider_mappings(profile)

            job.status = transition(job.status, "routing")
            strategy = ProviderStrategy.model_validate(req.provider_strategy or {})
            provider_name = job.provider
            scores = None
            if not provider_name:
                provider_name, scores = route_voice_provider(
                    self.session, spec, strategy, profile=profile
                )
                job.provider = provider_name
            job.parameters = {**(job.parameters or {}), "routing_score": scores}

            artifact = self._run_with_fallback(job, req, spec, strategy, profile, t0)
            if artifact:
                get_bus().publish(
                    EventType.VOICE_TECHNICAL_QA_COMPLETED,
                    {
                        "job_id": job.id,
                        "artifact_id": artifact.id,
                        "ok": bool((artifact.technical_qa or {}).get("ok")),
                        "timestamps_available": bool(
                            (artifact.technical_qa or {}).get("timestamps_available")
                        ),
                    },
                    producer="voice-generation-engine",
                )
            self.session.flush()
            return job
        except Exception as exc:  # noqa: BLE001
            job.status = "failed_permanently"
            job.error = {"message": str(exc), "type": type(exc).__name__}
            job.completed_at = datetime.now(timezone.utc)
            self.session.flush()
            get_bus().publish(
                EventType.VOICE_GENERATION_FAILED,
                {"job_id": job.id, "error": job.error},
                producer="voice-generation-engine",
            )
            return job

    def _run_with_fallback(
        self,
        job: VoiceGenerationJob,
        req: VoiceGenerationRequest,
        spec: VoiceSpecification,
        strategy: ProviderStrategy,
        profile: VoiceProfile | None,
        t0: float,
    ) -> VoiceArtifact | None:
        providers = [job.provider] + voice_fallback_chain(strategy, job.provider or "")
        chain: list[str] = []
        seen: set[str] = set()
        for p in providers:
            if p and p not in seen:
                seen.add(p)
                chain.append(p)

        last_error = None
        for i, provider_name in enumerate(chain):
            if i > 0:
                mapped = provider_voice_id(profile, provider_name)
                est = get_voice_provider(provider_name).estimate_cost(
                    voice_spec_to_provider_request(spec, provider_voice_id=mapped)
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
                    EventType.VOICE_GENERATION_FALLBACK,
                    {
                        "job_id": job.id,
                        "from_provider": job.provider,
                        "to_provider": provider_name,
                        "mapped_voice_id": mapped,
                    },
                    producer="voice-generation-engine",
                )
                job.provider = provider_name
                job.status = transition("fallback", "routing")

            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    job.attempt = attempt
                    return self._execute_once(job, req, spec, provider_name, profile, t0)
                except TransientVoiceError as exc:
                    last_error = {"message": str(exc), "retryable": True, "attempt": attempt}
                    job.error = last_error
                    job.status = "retry"
                    get_bus().publish(
                        EventType.VOICE_GENERATION_RETRIED,
                        {"job_id": job.id, "attempt": attempt, "provider": provider_name},
                        producer="voice-generation-engine",
                    )
                    if attempt >= MAX_ATTEMPTS:
                        break
                    job.status = transition("retry", "routing")
                except PermanentVoiceError as exc:
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
            modality="voice",
            success=False,
            latency_ms=int((time.time() - t0) * 1000),
            cost=float(job.actual_cost or 0),
            used_fallback=bool(job.fallback_count),
        )
        get_bus().publish(
            EventType.VOICE_GENERATION_FAILED,
            {"job_id": job.id, "error": job.error},
            producer="voice-generation-engine",
        )
        self.session.flush()
        return None

    def _execute_once(
        self,
        job: VoiceGenerationJob,
        req: VoiceGenerationRequest,
        spec: VoiceSpecification,
        provider_name: str,
        profile: VoiceProfile | None,
        t0: float,
    ) -> VoiceArtifact:
        provider = get_voice_provider(provider_name)
        caps = provider.get_capabilities()
        job.provider = provider_name
        job.model = str(caps.get("model") or provider_name)

        # Apply variant deltas from job parameters
        spec = spec.model_copy(deep=True)
        deltas = (job.parameters or {}).get("variant_deltas") or {}
        if "intensity_delta" in deltas:
            spec.delivery.intensity = max(
                0.0, min(1.0, spec.delivery.intensity + float(deltas["intensity_delta"]))
            )
        if "rate_delta" in deltas:
            spec.delivery.speaking_rate = max(
                0.5, min(2.0, spec.delivery.speaking_rate + float(deltas["rate_delta"]))
            )

        pronounced, applied = apply_pronunciations(
            self.session, spec.text, language=spec.language
        )
        if applied:
            spec.pronunciation = {**spec.pronunciation, **applied}

        mapped_voice = provider_voice_id(profile, provider_name)
        job.provider_voice_id = mapped_voice
        provider_req = voice_spec_to_provider_request(
            spec, provider_voice_id=mapped_voice, pronounced_text=pronounced
        )

        est = provider.estimate_cost(provider_req)
        job.estimated_cost = est
        max_cost = float((req.budget or {}).get("max_cost_usd") or 999)
        spent = self._spent(req.id)
        if spent + est > max_cost:
            raise PermanentVoiceError(
                f"budget exceeded: spent={spent} + est={est} > {max_cost}"
            )

        issues = provider.validate_request(provider_req)
        if issues:
            raise PermanentVoiceError("invalid_request: " + "; ".join(issues))

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
                raise TransientVoiceError(msg)
            raise PermanentVoiceError(msg)
        if status.status != "completed" or not status.result_uri:
            raise TransientVoiceError("timeout: result not ready")

        job.status = transition(job.status, "downloading")
        downloaded = provider.get_result(result.provider_job_id)
        uri = downloaded.result_uri or status.result_uri

        job.status = transition(job.status, "validating_artifact")
        qa = validate_voice_artifact(
            uri, expected_duration=spec.timing.target_duration_sec
        )
        min_score = float((req.quality or {}).get("minimum_score") or 0.0)
        if not qa.ok or qa.technical_score < min_score:
            raise PermanentVoiceError(
                f"artifact validation failed: score={qa.technical_score} notes={qa.notes}"
            )

        digest, size = sha256_file(uri)
        probed = qa.probed or {}
        timestamps = probed.get("timestamps") or (downloaded.metadata or {}).get("timestamps")
        job.actual_cost = downloaded.actual_cost if downloaded.actual_cost is not None else est
        job.latency_ms = int((time.time() - t0) * 1000)
        job.status = transition(job.status, "completed")
        job.completed_at = datetime.now(timezone.utc)
        job.error = None

        sh = script_hash(spec.text)
        artifact = VoiceArtifact(
            id=str(uuid4()),
            generation_job_id=job.id,
            character_id=spec.character_id or req.character_id,
            voice_profile_id=spec.voice_profile_id or req.voice_profile_id,
            artifact_type=spec.voice_type,
            storage_uri=uri,
            mime_type="audio/wav",
            duration_sec=probed.get("duration_sec") or spec.timing.target_duration_sec,
            sample_rate=probed.get("sample_rate") or 48000,
            channels=probed.get("channels") or 1,
            loudness_lufs=probed.get("loudness_lufs"),
            true_peak_db=probed.get("true_peak_db"),
            script_hash=sh,
            timestamps=timestamps,
            file_size_bytes=size,
            sha256=digest,
            technical_qa=qa.model_dump(),
            provider=provider_name,
            model=job.model,
            prompt_package_id=job.prompt_package_id or req.prompt_package_id,
            lineage={
                **(req.lineage or {}),
                "voice_request_id": req.id,
                "voice_job_id": job.id,
                "provider": provider_name,
                "provider_voice_id": mapped_voice,
                "model": job.model,
                "seed": job.seed,
                "dialogue_id": spec.dialogue_id,
                "script_hash": sh,
            },
        )
        self.session.add(artifact)
        self.session.flush()

        get_artifact_registry().register(
            type="voice",
            uri=uri,
            source_service="voice-generation-engine",
            metadata={"artifact_id": artifact.id, "job_id": job.id, "sha256": digest},
        )
        record_outcome(
            self.session,
            provider=provider_name,
            model=job.model,
            modality="voice",
            success=True,
            latency_ms=job.latency_ms,
            cost=float(job.actual_cost or 0),
            used_fallback=bool(job.fallback_count),
            qa_score=float(qa.technical_score),
        )
        get_bus().publish(
            EventType.VOICE_GENERATION_COMPLETED,
            {
                "request_id": req.id,
                "job_id": job.id,
                "artifact_id": artifact.id,
                "provider": provider_name,
                "duration_sec": float(artifact.duration_sec or 0),
                "cost": float(job.actual_cost or 0),
            },
            producer="voice-generation-engine",
        )
        get_bus().publish(
            EventType.VOICE_ARTIFACT_CREATED,
            {
                "request_id": req.id,
                "job_id": job.id,
                "artifact_id": artifact.id,
                "character_id": artifact.character_id,
                "voice_profile_id": artifact.voice_profile_id,
                "provider": provider_name,
                "duration_sec": float(artifact.duration_sec or 0),
                "timestamps_available": bool(timestamps and timestamps.get("words")),
                "storage_uri": uri,
            },
            producer="voice-generation-engine",
        )
        self.session.flush()
        return artifact

    def _load_spec(
        self, req: VoiceGenerationRequest, job: VoiceGenerationJob
    ) -> VoiceSpecification:
        if req.voice_spec:
            return VoiceSpecification.model_validate(req.voice_spec)
        script = req.script or {}
        if script.get("text"):
            return VoiceSpecification.model_validate(
                {
                    "character_id": req.character_id,
                    "voice_profile_id": req.voice_profile_id,
                    "script": {"text": script["text"]},
                    "delivery": script.get("delivery") or {},
                    "dialogue_id": script.get("dialogue_id"),
                }
            )
        raise PermanentVoiceError("voice specification missing")

    def _spent(self, request_id: str) -> float:
        jobs = list(
            self.session.scalars(
                select(VoiceGenerationJob).where(VoiceGenerationJob.request_id == request_id)
            ).all()
        )
        return sum(float(j.actual_cost or 0) for j in jobs if j.actual_cost)

    def _refresh_request(self, req: VoiceGenerationRequest) -> None:
        jobs = list(
            self.session.scalars(
                select(VoiceGenerationJob).where(VoiceGenerationJob.request_id == req.id)
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


def allocate_voice_variants(
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
        deltas = {}
        if strategy in {"different_emotion", "mixed"}:
            deltas["intensity_delta"] = VARIANT_EMOTION_DELTAS[(i - 1) % len(VARIANT_EMOTION_DELTAS)]
        if strategy in {"different_pace", "mixed"}:
            deltas["rate_delta"] = VARIANT_RATE_DELTAS[(i - 1) % len(VARIANT_RATE_DELTAS)]
        plan.append(
            {
                "variant_number": i,
                "provider": provider,
                "seed": random.randint(1, 1_000_000),
                "variant_deltas": deltas,
            }
        )
    return plan
