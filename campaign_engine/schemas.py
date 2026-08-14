from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


CampaignType = Literal[
    "brand",
    "product",
    "character",
    "launch",
    "seasonal",
    "narrative",
    "growth",
    "community",
    "education",
    "conversion",
    "experimental",
]
NarrativeRole = Literal[
    "introduction",
    "setup",
    "escalation",
    "conflict",
    "reveal",
    "payoff",
    "cliffhanger",
    "character_development",
    "audience_interaction",
    "finale",
]
AudienceRole = Literal[
    "discovery",
    "curiosity",
    "relationship",
    "community",
    "conversion",
    "deep",
]


class CampaignObjective(BaseModel):
    primary: str = "audience_growth"
    secondary: list[str] = Field(default_factory=lambda: ["engagement", "character_affinity"])
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "awareness": 0.4,
            "engagement": 0.25,
            "follower_growth": 0.25,
            "conversion": 0.1,
        }
    )


class CreateCampaignRequest(BaseModel):
    name: str
    campaign_type: CampaignType = "character"
    objective: CampaignObjective | dict[str, Any] | None = None
    audience: list[str] = Field(default_factory=lambda: ["gen_z", "millennials"])
    platforms: list[str] = Field(default_factory=lambda: ["instagram", "tiktok", "youtube"])
    character_slug: str = "ghost_kid"
    strategy_id: str | None = None
    content_target: int = 10
    hypothesis: str | None = None
    days: int = 30
    auto_decompose: bool = True
    series_name: str | None = None
    series_premise: str | None = None
    episode_count: int = 5


class CreateSeriesRequest(BaseModel):
    campaign_id: str
    name: str
    premise: str | None = None
    format: str = "reel"
    character_slug: str | None = None
    target_episodes: int = 5
    cadence: dict[str, Any] = Field(default_factory=lambda: {"per_week": 2})


class CreateEpisodeRequest(BaseModel):
    series_id: str
    episode_number: int | None = None
    title: str | None = None
    objective: str | None = None
    premise: str | None = None
    hook: str | None = None
    narrative_role: NarrativeRole | str = "setup"
    audience_role: AudienceRole | str = "discovery"
    platform: str = "instagram"
    cta: str | None = None
    continuity_requirements: dict[str, Any] = Field(default_factory=dict)


class InjectTrendRequest(BaseModel):
    campaign_id: str
    series_id: str | None = None
    episode_id: str | None = None
    trend_id: str
    viral_mechanism: str | None = None
    title: str | None = None
    opportunity_score: float = 0.85


class RecordPerformanceRequest(BaseModel):
    episode_id: str
    views: float | None = None
    shares: float | None = None
    followers_gained: float | None = None
    retention: float | None = None
    extras: dict[str, Any] = Field(default_factory=dict)


class OptimizeCampaignRequest(BaseModel):
    campaign_id: str
    extend_if_strong: bool = True
    retire_if_weak: bool = True


class ExecuteEpisodeRequest(BaseModel):
    episode_id: str
    run_pipeline: bool = False
    orchestration_mode: str = "autonomous"
    push_to_strategy: bool = True


class EpisodeOut(BaseModel):
    episode_id: str
    series_id: str
    campaign_id: str
    episode_number: int
    title: str | None = None
    objective: str | None = None
    premise: str | None = None
    hook: str | None = None
    narrative_role: str | None = None
    audience_role: str | None = None
    platform: str
    trend_id: str | None = None
    status: str
    performance: dict[str, Any] | None = None
    orchestration_job_id: str | None = None
    continuity_requirements: dict[str, Any] = Field(default_factory=dict)


class SeriesOut(BaseModel):
    series_id: str
    campaign_id: str
    name: str
    premise: str | None = None
    status: str
    target_episodes: int
    episodes: list[EpisodeOut] = Field(default_factory=list)


class CampaignOut(BaseModel):
    campaign_id: str
    strategy_id: str | None = None
    name: str
    campaign_type: str
    objective: dict[str, Any]
    audience: list[Any] = Field(default_factory=list)
    platforms: list[Any] = Field(default_factory=list)
    status: str
    priority: float
    content_target: int
    character_slug: str | None = None
    hypothesis: str | None = None
    continuity: dict[str, Any] = Field(default_factory=dict)
    journey: dict[str, Any] = Field(default_factory=dict)
    series: list[SeriesOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class FranchiseOut(BaseModel):
    franchise_id: str
    campaign_id: str | None
    series_id: str | None
    name: str | None
    status: str
    confidence: float | None
    performance_basis: dict[str, Any] = Field(default_factory=dict)
