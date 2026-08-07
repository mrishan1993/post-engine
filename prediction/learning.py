from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import PredictionError, PredictionLesson
from prediction.calibration import apply_calibration_to_model, calibration_report


def self_improvement_kpis(session: Session) -> dict[str, Any]:
    """KPIs the prediction system tracks about itself."""
    report = calibration_report(session)
    errors = session.scalars(select(PredictionError).where(PredictionError.metric == "views")).all()
    lessons = session.scalars(select(PredictionLesson)).all()

    hit_rate = None
    if errors:
        # "hit" = within 30% of predicted views
        hits = sum(
            1
            for e in errors
            if e.percentage_error is not None and float(e.percentage_error) <= 30
        )
        hit_rate = round(hits / len(errors), 3)

    return {
        "mape": report.get("mean_mape"),
        "calibration": report.get("overall"),
        "top_recommendation_hit_rate_30pct": hit_rate,
        "lessons_recorded": len(lessons),
        "verified_n": report.get("n", 0),
        "status": report.get("status"),
    }


def retrain_stub(session: Session) -> dict[str, Any]:
    """Phase 3 stub: apply calibration multipliers as 'retraining'."""
    report = calibration_report(session)
    if report.get("status") != "ok":
        return {"status": "skipped", "reason": "insufficient_data", "report": report}
    model = apply_calibration_to_model(session, report)
    return {
        "status": "calibrated",
        "model_version": model.name,
        "calibration": model.calibration,
        "report": report,
    }
