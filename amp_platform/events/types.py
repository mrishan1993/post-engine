from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EventType(StrEnum):
    TREND_OPPORTUNITY_CREATED = "amp.trend.opportunity_created.v1"
    CONTENT_BRIEF_CREATED = "amp.strategy.brief_created.v1"
    PREDICTION_CREATED = "amp.probability.prediction_created.v1"
    PROMPT_PACK_CREATED = "amp.prompt.pack_created.v1"
    VIDEO_CREATED = "amp.generation.video_created.v1"
    VIDEO_APPROVED = "amp.qa.video_approved.v1"
    VIDEO_REJECTED = "amp.qa.video_rejected.v1"
    VIDEO_PUBLISHED = "amp.publishing.video_published.v1"
    METRICS_UPDATED = "amp.metrics.updated.v1"
    PREDICTION_VERIFIED = "amp.verification.prediction_verified.v1"
    MODEL_UPDATED = "amp.learning.model_updated.v1"


class TrendOpportunityCreated(BaseModel):
    opportunity_id: int
    vertical_slug: str
    score: float
    lifecycle: str | None = None
    pattern_key: str | None = None
    title: str | None = None
    dna_summary: dict[str, Any] = Field(default_factory=dict)


class ContentBriefCreated(BaseModel):
    brief_id: int
    vertical_slug: str
    priority: int = 0
    source: str = "trend_engine_v2"
    opportunity_id: int | None = None
    character_slug: str | None = None
    prediction_id: int | None = None


class PredictionCreated(BaseModel):
    prediction_id: int
    brief_id: int | None = None
    opportunity_id: int | None = None
    vertical_slug: str | None = None
    virality_probability: float
    expected_views: int
    confidence: float
    final_opportunity_score: float
    model_version: str


class VideoCreated(BaseModel):
    video_run_id: int
    brief_id: int
    rendered_path: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)


class VideoApproved(BaseModel):
    video_run_id: int
    reviewer: str
    qa_notes: str | None = None


class VideoRejected(BaseModel):
    video_run_id: int
    reviewer: str
    reason: str


class VideoPublished(BaseModel):
    video_run_id: int
    platforms: list[str] = Field(default_factory=list)
    publication_ids: list[int] = Field(default_factory=list)


class MetricsUpdated(BaseModel):
    publication_id: int
    video_run_id: int | None = None
    views: int | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class PredictionVerified(BaseModel):
    prediction_id: int
    verification_id: int
    mape: float | None = None
    lesson: str | None = None
