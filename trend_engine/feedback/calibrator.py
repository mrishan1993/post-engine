from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import (
    ContentBrief,
    Publication,
    TrendFeedback,
    TrendScore,
    TrendTopic,
    VideoMetric,
    VideoRun,
)


def record_feedback(session: Session, topic_id: int, content_brief_id: int) -> TrendFeedback | None:
    """Compare predicted trend score vs published video metrics for a brief."""
    topic = session.get(TrendTopic, topic_id)
    brief = session.get(ContentBrief, content_brief_id)
    if not topic or not brief:
        return None

    predicted = session.scalar(
        select(TrendScore)
        .where(TrendScore.topic_id == topic_id)
        .order_by(TrendScore.scored_at.desc())
        .limit(1)
    )
    run = session.scalar(
        select(VideoRun)
        .where(VideoRun.brief_id == content_brief_id, VideoRun.status == "published")
        .order_by(VideoRun.created_at.desc())
        .limit(1)
    )
    views = 0
    engagement = 0.0
    if run:
        pubs = session.scalars(
            select(Publication).where(Publication.video_run_id == run.id)
        ).all()
        for pub in pubs:
            metric = session.scalar(
                select(VideoMetric)
                .where(VideoMetric.publication_id == pub.id)
                .order_by(VideoMetric.pulled_at.desc())
                .limit(1)
            )
            if metric:
                views += int(metric.views or 0)
                likes = int(metric.likes or 0)
                comments = int(metric.comments or 0)
                if views > 0:
                    engagement = max(engagement, (likes + comments) / views)

    row = TrendFeedback(
        topic_id=topic_id,
        content_brief_id=content_brief_id,
        predicted_score=float(predicted.score) if predicted else None,
        actual_views=views,
        actual_engagement_rate=round(engagement, 4),
        recorded_at=datetime.now(timezone.utc),
    )
    session.add(row)
    session.flush()
    return row


def suggest_weight_adjustments(session: Session) -> dict[str, str]:
    """Monthly manual calibration helper — not auto-retraining (PRP §9)."""
    rows = session.scalars(select(TrendFeedback)).all()
    if len(rows) < 5:
        return {"status": "insufficient_data", "n": str(len(rows))}

    # Simple correlation proxy: high predicted + low views → overconfident
    overconfident = [
        r
        for r in rows
        if r.predicted_score is not None
        and float(r.predicted_score) >= 0.7
        and int(r.actual_views or 0) < 1000
    ]
    underconfident = [
        r
        for r in rows
        if r.predicted_score is not None
        and float(r.predicted_score) < 0.5
        and int(r.actual_views or 0) >= 10_000
    ]
    return {
        "status": "review",
        "n": str(len(rows)),
        "overconfident_count": str(len(overconfident)),
        "underconfident_count": str(len(underconfident)),
        "suggestion": (
            "If overconfident_count dominates, discount tiktok_presence / "
            "raise youtube_velocity weight after review."
            if len(overconfident) > len(underconfident)
            else "Weights look roughly calibrated; keep defaults another cycle."
        ),
    }
