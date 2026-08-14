from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


OrchestrationMode = Literal["assisted", "semi_autonomous", "autonomous"]
Actionability = Literal["ACT", "WATCH", "REJECT"]
JobStatus = Literal[
    "DISCOVERED",
    "EVALUATING",
    "ACTIONABLE",
    "WATCHING",
    "REJECTED",
    "CONCEPT_GENERATING",
    "CONCEPT_SELECTED",
    "BRIEF_CREATED",
    "STORY_GENERATING",
    "STORYBOARD_GENERATING",
    "ASSET_GENERATING",
    "ASSEMBLING",
    "QA",
    "APPROVED",
    "PUBLISHING",
    "PUBLISHED",
    "MEASURING",
    "LEARNING",
    "AWAITING_APPROVAL",
    "FAILED",
    "CANCELLED",
]


class TrendOpportunityIn(BaseModel):
    """Normalized trend opportunity — maps from OpportunityScore or synthetic input."""

    trend_id: str
    platform: str = "instagram"
    trend_stage: str = "accelerating"
    velocity_score: float = 0.7
    freshness_score: float = 0.7
    saturation_score: float = 0.3
    opportunity_score: float = 0.75
    viral_mechanism: str | None = None
    format: str = "short_form_video"
    title: str | None = None
    audio: dict[str, Any] = Field(default_factory=dict)
    audience: list[str] = Field(default_factory=lambda: ["gen_z"])
    opportunity_id: int | None = None
    vertical_slug: str | None = None
    pattern_key: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class ActionabilityThresholds(BaseModel):
    min_act_score: float = 0.70
    min_act_velocity: float = 0.55
    min_act_freshness: float = 0.50
    max_act_saturation: float = 0.55
    reject_saturation: float = 0.85
    reject_score_below: float = 0.35


class ConceptScoreWeights(BaseModel):
    trend_fit: float = 0.15
    hook_strength: float = 0.15
    audience_fit: float = 0.15
    character_fit: float = 0.10
    novelty: float = 0.10
    retention_potential: float = 0.15
    shareability: float = 0.10
    production_feasibility: float = 0.05
    platform_fit: float = 0.05


class ConceptOut(BaseModel):
    concept_id: str
    title: str
    hook: str
    core_idea: str
    trend_mechanism: str
    character_role: str
    audience_payoff: str
    emotional_arc: str
    visual_direction: str
    audio_direction: str
    estimated_duration: int
    cta: str
    originality_score: float
    angle: str
    score: float | None = None
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    selected: bool = False
    is_backup: bool = False
    rejection_reason: str | None = None


class ReelProductionBrief(BaseModel):
    content_id: str
    trend_id: str | None = None
    concept_id: str
    platform: str
    objective: str = "growth"
    creative: dict[str, Any] = Field(default_factory=dict)
    visual: dict[str, Any] = Field(default_factory=dict)
    audio: dict[str, Any] = Field(default_factory=dict)
    editing: dict[str, Any] = Field(default_factory=dict)
    qa_requirements: dict[str, Any] = Field(default_factory=dict)
    publishing_requirements: dict[str, Any] = Field(default_factory=dict)
    optimization_profile: dict[str, Any] | None = None
    mechanism: dict[str, Any] = Field(default_factory=dict)


class CreateJobRequest(BaseModel):
    opportunity: TrendOpportunityIn | dict[str, Any] | None = None
    opportunity_id: int | None = None
    character_slug: str = "ghost_kid"
    platform: str | None = None
    mode: OrchestrationMode = "semi_autonomous"
    process: bool = True
    run_pipeline: bool = True
    # When False, stop after BRIEF_CREATED (concept/brief only)
    concept_count: int = 5
    thresholds: ActionabilityThresholds | None = None
    score_weights: ConceptScoreWeights | None = None


class ApproveJobRequest(BaseModel):
    job_id: str
    gate: Literal["trend", "concept", "publish"] | None = None
    reviewer: str = "human"
    notes: str | None = None
    continue_pipeline: bool = True


class JobOut(BaseModel):
    job_id: str
    content_id: str
    status: str
    current_stage: str
    actionability: str | None = None
    priority: float = 0.0
    mode: str
    platform: str
    character_slug: str | None = None
    selected_concept_id: str | None = None
    backup_concept_id: str | None = None
    production_brief_id: str | None = None
    approval_gate: str | None = None
    lineage: dict[str, Any] = Field(default_factory=dict)
    mechanism: dict[str, Any] | None = None
    concepts: list[ConceptOut] = Field(default_factory=list)
    brief: ReelProductionBrief | None = None
    failure_reason: str | None = None
    retry_count: int = 0
    created_at: datetime | None = None
    completed_at: datetime | None = None
