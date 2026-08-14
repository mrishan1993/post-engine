from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


IntentType = Literal[
    "information_seeking",
    "content_request",
    "character_request",
    "purchase_intent",
    "complaint",
    "praise",
    "participation",
    "prediction",
    "emotional_attachment",
    "conflict",
    "other",
]
DemandType = Literal[
    "new_character",
    "character_pairing",
    "story_continuation",
    "topic",
    "tutorial",
    "bts",
    "product_feature",
    "format",
    "challenge",
    "collaboration",
    "other",
]
CommunityAction = Literal[
    "reply",
    "like",
    "pin",
    "feature",
    "create_content",
    "create_poll",
    "create_episode",
    "create_campaign",
    "escalate",
    "ignore",
]


class CommentIn(BaseModel):
    text: str
    platform: str = "instagram"
    content_id: str | None = None
    user_tier: str | None = None  # new / follower / fan / advocate — not PII
    likes: int = 0


class AnalyticsIn(BaseModel):
    content_id: str
    views: float | None = None
    likes: float | None = None
    shares: float | None = None
    comments: float | None = None
    completion_rate: float | None = None
    retention: float | None = None
    follows: float | None = None
    unfollows: float | None = None
    returning_viewer_rate: float | None = None
    platform: str = "instagram"


class IngestBatchRequest(BaseModel):
    comments: list[CommentIn] = Field(default_factory=list)
    analytics: list[AnalyticsIn] = Field(default_factory=list)
    characters: list[str] = Field(default_factory=lambda: ["character_a", "character_b"])
    content_id: str | None = None
    platform: str = "instagram"
    process: bool = True  # run clustering/demand/opportunity pipeline


class CreateSegmentRequest(BaseModel):
    name: str
    description: str | None = None
    criteria: dict[str, Any] = Field(default_factory=dict)
    size: int = 0
    segment_kind: Literal["explicit", "discovered"] = "explicit"
    lifecycle_stage: str | None = None
    confidence: float = 0.8


class AcceptOpportunityRequest(BaseModel):
    opportunity_id: str
    strategy_id: str | None = None
    campaign_id: str | None = None
    series_id: str | None = None
    push_to_strategy: bool = True
    push_to_campaign: bool = False


class ResolveAlertRequest(BaseModel):
    alert_id: str
    resolution: str = "resolved"
    notes: str | None = None


class InteractionOut(BaseModel):
    interaction_id: str
    platform: str
    content_id: str | None = None
    text: str | None = None
    intent_type: str | None = None
    sentiment: str | None = None
    emotion: str | None = None
    language: str | None = None
    priority: float | None = None
    is_noise: bool = False
    entities: dict[str, Any] = Field(default_factory=dict)


class DemandOut(BaseModel):
    demand_id: str
    subject: str
    type: str
    volume: int
    velocity: float | None = None
    confidence: float | None = None
    strategic_fit: float | None = None
    recommended_action: str | None = None
    status: str
    audience_segments: list[str] = Field(default_factory=list)
    sentiment: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class OpportunityOut(BaseModel):
    opportunity_id: str
    type: str
    subject: str
    volume: int
    velocity: float | None = None
    confidence: float | None = None
    strategic_fit: float | None = None
    audience_segments: list[str] = Field(default_factory=list)
    sentiment: str | None = None
    recommended_action: str | None = None
    priority: str
    status: str
    demand_id: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    strategy_opportunity_id: str | None = None
    campaign_episode_id: str | None = None


class TopicOut(BaseModel):
    topic_id: str
    topic: str
    volume: int
    velocity: float | None = None
    sentiment: dict[str, Any] = Field(default_factory=dict)
    status: str
    keywords: list[str] = Field(default_factory=list)


class AlertOut(BaseModel):
    alert_id: str
    alert_type: str
    severity: str
    subject: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    recommended_action: str | None = None
    status: str
    created_at: datetime | None = None


class SegmentOut(BaseModel):
    segment_id: str
    name: str
    description: str | None = None
    size: int
    confidence: float | None = None
    status: str
    segment_kind: str
    lifecycle_stage: str | None = None


class CharacterAffinityOut(BaseModel):
    character_slug: str
    affinity_score: float | None = None
    sentiment: dict[str, Any] = Field(default_factory=dict)
    trend: str | None = None
    relationships: dict[str, Any] = Field(default_factory=dict)


class OverviewOut(BaseModel):
    community_health: float
    signal_count: int
    interaction_count: int
    noise_filtered: int
    topics: list[TopicOut] = Field(default_factory=list)
    demands: list[DemandOut] = Field(default_factory=list)
    opportunities: list[OpportunityOut] = Field(default_factory=list)
    alerts: list[AlertOut] = Field(default_factory=list)
    segments: list[SegmentOut] = Field(default_factory=list)
    character_affinity: list[CharacterAffinityOut] = Field(default_factory=list)
    intelligence: dict[str, Any] = Field(default_factory=dict)
