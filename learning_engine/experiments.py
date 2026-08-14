from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from learning_engine.schemas import CreateExperimentRequest
from db.models import OptimizationExperiment


def create_experiment(session: Session, req: CreateExperimentRequest) -> OptimizationExperiment:
    variants = req.variants or []
    exp = OptimizationExperiment(
        id=str(uuid4()),
        hypothesis=req.hypothesis,
        variable=req.variable,
        control=req.control,
        variants=variants,
        target_metric=req.target_metric,
        status="running" if req.start else "draft",
        sample_target=req.sample_target,
        sample_count=0,
        assignment_counts={"control": 0, **{f"v{i}": 0 for i in range(len(variants))}},
        scope=req.scope.model_dump() if req.scope else None,
        created_at=datetime.now(timezone.utc),
    )
    session.add(exp)
    session.flush()
    get_bus().publish(
        EventType.EXPERIMENT_CREATED,
        {
            "experiment_id": exp.id,
            "variable": exp.variable,
            "target_metric": exp.target_metric,
            "status": exp.status,
        },
        producer="learning-engine",
    )
    return exp


def assign_variant(session: Session, experiment_id: str) -> dict[str, Any]:
    """Round-robin-ish assignment via counts — avoid biased assignment."""
    exp = session.get(OptimizationExperiment, experiment_id)
    if not exp:
        raise ValueError("experiment not found")
    if exp.status not in {"running", "draft"}:
        raise ValueError(f"experiment status={exp.status}")

    counts = dict(exp.assignment_counts or {"control": 0})
    options = [("control", exp.control)]
    for i, v in enumerate(exp.variants or []):
        options.append((f"v{i}", v))

    # Pick arm with lowest count
    arm_key, arm_val = min(options, key=lambda x: int(counts.get(x[0], 0)))
    counts[arm_key] = int(counts.get(arm_key, 0)) + 1
    exp.assignment_counts = counts
    exp.sample_count = int(exp.sample_count or 0) + 1
    if exp.status == "draft":
        exp.status = "running"
    session.flush()

    if exp.sample_count >= int(exp.sample_target or 30):
        complete_experiment(session, exp.id)

    return {
        "experiment_id": exp.id,
        "arm": arm_key,
        "assignment": arm_val,
        "variable": exp.variable,
        "sample_count": exp.sample_count,
    }


def complete_experiment(session: Session, experiment_id: str, results: dict[str, Any] | None = None) -> OptimizationExperiment:
    exp = session.get(OptimizationExperiment, experiment_id)
    if not exp:
        raise ValueError("experiment not found")
    exp.status = "completed"
    exp.completed_at = datetime.now(timezone.utc)
    exp.results = results or {
        "assignment_counts": exp.assignment_counts,
        "sample_count": exp.sample_count,
        "note": "V1: counts only — attach metric aggregates in Phase 4+",
    }
    session.flush()
    get_bus().publish(
        EventType.EXPERIMENT_COMPLETED,
        {
            "experiment_id": exp.id,
            "variable": exp.variable,
            "sample_count": exp.sample_count,
            "results": exp.results,
        },
        producer="learning-engine",
    )
    return exp


def get_experiment(session: Session, experiment_id: str) -> OptimizationExperiment:
    row = session.get(OptimizationExperiment, experiment_id)
    if row:
        return row
    rows = list(
        session.scalars(
            select(OptimizationExperiment).where(
                OptimizationExperiment.id.startswith(experiment_id)
            )
        ).all()
    )
    if len(rows) != 1:
        raise ValueError("experiment not found")
    return rows[0]


def list_experiments(session: Session, *, status: str | None = None) -> list[OptimizationExperiment]:
    stmt = select(OptimizationExperiment).order_by(OptimizationExperiment.created_at.desc())
    if status:
        stmt = stmt.where(OptimizationExperiment.status == status)
    return list(session.scalars(stmt).all())
