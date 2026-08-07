from __future__ import annotations

from sqlalchemy.orm import Session

from db.models import Publication, VideoMetric


def collect_stub_metrics(session: Session, publication_id: int) -> VideoMetric:
    """Placeholder metrics pull until YouTube Analytics API is wired."""
    pub = session.get(Publication, publication_id)
    if not pub:
        raise ValueError(f"publication {publication_id} not found")
    metric = VideoMetric(
        publication_id=publication_id,
        views=0,
        avg_view_duration_sec=0,
        likes=0,
        comments=0,
        estimated_revenue_usd=0,
    )
    session.add(metric)
    session.flush()
    return metric
