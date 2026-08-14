from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


EvidenceStatus = Literal["EXPLORATORY", "SUPPORTED", "STRONG"]
AutonomyLevel = Literal[1, 2, 3, 4, 5]
ObjectiveProfile = Literal["growth", "engagement", "retention", "brand"]


class OptimizationPolicy(BaseModel):
    exploration_rate: float = 0.20
    min_sample_size: int = 30
    auto_apply_confidence: float = 0.90
    require_human_review_below: float = 0.65
    max_change_per_iteration: float = 0.15
    autonomy_level: AutonomyLevel = 2
    # V1: analyze + recommend only (levels 1–2)
    objective_profile: ObjectiveProfile = "growth"
    objective_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "virality": 0.40,
            "engagement": 0.25,
            "completion": 0.20,
            "follower_conversion": 0.10,
            "brand_health": 0.05,
        }
    )


class ScopeSpec(BaseModel):
    character: str | None = None
    platform: str | None = None
    content_type: str = "short_video"
    story_type: str | None = None
    trend_category: str | None = None


class PatternStat(BaseModel):
    dimension: str
    value: str
    sample_size: int
    median_metric: float
    baseline_median: float
    lift: float
    evidence_status: EvidenceStatus
    confidence: float
    note: str = "Association in observed sample; not causal proof"


class RecommendationOut(BaseModel):
    id: str | None = None
    target: str
    action: str
    change: dict[str, Any] = Field(default_factory=dict)
    expected_effect: dict[str, Any] = Field(default_factory=dict)
    confidence: float
    evidence: dict[str, Any] = Field(default_factory=dict)
    status: str = "proposed"


class ContentOptimizationBrief(BaseModel):
    """Handed to Story / Storyboard / Prompt — does not write the story."""

    character: dict[str, Any] = Field(default_factory=dict)
    platform: dict[str, Any] = Field(default_factory=dict)
    trend: dict[str, Any] = Field(default_factory=dict)
    recommendations: dict[str, Any] = Field(default_factory=dict)
    exploration: dict[str, Any] | None = None
    confidence: dict[str, Any] = Field(default_factory=dict)
    evidence_summary: list[dict[str, Any]] = Field(default_factory=list)
    note: str = "Brief constrains creative engines; Story Engine still owns narrative"


class OptimizationProfileOut(BaseModel):
    profile_id: str
    scope: ScopeSpec
    recommendations: list[RecommendationOut] = Field(default_factory=list)
    patterns: list[PatternStat] = Field(default_factory=list)
    brief: ContentOptimizationBrief | None = None
    confidence: float = 0.5
    version: int = 1
    status: str = "active"
    observation_count: int = 0
    policy: OptimizationPolicy = Field(default_factory=OptimizationPolicy)


class CreateObservationRequest(BaseModel):
    verification_id: str | None = None
    publication_id: str | None = None
    feature_vector: dict[str, Any] = Field(default_factory=dict)
    outcome_vector: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None


class RecommendRequest(BaseModel):
    scope: ScopeSpec = Field(default_factory=ScopeSpec)
    policy: OptimizationPolicy | None = None
    persist: bool = True
    include_exploration: bool = True


class CreateExperimentRequest(BaseModel):
    hypothesis: str
    variable: str
    control: dict[str, Any]
    variants: list[dict[str, Any]] = Field(default_factory=list)
    target_metric: str = "completion_rate"
    sample_target: int = 100
    scope: ScopeSpec | None = None
    start: bool = True


class TrainModelRequest(BaseModel):
    model_name: str = "virality_predictor"
    version: str | None = None
    notes: str | None = None


class PromoteModelRequest(BaseModel):
    model_id: str
    require_better_than_champion: bool = True


class IngestVerificationRequest(BaseModel):
    verification_id: str
