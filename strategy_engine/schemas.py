from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


AutonomyMode = Literal["manual", "assisted", "semi_autonomous", "autonomous"]
OpportunitySource = Literal[
    "trend",
    "evergreen",
    "audience_request",
    "campaign",
    "experiment",
    "reactive",
    "repurpose",
    "gap",
]
PriorityTier = Literal["P0", "P1", "P2", "P3", "P4"]


class BusinessObjective(BaseModel):
    objective: str
    weight: float = 0.25


class ContentPillar(BaseModel):
    name: str
    target_pct: float
    objective: str | None = None
    audiences: list[str] = Field(default_factory=list)
    formats: list[str] = Field(default_factory=lambda: ["reel"])


class AudienceSegment(BaseModel):
    id: str
    label: str
    priority: float = 0.5
    needs: list[str] = Field(default_factory=list)


class StrategyProfile(BaseModel):
    business_objectives: list[BusinessObjective] = Field(
        default_factory=lambda: [
            BusinessObjective(objective="awareness", weight=0.40),
            BusinessObjective(objective="engagement", weight=0.25),
            BusinessObjective(objective="follower_growth", weight=0.20),
            BusinessObjective(objective="conversion", weight=0.15),
        ]
    )
    content_objectives: list[str] = Field(
        default_factory=lambda: [
            "increase_discovery",
            "increase_shareability",
            "increase_profile_visits",
            "improve_audience_relevance",
        ]
    )
    target_audiences: list[AudienceSegment] = Field(
        default_factory=lambda: [
            AudienceSegment(id="new_viewers", label="New viewers", priority=0.8, needs=["hooks", "trends"]),
            AudienceSegment(
                id="engaged_followers",
                label="Engaged followers",
                priority=0.7,
                needs=["character", "series"],
            ),
        ]
    )
    brand_positioning: str = "character-led short-form entertainment"
    content_pillars: list[ContentPillar] = Field(
        default_factory=lambda: [
            ContentPillar(name="trends", target_pct=0.30, objective="discovery"),
            ContentPillar(name="evergreen", target_pct=0.25, objective="authority"),
            ContentPillar(name="character", target_pct=0.20, objective="affinity"),
            ContentPillar(name="education", target_pct=0.15, objective="saves"),
            ContentPillar(name="experiment", target_pct=0.10, objective="learning"),
        ]
    )
    platform_strategy: dict[str, Any] = Field(
        default_factory=lambda: {
            "instagram": {"formats": ["reel"], "weight": 0.7},
            "youtube": {"formats": ["short"], "weight": 0.3},
        }
    )
    content_mix: dict[str, float] = Field(
        default_factory=lambda: {
            "trend": 0.30,
            "evergreen": 0.25,
            "character": 0.20,
            "education": 0.15,
            "experiment": 0.10,
        }
    )
    cadence: dict[str, Any] = Field(
        default_factory=lambda: {"posts_per_day": 2, "max_posts_per_day": 3, "posts_per_week": 14}
    )
    capacity: dict[str, Any] = Field(
        default_factory=lambda: {"reels_per_week": 14, "reels_per_day": 2}
    )
    creative_constraints: dict[str, Any] = Field(default_factory=dict)
    brand_constraints: dict[str, Any] = Field(
        default_factory=lambda: {"forbidden_topics": [], "max_same_hook_in_10": 3}
    )
    experimentation_policy: dict[str, Any] = Field(
        default_factory=lambda: {"reserve_pct": 0.10, "max_high_risk_pct": 0.05}
    )
    optimization_preferences: dict[str, Any] = Field(
        default_factory=lambda: {"optimize_for": "portfolio_value", "not": "raw_views"}
    )


class CreateStrategyRequest(BaseModel):
    name: str = "default"
    character_slug: str = "ghost_kid"
    profile: StrategyProfile | dict[str, Any] | None = None
    autonomy: AutonomyMode = "semi_autonomous"


class IngestOpportunityRequest(BaseModel):
    strategy_id: str
    source: OpportunitySource = "trend"
    title: str | None = None
    platform: str = "instagram"
    format: str = "reel"
    pillar: str | None = None
    audience: str | None = None
    objective: str | None = None
    trend_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    expiration_hours: float | None = None
    auto_accept: bool = True


class CreatePlanRequest(BaseModel):
    strategy_id: str
    days: int = 7
    persist: bool = True


class ReplanRequest(BaseModel):
    plan_id: str
    reason: str | None = None
    force_trend_id: str | None = None


class ExecuteRequest(BaseModel):
    strategy_id: str
    plan_id: str | None = None
    max_jobs: int = 1
    orchestration_mode: str = "autonomous"
    run_pipeline: bool = False


class OpportunityOut(BaseModel):
    opportunity_id: str
    strategy_id: str
    source: str
    title: str | None = None
    pillar: str | None = None
    platform: str
    priority: str
    strategic_score: float | None = None
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    status: str
    expiration_at: datetime | None = None
    trend_id: str | None = None


class PlanItemOut(BaseModel):
    item_id: str
    opportunity_id: str | None = None
    platform: str
    pillar: str | None = None
    content_type: str | None = None
    priority: str
    scheduled_at: datetime | None = None
    status: str
    title: str | None = None


class PlanOut(BaseModel):
    plan_id: str
    strategy_id: str
    period_start: datetime
    period_end: datetime
    objectives: list[dict[str, Any]] = Field(default_factory=list)
    content_mix: dict[str, float] = Field(default_factory=dict)
    capacity: dict[str, Any] = Field(default_factory=dict)
    status: str
    version: int = 1
    items: list[PlanItemOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    content_debt: dict[str, float] = Field(default_factory=dict)


class StrategyOut(BaseModel):
    strategy_id: str
    name: str
    character_slug: str | None
    profile: StrategyProfile
    status: str
    autonomy: str
    version: int
