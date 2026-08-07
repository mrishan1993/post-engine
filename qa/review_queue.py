from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Vertical, VideoRun
from orchestration.state_machine import RunStatus


@dataclass
class ReviewItem:
    id: int
    title: str
    vertical: str
    flags: dict[str, Any]


def list_pending_reviews(session: Session) -> list[ReviewItem]:
    rows = session.execute(
        select(VideoRun, Vertical)
        .join(Vertical, Vertical.id == VideoRun.vertical_id)
        .where(VideoRun.status == RunStatus.QA_PENDING.value)
        .order_by(VideoRun.updated_at.asc())
    ).all()
    items: list[ReviewItem] = []
    for run, vertical in rows:
        flags = {}
        if run.safety_check_result and isinstance(run.safety_check_result, dict):
            flags = run.safety_check_result.get("flags") or {}
        items.append(
            ReviewItem(
                id=run.id,
                title=run.title or "(untitled)",
                vertical=vertical.slug,
                flags=flags,
            )
        )
    return items
