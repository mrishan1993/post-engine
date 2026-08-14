"""learning & optimization engine schema

Revision ID: 019
Revises: 018
Create Date: 2026-08-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "learning_observations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("content_id", sa.String(64), nullable=True),
        sa.Column("publication_id", sa.String(36), nullable=True),
        sa.Column("prediction_ref", sa.String(64), nullable=True),
        sa.Column("source_verification_id", sa.String(36), nullable=True),
        sa.Column("feature_vector", sa.JSON(), nullable=False),
        sa.Column("outcome_vector", sa.JSON(), nullable=False),
        sa.Column("quality_flags", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("excluded", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("exclude_reason", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["source_verification_id"], ["verification_runs.id"]),
        sa.ForeignKeyConstraint(["publication_id"], ["publication_receipts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_learning_observations_content", "learning_observations", ["content_id"])
    op.create_index(
        "idx_learning_observations_publication", "learning_observations", ["publication_id"]
    )

    op.create_table(
        "optimization_profiles",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("recommendations", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("brief", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("policy_snapshot", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_optimization_profiles_status", "optimization_profiles", ["status"])

    op.create_table(
        "optimization_experiments",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("variable", sa.String(128), nullable=False),
        sa.Column("control", sa.JSON(), nullable=False),
        sa.Column("variants", sa.JSON(), nullable=False),
        sa.Column("target_metric", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("sample_target", sa.Integer(), server_default="30", nullable=False),
        sa.Column("sample_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("assignment_counts", sa.JSON(), nullable=True),
        sa.Column("results", sa.JSON(), nullable=True),
        sa.Column("scope", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_optimization_experiments_status", "optimization_experiments", ["status"])

    op.create_table(
        "optimization_model_versions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), server_default="challenger", nullable=False),
        sa.Column("training_data_version", sa.String(128), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("weights", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_name", "version", name="uq_opt_model_name_version"),
    )
    op.create_index(
        "idx_optimization_model_versions_status", "optimization_model_versions", ["status"]
    )

    op.create_table(
        "optimization_recommendations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("profile_id", sa.String(36), nullable=True),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("target", sa.String(128), nullable=False),
        sa.Column("action", sa.String(256), nullable=False),
        sa.Column("change", sa.JSON(), nullable=True),
        sa.Column("expected_effect", sa.JSON(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(32), server_default="proposed", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["optimization_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_optimization_recommendations_status", "optimization_recommendations", ["status"]
    )


def downgrade() -> None:
    op.drop_index(
        "idx_optimization_recommendations_status", table_name="optimization_recommendations"
    )
    op.drop_table("optimization_recommendations")
    op.drop_index(
        "idx_optimization_model_versions_status", table_name="optimization_model_versions"
    )
    op.drop_table("optimization_model_versions")
    op.drop_index("idx_optimization_experiments_status", table_name="optimization_experiments")
    op.drop_table("optimization_experiments")
    op.drop_index("idx_optimization_profiles_status", table_name="optimization_profiles")
    op.drop_table("optimization_profiles")
    op.drop_index("idx_learning_observations_publication", table_name="learning_observations")
    op.drop_index("idx_learning_observations_content", table_name="learning_observations")
    op.drop_table("learning_observations")
