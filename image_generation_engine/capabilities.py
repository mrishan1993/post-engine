from __future__ import annotations

from typing import Any


IMAGE_PROVIDER_REGISTRY: dict[str, dict[str, Any]] = {
    "provider_a": {
        "id": "provider_a",
        "modality": "image",
        "enabled": True,
        "model": "provider-a-image-stub-1",
        "capabilities": {
            "text_to_image": True,
            "image_to_image": True,
            "image_editing": True,
            "reference_images": True,
            "character_reference": True,
            "style_reference": True,
            "mask_editing": True,
            "transparency": True,
        },
        "limits": {
            "max_references": 5,
            "max_resolution": "2048x2048",
            "supported_ratios": ["1:1", "4:5", "9:16", "16:9", "2:3"],
            "supported_resolutions": [
                "1024x1024",
                "1024x1536",
                "1536x1024",
                "1080x1920",
                "1920x1080",
            ],
        },
        "pricing": {"model": "per_image", "cost_per_image": 0.04},
        "max_concurrent": 20,
        "strengths": ["character_consistency", "visual_quality"],
    },
    "provider_b": {
        "id": "provider_b",
        "modality": "image",
        "enabled": True,
        "model": "provider-b-image-stub-1",
        "capabilities": {
            "text_to_image": True,
            "image_to_image": True,
            "image_editing": True,
            "reference_images": True,
            "character_reference": True,
            "style_reference": False,
            "mask_editing": False,
            "transparency": False,
        },
        "limits": {
            "max_references": 2,
            "max_resolution": "1536x1536",
            "supported_ratios": ["1:1", "9:16", "16:9"],
            "supported_resolutions": ["1024x1024", "1024x1536", "1080x1920"],
        },
        "pricing": {"model": "per_image", "cost_per_image": 0.025},
        "max_concurrent": 30,
        "strengths": ["cost", "latency"],
    },
}


def list_image_providers(*, enabled_only: bool = True) -> list[dict[str, Any]]:
    out = []
    for p in IMAGE_PROVIDER_REGISTRY.values():
        if enabled_only and not p.get("enabled", True):
            continue
        out.append(dict(p))
    return out


def get_image_provider_meta(provider_id: str) -> dict[str, Any] | None:
    return IMAGE_PROVIDER_REGISTRY.get(provider_id)
