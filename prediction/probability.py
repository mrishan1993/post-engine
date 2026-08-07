from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from prediction.explainability import build_reasoning
from prediction.features import FeatureVector, engineer_features

MODEL_VERSION = "rule_v1"

# Weights for virality probability (Phase 1 rule-based)
VIRALITY_WEIGHTS = {
    "hook_strength": 0.16,
    "trend_velocity": 0.14,
    "lifecycle_score": 0.12,
    "curiosity_score": 0.08,
    "fear_score": 0.06,
    "joy_score": 0.05,
    "novelty": 0.08,
    "character_fit": 0.08,
    "audience_fit": 0.06,
    "cross_platform": 0.07,
    "posting_fit": 0.05,
    "similar_winners": 0.05,
}

# Competition and story complexity act as mild penalties when high complexity + high competition
PENALTY_FEATURES = {
    "competition": 0.12,
    "story_complexity": 0.04,  # very complex shorts can hurt retention
}


@dataclass
class PredictionResult:
    virality_probability: float
    confidence: float
    predicted_views: int
    predicted_views_low: int
    predicted_views_high: int
    predicted_reach: int
    predicted_ctr: float
    predicted_watch_time_sec: float
    predicted_retention: float
    predicted_engagement_rate: float
    predicted_shares: int
    predicted_saves: int
    predicted_comments: int
    predicted_followers: int
    predicted_revenue_usd: float
    predicted_roi: float
    expected_cost_usd: float
    risk_score: float
    final_opportunity_score: float
    metrics_json: dict[str, Any] = field(default_factory=dict)
    reasoning_json: dict[str, Any] = field(default_factory=dict)
    features: FeatureVector = field(default_factory=FeatureVector)
    model_version: str = MODEL_VERSION


def predict_from_features(
    features: FeatureVector,
    *,
    calibration: dict[str, float] | None = None,
    base_views: int = 50_000,
) -> PredictionResult:
    """Core probability engine — never returns a single number."""
    calibration = calibration or {}
    vertical = str(features.raw.get("vertical_slug") or "default")
    vertical_bias = float(calibration.get(vertical, 1.0))

    viral = _weighted(features, VIRALITY_WEIGHTS)
    penalty = _weighted(features, PENALTY_FEATURES)
    virality = _clamp(viral * (1.0 - 0.35 * penalty) * vertical_bias, 0.05, 0.97)

    # Confidence: higher when trend confidence + similar winners + cross-platform
    confidence = _clamp(
        0.35
        + 0.25 * features.get("trend_confidence")
        + 0.2 * features.get("similar_winners")
        + 0.15 * features.get("cross_platform")
        + 0.05 * features.get("character_familiarity"),
        0.2,
        0.96,
    )
    # Low lifecycle / high competition → lower confidence
    if features.get("lifecycle_score") < 0.3:
        confidence = _clamp(confidence * 0.6, 0.2, 0.96)

    expected_views = int(base_views * (0.4 + 8.0 * virality) * vertical_bias)
    spread = 0.35 + (1.0 - confidence) * 0.5
    views_low = max(int(expected_views * (1 - spread)), 100)
    views_high = int(expected_views * (1 + spread))

    ctr = _clamp(0.04 + 0.08 * features.get("hook_strength") + 0.02 * features.get("curiosity_score"), 0.02, 0.18)
    retention = _clamp(
        0.35
        + 0.25 * features.get("hook_strength")
        + 0.15 * (1.0 - features.get("story_complexity") * 0.5)
        + 0.1 * features.get("editing_density"),
        0.2,
        0.85,
    )
    watch_time = round(15 + 40 * retention, 2)
    engagement = _clamp(0.02 + 0.06 * virality + 0.03 * features.get("fear_score"), 0.01, 0.2)
    shares = int(expected_views * engagement * 0.35)
    saves = int(expected_views * engagement * 0.25)
    comments = int(expected_views * engagement * 0.08)
    followers = int(expected_views * engagement * 0.05)
    reach = int(expected_views / max(ctr, 0.02))

    cost = max(features.get("expected_cost"), 0.5)
    # Rough Shorts RPM proxy
    rpm = 0.8 + 1.5 * features.get("audience_fit")
    revenue = round((expected_views / 1000.0) * rpm, 2)
    roi = round((revenue - cost) / cost, 3) if cost else 0.0

    risk = _clamp(
        0.2 + 0.4 * features.get("competition") + 0.3 * (1.0 - features.get("lifecycle_score")),
        0.05,
        0.95,
    )

    # Final opportunity score blends EV + probability + confidence − risk
    final_score = _clamp(
        100
        * (
            0.35 * virality
            + 0.25 * min(roi / 50.0, 1.0)
            + 0.2 * confidence
            + 0.1 * (revenue / max(expected_views * 0.002, 1))
            + 0.1 * (1.0 - risk)
        ),
        1,
        99,
    )

    metrics = {
        "discovery": {
            "virality_probability": round(virality, 4),
            "reach": reach,
            "impressions": reach,
            "browse_probability": round(0.3 + 0.4 * virality, 4),
            "suggested_probability": round(0.25 + 0.5 * virality, 4),
            "shorts_shelf_probability": round(0.2 + 0.55 * virality, 4),
            "explore_probability": round(0.15 + 0.4 * features.get("novelty"), 4),
        },
        "click": {
            "ctr": round(ctr, 4),
            "thumbnail_ctr": round(ctr * 0.9, 4),
            "hook_retention": round(min(retention + 0.1, 0.95), 4),
        },
        "watch": {
            "watch_time_sec": watch_time,
            "average_view_duration_sec": watch_time,
            "completion_rate": round(retention, 4),
            "retention_curve": _retention_curve(retention),
        },
        "engagement": {
            "like_rate": round(engagement * 1.2, 4),
            "comment_rate": round(engagement * 0.15, 4),
            "share_rate": round(engagement * 0.35, 4),
            "save_rate": round(engagement * 0.25, 4),
            "follow_conversion": round(engagement * 0.08, 4),
            "profile_visits": int(followers * 2.5),
        },
        "business": {
            "revenue_usd": revenue,
            "rpm": round(rpm, 3),
            "cost_per_view": round(cost / max(expected_views, 1), 6),
            "roi": roi,
            "subscriber_growth": followers,
            "brand_safety_score": round(0.7 + 0.25 * features.get("brand_fit"), 3),
        },
    }

    reasoning = build_reasoning(features, virality=virality, confidence=confidence)

    return PredictionResult(
        virality_probability=round(virality, 4),
        confidence=round(confidence, 4),
        predicted_views=expected_views,
        predicted_views_low=views_low,
        predicted_views_high=views_high,
        predicted_reach=reach,
        predicted_ctr=round(ctr, 4),
        predicted_watch_time_sec=watch_time,
        predicted_retention=round(retention, 4),
        predicted_engagement_rate=round(engagement, 4),
        predicted_shares=shares,
        predicted_saves=saves,
        predicted_comments=comments,
        predicted_followers=followers,
        predicted_revenue_usd=revenue,
        predicted_roi=roi,
        expected_cost_usd=cost,
        risk_score=round(risk, 4),
        final_opportunity_score=round(final_score, 2),
        metrics_json=metrics,
        reasoning_json=reasoning,
        features=features,
        model_version=MODEL_VERSION,
    )


def predict_opportunity(
    *,
    opportunity: dict[str, Any],
    score_breakdown: dict[str, Any] | None = None,
    lifecycle_stage: str | None = None,
    vertical_slug: str | None = None,
    character: dict[str, Any] | None = None,
    platform: str = "youtube",
    posting_hour: int = 21,
    expected_cost_usd: float = 1.0,
    similar_winners: int = 0,
    calibration: dict[str, float] | None = None,
) -> PredictionResult:
    features = engineer_features(
        opportunity=opportunity,
        score_breakdown=score_breakdown,
        lifecycle_stage=lifecycle_stage,
        vertical_slug=vertical_slug,
        character=character,
        platform=platform,
        posting_hour=posting_hour,
        expected_cost_usd=expected_cost_usd,
        similar_winners=similar_winners,
    )
    return predict_from_features(features, calibration=calibration)


def predict_variants(
    variants: list[dict[str, Any]],
    *,
    base_opportunity: dict[str, Any],
    vertical_slug: str,
    **kwargs: Any,
) -> list[tuple[dict[str, Any], PredictionResult]]:
    """Score hook/script variants independently; caller picks the best."""
    results: list[tuple[dict[str, Any], PredictionResult]] = []
    for variant in variants:
        opp = {**base_opportunity, **variant.get("opportunity_overrides", {})}
        if "hook" in variant:
            opp["hook"] = variant["hook"]
            opp["hook_type"] = variant.get("hook_type", opp.get("hook_type"))
        pred = predict_opportunity(
            opportunity=opp,
            vertical_slug=vertical_slug,
            character=variant.get("character"),
            **kwargs,
        )
        results.append((variant, pred))
    results.sort(key=lambda x: x[1].final_opportunity_score, reverse=True)
    return results


def _weighted(features: FeatureVector, weights: dict[str, float]) -> float:
    total_w = sum(weights.values()) or 1.0
    return sum(features.get(k) * w for k, w in weights.items()) / total_w


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _retention_curve(retention: float) -> list[float]:
    """Synthetic retention checkpoints at 0%, 25%, 50%, 75%, 100%."""
    return [
        1.0,
        round(min(0.95, retention + 0.25), 3),
        round(min(0.9, retention + 0.1), 3),
        round(retention, 3),
        round(max(retention - 0.15, 0.1), 3),
    ]
