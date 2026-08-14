from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from verification_engine.schemas import MetricVerification
from db.models import CalibrationBucket


def probability_bucket(p: float) -> str:
    lo = int(max(0.0, min(0.9, p)) * 10) / 10.0
    hi = lo + 0.1
    return f"{lo:.1f}-{hi:.1f}"


def update_calibration_bucket(
    session: Session,
    *,
    model_id: str,
    model_version: str,
    metric: str,
    probability: float,
    outcome: bool,
    segment_key: str = "global",
) -> CalibrationBucket:
    bucket = probability_bucket(probability)
    row = session.scalar(
        select(CalibrationBucket).where(
            CalibrationBucket.model_id == model_id,
            CalibrationBucket.model_version == model_version,
            CalibrationBucket.metric == metric,
            CalibrationBucket.probability_bucket == bucket,
            CalibrationBucket.segment_key == segment_key,
        )
    )
    if not row:
        row = CalibrationBucket(
            id=str(uuid4()),
            model_id=model_id,
            model_version=model_version,
            metric=metric,
            probability_bucket=bucket,
            segment_key=segment_key,
            sample_count=0,
            mean_prediction=0.0,
            actual_success_rate=0.0,
            calibration_error=0.0,
        )
        session.add(row)
        session.flush()

    n = int(row.sample_count or 0)
    mean_p = float(row.mean_prediction or 0.0)
    success_rate = float(row.actual_success_rate or 0.0)
    # Incremental mean update
    new_n = n + 1
    row.mean_prediction = (mean_p * n + probability) / new_n
    row.actual_success_rate = (success_rate * n + (1.0 if outcome else 0.0)) / new_n
    row.sample_count = new_n
    row.calibration_error = float(row.actual_success_rate) - float(row.mean_prediction)
    session.flush()
    return row


def apply_calibration_updates(
    session: Session,
    *,
    model_id: str,
    model_version: str,
    metrics: list[MetricVerification],
    segments: dict[str, str] | None = None,
) -> list[CalibrationBucket]:
    updated: list[CalibrationBucket] = []
    segs = ["global"]
    if segments:
        for k, v in segments.items():
            if v:
                segs.append(f"{k}:{v}")
    for m in metrics:
        if m.outcome is None or m.predicted_value is None:
            continue
        if not (0.0 <= float(m.predicted_value) <= 1.0):
            continue
        for seg in segs:
            updated.append(
                update_calibration_bucket(
                    session,
                    model_id=model_id,
                    model_version=model_version,
                    metric=m.metric,
                    probability=float(m.predicted_value),
                    outcome=bool(m.outcome),
                    segment_key=seg,
                )
            )
    return updated


def list_calibration(
    session: Session,
    *,
    model_id: str,
    model_version: str | None = None,
    metric: str = "viral_target",
) -> list[dict[str, Any]]:
    stmt = select(CalibrationBucket).where(
        CalibrationBucket.model_id == model_id,
        CalibrationBucket.metric == metric,
    )
    if model_version:
        stmt = stmt.where(CalibrationBucket.model_version == model_version)
    rows = list(session.scalars(stmt.order_by(CalibrationBucket.probability_bucket)).all())
    return [
        {
            "model_id": r.model_id,
            "model_version": r.model_version,
            "metric": r.metric,
            "probability_bucket": r.probability_bucket,
            "segment_key": r.segment_key,
            "sample_count": r.sample_count,
            "mean_prediction": float(r.mean_prediction or 0),
            "actual_success_rate": float(r.actual_success_rate or 0),
            "calibration_error": float(r.calibration_error or 0),
        }
        for r in rows
    ]
