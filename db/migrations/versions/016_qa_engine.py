"""qa engine schema

Revision ID: 016
Revises: 015
Create Date: 2026-08-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "qa_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("content_id", sa.String(64), nullable=False),
        sa.Column("assembly_id", sa.String(36), nullable=True),
        sa.Column("artifact_id", sa.String(36), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), server_default="queued", nullable=False),
        sa.Column("decision", sa.String(32), nullable=True),
        sa.Column("overall_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("dimension_scores", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("human_review", sa.JSON(), nullable=True),
        sa.Column("lineage", sa.JSON(), nullable=True),
        sa.Column("thresholds", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["assembly_id"], ["assemblies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_id", "version", name="uq_qa_content_version"),
    )
    op.create_index("idx_qa_runs_status", "qa_runs", ["status"])
    op.create_index("idx_qa_runs_content", "qa_runs", ["content_id"])

    op.create_table(
        "qa_issues",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("qa_run_id", sa.String(36), nullable=False),
        sa.Column("issue_code", sa.String(128), nullable=False),
        sa.Column("severity", sa.String(32), server_default="medium", nullable=False),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("artifact_id", sa.String(36), nullable=True),
        sa.Column("scene_id", sa.String(64), nullable=True),
        sa.Column("timestamp_sec", sa.Numeric(10, 3), nullable=True),
        sa.Column("score", sa.Numeric(5, 4), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_engine", sa.String(128), nullable=True),
        sa.Column("recommended_action", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), server_default="open", nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["qa_run_id"], ["qa_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_qa_issues_run", "qa_issues", ["qa_run_id"])

    op.create_table(
        "qa_measurements",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("qa_run_id", sa.String(36), nullable=False),
        sa.Column("dimension", sa.String(64), nullable=False),
        sa.Column("metric", sa.String(128), nullable=False),
        sa.Column("value", sa.Numeric(12, 4), nullable=True),
        sa.Column("threshold", sa.Numeric(12, 4), nullable=True),
        sa.Column("passed", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["qa_run_id"], ["qa_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_qa_measurements_run", "qa_measurements", ["qa_run_id"])


def downgrade() -> None:
    op.drop_index("idx_qa_measurements_run", table_name="qa_measurements")
    op.drop_table("qa_measurements")
    op.drop_index("idx_qa_issues_run", table_name="qa_issues")
    op.drop_table("qa_issues")
    op.drop_index("idx_qa_runs_content", table_name="qa_runs")
    op.drop_index("idx_qa_runs_status", table_name="qa_runs")
    op.drop_table("qa_runs")
