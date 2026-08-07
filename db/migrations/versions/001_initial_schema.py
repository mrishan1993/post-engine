"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-08-07

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "verticals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("config_path", sa.String(length=256), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "provider_health",
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_healthy", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("provider"),
    )

    op.create_table(
        "content_briefs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vertical_id", sa.Integer(), nullable=False),
        sa.Column("brief_text", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("generated_by_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["vertical_id"], ["verticals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_content_briefs_status_priority", "content_briefs", ["status", "priority"])

    op.create_table(
        "video_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("brief_id", sa.Integer(), nullable=False),
        sa.Column("vertical_id", sa.Integer(), nullable=False),
        sa.Column("parent_run_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="created"),
        sa.Column("script_text", sa.Text(), nullable=True),
        sa.Column("title", sa.String(length=256), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("audio_asset_path", sa.String(length=512), nullable=True),
        sa.Column("audio_duration_sec", sa.Integer(), nullable=True),
        sa.Column("visual_asset_path", sa.String(length=512), nullable=True),
        sa.Column("rendered_video_path", sa.String(length=512), nullable=True),
        sa.Column("rendered_duration_sec", sa.Integer(), nullable=True),
        sa.Column("safety_check_result", sa.JSON(), nullable=True),
        sa.Column("qa_reviewer", sa.String(length=128), nullable=True),
        sa.Column("qa_notes", sa.Text(), nullable=True),
        sa.Column("qa_decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_log", sa.Text(), nullable=True),
        sa.Column("total_cost_usd", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["brief_id"], ["content_briefs.id"]),
        sa.ForeignKeyConstraint(["parent_run_id"], ["video_runs.id"]),
        sa.ForeignKeyConstraint(["vertical_id"], ["verticals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_video_runs_status", "video_runs", ["status"])
    op.create_index("idx_video_runs_vertical", "video_runs", ["vertical_id", "created_at"])

    op.create_table(
        "publications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("video_run_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("platform_post_id", sa.String(length=256), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("platform_metadata", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="scheduled"),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["video_run_id"], ["video_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("video_run_id", "platform", name="idx_publications_run_platform"),
    )

    op.create_table(
        "agent_run_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("video_run_id", sa.Integer(), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("input_summary", sa.Text(), nullable=True),
        sa.Column("output_summary", sa.Text(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(8, 4), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["video_run_id"], ["video_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_agent_run_logs_video_run", "agent_run_logs", ["video_run_id", "created_at"])

    op.create_table(
        "video_metrics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("publication_id", sa.Integer(), nullable=False),
        sa.Column("pulled_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("views", sa.Integer(), nullable=True),
        sa.Column("avg_view_duration_sec", sa.Integer(), nullable=True),
        sa.Column("likes", sa.Integer(), nullable=True),
        sa.Column("comments", sa.Integer(), nullable=True),
        sa.Column("estimated_revenue_usd", sa.Numeric(10, 2), nullable=True),
        sa.ForeignKeyConstraint(["publication_id"], ["publications.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_video_metrics_publication", "video_metrics", ["publication_id", "pulled_at"])


def downgrade() -> None:
    op.drop_index("idx_video_metrics_publication", table_name="video_metrics")
    op.drop_table("video_metrics")
    op.drop_index("idx_agent_run_logs_video_run", table_name="agent_run_logs")
    op.drop_table("agent_run_logs")
    op.drop_table("publications")
    op.drop_index("idx_video_runs_vertical", table_name="video_runs")
    op.drop_index("idx_video_runs_status", table_name="video_runs")
    op.drop_table("video_runs")
    op.drop_index("idx_content_briefs_status_priority", table_name="content_briefs")
    op.drop_table("content_briefs")
    op.drop_table("provider_health")
    op.drop_table("verticals")
