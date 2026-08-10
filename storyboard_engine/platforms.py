from __future__ import annotations

from typing import Any


PLATFORM_CONFIGS: dict[str, dict[str, Any]] = {
    "instagram_reels": {
        "name": "instagram_reels",
        "aspect_ratio": "9:16",
        "resolution": "1080x1920",
        "max_duration_sec": 90,
        "safe_zones": {"top": 0.10, "bottom": 0.18},
        "caption_position": {"preferred": "lower_center"},
        "hook_window_sec": 3.0,
    },
    "youtube_shorts": {
        "name": "youtube_shorts",
        "aspect_ratio": "9:16",
        "resolution": "1080x1920",
        "max_duration_sec": 60,
        "safe_zones": {"top": 0.08, "bottom": 0.16},
        "caption_position": {"preferred": "lower_center"},
        "hook_window_sec": 3.0,
    },
    "tiktok": {
        "name": "tiktok",
        "aspect_ratio": "9:16",
        "resolution": "1080x1920",
        "max_duration_sec": 60,
        "safe_zones": {"top": 0.12, "bottom": 0.20},
        "caption_position": {"preferred": "center"},
        "hook_window_sec": 2.5,
    },
}


def get_platform(name: str) -> dict[str, Any]:
    return dict(PLATFORM_CONFIGS.get(name, PLATFORM_CONFIGS["instagram_reels"]))
