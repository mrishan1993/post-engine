from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import ContentBrief, TrendScore, TrendTopic, Vertical


def generate_briefs(
    session: Session,
    topics: list[TrendTopic],
    *,
    min_score: float = 0.55,
    max_briefs: int = 10,
) -> list[ContentBrief]:
    """Insert top-scored topics into content_briefs with source='trend_engine'."""
    created: list[ContentBrief] = []
    scored: list[tuple[TrendTopic, float]] = []
    for topic in topics:
        latest = session.scalar(
            select(TrendScore)
            .where(TrendScore.topic_id == topic.id)
            .order_by(TrendScore.scored_at.desc())
            .limit(1)
        )
        if not latest:
            continue
        score = float(latest.score)
        if score < min_score:
            continue
        if topic.status == "briefed":
            continue
        scored.append((topic, score))

    scored.sort(key=lambda x: x[1], reverse=True)

    for topic, score in scored:
        if len(created) >= max_briefs:
            break
        verticals = list(topic.candidate_verticals or [])
        if not verticals:
            continue
        for slug in verticals:
            if len(created) >= max_briefs:
                break
            vertical = session.scalar(select(Vertical).where(Vertical.slug == slug))
            if not vertical:
                # Auto-register vertical shell so briefs aren't dropped if YAML exists
                # but DB row wasn't seeded yet — pipeline.ensure_vertical is preferred;
                # here we skip unknown slugs.
                continue
            brief = ContentBrief(
                vertical_id=vertical.id,
                brief_text=f"{topic.topic_label}: {topic.description or ''}".strip(),
                priority=int(score * 10),
                status="pending",
                source="trend_engine",
            )
            session.add(brief)
            created.append(brief)
        topic.status = "briefed"

    session.flush()
    return created
