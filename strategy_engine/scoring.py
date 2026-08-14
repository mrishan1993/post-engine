from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from strategy_engine.schemas import PriorityTier, StrategyProfile


def score_opportunity(
    *,
    profile: StrategyProfile,
    source: str,
    pillar: str | None,
    platform: str,
    payload: dict[str, Any] | None = None,
    learning_boost: float = 0.0,
) -> tuple[float, dict[str, float], PriorityTier]:
    """Portfolio-aware strategic score (not raw virality)."""
    payload = payload or {}
    trend_score = float(payload.get("opportunity_score") or payload.get("trend_score") or 0.5)
    freshness = float(payload.get("freshness_score") or 0.6)
    saturation = float(payload.get("saturation_score") or 0.3)
    velocity = float(payload.get("velocity_score") or trend_score)

    # Strategic fit vs pillars / mix
    mix = profile.content_mix or {}
    pillar_key = (pillar or source or "evergreen").lower()
    if pillar_key == "trends":
        pillar_key = "trend"
    mix_weight = float(mix.get(pillar_key, mix.get(source, 0.15)))

    brand_ok = 0.9
    forbidden = (profile.brand_constraints or {}).get("forbidden_topics") or []
    title = str(payload.get("title") or "").lower()
    forbidden_hit = any(str(t).lower() in title for t in forbidden)
    if forbidden_hit:
        brand_ok = 0.0

    audience_value = 0.75
    if payload.get("audience") or (profile.target_audiences):
        audience_value = 0.85

    expected_impact = min(1.0, 0.4 * trend_score + 0.3 * velocity + 0.3 * freshness)
    timing = min(1.0, freshness * (1.0 - 0.6 * saturation))
    historical = min(1.0, 0.55 + learning_boost)
    platform_fit = 0.9 if platform in (profile.platform_strategy or {}) else 0.65
    learning_value = 0.85 if source == "experiment" else (0.7 if source == "trend" else 0.55)
    effort = float(payload.get("effort") or (0.4 if source == "trend" else 0.35))
    risk = float(payload.get("risk") or (0.35 if source == "experiment" else 0.2))
    if forbidden_hit:
        risk = max(risk, 0.95)

    strategic_fit = min(1.0, 0.5 * mix_weight / max(0.1, max(mix.values()) if mix else 0.3) + 0.5 * brand_ok)
    if forbidden_hit:
        strategic_fit = min(strategic_fit, 0.1)

    dims = {
        "strategic_fit": round(strategic_fit, 4),
        "audience_value": round(audience_value, 4),
        "expected_impact": round(expected_impact, 4),
        "freshness": round(freshness, 4),
        "timing": round(timing, 4),
        "historical_evidence": round(historical, 4),
        "platform_fit": round(platform_fit, 4),
        "learning_value": round(learning_value, 4),
        "effort": round(effort, 4),
        "risk": round(risk, 4),
    }

    score = (
        dims["strategic_fit"] * 0.18
        + dims["audience_value"] * 0.12
        + dims["expected_impact"] * 0.18
        + dims["freshness"] * 0.10
        + dims["timing"] * 0.12
        + dims["historical_evidence"] * 0.10
        + dims["platform_fit"] * 0.08
        + dims["learning_value"] * 0.07
        - dims["effort"] * 0.05
        - dims["risk"] * 0.04
    )
    score = round(max(0.0, min(1.0, score)), 4)

    # Priority from urgency + score
    hours = payload.get("expiration_hours")
    if hours is None and source == "trend":
        hours = 18 if velocity > 0.8 else 36
    if hours is not None and float(hours) <= 12 and score >= 0.7:
        priority: PriorityTier = "P0"
    elif score >= 0.85:
        priority = "P1"
    elif score >= 0.7:
        priority = "P2"
    elif source == "experiment":
        priority = "P4"
    else:
        priority = "P3"

    return score, dims, priority


def estimate_expiration(
    source: str,
    payload: dict[str, Any] | None = None,
    *,
    now: datetime | None = None,
) -> datetime | None:
    now = now or datetime.now(timezone.utc)
    payload = payload or {}
    if source in {"evergreen", "campaign", "gap"}:
        return None
    hours = payload.get("expiration_hours")
    if hours is None:
        hours = {"trend": 18, "reactive": 12, "experiment": 168, "repurpose": 72}.get(source, 48)
    return now + timedelta(hours=float(hours))
