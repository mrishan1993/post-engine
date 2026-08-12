from __future__ import annotations

from typing import Any

from db.models import PromptPackage
from video_generation_engine.references import infer_mode
from video_generation_engine.schemas import (
    VideoCamera,
    VideoGenerationParams,
    VideoPromptBlock,
    VideoPromptPackage,
    VideoReference,
)


def from_prompt_package(pkg: PromptPackage) -> VideoPromptPackage:
    """Adapt Prompt Engine package → immutable VideoPromptPackage (no creative rewrite)."""
    doc = pkg.provider_prompt or {}
    params = doc.get("parameters") or {}
    lineage = pkg.lineage or {}

    positive = doc.get("positive_prompt") or ""
    negative = doc.get("negative_prompt") or ""
    refs = []
    for asset_id in doc.get("reference_assets") or []:
        refs.append(VideoReference(asset_id=str(asset_id), role="character"))

    duration = float(params.get("duration_sec") or 6)
    aspect = str(params.get("aspect_ratio") or "9:16")
    resolution = str(params.get("resolution") or _resolution_for_aspect(aspect))

    package = VideoPromptPackage(
        prompt_package_id=pkg.id,
        prompt=VideoPromptBlock(positive=positive, negative=negative),
        references=refs,
        generation=VideoGenerationParams(
            duration_sec=duration,
            aspect_ratio=aspect,
            resolution=resolution,
            fps=float(params.get("fps") or 24),
            mode="text_to_video",
        ),
        camera=VideoCamera(
            shot_type=str((doc.get("provider_options") or {}).get("shot_type") or "medium"),
            movement=str(params.get("motion_strength") or "static"),
        ),
        continuity={"previous_shot_id": lineage.get("previous_shot_id")},
        character_constraints={"preserve_identity": True},
        canonical_spec_id=pkg.prompt_spec_id or doc.get("canonical_spec_id"),
        storyboard_shot_id=lineage.get("storyboard_shot_id"),
        provider_prompt=doc,
        lineage=dict(lineage),
    )
    package.generation.mode = infer_mode(package)  # type: ignore[assignment]
    return package


def to_provider_request(package: VideoPromptPackage, *, prepared_refs: list[dict[str, Any]]) -> dict[str, Any]:
    """Provider-facing request; preserves original prompt text."""
    return {
        "prompt_package_id": package.prompt_package_id,
        "canonical_spec_id": package.canonical_spec_id,
        "storyboard_shot_id": package.storyboard_shot_id,
        "prompt": package.prompt.model_dump(),
        "generation": package.generation.model_dump(),
        "camera": package.camera.model_dump(),
        "continuity": package.continuity,
        "character_constraints": package.character_constraints,
        "frames": package.frames,
        "references": prepared_refs,
        # Original provider prompt retained for lineage
        "original_provider_prompt": package.provider_prompt,
    }


def _resolution_for_aspect(aspect: str) -> str:
    return {
        "9:16": "1080x1920",
        "16:9": "1920x1080",
        "1:1": "1080x1080",
    }.get(aspect, "1080x1920")
