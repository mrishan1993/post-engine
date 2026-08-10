from __future__ import annotations

from typing import Any

from prompt_engine.schemas import CanonicalGenerationSpec


# Component-level templates (not giant monolithic prompts)
COMPONENT_LIBRARY: dict[str, dict[str, Any]] = {
    "character_identity_v3": {
        "type": "character",
        "text": (
            "Maintain the exact facial identity, hairstyle, clothing silhouette, age, "
            "and proportions defined by the supplied character references."
        ),
    },
    "environment_horror_v2": {
        "type": "environment",
        "text": "Ominous atmosphere, subtle decay, flickering practical lights, deep shadows.",
    },
    "camera_pov_v4": {
        "type": "camera",
        "text": "Immersive POV framing with restrained handheld micro-movement.",
    },
    "camera_push_v1": {
        "type": "camera",
        "text": "Slow push-in toward subject; keep horizon stable.",
    },
    "lighting_low_key_v2": {
        "type": "lighting",
        "text": "Low-key lighting, side key, muted highlights, cinematic contrast.",
    },
    "motion_handheld_v1": {
        "type": "motion",
        "text": "Natural handheld motion, avoid whip-pan unless specified.",
    },
    "continuity_v1": {
        "type": "continuity",
        "text": "Match prior shot wardrobe, prop placement, and screen direction.",
    },
    "constraints_no_invent_v1": {
        "type": "constraints",
        "text": "Do not invent new characters, props, or locations not in the specification.",
    },
}


def select_components(spec: CanonicalGenerationSpec) -> list[str]:
    names = ["constraints_no_invent_v1"]
    if spec.constraints.get("preserve_character_identity"):
        names.append("character_identity_v3")
    style = str((spec.visual_style or {}).get("name") or "").lower()
    lighting = str((spec.lighting or {}).get("style") or (spec.lighting or {}).get("type") or "").lower()
    if "horror" in style or "low" in lighting or "ominous" in str(spec.environment.state).lower():
        names.append("environment_horror_v2")
        names.append("lighting_low_key_v2")
    if spec.camera.shot_type == "pov":
        names.append("camera_pov_v4")
    if spec.camera.movement in {"slow_push", "dolly_in"}:
        names.append("camera_push_v1")
    if spec.camera.movement == "handheld" or "handheld" in str(
        (spec.motion or {}).get("style") or ""
    ):
        names.append("motion_handheld_v1")
    if spec.continuity:
        names.append("continuity_v1")
    # unique preserve order
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n not in seen and n in COMPONENT_LIBRARY:
            seen.add(n)
            out.append(n)
    return out


def render_components(names: list[str]) -> list[str]:
    return [COMPONENT_LIBRARY[n]["text"] for n in names if n in COMPONENT_LIBRARY]
