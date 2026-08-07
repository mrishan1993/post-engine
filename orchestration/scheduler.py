from __future__ import annotations

"""Cron-friendly entry helpers.

Example crontab:
0 6 * * * cd /path/to/post-engine && pipeline run --vertical kids_rhymes >> logs/cron.log 2>&1
"""

from sqlalchemy import select

from db.models import ContentBrief
from db.session import get_session, init_db
from orchestration.pipeline import Pipeline


def run_next_brief(vertical_slug: str) -> int | None:
    """Pick highest-priority pending brief for a vertical and run to qa_pending."""
    init_db()
    with get_session() as session:
        pipeline = Pipeline(session)
        vertical = pipeline.ensure_vertical(vertical_slug)
        brief = session.scalar(
            select(ContentBrief)
            .where(
                ContentBrief.vertical_id == vertical.id,
                ContentBrief.status == "pending",
            )
            .order_by(ContentBrief.priority.desc(), ContentBrief.created_at.asc())
        )
        if not brief:
            return None
        run = pipeline.create_run(brief)
        pipeline.run_until_qa(run.id)
        return run.id
