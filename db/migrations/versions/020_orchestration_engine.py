"""trend-to-reel orchestration engine schema

Revision ID: 020
Revises: 019
Create Date: 2026-08-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "orchestration_jobs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("content_id", sa.String(64), nullable=False),
        sa.Column("trend_id", sa.String(64), nullable=True),
        sa.Column("opportunity_id", sa.Integer(), nullable=True),
        sa.Column("platform", sa.String(64), nullable=False),
        sa.Column("character_slug", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("current_stage", sa.String(32), nullable=False),
        sa.Column("priority", sa.Numeric(10, 4), server_default="0", nullable=False),
        sa.Column("mode", sa.String(32), server_default="semi_autonomous", nullable=False),
        sa.Column("actionability", sa.String(16), nullable=True),
        sa.Column("trend_snapshot", sa.JSON(), nullable=True),
        sa.Column("mechanism", sa.JSON(), nullable=True),
        sa.Column("creative_context", sa.JSON(), nullable=True),
        sa.Column("lineage", sa.JSON(), nullable=True),
        sa.Column("selected_concept_id", sa.String(36), nullable=True),
        sa.Column("backup_concept_id", sa.String(36), nullable=True),
        sa.Column("production_brief_id", sa.String(36), nullable=True),
        sa.Column("approval_gate", sa.String(32), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("last_successful_stage", sa.String(32), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("recovery_strategy", sa.String(64), nullable=True),
        sa.Column("expiration_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trend_detected_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunity_scores.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_orchestration_jobs_status", "orchestration_jobs", ["status"])
    op.create_index("idx_orchestration_jobs_priority", "orchestration_jobs", ["priority"])
    op.create_index("idx_orchestration_jobs_content", "orchestration_jobs", ["content_id"])

    op.create_table(
        "creative_concepts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("job_id", sa.String(36), nullable=False),
        sa.Column("trend_id", sa.String(64), nullable=True),
        sa.Column("concept", sa.JSON(), nullable=False),
        sa.Column("score", sa.Numeric(8, 4), nullable=True),
        sa.Column("score_breakdown", sa.JSON(), nullable=True),
        sa.Column("selected", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("is_backup", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("rejection_reason", sa.String(256), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["orchestration_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_creative_concepts_job", "creative_concepts", ["job_id"])

    op.create_table(
        "production_briefs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("job_id", sa.String(36), nullable=False),
        sa.Column("concept_id", sa.String(36), nullable=True),
        sa.Column("brief", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["orchestration_jobs.id"]),
        sa.ForeignKeyConstraint(["concept_id"], ["creative_concepts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_production_briefs_job", "production_briefs", ["job_id"])

    op.create_table(
        "orchestration_engine_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("job_id", sa.String(36), nullable=False),
        sa.Column("engine_name", sa.String(64), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("input_reference", sa.JSON(), nullable=True),
        sa.Column("output_reference", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["orchestration_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_orchestration_engine_runs_job", "orchestration_engine_runs", ["job_id"])

    op.create_table(
        "orchestration_decision_log",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("job_id", sa.String(36), nullable=False),
        sa.Column("decision_type", sa.String(64), nullable=False),
        sa.Column("decision", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("score", sa.Numeric(8, 4), nullable=True),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["orchestration_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_orchestration_decision_log_job", "orchestration_decision_log", ["job_id"])


def downgrade() -> None:
    op.drop_index("idx_orchestration_decision_log_job", table_name="orchestration_decision_log")
    op.drop_table("orchestration_decision_log")
    op.drop_index("idx_orchestration_engine_runs_job", table_name="orchestration_engine_runs")
    op.drop_table("orchestration_engine_runs")
    op.drop_index("idx_production_briefs_job", table_name="production_briefs")
    op.drop_table("production_briefs")
    op.drop_index("idx_creative_concepts_job", table_name="creative_concepts")
    op.drop_table("creative_concepts")
    op.drop_index("idx_orchestration_jobs_content", table_name="orchestration_jobs")
    op.drop_index("idx_orchestration_jobs_priority", table_name="orchestration_jobs")
    op.drop_index("idx_orchestration_jobs_status", table_name="orchestration_jobs")
    op.drop_table("orchestration_jobs")
