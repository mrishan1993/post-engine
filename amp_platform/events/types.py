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
    ANALYTICS_TRACKING_STARTED = "amp.performance.tracking_started.v1"
    ANALYTICS_COLLECTION_STARTED = "amp.performance.collection_started.v1"
    ANALYTICS_COLLECTION_COMPLETED = "amp.performance.collection_completed.v1"
    PERFORMANCE_SNAPSHOT_CAPTURED = "amp.performance.snapshot_captured.v1"
    VIRAL_STATE_CHANGED = "amp.performance.viral_state_changed.v1"
    VIRAL_DETECTED = "amp.performance.viral_detected.v1"
    LOW_RETENTION_DETECTED = "amp.performance.low_retention_detected.v1"
    PERFORMANCE_DROP = "amp.performance.drop_detected.v1"
    SECOND_WAVE_DETECTED = "amp.performance.second_wave_detected.v1"
    HIGH_SHARE_RATE = "amp.performance.high_share_rate.v1"
    VERIFICATION_STARTED = "amp.verification.started.v1"
    EARLY_VERIFICATION_COMPLETED = "amp.verification.early_completed.v1"
    PRIMARY_VERIFICATION_COMPLETED = "amp.verification.primary_completed.v1"
    LONG_TERM_VERIFICATION_COMPLETED = "amp.verification.long_term_completed.v1"
    PREDICTION_CORRECT = "amp.verification.prediction_correct.v1"
    PREDICTION_INCORRECT = "amp.verification.prediction_incorrect.v1"
    PREDICTION_OVERCONFIDENT = "amp.verification.prediction_overconfident.v1"
    PREDICTION_UNDERCONFIDENT = "amp.verification.prediction_underconfident.v1"
    CALIBRATION_UPDATED = "amp.verification.calibration_updated.v1"
    LEARNING_SIGNAL_CREATED = "amp.verification.learning_signal_created.v1"
    LEARNING_OBSERVATION_CREATED = "amp.learning.observation_created.v1"
    PATTERN_DETECTED = "amp.learning.pattern_detected.v1"
    OPTIMIZATION_RECOMMENDATION_CREATED = "amp.learning.recommendation_created.v1"
    EXPERIMENT_CREATED = "amp.learning.experiment_created.v1"
    EXPERIMENT_COMPLETED = "amp.learning.experiment_completed.v1"
    MODEL_TRAINING_STARTED = "amp.learning.model_training_started.v1"
    MODEL_TRAINING_COMPLETED = "amp.learning.model_training_completed.v1"
    MODEL_EVALUATION_COMPLETED = "amp.learning.model_evaluation_completed.v1"
    MODEL_PROMOTED = "amp.learning.model_promoted.v1"
    OPTIMIZATION_PROFILE_UPDATED = "amp.learning.optimization_profile_updated.v1"
    GENERATION_STRATEGY_UPDATED = "amp.learning.generation_strategy_updated.v1"
    ORCHESTRATION_JOB_CREATED = "amp.orchestration.job_created.v1"
    ORCHESTRATION_EVALUATED = "amp.orchestration.evaluated.v1"
    TREND_ACTIONABLE = "amp.orchestration.trend_actionable.v1"
    CONCEPT_GENERATION_REQUESTED = "amp.orchestration.concept_generation_requested.v1"
    CONCEPT_GENERATION_COMPLETED = "amp.orchestration.concept_generation_completed.v1"
    CONCEPT_SELECTED = "amp.orchestration.concept_selected.v1"
    PRODUCTION_BRIEF_CREATED = "amp.orchestration.production_brief_created.v1"
    STORY_REQUESTED = "amp.orchestration.story_requested.v1"
    ORCHESTRATION_STORY_COMPLETED = "amp.orchestration.story_completed.v1"
    ORCHESTRATION_STORYBOARD_COMPLETED = "amp.orchestration.storyboard_completed.v1"
    ORCHESTRATION_ASSETS_COMPLETED = "amp.orchestration.assets_completed.v1"
    ORCHESTRATION_ASSEMBLY_COMPLETED = "amp.orchestration.assembly_completed.v1"
    ORCHESTRATION_QA_COMPLETED = "amp.orchestration.qa_completed.v1"
    ORCHESTRATION_PUBLISHED = "amp.orchestration.published.v1"
    ORCHESTRATION_LEARNING_HANDOFF = "amp.orchestration.learning_handoff.v1"
    ORCHESTRATION_AWAITING_APPROVAL = "amp.orchestration.awaiting_approval.v1"
    ORCHESTRATION_JOB_COMPLETED = "amp.orchestration.job_completed.v1"
    ORCHESTRATION_JOB_FAILED = "amp.orchestration.job_failed.v1"
    STRATEGY_CREATED = "amp.strategy.created.v1"
    STRATEGY_UPDATED = "amp.strategy.updated.v1"
    OPPORTUNITY_RECEIVED = "amp.strategy.opportunity_received.v1"
    OPPORTUNITY_SCORED = "amp.strategy.opportunity_scored.v1"
    OPPORTUNITY_ACCEPTED = "amp.strategy.opportunity_accepted.v1"
    OPPORTUNITY_REJECTED = "amp.strategy.opportunity_rejected.v1"
    PLAN_CREATED = "amp.strategy.plan_created.v1"
    PLAN_UPDATED = "amp.strategy.plan_updated.v1"
    PLAN_REPLANNED = "amp.strategy.plan_replanned.v1"
    CONTENT_SCHEDULED = "amp.strategy.content_scheduled.v1"
    CONTENT_PRIORITIZED = "amp.strategy.content_prioritized.v1"
    CONTENT_DEFERRED = "amp.strategy.content_deferred.v1"
    CONTENT_CANCELLED = "amp.strategy.content_cancelled.v1"
    CONTENT_EXECUTION_REQUESTED = "amp.strategy.content_execution_requested.v1"
    STRATEGY_LEARNING_RECEIVED = "amp.strategy.learning_received.v1"
    STRATEGY_OPTIMIZED = "amp.strategy.optimized.v1"
    # Campaign & Content Portfolio Engine
    CAMPAIGN_CREATED = "amp.campaign.created.v1"
    CAMPAIGN_STARTED = "amp.campaign.started.v1"
    CAMPAIGN_UPDATED = "amp.campaign.updated.v1"
    CAMPAIGN_PAUSED = "amp.campaign.paused.v1"
    CAMPAIGN_COMPLETED = "amp.campaign.completed.v1"
    SERIES_CREATED = "amp.campaign.series_created.v1"
    SERIES_VALIDATED = "amp.campaign.series_validated.v1"
    SERIES_EXTENDED = "amp.campaign.series_extended.v1"
    SERIES_RETIRED = "amp.campaign.series_retired.v1"
    EPISODE_CREATED = "amp.campaign.episode_created.v1"
    EPISODE_SCHEDULED = "amp.campaign.episode_scheduled.v1"
    EPISODE_EXECUTION_REQUESTED = "amp.campaign.episode_execution_requested.v1"
    EPISODE_PUBLISHED = "amp.campaign.episode_published.v1"
    CAMPAIGN_PERFORMANCE_UPDATED = "amp.campaign.performance_updated.v1"
    FRANCHISE_DETECTED = "amp.campaign.franchise_detected.v1"
    FRANCHISE_APPROVED = "amp.campaign.franchise_approved.v1"
    FRANCHISE_RETIRED = "amp.campaign.franchise_retired.v1"
    CAMPAIGN_REPLANNED = "amp.campaign.replanned.v1"
    CAMPAIGN_OPTIMIZED = "amp.campaign.optimized.v1"
    # Audience Intelligence & Community Engine
    AUDIENCE_SIGNAL_DETECTED = "amp.audience.signal_detected.v1"
    AUDIENCE_SEGMENT_UPDATED = "amp.audience.segment_updated.v1"
    AUDIENCE_INTENT_DETECTED = "amp.audience.intent_detected.v1"
    AUDIENCE_DEMAND_DETECTED = "amp.audience.demand_detected.v1"
    COMMUNITY_TOPIC_DETECTED = "amp.audience.community_topic_detected.v1"
    COMMUNITY_TREND_DETECTED = "amp.audience.community_trend_detected.v1"
    COMMUNITY_SENTIMENT_CHANGED = "amp.audience.community_sentiment_changed.v1"
    CHARACTER_AFFINITY_CHANGED = "amp.audience.character_affinity_changed.v1"
    CHARACTER_RELATIONSHIP_SIGNAL_DETECTED = "amp.audience.character_relationship_signal.v1"
    CONTENT_REQUEST_DETECTED = "amp.audience.content_request_detected.v1"
    CONTENT_OPPORTUNITY_CREATED = "amp.audience.content_opportunity_created.v1"
    COMMUNITY_HEALTH_CHANGED = "amp.audience.community_health_changed.v1"
    AUDIENCE_CHURN_RISK_DETECTED = "amp.audience.churn_risk_detected.v1"
    COMMUNITY_ALERT_CREATED = "amp.audience.community_alert_created.v1"


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
