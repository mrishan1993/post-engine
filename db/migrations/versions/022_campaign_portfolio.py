"""campaign & content portfolio engine schema

Revision ID: 022
Revises: 021
Create Date: 2026-08-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("strategy_id", sa.String(36), nullable=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("campaign_type", sa.String(64), server_default="growth", nullable=False),
        sa.Column("objective", sa.JSON(), nullable=False),
        sa.Column("audience", sa.JSON(), nullable=True),
        sa.Column("platforms", sa.JSON(), nullable=True),
        sa.Column("kpis", sa.JSON(), nullable=True),
        sa.Column("hypothesis", sa.Text(), nullable=True),
        sa.Column("priority", sa.Numeric(8, 4), server_default="0.5", nullable=False),
        sa.Column("budget", sa.JSON(), nullable=True),
        sa.Column("content_target", sa.Integer(), server_default="10", nullable=False),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("character_slug", sa.String(64), nullable=True),
        sa.Column("continuity", sa.JSON(), nullable=True),
        sa.Column("journey", sa.JSON(), nullable=True),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["strategy_id"], ["content_strategies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_campaigns_status", "campaigns", ["status"])
    op.create_index("idx_campaigns_strategy", "campaigns", ["strategy_id"])

    op.create_table(
        "content_series",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("premise", sa.Text(), nullable=True),
        sa.Column("format", sa.String(64), server_default="reel", nullable=False),
        sa.Column("character_slug", sa.String(64), nullable=True),
        sa.Column("narrative_rules", sa.JSON(), nullable=True),
        sa.Column("visual_rules", sa.JSON(), nullable=True),
        sa.Column("episode_template", sa.JSON(), nullable=True),
        sa.Column("publishing_cadence", sa.JSON(), nullable=True),
        sa.Column("platform_strategy", sa.JSON(), nullable=True),
        sa.Column("success_metrics", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("target_episodes", sa.Integer(), server_default="5", nullable=False),
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
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_content_series_campaign", "content_series", ["campaign_id"])

    op.create_table(
        "campaign_episodes",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("series_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("episode_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(256), nullable=True),
        sa.Column("objective", sa.String(128), nullable=True),
        sa.Column("premise", sa.Text(), nullable=True),
        sa.Column("hook", sa.Text(), nullable=True),
        sa.Column("narrative_role", sa.String(64), nullable=True),
        sa.Column("audience_role", sa.String(64), nullable=True),
        sa.Column("platform", sa.String(64), server_default="instagram", nullable=False),
        sa.Column("trend_id", sa.String(64), nullable=True),
        sa.Column("continuity_requirements", sa.JSON(), nullable=True),
        sa.Column("cta", sa.String(256), nullable=True),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("performance", sa.JSON(), nullable=True),
        sa.Column("orchestration_job_id", sa.String(36), nullable=True),
        sa.Column("strategy_opportunity_id", sa.String(36), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["series_id"], ["content_series.id"]),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("series_id", "episode_number", name="uq_series_episode_number"),
    )
    op.create_index("idx_campaign_episodes_series", "campaign_episodes", ["series_id"])
    op.create_index("idx_campaign_episodes_status", "campaign_episodes", ["status"])

    op.create_table(
        "campaign_content",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("episode_id", sa.String(36), nullable=True),
        sa.Column("content_id", sa.String(64), nullable=True),
        sa.Column("role", sa.String(64), nullable=True),
        sa.Column("platform", sa.String(64), nullable=True),
        sa.Column("sequence_position", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(32), server_default="planned", nullable=False),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["episode_id"], ["campaign_episodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_campaign_content_campaign", "campaign_content", ["campaign_id"])

    op.create_table(
        "campaign_dependencies",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("source_episode_id", sa.String(36), nullable=False),
        sa.Column("target_episode_id", sa.String(36), nullable=False),
        sa.Column("dependency_type", sa.String(64), server_default="sequence", nullable=False),
        sa.Column("condition", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["source_episode_id"], ["campaign_episodes.id"]),
        sa.ForeignKeyConstraint(["target_episode_id"], ["campaign_episodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_campaign_dependencies_campaign", "campaign_dependencies", ["campaign_id"])

    op.create_table(
        "campaign_metrics",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=False),
        sa.Column("series_id", sa.String(36), nullable=True),
        sa.Column("episode_id", sa.String(36), nullable=True),
        sa.Column("metric", sa.String(128), nullable=False),
        sa.Column("value", sa.Numeric(18, 4), nullable=True),
        sa.Column("period", sa.String(64), nullable=True),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_campaign_metrics_campaign", "campaign_metrics", ["campaign_id"])

    op.create_table(
        "campaign_decisions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=True),
        sa.Column("decision_type", sa.String(64), nullable=False),
        sa.Column("decision", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("expected_outcome", sa.JSON(), nullable=True),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_campaign_decisions_campaign", "campaign_decisions", ["campaign_id"])

    op.create_table(
        "franchises",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=True),
        sa.Column("series_id", sa.String(36), nullable=True),
        sa.Column("name", sa.String(256), nullable=True),
        sa.Column("status", sa.String(32), server_default="detected", nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("performance_basis", sa.JSON(), nullable=True),
        sa.Column("source_episode_ids", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["series_id"], ["content_series.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_franchises_status", "franchises", ["status"])


def downgrade() -> None:
    op.drop_index("idx_franchises_status", table_name="franchises")
    op.drop_table("franchises")
    op.drop_index("idx_campaign_decisions_campaign", table_name="campaign_decisions")
    op.drop_table("campaign_decisions")
    op.drop_index("idx_campaign_metrics_campaign", table_name="campaign_metrics")
    op.drop_table("campaign_metrics")
    op.drop_index("idx_campaign_dependencies_campaign", table_name="campaign_dependencies")
    op.drop_table("campaign_dependencies")
    op.drop_index("idx_campaign_content_campaign", table_name="campaign_content")
    op.drop_table("campaign_content")
    op.drop_index("idx_campaign_episodes_status", table_name="campaign_episodes")
    op.drop_index("idx_campaign_episodes_series", table_name="campaign_episodes")
    op.drop_table("campaign_episodes")
    op.drop_index("idx_content_series_campaign", table_name="content_series")
    op.drop_table("content_series")
    op.drop_index("idx_campaigns_strategy", table_name="campaigns")
    op.drop_index("idx_campaigns_status", table_name="campaigns")
    op.drop_table("campaigns")
