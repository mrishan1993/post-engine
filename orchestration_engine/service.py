from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from orchestration_engine.executor import OrchestrationExecutor, to_job_out
from orchestration_engine.schemas import ApproveJobRequest, CreateJobRequest, JobOut
from db.models import OrchestrationDecisionLog, OrchestrationEngineRun, OrchestrationJob


class OrchestrationService:
    """Trend-to-Reel Orchestration — coordinates engines; does not generate media itself."""

    def __init__(self, session: Session):
        self.session = session
        self.executor = OrchestrationExecutor(session)

    def create_job(self, request: CreateJobRequest | dict[str, Any]) -> JobOut:
        req = (
            request
            if isinstance(request, CreateJobRequest)
            else CreateJobRequest.model_validate(request)
        )
        job = self.executor.create_and_process(req)
        return to_job_out(self.session, job)

    def get(self, job_id: str) -> JobOut:
        return to_job_out(self.session, self.executor._get_job(job_id))

    def approve(self, request: ApproveJobRequest | dict[str, Any]) -> JobOut:
        req = (
            request
            if isinstance(request, ApproveJobRequest)
            else ApproveJobRequest.model_validate(request)
        )
        job = self.executor.approve(
            req.job_id, gate=req.gate, continue_pipeline=req.continue_pipeline
        )
        return to_job_out(self.session, job)

    def retry(self, job_id: str) -> JobOut:
        return to_job_out(self.session, self.executor.retry(job_id))

    def advance(self, job_id: str, *, run_pipeline: bool = True) -> JobOut:
        job = self.executor.advance(job_id, run_pipeline=run_pipeline, from_approval=True)
        return to_job_out(self.session, job)

    def list_jobs(self, *, status: str | None = None, limit: int = 50) -> list[JobOut]:
        stmt = select(OrchestrationJob).order_by(OrchestrationJob.created_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(OrchestrationJob.status == status)
        return [to_job_out(self.session, j) for j in self.session.scalars(stmt).all()]

    def decision_log(self, job_id: str) -> list[dict[str, Any]]:
        job = self.executor._get_job(job_id)
        rows = list(
            self.session.scalars(
                select(OrchestrationDecisionLog)
                .where(OrchestrationDecisionLog.job_id == job.id)
                .order_by(OrchestrationDecisionLog.created_at.asc())
            ).all()
        )
        return [
            {
                "id": r.id,
                "decision_type": r.decision_type,
                "decision": r.decision,
                "reason": r.reason,
                "score": float(r.score) if r.score is not None else None,
                "model_version": r.model_version,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    def engine_runs(self, job_id: str) -> list[dict[str, Any]]:
        job = self.executor._get_job(job_id)
        rows = list(
            self.session.scalars(
                select(OrchestrationEngineRun)
                .where(OrchestrationEngineRun.job_id == job.id)
                .order_by(OrchestrationEngineRun.created_at.asc())
            ).all()
        )
        return [
            {
                "id": r.id,
                "engine_name": r.engine_name,
                "stage": r.stage,
                "status": r.status,
                "input_reference": r.input_reference,
                "output_reference": r.output_reference,
                "duration_ms": r.duration_ms,
                "error": r.error,
            }
            for r in rows
        ]

    def lineage(self, job_id: str) -> dict[str, Any]:
        job = self.executor._get_job(job_id)
        return {
            "content_id": job.content_id,
            "trend_id": job.trend_id,
            "job_id": job.id,
            **(job.lineage or {}),
        }
