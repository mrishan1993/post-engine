from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from db.models import GenerationJob, GenerationRequest, MediaArtifact, PromptPackage, PromptSpec
from generation_engine.artifacts import (
    mime_for,
    register_platform_artifact,
    sha256_file,
    validate_artifact,
)
from generation_engine.performance import record_outcome
from generation_engine.providers.base import PermanentGenerationError, TransientGenerationError
from generation_engine.providers.registry import get_generation_provider
from generation_engine.router import fallback_chain, route_provider
from generation_engine.schemas import ProviderStrategy
from generation_engine.state import transition
from prompt_engine.compiler import compile_package
from prompt_engine.schemas import CanonicalGenerationSpec


RETRYABLE = {"timeout", "rate_limit", "provider_5xx", "network"}
MAX_ATTEMPTS = 3


class JobExecutor:
    def __init__(self, session: Session):
        self.session = session

    def process_request(self, request_id: str) -> GenerationRequest:
        req = self.session.get(GenerationRequest, request_id)
        if not req:
            raise ValueError(f"request {request_id} not found")
        jobs = list(
            self.session.scalars(
                select(GenerationJob)
                .where(GenerationJob.request_id == request_id)
                .order_by(GenerationJob.variant_number)
            ).all()
        )
        get_bus().publish(
            EventType.GENERATION_STARTED,
            {"request_id": request_id, "job_count": len(jobs)},
            producer="generation-engine",
        )
        for job in jobs:
            if job.status in {"approved", "completed", "qa_pending", "cancelled", "failed_permanently"}:
                continue
            # dependency gate
            if job.depends_on:
                deps_ok = True
                for dep_id in job.depends_on:
                    dep = self.session.get(GenerationJob, dep_id)
                    if not dep or dep.status not in {"completed", "qa_pending", "approved"}:
                        deps_ok = False
                        break
                if not deps_ok:
                    continue
            self.process_job(job.id)

        self._refresh_request_status(req)
        return req

    def process_job(self, job_id: str) -> GenerationJob:
        job = self.session.get(GenerationJob, job_id)
        if not job:
            raise ValueError(f"job {job_id} not found")
        req = self.session.get(GenerationRequest, job.request_id)
        assert req is not None

        t0 = time.time()
        queue_sec = max(0.0, (datetime.now(timezone.utc) - job.created_at).total_seconds()) if job.created_at else 0.0

        try:
            job.status = transition(job.status, "validating")
            package = self._load_package(job, req)
            self._validate_package(package, req.modality)

            job.status = transition(job.status, "routing")
            strategy = ProviderStrategy.model_validate(req.provider_strategy or {})
            exclude: list[str] = []
            provider_name = job.provider
            if not provider_name:
                provider_name, scores = route_provider(
                    self.session,
                    modality=req.modality,
                    prompt_package=package.provider_prompt,
                    strategy=strategy,
                )
                job.provider = provider_name
                job.parameters = {**(job.parameters or {}), "routing_score": scores}

            artifact = self._submit_with_retries(job, req, package, strategy, exclude, t0, queue_sec)
            if artifact:
                job.status = transition(job.status, "qa_pending")
                # technical QA already on artifact; mark approved for Phase-0 if ok
                if (artifact.technical_qa or {}).get("ok"):
                    job.status = transition(job.status, "approved")
                get_bus().publish(
                    EventType.GENERATION_QA_COMPLETED,
                    {
                        "job_id": job.id,
                        "artifact_id": artifact.id,
                        "ok": bool((artifact.technical_qa or {}).get("ok")),
                    },
                    producer="generation-engine",
                )
            self.session.flush()
            return job
        except Exception as exc:  # noqa: BLE001
            job.status = "failed_permanently"
            job.error = {"message": str(exc), "type": type(exc).__name__}
            job.completed_at = datetime.now(timezone.utc)
            self.session.flush()
            get_bus().publish(
                EventType.GENERATION_FAILED,
                {"job_id": job.id, "error": job.error},
                producer="generation-engine",
            )
            return job

    def _submit_with_retries(
        self,
        job: GenerationJob,
        req: GenerationRequest,
        package: PromptPackage,
        strategy: ProviderStrategy,
        exclude: list[str],
        t0: float,
        queue_sec: float,
    ) -> MediaArtifact | None:
        chain = [job.provider] + fallback_chain(strategy, job.provider or "", req.modality)
        # unique preserve order
        seen: set[str] = set()
        providers = []
        for p in chain:
            if p and p not in seen and p not in exclude:
                seen.add(p)
                providers.append(p)

        last_error: dict[str, Any] | None = None
        for switch_i, provider_name in enumerate(providers):
            if switch_i > 0:
                job.status = "fallback"
                job.fallback_count = int(job.fallback_count or 0) + 1
                get_bus().publish(
                    EventType.GENERATION_FALLBACK,
                    {
                        "job_id": job.id,
                        "from_provider": job.provider,
                        "to_provider": provider_name,
                    },
                    producer="generation-engine",
                )
                # Recompile prompt for fallback provider (never reuse foreign prompt)
                package = self._recompile_for_provider(package, provider_name)
                job.prompt_package_id = package.id
                job.provider = provider_name
                job.status = transition("fallback", "routing")

            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    return self._execute_once(job, req, package, provider_name, t0, queue_sec)
                except TransientGenerationError as exc:
                    job.retry_count = int(job.retry_count or 0) + 1
                    job.status = "retry"
                    last_error = {"message": str(exc), "retryable": True, "attempt": attempt}
                    job.error = last_error
                    get_bus().publish(
                        EventType.GENERATION_RETRIED,
                        {"job_id": job.id, "attempt": attempt, "provider": provider_name},
                        producer="generation-engine",
                    )
                    if attempt >= MAX_ATTEMPTS:
                        break
                    job.status = transition("retry", "routing")
                except PermanentGenerationError as exc:
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
            modality=req.modality,
            success=False,
            latency_ms=int((time.time() - t0) * 1000),
            cost=float(job.actual_cost or 0),
            used_fallback=bool(job.fallback_count),
        )
        get_bus().publish(
            EventType.GENERATION_FAILED,
            {"job_id": job.id, "error": job.error},
            producer="generation-engine",
        )
        self.session.flush()
        return None

    def _execute_once(
        self,
        job: GenerationJob,
        req: GenerationRequest,
        package: PromptPackage,
        provider_name: str,
        t0: float,
        queue_sec: float,
    ) -> MediaArtifact:
        provider = get_generation_provider(provider_name)
        job.provider = provider_name
        job.model = str((provider.get_capabilities() or {}).get("model") or provider_name)
        job.estimated_cost = provider.estimate_cost(package.provider_prompt)

        # Budget check
        budget = req.budget or {}
        max_cost = float(budget.get("max_cost") or 999)
        spent = self._spent_for_request(req.id)
        if spent + float(job.estimated_cost or 0) > max_cost:
            raise PermanentGenerationError(
                f"budget exceeded: spent={spent} + est={job.estimated_cost} > {max_cost}"
            )

        submit_t = time.time()
        refs = self._ensure_references(package, provider_name)
        result = provider.submit(
            package.provider_prompt,
            seed=job.seed,
            references=refs,
        )
        job.provider_job_id = result.provider_job_id
        job.submitted_at = datetime.now(timezone.utc)
        job.status = transition(job.status if job.status != "retry" else "routing", "submitted")
        get_bus().publish(
            EventType.GENERATION_SUBMITTED,
            {
                "job_id": job.id,
                "provider": provider_name,
                "provider_job_id": result.provider_job_id,
            },
            producer="generation-engine",
        )

        job.status = transition(job.status, "processing")
        get_bus().publish(
            EventType.GENERATION_PROCESSING,
            {"job_id": job.id, "provider": provider_name},
            producer="generation-engine",
        )

        status = provider.get_status(result.provider_job_id)
        if status.status == "failed":
            err = (status.error or {}).get("message") or "provider failed"
            if any(k in err for k in RETRYABLE):
                raise TransientGenerationError(err)
            raise PermanentGenerationError(err)
        if status.status != "completed" or not status.result_uri:
            raise TransientGenerationError("timeout: result not ready")

        provider_sec = time.time() - submit_t
        dl_t = time.time()
        qa = validate_artifact(
            status.result_uri,
            modality=req.modality,
            expected_duration=float(
                (package.provider_prompt.get("parameters") or {}).get("duration_sec") or 0
            )
            or None,
        )
        download_sec = time.time() - dl_t
        if not qa.ok:
            raise PermanentGenerationError(f"artifact validation failed: {qa.notes}")

        digest, size = sha256_file(status.result_uri)
        total_ms = int((time.time() - t0) * 1000)
        job.actual_cost = status.actual_cost if status.actual_cost is not None else job.estimated_cost
        job.latency_ms = total_ms
        job.latency = {
            "queue_sec": round(queue_sec, 3),
            "provider_sec": round(provider_sec, 3),
            "download_sec": round(download_sec, 3),
            "total_sec": round(total_ms / 1000.0, 3),
        }
        job.status = transition(job.status, "completed")
        job.completed_at = datetime.now(timezone.utc)
        job.error = None

        lineage = {
            **(req.lineage or {}),
            "generation_request_id": req.id,
            "generation_job_id": job.id,
            "prompt_package_id": package.id,
            "provider": provider_name,
            "model": job.model,
            "seed": job.seed,
        }
        artifact = MediaArtifact(
            id=str(uuid4()),
            generation_job_id=job.id,
            artifact_type=req.modality,
            storage_uri=status.result_uri,
            mime_type=mime_for(status.result_uri),
            metadata_json={
                "duration_sec": (package.provider_prompt.get("parameters") or {}).get("duration_sec"),
                "aspect_ratio": (package.provider_prompt.get("parameters") or {}).get("aspect_ratio"),
                "stub": True,
            },
            sha256=digest,
            size_bytes=size,
            prompt_package_id=package.id,
            provider=provider_name,
            model=job.model,
            technical_qa=qa.model_dump(),
            lineage=lineage,
        )
        self.session.add(artifact)
        self.session.flush()

        register_platform_artifact(
            uri=status.result_uri,
            artifact_type=req.modality,
            job_id=job.id,
            metadata={"artifact_id": artifact.id, "sha256": digest},
        )
        record_outcome(
            self.session,
            provider=provider_name,
            model=job.model,
            modality=req.modality,
            success=True,
            latency_ms=total_ms,
            cost=float(job.actual_cost or 0),
            used_fallback=bool(job.fallback_count),
            qa_score=1.0 if qa.ok else 0.0,
        )
        get_bus().publish(
            EventType.GENERATION_COMPLETED,
            {
                "job_id": job.id,
                "artifact_id": artifact.id,
                "provider": provider_name,
                "model": job.model,
                "cost": float(job.actual_cost or 0),
            },
            producer="generation-engine",
        )
        get_bus().publish(
            EventType.ARTIFACT_CREATED,
            {
                "artifact_id": artifact.id,
                "job_id": job.id,
                "type": req.modality,
                "storage_uri": status.result_uri,
                "sha256": digest,
            },
            producer="generation-engine",
        )
        self.session.flush()
        return artifact

    def _load_package(self, job: GenerationJob, req: GenerationRequest) -> PromptPackage:
        pid = job.prompt_package_id or req.prompt_package_id
        if not pid:
            raise PermanentGenerationError("missing prompt_package_id")
        pkg = self.session.get(PromptPackage, pid)
        if not pkg:
            raise PermanentGenerationError(f"prompt package {pid} not found")
        return pkg

    def _validate_package(self, package: PromptPackage, modality: str) -> None:
        prompt = package.provider_prompt or {}
        if not prompt.get("positive_prompt") and modality not in {"music"}:
            # voice may use parameters.text
            if not (prompt.get("parameters") or {}).get("text"):
                raise PermanentGenerationError("prompt package missing positive_prompt")
        if package.modality and package.modality != modality and modality != "thumbnail":
            # soft allow mismatch for thumbnail/image
            if not (modality == "image" and package.modality == "thumbnail"):
                pass

    def _recompile_for_provider(self, package: PromptPackage, provider: str) -> PromptPackage:
        if not package.prompt_spec_id:
            return package
        spec_row = self.session.get(PromptSpec, package.prompt_spec_id)
        if not spec_row:
            return package
        cgs = CanonicalGenerationSpec.model_validate(spec_row.canonical_spec)
        _, doc = compile_package(cgs, provider=provider)
        new_pkg = PromptPackage(
            id=str(uuid4()),
            prompt_spec_id=spec_row.id,
            provider=provider,
            model=doc.model,
            modality=doc.modality,
            provider_prompt=doc.model_dump(),
            version=int(package.version or 1) + 1,
            quality_score=package.quality_score,
            estimated_cost=doc.estimate.get("estimated_cost") if doc.estimate else None,
            estimated_latency_sec=doc.estimate.get("estimated_latency_sec") if doc.estimate else None,
            lineage={**(package.lineage or {}), "fallback_from": package.id},
            status="compiled",
        )
        self.session.add(new_pkg)
        self.session.flush()
        return new_pkg

    def _ensure_references(
        self, package: PromptPackage, provider: str
    ) -> list[dict[str, Any]]:
        refs = []
        for asset_id in (package.provider_prompt or {}).get("reference_assets") or []:
            # Phase-0: map internal→provider ref without upload
            refs.append(
                {
                    "internal_asset_id": asset_id,
                    "provider": provider,
                    "provider_asset_id": f"ref_{provider}_{str(asset_id)[:8]}",
                    "status": "active",
                }
            )
        return refs

    def _spent_for_request(self, request_id: str) -> float:
        jobs = list(
            self.session.scalars(
                select(GenerationJob).where(GenerationJob.request_id == request_id)
            ).all()
        )
        return sum(float(j.actual_cost or 0) for j in jobs if j.actual_cost)

    def _refresh_request_status(self, req: GenerationRequest) -> None:
        jobs = list(
            self.session.scalars(
                select(GenerationJob).where(GenerationJob.request_id == req.id)
            ).all()
        )
        if not jobs:
            return
        statuses = {j.status for j in jobs}
        if statuses <= {"approved", "qa_pending", "completed"}:
            req.status = "completed"
        elif "failed_permanently" in statuses and not (
            statuses & {"approved", "qa_pending", "completed", "processing", "queued"}
        ):
            req.status = "failed"
        elif statuses & {"processing", "submitted", "routing", "validating", "retry", "fallback"}:
            req.status = "processing"
        req.updated_at = datetime.now(timezone.utc)
        self.session.flush()


def allocate_variant_plan(
    *,
    count: int,
    strategy: str,
    primary: str,
    modality: str,
    fallbacks: list[str],
) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for i in range(1, count + 1):
        if strategy == "mixed_providers" and i > 1 and fallbacks:
            provider = fallbacks[(i - 2) % len(fallbacks)]
        else:
            provider = primary
        plan.append(
            {
                "variant_number": i,
                "provider": provider,
                "seed": random.randint(1, 1_000_000),
            }
        )
    return plan
