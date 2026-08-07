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
