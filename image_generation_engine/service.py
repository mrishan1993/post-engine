from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from db.models import (
    ImageArtifact,
    ImageGenerationJob,
    ImageGenerationRequest,
    PromptPackage,
    Storyboard,
)
from image_generation_engine.executor import ImageJobExecutor, allocate_image_variants
from image_generation_engine.package_adapter import from_prompt_package, to_provider_request
from image_generation_engine.providers import get_image_provider
from image_generation_engine.router import image_fallback_chain, route_image_provider
from image_generation_engine.schemas import (
    ImageEditRequestIn,
    ImageGenerationRequestIn,
    ImagePromptBlock,
    ImagePromptPackage,
    ImageReference,
    ProviderStrategy,
)


class ImageGenerationService:
    def __init__(self, session: Session):
        self.session = session

    def create(self, request: ImageGenerationRequestIn | dict[str, Any]) -> ImageGenerationRequest:
        req_in = (
            request
            if isinstance(request, ImageGenerationRequestIn)
            else ImageGenerationRequestIn.model_validate(request)
        )

        if req_in.idempotency_key:
            existing = self.session.scalar(
                select(ImageGenerationRequest).where(
                    ImageGenerationRequest.idempotency_key == req_in.idempotency_key
                )
            )
            if existing:
                return existing

        package_row, image_pkg = self._resolve_packages(req_in)
        if req_in.purpose:
            image_pkg = image_pkg.model_copy(update={"purpose": req_in.purpose})

        strategy = req_in.provider_strategy
        provider, scores = route_image_provider(self.session, image_pkg, strategy)

        variant_count = int((req_in.variants or {}).get("count") or 1)
        variant_count = max(1, min(variant_count, 8))
        est = get_image_provider(provider).estimate_cost(
            to_provider_request(image_pkg, prepared_refs=[])
        )
        max_cost = float((req_in.budget or {}).get("max_cost_usd") or 2.0)
        if est * variant_count > max_cost:
            variant_count = max(1, int(max_cost // max(est, 0.01)))

        lineage = {
            **image_pkg.lineage,
            "prompt_package_id": package_row.id,
            "canonical_spec_id": image_pkg.canonical_spec_id or package_row.prompt_spec_id,
            "storyboard_id": req_in.storyboard_id or image_pkg.lineage.get("storyboard_id"),
            "storyboard_shot_id": req_in.storyboard_shot_id
            or image_pkg.storyboard_shot_id
            or image_pkg.lineage.get("storyboard_shot_id"),
            "purpose": image_pkg.purpose,
        }

        ireq = ImageGenerationRequest(
            id=str(uuid4()),
            purpose=image_pkg.purpose,
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
            image_prompt_package=image_pkg.model_dump(),
            lineage=lineage,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(ireq)
        self.session.flush()

        get_bus().publish(
            EventType.IMAGE_GENERATION_REQUESTED,
            {
                "request_id": ireq.id,
                "prompt_package_id": package_row.id,
                "variants": variant_count,
                "purpose": ireq.purpose,
                "storyboard_shot_id": ireq.storyboard_shot_id,
            },
            producer="image-generation-engine",
        )

        fb = image_fallback_chain(strategy, provider)
        plan = allocate_image_variants(
            count=variant_count,
            strategy=str((req_in.variants or {}).get("strategy") or "different_seed"),
            primary=provider,
            fallbacks=fb,
        )
        jobs = []
        for item in plan:
            job = ImageGenerationJob(
                id=str(uuid4()),
                request_id=ireq.id,
                variant_number=item["variant_number"],
                provider=item["provider"],
                status="queued",
                seed=item["seed"],
                prompt_package_id=package_row.id,
                estimated_cost=est,
                parameters={
                    "routing_score": scores,
                    "composition_variant": item.get("composition_variant"),
                },
                depends_on=list(req_in.depends_on_job_ids),
                created_at=datetime.now(timezone.utc),
            )
            self.session.add(job)
            jobs.append(job)
        self.session.flush()

        get_bus().publish(
            EventType.IMAGE_GENERATION_QUEUED,
            {"request_id": ireq.id, "jobs": [j.id for j in jobs]},
            producer="image-generation-engine",
        )

        if req_in.process:
            ImageJobExecutor(self.session).process_request(ireq.id)
            self.session.refresh(ireq)
        return ireq

    def edit(self, request: ImageEditRequestIn | dict[str, Any]) -> ImageGenerationRequest:
        req_in = (
            request
            if isinstance(request, ImageEditRequestIn)
            else ImageEditRequestIn.model_validate(request)
        )
        parent = self.session.get(ImageArtifact, req_in.artifact_id)
        if not parent:
            rows = list(
                self.session.scalars(
                    select(ImageArtifact).where(ImageArtifact.id.startswith(req_in.artifact_id))
                ).all()
            )
            if len(rows) != 1:
                raise ValueError("artifact not found")
            parent = rows[0]

        parent_job = self.session.get(ImageGenerationJob, parent.generation_job_id)
        parent_req = (
            self.session.get(ImageGenerationRequest, parent_job.request_id) if parent_job else None
        )
        package_id = parent.prompt_package_id or (parent_req.prompt_package_id if parent_req else None)
        if not package_id:
            raise ValueError("parent artifact missing prompt_package_id")

        base_pkg = None
        if parent_req and parent_req.image_prompt_package:
            base_pkg = ImagePromptPackage.model_validate(parent_req.image_prompt_package)
        else:
            pkg = self.session.get(PromptPackage, package_id)
            if not pkg:
                raise ValueError("prompt package not found")
            base_pkg = from_prompt_package(pkg)

        edit_pkg = base_pkg.model_copy(deep=True)
        edit_pkg.purpose = "edit"
        edit_pkg.generation.mode = "image_editing"
        edit_pkg.edit = {
            "instruction": req_in.instruction,
            "mask_asset_id": req_in.mask_asset_id,
            "source_artifact_id": parent.id,
        }
        edit_pkg.prompt = ImagePromptBlock(
            positive=f"Edit: {req_in.instruction}. {edit_pkg.prompt.positive}",
            negative=edit_pkg.prompt.negative,
        )
        edit_pkg.references = list(edit_pkg.references) + [
            ImageReference(asset_id=parent.id, role="source", score=0.9)
        ]

        ireq = self.create(
            ImageGenerationRequestIn(
                prompt_package_id=package_id,
                image_prompt_package=edit_pkg,
                purpose="edit",
                provider_strategy=req_in.provider_strategy,
                variants={"count": 1, "strategy": "different_seed"},
                budget=req_in.budget,
                quality={"minimum_score": 0.7},
                process=False,
            )
        )
        # Attach parent on jobs before processing
        for job in self.list_jobs(ireq.id):
            job.parent_artifact_id = parent.id
        self.session.flush()

        if req_in.process:
            ImageJobExecutor(self.session).process_request(ireq.id)
            self.session.refresh(ireq)
        return ireq

    def process(self, request_id: str) -> ImageGenerationRequest:
        return ImageJobExecutor(self.session).process_request(request_id)

    def get_request(self, request_id: str) -> ImageGenerationRequest | None:
        return self.session.get(ImageGenerationRequest, request_id)

    def get_job(self, job_id: str) -> ImageGenerationJob | None:
        return self.session.get(ImageGenerationJob, job_id)

    def list_jobs(self, request_id: str) -> list[ImageGenerationJob]:
        return list(
            self.session.scalars(
                select(ImageGenerationJob)
                .where(ImageGenerationJob.request_id == request_id)
                .order_by(ImageGenerationJob.variant_number)
            ).all()
        )

    def list_artifacts(self, request_id: str) -> list[ImageArtifact]:
        jobs = self.list_jobs(request_id)
        if not jobs:
            return []
        return list(
            self.session.scalars(
                select(ImageArtifact).where(
                    ImageArtifact.generation_job_id.in_([j.id for j in jobs])
                )
            ).all()
        )

    def cancel_job(self, job_id: str) -> ImageGenerationJob:
        job = self.session.get(ImageGenerationJob, job_id)
        if not job:
            raise ValueError("job not found")
        if job.status in {"queued", "validating", "routing", "preparing_references"}:
            job.status = "cancelled"
            self.session.flush()
        return job

    def retry_job(self, job_id: str) -> ImageGenerationJob:
        job = self.session.get(ImageGenerationJob, job_id)
        if not job:
            raise ValueError("job not found")
        job.status = "queued"
        job.error = None
        job.attempt = 0
        self.session.flush()
        return ImageJobExecutor(self.session).process_job(job.id)

    def regenerate(self, request_id: str) -> ImageGenerationRequest:
        old = self.get_request(request_id)
        if not old:
            raise ValueError("request not found")
        return self.create(
            ImageGenerationRequestIn(
                prompt_package_id=old.prompt_package_id,
                image_prompt_package=old.image_prompt_package,
                storyboard_id=old.storyboard_id,
                storyboard_shot_id=old.storyboard_shot_id,
                purpose=old.purpose,  # type: ignore[arg-type]
                provider_strategy=ProviderStrategy.model_validate(old.provider_strategy or {}),
                variants={"count": old.variant_count, "strategy": "different_seed"},
                quality=old.quality or {},
                budget=old.budget or {},
                priority=old.priority,  # type: ignore[arg-type]
                process=True,
            )
        )

    def _resolve_packages(
        self, req_in: ImageGenerationRequestIn
    ) -> tuple[PromptPackage, ImagePromptPackage]:
        if req_in.image_prompt_package and not req_in.prompt_package_id:
            ipkg = (
                req_in.image_prompt_package
                if isinstance(req_in.image_prompt_package, ImagePromptPackage)
                else ImagePromptPackage.model_validate(req_in.image_prompt_package)
            )
            if not ipkg.prompt_package_id:
                raise ValueError("image_prompt_package requires prompt_package_id for lineage")
            pkg = self.session.get(PromptPackage, ipkg.prompt_package_id)
            if not pkg:
                raise ValueError("prompt package not found")
            return pkg, ipkg

        if req_in.image_prompt_package and req_in.prompt_package_id:
            pkg = self.session.get(PromptPackage, req_in.prompt_package_id)
            if not pkg:
                raise ValueError("prompt package not found")
            ipkg = (
                req_in.image_prompt_package
                if isinstance(req_in.image_prompt_package, ImagePromptPackage)
                else ImagePromptPackage.model_validate(req_in.image_prompt_package)
            )
            if not ipkg.prompt_package_id:
                ipkg = ipkg.model_copy(update={"prompt_package_id": pkg.id})
            return pkg, ipkg

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
            packages = PromptService(self.session).compile(
                CompileRequest(
                    storyboard_id=board.id,
                    storyboard_shot_id=req_in.storyboard_shot_id,
                    modality="image",
                    provider="gpt_image",
                    compile_all_shots=False,
                )
            )
            if not packages:
                raise ValueError("failed to compile image prompt package")
            return packages[0], from_prompt_package(packages[0])

        raise ValueError("prompt_package_id, storyboard_id, or image_prompt_package required")


def create_image_generation(
    session: Session, request: ImageGenerationRequestIn | dict[str, Any]
) -> ImageGenerationRequest:
    return ImageGenerationService(session).create(request)
