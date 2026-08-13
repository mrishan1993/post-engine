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
    ASSET_CREATED = "amp.asset.created.v1"
    CHARACTER_CREATED = "amp.asset.character_created.v1"
    CHARACTER_VERSIONED = "amp.asset.character_versioned.v1"
    GENERATION_CONTEXT_RESOLVED = "amp.asset.generation_context_resolved.v1"
    STORY_CREATED = "amp.story.created.v1"
    STORY_APPROVED = "amp.story.approved.v1"
    STORYBOARD_CREATED = "amp.storyboard.created.v1"
    STORYBOARD_APPROVED = "amp.storyboard.approved.v1"
    GENERATION_REQUESTED = "amp.generation.requested.v1"
    GENERATION_QUEUED = "amp.generation.queued.v1"
    GENERATION_STARTED = "amp.generation.started.v1"
    GENERATION_SUBMITTED = "amp.generation.submitted.v1"
    GENERATION_PROCESSING = "amp.generation.processing.v1"
    GENERATION_COMPLETED = "amp.generation.completed.v1"
    GENERATION_FAILED = "amp.generation.failed.v1"
    GENERATION_RETRIED = "amp.generation.retried.v1"
    GENERATION_FALLBACK = "amp.generation.fallback.v1"
    ARTIFACT_CREATED = "amp.generation.artifact_created.v1"
    GENERATION_QA_COMPLETED = "amp.generation.qa_completed.v1"
    VIDEO_GENERATION_REQUESTED = "amp.video.generation_requested.v1"
    VIDEO_GENERATION_QUEUED = "amp.video.generation_queued.v1"
    VIDEO_GENERATION_STARTED = "amp.video.generation_started.v1"
    VIDEO_GENERATION_SUBMITTED = "amp.video.generation_submitted.v1"
    VIDEO_GENERATION_PROCESSING = "amp.video.generation_processing.v1"
    VIDEO_GENERATION_COMPLETED = "amp.video.generation_completed.v1"
    VIDEO_GENERATION_FAILED = "amp.video.generation_failed.v1"
    VIDEO_GENERATION_RETRIED = "amp.video.generation_retried.v1"
    VIDEO_GENERATION_FALLBACK = "amp.video.generation_fallback.v1"
    VIDEO_ARTIFACT_CREATED = "amp.video.artifact_created.v1"
    VIDEO_TECHNICAL_QA_COMPLETED = "amp.video.technical_qa_completed.v1"
    IMAGE_GENERATION_REQUESTED = "amp.image.generation_requested.v1"
    IMAGE_GENERATION_QUEUED = "amp.image.generation_queued.v1"
    IMAGE_GENERATION_STARTED = "amp.image.generation_started.v1"
    IMAGE_GENERATION_SUBMITTED = "amp.image.generation_submitted.v1"
    IMAGE_GENERATION_PROCESSING = "amp.image.generation_processing.v1"
    IMAGE_GENERATION_COMPLETED = "amp.image.generation_completed.v1"
    IMAGE_GENERATION_FAILED = "amp.image.generation_failed.v1"
    IMAGE_GENERATION_RETRIED = "amp.image.generation_retried.v1"
    IMAGE_GENERATION_FALLBACK = "amp.image.generation_fallback.v1"
    IMAGE_ARTIFACT_CREATED = "amp.image.artifact_created.v1"
    IMAGE_TECHNICAL_QA_COMPLETED = "amp.image.technical_qa_completed.v1"
    IMAGE_EDITED = "amp.image.edited.v1"
    IMAGE_VERSION_CREATED = "amp.image.version_created.v1"
    MUSIC_GENERATION_REQUESTED = "amp.music.generation_requested.v1"
    MUSIC_GENERATION_STARTED = "amp.music.generation_started.v1"
    MUSIC_GENERATION_COMPLETED = "amp.music.generation_completed.v1"
    MUSIC_GENERATION_FAILED = "amp.music.generation_failed.v1"
    MUSIC_GENERATION_FALLBACK = "amp.music.generation_fallback.v1"
    MUSIC_ARTIFACT_CREATED = "amp.music.artifact_created.v1"
    SFX_REQUESTED = "amp.music.sfx_requested.v1"
    SFX_SELECTED = "amp.music.sfx_selected.v1"
    AUDIO_TIMELINE_CREATED = "amp.music.audio_timeline_created.v1"
    AUDIO_QUALITY_VALIDATED = "amp.music.audio_quality_validated.v1"
    VOICE_GENERATION_REQUESTED = "amp.voice.generation_requested.v1"
    VOICE_GENERATION_QUEUED = "amp.voice.generation_queued.v1"
    VOICE_GENERATION_STARTED = "amp.voice.generation_started.v1"
    VOICE_GENERATION_COMPLETED = "amp.voice.generation_completed.v1"
    VOICE_GENERATION_FAILED = "amp.voice.generation_failed.v1"
    VOICE_GENERATION_RETRIED = "amp.voice.generation_retried.v1"
    VOICE_GENERATION_FALLBACK = "amp.voice.generation_fallback.v1"
    VOICE_ARTIFACT_CREATED = "amp.voice.artifact_created.v1"
    VOICE_TECHNICAL_QA_COMPLETED = "amp.voice.technical_qa_completed.v1"
    VOICE_TIMELINE_CREATED = "amp.voice.timeline_created.v1"
    ASSEMBLY_CREATED = "amp.assembly.created.v1"
    ASSEMBLY_UPDATED = "amp.assembly.updated.v1"
    ASSEMBLY_VALIDATED = "amp.assembly.validated.v1"
    RENDER_REQUESTED = "amp.assembly.render_requested.v1"
    RENDER_QUEUED = "amp.assembly.render_queued.v1"
    RENDER_STARTED = "amp.assembly.render_started.v1"
    RENDER_PROGRESS = "amp.assembly.render_progress.v1"
    RENDER_COMPLETED = "amp.assembly.render_completed.v1"
    RENDER_FAILED = "amp.assembly.render_failed.v1"
    RENDER_CANCELLED = "amp.assembly.render_cancelled.v1"
    RENDER_ARTIFACT_CREATED = "amp.assembly.render_artifact_created.v1"
    RENDER_TECHNICAL_QA_COMPLETED = "amp.assembly.render_technical_qa_completed.v1"
    SOCIAL_ACCOUNT_CONNECTED = "amp.publishing.social_account_connected.v1"
    SOCIAL_ACCOUNT_DISCONNECTED = "amp.publishing.social_account_disconnected.v1"
    PUBLISHING_PLAN_CREATED = "amp.publishing.plan_created.v1"
    PUBLISHING_PLAN_APPROVED = "amp.publishing.plan_approved.v1"
    PUBLISHING_SCHEDULED = "amp.publishing.scheduled.v1"
    PUBLISHING_QUEUED = "amp.publishing.queued.v1"
    PUBLISHING_STARTED = "amp.publishing.started.v1"
    MEDIA_UPLOAD_STARTED = "amp.publishing.media_upload_started.v1"
    MEDIA_UPLOAD_COMPLETED = "amp.publishing.media_upload_completed.v1"
    PUBLISHING_COMPLETED = "amp.publishing.completed.v1"
    PUBLISHING_FAILED = "amp.publishing.failed.v1"
    PUBLISHING_RETRY = "amp.publishing.retry.v1"
    PUBLISHING_BLOCKED = "amp.publishing.blocked.v1"
    PUBLICATION_VERIFIED = "amp.publishing.publication_verified.v1"
    QA_RUN_STARTED = "amp.qa.run_started.v1"
    TECHNICAL_QA_COMPLETED = "amp.qa.technical_completed.v1"
    VISUAL_QA_COMPLETED = "amp.qa.visual_completed.v1"
    AUDIO_QA_COMPLETED = "amp.qa.audio_completed.v1"
    CHARACTER_QA_COMPLETED = "amp.qa.character_completed.v1"
    STORY_QA_COMPLETED = "amp.qa.story_completed.v1"
    CAPTION_QA_COMPLETED = "amp.qa.caption_completed.v1"
    PLATFORM_QA_COMPLETED = "amp.qa.platform_completed.v1"
    SAFETY_QA_COMPLETED = "amp.qa.safety_completed.v1"
    QA_RUN_COMPLETED = "amp.qa.run_completed.v1"
    QA_APPROVED = "amp.qa.approved.v1"
    QA_REJECTED = "amp.qa.rejected.v1"
    QA_REPAIR_REQUESTED = "amp.qa.repair_requested.v1"
    QA_REGENERATION_REQUESTED = "amp.qa.regeneration_requested.v1"
    QA_REVIEW_REQUIRED = "amp.qa.review_required.v1"


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


class StoryCreated(BaseModel):
    story_id: str
    title: str | None = None
    quality_score: float = 0.0
    platform: str | None = None
    candidate_index: int = 0


class StoryApproved(BaseModel):
    story_id: str
    quality_score: float = 0.0


class StoryboardCreated(BaseModel):
    storyboard_id: str
    story_id: str
    version: int = 1
    scene_count: int = 0
    shot_count: int = 0
    duration_sec: float = 0.0
    quality_score: float = 0.0


class StoryboardApproved(BaseModel):
    storyboard_id: str
    story_id: str
    version: int = 1
    quality_score: float = 0.0


class PromptPackCreated(BaseModel):
    prompt_package_id: str
    prompt_spec_id: str | None = None
    provider: str | None = None
    model: str | None = None
    modality: str | None = None
    quality_score: float = 0.0
    storyboard_id: str | None = None
    storyboard_shot_id: str | None = None
    story_id: str | None = None
    brief_id: int | None = None
    prediction_id: int | None = None
    prompt_artifact_ids: list[str] = Field(default_factory=list)


class GenerationRequested(BaseModel):
    request_id: str
    modality: str
    variants: int = 1
    prompt_package_id: str | None = None


class GenerationCompleted(BaseModel):
    job_id: str
    artifact_id: str
    provider: str | None = None
    model: str | None = None
    cost: float = 0.0


class ArtifactCreated(BaseModel):
    artifact_id: str
    job_id: str
    type: str
    storage_uri: str | None = None
    sha256: str | None = None


class VideoArtifactCreated(BaseModel):
    request_id: str
    job_id: str
    artifact_id: str
    provider: str | None = None
    duration_sec: float = 0.0
    storage_uri: str | None = None
    width: int | None = None
    height: int | None = None


class ImageArtifactCreated(BaseModel):
    request_id: str
    job_id: str
    artifact_id: str
    provider: str | None = None
    storage_uri: str | None = None
    width: int | None = None
    height: int | None = None
    quality_score: float | None = None
