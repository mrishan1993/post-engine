from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ContentOpportunityIn(BaseModel):
    topic: str
    trend_score: float = 0.0
    trend_stage: str = "growing"
    emotion: str = "curiosity"
    platform: str = "instagram_reels"


class CreativeDirectionIn(BaseModel):
    format: str = "POV"
    visual_style: str = "cinematic_horror"
    pacing: str = "fast"
    target_duration_sec: int = 30
    template: str | None = None


class CharacterRoleIn(BaseModel):
    character_id: str | None = None
    character_slug: str | None = None
    role: str = "protagonist"


class AudienceIn(BaseModel):
    age_range: str = "18-24"
    market: str = "global"


class PredictionIn(BaseModel):
    virality_probability: float = 0.7
    predicted_retention: float = 0.65
    share_rate: float | None = None


class StoryRequest(BaseModel):
    content_opportunity: ContentOpportunityIn
    creative_direction: CreativeDirectionIn = Field(default_factory=CreativeDirectionIn)
    characters: list[CharacterRoleIn] = Field(default_factory=list)
    audience: AudienceIn = Field(default_factory=AudienceIn)
    prediction: PredictionIn = Field(default_factory=PredictionIn)
    opportunity_id: int | None = None
    content_brief_id: int | None = None
    candidate_count: int = 1
    max_revisions: int = 2
    story_type: str | None = None


class HookBlueprint(BaseModel):
    type: str
    duration_sec: float
    objective: str
    event: str
    hook_text: str
    visual: str | None = None
    emotion: str | None = None


class BeatBlueprint(BaseModel):
    duration_sec: float
    objective: str | None = None
    event: str | None = None
    events: list[str] = Field(default_factory=list)
    text: str | None = None


class OpenLoop(BaseModel):
    question: str
    status: Literal["open", "resolved", "escalated", "intentionally_open"] = "open"


class ForeshadowClue(BaseModel):
    scene: int
    clue: str


class TensionPoint(BaseModel):
    time: float
    intensity: float


class DurationMeta(BaseModel):
    target_seconds: int
    estimated_seconds: float
    narration_words: int
    scene_count: int


class QualityScores(BaseModel):
    hook: float
    conflict: float
    curiosity: float
    escalation: float
    payoff: float
    originality: float
    character_fit: float
    platform_fit: float
    clarity: float = 0.8
    emotional_impact: float = 0.8
    overall: float


class StoryBlueprint(BaseModel):
    title: str
    logline: str
    format: dict[str, Any]
    template: str = "three_act_short"
    hook: HookBlueprint
    setup: BeatBlueprint
    conflict: BeatBlueprint
    escalation: BeatBlueprint
    twist: BeatBlueprint | None = None
    ending: BeatBlueprint
    cta: BeatBlueprint
    conflict_meta: dict[str, Any] = Field(default_factory=dict)
    stakes: list[str] = Field(default_factory=list)
    open_loops: list[OpenLoop] = Field(default_factory=list)
    foreshadowing: list[ForeshadowClue] = Field(default_factory=list)
    tension_curve: list[TensionPoint] = Field(default_factory=list)
    loop: dict[str, Any] = Field(default_factory=lambda: {"enabled": False})
    duration: DurationMeta
    density: float = 0.2
    ending_type: str = "twist"
    character_roles: list[dict[str, Any]] = Field(default_factory=list)
    quality: QualityScores | None = None
    critic: dict[str, Any] | None = None

    @model_validator(mode="after")
    def durations_roughly_sum(self) -> StoryBlueprint:
        parts = [
            self.hook.duration_sec,
            self.setup.duration_sec,
            self.conflict.duration_sec,
            self.escalation.duration_sec,
            self.ending.duration_sec,
            self.cta.duration_sec,
        ]
        if self.twist:
            parts.append(self.twist.duration_sec)
        total = sum(parts)
        # Soft check — generator is responsible for fitting target
        self.duration.estimated_seconds = round(total, 2)
        return self


class CriticResult(BaseModel):
    would_keep_watching: bool
    hook_clear: bool
    enough_tension: bool
    conflict_clear: bool
    escalates: bool
    ending_pays_off: bool
    twist_predictable: bool | None = None
    cta_natural: bool
    confusing: bool
    too_long: bool
    notes: list[str] = Field(default_factory=list)
    suggested_fixes: list[str] = Field(default_factory=list)
    critic_score: float = 0.0
