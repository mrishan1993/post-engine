from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Modality = Literal["video", "image", "voice", "music", "sfx", "caption", "thumbnail"]


class CompileRequest(BaseModel):
    storyboard_id: str | None = None
    storyboard_shot_id: str | None = None
    modality: Modality = "video"
    provider: str | None = None  # auto-select if None
    shot: dict[str, Any] | None = None
    scene: dict[str, Any] | None = None
    global_direction: dict[str, Any] | None = None
    story_id: str | None = None
    compile_all_shots: bool = False
    experiment: bool = False
    fallback_providers: list[str] = Field(default_factory=list)


class CanonicalSubject(BaseModel):
    character_id: str | None = None
    character_version: int | None = None
    character_slug: str | None = None
    name: str | None = None
    action: str | None = None
    emotion: str | None = None
    immutable: dict[str, Any] = Field(default_factory=dict)
    behavior: list[str] = Field(default_factory=list)
    visual_references: list[str] = Field(default_factory=list)


class CanonicalEnvironment(BaseModel):
    location_id: str | None = None
    location_name: str | None = None
    state: dict[str, Any] = Field(default_factory=dict)
    references: list[str] = Field(default_factory=list)


class CanonicalCamera(BaseModel):
    shot_type: str = "medium"
    angle: str = "eye_level"
    movement: str = "static"
    lens: str | None = None
    screen_direction: str | None = None


class CanonicalGenerationSpec(BaseModel):
    """Provider-agnostic source of truth for a single generation unit."""

    modality: Modality
    objective: str
    duration_sec: float = 4.0
    aspect_ratio: str = "9:16"
    resolution: str | None = None
    subject: CanonicalSubject = Field(default_factory=CanonicalSubject)
    environment: CanonicalEnvironment = Field(default_factory=CanonicalEnvironment)
    camera: CanonicalCamera = Field(default_factory=CanonicalCamera)
    composition: dict[str, Any] = Field(default_factory=dict)
    visual_style: dict[str, Any] = Field(default_factory=dict)
    lighting: dict[str, Any] = Field(default_factory=dict)
    motion: dict[str, Any] = Field(default_factory=dict)
    audio: dict[str, Any] = Field(default_factory=dict)
    continuity: dict[str, Any] = Field(default_factory=dict)
    references: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(
        default_factory=lambda: {
            "preserve_character_identity": True,
            "preserve_environment": True,
            "no_new_objects": True,
        }
    )
    narration: dict[str, Any] | None = None
    text_overlay: dict[str, Any] | None = None
    music: dict[str, Any] | None = None
    sfx: list[dict[str, Any]] = Field(default_factory=list)
    image_purpose: str | None = None  # character_ref | frame | thumbnail | ...
    lineage: dict[str, Any] = Field(default_factory=dict)


class PromptConflict(BaseModel):
    type: str
    severity: Literal["low", "medium", "high"] = "medium"
    sources: list[str] = Field(default_factory=list)
    detail: str = ""


class PromptQuality(BaseModel):
    completeness: float
    consistency: float
    provider_compatibility: float
    asset_coverage: float
    ambiguity: float  # lower is better
    overall: float


class PromptValidationResult(BaseModel):
    ok: bool
    structural: list[str] = Field(default_factory=list)
    creative: list[str] = Field(default_factory=list)
    safety: list[str] = Field(default_factory=list)
    continuity: list[str] = Field(default_factory=list)
    conflicts: list[PromptConflict] = Field(default_factory=list)


class PromptCriticResult(BaseModel):
    faithful_to_storyboard: bool
    preserves_character: bool
    no_contradictions: bool
    visual_priorities_clear: bool
    camera_unambiguous: bool
    environment_specified: bool
    references_used: bool
    not_verbose: bool
    provider_compatible: bool
    notes: list[str] = Field(default_factory=list)
    suggested_fixes: list[str] = Field(default_factory=list)
    critic_score: float = 0.0


class PromptPackageDoc(BaseModel):
    provider: str
    model: str
    modality: Modality
    positive_prompt: str
    negative_prompt: str = ""
    reference_assets: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    seed: dict[str, Any] = Field(default_factory=lambda: {"value": None})
    provider_options: dict[str, Any] = Field(default_factory=dict)
    canonical_spec_id: str | None = None
    prompt_version: int = 1
    quality: PromptQuality | None = None
    validation: PromptValidationResult | None = None
    critic: PromptCriticResult | None = None
    estimate: dict[str, Any] = Field(default_factory=dict)
    components_used: list[str] = Field(default_factory=list)
