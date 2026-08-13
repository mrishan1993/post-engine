from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


EmotionType = Literal[
    "neutral",
    "happy",
    "sad",
    "angry",
    "fear",
    "fearful",
    "excited",
    "surprised",
    "confused",
    "sarcastic",
    "calm",
    "whisper",
    "urgent",
    "serious",
    "playful",
    "panic",
]

VoiceType = Literal["character", "narrator", "dialogue", "voiceover", "cta"]


class PauseSpec(BaseModel):
    after_word: str | None = None
    after: str | None = None  # alias
    duration_ms: int = 200
    type: Literal["dramatic", "natural", "breath", "sentence", "word", "reaction"] = "natural"


class EmotionPoint(BaseModel):
    time: float
    emotion: str
    intensity: float = 0.5


class DeliverySpec(BaseModel):
    emotion: str = "neutral"
    intensity: float = 0.5
    energy: float = 0.5
    speaking_rate: float = 1.0
    pitch: float = 0.0
    volume: float = 0.8


class TimingSpec(BaseModel):
    target_duration_sec: float | None = None
    start_sec: float | None = None


class VoiceSpecification(BaseModel):
    """Canonical voice performance spec — words come from Story/Storyboard."""

    character_id: str | None = None
    character_slug: str | None = None
    voice_profile_id: str | None = None
    language: str = "en-IN"
    voice_type: VoiceType = "dialogue"
    script: dict[str, Any] = Field(default_factory=dict)  # {text: ...}
    delivery: DeliverySpec = Field(default_factory=DeliverySpec)
    timing: TimingSpec = Field(default_factory=TimingSpec)
    pauses: list[PauseSpec] = Field(default_factory=list)
    emotion_curve: list[EmotionPoint] = Field(default_factory=list)
    pronunciation: dict[str, Any] = Field(default_factory=dict)
    speech_profile: dict[str, Any] = Field(default_factory=dict)
    dialogue_id: str | None = None
    storyboard_shot_id: str | None = None
    lineage: dict[str, Any] = Field(default_factory=dict)

    @property
    def text(self) -> str:
        return str((self.script or {}).get("text") or "")


class DialogueLine(BaseModel):
    speaker: str
    line: str
    character_id: str | None = None
    voice_profile_id: str | None = None
    emotion: str | None = None
    intensity: float | None = None
    start_sec: float | None = None
    dialogue_id: str | None = None
    storyboard_shot_id: str | None = None


class DialogueScript(BaseModel):
    lines: list[DialogueLine] = Field(default_factory=list)
    language: str = "en-IN"


class VoiceTimelineSegment(BaseModel):
    speaker: str
    artifact_id: str | None = None
    start: float
    end: float
    character_id: str | None = None
    voice_profile_id: str | None = None
    dialogue_id: str | None = None
    request_id: str | None = None


class VoiceTimeline(BaseModel):
    duration_sec: float
    segments: list[VoiceTimelineSegment] = Field(default_factory=list)


class ProviderStrategy(BaseModel):
    mode: Literal["automatic", "preferred", "locked"] = "automatic"
    preferred: str | None = None
    locked: str | None = None
    fallback: list[str] = Field(default_factory=lambda: ["provider_b"])
    max_provider_switches: int = 2


class VoiceGenerationRequestIn(BaseModel):
    story_id: str | None = None
    storyboard_id: str | None = None
    character_id: str | None = None
    character_slug: str | None = None
    voice_profile_id: str | None = None
    prompt_package_id: str | None = None
    voice_spec: VoiceSpecification | dict[str, Any] | None = None
    dialogue: DialogueScript | dict[str, Any] | list[dict[str, Any]] | None = None
    content_id: str | None = None
    provider_strategy: ProviderStrategy = Field(default_factory=ProviderStrategy)
    variants: dict[str, Any] = Field(default_factory=lambda: {"count": 1, "strategy": "different_emotion"})
    budget: dict[str, Any] = Field(default_factory=lambda: {"max_cost_usd": 1.0})
    quality: dict[str, Any] = Field(default_factory=lambda: {"minimum_score": 0.8})
    priority: Literal["critical", "high", "normal", "low"] = "normal"
    idempotency_key: str | None = None
    build_timeline: bool = True
    process: bool = True


class TechnicalVoiceQA(BaseModel):
    ok: bool
    file_exists: bool = False
    readable: bool = False
    duration_ok: bool = True
    sample_rate_ok: bool = True
    clipping_risk: bool = False
    silence_risk: bool = False
    corruption_risk: bool = False
    timestamps_available: bool = False
    probe_source: str = "stub"
    technical_score: float = 0.0
    notes: list[str] = Field(default_factory=list)
    probed: dict[str, Any] = Field(default_factory=dict)


ROUTING_WEIGHTS: dict[str, float] = {
    "voice_quality": 0.20,
    "character_consistency": 0.20,
    "emotion_control": 0.15,
    "language_quality": 0.10,
    "pronunciation": 0.10,
    "historical_qa": 0.10,
    "latency": 0.05,
    "cost": 0.05,
    "reliability": 0.05,
}

VARIANT_EMOTION_DELTAS = [-0.1, 0.0, 0.1]
VARIANT_RATE_DELTAS = [0.0, -0.05, 0.05]
