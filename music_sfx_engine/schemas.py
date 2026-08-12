from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


MusicPurpose = Literal[
    "background_score",
    "theme",
    "hook_music",
    "tension",
    "comedy",
    "emotional",
    "action",
    "ending",
    "cta",
]


class EmotionalPoint(BaseModel):
    time: float
    emotion: str
    intensity: float = 0.5


class EnergyPoint(BaseModel):
    time: float
    intensity: float


class MusicMood(BaseModel):
    primary: str = "ominous"
    secondary: str | None = None


class MusicSpecification(BaseModel):
    purpose: MusicPurpose = "background_score"
    mood: MusicMood = Field(default_factory=MusicMood)
    genre: str = "cinematic_horror"
    tempo_bpm: float = 82.0
    instrumentation: list[str] = Field(
        default_factory=lambda: ["low_strings", "sub_bass", "atmospheric_pad", "percussion"]
    )
    vocals_enabled: bool = False
    energy_curve: list[EnergyPoint] = Field(default_factory=list)
    duration_sec: float = 30.0
    segments: list[dict[str, Any]] = Field(default_factory=list)
    character_theme: dict[str, Any] = Field(default_factory=dict)
    world_theme: dict[str, Any] = Field(default_factory=dict)


class SfxSpec(BaseModel):
    id: str
    type: str
    start_sec: float
    duration_sec: float = 1.0
    intensity: float = 0.7
    spatial_position: dict[str, float] = Field(default_factory=lambda: {"x": 0.5, "y": 0.5})
    source_preference: Literal["library_first", "generate", "library_only"] = "library_first"
    tags: list[str] = Field(default_factory=list)
    visual_event: str | None = None


class SilenceSpec(BaseModel):
    start_sec: float
    end_sec: float
    reason: str = "twist"


class AudioBlueprint(BaseModel):
    total_duration_sec: float = 30.0
    emotional_arc: list[EmotionalPoint] = Field(default_factory=list)
    music: dict[str, Any] = Field(default_factory=lambda: {"required": True})
    ambience: dict[str, Any] = Field(default_factory=lambda: {"required": True})
    sfx: dict[str, Any] = Field(default_factory=lambda: {"required": True, "items": []})
    silences: list[SilenceSpec] = Field(default_factory=list)
    voice_windows: list[dict[str, Any]] = Field(default_factory=list)
    story_beats: list[dict[str, Any]] = Field(default_factory=list)
    music_spec: MusicSpecification | None = None
    lineage: dict[str, Any] = Field(default_factory=dict)


class TimelineTrack(BaseModel):
    type: Literal["music", "ambience", "sfx", "voice", "silence"]
    artifact_id: str | None = None
    start: float
    end: float
    gain_db: float = 0.0
    fade_in_sec: float = 0.0
    fade_out_sec: float = 0.0
    sfx_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AudioTimeline(BaseModel):
    duration_sec: float
    tracks: list[TimelineTrack] = Field(default_factory=list)
    beat_grid: list[float] = Field(default_factory=list)
    voice_windows: list[dict[str, Any]] = Field(default_factory=list)
    ducking: dict[str, Any] = Field(
        default_factory=lambda: {"music_bed_db": -12, "music_duck_db": -20}
    )
    loudness_profile: dict[str, Any] = Field(
        default_factory=lambda: {"target_lufs": -14, "platform": "instagram_reels"}
    )


class ProviderStrategy(BaseModel):
    mode: Literal["automatic", "preferred", "locked"] = "automatic"
    preferred: str | None = None
    locked: str | None = None
    fallback: list[str] = Field(default_factory=lambda: ["provider_b"])
    max_provider_switches: int = 2


class MusicGenerationRequestIn(BaseModel):
    story_id: str | None = None
    storyboard_id: str | None = None
    prompt_package_id: str | None = None
    audio_blueprint: AudioBlueprint | dict[str, Any] | None = None
    content_id: str | None = None
    provider_strategy: ProviderStrategy = Field(default_factory=ProviderStrategy)
    variants: dict[str, Any] = Field(default_factory=lambda: {"count": 1})
    budget: dict[str, Any] = Field(default_factory=lambda: {"max_cost_usd": 1.5})
    quality: dict[str, Any] = Field(default_factory=lambda: {"minimum_score": 0.8})
    priority: Literal["critical", "high", "normal", "low"] = "normal"
    idempotency_key: str | None = None
    build_timeline: bool = True
    resolve_sfx: bool = True
    process: bool = True


class TechnicalAudioQA(BaseModel):
    ok: bool
    file_exists: bool = False
    readable: bool = False
    duration_ok: bool = True
    sample_rate_ok: bool = True
    clipping_risk: bool = False
    silence_risk: bool = False
    corruption_risk: bool = False
    probe_source: str = "stub"
    technical_score: float = 0.0
    notes: list[str] = Field(default_factory=list)
    probed: dict[str, Any] = Field(default_factory=dict)


ROUTING_WEIGHTS: dict[str, float] = {
    "genre": 0.20,
    "mood": 0.20,
    "instrument_control": 0.15,
    "duration": 0.10,
    "stems": 0.05,
    "historical_qa": 0.10,
    "cost": 0.10,
    "latency": 0.05,
    "reliability": 0.05,
}
