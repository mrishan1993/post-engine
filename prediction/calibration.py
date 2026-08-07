from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import ModelVersion, Prediction, PredictionError, VerificationResult


def calibration_report(session: Session) -> dict[str, Any]:
    """Are we over/under-estimating by vertical / platform / model?"""
    verified = session.scalars(
        select(Prediction).where(Prediction.status == "verified")
    ).all()
    if not verified:
        return {"status": "insufficient_data", "n": 0}

    by_vertical: dict[str, list[float]] = defaultdict(list)
    by_platform: dict[str, list[float]] = defaultdict(list)
    signed_errors: list[float] = []

    for pred in verified:
        err = session.scalar(
            select(PredictionError).where(
                PredictionError.prediction_id == pred.id,
                PredictionError.metric == "views",
            )
        )
        if not err or err.predicted is None or err.actual is None or float(err.predicted) == 0:
            continue
        # positive => overestimate
        signed = (float(err.predicted) - float(err.actual)) / float(err.predicted)
        signed_errors.append(signed)
        if pred.vertical_slug:
            by_vertical[pred.vertical_slug].append(signed)
        if pred.platform:
            by_platform[pred.platform].append(signed)

    def summarize(values: list[float]) -> dict[str, Any]:
        if not values:
            return {}
        avg = sum(values) / len(values)
        return {
            "n": len(values),
            "avg_signed_error": round(avg, 4),
            "bias": "overestimating" if avg > 0.05 else ("underestimating" if avg < -0.05 else "calibrated"),
            "suggested_multiplier": round(max(0.5, min(1.5, 1.0 - avg * 0.5)), 3),
        }

    mape_rows = session.scalars(select(VerificationResult)).all()
    mapes = [float(r.mape) for r in mape_rows if r.mape is not None]

    return {
        "status": "ok",
        "n": len(verified),
        "overall": summarize(signed_errors),
        "by_vertical": {k: summarize(v) for k, v in by_vertical.items()},
        "by_platform": {k: summarize(v) for k, v in by_platform.items()},
        "mean_mape": round(sum(mapes) / len(mapes), 2) if mapes else None,
    }


def apply_calibration_to_model(session: Session, report: dict[str, Any] | None = None) -> ModelVersion:
    """Create a new active model version with vertical multipliers (Phase 3 light)."""
    report = report or calibration_report(session)
    calibration: dict[str, float] = {}
    for slug, stats in (report.get("by_vertical") or {}).items():
        if stats.get("suggested_multiplier"):
            calibration[slug] = float(stats["suggested_multiplier"])

    # deactivate prior
    for mv in session.scalars(
        select(ModelVersion).where(ModelVersion.subsystem == "probability_engine", ModelVersion.is_active.is_(True))
    ).all():
        mv.is_active = False

    version_name = f"rule_v1_cal_{len(calibration)}_{report.get('n', 0)}"
    row = ModelVersion(
        name=version_name,
        subsystem="probability_engine",
        weights={},
        calibration=calibration,
        is_active=True,
        notes=f"Auto-calibration from {report.get('n')} verified predictions",
    )
    session.add(row)
    session.flush()
    return row
