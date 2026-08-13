from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ViralState = Literal[
    "normal", "accelerating", "viral", "peak", "decelerating", "plateau", "second_wave"
]
PollTier = Literal["high", "medium", "low", "archival"]


class CanonicalMetrics(BaseModel):
    views: int = 0
    impressions: int | None = None
    reach: int | None = None
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    watch_time_sec: float | None = None
    average_watch_time_sec: float | None = None
    completion_rate: float | None = None
    replays: int | None = None
    profile_visits: int | None = None
    followers_gained: int | None = None
    link_clicks: int | None = None
    non_follower_reach: int | None = None
    unique_viewers: int | None = None


class MetricPoint(BaseModel):
    name: str
    value: float | None
    source: str = "platform"
    captured_at: datetime | None = None
    availability: Literal["available", "unavailable"] = "available"
    confidence: Literal["high", "medium", "low"] = "high"


class DerivedMetrics(BaseModel):
    like_rate: float = 0.0
    comment_rate: float = 0.0
    share_rate: float = 0.0
    save_rate: float = 0.0
    engagement_rate: float = 0.0
    weighted_engagement: float = 0.0
    virality_score: float = 0.0
    view_velocity_per_hour: float = 0.0
    share_velocity_per_hour: float = 0.0
    acceleration: float = 0.0
    engagement_formula_version: str = "v1"
    virality_model_version: str = "v1"


class EngagementWeights(BaseModel):
    like: float = 1.0
    comment: float = 3.0
    save: float = 4.0
    share: float = 5.0
    follow: float = 6.0
    version: str = "v1"


class ViralityWeights(BaseModel):
    share_rate: float = 0.25
    view_velocity: float = 0.20
    non_follower_reach: float = 0.20
    completion: float = 0.15
    rewatch: float = 0.10
    engagement: float = 0.10
    version: str = "v1"


class ContentFingerprint(BaseModel):
    character: str | None = None
    genre: str | None = None
    hook_type: str | None = None
    conflict_type: str | None = None
    twist_type: str | None = None
    ending_type: str | None = None
    duration: float | None = None
    emotion: dict[str, float] = Field(default_factory=dict)
    visual_style: str | None = None
    music_style: str | None = None
    experiment_id: str | None = None
    variant_id: str | None = None


class RetentionPoint(BaseModel):
    timestamp_sec: float
    retention_percent: float


class AudienceData(BaseModel):
    follower_count: int | None = None
    non_follower_reach: int | None = None
    demographics: dict[str, Any] = Field(default_factory=dict)
    geography: dict[str, Any] = Field(default_factory=dict)


class AdapterFetchResult(BaseModel):
    raw_response: dict[str, Any]
    endpoint: str = "insights"
    http_status: int = 200
    metrics: CanonicalMetrics
    retention: list[RetentionPoint] = Field(default_factory=list)
    audience: AudienceData | None = None
    platform_updated_at: datetime | None = None


class PerformanceSnapshotOut(BaseModel):
    id: str
    publication_id: str
    platform: str
    account_id: str | None = None
    captured_at: datetime
    age_since_publish_sec: int | None = None
    metrics: CanonicalMetrics
    derived: DerivedMetrics | None = None


class BenchmarkResult(BaseModel):
    dimension: str
    key: str
    sample_size: int
    metric: str
    median: float
    p75: float
    p90: float
    p95: float
    performance_index: float | None = None
    percentile_rank: float | None = None


class StartTrackingRequest(BaseModel):
    publication_id: str
    content_fingerprint: ContentFingerprint | dict[str, Any] | None = None
    prediction: dict[str, Any] = Field(default_factory=dict)
    collect_now: bool = True
    # Simulate age progression for offline/stub acceptance tests
    simulate_age_sec: int | None = None
    growth_profile: Literal["normal", "viral", "slow"] = "normal"


class RefreshRequest(BaseModel):
    publication_id: str
    simulate_age_sec: int | None = None
    growth_profile: Literal["normal", "viral", "slow"] | None = None


class CompareRequest(BaseModel):
    publication_ids: list[str]
