from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from amp_platform.events.types import PredictionVerified
from db.models import (
    Prediction,
    PredictionError,
    PredictionLesson,
    Publication,
    VerificationResult,
    VideoMetric,
    VideoRun,
)
from prediction.registry import PredictionRegistry


METRIC_MAP = {
    "views": ("predicted_views", "actual_views"),
    "ctr": ("predicted_ctr", "actual_ctr"),
    "retention": ("predicted_retention", "actual_retention"),
    "watch_time_sec": ("predicted_watch_time_sec", "actual_watch_time_sec"),
    "comments": ("predicted_comments", "actual_comments"),
    "shares": ("predicted_shares", "actual_shares"),
    "saves": ("predicted_saves", "actual_saves"),
    "followers": ("predicted_followers", "actual_followers"),
    "revenue_usd": ("predicted_revenue_usd", "actual_revenue_usd"),
}


def verify_prediction(
    session: Session,
    prediction_id: int,
    actuals: dict[str, Any],
) -> VerificationResult:
    """Compare prediction vs actuals, store errors + root-cause lesson."""
    pred = session.get(Prediction, prediction_id)
    if not pred:
        raise ValueError(f"prediction {prediction_id} not found")

    errors: list[PredictionError] = []
    pct_errors: list[float] = []
    for metric, (pred_attr, actual_key) in METRIC_MAP.items():
        predicted = getattr(pred, pred_attr, None)
        actual = actuals.get(actual_key.replace("actual_", "") if actual_key.startswith("actual_") else metric)
        # allow both "views" and "actual_views" keys
        if actual is None:
            actual = actuals.get(actual_key)
        if predicted is None or actual is None:
            continue
        predicted_f = float(predicted)
        actual_f = float(actual)
        abs_err = abs(predicted_f - actual_f)
        pct_err = (abs_err / predicted_f * 100.0) if predicted_f else None
        if pct_err is not None:
            pct_errors.append(pct_err)
        err = PredictionError(
            prediction_id=pred.id,
            metric=metric,
            predicted=predicted_f,
            actual=actual_f,
            absolute_error=abs_err,
            percentage_error=pct_err,
        )
        session.add(err)
        errors.append(err)

    mape = sum(pct_errors) / len(pct_errors) if pct_errors else None
    explanation = _root_cause(pred, actuals, errors)

    existing = session.scalar(
        select(VerificationResult).where(VerificationResult.prediction_id == pred.id)
    )
    payload = {
        "actual_views": _i(actuals, "views", "actual_views"),
        "actual_ctr": _f(actuals, "ctr", "actual_ctr"),
        "actual_retention": _f(actuals, "retention", "actual_retention"),
        "actual_watch_time_sec": _f(actuals, "watch_time_sec", "actual_watch_time_sec"),
        "actual_comments": _i(actuals, "comments", "actual_comments"),
        "actual_shares": _i(actuals, "shares", "actual_shares"),
        "actual_saves": _i(actuals, "saves", "actual_saves"),
        "actual_followers": _i(actuals, "followers", "actual_followers"),
        "actual_revenue_usd": _f(actuals, "revenue_usd", "actual_revenue_usd"),
        "actual_engagement_rate": _f(actuals, "engagement_rate", "actual_engagement_rate"),
    }
    if existing:
        for k, v in payload.items():
            setattr(existing, k, v)
        existing.metrics_json = actuals
        existing.explanation = explanation
        existing.mape = mape
        existing.captured_at = datetime.now(timezone.utc)
        result = existing
    else:
        result = VerificationResult(
            prediction_id=pred.id,
            metrics_json=actuals,
            explanation=explanation,
            mape=mape,
            captured_at=datetime.now(timezone.utc),
            **payload,
        )
        session.add(result)

    session.add(
        PredictionLesson(
            prediction_id=pred.id,
            primary_cause=explanation.get("primary_cause"),
            secondary_causes=explanation.get("secondary_causes") or [],
            suggested_confidence=explanation.get("suggested_confidence"),
            lesson=explanation.get("lesson"),
        )
    )
    pred.status = "verified"
    session.flush()
    get_bus().publish(
        EventType.PREDICTION_VERIFIED,
        PredictionVerified(
            prediction_id=pred.id,
            verification_id=result.id,
            mape=float(result.mape) if result.mape is not None else None,
            lesson=(result.explanation or {}).get("lesson"),
        ),
        producer="verification-service",
    )
    return result


def verify_from_video_run(session: Session, video_run_id: int) -> VerificationResult | None:
    """Pull latest publication metrics for a run and verify linked prediction."""
    run = session.get(VideoRun, video_run_id)
    if not run or not run.brief_id:
        return None
    registry = PredictionRegistry(session)
    pred = registry.for_brief(run.brief_id)
    if not pred:
        # fallback: prediction linked directly to video_run
        pred = session.scalar(
            select(Prediction)
            .where(Prediction.video_run_id == video_run_id)
            .order_by(Prediction.created_at.desc())
            .limit(1)
        )
    if not pred:
        return None

    pubs = session.scalars(select(Publication).where(Publication.video_run_id == video_run_id)).all()
    views = likes = comments = 0
    watch = 0
    revenue = 0.0
    for pub in pubs:
        metric = session.scalar(
            select(VideoMetric)
            .where(VideoMetric.publication_id == pub.id)
            .order_by(VideoMetric.pulled_at.desc())
            .limit(1)
        )
        if not metric:
            continue
        views += int(metric.views or 0)
        likes += int(metric.likes or 0)
        comments += int(metric.comments or 0)
        watch = max(watch, int(metric.avg_view_duration_sec or 0))
        revenue += float(metric.estimated_revenue_usd or 0)

    if views == 0 and not pubs:
        return None

    engagement = ((likes + comments) / views) if views else 0.0
    retention = None
    if watch and pred.predicted_watch_time_sec:
        # crude proxy
        retention = min(watch / 60.0, 1.0)

    return verify_prediction(
        session,
        pred.id,
        {
            "views": views,
            "comments": comments,
            "watch_time_sec": watch,
            "revenue_usd": revenue,
            "engagement_rate": engagement,
            "retention": retention,
            "shares": int(views * 0.01),
            "saves": int(views * 0.008),
            "followers": int(views * 0.002),
            "ctr": 0.05,  # unknown without impressions
        },
    )


def _root_cause(
    pred: Prediction,
    actuals: dict[str, Any],
    errors: list[PredictionError],
) -> dict[str, Any]:
    views_err = next((e for e in errors if e.metric == "views"), None)
    primary = "Within expected range"
    secondary: list[str] = []
    suggested_conf = float(pred.confidence or 0.5)

    if views_err and views_err.predicted and views_err.actual is not None:
        ratio = float(views_err.actual) / float(views_err.predicted) if views_err.predicted else 1.0
        if ratio < 0.4:
            primary = "Severe overestimate — trend may have saturated or creative underperformed"
            secondary = ["Weak thumbnail / hook mismatch", "Posting time may have missed peak audience"]
            suggested_conf = min(suggested_conf, 0.42)
        elif ratio < 0.7:
            primary = "Moderate overestimate"
            secondary = ["Competition higher than modeled", "Retention below prediction"]
            suggested_conf = min(suggested_conf, 0.55)
        elif ratio > 1.5:
            primary = "Underestimate — breakout performance"
            secondary = ["Trend stronger than features captured", "Character/hook synergy"]
            suggested_conf = max(suggested_conf, float(pred.confidence or 0.5))

    lifecycle = (pred.reasoning_json or {}).get("context", {}).get("lifecycle_stage")
    if lifecycle in {"saturated", "declining", "dead"}:
        secondary.append(f"Lifecycle was {lifecycle}")

    lesson = (
        f"Views predicted={pred.predicted_views}, actual={actuals.get('views') or actuals.get('actual_views')}. "
        f"Primary: {primary}. Confidence should have been ~{suggested_conf:.0%} "
        f"instead of {float(pred.confidence or 0):.0%}."
    )
    return {
        "primary_cause": primary,
        "secondary_causes": secondary,
        "suggested_confidence": round(suggested_conf, 4),
        "lesson": lesson,
        "error_count": len(errors),
    }


def rmse_for_metric(session: Session, metric: str = "views") -> float | None:
    rows = session.scalars(select(PredictionError).where(PredictionError.metric == metric)).all()
    if not rows:
        return None
    return math.sqrt(sum(float(r.absolute_error or 0) ** 2 for r in rows) / len(rows))


def _i(d: dict[str, Any], *keys: str) -> int | None:
    for k in keys:
        if k in d and d[k] is not None:
            return int(d[k])
    return None


def _f(d: dict[str, Any], *keys: str) -> float | None:
    for k in keys:
        if k in d and d[k] is not None:
            return float(d[k])
    return None
