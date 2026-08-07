from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import ContentBrief, Publication, VideoMetric, VideoRun


def top_briefs_by_views(session: Session, limit: int = 20) -> list[tuple[str, int]]:
    rows = session.execute(
        select(ContentBrief.brief_text, func.coalesce(func.sum(VideoMetric.views), 0))
        .join(VideoRun, VideoRun.brief_id == ContentBrief.id)
        .join(Publication, Publication.video_run_id == VideoRun.id)
        .join(VideoMetric, VideoMetric.publication_id == Publication.id)
        .group_by(ContentBrief.brief_text)
        .order_by(func.sum(VideoMetric.views).desc())
        .limit(limit)
    ).all()
    return [(text, int(views)) for text, views in rows]
