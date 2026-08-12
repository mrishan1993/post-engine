from __future__ import annotations

from typing import Any


# First production provider + fallback stub (PRP: implement Provider A end-to-end)
VIDEO_PROVIDER_REGISTRY: dict[str, dict[str, Any]] = {
    "provider_a": {
        "id": "provider_a",
        "modality": "video",
        "enabled": True,
        "model": "provider-a-stub-1",
        "capabilities": {
            "text_to_video": True,
            "image_to_video": True,
            "reference_video": False,
            "reference_image": True,
            "character_reference": True,
            "audio_generation": False,
            "first_last_frame": True,
        },
        "limits": {
            "min_duration_sec": 2,
            "max_duration_sec": 8,
            "supported_durations": [2, 4, 5, 6, 8],
            "max_references": 4,
            "supported_ratios": ["9:16", "16:9", "1:1"],
            "supported_resolutions": ["720x1280", "1080x1920", "1920x1080", "1080x1080"],
            "supported_fps": [24, 25, 30],
        },
        "pricing": {"model": "per_second", "cost_per_sec": 0.08},
        "max_concurrent": 10,
        "strengths": ["character_consistency", "cinematic"],
    },
    "provider_b": {
        "id": "provider_b",
        "modality": "video",
        "enabled": True,
        "model": "provider-b-stub-1",
        "capabilities": {
            "text_to_video": True,
            "image_to_video": True,
            "reference_video": False,
            "reference_image": True,
            "character_reference": True,
            "audio_generation": False,
            "first_last_frame": False,
        },
        "limits": {
            "min_duration_sec": 2,
            "max_duration_sec": 10,
            "supported_durations": [2, 5, 10],
            "max_references": 3,
            "supported_ratios": ["9:16", "16:9"],
            "supported_resolutions": ["1080x1920", "1920x1080"],
            "supported_fps": [24, 30],
        },
        "pricing": {"model": "per_second", "cost_per_sec": 0.07},
        "max_concurrent": 15,
        "strengths": ["motion", "camera_movement"],
    },
}


def list_video_providers(*, enabled_only: bool = True) -> list[dict[str, Any]]:
    out = []
    for p in VIDEO_PROVIDER_REGISTRY.values():
        if enabled_only and not p.get("enabled", True):
            continue
        out.append(dict(p))
    return out


def get_video_provider_meta(provider_id: str) -> dict[str, Any] | None:
    return VIDEO_PROVIDER_REGISTRY.get(provider_id)
