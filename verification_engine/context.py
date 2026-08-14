from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from verification_engine.schemas import ActualSnapshot, PredictionSnapshot, PredictionTarget
from db.models import (
    PostAnalytics,
    Prediction,
    PredictionFeature,
    PublicationReceipt,
)


def snapshot_from_registry(pred: Prediction) -> PredictionSnapshot:
    features = {}
    # features loaded separately if needed
    return PredictionSnapshot(
        id=str(pred.id),
        content_id=None,
        model_id="virality_predictor",
        model_version=pred.model_version or "rule_v1",
        created_at=pred.created_at,
        predictions={
            "virality": {"probability": float(pred.virality_probability or 0)},
            "engagement": {"probability": float(pred.predicted_engagement_rate or 0)},
            "completion": {"probability": float(pred.predicted_retention or 0)},
            "share_rate": {
                "expected": (
                    float(pred.predicted_shares) / float(pred.predicted_views)
                    if pred.predicted_shares and pred.predicted_views
                    else None
                )
            },
            "views": {"expected": float(pred.predicted_views or 0)},
        },
        confidence={"overall": float(pred.confidence or 0)},
        target=PredictionTarget(
            metric="views",
            threshold=float(pred.predicted_views or 1_000_000),
            window_hours=48,
        ),
        signals=_signals_from_reasoning(pred.reasoning_json or {}),
        features=features,
        segments={
            "platform": pred.platform or "unknown",
            "character": str((pred.reasoning_json or {}).get("character") or ""),
            "vertical": pred.vertical_slug or "",
        },
        registry_prediction_id=pred.id,
    )


def _signals_from_reasoning(reasoning: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for k, v in (reasoning.get("signals") or reasoning.get("feature_scores") or {}).items():
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def resolve_prediction_snapshot(
    session: Session,
    *,
    prediction: PredictionSnapshot | dict[str, Any] | None = None,
    prediction_ref: str | None = None,
    registry_prediction_id: int | None = None,
    publication_id: str | None = None,
) -> PredictionSnapshot:
    if isinstance(prediction, PredictionSnapshot):
        return prediction
    if isinstance(prediction, dict):
        return PredictionSnapshot.model_validate(prediction)

    rid = registry_prediction_id
    if rid is None and prediction_ref and prediction_ref.isdigit():
        rid = int(prediction_ref)
    if rid is not None:
        row = session.get(Prediction, rid)
        if row:
            snap = snapshot_from_registry(row)
            # attach feature rows
            feats = list(
                session.scalars(
                    select(PredictionFeature).where(PredictionFeature.prediction_id == row.id)
                ).all()
            )
            snap.features = {f.feature_name: float(f.feature_value or 0) for f in feats}
            return snap

    if publication_id:
        receipt = session.get(PublicationReceipt, publication_id)
        if not receipt:
            rows = list(
                session.scalars(
                    select(PublicationReceipt).where(
                        PublicationReceipt.id.startswith(publication_id)
                    )
                ).all()
            )
            if len(rows) == 1:
                receipt = rows[0]
                publication_id = receipt.id
        analytics = session.get(PostAnalytics, publication_id) if publication_id else None
        link = (analytics.prediction_link if analytics else None) or {}
        pred_id = prediction_ref
        if pred_id is None and analytics is not None:
            pred_id = analytics.prediction_id
        if pred_id is None and receipt is not None:
            pred_id = (receipt.lineage or {}).get("prediction_id")
        # Build from prediction_link predicted fields if present
        predicted = link.get("predicted") or link.get("predictions") or {}
        if predicted or pred_id:
            return PredictionSnapshot(
                id=str(pred_id or f"anon_{publication_id[:8]}"),
                content_id=analytics.content_id if analytics else None,
                model_id=str(link.get("model_id") or "virality_predictor"),
                model_version=str(link.get("model_version") or "rule_v1"),
                predictions={
                    "virality": {"probability": float(predicted.get("virality", link.get("virality", 0.7)))},
                    "engagement": {
                        "probability": float(predicted.get("engagement", link.get("engagement", 0.7)))
                    },
                    "completion": {
                        "probability": float(predicted.get("completion", link.get("completion", 0.65)))
                    },
                    "share_rate": {"expected": float(predicted.get("share_rate", 0.03))},
                    "views": {"expected": float(predicted.get("views", 1_000_000))},
                },
                confidence={"overall": float(link.get("confidence", 0.75))},
                target=PredictionTarget(
                    metric="views",
                    threshold=float(predicted.get("views", 1_000_000)),
                    window_hours=48,
                ),
                signals=dict(link.get("signals") or {}),
                segments={
                    "platform": (analytics.platform if analytics else None) or "unknown",
                    "character": str(
                        ((analytics.content_fingerprint if analytics else None) or {}).get(
                            "character"
                        )
                        or ""
                    ),
                },
            )

    raise ValueError("prediction snapshot could not be resolved")


def resolve_actual_snapshot(
    session: Session,
    *,
    publication_id: str,
    window_hours: float = 48.0,
    qa_score: float | None = None,
    actual_overrides: dict[str, Any] | None = None,
) -> ActualSnapshot:
    receipt = session.get(PublicationReceipt, publication_id)
    if not receipt:
        rows = list(
            session.scalars(
                select(PublicationReceipt).where(
                    PublicationReceipt.id.startswith(publication_id)
                )
            ).all()
        )
        if len(rows) != 1:
            raise ValueError("publication not found")
        receipt = rows[0]

    analytics = session.get(PostAnalytics, receipt.id)
    published_at = receipt.published_at or receipt.created_at
    if published_at and published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    age_h = ((now - published_at).total_seconds() / 3600.0) if published_at else None
    end = published_at + timedelta(hours=window_hours) if published_at else now

    metrics: dict[str, Any] = {}
    if analytics:
        metrics = {
            "views": analytics.current_views,
            "likes": analytics.current_likes,
            "comments": analytics.current_comments,
            "shares": analytics.current_shares,
            "saves": analytics.current_saves,
            "reach": analytics.current_reach,
            "engagement_rate": float(analytics.engagement_rate or 0),
            "share_rate": float(analytics.share_rate or 0),
            "save_rate": float(analytics.save_rate or 0),
            "completion_rate": float(analytics.completion_rate or 0),
            "virality_score": float(analytics.virality_score or 0),
            "followers_gained": analytics.followers_gained,
        }
        # Prefer actuals nested in prediction_link if richer
        link_actual = (analytics.prediction_link or {}).get("actual") or {}
        for k, v in link_actual.items():
            if k not in metrics or metrics[k] is None:
                metrics[k] = v

    if actual_overrides:
        metrics.update(actual_overrides)

    return ActualSnapshot(
        publication_id=receipt.id,
        measurement_window={
            "start": published_at.isoformat() if published_at else None,
            "end": end.isoformat(),
            "window_hours": window_hours,
        },
        metrics=metrics,
        viral_state=analytics.viral_state if analytics else None,
        qa_score=qa_score,
        age_hours=age_h,
    )


def stage_for_age(age_hours: float | None, target_window_hours: float) -> str:
    if age_hours is None:
        return "primary"
    if age_hours < 1:
        return "early"
    if age_hours < 6:
        return "early"
    if age_hours < target_window_hours:
        return "intermediate"
    if age_hours < 24 * 7:
        return "primary"
    return "long_term"


def status_for_stage(stage: str, *, has_actuals: bool) -> str:
    if not has_actuals:
        return "insufficient_data"
    if stage == "early":
        return "early_result"
    if stage in {"primary", "long_term", "intermediate"}:
        return "verified" if stage != "intermediate" else "early_result"
    return "verified"
