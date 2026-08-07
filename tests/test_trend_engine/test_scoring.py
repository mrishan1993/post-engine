from __future__ import annotations

from trend_engine.processing.scoring_agent import compute_trend_score


def test_velocity_beats_stale_popularity() -> None:
    hot = compute_trend_score(
        [
            {
                "source": "youtube",
                "raw_metrics": {
                    "velocity_views_per_hour": 80_000,
                    "age_hours": 4,
                    "views": 320_000,
                },
            }
        ]
    )
    stale = compute_trend_score(
        [
            {
                "source": "youtube",
                "raw_metrics": {
                    "velocity_views_per_hour": 2_000,
                    "age_hours": 90,
                    "views": 5_000_000,
                },
            }
        ]
    )
    assert hot["score"] > stale["score"]


def test_cross_source_bonus() -> None:
    single = compute_trend_score(
        [
            {
                "source": "youtube",
                "raw_metrics": {"velocity_views_per_hour": 40_000, "age_hours": 5},
            }
        ]
    )
    multi = compute_trend_score(
        [
            {
                "source": "youtube",
                "raw_metrics": {"velocity_views_per_hour": 40_000, "age_hours": 5},
            },
            {
                "source": "google_trends",
                "raw_metrics": {"interest_latest": 70, "rising_ratio": 1.3},
            },
        ]
    )
    assert multi["score"] > single["score"]
    assert multi["breakdown"]["cross_source_confirmation"] == 1.0
