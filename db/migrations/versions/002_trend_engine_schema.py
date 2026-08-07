"""trend engine schema

Revision ID: 002
Revises: 001
Create Date: 2026-08-07

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trend_signals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=256), nullable=True),
        sa.Column("title_or_query", sa.Text(), nullable=True),
        sa.Column("raw_metrics", sa.JSON(), nullable=True),
        sa.Column("region", sa.String(length=16), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_trend_signals_source_collected",
        "trend_signals",
        ["source", "collected_at"],
    )

    op.create_table(
        "trend_topics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("topic_label", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("candidate_verticals", sa.JSON(), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "trend_topic_signals",
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column("signal_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["signal_id"], ["trend_signals.id"]),
        sa.ForeignKeyConstraint(["topic_id"], ["trend_topics.id"]),
        sa.PrimaryKeyConstraint("topic_id", "signal_id"),
    )

    op.create_table(
        "trend_scores",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Numeric(6, 3), nullable=False),
        sa.Column("score_breakdown", sa.JSON(), nullable=True),
        sa.Column(
            "scored_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["topic_id"], ["trend_topics.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_trend_scores_topic_time", "trend_scores", ["topic_id", "scored_at"])

    op.create_table(
        "trend_feedback",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column("content_brief_id", sa.Integer(), nullable=True),
        sa.Column("predicted_score", sa.Numeric(6, 3), nullable=True),
        sa.Column("actual_views", sa.Integer(), nullable=True),
        sa.Column("actual_engagement_rate", sa.Numeric(6, 4), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["content_brief_id"], ["content_briefs.id"]),
        sa.ForeignKeyConstraint(["topic_id"], ["trend_topics.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("trend_feedback")
    op.drop_index("idx_trend_scores_topic_time", table_name="trend_scores")
    op.drop_table("trend_scores")
    op.drop_table("trend_topic_signals")
    op.drop_table("trend_topics")
    op.drop_index("idx_trend_signals_source_collected", table_name="trend_signals")
    op.drop_table("trend_signals")
