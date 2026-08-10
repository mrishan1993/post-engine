from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class StoryboardRequest(BaseModel):
    story_id: str | None = None
    blueprint: dict[str, Any] | None = None
    platform: str = "instagram_reels"
    character_ids: list[str] = Field(default_factory=list)
    character_slugs: list[str] = Field(default_factory=list)
    location_query: str | None = None
    style_id: str | None = None
    visual_style: str | None = None
    aspect_ratio: str | None = None
    target_duration_sec: int | None = None
    predicted_retention: float | None = None
    virality_probability: float | None = None
    max_revisions: int = 2
    template: str | None = None


class CameraSpec(BaseModel):
    angle: str = "eye_level"
    movement: str = "static"
    lens: str = "35mm"
    screen_direction: Literal["left", "right", "center", "toward", "away"] = "center"


class CompositionSpec(BaseModel):
    framing: str = "center"
    subject_position: str = "foreground"


class LightingSpec(BaseModel):
    direction: str = "side"
    intensity: str = "low"
    style: str | None = None


class TransitionSpec(BaseModel):
    in_: str = Field(default="cut", alias="in")
    out: str = "cut"

    model_config = {"populate_by_name": True}


class GenerationReq(BaseModel):
    modality: Literal["image", "video", "animation", "existing_asset", "text_overlay", "audio"] = (
        "video"
    )
    generation_type: dict[str, bool] = Field(
        default_factory=lambda: {"text_to_video": False, "image_to_video": True}
    )
    reference_assets: list[str] = Field(default_factory=list)
    duration_sec: float = 0.0


class AudioBlock(BaseModel):
    narration: dict[str, Any] | None = None
    dialogue: dict[str, Any] | None = None
    music: dict[str, Any] = Field(default_factory=dict)
    ambience: dict[str, Any] | None = None
    sfx: list[dict[str, Any]] = Field(default_factory=list)
    silence: dict[str, Any] | None = None


class CaptionPlan(BaseModel):
    text: str
    start_sec: float
    end_sec: float
    emphasis: str = "medium"
    position: str = "lower_center"


class PatternInterrupt(BaseModel):
    time_sec: float
    type: str
    purpose: str


class ShotSpec(BaseModel):
    id: str
    sequence: int
    start_time_sec: float
    end_time_sec: float
    duration_sec: float
    shot_type: str
    camera: CameraSpec = Field(default_factory=CameraSpec)
    subject: dict[str, Any] = Field(default_factory=dict)
    action: str
    expression: dict[str, Any] = Field(default_factory=dict)
    composition: CompositionSpec = Field(default_factory=CompositionSpec)
    environment: dict[str, Any] = Field(default_factory=dict)
    lighting: LightingSpec = Field(default_factory=LightingSpec)
    visual_priority: dict[str, str] = Field(default_factory=dict)
    transition: TransitionSpec = Field(default_factory=TransitionSpec)
    audio: AudioBlock = Field(default_factory=AudioBlock)
    captions: list[CaptionPlan] = Field(default_factory=list)
    text_overlay: dict[str, Any] | None = None
    generation: GenerationReq = Field(default_factory=GenerationReq)
    pattern_name: str | None = None


class SceneSpec(BaseModel):
    id: str
    sequence: int
    start_time_sec: float
    end_time_sec: float
    duration_sec: float
    narrative_function: str
    objective: str | None = None
    emotional_state: dict[str, Any] = Field(default_factory=dict)
    tension: dict[str, float] = Field(default_factory=dict)
    location_id: str | None = None
    location_name: str | None = None
    characters: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    dialogue: str | None = None
    narration: dict[str, Any] | None = None
    text_overlay: dict[str, Any] | None = None
    music: dict[str, Any] = Field(default_factory=dict)
    sound_effects: list[dict[str, Any]] = Field(default_factory=list)
    shots: list[ShotSpec] = Field(default_factory=list)
    character_state: dict[str, Any] = Field(default_factory=dict)
    prop_state: dict[str, Any] = Field(default_factory=dict)


class GlobalDirection(BaseModel):
    visual_style: str = "cinematic_horror"
    visual_reference: dict[str, Any] = Field(default_factory=dict)
    aspect_ratio: str = "9:16"
    resolution: str = "1080x1920"
    frame_rate: int = 30
    pacing: str = "fast"
    color_direction: dict[str, Any] = Field(default_factory=dict)
    lighting: dict[str, Any] = Field(default_factory=lambda: {"style": "low_key"})
    camera_language: dict[str, Any] = Field(
        default_factory=lambda: {"style": "handheld", "movement": "restrained"}
    )
    typography: dict[str, Any] = Field(default_factory=lambda: {"style": "bold_minimal"})
    subtitle_style: dict[str, Any] = Field(default_factory=lambda: {"enabled": True})
    platform: dict[str, Any] = Field(default_factory=dict)
    template: str = "horror"


class PacingMeta(BaseModel):
    average_shot_duration_sec: float
    cuts_per_10_sec: float
    motion_density: float
    visual_novelty: float


class AssetRequirements(BaseModel):
    characters: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    props: list[str] = Field(default_factory=list)
    expressions: list[str] = Field(default_factory=list)
    environment_states: list[str] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list)


class StoryboardQuality(BaseModel):
    narrative_coverage: float
    timing: float
    character_continuity: float
    location_continuity: float
    prop_continuity: float
    camera_continuity: float
    audio_sync: float
    asset_availability: float
    platform_compatibility: float
    visual_pacing: float
    retention_potential: float
    overall: float


class StoryboardCriticResult(BaseModel):
    narrative_covered: bool
    hook_visual_interest: bool
    no_unnecessary_shots: bool
    shot_lengths_ok: bool
    enough_pattern_changes: bool
    camera_consistent: bool
    positions_logical: bool
    audio_reinforces: bool
    twist_emphasized: bool
    ending_lands: bool
    generation_realistic: bool
    notes: list[str] = Field(default_factory=list)
    suggested_fixes: list[str] = Field(default_factory=list)
    critic_score: float = 0.0


class StoryboardDocument(BaseModel):
    title: str
    story_id: str | None = None
    platform: str
    duration_sec: float
    global_direction: GlobalDirection
    scenes: list[SceneSpec]
    pacing: PacingMeta
    pattern_interrupts: list[PatternInterrupt] = Field(default_factory=list)
    asset_requirements: AssetRequirements = Field(default_factory=AssetRequirements)
    resolved_assets: dict[str, Any] = Field(default_factory=dict)
    music_cues: list[dict[str, Any]] = Field(default_factory=list)
    quality: StoryboardQuality | None = None
    critic: StoryboardCriticResult | None = None

    @model_validator(mode="after")
    def sync_duration(self) -> StoryboardDocument:
        if self.scenes:
            self.duration_sec = round(self.scenes[-1].end_time_sec, 3)
        return self
