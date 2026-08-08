from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from amp_platform.events.types import PredictionCreated
from db.models import ModelVersion, Prediction, PredictionFeature
from prediction.probability import PredictionResult, predict_opportunity


class PredictionRegistry:
    """Shared registry — every AI subsystem records decisions here."""

    def __init__(self, session: Session):
        self.session = session

    def record(
        self,
        result: PredictionResult,
        *,
        subsystem: str,
        decision_type: str,
        content_brief_id: int | None = None,
        video_run_id: int | None = None,
        opportunity_id: int | None = None,
        vertical_slug: str | None = None,
        platform: str | None = None,
    ) -> Prediction:
        row = Prediction(
            subsystem=subsystem,
            decision_type=decision_type,
            content_brief_id=content_brief_id,
            video_run_id=video_run_id,
            opportunity_id=opportunity_id,
            vertical_slug=vertical_slug,
            platform=platform or (result.features.raw.get("platform") if result.features else None),
            model_version=result.model_version,
            status="pending",
            virality_probability=result.virality_probability,
            confidence=result.confidence,
            predicted_views=result.predicted_views,
            predicted_views_low=result.predicted_views_low,
            predicted_views_high=result.predicted_views_high,
            predicted_reach=result.predicted_reach,
            predicted_ctr=result.predicted_ctr,
            predicted_watch_time_sec=result.predicted_watch_time_sec,
            predicted_retention=result.predicted_retention,
            predicted_engagement_rate=result.predicted_engagement_rate,
            predicted_shares=result.predicted_shares,
            predicted_saves=result.predicted_saves,
            predicted_comments=result.predicted_comments,
            predicted_followers=result.predicted_followers,
            predicted_revenue_usd=result.predicted_revenue_usd,
            predicted_roi=result.predicted_roi,
            expected_cost_usd=result.expected_cost_usd,
            final_opportunity_score=result.final_opportunity_score,
            risk_score=result.risk_score,
            metrics_json=result.metrics_json,
            reasoning_json=result.reasoning_json,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(row)
        self.session.flush()

        for name, value in result.features.values.items():
            self.session.add(
                PredictionFeature(
                    prediction_id=row.id,
                    feature_name=name,
                    feature_value=value,
                    feature_raw=str(result.features.raw.get(name, "")),
                )
            )
        self.session.flush()
        get_bus().publish(
            EventType.PREDICTION_CREATED,
            PredictionCreated(
                prediction_id=row.id,
                brief_id=content_brief_id,
                opportunity_id=opportunity_id,
                vertical_slug=vertical_slug,
                virality_probability=float(result.virality_probability),
                expected_views=int(result.predicted_views),
                confidence=float(result.confidence),
                final_opportunity_score=float(result.final_opportunity_score),
                model_version=result.model_version,
            ),
            producer="probability-service",
        )
        return row

    def predict_and_record(
        self,
        *,
        opportunity: dict[str, Any],
        score_breakdown: dict[str, Any] | None = None,
        lifecycle_stage: str | None = None,
        vertical_slug: str | None = None,
        character: dict[str, Any] | None = None,
        content_brief_id: int | None = None,
        opportunity_id: int | None = None,
        video_run_id: int | None = None,
        platform: str = "youtube",
        subsystem: str = "probability_engine",
        decision_type: str = "virality",
        expected_cost_usd: float = 1.0,
        similar_winners: int = 0,
    ) -> tuple[Prediction, PredictionResult]:
        calibration = self.active_calibration()
        result = predict_opportunity(
            opportunity=opportunity,
            score_breakdown=score_breakdown,
            lifecycle_stage=lifecycle_stage,
            vertical_slug=vertical_slug,
            character=character,
            platform=platform,
            expected_cost_usd=expected_cost_usd,
            similar_winners=similar_winners,
            calibration=calibration,
        )
        row = self.record(
            result,
            subsystem=subsystem,
            decision_type=decision_type,
            content_brief_id=content_brief_id,
            video_run_id=video_run_id,
            opportunity_id=opportunity_id,
            vertical_slug=vertical_slug,
            platform=platform,
        )
        return row, result

    def active_calibration(self) -> dict[str, float]:
        model = self.session.scalar(
            select(ModelVersion).where(
                ModelVersion.subsystem == "probability_engine",
                ModelVersion.is_active.is_(True),
            )
        )
        if not model or not model.calibration:
            return {}
        return {k: float(v) for k, v in model.calibration.items()}

    def get(self, prediction_id: int) -> Prediction | None:
        return self.session.get(Prediction, prediction_id)

    def list_pending(self, limit: int = 50) -> list[Prediction]:
        return list(
            self.session.scalars(
                select(Prediction)
                .where(Prediction.status == "pending")
                .order_by(Prediction.created_at.desc())
                .limit(limit)
            ).all()
        )

    def for_brief(self, content_brief_id: int) -> Prediction | None:
        return self.session.scalar(
            select(Prediction)
            .where(Prediction.content_brief_id == content_brief_id)
            .order_by(Prediction.created_at.desc())
            .limit(1)
        )
