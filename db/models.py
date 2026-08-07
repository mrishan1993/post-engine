from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


class JSONList(TypeDecorator):
    """Store list values as JSON; portable across SQLite and Postgres."""

    impl = JSON
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return []
        return list(value)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return []
        return list(value)


class Base(DeclarativeBase):
    pass


class Vertical(Base):
    __tablename__ = "verticals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    config_path: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    briefs: Mapped[list[ContentBrief]] = relationship(back_populates="vertical")
    video_runs: Mapped[list[VideoRun]] = relationship(back_populates="vertical")


class ContentBrief(Base):
    __tablename__ = "content_briefs"
    __table_args__ = (
        Index("idx_content_briefs_status_priority", "status", "priority"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vertical_id: Mapped[int] = mapped_column(ForeignKey("verticals.id"), nullable=False)
    brief_text: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    source: Mapped[str | None] = mapped_column(String(64))
    generated_by_run_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    vertical: Mapped[Vertical] = relationship(back_populates="briefs")
    video_runs: Mapped[list[VideoRun]] = relationship(back_populates="brief")


class VideoRun(Base):
    __tablename__ = "video_runs"
    __table_args__ = (
        Index("idx_video_runs_status", "status"),
        Index("idx_video_runs_vertical", "vertical_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    brief_id: Mapped[int] = mapped_column(ForeignKey("content_briefs.id"), nullable=False)
    vertical_id: Mapped[int] = mapped_column(ForeignKey("verticals.id"), nullable=False)
    parent_run_id: Mapped[int | None] = mapped_column(ForeignKey("video_runs.id"))
    status: Mapped[str] = mapped_column(String(32), default="created")
    script_text: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(String(256))
    description: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JSONList, default=list)
    audio_asset_path: Mapped[str | None] = mapped_column(String(512))
    audio_duration_sec: Mapped[int | None] = mapped_column(Integer)
    visual_asset_path: Mapped[str | None] = mapped_column(String(512))
    rendered_video_path: Mapped[str | None] = mapped_column(String(512))
    rendered_duration_sec: Mapped[int | None] = mapped_column(Integer)
    safety_check_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    qa_reviewer: Mapped[str | None] = mapped_column(String(128))
    qa_notes: Mapped[str | None] = mapped_column(Text)
    qa_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_log: Mapped[str | None] = mapped_column(Text)
    total_cost_usd: Mapped[float] = mapped_column(Numeric(8, 4), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    brief: Mapped[ContentBrief] = relationship(back_populates="video_runs")
    vertical: Mapped[Vertical] = relationship(back_populates="video_runs")
    publications: Mapped[list[Publication]] = relationship(back_populates="video_run")
    agent_logs: Mapped[list[AgentRunLog]] = relationship(back_populates="video_run")
    parent_run: Mapped[VideoRun | None] = relationship(remote_side=[id])


class Publication(Base):
    __tablename__ = "publications"
    __table_args__ = (
        UniqueConstraint("video_run_id", "platform", name="idx_publications_run_platform"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_run_id: Mapped[int] = mapped_column(ForeignKey("video_runs.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    platform_post_id: Mapped[str | None] = mapped_column(String(256))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    platform_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="scheduled")
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    video_run: Mapped[VideoRun] = relationship(back_populates="publications")
    metrics: Mapped[list[VideoMetric]] = relationship(back_populates="publication")


class VideoMetric(Base):
    __tablename__ = "video_metrics"
    __table_args__ = (
        Index("idx_video_metrics_publication", "publication_id", "pulled_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    publication_id: Mapped[int] = mapped_column(ForeignKey("publications.id"), nullable=False)
    pulled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    views: Mapped[int | None] = mapped_column(Integer)
    avg_view_duration_sec: Mapped[int | None] = mapped_column(Integer)
    likes: Mapped[int | None] = mapped_column(Integer)
    comments: Mapped[int | None] = mapped_column(Integer)
    estimated_revenue_usd: Mapped[float | None] = mapped_column(Numeric(10, 2))

    publication: Mapped[Publication] = relationship(back_populates="metrics")


class AgentRunLog(Base):
    __tablename__ = "agent_run_logs"
    __table_args__ = (
        Index("idx_agent_run_logs_video_run", "video_run_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_run_id: Mapped[int] = mapped_column(ForeignKey("video_runs.id"), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64))
    input_summary: Mapped[str | None] = mapped_column(Text)
    output_summary: Mapped[str | None] = mapped_column(Text)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(8, 4))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    success: Mapped[bool | None] = mapped_column(Boolean)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    video_run: Mapped[VideoRun] = relationship(back_populates="agent_logs")


class ProviderHealth(Base):
    __tablename__ = "provider_health"

    provider: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    is_healthy: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------------------------------------------------------------------------
# Trend engine tables (shared DB with content pipeline)
# ---------------------------------------------------------------------------


class TrendSignal(Base):
    __tablename__ = "trend_signals"
    __table_args__ = (
        Index("idx_trend_signals_source_collected", "source", "collected_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(256))
    title_or_query: Mapped[str | None] = mapped_column(Text)
    raw_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    region: Mapped[str | None] = mapped_column(String(16))
    category: Mapped[str | None] = mapped_column(String(64))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    topics: Mapped[list[TrendTopic]] = relationship(
        secondary="trend_topic_signals",
        back_populates="signals",
    )


class TrendTopic(Base):
    __tablename__ = "trend_topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_label: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    candidate_verticals: Mapped[list[str]] = mapped_column(JSONList, default=list)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(32), default="active")

    signals: Mapped[list[TrendSignal]] = relationship(
        secondary="trend_topic_signals",
        back_populates="topics",
    )
    scores: Mapped[list[TrendScore]] = relationship(back_populates="topic")
    feedback: Mapped[list[TrendFeedback]] = relationship(back_populates="topic")


class TrendTopicSignal(Base):
    __tablename__ = "trend_topic_signals"

    topic_id: Mapped[int] = mapped_column(ForeignKey("trend_topics.id"), primary_key=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("trend_signals.id"), primary_key=True)


class TrendScore(Base):
    __tablename__ = "trend_scores"
    __table_args__ = (
        Index("idx_trend_scores_topic_time", "topic_id", "scored_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("trend_topics.id"), nullable=False)
    score: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    score_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    topic: Mapped[TrendTopic] = relationship(back_populates="scores")


class TrendFeedback(Base):
    __tablename__ = "trend_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("trend_topics.id"), nullable=False)
    content_brief_id: Mapped[int | None] = mapped_column(ForeignKey("content_briefs.id"))
    predicted_score: Mapped[float | None] = mapped_column(Numeric(6, 3))
    actual_views: Mapped[int | None] = mapped_column(Integer)
    actual_engagement_rate: Mapped[float | None] = mapped_column(Numeric(6, 4))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    topic: Mapped[TrendTopic] = relationship(back_populates="feedback")


# ---------------------------------------------------------------------------
# Trend Engine V2 — Viral Intelligence (patterns, not just topics)
# ---------------------------------------------------------------------------


class RawContent(Base):
    """Discovered content units from sanctioned sources (Layer 1)."""

    __tablename__ = "raw_content"
    __table_args__ = (
        Index("idx_raw_content_source_collected", "source", "collected_at"),
        Index("idx_raw_content_external", "source", "external_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(256))
    url: Mapped[str | None] = mapped_column(String(1024))
    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    creator_handle: Mapped[str | None] = mapped_column(String(256))
    platform_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    trend_signal_id: Mapped[int | None] = mapped_column(ForeignKey("trend_signals.id"))


class ContentFeature(Base):
    """Content DNA — structured viral features for one raw_content item."""

    __tablename__ = "content_features"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raw_content_id: Mapped[int] = mapped_column(ForeignKey("raw_content.id"), unique=True, nullable=False)
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    hook: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    story_arc: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    emotion: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    visual_style: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    audio_style: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    editing_style: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    format: Mapped[str | None] = mapped_column(String(64))
    audience: Mapped[str | None] = mapped_column(String(128))
    topics: Mapped[list[str]] = mapped_column(JSONList, default=list)
    hashtags: Mapped[list[str]] = mapped_column(JSONList, default=list)
    cta: Mapped[str | None] = mapped_column(Text)
    velocity: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CommentSentiment(Base):
    __tablename__ = "comment_sentiment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raw_content_id: Mapped[int] = mapped_column(ForeignKey("raw_content.id"), nullable=False)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    requests: Mapped[list[str]] = mapped_column(JSONList, default=list)
    questions: Mapped[list[str]] = mapped_column(JSONList, default=list)
    sentiment_scores: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    future_opportunities: Mapped[list[str]] = mapped_column(JSONList, default=list)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HookLibrary(Base):
    __tablename__ = "hook_library"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hook_type: Mapped[str] = mapped_column(String(64), nullable=False)
    example_text: Mapped[str | None] = mapped_column(Text)
    emotion: Mapped[str | None] = mapped_column(String(64))
    source_feature_id: Mapped[int | None] = mapped_column(ForeignKey("content_features.id"))
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StoryPattern(Base):
    __tablename__ = "story_patterns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern_name: Mapped[str] = mapped_column(String(128), nullable=False)
    beats: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    source_feature_id: Mapped[int | None] = mapped_column(ForeignKey("content_features.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VisualPattern(Base):
    __tablename__ = "visual_patterns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern_name: Mapped[str] = mapped_column(String(128), nullable=False)
    features: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    meme_type: Mapped[str | None] = mapped_column(String(64))
    source_feature_id: Mapped[int | None] = mapped_column(ForeignKey("content_features.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AudioPattern(Base):
    __tablename__ = "audio_patterns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern_name: Mapped[str] = mapped_column(String(128), nullable=False)
    features: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    meme_type: Mapped[str | None] = mapped_column(String(64))
    source_feature_id: Mapped[int | None] = mapped_column(ForeignKey("content_features.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmotionVector(Base):
    __tablename__ = "emotion_vectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raw_content_id: Mapped[int] = mapped_column(ForeignKey("raw_content.id"), nullable=False)
    scores: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    dominant: Mapped[str | None] = mapped_column(String(64))
    progression: Mapped[list[str]] = mapped_column(JSONList, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrendLifecycle(Base):
    __tablename__ = "trend_lifecycle"
    __table_args__ = (
        Index("idx_trend_lifecycle_stage", "stage", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern_key: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    stage: Mapped[str] = mapped_column(String(32), default="emerging")
    # emerging | growing | peak | saturated | declining | dead
    confidence: Mapped[float] = mapped_column(Numeric(5, 3), default=0)
    platforms: Mapped[list[str]] = mapped_column(JSONList, default=list)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeGraphNode(Base):
    __tablename__ = "knowledge_graph_nodes"
    __table_args__ = (
        UniqueConstraint("node_type", "label", name="uq_kg_node_type_label"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # topic | emotion | character | format | hook | audience | meme | vertical
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    properties: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeGraphEdge(Base):
    __tablename__ = "knowledge_graph_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_node_id: Mapped[int] = mapped_column(ForeignKey("knowledge_graph_nodes.id"), nullable=False)
    to_node_id: Mapped[int] = mapped_column(ForeignKey("knowledge_graph_nodes.id"), nullable=False)
    relation: Mapped[str] = mapped_column(String(64), nullable=False)
    weight: Mapped[float] = mapped_column(Numeric(6, 3), default=1.0)
    properties: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OpportunityScore(Base):
    """Ranked viral content opportunity — V2 primary output unit."""

    __tablename__ = "opportunity_scores"
    __table_args__ = (
        Index("idx_opportunity_scores_vertical", "vertical_slug", "score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vertical_slug: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    score: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    score_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    opportunity: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    lifecycle_stage: Mapped[str | None] = mapped_column(String(32))
    pattern_key: Mapped[str | None] = mapped_column(String(256))
    content_brief_ids: Mapped[list[int]] = mapped_column(JSONList, default=list)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ViralPrediction(Base):
    __tablename__ = "viral_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunity_scores.id"), nullable=False)
    content_brief_id: Mapped[int | None] = mapped_column(ForeignKey("content_briefs.id"))
    predicted_score: Mapped[float | None] = mapped_column(Numeric(6, 2))
    actual_views: Mapped[int | None] = mapped_column(Integer)
    actual_ctr: Mapped[float | None] = mapped_column(Numeric(6, 4))
    actual_watch_time_sec: Mapped[int | None] = mapped_column(Integer)
    actual_shares: Mapped[int | None] = mapped_column(Integer)
    actual_comments: Mapped[int | None] = mapped_column(Integer)
    actual_subscribers: Mapped[int | None] = mapped_column(Integer)
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CreatorProfile(Base):
    __tablename__ = "creator_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    handle: Mapped[str] = mapped_column(String(256), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(256))
    niche_tags: Mapped[list[str]] = mapped_column(JSONList, default=list)
    posting_cadence: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    is_competitor: Mapped[bool] = mapped_column(Boolean, default=False)
    is_managed: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CompetitorChannel(Base):
    __tablename__ = "competitor_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(256), nullable=False)
    name: Mapped[str | None] = mapped_column(String(256))
    vertical_slugs: Mapped[list[str]] = mapped_column(JSONList, default=list)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Probability Engine & Verification — Prediction Registry
# ---------------------------------------------------------------------------


class Prediction(Base):
    """Central registry row for any AI decision (content, trend, experiment, publish)."""

    __tablename__ = "predictions"
    __table_args__ = (
        Index("idx_predictions_brief", "content_brief_id"),
        Index("idx_predictions_subsystem", "subsystem", "created_at"),
        Index("idx_predictions_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subsystem: Mapped[str] = mapped_column(String(64), nullable=False)
    # probability_engine | trend_engine | character_engine | experiment_engine | publishing_engine
    decision_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # virality | variant_choice | publish_timing | opportunity_rank
    content_brief_id: Mapped[int | None] = mapped_column(ForeignKey("content_briefs.id"))
    video_run_id: Mapped[int | None] = mapped_column(ForeignKey("video_runs.id"))
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunity_scores.id"))
    vertical_slug: Mapped[str | None] = mapped_column(String(64))
    platform: Mapped[str | None] = mapped_column(String(32))
    model_version: Mapped[str] = mapped_column(String(64), default="rule_v1")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    # pending | verified | expired

    virality_probability: Mapped[float | None] = mapped_column(Numeric(5, 4))
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    predicted_views: Mapped[int | None] = mapped_column(Integer)
    predicted_views_low: Mapped[int | None] = mapped_column(Integer)
    predicted_views_high: Mapped[int | None] = mapped_column(Integer)
    predicted_reach: Mapped[int | None] = mapped_column(Integer)
    predicted_ctr: Mapped[float | None] = mapped_column(Numeric(6, 4))
    predicted_watch_time_sec: Mapped[float | None] = mapped_column(Numeric(8, 2))
    predicted_retention: Mapped[float | None] = mapped_column(Numeric(5, 4))
    predicted_engagement_rate: Mapped[float | None] = mapped_column(Numeric(6, 4))
    predicted_shares: Mapped[int | None] = mapped_column(Integer)
    predicted_saves: Mapped[int | None] = mapped_column(Integer)
    predicted_comments: Mapped[int | None] = mapped_column(Integer)
    predicted_followers: Mapped[int | None] = mapped_column(Integer)
    predicted_revenue_usd: Mapped[float | None] = mapped_column(Numeric(10, 2))
    predicted_roi: Mapped[float | None] = mapped_column(Numeric(8, 3))
    expected_cost_usd: Mapped[float | None] = mapped_column(Numeric(8, 4))
    final_opportunity_score: Mapped[float | None] = mapped_column(Numeric(6, 2))
    risk_score: Mapped[float | None] = mapped_column(Numeric(5, 4))

    metrics_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    reasoning_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    features: Mapped[list[PredictionFeature]] = relationship(back_populates="prediction")
    verification: Mapped[VerificationResult | None] = relationship(back_populates="prediction", uselist=False)
    errors: Mapped[list[PredictionError]] = relationship(back_populates="prediction")


class PredictionFeature(Base):
    __tablename__ = "prediction_features"
    __table_args__ = (
        Index("idx_prediction_features_pred", "prediction_id"),
        UniqueConstraint("prediction_id", "feature_name", name="uq_prediction_feature"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), nullable=False)
    feature_name: Mapped[str] = mapped_column(String(128), nullable=False)
    feature_value: Mapped[float | None] = mapped_column(Numeric(12, 6))
    feature_raw: Mapped[str | None] = mapped_column(Text)

    prediction: Mapped[Prediction] = relationship(back_populates="features")


class VerificationResult(Base):
    __tablename__ = "verification_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), unique=True, nullable=False)
    actual_views: Mapped[int | None] = mapped_column(Integer)
    actual_ctr: Mapped[float | None] = mapped_column(Numeric(6, 4))
    actual_retention: Mapped[float | None] = mapped_column(Numeric(5, 4))
    actual_watch_time_sec: Mapped[float | None] = mapped_column(Numeric(8, 2))
    actual_comments: Mapped[int | None] = mapped_column(Integer)
    actual_shares: Mapped[int | None] = mapped_column(Integer)
    actual_saves: Mapped[int | None] = mapped_column(Integer)
    actual_followers: Mapped[int | None] = mapped_column(Integer)
    actual_revenue_usd: Mapped[float | None] = mapped_column(Numeric(10, 2))
    actual_engagement_rate: Mapped[float | None] = mapped_column(Numeric(6, 4))
    metrics_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    explanation: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    mape: Mapped[float | None] = mapped_column(Numeric(8, 4))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    prediction: Mapped[Prediction] = relationship(back_populates="verification")


class PredictionError(Base):
    __tablename__ = "prediction_errors"
    __table_args__ = (
        Index("idx_prediction_errors_pred", "prediction_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), nullable=False)
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    predicted: Mapped[float | None] = mapped_column(Numeric(14, 4))
    actual: Mapped[float | None] = mapped_column(Numeric(14, 4))
    absolute_error: Mapped[float | None] = mapped_column(Numeric(14, 4))
    percentage_error: Mapped[float | None] = mapped_column(Numeric(10, 4))

    prediction: Mapped[Prediction] = relationship(back_populates="errors")


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    subsystem: Mapped[str] = mapped_column(String(64), default="probability_engine")
    weights: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    calibration: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PredictionLesson(Base):
    """Root-cause / lessons-learned rows feeding the learning engine."""

    __tablename__ = "prediction_lessons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), nullable=False)
    primary_cause: Mapped[str | None] = mapped_column(Text)
    secondary_causes: Mapped[list[str]] = mapped_column(JSONList, default=list)
    suggested_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    lesson: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

