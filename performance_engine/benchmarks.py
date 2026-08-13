from __future__ import annotations

from statistics import median
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from performance_engine.schemas import BenchmarkResult
from db.models import PostAnalytics


def percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    k = (len(sorted_vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return float(sorted_vals[f])
    return float(sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f))


def compute_benchmarks(
    session: Session,
    *,
    publication_id: str,
    metric: str = "views",
    character: str | None = None,
    platform: str | None = None,
) -> list[BenchmarkResult]:
    """Cold-start hierarchy: character → platform → global."""
    rows = list(session.scalars(select(PostAnalytics)).all())
    current = session.get(PostAnalytics, publication_id)
    current_val = _metric_value(current, metric) if current else 0.0

    results: list[BenchmarkResult] = []
    # Character
    if character:
        char_vals = [
            _metric_value(r, metric)
            for r in rows
            if (r.content_fingerprint or {}).get("character") == character
            and r.publication_id != publication_id
        ]
        results.append(_bench("character", character, char_vals, metric, current_val))
    # Platform
    if platform:
        plat_vals = [
            _metric_value(r, metric)
            for r in rows
            if r.platform == platform and r.publication_id != publication_id
        ]
        results.append(_bench("platform", platform, plat_vals, metric, current_val))
    # Global
    global_vals = [
        _metric_value(r, metric) for r in rows if r.publication_id != publication_id
    ]
    results.append(_bench("global", "all", global_vals, metric, current_val))
    return results


def _metric_value(row: PostAnalytics | None, metric: str) -> float:
    if not row:
        return 0.0
    mapping = {
        "views": row.current_views,
        "likes": row.current_likes,
        "shares": row.current_shares,
        "engagement_rate": row.engagement_rate,
        "virality_score": row.virality_score,
        "completion_rate": row.completion_rate,
        "view_velocity": row.view_velocity_per_hour,
        "share_rate": row.share_rate,
    }
    return float(mapping.get(metric) or 0)


def _bench(
    dimension: str, key: str, values: list[float], metric: str, current: float
) -> BenchmarkResult:
    # Cold start defaults when empty
    if not values:
        defaults = {
            "views": [50_000, 84_000, 100_000, 190_000, 480_000, 920_000],
            "view_velocity": [5_000, 12_000, 25_000, 40_000, 80_000],
            "share_rate": [0.01, 0.015, 0.02, 0.03, 0.04],
            "engagement_rate": [0.04, 0.06, 0.08, 0.1],
        }
        values = list(defaults.get(metric, [1.0, 2.0, 3.0]))
    vals = sorted(float(v) for v in values)
    med = float(median(vals))
    p75 = percentile(vals, 0.75)
    p90 = percentile(vals, 0.90)
    p95 = percentile(vals, 0.95)
    idx = (current / med) if med else None
    # percentile rank of current among sample + itself
    below = sum(1 for v in vals if v <= current)
    rank = below / max(len(vals), 1)
    return BenchmarkResult(
        dimension=dimension,
        key=key,
        sample_size=len(values),
        metric=metric,
        median=round(med, 6),
        p75=round(p75, 6),
        p90=round(p90, 6),
        p95=round(p95, 6),
        performance_index=round(idx, 4) if idx is not None else None,
        percentile_rank=round(rank, 4),
    )


def default_velocity_share_benchmarks(character: str | None = None) -> dict[str, float]:
    """Fallback thresholds used by viral state when history is thin."""
    return {
        "p95_velocity": 80_000.0 if not character else 60_000.0,
        "p75_share_rate": 0.03,
    }
