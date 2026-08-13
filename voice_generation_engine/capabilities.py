from __future__ import annotations

from typing import Any


VOICE_PROVIDER_REGISTRY: dict[str, dict[str, Any]] = {
    "provider_a": {
        "id": "provider_a",
        "modality": "voice",
        "enabled": True,
        "model": "provider-a-voice-stub-1",
        "capabilities": {
            "text_to_speech": True,
            "emotion_control": True,
            "multilingual": True,
            "voice_cloning": False,
            "pronunciation_control": True,
            "word_timestamps": True,
            "phoneme_timestamps": False,
            "languages": ["en", "en-IN", "hi", "hinglish"],
        },
        "limits": {"max_characters": 5000, "max_duration_sec": 120},
        "pricing": {"model": "per_char", "cost_per_1k_chars": 0.03},
        "strengths": ["emotion_control", "character_consistency", "word_timestamps"],
    },
    "provider_b": {
        "id": "provider_b",
        "modality": "voice",
        "enabled": True,
        "model": "provider-b-voice-stub-1",
        "capabilities": {
            "text_to_speech": True,
            "emotion_control": True,
            "multilingual": True,
            "voice_cloning": False,
            "pronunciation_control": True,
            "word_timestamps": True,
            "phoneme_timestamps": False,
            "languages": ["en", "en-IN", "hi"],
        },
        "limits": {"max_characters": 4000, "max_duration_sec": 90},
        "pricing": {"model": "per_char", "cost_per_1k_chars": 0.02},
        "strengths": ["cost", "latency", "language_quality"],
    },
}


def list_voice_providers(*, enabled_only: bool = True) -> list[dict[str, Any]]:
    out = []
    for p in VOICE_PROVIDER_REGISTRY.values():
        if enabled_only and not p.get("enabled", True):
            continue
        out.append(dict(p))
    return out


def get_voice_provider_meta(provider_id: str) -> dict[str, Any] | None:
    return VOICE_PROVIDER_REGISTRY.get(provider_id)
