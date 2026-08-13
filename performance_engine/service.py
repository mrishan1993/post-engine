from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from performance_engine.benchmarks import compute_benchmarks
from performance_engine.collector import PerformanceCollector
from performance_engine.schemas import (
    CompareRequest,
    ContentFingerprint,
    RefreshRequest,
    StartTrackingRequest,
)
from db.models import (
    AnalyticsCollectionJob,
    AudienceSnapshot,
    PerformanceSnapshot,
    PerformanceTimeseries,
    PlatformMetricResponse,
    PostAnalytics,
    PublicationReceipt,
    RetentionCurve,
)


class PerformanceService:
    def __init__(self, session: Session):
        self.session = session
        self.collector = PerformanceCollector(session)

    def start_tracking(self, request: StartTrackingRequest | dict[str, Any]) -> AnalyticsCollectionJob:
        req = (
            request
            if isinstance(request, StartTrackingRequest)
            else StartTrackingRequest.model_validate(request)
        )
        fp = req.content_fingerprint
        if isinstance(fp, dict):
            fp = {**fp, "growth_profile": req.growth_profile}
        elif isinstance(fp, ContentFingerprint):
            data = fp.model_dump()
            data["growth_profile"] = req.growth_profile
            fp = data
        else:
            fp = {"growth_profile": req.growth_profile}
        return self.collector.start_tracking(
            req.publication_id,
            content_fingerprint=fp,
            prediction=req.prediction,
            collect_now=req.collect_now,
            simulate_age_sec=req.simulate_age_sec,
            growth_profile=req.growth_profile,
        )

    def refresh(self, request: RefreshRequest | dict[str, Any]) -> PerformanceSnapshot:
        req = (
            request
            if isinstance(request, RefreshRequest)
            else RefreshRequest.model_validate(request)
        )
        return self.collector.collect(
            req.publication_id,
            simulate_age_sec=req.simulate_age_sec,
            growth_profile=req.growth_profile,
        )

    def get_performance(self, publication_id: str) -> dict[str, Any]:
        receipt = self._get_receipt(publication_id)
        analytics = self.session.get(PostAnalytics, receipt.id)
        latest = self.session.scalars(
            select(PerformanceSnapshot)
            .where(PerformanceSnapshot.publication_id == receipt.id)
            .order_by(PerformanceSnapshot.captured_at.desc())
        ).first()
        return {
            "publication_id": receipt.id,
            "content_id": receipt.content_id,
            "prediction_id": (receipt.lineage or {}).get("prediction_id"),
            "platform": receipt.platform,
            "external_post_id": receipt.external_post_id,
            "url": receipt.post_url,
            "analytics": {
                "views": analytics.current_views if analytics else None,
                "likes": analytics.current_likes if analytics else None,
                "comments": analytics.current_comments if analytics else None,
                "shares": analytics.current_shares if analytics else None,
                "saves": analytics.current_saves if analytics else None,
                "reach": analytics.current_reach if analytics else None,
                "engagement_rate": float(analytics.engagement_rate or 0) if analytics else None,
                "share_rate": float(analytics.share_rate or 0) if analytics else None,
                "save_rate": float(analytics.save_rate or 0) if analytics else None,
                "completion_rate": float(analytics.completion_rate or 0) if analytics else None,
                "virality_score": float(analytics.virality_score or 0) if analytics else None,
                "performance_index": float(analytics.performance_index or 0) if analytics else None,
                "percentile_rank": float(analytics.percentile_rank or 0) if analytics else None,
                "view_velocity_per_hour": (
                    float(analytics.view_velocity_per_hour or 0) if analytics else None
                ),
                "acceleration": float(analytics.acceleration or 0) if analytics else None,
                "viral_state": analytics.viral_state if analytics else None,
                "performance_vector": analytics.performance_vector if analytics else None,
                "first_hour": analytics.first_hour if analytics else None,
                "prediction_link": analytics.prediction_link if analytics else None,
                "content_fingerprint": analytics.content_fingerprint if analytics else None,
                "engagement_formula_version": (
                    analytics.engagement_formula_version if analytics else None
                ),
                "virality_model_version": analytics.virality_model_version if analytics else None,
            },
            "latest_snapshot": {
                "id": latest.id,
                "captured_at": latest.captured_at.isoformat() if latest else None,
                "age_since_publish_sec": latest.age_since_publish_sec if latest else None,
                "metrics": latest.metrics if latest else None,
                "derived": latest.derived if latest else None,
            }
            if latest
            else None,
            "lineage": receipt.lineage,
        }

    def get_timeseries(self, publication_id: str, metric: str = "views") -> list[dict[str, Any]]:
        receipt = self._get_receipt(publication_id)
        rows = list(
            self.session.scalars(
                select(PerformanceTimeseries)
                .where(
                    PerformanceTimeseries.publication_id == receipt.id,
                    PerformanceTimeseries.metric == metric,
                )
                .order_by(PerformanceTimeseries.timestamp.asc())
            ).all()
        )
        return [
            {
                "timestamp": r.timestamp.isoformat(),
                "value": float(r.value or 0),
                "metric": r.metric,
                "source": r.source,
            }
            for r in rows
        ]

    def get_retention(self, publication_id: str) -> list[dict[str, Any]]:
        receipt = self._get_receipt(publication_id)
        rows = list(
            self.session.scalars(
                select(RetentionCurve)
                .where(RetentionCurve.publication_id == receipt.id)
                .order_by(RetentionCurve.timestamp_sec.asc())
            ).all()
        )
        return [
            {
                "timestamp_sec": float(r.timestamp_sec),
                "retention_percent": float(r.retention_percent),
                "source": r.source,
            }
            for r in rows
        ]

    def get_audience(self, publication_id: str) -> dict[str, Any] | None:
        receipt = self._get_receipt(publication_id)
        row = self.session.scalars(
            select(AudienceSnapshot)
            .where(AudienceSnapshot.publication_id == receipt.id)
            .order_by(AudienceSnapshot.captured_at.desc())
        ).first()
        if not row:
            return None
        return {
            "follower_count": row.follower_count,
            "non_follower_reach": row.non_follower_reach,
            "demographics": row.demographics,
            "geography": row.geography,
            "captured_at": row.captured_at.isoformat(),
        }

    def get_benchmarks(self, publication_id: str, metric: str = "views") -> list[dict[str, Any]]:
        receipt = self._get_receipt(publication_id)
        analytics = self.session.get(PostAnalytics, receipt.id)
        character = (analytics.content_fingerprint or {}).get("character") if analytics else None
        benches = compute_benchmarks(
            self.session,
            publication_id=receipt.id,
            metric=metric,
            character=character,
            platform=receipt.platform,
        )
        return [b.model_dump() for b in benches]

    def get_raw_responses(self, publication_id: str) -> list[dict[str, Any]]:
        receipt = self._get_receipt(publication_id)
        rows = list(
            self.session.scalars(
                select(PlatformMetricResponse)
                .where(PlatformMetricResponse.publication_id == receipt.id)
                .order_by(PlatformMetricResponse.captured_at.desc())
            ).all()
        )
        return [
            {
                "id": r.id,
                "endpoint": r.endpoint,
                "http_status": r.http_status,
                "captured_at": r.captured_at.isoformat(),
                "response": r.response,
            }
            for r in rows
        ]

    def compare(self, request: CompareRequest | dict[str, Any]) -> dict[str, Any]:
        req = (
            request if isinstance(request, CompareRequest) else CompareRequest.model_validate(request)
        )
        posts = [self.get_performance(pid) for pid in req.publication_ids]
        return {"posts": posts}

    def list_snapshots(self, publication_id: str) -> list[PerformanceSnapshot]:
        receipt = self._get_receipt(publication_id)
        return list(
            self.session.scalars(
                select(PerformanceSnapshot)
                .where(PerformanceSnapshot.publication_id == receipt.id)
                .order_by(PerformanceSnapshot.captured_at.asc())
            ).all()
        )

    def _get_receipt(self, publication_id: str) -> PublicationReceipt:
        row = self.session.get(PublicationReceipt, publication_id)
        if row:
            return row
        rows = list(
            self.session.scalars(
                select(PublicationReceipt).where(
                    PublicationReceipt.id.startswith(publication_id)
                )
            ).all()
        )
        if len(rows) != 1:
            raise ValueError("publication receipt not found")
        return rows[0]
