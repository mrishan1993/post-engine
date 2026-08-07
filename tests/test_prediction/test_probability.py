from __future__ import annotations

from prediction.probability import predict_opportunity, predict_variants


def test_predict_returns_probability_value_and_confidence() -> None:
    result = predict_opportunity(
        opportunity={
            "trend": "POV Horror",
            "emotion": "fear",
            "hook": "I should never have opened that door...",
            "hook_type": "open_loop",
            "story_pattern": "pov",
            "editing_style": "fast",
            "lifecycle": "growing",
            "platforms": ["youtube", "instagram"],
            "confidence": 0.8,
        },
        score_breakdown={
            "virality": 0.9,
            "novelty": 0.8,
            "growth": 0.85,
            "competition": 0.7,
            "character_fit": 0.85,
            "audience_fit": 0.9,
            "brand_fit": 0.9,
        },
        lifecycle_stage="growing",
        vertical_slug="horror_narration",
        character={"slug": "ghost_kid", "name": "Ghost Kid"},
        similar_winners=12,
    )
    assert 0.05 < result.virality_probability < 0.98
    assert 0.2 < result.confidence < 0.97
    assert result.predicted_views_low < result.predicted_views < result.predicted_views_high
    assert result.reasoning_json["top_positive_signals"]
    assert "discovery" in result.metrics_json
    assert result.final_opportunity_score > 0


def test_variant_ranking_picks_best_hook() -> None:
    base = {
        "trend": "POV Horror",
        "emotion": "fear",
        "story_pattern": "pov",
        "lifecycle": "growing",
        "platforms": ["youtube"],
        "confidence": 0.7,
    }
    ranked = predict_variants(
        [
            {"hook": "hi", "hook_type": "unknown", "opportunity_overrides": {}},
            {
                "hook": "I should never have opened that door in the dark...",
                "hook_type": "open_loop",
                "opportunity_overrides": {},
            },
        ],
        base_opportunity=base,
        vertical_slug="horror_narration",
        score_breakdown={"virality": 0.7, "novelty": 0.7, "competition": 0.6, "character_fit": 0.7, "audience_fit": 0.7, "brand_fit": 0.7, "growth": 0.7},
    )
    assert ranked[0][1].final_opportunity_score >= ranked[1][1].final_opportunity_score
