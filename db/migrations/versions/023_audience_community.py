"""audience intelligence & community engine schema

Revision ID: 023
Revises: 022
Create Date: 2026-08-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audience_segments",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("criteria", sa.JSON(), nullable=True),
        sa.Column("size", sa.Integer(), server_default="0", nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("segment_kind", sa.String(32), server_default="explicit", nullable=False),
        sa.Column("lifecycle_stage", sa.String(64), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audience_segments_status", "audience_segments", ["status"])

    op.create_table(
        "audience_signals",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("content_id", sa.String(64), nullable=True),
        sa.Column("segment_id", sa.String(36), nullable=True),
        sa.Column("signal_type", sa.String(64), nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("platform", sa.String(64), nullable=True),
        sa.Column("language", sa.String(32), nullable=True),
        sa.Column("is_noise", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["segment_id"], ["audience_segments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audience_signals_content", "audience_signals", ["content_id"])
    op.create_index("idx_audience_signals_type", "audience_signals", ["signal_type"])

    op.create_table(
        "audience_intents",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("segment_id", sa.String(36), nullable=True),
        sa.Column("intent_type", sa.String(64), nullable=False),
        sa.Column("subject", sa.String(512), nullable=True),
        sa.Column("volume", sa.Integer(), server_default="1", nullable=False),
        sa.Column("velocity", sa.Numeric(10, 4), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("content_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["segment_id"], ["audience_segments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audience_intents_type", "audience_intents", ["intent_type"])

    op.create_table(
        "community_topics",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("topic", sa.String(256), nullable=False),
        sa.Column("volume", sa.Integer(), server_default="0", nullable=False),
        sa.Column("velocity", sa.Numeric(12, 4), nullable=True),
        sa.Column("sentiment", sa.JSON(), nullable=True),
        sa.Column("related_content", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_community_topics_status", "community_topics", ["status"])

    op.create_table(
        "audience_demands",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("subject", sa.String(512), nullable=False),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("volume", sa.Integer(), server_default="0", nullable=False),
        sa.Column("velocity", sa.Numeric(10, 4), nullable=True),
        sa.Column("strategic_fit", sa.Numeric(5, 4), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("recommended_action", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), server_default="detected", nullable=False),
        sa.Column("audience_segments", sa.JSON(), nullable=True),
        sa.Column("sentiment", sa.String(32), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("related_content", sa.JSON(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audience_demands_status", "audience_demands", ["status"])

    op.create_table(
        "character_affinity",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("character_slug", sa.String(64), nullable=False),
        sa.Column("segment_id", sa.String(36), nullable=True),
        sa.Column("affinity_score", sa.Numeric(8, 4), nullable=True),
        sa.Column("sentiment", sa.JSON(), nullable=True),
        sa.Column("trend", sa.String(32), nullable=True),
        sa.Column("relationships", sa.JSON(), nullable=True),
        sa.Column("memorable_traits", sa.JSON(), nullable=True),
        sa.Column("audience_requests", sa.JSON(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["segment_id"], ["audience_segments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_character_affinity_slug", "character_affinity", ["character_slug"])

    op.create_table(
        "community_interactions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("platform", sa.String(64), nullable=False),
        sa.Column("content_id", sa.String(64), nullable=True),
        sa.Column("interaction_type", sa.String(64), nullable=False),
        sa.Column("text_reference", sa.Text(), nullable=True),
        sa.Column("text_normalized", sa.Text(), nullable=True),
        sa.Column("segment_id", sa.String(36), nullable=True),
        sa.Column("intent_id", sa.String(36), nullable=True),
        sa.Column("intent_type", sa.String(64), nullable=True),
        sa.Column("sentiment", sa.String(32), nullable=True),
        sa.Column("emotion", sa.String(32), nullable=True),
        sa.Column("language", sa.String(32), nullable=True),
        sa.Column("priority", sa.Numeric(8, 4), nullable=True),
        sa.Column("is_noise", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("moderation_flags", sa.JSON(), nullable=True),
        sa.Column("entities", sa.JSON(), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["segment_id"], ["audience_segments.id"]),
        sa.ForeignKeyConstraint(["intent_id"], ["audience_intents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_community_interactions_content", "community_interactions", ["content_id"])
    op.create_index("idx_community_interactions_noise", "community_interactions", ["is_noise"])

    op.create_table(
        "community_alerts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("alert_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), server_default="P2", nullable=False),
        sa.Column("subject", sa.String(512), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("recommended_action", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), server_default="open", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_community_alerts_status", "community_alerts", ["status"])

    op.create_table(
        "audience_opportunities",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("subject", sa.String(512), nullable=False),
        sa.Column("volume", sa.Integer(), server_default="0", nullable=False),
        sa.Column("velocity", sa.Numeric(10, 4), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("strategic_fit", sa.Numeric(5, 4), nullable=True),
        sa.Column("audience_segments", sa.JSON(), nullable=True),
        sa.Column("sentiment", sa.String(32), nullable=True),
        sa.Column("recommended_action", sa.String(64), nullable=True),
        sa.Column("priority", sa.String(8), server_default="P2", nullable=False),
        sa.Column("status", sa.String(32), server_default="detected", nullable=False),
        sa.Column("demand_id", sa.String(36), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("strategy_opportunity_id", sa.String(64), nullable=True),
        sa.Column("campaign_episode_id", sa.String(36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["demand_id"], ["audience_demands.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audience_opportunities_status", "audience_opportunities", ["status"])

    op.create_table(
        "audience_intelligence_snapshots",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("community_health", sa.Numeric(8, 4), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("audience_intelligence_snapshots")
    op.drop_index("idx_audience_opportunities_status", table_name="audience_opportunities")
    op.drop_table("audience_opportunities")
    op.drop_index("idx_community_alerts_status", table_name="community_alerts")
    op.drop_table("community_alerts")
    op.drop_index("idx_community_interactions_noise", table_name="community_interactions")
    op.drop_index("idx_community_interactions_content", table_name="community_interactions")
    op.drop_table("community_interactions")
    op.drop_index("idx_character_affinity_slug", table_name="character_affinity")
    op.drop_table("character_affinity")
    op.drop_index("idx_audience_demands_status", table_name="audience_demands")
    op.drop_table("audience_demands")
    op.drop_index("idx_community_topics_status", table_name="community_topics")
    op.drop_table("community_topics")
    op.drop_index("idx_audience_intents_type", table_name="audience_intents")
    op.drop_table("audience_intents")
    op.drop_index("idx_audience_signals_type", table_name="audience_signals")
    op.drop_index("idx_audience_signals_content", table_name="audience_signals")
    op.drop_table("audience_signals")
    op.drop_index("idx_audience_segments_status", table_name="audience_segments")
    op.drop_table("audience_segments")
