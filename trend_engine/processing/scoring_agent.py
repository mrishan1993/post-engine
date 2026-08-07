from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from db.models import TrendScore, TrendSignal, TrendTopic, TrendTopicSignal


DEFAULT_WEIGHTS = {
    "youtube_velocity": 0.4,
    "youtube_recency": 0.15,
    "google_trends_interest": 0.25,
    "tiktok_presence": 0.15,
    "cross_source_confirmation": 0.05,
}


def score_topics(
    session: Session,
    topics: list[TrendTopic],
    *,
    weights: dict[str, float] | None = None,
) -> list[TrendScore]:
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    results: list[TrendScore] = []
    for topic in topics:
        signals = _signals_for_topic(session, topic.id)
        breakdown = _compute_sub_scores(signals)
        composite = sum(breakdown[k] * weights.get(k, 0.0) for k in weights)
        row = TrendScore(
            topic_id=topic.id,
            score=round(composite, 3),
            score_breakdown=breakdown,
            scored_at=datetime.now(timezone.utc),
        )
        session.add(row)
        results.append(row)
    session.flush()
    return results


def _signals_for_topic(session: Session, topic_id: int) -> list[TrendSignal]:
    from sqlalchemy import select

    links = session.scalars(
        select(TrendTopicSignal).where(TrendTopicSignal.topic_id == topic_id)
    ).all()
    ids = [link.signal_id for link in links]
    if not ids:
        return []
    return list(session.scalars(select(TrendSignal).where(TrendSignal.id.in_(ids))).all())


def _compute_sub_scores(signals: list[TrendSignal]) -> dict[str, float]:
    yt = [s for s in signals if s.source == "youtube"]
    gt = [s for s in signals if s.source == "google_trends"]
    tt = [s for s in signals if s.source == "tiktok"]
    sources = {s.source for s in signals}

    return {
        "youtube_velocity": _normalize_velocity(yt),
        "youtube_recency": _normalize_recency(yt),
        "google_trends_interest": _normalize_trends(gt),
        "tiktok_presence": 1.0 if tt else 0.0,
        "cross_source_confirmation": 1.0 if len(sources) >= 2 else 0.0,
    }


def _normalize_velocity(yt_signals: list[TrendSignal]) -> float:
    if not yt_signals:
        return 0.0
    velocities = [
        float((s.raw_metrics or {}).get("velocity_views_per_hour") or 0.0) for s in yt_signals
    ]
    # Soft cap: 50k views/hour ≈ 1.0 (favor velocity over absolute popularity)
    peak = max(velocities)
    return min(peak / 50_000.0, 1.0)


def _normalize_recency(yt_signals: list[TrendSignal]) -> float:
    if not yt_signals:
        return 0.0
    ages = [float((s.raw_metrics or {}).get("age_hours") or 72.0) for s in yt_signals]
    age = min(ages)
    # Full score under 6h, linear decay to 0 at 72h
    if age <= 6:
        return 1.0
    if age >= 72:
        return 0.0
    return max(0.0, 1.0 - (age - 6) / 66.0)


def _normalize_trends(gt_signals: list[TrendSignal]) -> float:
    if not gt_signals:
        return 0.0
    scores = []
    for s in gt_signals:
        m = s.raw_metrics or {}
        latest = float(m.get("interest_latest") or 0.0) / 100.0
        rising = min(float(m.get("rising_ratio") or 0.0) / 2.0, 1.0)
        scores.append(0.6 * latest + 0.4 * rising)
    return max(scores) if scores else 0.0


def compute_trend_score(topic_signals: list[dict[str, Any]], weights: dict[str, float] | None = None) -> dict:
    """Pure-function form from PRP §6 — useful for unit tests without a DB session."""
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    # Adapt dict-shaped fixtures into lightweight stand-ins
    class _S:
        def __init__(self, d: dict[str, Any]):
            self.source = d.get("source", "")
            self.raw_metrics = d.get("raw_metrics", {})

    signals = [_S(d) for d in topic_signals]
    breakdown = _compute_sub_scores(signals)  # type: ignore[arg-type]
    composite = sum(breakdown[k] * weights.get(k, 0.0) for k in weights)
    return {"score": composite, "breakdown": breakdown}
