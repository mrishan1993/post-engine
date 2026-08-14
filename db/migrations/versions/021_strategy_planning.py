"""content strategy & planning engine schema

Revision ID: 021
Revises: 020
Create Date: 2026-08-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "content_strategies",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("character_slug", sa.String(64), nullable=True),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("autonomy", sa.String(32), server_default="semi_autonomous", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
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
    op.create_index("idx_content_strategies_status", "content_strategies", ["status"])

    op.create_table(
        "strategy_opportunities",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("strategy_id", sa.String(36), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("title", sa.String(256), nullable=True),
        sa.Column("objective", sa.String(128), nullable=True),
        sa.Column("audience", sa.String(128), nullable=True),
        sa.Column("pillar", sa.String(64), nullable=True),
        sa.Column("platform", sa.String(64), nullable=False),
        sa.Column("format", sa.String(64), server_default="reel", nullable=False),
        sa.Column("priority", sa.String(8), server_default="P3", nullable=False),
        sa.Column("strategic_score", sa.Numeric(8, 4), nullable=True),
        sa.Column("score_breakdown", sa.JSON(), nullable=True),
        sa.Column("expected_impact", sa.Numeric(8, 4), nullable=True),
        sa.Column("effort", sa.Numeric(8, 4), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(32), server_default="detected", nullable=False),
        sa.Column("expiration_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trend_id", sa.String(64), nullable=True),
        sa.Column("orchestration_job_id", sa.String(36), nullable=True),
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
    op.create_index("idx_strategy_opportunities_strategy", "strategy_opportunities", ["strategy_id"])
    op.create_index("idx_strategy_opportunities_status", "strategy_opportunities", ["status"])
    op.create_index("idx_strategy_opportunities_priority", "strategy_opportunities", ["priority"])

    op.create_table(
        "content_plans",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("strategy_id", sa.String(36), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("objectives", sa.JSON(), nullable=True),
        sa.Column("content_mix", sa.JSON(), nullable=True),
        sa.Column("capacity", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
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
    op.create_index("idx_content_plans_strategy", "content_plans", ["strategy_id"])

    op.create_table(
        "content_plan_items",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("plan_id", sa.String(36), nullable=False),
        sa.Column("opportunity_id", sa.String(36), nullable=True),
        sa.Column("platform", sa.String(64), nullable=False),
        sa.Column("pillar", sa.String(64), nullable=True),
        sa.Column("content_type", sa.String(64), nullable=True),
        sa.Column("priority", sa.String(8), server_default="P3", nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), server_default="planned", nullable=False),
        sa.Column("slot_meta", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["content_plans.id"]),
        sa.ForeignKeyConstraint(["opportunity_id"], ["strategy_opportunities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_content_plan_items_plan", "content_plan_items", ["plan_id"])
    op.create_index("idx_content_plan_items_status", "content_plan_items", ["status"])

    op.create_table(
        "strategy_decision_log",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("strategy_id", sa.String(36), nullable=True),
        sa.Column("plan_id", sa.String(36), nullable=True),
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
        sa.ForeignKeyConstraint(["strategy_id"], ["content_strategies.id"]),
        sa.ForeignKeyConstraint(["plan_id"], ["content_plans.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_strategy_decision_log_strategy", "strategy_decision_log", ["strategy_id"])


def downgrade() -> None:
    op.drop_index("idx_strategy_decision_log_strategy", table_name="strategy_decision_log")
    op.drop_table("strategy_decision_log")
    op.drop_index("idx_content_plan_items_status", table_name="content_plan_items")
    op.drop_index("idx_content_plan_items_plan", table_name="content_plan_items")
    op.drop_table("content_plan_items")
    op.drop_index("idx_content_plans_strategy", table_name="content_plans")
    op.drop_table("content_plans")
    op.drop_index("idx_strategy_opportunities_priority", table_name="strategy_opportunities")
    op.drop_index("idx_strategy_opportunities_status", table_name="strategy_opportunities")
    op.drop_index("idx_strategy_opportunities_strategy", table_name="strategy_opportunities")
    op.drop_table("strategy_opportunities")
    op.drop_index("idx_content_strategies_status", table_name="content_strategies")
    op.drop_table("content_strategies")
