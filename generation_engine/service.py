from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from db.models import GenerationJob, GenerationRequest, MediaArtifact, PromptPackage, Storyboard
from generation_engine.executor import JobExecutor, allocate_variant_plan
from generation_engine.router import fallback_chain, route_provider
from generation_engine.schemas import (
    GENERATION_PROFILES,
    BudgetConfig,
    GenerationRequestIn,
    ProviderStrategy,
    VariantsConfig,
)


class GenerationService:
    def __init__(self, session: Session):
        self.session = session

    def create(self, request: GenerationRequestIn | dict[str, Any]) -> GenerationRequest:
        req_in = (
            request
            if isinstance(request, GenerationRequestIn)
            else GenerationRequestIn.model_validate(request)
        )

        if req_in.idempotency_key:
            existing = self.session.scalar(
                select(GenerationRequest).where(
                    GenerationRequest.idempotency_key == req_in.idempotency_key
                )
            )
            if existing:
                return existing

        req_in = self._apply_profile(req_in)
        package = self._resolve_package(req_in)
        modality = req_in.modality or package.modality or "video"

        strategy = req_in.provider_strategy
        provider, scores = route_provider(
            self.session,
            modality=modality,
            prompt_package=package.provider_prompt,
            strategy=strategy,
        )
        est = float(package.estimated_cost or 0.1)
        variants = max(1, min(req_in.variants.count, req_in.budget.max_variants or 8))
        # Budget: reduce variants if needed
        if est * variants > req_in.budget.max_cost:
            variants = max(1, int(req_in.budget.max_cost // max(est, 0.01)))

        lineage = {
            **(package.lineage or {}),
            "prompt_package_id": package.id,
            "storyboard_id": req_in.storyboard_id or (package.lineage or {}).get("storyboard_id"),
            "storyboard_shot_id": req_in.storyboard_shot_id
            or (package.lineage or {}).get("storyboard_shot_id"),
            "story_id": (package.lineage or {}).get("story_id"),
        }

        gen_req = GenerationRequest(
            id=str(uuid4()),
            content_id=req_in.content_id,
            storyboard_id=lineage.get("storyboard_id"),
            storyboard_shot_id=lineage.get("storyboard_shot_id"),
            prompt_package_id=package.id,
            modality=modality,
            requested_variants=variants,
            priority=req_in.priority,
            budget=req_in.budget.model_dump(),
            provider_strategy=strategy.model_dump(),
            quality=req_in.quality.model_dump(),
            idempotency_key=req_in.idempotency_key,
            profile=req_in.profile,
            status="queued",
            lineage=lineage,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.session.add(gen_req)
        self.session.flush()

        get_bus().publish(
            EventType.GENERATION_REQUESTED,
            {
                "request_id": gen_req.id,
                "modality": modality,
                "variants": variants,
                "prompt_package_id": package.id,
            },
            producer="generation-engine",
        )

        fb = fallback_chain(strategy, provider, modality)
        plan = allocate_variant_plan(
            count=variants,
            strategy=req_in.variants.strategy,
            primary=provider,
            modality=modality,
            fallbacks=fb,
        )
        jobs: list[GenerationJob] = []
        for item in plan:
            job = GenerationJob(
                id=str(uuid4()),
                request_id=gen_req.id,
                variant_number=item["variant_number"],
                provider=item["provider"],
                model=None,
                status="queued",
                prompt_package_id=package.id,
                seed=item["seed"],
                estimated_cost=est,
                parameters={"routing_score": scores},
                depends_on=list(req_in.depends_on_job_ids),
                created_at=datetime.now(timezone.utc),
            )
            self.session.add(job)
            jobs.append(job)
        self.session.flush()

        get_bus().publish(
            EventType.GENERATION_QUEUED,
            {
                "request_id": gen_req.id,
                "jobs": [j.id for j in jobs],
                "priority": gen_req.priority,
            },
            producer="generation-engine",
        )

        if req_in.process:
            JobExecutor(self.session).process_request(gen_req.id)
            self.session.refresh(gen_req)
        return gen_req

    def process(self, request_id: str) -> GenerationRequest:
        return JobExecutor(self.session).process_request(request_id)

    def get_request(self, request_id: str) -> GenerationRequest | None:
        return self.session.get(GenerationRequest, request_id)

    def get_job(self, job_id: str) -> GenerationJob | None:
        return self.session.get(GenerationJob, job_id)

    def list_jobs(self, request_id: str) -> list[GenerationJob]:
        return list(
            self.session.scalars(
                select(GenerationJob)
                .where(GenerationJob.request_id == request_id)
                .order_by(GenerationJob.variant_number)
            ).all()
        )

    def list_artifacts(self, request_id: str) -> list[MediaArtifact]:
        jobs = self.list_jobs(request_id)
        if not jobs:
            return []
        ids = [j.id for j in jobs]
        return list(
            self.session.scalars(
                select(MediaArtifact).where(MediaArtifact.generation_job_id.in_(ids))
            ).all()
        )

    def cancel(self, request_id: str) -> GenerationRequest:
        req = self.session.get(GenerationRequest, request_id)
        if not req:
            raise ValueError("request not found")
        for job in self.list_jobs(request_id):
            if job.status in {"queued", "validating", "routing"}:
                job.status = "cancelled"
        req.status = "cancelled"
        req.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return req

    def retry(self, request_id: str) -> GenerationRequest:
        req = self.session.get(GenerationRequest, request_id)
        if not req:
            raise ValueError("request not found")
        for job in self.list_jobs(request_id):
            if job.status in {"failed", "failed_permanently"}:
                job.status = "queued"
                job.error = None
                job.retry_count = 0
        req.status = "queued"
        self.session.flush()
        return JobExecutor(self.session).process_request(request_id)

    def create_from_storyboard(
        self,
        storyboard_id: str,
        *,
        modality: str = "video",
        variants: int = 1,
        provider: str | None = None,
        process: bool = True,
        profile: str | None = None,
    ) -> list[GenerationRequest]:
        """Compile prompts for all shots (if needed) is caller's job; here we expect packages exist.

        Convenience: compile via PromptService then generate first package / all packages.
        """
        from prompt_engine.schemas import CompileRequest
        from prompt_engine.service import PromptService

        board = self.session.get(Storyboard, storyboard_id)
        if not board:
            rows = list(
                self.session.scalars(
                    select(Storyboard).where(Storyboard.id.startswith(storyboard_id))
                ).all()
            )
            if len(rows) != 1:
                raise ValueError("storyboard not found")
            board = rows[0]

        packages = PromptService(self.session).compile(
            CompileRequest(
                storyboard_id=board.id,
                modality=modality,  # type: ignore[arg-type]
                provider=provider,
                compile_all_shots=True,
            )
        )
        results: list[GenerationRequest] = []
        strategy = ProviderStrategy(
            mode="preferred" if provider else "automatic",
            preferred=provider,
        )
        for pkg in packages:
            results.append(
                self.create(
                    GenerationRequestIn(
                        prompt_package_id=pkg.id,
                        storyboard_id=board.id,
                        modality=modality,
                        provider_strategy=strategy,
                        variants=VariantsConfig(count=variants),
                        process=process,
                        profile=profile,
                    )
                )
            )
        return results

    def _resolve_package(self, req_in: GenerationRequestIn) -> PromptPackage:
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
            return pkg

        if req_in.storyboard_id:
            from prompt_engine.schemas import CompileRequest
            from prompt_engine.service import PromptService

            packages = PromptService(self.session).compile(
                CompileRequest(
                    storyboard_id=req_in.storyboard_id,
                    storyboard_shot_id=req_in.storyboard_shot_id,
                    modality=(req_in.modality or "video"),  # type: ignore[arg-type]
                    provider=req_in.provider_strategy.preferred
                    or req_in.provider_strategy.locked,
                    compile_all_shots=False,
                )
            )
            if not packages:
                raise ValueError("failed to compile prompt package from storyboard")
            return packages[0]

        raise ValueError("prompt_package_id or storyboard_id required")

    def _apply_profile(self, req_in: GenerationRequestIn) -> GenerationRequestIn:
        if not req_in.profile or req_in.profile not in GENERATION_PROFILES:
            return req_in
        prof = GENERATION_PROFILES[req_in.profile]
        data = req_in.model_dump()
        if req_in.variants.count == 1 and prof.get("variants"):
            data["variants"] = {"count": prof["variants"], "strategy": req_in.variants.strategy}
        if req_in.priority == "normal" and prof.get("priority"):
            data["priority"] = prof["priority"]
        max_cost = prof.get("max_cost_per_scene")
        if max_cost and req_in.budget.max_cost == BudgetConfig().max_cost:
            data["budget"] = {**req_in.budget.model_dump(), "max_cost": float(max_cost)}
        if prof.get("provider_strategy") and req_in.provider_strategy.mode == "automatic":
            data["provider_strategy"] = {
                **req_in.provider_strategy.model_dump(),
                **prof["provider_strategy"],
            }
        return GenerationRequestIn.model_validate(data)


def create_generation(
    session: Session, request: GenerationRequestIn | dict[str, Any]
) -> GenerationRequest:
    return GenerationService(session).create(request)
