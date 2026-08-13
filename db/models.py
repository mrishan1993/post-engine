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


# ---------------------------------------------------------------------------
# Asset & Character Management Engine (AMP)
# Identity ≠ Representation; provider-agnostic creative entities
# ---------------------------------------------------------------------------


class Universe(Base):
    __tablename__ = "universes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    rules: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Character(Base):
    __tablename__ = "characters"
    __table_args__ = (Index("idx_characters_status", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    universe_id: Mapped[str | None] = mapped_column(ForeignKey("universes.id"))
    canonical_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    # draft | approved | active | deprecated | archived
    tags: Mapped[list[str]] = mapped_column(JSONList, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CharacterVersion(Base):
    __tablename__ = "character_versions"
    __table_args__ = (UniqueConstraint("character_id", "version", name="uq_character_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    canonical_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    change_log: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VoiceProfile(Base):
    """Voice identity separate from TTS provider mapping."""

    __tablename__ = "voice_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    characteristics: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    provider_mappings: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CreativeStyle(Base):
    __tablename__ = "creative_styles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Asset(Base):
    """Provider-agnostic asset registry — identity ≠ which generator made it."""

    __tablename__ = "assets"
    __table_args__ = (
        Index("idx_assets_type_status", "asset_type", "status"),
        Index("idx_assets_name", "name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    asset_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # character_reference | face_reference | location | prop | style_ref |
    # voice_sample | music | sfx | motion_reference | generation_reference | other
    name: Mapped[str | None] = mapped_column(String(256))
    storage_uri: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(String(128))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # embedding stored as JSON list until pgvector migration (Phase 3)
    embedding: Mapped[list[float] | None] = mapped_column(JSON)
    tags: Mapped[list[str]] = mapped_column(JSONList, default=list)
    provider: Mapped[str | None] = mapped_column(String(128))
    provider_asset_id: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"))
    quality: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    owner: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AssetRelationship(Base):
    __tablename__ = "asset_relationships"
    __table_args__ = (
        Index("idx_asset_rel_source", "source_id", "relationship_type"),
        Index("idx_asset_rel_target", "target_id", "relationship_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # character | asset | universe | style | voice | scene
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # has_voice | has_reference | belongs_to_universe | contains_character |
    # contains_prop | knows_character | uses_style | ...
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Scene(Base):
    __tablename__ = "scenes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    story_id: Mapped[str | None] = mapped_column(String(36))
    sequence_number: Mapped[int | None] = mapped_column(Integer)
    scene_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CreativeConfiguration(Base):
    """Composable scene config — does not mutate character identity."""

    __tablename__ = "creative_configurations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(256))
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AssetPack(Base):
    __tablename__ = "asset_packs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner_type: Mapped[str | None] = mapped_column(String(64))
    # character | universe | vertical | campaign
    owner_id: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(32), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AssetPackMember(Base):
    __tablename__ = "asset_pack_members"
    __table_args__ = (UniqueConstraint("pack_id", "asset_id", name="uq_pack_asset"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    pack_id: Mapped[str] = mapped_column(ForeignKey("asset_packs.id"), nullable=False)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), nullable=False)
    role: Mapped[str | None] = mapped_column(String(64))
    # face_reference | full_body | voice | expression | clothing | prompt_rules


class CharacterMemory(Base):
    __tablename__ = "character_memory"
    __table_args__ = (Index("idx_character_memory_char", "character_id", "episode_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id"), nullable=False)
    episode_key: Mapped[str] = mapped_column(String(128), nullable=False)
    memory_text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UniverseMemory(Base):
    __tablename__ = "universe_memory"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    universe_id: Mapped[str] = mapped_column(ForeignKey("universes.id"), nullable=False)
    memory_key: Mapped[str] = mapped_column(String(128), nullable=False)
    memory_text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AssetPerformance(Base):
    """Attribution rollup — asset → posts → metrics (Phase 6)."""

    __tablename__ = "asset_performance"
    __table_args__ = (Index("idx_asset_perf", "asset_id", "updated_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), nullable=False)
    character_id: Mapped[str | None] = mapped_column(ForeignKey("characters.id"))
    posts_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_views: Mapped[float | None] = mapped_column(Numeric(14, 2))
    avg_retention: Mapped[float | None] = mapped_column(Numeric(6, 4))
    total_views: Mapped[int] = mapped_column(Integer, default=0)
    metrics_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Story Engine — narrative blueprints (not video/prose generation)
# ---------------------------------------------------------------------------


class Story(Base):
    __tablename__ = "stories"
    __table_args__ = (Index("idx_stories_status", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str | None] = mapped_column(String(256))
    logline: Mapped[str | None] = mapped_column(Text)
    story_type: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="draft")
    # draft | scored | approved | rejected | in_production
    target_duration_sec: Mapped[int | None] = mapped_column(Integer)
    blueprint: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    quality_score: Mapped[float | None] = mapped_column(Numeric(5, 4))
    originality_score: Mapped[float | None] = mapped_column(Numeric(5, 4))
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    opportunity_id: Mapped[int | None] = mapped_column(Integer)
    content_brief_id: Mapped[int | None] = mapped_column(ForeignKey("content_briefs.id"))
    character_ids: Mapped[list[str]] = mapped_column(JSONList, default=list)
    platform: Mapped[str | None] = mapped_column(String(64))
    prediction_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StoryVersion(Base):
    __tablename__ = "story_versions"
    __table_args__ = (UniqueConstraint("story_id", "version", name="uq_story_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    blueprint: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    critic_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    quality_score: Mapped[float | None] = mapped_column(Numeric(5, 4))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NarrativePattern(Base):
    """Reusable narrative structures owned by Story Engine (distinct from Trend V2 story_patterns)."""

    __tablename__ = "narrative_patterns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    pattern_type: Mapped[str | None] = mapped_column(String(64))
    structure: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(JSON)
    performance_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StoryPerformance(Base):
    __tablename__ = "story_performance"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id"), nullable=False)
    post_id: Mapped[str | None] = mapped_column(String(36))
    video_run_id: Mapped[int | None] = mapped_column(ForeignKey("video_runs.id"))
    views: Mapped[int | None] = mapped_column(Integer)
    retention: Mapped[float | None] = mapped_column(Numeric(8, 4))
    engagement_rate: Mapped[float | None] = mapped_column(Numeric(8, 4))
    share_rate: Mapped[float | None] = mapped_column(Numeric(8, 4))
    comment_rate: Mapped[float | None] = mapped_column(Numeric(8, 4))
    follower_conversion: Mapped[float | None] = mapped_column(Numeric(8, 4))
    component_scores: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Storyboard Engine — visual/audio specs (not generation / prompts)
# ---------------------------------------------------------------------------


class Storyboard(Base):
    __tablename__ = "storyboards"
    __table_args__ = (
        UniqueConstraint("story_id", "version", name="uq_storyboard_story_version"),
        Index("idx_storyboards_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    platform: Mapped[str | None] = mapped_column(String(64))
    duration_sec: Mapped[float | None] = mapped_column(Numeric(8, 3))
    global_direction: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    quality_score: Mapped[float | None] = mapped_column(Numeric(5, 4))
    status: Mapped[str] = mapped_column(String(32), default="draft")
    # draft | scored | approved | rejected
    critic_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    prediction_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    story_version: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StoryboardScene(Base):
    __tablename__ = "storyboard_scenes"
    __table_args__ = (Index("idx_storyboard_scenes_board", "storyboard_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    storyboard_id: Mapped[str] = mapped_column(ForeignKey("storyboards.id"), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time_sec: Mapped[float | None] = mapped_column(Numeric(8, 3))
    end_time_sec: Mapped[float | None] = mapped_column(Numeric(8, 3))
    narrative_function: Mapped[str | None] = mapped_column(String(64))
    emotional_state: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    scene_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StoryboardShot(Base):
    __tablename__ = "storyboard_shots"
    __table_args__ = (Index("idx_storyboard_shots_scene", "scene_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("storyboard_scenes.id"), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time_sec: Mapped[float | None] = mapped_column(Numeric(8, 3))
    end_time_sec: Mapped[float | None] = mapped_column(Numeric(8, 3))
    shot_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    generation_config: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StoryboardAsset(Base):
    __tablename__ = "storyboard_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    storyboard_id: Mapped[str] = mapped_column(ForeignKey("storyboards.id"), nullable=False)
    shot_id: Mapped[str | None] = mapped_column(ForeignKey("storyboard_shots.id"))
    asset_id: Mapped[str | None] = mapped_column(String(36))
    asset_role: Mapped[str | None] = mapped_column(String(64))
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Prompt Engine — CGS + provider packages (never generates media)
# ---------------------------------------------------------------------------


class PromptSpec(Base):
    __tablename__ = "prompt_specs"
    __table_args__ = (Index("idx_prompt_specs_modality", "modality"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    modality: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_spec: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    storyboard_id: Mapped[str | None] = mapped_column(ForeignKey("storyboards.id"))
    storyboard_shot_id: Mapped[str | None] = mapped_column(String(64))
    story_id: Mapped[str | None] = mapped_column(ForeignKey("stories.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PromptPackage(Base):
    __tablename__ = "prompt_packages"
    __table_args__ = (Index("idx_prompt_packages_provider", "provider"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    prompt_spec_id: Mapped[str | None] = mapped_column(ForeignKey("prompt_specs.id"))
    provider: Mapped[str | None] = mapped_column(String(128))
    model: Mapped[str | None] = mapped_column(String(128))
    modality: Mapped[str | None] = mapped_column(String(32))
    provider_prompt: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    quality_score: Mapped[float | None] = mapped_column(Numeric(5, 4))
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(12, 6))
    estimated_latency_sec: Mapped[float | None] = mapped_column(Numeric(10, 3))
    validation_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    critic_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    lineage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="compiled")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PromptComponent(Base):
    __tablename__ = "prompt_components"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    component_type: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    performance_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PromptExperiment(Base):
    __tablename__ = "prompt_experiments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    storyboard_shot_id: Mapped[str | None] = mapped_column(String(64))
    variants: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    selected_variant: Mapped[str | None] = mapped_column(String(36))
    results: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Generation Engine — execute PromptPackages → media artifacts
# ---------------------------------------------------------------------------


class GenerationRequest(Base):
    __tablename__ = "generation_requests"
    __table_args__ = (Index("idx_generation_requests_status", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    content_id: Mapped[str | None] = mapped_column(String(36))
    storyboard_id: Mapped[str | None] = mapped_column(ForeignKey("storyboards.id"))
    storyboard_shot_id: Mapped[str | None] = mapped_column(String(64))
    prompt_package_id: Mapped[str | None] = mapped_column(ForeignKey("prompt_packages.id"))
    modality: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_variants: Mapped[int] = mapped_column(Integer, default=1)
    priority: Mapped[str] = mapped_column(String(32), default="normal")
    budget: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    provider_strategy: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    quality: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    profile: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    lineage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GenerationJob(Base):
    __tablename__ = "generation_jobs"
    __table_args__ = (Index("idx_generation_jobs_status", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("generation_requests.id"), nullable=False)
    variant_number: Mapped[int] = mapped_column(Integer, default=1)
    provider: Mapped[str | None] = mapped_column(String(128))
    model: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    provider_job_id: Mapped[str | None] = mapped_column(String(256))
    prompt_package_id: Mapped[str | None] = mapped_column(ForeignKey("prompt_packages.id"))
    seed: Mapped[int | None] = mapped_column(Integer)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    fallback_count: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(12, 6))
    actual_cost: Mapped[float | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    latency: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    depends_on: Mapped[list[str]] = mapped_column(JSONList, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MediaArtifact(Base):
    __tablename__ = "media_artifacts"
    __table_args__ = (Index("idx_media_artifacts_job", "generation_job_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    generation_job_id: Mapped[str] = mapped_column(ForeignKey("generation_jobs.id"), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_uri: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(String(128))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    sha256: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    prompt_package_id: Mapped[str | None] = mapped_column(ForeignKey("prompt_packages.id"))
    provider: Mapped[str | None] = mapped_column(String(128))
    model: Mapped[str | None] = mapped_column(String(128))
    technical_qa: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    lineage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProviderPerformance(Base):
    __tablename__ = "provider_performance"
    __table_args__ = (
        UniqueConstraint("provider", "model", "modality", name="uq_provider_perf"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128))
    modality: Mapped[str] = mapped_column(String(32), nullable=False)
    success_rate: Mapped[float | None] = mapped_column(Numeric(8, 4))
    avg_latency_ms: Mapped[int | None] = mapped_column(Integer)
    avg_cost: Mapped[float | None] = mapped_column(Numeric(12, 6))
    avg_qa_score: Mapped[float | None] = mapped_column(Numeric(8, 4))
    fallback_rate: Mapped[float | None] = mapped_column(Numeric(8, 4))
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProviderReference(Base):
    """Maps internal assets to provider-side reference IDs."""

    __tablename__ = "provider_references"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    internal_asset_id: Mapped[str] = mapped_column(String(36), nullable=False)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_asset_id: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Video Generation Engine — specialized video path (PromptPackage → clip)
# ---------------------------------------------------------------------------


class VideoGenerationRequest(Base):
    __tablename__ = "video_generation_requests"
    __table_args__ = (
        Index("idx_video_gen_requests_status", "status"),
        UniqueConstraint("idempotency_key", name="uq_video_gen_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    storyboard_shot_id: Mapped[str | None] = mapped_column(String(64))
    storyboard_id: Mapped[str | None] = mapped_column(ForeignKey("storyboards.id"))
    prompt_package_id: Mapped[str] = mapped_column(ForeignKey("prompt_packages.id"), nullable=False)
    provider_strategy: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    variant_count: Mapped[int] = mapped_column(Integer, default=1)
    budget: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    quality: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    priority: Mapped[str] = mapped_column(String(32), default="normal")
    status: Mapped[str] = mapped_column(String(32), default="queued")
    idempotency_key: Mapped[str | None] = mapped_column(String(256))
    video_prompt_package: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    duration_strategy: Mapped[str] = mapped_column(String(32), default="nearest")
    continuity: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    lineage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VideoGenerationJob(Base):
    __tablename__ = "video_generation_jobs"
    __table_args__ = (Index("idx_video_gen_jobs_status", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str] = mapped_column(
        ForeignKey("video_generation_requests.id"), nullable=False
    )
    variant_number: Mapped[int] = mapped_column(Integer, default=1)
    provider: Mapped[str | None] = mapped_column(String(128))
    model: Mapped[str | None] = mapped_column(String(128))
    provider_job_id: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    fallback_count: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(12, 6))
    actual_cost: Mapped[float | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    generation_parameters: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    seed: Mapped[int | None] = mapped_column(Integer)
    prompt_package_id: Mapped[str | None] = mapped_column(ForeignKey("prompt_packages.id"))
    depends_on: Mapped[list[str]] = mapped_column(JSONList, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VideoArtifact(Base):
    __tablename__ = "video_artifacts"
    __table_args__ = (Index("idx_video_artifacts_job", "generation_job_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    generation_job_id: Mapped[str] = mapped_column(
        ForeignKey("video_generation_jobs.id"), nullable=False
    )
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_sec: Mapped[float | None] = mapped_column(Numeric(8, 3))
    fps: Mapped[float | None] = mapped_column(Numeric(8, 3))
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))
    technical_qa: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    provider: Mapped[str | None] = mapped_column(String(128))
    model: Mapped[str | None] = mapped_column(String(128))
    prompt_package_id: Mapped[str | None] = mapped_column(ForeignKey("prompt_packages.id"))
    lineage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Image Generation Engine — keyframes, refs, thumbnails, edits
# ---------------------------------------------------------------------------


class ImageGenerationRequest(Base):
    __tablename__ = "image_generation_requests"
    __table_args__ = (
        Index("idx_image_gen_requests_status", "status"),
        UniqueConstraint("idempotency_key", name="uq_image_gen_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    purpose: Mapped[str | None] = mapped_column(String(64))
    storyboard_shot_id: Mapped[str | None] = mapped_column(String(64))
    storyboard_id: Mapped[str | None] = mapped_column(ForeignKey("storyboards.id"))
    prompt_package_id: Mapped[str] = mapped_column(ForeignKey("prompt_packages.id"), nullable=False)
    provider_strategy: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    variant_count: Mapped[int] = mapped_column(Integer, default=1)
    budget: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    quality: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    priority: Mapped[str] = mapped_column(String(32), default="normal")
    status: Mapped[str] = mapped_column(String(32), default="queued")
    idempotency_key: Mapped[str | None] = mapped_column(String(256))
    image_prompt_package: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    lineage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImageGenerationJob(Base):
    __tablename__ = "image_generation_jobs"
    __table_args__ = (Index("idx_image_gen_jobs_status", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str] = mapped_column(
        ForeignKey("image_generation_requests.id"), nullable=False
    )
    variant_number: Mapped[int] = mapped_column(Integer, default=1)
    provider: Mapped[str | None] = mapped_column(String(128))
    model: Mapped[str | None] = mapped_column(String(128))
    provider_job_id: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    fallback_count: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(12, 6))
    actual_cost: Mapped[float | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    seed: Mapped[int | None] = mapped_column(Integer)
    prompt_package_id: Mapped[str | None] = mapped_column(ForeignKey("prompt_packages.id"))
    parent_artifact_id: Mapped[str | None] = mapped_column(String(36))
    depends_on: Mapped[list[str]] = mapped_column(JSONList, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImageArtifact(Base):
    __tablename__ = "image_artifacts"
    __table_args__ = (Index("idx_image_artifacts_job", "generation_job_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    generation_job_id: Mapped[str] = mapped_column(
        ForeignKey("image_generation_jobs.id"), nullable=False
    )
    parent_artifact_id: Mapped[str | None] = mapped_column(ForeignKey("image_artifacts.id"))
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))
    phash: Mapped[str | None] = mapped_column(String(128))
    technical_qa: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    provider: Mapped[str | None] = mapped_column(String(128))
    model: Mapped[str | None] = mapped_column(String(128))
    prompt_package_id: Mapped[str | None] = mapped_column(ForeignKey("prompt_packages.id"))
    purpose: Mapped[str | None] = mapped_column(String(64))
    lineage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Music & SFX Engine — blueprint, music, SFX, audio timeline
# ---------------------------------------------------------------------------


class MusicGenerationRequest(Base):
    __tablename__ = "music_generation_requests"
    __table_args__ = (
        Index("idx_music_gen_requests_status", "status"),
        UniqueConstraint("idempotency_key", name="uq_music_gen_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    content_id: Mapped[str | None] = mapped_column(String(64))
    story_id: Mapped[str | None] = mapped_column(ForeignKey("stories.id"))
    storyboard_id: Mapped[str | None] = mapped_column(ForeignKey("storyboards.id"))
    prompt_package_id: Mapped[str | None] = mapped_column(ForeignKey("prompt_packages.id"))
    audio_blueprint: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    music_spec: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    provider_strategy: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    variant_count: Mapped[int] = mapped_column(Integer, default=1)
    budget: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    quality: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    priority: Mapped[str] = mapped_column(String(32), default="normal")
    status: Mapped[str] = mapped_column(String(32), default="queued")
    idempotency_key: Mapped[str | None] = mapped_column(String(256))
    lineage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MusicGenerationJob(Base):
    __tablename__ = "music_generation_jobs"
    __table_args__ = (Index("idx_music_gen_jobs_status", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str] = mapped_column(
        ForeignKey("music_generation_requests.id"), nullable=False
    )
    variant_number: Mapped[int] = mapped_column(Integer, default=1)
    provider: Mapped[str | None] = mapped_column(String(128))
    model: Mapped[str | None] = mapped_column(String(128))
    provider_job_id: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    fallback_count: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(12, 6))
    actual_cost: Mapped[float | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    seed: Mapped[int | None] = mapped_column(Integer)
    prompt_package_id: Mapped[str | None] = mapped_column(ForeignKey("prompt_packages.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AudioArtifact(Base):
    __tablename__ = "audio_artifacts"
    __table_args__ = (Index("idx_audio_artifacts_job", "generation_job_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    generation_job_id: Mapped[str | None] = mapped_column(ForeignKey("music_generation_jobs.id"))
    artifact_type: Mapped[str] = mapped_column(String(32), default="music")
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128))
    duration_sec: Mapped[float | None] = mapped_column(Numeric(8, 3))
    sample_rate: Mapped[int | None] = mapped_column(Integer)
    channels: Mapped[int | None] = mapped_column(Integer)
    loudness_lufs: Mapped[float | None] = mapped_column(Numeric(8, 3))
    true_peak_db: Mapped[float | None] = mapped_column(Numeric(8, 3))
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))
    technical_qa: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    provider: Mapped[str | None] = mapped_column(String(128))
    model: Mapped[str | None] = mapped_column(String(128))
    prompt_package_id: Mapped[str | None] = mapped_column(ForeignKey("prompt_packages.id"))
    sfx_library_id: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON)
    lineage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SfxLibraryAsset(Base):
    __tablename__ = "sfx_library_assets"
    __table_args__ = (Index("idx_sfx_library_category", "category"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    subtype: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    duration_sec: Mapped[float] = mapped_column(Numeric(8, 3), default=1.0)
    intensity: Mapped[float] = mapped_column(Numeric(4, 3), default=0.7)
    tags: Mapped[list[str]] = mapped_column(JSONList, default=list)
    storage_uri: Mapped[str | None] = mapped_column(Text)
    licensed: Mapped[bool] = mapped_column(Boolean, default=True)
    reuse_count: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AudioTimelineRow(Base):
    __tablename__ = "audio_timelines"
    __table_args__ = (Index("idx_audio_timelines_storyboard", "storyboard_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    storyboard_id: Mapped[str | None] = mapped_column(ForeignKey("storyboards.id"))
    music_request_id: Mapped[str | None] = mapped_column(ForeignKey("music_generation_requests.id"))
    duration_sec: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False)
    tracks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    beat_grid: Mapped[list[float] | None] = mapped_column(JSON)
    voice_windows: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    ducking: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    loudness_profile: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="ready")
    lineage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Voice Generation Engine — dialogue/narration performance (not script)
# ---------------------------------------------------------------------------


class VoiceGenerationRequest(Base):
    __tablename__ = "voice_generation_requests"
    __table_args__ = (
        Index("idx_voice_gen_requests_status", "status"),
        UniqueConstraint("idempotency_key", name="uq_voice_gen_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    content_id: Mapped[str | None] = mapped_column(String(64))
    story_id: Mapped[str | None] = mapped_column(ForeignKey("stories.id"))
    storyboard_id: Mapped[str | None] = mapped_column(ForeignKey("storyboards.id"))
    character_id: Mapped[str | None] = mapped_column(ForeignKey("characters.id"))
    voice_profile_id: Mapped[str | None] = mapped_column(ForeignKey("voice_profiles.id"))
    prompt_package_id: Mapped[str | None] = mapped_column(ForeignKey("prompt_packages.id"))
    script: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    voice_spec: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    provider_strategy: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    variant_count: Mapped[int] = mapped_column(Integer, default=1)
    budget: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    quality: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    priority: Mapped[str] = mapped_column(String(32), default="normal")
    status: Mapped[str] = mapped_column(String(32), default="queued")
    idempotency_key: Mapped[str | None] = mapped_column(String(256))
    lineage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VoiceGenerationJob(Base):
    __tablename__ = "voice_generation_jobs"
    __table_args__ = (Index("idx_voice_gen_jobs_status", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str] = mapped_column(
        ForeignKey("voice_generation_requests.id"), nullable=False
    )
    variant_number: Mapped[int] = mapped_column(Integer, default=1)
    provider: Mapped[str | None] = mapped_column(String(128))
    model: Mapped[str | None] = mapped_column(String(128))
    provider_job_id: Mapped[str | None] = mapped_column(String(256))
    provider_voice_id: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    fallback_count: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(12, 6))
    actual_cost: Mapped[float | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    seed: Mapped[int | None] = mapped_column(Integer)
    prompt_package_id: Mapped[str | None] = mapped_column(ForeignKey("prompt_packages.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VoiceArtifact(Base):
    __tablename__ = "voice_artifacts"
    __table_args__ = (Index("idx_voice_artifacts_job", "generation_job_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    generation_job_id: Mapped[str] = mapped_column(
        ForeignKey("voice_generation_jobs.id"), nullable=False
    )
    parent_artifact_id: Mapped[str | None] = mapped_column(ForeignKey("voice_artifacts.id"))
    character_id: Mapped[str | None] = mapped_column(ForeignKey("characters.id"))
    voice_profile_id: Mapped[str | None] = mapped_column(ForeignKey("voice_profiles.id"))
    artifact_type: Mapped[str] = mapped_column(String(32), default="dialogue")
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128))
    duration_sec: Mapped[float | None] = mapped_column(Numeric(8, 3))
    sample_rate: Mapped[int | None] = mapped_column(Integer)
    channels: Mapped[int | None] = mapped_column(Integer)
    loudness_lufs: Mapped[float | None] = mapped_column(Numeric(8, 3))
    true_peak_db: Mapped[float | None] = mapped_column(Numeric(8, 3))
    script_hash: Mapped[str | None] = mapped_column(String(64))
    timestamps: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))
    technical_qa: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    provider: Mapped[str | None] = mapped_column(String(128))
    model: Mapped[str | None] = mapped_column(String(128))
    prompt_package_id: Mapped[str | None] = mapped_column(ForeignKey("prompt_packages.id"))
    lineage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VoiceTimelineRow(Base):
    __tablename__ = "voice_timelines"
    __table_args__ = (Index("idx_voice_timelines_storyboard", "storyboard_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    storyboard_id: Mapped[str | None] = mapped_column(ForeignKey("storyboards.id"))
    duration_sec: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False)
    segments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ready")
    lineage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PronunciationEntry(Base):
    __tablename__ = "pronunciation_entries"
    __table_args__ = (UniqueConstraint("term", "language", name="uq_pronunciation_term_lang"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    term: Mapped[str] = mapped_column(String(256), nullable=False)
    language: Mapped[str] = mapped_column(String(32), default="en")
    pronunciation: Mapped[str | None] = mapped_column(String(512))
    phoneme: Mapped[str | None] = mapped_column(String(512))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Assembly Engine — timeline + FFmpeg render → final reel
# ---------------------------------------------------------------------------


class Assembly(Base):
    __tablename__ = "assemblies"
    __table_args__ = (
        UniqueConstraint("content_id", "version", name="uq_assembly_content_version"),
        Index("idx_assemblies_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    content_id: Mapped[str] = mapped_column(String(64), nullable=False)
    storyboard_id: Mapped[str | None] = mapped_column(ForeignKey("storyboards.id"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    specification: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    timeline: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    duration_sec: Mapped[float | None] = mapped_column(Numeric(8, 3))
    status: Mapped[str] = mapped_column(String(32), default="draft")
    # draft | validated | rendering | completed | failed
    platform_profile: Mapped[str | None] = mapped_column(String(128))
    lineage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RenderJob(Base):
    __tablename__ = "render_jobs"
    __table_args__ = (Index("idx_render_jobs_status", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    assembly_id: Mapped[str] = mapped_column(ForeignKey("assemblies.id"), nullable=False)
    render_profile: Mapped[str] = mapped_column(String(128), default="instagram_reels_v1")
    quality: Mapped[str] = mapped_column(String(32), default="final")  # draft|preview|final
    status: Mapped[str] = mapped_column(String(32), default="queued")
    progress: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    ffmpeg_version: Mapped[str | None] = mapped_column(String(64))
    ffmpeg_used: Mapped[bool] = mapped_column(Boolean, default=False)
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RenderedArtifact(Base):
    __tablename__ = "rendered_artifacts"
    __table_args__ = (Index("idx_rendered_artifacts_render", "render_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    render_id: Mapped[str] = mapped_column(ForeignKey("render_jobs.id"), nullable=False)
    assembly_id: Mapped[str | None] = mapped_column(ForeignKey("assemblies.id"))
    artifact_type: Mapped[str] = mapped_column(String(32), default="final_video")
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    fps: Mapped[float | None] = mapped_column(Numeric(8, 3))
    duration_sec: Mapped[float | None] = mapped_column(Numeric(8, 3))
    video_codec: Mapped[str | None] = mapped_column(String(64))
    audio_codec: Mapped[str | None] = mapped_column(String(64))
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))
    technical_qa: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    render_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    lineage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Publishing Engine — QA-gated multi-platform publish + receipts
# ---------------------------------------------------------------------------


class SocialAccount(Base):
    __tablename__ = "social_accounts"
    __table_args__ = (
        UniqueConstraint("platform", "external_account_id", name="uq_social_platform_external"),
        Index("idx_social_accounts_platform", "platform"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    external_account_id: Mapped[str] = mapped_column(String(256), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(256))
    username: Mapped[str | None] = mapped_column(String(256))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    status: Mapped[str] = mapped_column(String(32), default="connected")
    # connected | disconnected | error | pending
    token_status: Mapped[str] = mapped_column(String(32), default="active")
    # active | expired | refresh_required | revoked
    permissions: Mapped[list[str]] = mapped_column(JSONList, default=list)
    capabilities: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    default_settings: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    character_slug: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SocialCredential(Base):
    __tablename__ = "social_credentials"
    __table_args__ = (Index("idx_social_credentials_account", "social_account_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    social_account_id: Mapped[str] = mapped_column(ForeignKey("social_accounts.id"), nullable=False)
    # Opaque reference into encrypted secret store — never plaintext tokens
    credential_reference: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[list[str]] = mapped_column(JSONList, default=list)
    status: Mapped[str] = mapped_column(String(32), default="active")
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refresh_status: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PublishingPlan(Base):
    __tablename__ = "publishing_plans"
    __table_args__ = (
        Index("idx_publishing_plans_status", "status"),
        Index("idx_publishing_plans_content", "content_id"),
        UniqueConstraint("idempotency_key", name="uq_publishing_plan_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    content_id: Mapped[str] = mapped_column(String(64), nullable=False)
    assembly_id: Mapped[str | None] = mapped_column(ForeignKey("assemblies.id"))
    master_artifact_id: Mapped[str | None] = mapped_column(String(36))
    cover_artifact_id: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(32), default="draft")
    # draft | approved | scheduled | publishing | completed | partial | failed | cancelled
    schedule: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    approval: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    policy: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    platforms: Mapped[list[dict[str, Any]]] = mapped_column(JSONList, default=list)
    lineage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PublishingJob(Base):
    __tablename__ = "publishing_jobs"
    __table_args__ = (
        Index("idx_publishing_jobs_status", "status"),
        Index("idx_publishing_jobs_plan", "publishing_plan_id"),
        UniqueConstraint("idempotency_key", name="uq_publishing_job_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    publishing_plan_id: Mapped[str] = mapped_column(ForeignKey("publishing_plans.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    social_account_id: Mapped[str] = mapped_column(ForeignKey("social_accounts.id"), nullable=False)
    platform_package: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    external_media_id: Mapped[str | None] = mapped_column(String(256))
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PublicationReceipt(Base):
    __tablename__ = "publication_receipts"
    __table_args__ = (
        Index("idx_publication_receipts_job", "publishing_job_id"),
        UniqueConstraint(
            "platform", "external_post_id", name="uq_publication_platform_external_post"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    publishing_job_id: Mapped[str] = mapped_column(ForeignKey("publishing_jobs.id"), nullable=False)
    publishing_plan_id: Mapped[str | None] = mapped_column(ForeignKey("publishing_plans.id"))
    content_id: Mapped[str | None] = mapped_column(String(64))
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    social_account_id: Mapped[str | None] = mapped_column(ForeignKey("social_accounts.id"))
    external_post_id: Mapped[str | None] = mapped_column(String(256))
    external_media_id: Mapped[str | None] = mapped_column(String(256))
    post_url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_status: Mapped[str] = mapped_column(String(32), default="pending")
    # pending | verified | failed
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    lineage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Bridge to legacy publications table when present
    legacy_publication_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# QA Engine — multi-dimension gatekeeper before publishing
# ---------------------------------------------------------------------------


class QaRun(Base):
    __tablename__ = "qa_runs"
    __table_args__ = (
        Index("idx_qa_runs_status", "status"),
        Index("idx_qa_runs_content", "content_id"),
        UniqueConstraint("content_id", "version", name="uq_qa_content_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    content_id: Mapped[str] = mapped_column(String(64), nullable=False)
    assembly_id: Mapped[str | None] = mapped_column(ForeignKey("assemblies.id"))
    artifact_id: Mapped[str | None] = mapped_column(String(36))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    # queued | running | completed | failed | review_required
    decision: Mapped[str | None] = mapped_column(String(32))
    # pass | repair | regenerate | block | review_required
    overall_score: Mapped[float | None] = mapped_column(Numeric(5, 4))
    dimension_scores: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    human_review: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    lineage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    thresholds: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QaIssue(Base):
    __tablename__ = "qa_issues"
    __table_args__ = (Index("idx_qa_issues_run", "qa_run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    qa_run_id: Mapped[str] = mapped_column(ForeignKey("qa_runs.id"), nullable=False)
    issue_code: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), default="medium")
    category: Mapped[str | None] = mapped_column(String(64))
    artifact_id: Mapped[str | None] = mapped_column(String(36))
    scene_id: Mapped[str | None] = mapped_column(String(64))
    timestamp_sec: Mapped[float | None] = mapped_column(Numeric(10, 3))
    score: Mapped[float | None] = mapped_column(Numeric(5, 4))
    description: Mapped[str | None] = mapped_column(Text)
    owner_engine: Mapped[str | None] = mapped_column(String(128))
    recommended_action: Mapped[str | None] = mapped_column(String(64))
    # none | repair | regenerate | block | review
    status: Mapped[str] = mapped_column(String(32), default="open")
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class QaMeasurement(Base):
    __tablename__ = "qa_measurements"
    __table_args__ = (Index("idx_qa_measurements_run", "qa_run_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    qa_run_id: Mapped[str] = mapped_column(ForeignKey("qa_runs.id"), nullable=False)
    dimension: Mapped[str] = mapped_column(String(64), nullable=False)
    metric: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[float | None] = mapped_column(Numeric(12, 4))
    threshold: Mapped[float | None] = mapped_column(Numeric(12, 4))
    passed: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Performance & Analytics Engine — actuals after publication
# ---------------------------------------------------------------------------


class AnalyticsCollectionJob(Base):
    __tablename__ = "analytics_collection_jobs"
    __table_args__ = (
        Index("idx_analytics_jobs_status", "status"),
        Index("idx_analytics_jobs_publication", "publication_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    publication_id: Mapped[str] = mapped_column(
        ForeignKey("publication_receipts.id"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active")
    # active | paused | completed | failed
    poll_tier: Mapped[str] = mapped_column(String(32), default="high")
    # high | medium | low | archival
    next_collect_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snapshot_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    lineage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlatformMetricResponse(Base):
    __tablename__ = "platform_metric_responses"
    __table_args__ = (Index("idx_platform_metric_responses_pub", "publication_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    publication_id: Mapped[str | None] = mapped_column(ForeignKey("publication_receipts.id"))
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint: Mapped[str | None] = mapped_column(String(256))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    response: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PerformanceSnapshot(Base):
    __tablename__ = "performance_snapshots"
    __table_args__ = (
        Index("idx_perf_snapshots_pub_captured", "publication_id", "captured_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    publication_id: Mapped[str] = mapped_column(
        ForeignKey("publication_receipts.id"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    account_id: Mapped[str | None] = mapped_column(String(36))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    age_since_publish_sec: Mapped[int | None] = mapped_column(Integer)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    derived: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    raw_response_id: Mapped[str | None] = mapped_column(ForeignKey("platform_metric_responses.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PerformanceTimeseries(Base):
    __tablename__ = "performance_timeseries"
    __table_args__ = (
        Index("idx_perf_ts_pub_metric", "publication_id", "metric", "timestamp"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    publication_id: Mapped[str] = mapped_column(
        ForeignKey("publication_receipts.id"), nullable=False
    )
    metric: Mapped[str] = mapped_column(String(128), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[float | None] = mapped_column(Numeric(18, 4))
    source: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PostAnalytics(Base):
    __tablename__ = "post_analytics"

    publication_id: Mapped[str] = mapped_column(
        ForeignKey("publication_receipts.id"), primary_key=True
    )
    content_id: Mapped[str | None] = mapped_column(String(64))
    prediction_id: Mapped[str | None] = mapped_column(String(64))
    platform: Mapped[str | None] = mapped_column(String(64))
    current_views: Mapped[int | None] = mapped_column(Integer)
    current_likes: Mapped[int | None] = mapped_column(Integer)
    current_comments: Mapped[int | None] = mapped_column(Integer)
    current_shares: Mapped[int | None] = mapped_column(Integer)
    current_saves: Mapped[int | None] = mapped_column(Integer)
    current_reach: Mapped[int | None] = mapped_column(Integer)
    followers_gained: Mapped[int | None] = mapped_column(Integer)
    engagement_rate: Mapped[float | None] = mapped_column(Numeric(10, 6))
    share_rate: Mapped[float | None] = mapped_column(Numeric(10, 6))
    save_rate: Mapped[float | None] = mapped_column(Numeric(10, 6))
    completion_rate: Mapped[float | None] = mapped_column(Numeric(10, 6))
    weighted_engagement: Mapped[float | None] = mapped_column(Numeric(10, 6))
    virality_score: Mapped[float | None] = mapped_column(Numeric(10, 6))
    performance_index: Mapped[float | None] = mapped_column(Numeric(10, 6))
    percentile_rank: Mapped[float | None] = mapped_column(Numeric(10, 6))
    view_velocity_per_hour: Mapped[float | None] = mapped_column(Numeric(18, 4))
    share_velocity_per_hour: Mapped[float | None] = mapped_column(Numeric(18, 4))
    acceleration: Mapped[float | None] = mapped_column(Numeric(18, 4))
    viral_state: Mapped[str] = mapped_column(String(32), default="normal")
    content_fingerprint: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    performance_vector: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    first_hour: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    prediction_link: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    engagement_formula_version: Mapped[str] = mapped_column(String(32), default="v1")
    virality_model_version: Mapped[str] = mapped_column(String(32), default="v1")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RetentionCurve(Base):
    __tablename__ = "retention_curves"
    __table_args__ = (Index("idx_retention_curves_pub", "publication_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    publication_id: Mapped[str] = mapped_column(
        ForeignKey("publication_receipts.id"), nullable=False
    )
    timestamp_sec: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)
    retention_percent: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    source: Mapped[str | None] = mapped_column(String(64))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AudienceSnapshot(Base):
    __tablename__ = "audience_snapshots"
    __table_args__ = (Index("idx_audience_snapshots_pub", "publication_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    publication_id: Mapped[str] = mapped_column(
        ForeignKey("publication_receipts.id"), nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    follower_count: Mapped[int | None] = mapped_column(Integer)
    non_follower_reach: Mapped[int | None] = mapped_column(Integer)
    demographics: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    geography: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


