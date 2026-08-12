from __future__ import annotations

from typing import Any

from db.models import PromptPackage
from image_generation_engine.references import infer_mode
from image_generation_engine.schemas import (
    ImageGenerationParams,
    ImagePromptBlock,
    ImagePromptPackage,
    ImagePurpose,
    ImageReference,
)


def from_prompt_package(pkg: PromptPackage) -> ImagePromptPackage:
    """Adapt Prompt Engine package → immutable ImagePromptPackage (no creative rewrite)."""
    doc = pkg.provider_prompt or {}
    params = doc.get("parameters") or {}
    lineage = pkg.lineage or {}

    positive = doc.get("positive_prompt") or ""
    negative = doc.get("negative_prompt") or ""
    refs = []
    for asset_id in doc.get("reference_assets") or []:
        refs.append(ImageReference(asset_id=str(asset_id), role="character"))

    aspect = str(params.get("aspect_ratio") or "9:16")
    resolution = str(params.get("resolution") or _resolution_for_aspect(aspect))
    purpose_raw = str(params.get("purpose") or lineage.get("image_purpose") or "storyboard_keyframe")
    purpose = _normalize_purpose(purpose_raw)

    package = ImagePromptPackage(
        prompt_package_id=pkg.id,
        purpose=purpose,  # type: ignore[arg-type]
        prompt=ImagePromptBlock(positive=positive, negative=negative),
        references=refs,
        generation=ImageGenerationParams(
            aspect_ratio=aspect,
            resolution=resolution,
            mode="text_to_image",
        ),
        character_constraints={"preserve_identity": True},
        style=dict(lineage.get("style") or {}),
        environment=dict(lineage.get("environment") or {}),
        shot={
            "camera": lineage.get("camera"),
            "angle": lineage.get("angle"),
            "composition": lineage.get("composition"),
            "emotion": lineage.get("emotion"),
        },
        canonical_spec_id=pkg.prompt_spec_id or doc.get("canonical_spec_id"),
        storyboard_shot_id=lineage.get("storyboard_shot_id"),
        provider_prompt=doc,
        lineage=dict(lineage),
    )
    package.generation.mode = infer_mode(package)  # type: ignore[assignment]
    return package


def to_provider_request(
    package: ImagePromptPackage, *, prepared_refs: list[dict[str, Any]]
) -> dict[str, Any]:
    """Provider-facing request; preserves original prompt text."""
    return {
        "prompt_package_id": package.prompt_package_id,
        "canonical_spec_id": package.canonical_spec_id,
        "storyboard_shot_id": package.storyboard_shot_id,
        "purpose": package.purpose,
        "prompt": package.prompt.model_dump(),
        "generation": package.generation.model_dump(),
        "character_constraints": package.character_constraints,
        "style": package.style,
        "environment": package.environment,
        "shot": package.shot,
        "edit": package.edit,
        "references": prepared_refs,
        "original_provider_prompt": package.provider_prompt,
    }


def _resolution_for_aspect(aspect: str) -> str:
    return {
        "9:16": "1024x1536",
        "16:9": "1536x1024",
        "1:1": "1024x1024",
        "4:5": "1024x1280",
        "2:3": "1024x1536",
    }.get(aspect, "1024x1536")


def _normalize_purpose(raw: str) -> ImagePurpose | str:
    mapping = {
        "storyboard_frame": "storyboard_keyframe",
        "keyframe": "storyboard_keyframe",
        "frame": "storyboard_keyframe",
        "cover": "social_cover",
        "character_ref": "character_reference",
        "env": "environment",
    }
    return mapping.get(raw, raw)  # type: ignore[return-value]
