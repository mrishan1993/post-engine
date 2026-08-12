from __future__ import annotations

from typing import Any


MUSIC_PROVIDER_REGISTRY: dict[str, dict[str, Any]] = {
    "provider_a": {
        "id": "provider_a",
        "modality": "music",
        "enabled": True,
        "model": "provider-a-music-stub-1",
        "capabilities": {
            "text_to_music": True,
            "music_variation": True,
            "instrumental": True,
            "vocals": True,
            "stems": False,
            "looping": True,
            "genres": ["cinematic_horror", "cinematic", "ambient", "tension", "emotional"],
        },
        "limits": {"min_duration_sec": 5, "max_duration_sec": 180},
        "pricing": {"model": "per_generation", "cost_per_generation": 0.12},
        "strengths": ["cinematic", "mood_control"],
    },
    "provider_b": {
        "id": "provider_b",
        "modality": "music",
        "enabled": True,
        "model": "provider-b-music-stub-1",
        "capabilities": {
            "text_to_music": True,
            "music_variation": True,
            "instrumental": True,
            "vocals": False,
            "stems": False,
            "looping": True,
            "genres": ["cinematic_horror", "ambient", "comedy", "action"],
        },
        "limits": {"min_duration_sec": 5, "max_duration_sec": 120},
        "pricing": {"model": "per_generation", "cost_per_generation": 0.08},
        "strengths": ["cost", "latency"],
    },
}


def list_music_providers(*, enabled_only: bool = True) -> list[dict[str, Any]]:
    out = []
    for p in MUSIC_PROVIDER_REGISTRY.values():
        if enabled_only and not p.get("enabled", True):
            continue
        out.append(dict(p))
    return out


def get_music_provider_meta(provider_id: str) -> dict[str, Any] | None:
    return MUSIC_PROVIDER_REGISTRY.get(provider_id)
