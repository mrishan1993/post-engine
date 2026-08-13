from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


TrackType = Literal[
    "video", "image", "voice", "music", "sfx", "caption", "text", "overlay", "effect", "ambience"
]
TransitionType = Literal["cut", "fade", "crossfade", "dip_to_black"]
CropStrategy = Literal["crop", "fit", "stretch", "blur_background", "smart_crop"]
RenderQuality = Literal["draft", "preview", "final"]


class CanvasSpec(BaseModel):
    width: int = 1080
    height: int = 1920
    fps: float = 30.0
    aspect_ratio: str = "9:16"


class TransformSpec(BaseModel):
    scale: float = 1.0
    scale_start: float | None = None
    scale_end: float | None = None
    x: float = 0.5
    y: float = 0.5
    position_start: dict[str, float] | None = None
    position_end: dict[str, float] | None = None
    rotation: float = 0.0
    opacity: float = 1.0
    mirror: bool = False


class TransitionSpec(BaseModel):
    type: TransitionType = "cut"
    duration_ms: int = 0


class ClipSpec(BaseModel):
    artifact_id: str
    storage_uri: str | None = None
    start: float
    end: float
    source_start: float = 0.0
    source_end: float | None = None
    speed: float = 1.0
    transition: TransitionSpec = Field(default_factory=TransitionSpec)
    transform: TransformSpec = Field(default_factory=TransformSpec)
    crop_strategy: CropStrategy = "smart_crop"
    focal_point: dict[str, Any] | None = None
    volume_db: float = 0.0
    z_index: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class AudioClipSpec(BaseModel):
    artifact_id: str
    storage_uri: str | None = None
    start: float
    end: float
    source_start: float = 0.0
    volume_db: float = 0.0
    fade_in_ms: int = 0
    fade_out_ms: int = 0
    loop: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaptionClipSpec(BaseModel):
    text: str
    start: float
    end: float
    style: str = "bold"
    position: str = "bottom_safe"
    words: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OverlaySpec(BaseModel):
    text: str
    start: float
    end: float
    position: dict[str, float] = Field(default_factory=lambda: {"x": 0.5, "y": 0.15})
    animation: Literal["fade", "slide", "scale", "pop"] = "fade"
    role: str = "hook"  # hook|cta|chapter|location|disclaimer
    metadata: dict[str, Any] = Field(default_factory=dict)


class EffectSpec(BaseModel):
    type: str
    start: float
    end: float
    intensity: float = 0.5
    metadata: dict[str, Any] = Field(default_factory=dict)


class SilenceSpec(BaseModel):
    start: float
    end: float
    tracks: list[str] = Field(default_factory=lambda: ["music"])
    reason: str = "dramatic"


class DuckingSpec(BaseModel):
    target_db: float = -20.0
    bed_db: float = -12.0
    attack_ms: int = 80
    release_ms: int = 300


class SceneBlock(BaseModel):
    scene_id: str
    start: float
    end: float
    transition: TransitionSpec = Field(default_factory=TransitionSpec)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExportSpec(BaseModel):
    format: str = "mp4"
    video_codec: str = "h264"
    audio_codec: str = "aac"
    resolution: str = "1080x1920"
    fps: float = 30.0
    audio_sample_rate: int = 48000


class AssemblySpecification(BaseModel):
    """Immutable creative assembly contract — executed, not invented."""

    id: str | None = None
    content_id: str
    storyboard_id: str | None = None
    canvas: CanvasSpec = Field(default_factory=CanvasSpec)
    duration_sec: float = 30.0
    scenes: list[SceneBlock] = Field(default_factory=list)
    video_clips: list[ClipSpec] = Field(default_factory=list)
    image_clips: list[ClipSpec] = Field(default_factory=list)
    voice_clips: list[AudioClipSpec] = Field(default_factory=list)
    music_clips: list[AudioClipSpec] = Field(default_factory=list)
    sfx_clips: list[AudioClipSpec] = Field(default_factory=list)
    ambience_clips: list[AudioClipSpec] = Field(default_factory=list)
    captions: list[CaptionClipSpec] = Field(default_factory=list)
    overlays: list[OverlaySpec] = Field(default_factory=list)
    effects: list[EffectSpec] = Field(default_factory=list)
    silences: list[SilenceSpec] = Field(default_factory=list)
    ducking: DuckingSpec = Field(default_factory=DuckingSpec)
    beat_grid: list[float] = Field(default_factory=list)
    cut_on_beat: bool = False
    captions_enabled: bool = True
    effects_enabled: bool = True
    export: ExportSpec = Field(default_factory=ExportSpec)
    platform_profile: str = "instagram_reels_v1"
    lineage: dict[str, Any] = Field(default_factory=dict)


class TimelineTrack(BaseModel):
    type: TrackType
    id: str
    clips: list[dict[str, Any]] = Field(default_factory=list)


class BuiltTimeline(BaseModel):
    duration_sec: float
    canvas: CanvasSpec
    tracks: list[TimelineTrack]
    ducking: DuckingSpec
    silences: list[SilenceSpec] = Field(default_factory=list)
    source_hashes: dict[str, str] = Field(default_factory=dict)


class TechnicalAssemblyQA(BaseModel):
    ok: bool
    file_exists: bool = False
    readable: bool = False
    duration_ok: bool = True
    resolution_ok: bool = True
    fps_ok: bool = True
    codec_ok: bool = True
    av_sync_ok: bool = True
    black_frame_risk: bool = False
    missing_audio: bool = False
    probe_source: str = "stub"
    technical_score: float = 0.0
    notes: list[str] = Field(default_factory=list)
    probed: dict[str, Any] = Field(default_factory=dict)


class CreateAssemblyRequest(BaseModel):
    content_id: str | None = None
    storyboard_id: str | None = None
    specification: AssemblySpecification | dict[str, Any] | None = None
    # Convenience refs when building from generated artifacts
    video_artifact_ids: list[str] = Field(default_factory=list)
    image_artifact_ids: list[str] = Field(default_factory=list)
    voice_timeline_id: str | None = None
    music_artifact_id: str | None = None
    audio_timeline_id: str | None = None
    platform_profile: str = "instagram_reels_v1"
    captions_enabled: bool = True
    process_render: bool = False
    render_quality: RenderQuality = "final"


class RenderRequestIn(BaseModel):
    assembly_id: str
    quality: RenderQuality = "final"
    render_profile: str | None = None
    priority: Literal["critical", "high", "normal", "low"] = "normal"
    process: bool = True
