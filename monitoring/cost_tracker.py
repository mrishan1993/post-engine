from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import Vertical, VideoRun
from orchestration.state_machine import RunStatus


def cost_by_vertical(session: Session, days: int = 30) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = session.execute(
        select(
            Vertical.slug,
            func.avg(VideoRun.total_cost_usd),
            func.count(VideoRun.id),
        )
        .join(Vertical, Vertical.id == VideoRun.vertical_id)
        .where(
            VideoRun.created_at > cutoff,
            VideoRun.status == RunStatus.PUBLISHED.value,
        )
        .group_by(Vertical.slug)
    ).all()
    return [
        {"slug": slug, "avg_cost": float(avg or 0), "video_count": count}
        for slug, avg, count in rows
    ]
