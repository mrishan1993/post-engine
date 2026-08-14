from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from learning_engine.dataset import list_observations
from learning_engine.schemas import PromoteModelRequest, TrainModelRequest
from db.models import OptimizationModelVersion


def train_challenger(session: Session, req: TrainModelRequest) -> OptimizationModelVersion:
    """Offline challenger training stub — never mutates champion weights in place."""
    get_bus().publish(
        EventType.MODEL_TRAINING_STARTED,
        {"model_name": req.model_name},
        producer="learning-engine",
    )

    obs = list_observations(session, limit=2000)
    # Exclude early_result-heavy / flagged for training
    usable = [
        o
        for o in obs
        if not o.excluded
        and not (o.quality_flags or {}).get("stage_early")
        and (o.feature_vector or {}).get("verification_stage") in {None, "primary", "long_term", "intermediate"}
    ]
    data_version = f"obs_{len(usable)}_{datetime.now(timezone.utc).strftime('%Y%m%d')}"

    # V1: derive simple feature association weights from completion lift by hook_type
    from learning_engine.patterns import analyze_dimension

    hooks = analyze_dimension(usable, dimension="hook_type", metric="completion_rate", min_group=2)
    weights = {h.value: round(0.5 + h.lift, 4) for h in hooks}
    # Naive offline metrics
    n = len(usable)
    metrics = {
        "training_n": n,
        "feature_count": len(weights),
        "brier_score": None,  # needs labeled probs — filled when verification calibration linked
        "ranking_accuracy": None,
        "note": "challenger stub — promote only after champion comparison",
    }

    version = req.version or f"challenger_{uuid4().hex[:6]}"
    row = OptimizationModelVersion(
        id=str(uuid4()),
        model_name=req.model_name,
        version=version,
        status="challenger",
        training_data_version=data_version,
        metrics=metrics,
        weights={"hook_type": weights, "schema_version": "v1"},
        notes=req.notes,
        created_at=datetime.now(timezone.utc),
    )
    session.add(row)
    session.flush()

    get_bus().publish(
        EventType.MODEL_TRAINING_COMPLETED,
        {
            "model_id": row.id,
            "model_name": row.model_name,
            "version": row.version,
            "training_n": n,
        },
        producer="learning-engine",
    )
    get_bus().publish(
        EventType.MODEL_EVALUATION_COMPLETED,
        {"model_id": row.id, "metrics": metrics},
        producer="learning-engine",
    )
    return row


def compare_models(session: Session, model_a_id: str, model_b_id: str) -> dict[str, Any]:
    a = session.get(OptimizationModelVersion, model_a_id)
    b = session.get(OptimizationModelVersion, model_b_id)
    if not a or not b:
        raise ValueError("model not found")
    return {
        "champion_candidate": _summary(a),
        "challenger_candidate": _summary(b),
        "note": "Do not auto-promote; require better offline metrics + backtest",
        "recommendation": "hold"
        if (a.metrics or {}).get("training_n", 0) >= (b.metrics or {}).get("training_n", 0)
        else "consider_challenger",
    }


def promote_model(session: Session, req: PromoteModelRequest) -> OptimizationModelVersion:
    row = session.get(OptimizationModelVersion, req.model_id)
    if not row:
        raise ValueError("model not found")
    if row.status == "champion":
        return row

    champ = session.scalar(
        select(OptimizationModelVersion).where(
            OptimizationModelVersion.model_name == row.model_name,
            OptimizationModelVersion.status == "champion",
        )
    )
    if req.require_better_than_champion and champ:
        cn = int((champ.metrics or {}).get("training_n") or 0)
        nn = int((row.metrics or {}).get("training_n") or 0)
        if nn < cn:
            raise ValueError("challenger training_n not better than champion; refuse promote")

    if champ:
        champ.status = "deprecated"
    row.status = "champion"
    row.promoted_at = datetime.now(timezone.utc)
    session.flush()

    get_bus().publish(
        EventType.MODEL_PROMOTED,
        {
            "model_id": row.id,
            "model_name": row.model_name,
            "version": row.version,
            "previous_champion_id": champ.id if champ else None,
        },
        producer="learning-engine",
    )
    get_bus().publish(
        EventType.MODEL_UPDATED,
        {
            "model_name": row.model_name,
            "version": row.version,
            "status": "champion",
        },
        producer="learning-engine",
    )
    return row


def list_models(session: Session, *, model_name: str | None = None) -> list[dict[str, Any]]:
    stmt = select(OptimizationModelVersion).order_by(OptimizationModelVersion.created_at.desc())
    if model_name:
        stmt = stmt.where(OptimizationModelVersion.model_name == model_name)
    return [_summary(r) for r in session.scalars(stmt).all()]


def _summary(row: OptimizationModelVersion) -> dict[str, Any]:
    return {
        "id": row.id,
        "model_name": row.model_name,
        "version": row.version,
        "status": row.status,
        "training_data_version": row.training_data_version,
        "metrics": row.metrics,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "promoted_at": row.promoted_at.isoformat() if row.promoted_at else None,
    }
