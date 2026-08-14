from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from orchestration_engine.actionability import (
    assess_actionability,
    compute_priority,
    estimate_expiration,
    opportunity_from_score_row,
)
from orchestration_engine.brief import build_production_brief
from orchestration_engine.concepts import generate_concepts, score_concept, select_concepts
from orchestration_engine.context import assemble_creative_context
from orchestration_engine.mechanism import extract_mechanism
from orchestration_engine.pipeline import (
    run_assembly,
    run_generation,
    run_measure_and_learn,
    run_publish,
    run_qa,
    run_story,
    run_storyboard,
)
from orchestration_engine.schemas import (
    ConceptOut,
    CreateJobRequest,
    JobOut,
    ReelProductionBrief,
    TrendOpportunityIn,
)
from orchestration_engine.state import can_transition, transition
from db.models import (
    CreativeConcept,
    OpportunityScore,
    OrchestrationDecisionLog,
    OrchestrationJob,
    ProductionBrief,
)


class OrchestrationExecutor:
    def __init__(self, session: Session):
        self.session = session

    def create_and_process(self, req: CreateJobRequest) -> OrchestrationJob:
        opportunity = self._resolve_opportunity(req)
        platform = req.platform or opportunity.platform or "instagram"
        content_id = f"content_{uuid4().hex[:10]}"
        now = datetime.now(timezone.utc)

        job = OrchestrationJob(
            id=str(uuid4()),
            content_id=content_id,
            trend_id=opportunity.trend_id,
            opportunity_id=opportunity.opportunity_id or req.opportunity_id,
            platform=platform,
            character_slug=req.character_slug,
            status="DISCOVERED",
            current_stage="DISCOVERED",
            priority=compute_priority(opportunity),
            mode=req.mode,
            trend_snapshot=opportunity.model_dump(),
            lineage={"content_id": content_id, "trend_id": opportunity.trend_id},
            trend_detected_at=now,
            expiration_at=estimate_expiration(opportunity, now=now),
            created_at=now,
            updated_at=now,
        )
        self.session.add(job)
        self.session.flush()
        self._log(job, "job_created", {"content_id": content_id, "trend_id": opportunity.trend_id})
        get_bus().publish(
            EventType.ORCHESTRATION_JOB_CREATED,
            {"job_id": job.id, "content_id": content_id, "trend_id": opportunity.trend_id},
            producer="orchestration-engine",
        )

        if req.process:
            self.advance(job.id, run_pipeline=req.run_pipeline, thresholds=req.thresholds, weights=req.score_weights, concept_count=req.concept_count)
        return self.session.get(OrchestrationJob, job.id)  # type: ignore[return-value]

    def advance(
        self,
        job_id: str,
        *,
        run_pipeline: bool = True,
        thresholds=None,
        weights=None,
        concept_count: int = 5,
        from_approval: bool = False,
    ) -> OrchestrationJob:
        job = self._get_job(job_id)
        if job.status in {"REJECTED", "CANCELLED", "LEARNING"} and not from_approval:
            return job
        if job.expiration_at and job.status not in {
            "PUBLISHED",
            "MEASURING",
            "LEARNING",
        }:
            exp = job.expiration_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp:
                return self._fail_or_cancel(job, "trend_expired", cancel=True)

        opportunity = TrendOpportunityIn.model_validate(job.trend_snapshot or {})

        # EVALUATING
        if job.status in {"DISCOVERED", "FAILED"} and (
            job.last_successful_stage is None or job.status == "DISCOVERED"
        ):
            self._set_status(job, "EVALUATING")
            action, detail = assess_actionability(opportunity, thresholds=thresholds)
            job.actionability = action
            self._log(job, "actionability", {"action": action, **detail}, score=opportunity.opportunity_score)
            get_bus().publish(
                EventType.TREND_ACTIONABLE if action == "ACT" else EventType.ORCHESTRATION_EVALUATED,
                {"job_id": job.id, "actionability": action, "detail": detail},
                producer="orchestration-engine",
            )
            if action == "REJECT":
                self._set_status(job, "REJECTED")
                job.completed_at = datetime.now(timezone.utc)
                return job
            if action == "WATCH":
                self._set_status(job, "WATCHING")
                return job
            self._set_status(job, "ACTIONABLE")
            if job.mode == "assisted" and not from_approval:
                return self._await(job, "trend")

        if job.status == "AWAITING_APPROVAL" and not from_approval:
            return job

        if job.status in {"ACTIONABLE", "AWAITING_APPROVAL"} and job.approval_gate in {None, "trend"}:
            if job.status == "AWAITING_APPROVAL" and not from_approval:
                return job
            # clear gate after approval path
            if from_approval and job.approval_gate == "trend":
                job.approval_gate = None
                self._set_status(job, "ACTIONABLE")

        # CONCEPTS
        if job.status == "ACTIONABLE" or (
            job.status == "AWAITING_APPROVAL" and from_approval and job.last_successful_stage == "ACTIONABLE"
        ):
            if job.status != "ACTIONABLE":
                self._set_status(job, "ACTIONABLE")
            self._set_status(job, "CONCEPT_GENERATING")
            get_bus().publish(
                EventType.CONCEPT_GENERATION_REQUESTED,
                {"job_id": job.id},
                producer="orchestration-engine",
            )
            mechanism = extract_mechanism(opportunity)
            job.mechanism = mechanism
            ctx = assemble_creative_context(
                self.session,
                opportunity=opportunity,
                mechanism=mechanism,
                character_slug=job.character_slug or "ghost_kid",
                platform=job.platform,
            )
            job.creative_context = ctx
            opt = ctx.get("optimization_profile")
            concepts = generate_concepts(
                opportunity=opportunity,
                mechanism=mechanism,
                character_slug=job.character_slug or "ghost_kid",
                count=concept_count,
                optimization_hints=opt if isinstance(opt, dict) else None,
            )
            scored = [
                score_concept(
                    c,
                    opportunity=opportunity,
                    mechanism=mechanism,
                    character_slug=job.character_slug or "ghost_kid",
                    weights=weights,
                )
                for c in concepts
            ]
            primary, backup, rejected = select_concepts(scored)
            self._persist_concepts(job, scored, primary, backup)
            job.selected_concept_id = primary.concept_id
            job.backup_concept_id = backup.concept_id if backup else None
            self._log(
                job,
                "concept_selection",
                {
                    "primary": primary.concept_id,
                    "primary_score": primary.score,
                    "backup": backup.concept_id if backup else None,
                    "rejected": [c.concept_id for c in rejected],
                },
                score=primary.score,
            )
            get_bus().publish(
                EventType.CONCEPT_GENERATION_COMPLETED,
                {"job_id": job.id, "count": len(scored)},
                producer="orchestration-engine",
            )
            get_bus().publish(
                EventType.CONCEPT_SELECTED,
                {
                    "job_id": job.id,
                    "concept_id": primary.concept_id,
                    "score": primary.score,
                    "backup_concept_id": backup.concept_id if backup else None,
                },
                producer="orchestration-engine",
            )
            self._set_status(job, "CONCEPT_SELECTED")
            if job.mode in {"assisted", "semi_autonomous"} and not from_approval:
                return self._await(job, "concept")

        # After concept approval
        if job.status == "AWAITING_APPROVAL" and from_approval and job.approval_gate == "concept":
            job.approval_gate = None
            self._set_status(job, "CONCEPT_SELECTED")

        # BRIEF
        if job.status == "CONCEPT_SELECTED":
            primary_row = self.session.get(CreativeConcept, job.selected_concept_id)
            if not primary_row:
                # resolve by concept id in JSON
                primary_row = self.session.scalar(
                    select(CreativeConcept).where(
                        CreativeConcept.job_id == job.id,
                        CreativeConcept.selected.is_(True),
                    )
                )
            concept = ConceptOut.model_validate(
                {
                    **(primary_row.concept if primary_row else {}),
                    "score": float(primary_row.score) if primary_row and primary_row.score is not None else None,
                    "score_breakdown": (primary_row.score_breakdown if primary_row else {}) or {},
                    "selected": True,
                }
            )
            brief = build_production_brief(
                content_id=job.content_id,
                opportunity=opportunity,
                concept=concept,
                mechanism=job.mechanism or {},
                optimization_profile=(job.creative_context or {}).get("optimization_profile"),
                creative_context=job.creative_context,
            )
            pb = ProductionBrief(
                id=str(uuid4()),
                job_id=job.id,
                concept_id=primary_row.id if primary_row else None,
                brief=brief.model_dump(),
                version=1,
            )
            self.session.add(pb)
            self.session.flush()
            job.production_brief_id = pb.id
            lin = dict(job.lineage or {})
            lin.update(
                {
                    "concept_id": concept.concept_id,
                    "concept_score": concept.score,
                    "production_brief_id": pb.id,
                    "opportunity_score": opportunity.opportunity_score,
                    "trend_snapshot": job.trend_snapshot,
                }
            )
            job.lineage = lin
            self._set_status(job, "BRIEF_CREATED")
            get_bus().publish(
                EventType.PRODUCTION_BRIEF_CREATED,
                {"job_id": job.id, "brief_id": pb.id, "concept_id": concept.concept_id},
                producer="orchestration-engine",
            )
            if not run_pipeline:
                return job

        if not run_pipeline:
            return job

        brief_obj = self._load_brief(job)
        try:
            # STORY → … → LEARNING
            if job.status == "BRIEF_CREATED":
                self._set_status(job, "STORY_GENERATING")
                get_bus().publish(
                    EventType.STORY_REQUESTED,
                    {"job_id": job.id, "brief_id": job.production_brief_id},
                    producer="orchestration-engine",
                )
                run_story(self.session, job, brief_obj)
                self._set_status(job, "STORYBOARD_GENERATING")

            if job.status == "STORYBOARD_GENERATING":
                story_id = (job.lineage or {}).get("story_id")
                run_storyboard(self.session, job, story_id)
                self._set_status(job, "ASSET_GENERATING")

            if job.status == "ASSET_GENERATING":
                board_id = (job.lineage or {}).get("storyboard_id")
                run_generation(self.session, job, board_id)
                self._set_status(job, "ASSEMBLING")

            if job.status == "ASSEMBLING":
                run_assembly(
                    self.session,
                    job,
                    storyboard_id=(job.lineage or {}).get("storyboard_id"),
                    artifact_ids=list((job.lineage or {}).get("asset_ids") or []),
                )
                self._set_status(job, "QA")

            if job.status == "QA":
                run_qa(self.session, job, (job.lineage or {}).get("assembly_id"))
                self._set_status(job, "APPROVED")
                if job.mode == "semi_autonomous" and not from_approval:
                    return self._await(job, "publish")

            if job.status == "AWAITING_APPROVAL" and from_approval and job.approval_gate == "publish":
                job.approval_gate = None
                self._set_status(job, "APPROVED")

            if job.status == "APPROVED":
                self._set_status(job, "PUBLISHING")
                run_publish(self.session, job, brief_obj)
                self._set_status(job, "PUBLISHED")

            if job.status == "PUBLISHED":
                self._set_status(job, "MEASURING")
                run_measure_and_learn(self.session, job)
                self._set_status(job, "LEARNING")
                job.completed_at = datetime.now(timezone.utc)
                get_bus().publish(
                    EventType.ORCHESTRATION_JOB_COMPLETED,
                    {"job_id": job.id, "lineage": job.lineage},
                    producer="orchestration-engine",
                )
        except Exception as exc:  # noqa: BLE001
            return self._handle_failure(job, exc)

        return job

    def approve(self, job_id: str, *, gate: str | None = None, continue_pipeline: bool = True) -> OrchestrationJob:
        job = self._get_job(job_id)
        gate = gate or job.approval_gate
        self._log(job, "human_approval", {"gate": gate})
        return self.advance(job.id, run_pipeline=continue_pipeline, from_approval=True)

    def retry(self, job_id: str) -> OrchestrationJob:
        job = self._get_job(job_id)
        if job.status != "FAILED":
            raise ValueError("retry only from FAILED")
        job.retry_count = int(job.retry_count or 0) + 1
        resume = job.last_successful_stage or "DISCOVERED"
        # Map resume to next runnable status
        mapping = {
            "DISCOVERED": "DISCOVERED",
            "ACTIONABLE": "ACTIONABLE",
            "CONCEPT_SELECTED": "CONCEPT_SELECTED",
            "BRIEF_CREATED": "BRIEF_CREATED",
            "STORY_GENERATING": "BRIEF_CREATED",
            "STORYBOARD_GENERATING": "STORYBOARD_GENERATING",
            "ASSET_GENERATING": "ASSET_GENERATING",
            "ASSEMBLING": "ASSEMBLING",
            "QA": "QA",
            "APPROVED": "APPROVED",
        }
        job.status = mapping.get(resume, "BRIEF_CREATED")
        job.current_stage = job.status
        job.failure_reason = None
        job.recovery_strategy = "resume_from_last_success"
        job.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        return self.advance(job.id, run_pipeline=True, from_approval=True)

    def _handle_failure(self, job: OrchestrationJob, exc: Exception) -> OrchestrationJob:
        msg = str(exc)
        transient = any(x in msg.lower() for x in ("timeout", "unavailable", "temporarily", "connection"))
        job.failure_reason = msg
        job.recovery_strategy = "auto_retry" if transient else "manual_or_abort"
        job.retry_count = int(job.retry_count or 0)
        if transient and job.retry_count < 2:
            job.retry_count += 1
            # stay at last_successful and retry once inline
            try:
                return self.advance(job.id, run_pipeline=True, from_approval=True)
            except Exception as exc2:  # noqa: BLE001
                msg = str(exc2)
                job.failure_reason = msg
        self._set_status(job, "FAILED", allow_from_any=True)
        get_bus().publish(
            EventType.ORCHESTRATION_JOB_FAILED,
            {
                "job_id": job.id,
                "error": msg,
                "stage": job.current_stage,
                "retry_count": job.retry_count,
                "last_successful_stage": job.last_successful_stage,
            },
            producer="orchestration-engine",
        )
        return job

    def _fail_or_cancel(self, job: OrchestrationJob, reason: str, *, cancel: bool) -> OrchestrationJob:
        job.failure_reason = reason
        self._set_status(job, "CANCELLED" if cancel else "FAILED", allow_from_any=True)
        job.completed_at = datetime.now(timezone.utc)
        return job

    def _await(self, job: OrchestrationJob, gate: str) -> OrchestrationJob:
        job.approval_gate = gate
        self._set_status(job, "AWAITING_APPROVAL", allow_from_any=True)
        get_bus().publish(
            EventType.ORCHESTRATION_AWAITING_APPROVAL,
            {"job_id": job.id, "gate": gate},
            producer="orchestration-engine",
        )
        return job

    def _set_status(self, job: OrchestrationJob, status: str, *, allow_from_any: bool = False) -> None:
        if not allow_from_any and not can_transition(job.status, status):
            # Allow idempotent same-status
            if job.status == status:
                return
            # Soft-allow forward pipeline jumps from BRIEF onward when already mid-flight
            if job.status in {
                "BRIEF_CREATED",
                "STORY_GENERATING",
                "STORYBOARD_GENERATING",
                "ASSET_GENERATING",
                "ASSEMBLING",
                "QA",
                "APPROVED",
                "PUBLISHING",
                "PUBLISHED",
                "MEASURING",
            } and status in {
                "STORY_GENERATING",
                "STORYBOARD_GENERATING",
                "ASSET_GENERATING",
                "ASSEMBLING",
                "QA",
                "APPROVED",
                "PUBLISHING",
                "PUBLISHED",
                "MEASURING",
                "LEARNING",
                "AWAITING_APPROVAL",
                "FAILED",
            }:
                pass
            else:
                transition(job.status, status)
        if job.status not in {"FAILED", "AWAITING_APPROVAL", "REJECTED", "CANCELLED", "WATCHING"}:
            if job.status not in {"DISCOVERED", "EVALUATING"}:
                job.last_successful_stage = job.status
        job.status = status
        job.current_stage = status
        job.updated_at = datetime.now(timezone.utc)
        self.session.flush()

    def _persist_concepts(
        self,
        job: OrchestrationJob,
        concepts: list[ConceptOut],
        primary: ConceptOut,
        backup: ConceptOut | None,
    ) -> None:
        id_map: dict[str, str] = {}
        for c in concepts:
            row = CreativeConcept(
                id=str(uuid4()),
                job_id=job.id,
                trend_id=job.trend_id,
                concept=c.model_dump(),
                score=c.score,
                score_breakdown=c.score_breakdown,
                selected=c.concept_id == primary.concept_id,
                is_backup=bool(backup and c.concept_id == backup.concept_id),
                rejection_reason=c.rejection_reason,
            )
            self.session.add(row)
            id_map[c.concept_id] = row.id
        self.session.flush()
        # Store logical concept_id in job; also keep DB uuid via lineage
        lin = dict(job.lineage or {})
        lin["concept_db_ids"] = id_map
        job.lineage = lin

    def _load_brief(self, job: OrchestrationJob) -> ReelProductionBrief:
        if not job.production_brief_id:
            raise ValueError("production brief missing")
        pb = self.session.get(ProductionBrief, job.production_brief_id)
        if not pb:
            raise ValueError("production brief not found")
        return ReelProductionBrief.model_validate(pb.brief)

    def _resolve_opportunity(self, req: CreateJobRequest) -> TrendOpportunityIn:
        if req.opportunity_id is not None:
            row = self.session.get(OpportunityScore, req.opportunity_id)
            if not row:
                raise ValueError("opportunity_id not found")
            return opportunity_from_score_row(row)
        if req.opportunity is not None:
            if isinstance(req.opportunity, TrendOpportunityIn):
                return req.opportunity
            return TrendOpportunityIn.model_validate(req.opportunity)
        raise ValueError("opportunity or opportunity_id required")

    def _log(
        self,
        job: OrchestrationJob,
        decision_type: str,
        decision: dict[str, Any],
        *,
        score: float | None = None,
        reason: str | None = None,
    ) -> None:
        self.session.add(
            OrchestrationDecisionLog(
                id=str(uuid4()),
                job_id=job.id,
                decision_type=decision_type,
                decision=decision,
                reason=reason,
                score=score,
                model_version="orchestrator_v1",
            )
        )
        self.session.flush()

    def _get_job(self, job_id: str) -> OrchestrationJob:
        row = self.session.get(OrchestrationJob, job_id)
        if row:
            return row
        rows = list(
            self.session.scalars(
                select(OrchestrationJob).where(OrchestrationJob.id.startswith(job_id))
            ).all()
        )
        if len(rows) != 1:
            raise ValueError("orchestration job not found")
        return rows[0]


def to_job_out(session: Session, job: OrchestrationJob) -> JobOut:
    concepts = list(
        session.scalars(select(CreativeConcept).where(CreativeConcept.job_id == job.id)).all()
    )
    brief = None
    if job.production_brief_id:
        pb = session.get(ProductionBrief, job.production_brief_id)
        if pb:
            brief = ReelProductionBrief.model_validate(pb.brief)
    return JobOut(
        job_id=job.id,
        content_id=job.content_id,
        status=job.status,
        current_stage=job.current_stage,
        actionability=job.actionability,
        priority=float(job.priority or 0),
        mode=job.mode,
        platform=job.platform,
        character_slug=job.character_slug,
        selected_concept_id=job.selected_concept_id,
        backup_concept_id=job.backup_concept_id,
        production_brief_id=job.production_brief_id,
        approval_gate=job.approval_gate,
        lineage=job.lineage or {},
        mechanism=job.mechanism,
        concepts=[
            ConceptOut.model_validate(
                {
                    **(c.concept or {}),
                    "score": float(c.score) if c.score is not None else None,
                    "score_breakdown": c.score_breakdown or {},
                    "selected": c.selected,
                    "is_backup": c.is_backup,
                    "rejection_reason": c.rejection_reason,
                }
            )
            for c in concepts
        ],
        brief=brief,
        failure_reason=job.failure_reason,
        retry_count=int(job.retry_count or 0),
        created_at=job.created_at,
        completed_at=job.completed_at,
    )
