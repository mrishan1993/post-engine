from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import ContentFeature, RawContent, TrendLifecycle


def pattern_key_for(feature: ContentFeature, raw: RawContent) -> str:
    emotion = (feature.emotion or {}).get("dominant") or "unknown"
    story = (feature.story_arc or {}).get("pattern") or "unknown"
    fmt = feature.format or "unknown"
    return f"{emotion}:{story}:{fmt}"


def update_lifecycles(
    session: Session,
    pairs: list[tuple[RawContent, ContentFeature]],
) -> list[TrendLifecycle]:
    """Classify patterns into emerging → dead based on velocity + platform breadth."""
    buckets: dict[str, list[tuple[RawContent, ContentFeature]]] = {}
    for raw, feat in pairs:
        key = pattern_key_for(feat, raw)
        buckets.setdefault(key, []).append((raw, feat))

    rows: list[TrendLifecycle] = []
    for key, group in buckets.items():
        platforms = sorted({r.source for r, _ in group})
        avg_vph = _avg_views_per_hour(group)
        weekly_growth = _estimate_weekly_growth(group)
        stage = _classify_stage(avg_vph, weekly_growth, len(platforms), len(group))
        confidence = _confidence(platforms, avg_vph, weekly_growth)

        existing = session.scalar(
            select(TrendLifecycle).where(TrendLifecycle.pattern_key == key)
        )
        metrics = {
            "avg_views_per_hour": avg_vph,
            "weekly_growth_pct": weekly_growth,
            "sample_size": len(group),
            "platforms": platforms,
        }
        if existing:
            existing.stage = stage
            existing.confidence = confidence
            existing.platforms = platforms
            existing.metrics = metrics
            existing.updated_at = datetime.now(timezone.utc)
            rows.append(existing)
        else:
            row = TrendLifecycle(
                pattern_key=key,
                stage=stage,
                confidence=confidence,
                platforms=platforms,
                metrics=metrics,
                updated_at=datetime.now(timezone.utc),
            )
            session.add(row)
            rows.append(row)
    session.flush()
    return rows


def _avg_views_per_hour(group: list[tuple[RawContent, ContentFeature]]) -> float:
    vals = []
    for _, feat in group:
        v = (feat.velocity or {}).get("views_per_hour")
        if v is not None:
            vals.append(float(v))
        rising = (feat.velocity or {}).get("rising_ratio")
        if rising is not None:
            vals.append(float(rising) * 10_000)
    return sum(vals) / len(vals) if vals else 0.0


def _estimate_weekly_growth(group: list[tuple[RawContent, ContentFeature]]) -> float:
    # Heuristic from rising_ratio / velocity until time-series exists
    ratios = [
        float((f.velocity or {}).get("rising_ratio") or 0)
        for _, f in group
        if (f.velocity or {}).get("rising_ratio")
    ]
    if ratios:
        return max(ratios) * 100  # e.g. 1.5 → 150%
    vph = _avg_views_per_hour(group)
    if vph > 40_000:
        return 280.0
    if vph > 15_000:
        return 120.0
    if vph > 5_000:
        return 60.0
    return 20.0


def _classify_stage(
    avg_vph: float, weekly_growth: float, platform_count: int, sample_size: int
) -> str:
    if weekly_growth < 15 and avg_vph < 1_000:
        return "dead"
    if weekly_growth < 25 and sample_size > 8:
        return "declining"
    if sample_size > 12 and weekly_growth < 40:
        return "saturated"
    if weekly_growth >= 150 and platform_count >= 2:
        return "growing"
    if weekly_growth >= 80 or avg_vph >= 20_000:
        return "growing"
    if weekly_growth >= 200:
        return "peak"
    return "emerging"


def _confidence(platforms: list[str], avg_vph: float, weekly_growth: float) -> float:
    base = 0.35
    if len(platforms) >= 2:
        base += 0.35
    if len(platforms) >= 3:
        base += 0.15
    if avg_vph > 10_000:
        base += 0.1
    if weekly_growth > 100:
        base += 0.1
    return round(min(base, 0.98), 3)
