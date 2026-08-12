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
    ImageArtifact,
    ImageGenerationJob,
    ImageGenerationRequest,
    PromptPackage,
    PromptSpec,
)
from generation_engine.performance import record_outcome
from image_generation_engine.package_adapter import from_prompt_package, to_provider_request
from image_generation_engine.providers import get_image_provider
from image_generation_engine.providers.base import PermanentImageError, TransientImageError
from image_generation_engine.references import validate_and_prepare_references
from image_generation_engine.router import image_fallback_chain, route_image_provider
from image_generation_engine.schemas import ImagePromptPackage, ProviderStrategy
from image_generation_engine.state import transition
from image_generation_engine.validation import perceptual_hash_stub, sha256_file, validate_image_artifact
from prompt_engine.compiler import compile_package
from prompt_engine.schemas import CanonicalGenerationSpec

MAX_ATTEMPTS = 3

COMPOSITION_VARIANTS = [
    {"composition": "close_up", "camera": "closeup"},
    {"composition": "medium", "camera": "medium"},
    {"composition": "low_angle", "camera": "low_angle"},
    {"composition": "over_shoulder", "camera": "over_the_shoulder"},
]


class ImageJobExecutor:
    def __init__(self, session: Session):
        self.session = session

    def process_request(self, request_id: str) -> ImageGenerationRequest:
        req = self.session.get(ImageGenerationRequest, request_id)
        if not req:
            raise ValueError(f"request {request_id} not found")
        jobs = list(
            self.session.scalars(
                select(ImageGenerationJob)
                .where(ImageGenerationJob.request_id == request_id)
                .order_by(ImageGenerationJob.variant_number)
            ).all()
        )
        get_bus().publish(
            EventType.IMAGE_GENERATION_STARTED,
            {"request_id": request_id, "job_count": len(jobs)},
            producer="image-generation-engine",
        )
        for job in jobs:
            if job.status in {"completed", "cancelled", "failed_permanently"}:
                continue
            if job.depends_on:
                ready = True
                for dep in job.depends_on:
                    d = self.session.get(ImageGenerationJob, dep)
                    if not d or d.status != "completed":
                        ready = False
                        break
                if not ready:
                    continue
            self.process_job(job.id)
        self._refresh_request(req)
        return req

    def process_job(self, job_id: str) -> ImageGenerationJob:
        job = self.session.get(ImageGenerationJob, job_id)
        if not job:
            raise ValueError(f"job {job_id} not found")
        req = self.session.get(ImageGenerationRequest, job.request_id)
        assert req is not None
        t0 = time.time()
        try:
            package = self._load_image_package(req, job)
            job.status = transition(job.status, "validating")
            if not package.prompt.positive and not (
                package.provider_prompt.get("parameters") or {}
            ).get("text"):
                if package.generation.mode != "image_editing":
                    raise PermanentImageError("invalid_request: empty positive prompt")

            job.status = transition(job.status, "routing")
            strategy = ProviderStrategy.model_validate(req.provider_strategy or {})
            provider_name = job.provider
            scores = None
            if not provider_name:
                provider_name, scores = route_image_provider(self.session, package, strategy)
                job.provider = provider_name
            job.parameters = {
                **(job.parameters or {}),
                "routing_score": scores,
            }

            artifact = self._run_with_fallback(job, req, package, strategy, t0)
            if artifact:
                get_bus().publish(
                    EventType.IMAGE_TECHNICAL_QA_COMPLETED,
                    {
                        "job_id": job.id,
                        "artifact_id": artifact.id,
                        "ok": bool((artifact.technical_qa or {}).get("ok")),
                        "technical_score": (artifact.technical_qa or {}).get("technical_score"),
                    },
                    producer="image-generation-engine",
                )
            self.session.flush()
            return job
        except Exception as exc:  # noqa: BLE001
            job.status = "failed_permanently"
            job.error = {"message": str(exc), "type": type(exc).__name__}
            job.completed_at = datetime.now(timezone.utc)
            self.session.flush()
            get_bus().publish(
                EventType.IMAGE_GENERATION_FAILED,
                {"job_id": job.id, "error": job.error},
                producer="image-generation-engine",
            )
            return job

    def _run_with_fallback(
        self,
        job: ImageGenerationJob,
        req: ImageGenerationRequest,
        package: ImagePromptPackage,
        strategy: ProviderStrategy,
        t0: float,
    ) -> ImageArtifact | None:
        providers = [job.provider] + image_fallback_chain(strategy, job.provider or "")
        chain: list[str] = []
        seen: set[str] = set()
        for p in providers:
            if p and p not in seen:
                seen.add(p)
                chain.append(p)

        last_error = None
        for i, provider_name in enumerate(chain):
            if i > 0:
                # Budget-aware fallback
                est = get_image_provider(provider_name).estimate_cost(
                    to_provider_request(package, prepared_refs=[])
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
                    EventType.IMAGE_GENERATION_FALLBACK,
                    {
                        "job_id": job.id,
                        "from_provider": job.provider,
                        "to_provider": provider_name,
                    },
                    producer="image-generation-engine",
                )
                package = self._recompile_package(req, job, package, provider_name)
                job.provider = provider_name
                job.status = transition("fallback", "routing")

            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    job.attempt = attempt
                    return self._execute_once(job, req, package, provider_name, t0)
                except TransientImageError as exc:
                    last_error = {"message": str(exc), "retryable": True, "attempt": attempt}
                    job.error = last_error
                    job.status = "retry"
                    get_bus().publish(
                        EventType.IMAGE_GENERATION_RETRIED,
                        {"job_id": job.id, "attempt": attempt, "provider": provider_name},
                        producer="image-generation-engine",
                    )
                    if attempt >= MAX_ATTEMPTS:
                        break
                    job.status = transition("retry", "routing")
                except PermanentImageError as exc:
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
            modality="image",
            success=False,
            latency_ms=int((time.time() - t0) * 1000),
            cost=float(job.actual_cost or 0),
            used_fallback=bool(job.fallback_count),
        )
        get_bus().publish(
            EventType.IMAGE_GENERATION_FAILED,
            {"job_id": job.id, "error": job.error},
            producer="image-generation-engine",
        )
        self.session.flush()
        return None

    def _execute_once(
        self,
        job: ImageGenerationJob,
        req: ImageGenerationRequest,
        package: ImagePromptPackage,
        provider_name: str,
        t0: float,
    ) -> ImageArtifact:
        provider = get_image_provider(provider_name)
        caps = provider.get_capabilities()
        job.provider = provider_name
        job.model = str(caps.get("model") or provider_name)

        package = package.model_copy(deep=True)
        # Apply composition variant from job parameters
        comp = (job.parameters or {}).get("composition_variant")
        if isinstance(comp, dict):
            package.shot = {**(package.shot or {}), **comp}

        est = provider.estimate_cost(to_provider_request(package, prepared_refs=[]))
        job.estimated_cost = est
        max_cost = float((req.budget or {}).get("max_cost_usd") or 999)
        spent = self._spent(req.id)
        if spent + est > max_cost:
            raise PermanentImageError(
                f"budget exceeded: spent={spent} + est={est} > {max_cost}"
            )

        job.status = transition(
            job.status if job.status != "retry" else "routing", "preparing_references"
        )
        limits = caps.get("limits") or {}
        prepared, ref_issues = validate_and_prepare_references(
            self.session,
            package,
            provider=provider_name,
            max_references=int(limits.get("max_references") or 5),
            preserve_identity=bool(
                (package.character_constraints or {}).get("preserve_identity", True)
            ),
        )
        if ref_issues and "character_reference_required" in str(ref_issues):
            raise PermanentImageError("; ".join(ref_issues))
        prepared = provider.prepare_references(prepared)

        provider_req = to_provider_request(package, prepared_refs=prepared)
        issues = provider.validate_request(provider_req)
        if issues:
            raise PermanentImageError("invalid_request: " + "; ".join(issues))

        job.status = transition(job.status, "submitting")
        result = provider.submit(provider_req, seed=job.seed)
        job.provider_job_id = result.provider_job_id
        get_bus().publish(
            EventType.IMAGE_GENERATION_SUBMITTED,
            {
                "job_id": job.id,
                "provider": provider_name,
                "provider_job_id": result.provider_job_id,
            },
            producer="image-generation-engine",
        )

        job.status = transition(job.status, "processing")
        get_bus().publish(
            EventType.IMAGE_GENERATION_PROCESSING,
            {"job_id": job.id, "provider": provider_name},
            producer="image-generation-engine",
        )

        status = provider.get_status(result.provider_job_id)
        if status.status == "failed":
            msg = (status.error or {}).get("message") or "provider failed"
            if any(k in msg for k in ("timeout", "429", "5xx", "network")):
                raise TransientImageError(msg)
            raise PermanentImageError(msg)
        if status.status != "completed" or not status.result_uri:
            raise TransientImageError("timeout: result not ready")

        job.status = transition(job.status, "downloading")
        downloaded = provider.download_result(result.provider_job_id)
        uri = downloaded.result_uri or status.result_uri

        job.status = transition(job.status, "validating_artifact")
        known = self._known_phashes(req.id)
        qa = validate_image_artifact(
            uri,
            expected_aspect=package.generation.aspect_ratio,
            expected_resolution=package.generation.resolution,
            known_hashes=known,
        )
        min_score = float((req.quality or {}).get("minimum_score") or 0.0)
        if not qa.ok or qa.technical_score < min_score:
            raise PermanentImageError(
                f"artifact validation failed: score={qa.technical_score} notes={qa.notes}"
            )

        digest, size = sha256_file(uri)
        probed = qa.probed or {}
        job.actual_cost = downloaded.actual_cost if downloaded.actual_cost is not None else est
        job.latency_ms = int((time.time() - t0) * 1000)
        job.status = transition(job.status, "completed")
        job.completed_at = datetime.now(timezone.utc)
        job.error = None

        parent_id = job.parent_artifact_id
        lineage = {
            **(req.lineage or {}),
            "image_request_id": req.id,
            "image_job_id": job.id,
            "prompt_package_id": package.prompt_package_id,
            "canonical_spec_id": package.canonical_spec_id,
            "storyboard_shot_id": package.storyboard_shot_id or req.storyboard_shot_id,
            "provider": provider_name,
            "model": job.model,
            "seed": job.seed,
            "purpose": package.purpose or req.purpose,
            "parent_artifact_id": parent_id,
        }
        artifact = ImageArtifact(
            id=str(uuid4()),
            generation_job_id=job.id,
            parent_artifact_id=parent_id,
            storage_uri=uri,
            mime_type=str(probed.get("mime_type") or "image/png"),
            width=probed.get("width"),
            height=probed.get("height"),
            file_size_bytes=size,
            sha256=digest,
            phash=str(probed.get("phash") or perceptual_hash_stub(uri)),
            technical_qa=qa.model_dump(),
            provider=provider_name,
            model=job.model,
            prompt_package_id=package.prompt_package_id,
            purpose=package.purpose or req.purpose,
            lineage=lineage,
        )
        self.session.add(artifact)
        self.session.flush()

        get_artifact_registry().register(
            type="image",
            uri=uri,
            source_service="image-generation-engine",
            metadata={"artifact_id": artifact.id, "job_id": job.id, "sha256": digest},
        )
        record_outcome(
            self.session,
            provider=provider_name,
            model=job.model,
            modality="image",
            success=True,
            latency_ms=job.latency_ms,
            cost=float(job.actual_cost or 0),
            used_fallback=bool(job.fallback_count),
            qa_score=float(qa.technical_score),
        )
        get_bus().publish(
            EventType.IMAGE_GENERATION_COMPLETED,
            {
                "request_id": req.id,
                "job_id": job.id,
                "artifact_id": artifact.id,
                "provider": provider_name,
                "cost": float(job.actual_cost or 0),
                "quality_score": qa.technical_score,
            },
            producer="image-generation-engine",
        )
        get_bus().publish(
            EventType.IMAGE_ARTIFACT_CREATED,
            {
                "request_id": req.id,
                "job_id": job.id,
                "artifact_id": artifact.id,
                "provider": provider_name,
                "storage_uri": uri,
                "width": artifact.width,
                "height": artifact.height,
                "quality_score": qa.technical_score,
            },
            producer="image-generation-engine",
        )
        if parent_id:
            get_bus().publish(
                EventType.IMAGE_VERSION_CREATED,
                {
                    "artifact_id": artifact.id,
                    "parent_artifact_id": parent_id,
                    "job_id": job.id,
                },
                producer="image-generation-engine",
            )
            get_bus().publish(
                EventType.IMAGE_EDITED,
                {
                    "artifact_id": artifact.id,
                    "parent_artifact_id": parent_id,
                    "instruction": (package.edit or {}).get("instruction"),
                },
                producer="image-generation-engine",
            )
        self.session.flush()
        return artifact

    def _load_image_package(
        self, req: ImageGenerationRequest, job: ImageGenerationJob
    ) -> ImagePromptPackage:
        if req.image_prompt_package:
            return ImagePromptPackage.model_validate(req.image_prompt_package)
        pid = job.prompt_package_id or req.prompt_package_id
        pkg = self.session.get(PromptPackage, pid)
        if not pkg:
            raise PermanentImageError(f"prompt package {pid} not found")
        return from_prompt_package(pkg)

    def _recompile_package(
        self,
        req: ImageGenerationRequest,
        job: ImageGenerationJob,
        package: ImagePromptPackage,
        provider: str,
    ) -> ImagePromptPackage:
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
        adapter_name = "gpt_image"
        cgs = CanonicalGenerationSpec.model_validate(spec_row.canonical_spec)
        if cgs.modality not in {"image", "thumbnail"}:
            cgs = cgs.model_copy(update={"modality": "image"})
        _, doc = compile_package(cgs, provider=adapter_name)
        new_pkg = PromptPackage(
            id=str(uuid4()),
            prompt_spec_id=spec_row.id,
            provider=adapter_name,
            model=doc.model,
            modality="image",
            provider_prompt=doc.model_dump(),
            version=1,
            lineage={
                **(package.lineage or {}),
                "fallback_for_image_provider": provider,
                "from_prompt_package": package.prompt_package_id,
            },
            status="compiled",
        )
        self.session.add(new_pkg)
        self.session.flush()
        job.prompt_package_id = new_pkg.id
        adapted = from_prompt_package(new_pkg)
        adapted.generation.aspect_ratio = package.generation.aspect_ratio
        adapted.generation.resolution = package.generation.resolution
        adapted.generation.mode = package.generation.mode
        adapted.references = package.references
        adapted.purpose = package.purpose
        adapted.style = package.style
        adapted.environment = package.environment
        adapted.shot = package.shot
        adapted.edit = package.edit
        return adapted

    def _spent(self, request_id: str) -> float:
        jobs = list(
            self.session.scalars(
                select(ImageGenerationJob).where(ImageGenerationJob.request_id == request_id)
            ).all()
        )
        return sum(float(j.actual_cost or 0) for j in jobs if j.actual_cost)

    def _known_phashes(self, request_id: str) -> set[str]:
        jobs = list(
            self.session.scalars(
                select(ImageGenerationJob).where(ImageGenerationJob.request_id == request_id)
            ).all()
        )
        if not jobs:
            return set()
        arts = list(
            self.session.scalars(
                select(ImageArtifact).where(
                    ImageArtifact.generation_job_id.in_([j.id for j in jobs])
                )
            ).all()
        )
        return {a.phash for a in arts if a.phash}

    def _refresh_request(self, req: ImageGenerationRequest) -> None:
        jobs = list(
            self.session.scalars(
                select(ImageGenerationJob).where(ImageGenerationJob.request_id == req.id)
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


def allocate_image_variants(
    *,
    count: int,
    strategy: str,
    primary: str,
    fallbacks: list[str],
    base_seed: int | None = None,
) -> list[dict[str, Any]]:
    plan = []
    seed0 = base_seed if base_seed is not None else random.randint(1, 1_000_000)
    for i in range(1, count + 1):
        provider = primary
        seed = seed0 + (i - 1) if strategy == "same_seed_variation" else random.randint(1, 1_000_000)
        if strategy in {"different_provider", "mixed"} and i > 1 and fallbacks:
            provider = fallbacks[(i - 2) % len(fallbacks)]
        composition = None
        if strategy in {"different_composition", "mixed"}:
            composition = COMPOSITION_VARIANTS[(i - 1) % len(COMPOSITION_VARIANTS)]
        plan.append(
            {
                "variant_number": i,
                "provider": provider,
                "seed": seed,
                "composition_variant": composition,
            }
        )
    return plan
