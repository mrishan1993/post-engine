from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


DurationStrategy = Literal["truncate", "extend", "nearest"]
CharacterRefMode = Literal[
    "character_reference_required",
    "character_reference_optional",
    "character_reference_disabled",
]


class VideoPromptBlock(BaseModel):
    positive: str = ""
    negative: str = ""


class VideoReference(BaseModel):
    asset_id: str
    role: str = "character"  # character | environment | prop | first_frame | last_frame
    uri: str | None = None


class VideoGenerationParams(BaseModel):
    duration_sec: float = 6.0
    aspect_ratio: str = "9:16"
    resolution: str = "1080x1920"
    fps: float = 24.0
    mode: Literal["text_to_video", "image_to_video", "reference_to_video"] = "text_to_video"


class VideoCamera(BaseModel):
    shot_type: str = "medium"
    movement: str = "static"
    angle: str | None = None


class VideoPromptPackage(BaseModel):
    """Immutable video generation input (from Prompt Engine)."""

    prompt_package_id: str | None = None
    modality: Literal["video"] = "video"
    prompt: VideoPromptBlock = Field(default_factory=VideoPromptBlock)
    references: list[VideoReference] = Field(default_factory=list)
    generation: VideoGenerationParams = Field(default_factory=VideoGenerationParams)
    camera: VideoCamera = Field(default_factory=VideoCamera)
    continuity: dict[str, Any] = Field(default_factory=dict)
    character_constraints: dict[str, Any] = Field(default_factory=dict)
    frames: dict[str, Any] = Field(default_factory=dict)
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


class VideoGenerationRequestIn(BaseModel):
    prompt_package_id: str | None = None
    video_prompt_package: VideoPromptPackage | dict[str, Any] | None = None
    storyboard_id: str | None = None
    storyboard_shot_id: str | None = None
    provider_strategy: ProviderStrategy = Field(default_factory=ProviderStrategy)
    variants: dict[str, Any] = Field(default_factory=lambda: {"count": 1, "strategy": "mixed"})
    quality: dict[str, Any] = Field(default_factory=lambda: {"minimum_score": 0.85})
    budget: dict[str, Any] = Field(default_factory=lambda: {"max_cost_usd": 3.0})
    priority: Literal["critical", "high", "normal", "low"] = "normal"
    idempotency_key: str | None = None
    duration_strategy: DurationStrategy = "nearest"
    character_reference: CharacterRefMode = "character_reference_optional"
    process: bool = True
    depends_on_job_ids: list[str] = Field(default_factory=list)


class TechnicalVideoQA(BaseModel):
    ok: bool
    file_exists: bool = False
    readable: bool = False
    codec_ok: bool = True
    duration_ok: bool = True
    dimensions_ok: bool = True
    aspect_ratio_ok: bool = True
    fps_ok: bool = True
    black_frame_risk: bool = False
    frozen_frame_risk: bool = False
    probe_source: str = "stub"  # stub | ffprobe
    notes: list[str] = Field(default_factory=list)
    probed: dict[str, Any] = Field(default_factory=dict)


# Configurable scoring weights (PRP §11)
ROUTING_WEIGHTS: dict[str, float] = {
    "capability": 0.30,
    "historical_quality": 0.25,
    "character_consistency": 0.15,
    "storyboard_adherence": 0.10,
    "reliability": 0.10,
    "latency": 0.05,
    "cost": 0.05,
}
