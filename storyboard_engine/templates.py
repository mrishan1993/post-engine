from __future__ import annotations

from typing import Any


STORYBOARD_TEMPLATES: dict[str, dict[str, Any]] = {
    "horror": {
        "pacing": "fast",
        "avg_shot_sec": 2.4,
        "lighting": "low_key",
        "camera_style": "handheld",
        "music_mood": "ominous",
        "color_palette": ["dark_blue", "muted_gray", "red_accent"],
        "early_motion_boost": True,
    },
    "mystery": {
        "pacing": "medium",
        "avg_shot_sec": 2.8,
        "lighting": "low_key",
        "camera_style": "restrained",
        "music_mood": "tense",
        "color_palette": ["desaturated", "cool_teal"],
        "early_motion_boost": True,
    },
    "pov": {
        "pacing": "fast",
        "avg_shot_sec": 2.2,
        "lighting": "naturalistic",
        "camera_style": "pov_handheld",
        "music_mood": "immersive",
        "color_palette": ["muted", "warm_edge"],
        "early_motion_boost": True,
    },
    "comedy": {
        "pacing": "very_fast",
        "avg_shot_sec": 1.8,
        "lighting": "bright",
        "camera_style": "static_punchy",
        "music_mood": "playful",
        "color_palette": ["saturated", "warm"],
        "early_motion_boost": True,
    },
    "educational": {
        "pacing": "medium",
        "avg_shot_sec": 3.5,
        "lighting": "clean",
        "camera_style": "static",
        "music_mood": "neutral",
        "color_palette": ["clear", "high_contrast_text"],
        "early_motion_boost": False,
    },
    "narrative": {
        "pacing": "medium",
        "avg_shot_sec": 3.0,
        "lighting": "cinematic",
        "camera_style": "motivated",
        "music_mood": "emotional",
        "color_palette": ["cinematic"],
        "early_motion_boost": False,
    },
}


def choose_template(blueprint: dict[str, Any], override: str | None = None) -> str:
    if override and override in STORYBOARD_TEMPLATES:
        return override
    fmt = str((blueprint.get("format") or {}).get("type") or "").lower()
    template = str(blueprint.get("template") or "").lower()
    emotion = str((blueprint.get("hook") or {}).get("emotion") or "").lower()
    if "pov" in fmt or template == "pov":
        return "pov"
    if emotion == "fear" or "horror" in template or "mystery" in template:
        return "horror" if emotion == "fear" else "mystery"
    if emotion == "joy":
        return "comedy"
    return "narrative"
