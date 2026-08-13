from __future__ import annotations

from typing import Any


PLATFORM_PROFILES: dict[str, dict[str, Any]] = {
    "instagram_reel_v1": {
        "id": "instagram_reel_v1",
        "platform": "instagram",
        "content_type": "reel",
        "aspect_ratio": "9:16",
        "min_duration_sec": 3.0,
        "max_duration_sec": 90.0,
        "max_file_size_mb": 300,
        "supported_formats": ["mp4", "mov"],
        "required_metadata": ["caption"],
        "custom_thumbnail": True,
        "scheduling": True,
        "analytics": True,
        "delete": True,
        "capabilities": {
            "reels": True,
            "images": True,
            "carousel": True,
            "scheduling": True,
            "custom_thumbnail": True,
            "first_comment": True,
            "analytics": True,
            "delete": True,
        },
        "retry": {"max_attempts": 4, "delays_sec": [0, 30, 120, 600]},
        "rate_limit": {"posts_per_day": 50},
    },
    "youtube_shorts_v1": {
        "id": "youtube_shorts_v1",
        "platform": "youtube",
        "content_type": "short",
        "aspect_ratio": "9:16",
        "min_duration_sec": 1.0,
        "max_duration_sec": 60.0,
        "max_file_size_mb": 256,
        "supported_formats": ["mp4", "mov"],
        "required_metadata": ["title"],
        "custom_thumbnail": True,
        "scheduling": True,
        "analytics": True,
        "delete": True,
        "capabilities": {
            "reels": False,
            "shorts": True,
            "images": False,
            "carousel": False,
            "scheduling": True,
            "custom_thumbnail": True,
            "analytics": True,
            "delete": True,
        },
        "retry": {"max_attempts": 4, "delays_sec": [0, 30, 120, 600]},
        "rate_limit": {"posts_per_day": 100},
    },
    "tiktok_v1": {
        "id": "tiktok_v1",
        "platform": "tiktok",
        "content_type": "video",
        "aspect_ratio": "9:16",
        "min_duration_sec": 3.0,
        "max_duration_sec": 180.0,
        "max_file_size_mb": 287,
        "supported_formats": ["mp4"],
        "required_metadata": ["caption"],
        "custom_thumbnail": False,
        "scheduling": True,
        "analytics": True,
        "delete": True,
        "capabilities": {
            "reels": False,
            "shorts": False,
            "tiktok": True,
            "scheduling": True,
            "custom_thumbnail": False,
            "analytics": True,
            "delete": True,
        },
        "retry": {"max_attempts": 4, "delays_sec": [0, 30, 120, 600]},
        "rate_limit": {"posts_per_day": 30},
    },
}


DEFAULT_PROFILE_BY_PLATFORM = {
    "instagram": "instagram_reel_v1",
    "youtube": "youtube_shorts_v1",
    "tiktok": "tiktok_v1",
}


def get_platform_profile(platform: str) -> dict[str, Any]:
    pid = DEFAULT_PROFILE_BY_PLATFORM.get(platform, platform)
    if pid not in PLATFORM_PROFILES:
        # allow direct profile id
        if platform in PLATFORM_PROFILES:
            return dict(PLATFORM_PROFILES[platform])
        raise ValueError(f"unknown platform profile: {platform}")
    return dict(PLATFORM_PROFILES[pid])
