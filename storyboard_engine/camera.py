from __future__ import annotations

SHOT_TYPES = [
    "extreme_close_up",
    "close_up",
    "medium_close_up",
    "medium",
    "medium_wide",
    "wide",
    "extreme_wide",
    "pov",
    "over_the_shoulder",
    "two_shot",
    "insert",
    "cutaway",
    "tracking_shot",
]

CAMERA_ANGLES = [
    "eye_level",
    "low_angle",
    "high_angle",
    "dutch_angle",
    "overhead",
    "ground_level",
]

CAMERA_MOVEMENTS = [
    "static",
    "pan",
    "tilt",
    "dolly_in",
    "dolly_out",
    "tracking",
    "orbit",
    "handheld",
    "zoom",
    "rack_focus",
    "whip_pan",
    "slow_push",
]


# Narrative function → preferred shot progression (semantic, not provider-specific)
BEAT_SHOT_RECIPES: dict[str, list[dict[str, str]]] = {
    "hook": [
        {"shot_type": "pov", "movement": "slow_push", "angle": "eye_level", "pattern": "pov_entry"},
        {
            "shot_type": "medium",
            "movement": "handheld",
            "angle": "eye_level",
            "pattern": "character_enters",
        },
    ],
    "setup": [
        {
            "shot_type": "wide",
            "movement": "static",
            "angle": "eye_level",
            "pattern": "establishing",
        },
        {
            "shot_type": "medium",
            "movement": "dolly_in",
            "angle": "eye_level",
            "pattern": "discovery",
        },
    ],
    "conflict": [
        {
            "shot_type": "over_the_shoulder",
            "movement": "static",
            "angle": "eye_level",
            "pattern": "approach",
        },
        {
            "shot_type": "close_up",
            "movement": "static",
            "angle": "eye_level",
            "pattern": "reaction",
        },
    ],
    "escalation": [
        {
            "shot_type": "medium_close_up",
            "movement": "handheld",
            "angle": "low_angle",
            "pattern": "threat_visible",
        },
        {
            "shot_type": "extreme_close_up",
            "movement": "static",
            "angle": "eye_level",
            "pattern": "object_focus",
        },
        {
            "shot_type": "tracking_shot",
            "movement": "tracking",
            "angle": "eye_level",
            "pattern": "escape_attempt",
        },
    ],
    "twist": [
        {
            "shot_type": "insert",
            "movement": "static",
            "angle": "high_angle",
            "pattern": "phone_closeup",
        },
        {
            "shot_type": "close_up",
            "movement": "dolly_in",
            "angle": "eye_level",
            "pattern": "reveal",
        },
    ],
    "ending": [
        {
            "shot_type": "close_up",
            "movement": "static",
            "angle": "eye_level",
            "pattern": "aftermath",
        },
    ],
    "cta": [
        {
            "shot_type": "medium",
            "movement": "static",
            "angle": "eye_level",
            "pattern": "cta_hold",
        },
    ],
}


def words_to_seconds(text: str | None, wpm: float = 150.0) -> float:
    if not text:
        return 0.0
    words = len(text.split())
    return round(max(0.4, words / (wpm / 60.0)), 2)
