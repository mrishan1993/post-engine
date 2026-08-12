from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ImagePurpose = Literal[
    "storyboard_keyframe",
    "video_reference",
    "thumbnail",
    "social_cover",
    "character_reference",
    "environment",
    "prop",
    "concept",
    "edit",
]

ImageMode = Literal[
    "text_to_image",
    "image_to_image",
    "reference_to_image",
    "image_editing",
]

VariantStrategy = Literal[
    "same_seed_variation",
    "different_seed",
    "different_provider",
    "different_composition",
    "different_prompt_variant",
    "mixed",
]


class ImagePromptBlock(BaseModel):
    positive: str = ""
    negative: str = ""


class ImageReference(BaseModel):
    asset_id: str
    role: str = "character"  # character | environment | style | pose | prop | source
    uri: str | None = None
    score: float = 0.5  # ranking weight for provider ref limits


class ImageGenerationParams(BaseModel):
    aspect_ratio: str = "9:16"
    resolution: str = "1024x1536"
    mode: ImageMode = "text_to_image"
    steps: int | None = None
    guidance: float | None = None
    style_strength: float | None = None
    reference_strength: float | None = None


class ImagePromptPackage(BaseModel):
    prompt_package_id: str | None = None
    modality: Literal["image"] = "image"
    purpose: ImagePurpose = "storyboard_keyframe"
    prompt: ImagePromptBlock = Field(default_factory=ImagePromptBlock)
    references: list[ImageReference] = Field(default_factory=list)
    generation: ImageGenerationParams = Field(default_factory=ImageGenerationParams)
    character_constraints: dict[str, Any] = Field(default_factory=dict)
    style: dict[str, Any] = Field(default_factory=dict)
    environment: dict[str, Any] = Field(default_factory=dict)
    shot: dict[str, Any] = Field(default_factory=dict)
    edit: dict[str, Any] | None = None  # instruction, mask_asset_id, source_artifact_id
    canonical_spec_id: str | None = None
    storyboard_shot_id: str | None = None
    provider_prompt: dict[str, Any] = Field(default_factory=dict)
    lineage: dict[str, Any] = Field(default_factory=dict)


class ProviderStrategy(BaseModel):
    mode: Literal["automatic", "preferred", "locked"] = "automatic"
    preferred: str | None = None
    locked: str | None = None
    fallback: list[str] = Field(default_factory=lambda: ["provider_b"])
    max_provider_switches: int = 2


class ImageGenerationRequestIn(BaseModel):
    prompt_package_id: str | None = None
    image_prompt_package: ImagePromptPackage | dict[str, Any] | None = None
    storyboard_id: str | None = None
    storyboard_shot_id: str | None = None
    purpose: ImagePurpose | None = None
    provider_strategy: ProviderStrategy = Field(default_factory=ProviderStrategy)
    variants: dict[str, Any] = Field(
        default_factory=lambda: {"count": 1, "strategy": "different_seed"}
    )
    quality: dict[str, Any] = Field(default_factory=lambda: {"minimum_score": 0.85})
    budget: dict[str, Any] = Field(default_factory=lambda: {"max_cost_usd": 2.0})
    priority: Literal["critical", "high", "normal", "low"] = "normal"
    idempotency_key: str | None = None
    process: bool = True
    depends_on_job_ids: list[str] = Field(default_factory=list)


class ImageEditRequestIn(BaseModel):
    artifact_id: str
    instruction: str
    mask_asset_id: str | None = None
    provider_strategy: ProviderStrategy = Field(default_factory=ProviderStrategy)
    budget: dict[str, Any] = Field(default_factory=lambda: {"max_cost_usd": 1.0})
    process: bool = True


class TechnicalImageQA(BaseModel):
    ok: bool
    file_exists: bool = False
    readable: bool = False
    mime_ok: bool = True
    dimensions_ok: bool = True
    aspect_ratio_ok: bool = True
    blank_risk: bool = False
    dark_risk: bool = False
    bright_risk: bool = False
    duplicate_risk: bool = False
    probe_source: str = "stub"
    technical_score: float = 0.0
    notes: list[str] = Field(default_factory=list)
    probed: dict[str, Any] = Field(default_factory=dict)


ROUTING_WEIGHTS: dict[str, float] = {
    "capability": 0.30,
    "visual_quality": 0.25,
    "character_consistency": 0.20,
    "historical_qa": 0.10,
    "cost": 0.05,
    "latency": 0.05,
    "reliability": 0.05,
}

# Reference role priority for provider limit ranking
REF_ROLE_SCORES: dict[str, float] = {
    "character": 0.98,
    "face": 0.98,
    "full_body": 0.94,
    "pose": 0.77,
    "style": 0.71,
    "environment": 0.64,
    "prop": 0.55,
    "source": 0.90,
    "mask": 0.85,
}
