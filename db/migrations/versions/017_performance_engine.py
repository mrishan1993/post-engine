"""performance & analytics engine schema

Revision ID: 017
Revises: 016
Create Date: 2026-08-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analytics_collection_jobs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("publication_id", sa.String(36), nullable=False),
        sa.Column("platform", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("poll_tier", sa.String(32), server_default="high", nullable=False),
        sa.Column("next_collect_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("lineage", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["publication_id"], ["publication_receipts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_analytics_jobs_status", "analytics_collection_jobs", ["status"])
    op.create_index(
        "idx_analytics_jobs_publication", "analytics_collection_jobs", ["publication_id"]
    )

    op.create_table(
        "platform_metric_responses",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("publication_id", sa.String(36), nullable=True),
        sa.Column("platform", sa.String(64), nullable=False),
        sa.Column("endpoint", sa.String(256), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["publication_id"], ["publication_receipts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_platform_metric_responses_pub", "platform_metric_responses", ["publication_id"]
    )

    op.create_table(
        "performance_snapshots",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("publication_id", sa.String(36), nullable=False),
        sa.Column("platform", sa.String(64), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("age_since_publish_sec", sa.Integer(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("derived", sa.JSON(), nullable=True),
        sa.Column("raw_response_id", sa.String(36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["publication_id"], ["publication_receipts.id"]),
        sa.ForeignKeyConstraint(["raw_response_id"], ["platform_metric_responses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_perf_snapshots_pub_captured",
        "performance_snapshots",
        ["publication_id", "captured_at"],
    )

    op.create_table(
        "performance_timeseries",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("publication_id", sa.String(36), nullable=False),
        sa.Column("metric", sa.String(128), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Numeric(18, 4), nullable=True),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["publication_id"], ["publication_receipts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_perf_ts_pub_metric",
        "performance_timeseries",
        ["publication_id", "metric", "timestamp"],
    )

    op.create_table(
        "post_analytics",
        sa.Column("publication_id", sa.String(36), nullable=False),
        sa.Column("content_id", sa.String(64), nullable=True),
        sa.Column("prediction_id", sa.String(64), nullable=True),
        sa.Column("platform", sa.String(64), nullable=True),
        sa.Column("current_views", sa.Integer(), nullable=True),
        sa.Column("current_likes", sa.Integer(), nullable=True),
        sa.Column("current_comments", sa.Integer(), nullable=True),
        sa.Column("current_shares", sa.Integer(), nullable=True),
        sa.Column("current_saves", sa.Integer(), nullable=True),
        sa.Column("current_reach", sa.Integer(), nullable=True),
        sa.Column("followers_gained", sa.Integer(), nullable=True),
        sa.Column("engagement_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("share_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("save_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("completion_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("weighted_engagement", sa.Numeric(10, 6), nullable=True),
        sa.Column("virality_score", sa.Numeric(10, 6), nullable=True),
        sa.Column("performance_index", sa.Numeric(10, 6), nullable=True),
        sa.Column("percentile_rank", sa.Numeric(10, 6), nullable=True),
        sa.Column("view_velocity_per_hour", sa.Numeric(18, 4), nullable=True),
        sa.Column("share_velocity_per_hour", sa.Numeric(18, 4), nullable=True),
        sa.Column("acceleration", sa.Numeric(18, 4), nullable=True),
        sa.Column("viral_state", sa.String(32), server_default="normal", nullable=False),
        sa.Column("content_fingerprint", sa.JSON(), nullable=True),
        sa.Column("performance_vector", sa.JSON(), nullable=True),
        sa.Column("first_hour", sa.JSON(), nullable=True),
        sa.Column("prediction_link", sa.JSON(), nullable=True),
        sa.Column("engagement_formula_version", sa.String(32), server_default="v1", nullable=False),
        sa.Column("virality_model_version", sa.String(32), server_default="v1", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["publication_id"], ["publication_receipts.id"]),
        sa.PrimaryKeyConstraint("publication_id"),
    )

    op.create_table(
        "retention_curves",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("publication_id", sa.String(36), nullable=False),
        sa.Column("timestamp_sec", sa.Numeric(10, 3), nullable=False),
        sa.Column("retention_percent", sa.Numeric(8, 4), nullable=False),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["publication_id"], ["publication_receipts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_retention_curves_pub", "retention_curves", ["publication_id"])

    op.create_table(
        "audience_snapshots",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("publication_id", sa.String(36), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("follower_count", sa.Integer(), nullable=True),
        sa.Column("non_follower_reach", sa.Integer(), nullable=True),
        sa.Column("demographics", sa.JSON(), nullable=True),
        sa.Column("geography", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["publication_id"], ["publication_receipts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audience_snapshots_pub", "audience_snapshots", ["publication_id"])


def downgrade() -> None:
    op.drop_index("idx_audience_snapshots_pub", table_name="audience_snapshots")
    op.drop_table("audience_snapshots")
    op.drop_index("idx_retention_curves_pub", table_name="retention_curves")
    op.drop_table("retention_curves")
    op.drop_table("post_analytics")
    op.drop_index("idx_perf_ts_pub_metric", table_name="performance_timeseries")
    op.drop_table("performance_timeseries")
    op.drop_index("idx_perf_snapshots_pub_captured", table_name="performance_snapshots")
    op.drop_table("performance_snapshots")
    op.drop_index("idx_platform_metric_responses_pub", table_name="platform_metric_responses")
    op.drop_table("platform_metric_responses")
    op.drop_index("idx_analytics_jobs_publication", table_name="analytics_collection_jobs")
    op.drop_index("idx_analytics_jobs_status", table_name="analytics_collection_jobs")
    op.drop_table("analytics_collection_jobs")
