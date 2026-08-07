from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FeatureVector:
    values: dict[str, float] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def get(self, name: str, default: float = 0.0) -> float:
        return float(self.values.get(name, default))


HOOK_STRENGTH = {
    "question": 0.75,
    "shock": 0.88,
    "curiosity": 0.82,
    "fear": 0.9,
    "relatability": 0.7,
    "open_loop": 0.92,
    "unknown": 0.45,
}

LIFECYCLE_SCORE = {
    "emerging": 0.85,
    "growing": 0.95,
    "peak": 0.7,
    "saturated": 0.25,
    "declining": 0.15,
    "dead": 0.05,
}


def engineer_features(
    *,
    opportunity: dict[str, Any] | None = None,
    score_breakdown: dict[str, Any] | None = None,
    lifecycle_stage: str | None = None,
    vertical_slug: str | None = None,
    character: dict[str, Any] | None = None,
    platform: str = "youtube",
    posting_hour: int = 21,
    expected_cost_usd: float = 1.0,
    similar_winners: int = 0,
) -> FeatureVector:
    """Turn trend/opportunity/character context into a numeric feature vector."""
    opp = opportunity or {}
    breakdown = {k: float(v) for k, v in (score_breakdown or {}).items()}
    emotion = (opp.get("emotion") or "curiosity").lower()
    hook_type = (opp.get("hook_type") or "unknown").lower()
    story = (opp.get("story_pattern") or "linear").lower()
    editing = (opp.get("editing_style") or "medium").lower()
    platforms = opp.get("platforms") or [platform]
    confidence_trend = float(opp.get("confidence") or 0.5)

    emotion_scores = {
        "fear": 0.2,
        "joy": 0.2,
        "curiosity": 0.2,
        "surprise": 0.2,
        "anger": 0.1,
        "hope": 0.1,
    }
    emotion_scores[emotion] = 0.85

    hook_strength = HOOK_STRENGTH.get(hook_type, 0.5)
    if opp.get("hook") and len(str(opp.get("hook"))) > 20:
        hook_strength = min(hook_strength + 0.05, 1.0)

    story_complexity = {
        "pov": 0.55,
        "twist": 0.75,
        "rhyme_loop": 0.35,
        "linear": 0.4,
    }.get(story, 0.45)

    editing_density = {"fast": 0.85, "medium": 0.55, "slow": 0.3}.get(editing, 0.55)
    trend_velocity = breakdown.get("virality") or breakdown.get("growth") or 0.5
    competition = 1.0 - breakdown.get("competition", 0.5)  # higher = more competition
    novelty = breakdown.get("novelty", 0.5)
    character_fit = breakdown.get("character_fit", 0.5)
    audience_fit = breakdown.get("audience_fit", 0.5)
    brand_fit = breakdown.get("brand_fit", 0.5)

    character_familiarity = 0.5
    if character:
        # Known cast members get a familiarity bump
        character_familiarity = 0.79 if character.get("slug") else 0.5

    lifecycle = LIFECYCLE_SCORE.get(lifecycle_stage or opp.get("lifecycle") or "emerging", 0.5)
    cross_platform = min(len(platforms) / 3.0, 1.0)
    similar_signal = min(similar_winners / 20.0, 1.0)

    # Posting hour: evenings 19-22 score higher for short-form
    if 19 <= posting_hour <= 22:
        posting_fit = 0.85
    elif 12 <= posting_hour <= 14:
        posting_fit = 0.65
    else:
        posting_fit = 0.45

    values = {
        "hook_strength": round(hook_strength, 4),
        "fear_score": round(emotion_scores.get("fear", 0.2), 4),
        "joy_score": round(emotion_scores.get("joy", 0.2), 4),
        "curiosity_score": round(emotion_scores.get("curiosity", 0.2), 4),
        "surprise_score": round(emotion_scores.get("surprise", 0.2), 4),
        "story_complexity": round(story_complexity, 4),
        "editing_density": round(editing_density, 4),
        "trend_velocity": round(float(trend_velocity), 4),
        "competition": round(float(competition), 4),
        "novelty": round(float(novelty), 4),
        "character_fit": round(float(character_fit), 4),
        "character_familiarity": round(character_familiarity, 4),
        "audience_fit": round(float(audience_fit), 4),
        "brand_fit": round(float(brand_fit), 4),
        "lifecycle_score": round(lifecycle, 4),
        "cross_platform": round(cross_platform, 4),
        "trend_confidence": round(confidence_trend, 4),
        "posting_fit": round(posting_fit, 4),
        "similar_winners": round(similar_signal, 4),
        "expected_cost": round(expected_cost_usd, 4),
    }
    raw = {
        "emotion": emotion,
        "hook_type": hook_type,
        "story_pattern": story,
        "platform": platform,
        "platforms": platforms,
        "posting_hour": posting_hour,
        "vertical_slug": vertical_slug,
        "character_slug": (character or {}).get("slug"),
        "lifecycle_stage": lifecycle_stage or opp.get("lifecycle"),
    }
    return FeatureVector(values=values, raw=raw)
