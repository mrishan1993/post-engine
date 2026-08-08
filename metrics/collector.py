from __future__ import annotations

from sqlalchemy.orm import Session

from amp_platform.events import EventType, get_bus
from amp_platform.events.types import MetricsUpdated
from db.models import Publication, VideoMetric
from prediction.verification import verify_from_video_run


def collect_stub_metrics(
    session: Session,
    publication_id: int,
    *,
    views: int = 0,
    avg_view_duration_sec: int = 0,
    likes: int = 0,
    comments: int = 0,
    estimated_revenue_usd: float = 0,
    auto_verify: bool = True,
) -> VideoMetric:
    """Ingest metrics; optionally trigger Verification Engine for linked predictions."""
    pub = session.get(Publication, publication_id)
    if not pub:
        raise ValueError(f"publication {publication_id} not found")
    metric = VideoMetric(
        publication_id=publication_id,
        views=views,
        avg_view_duration_sec=avg_view_duration_sec,
        likes=likes,
        comments=comments,
        estimated_revenue_usd=estimated_revenue_usd,
    )
    session.add(metric)
    session.flush()
    get_bus().publish(
        EventType.METRICS_UPDATED,
        MetricsUpdated(
            publication_id=publication_id,
            video_run_id=pub.video_run_id,
            views=views,
            metrics={
                "likes": likes,
                "comments": comments,
                "avg_view_duration_sec": avg_view_duration_sec,
                "estimated_revenue_usd": estimated_revenue_usd,
            },
        ),
        producer="metrics-service",
    )
    if auto_verify and pub.video_run_id:
        verify_from_video_run(session, pub.video_run_id)
    return metric
