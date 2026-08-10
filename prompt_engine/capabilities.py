from __future__ import annotations

from typing import Any


PROVIDER_CAPABILITIES: dict[str, dict[str, Any]] = {
    "veo": {
        "name": "veo",
        "modalities": ["video"],
        "capabilities": {
            "video": {
                "text_to_video": True,
                "image_to_video": True,
                "reference_images": True,
                "character_reference": True,
                "audio_generation": False,
            },
            "limits": {"max_duration_sec": 8, "max_references": 4},
            "strengths": ["character_consistency", "cinematic_realism"],
            "cost_per_sec": 0.08,
            "latency_base_sec": 28,
            "model": "veo-stub-1",
        },
    },
    "runway": {
        "name": "runway",
        "modalities": ["video"],
        "capabilities": {
            "video": {
                "text_to_video": True,
                "image_to_video": True,
                "reference_images": True,
                "character_reference": True,
                "audio_generation": False,
            },
            "limits": {"max_duration_sec": 10, "max_references": 3},
            "strengths": ["camera_movement", "motion"],
            "cost_per_sec": 0.07,
            "latency_base_sec": 32,
            "model": "runway-stub-1",
        },
    },
    "gpt_image": {
        "name": "gpt_image",
        "modalities": ["image", "thumbnail"],
        "capabilities": {
            "image": {"reference_images": True, "character_reference": True},
            "limits": {"max_references": 4},
            "strengths": ["composition", "style_control"],
            "cost_per_image": 0.04,
            "latency_base_sec": 12,
            "model": "gpt-image-stub-1",
        },
    },
    "elevenlabs": {
        "name": "elevenlabs",
        "modalities": ["voice"],
        "capabilities": {
            "voice": {"emotion_control": True, "ssml": False},
            "limits": {},
            "strengths": ["natural_speech"],
            "cost_per_1k_chars": 0.03,
            "latency_base_sec": 4,
            "model": "elevenlabs-stub-1",
        },
    },
    "suno": {
        "name": "suno",
        "modalities": ["music"],
        "capabilities": {
            "music": {"instrumental": True, "vocals": True},
            "limits": {"max_duration_sec": 120},
            "strengths": ["cinematic_score"],
            "cost_per_track": 0.12,
            "latency_base_sec": 40,
            "model": "suno-stub-1",
        },
    },
}
