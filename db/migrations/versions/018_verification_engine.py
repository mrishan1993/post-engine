"""verification engine schema

Revision ID: 018
Revises: 017
Create Date: 2026-08-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "verification_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("prediction_ref", sa.String(64), nullable=False),
        sa.Column("registry_prediction_id", sa.Integer(), nullable=True),
        sa.Column("publication_id", sa.String(36), nullable=True),
        sa.Column("content_id", sa.String(64), nullable=True),
        sa.Column("stage", sa.String(32), server_default="primary", nullable=False),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("measurement_window", sa.JSON(), nullable=True),
        sa.Column("prediction_snapshot", sa.JSON(), nullable=False),
        sa.Column("actual_snapshot", sa.JSON(), nullable=True),
        sa.Column("result_summary", sa.JSON(), nullable=True),
        sa.Column("diagnosis", sa.JSON(), nullable=True),
        sa.Column("model_id", sa.String(128), nullable=True),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column("lineage", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["registry_prediction_id"], ["predictions.id"]),
        sa.ForeignKeyConstraint(["publication_id"], ["publication_receipts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_verification_runs_status", "verification_runs", ["status"])
    op.create_index("idx_verification_runs_publication", "verification_runs", ["publication_id"])
    op.create_index("idx_verification_runs_prediction", "verification_runs", ["prediction_ref"])

    op.create_table(
        "verification_metric_results",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("verification_run_id", sa.String(36), nullable=False),
        sa.Column("metric", sa.String(128), nullable=False),
        sa.Column("predicted_value", sa.Numeric(18, 6), nullable=True),
        sa.Column("actual_value", sa.Numeric(18, 6), nullable=True),
        sa.Column("absolute_error", sa.Numeric(18, 6), nullable=True),
        sa.Column("relative_error", sa.Numeric(18, 6), nullable=True),
        sa.Column("log_error", sa.Numeric(18, 6), nullable=True),
        sa.Column("outcome", sa.Boolean(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["verification_run_id"], ["verification_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_verification_metric_results_run", "verification_metric_results", ["verification_run_id"]
    )

    op.create_table(
        "calibration_buckets",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("model_id", sa.String(128), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("metric", sa.String(128), nullable=False),
        sa.Column("probability_bucket", sa.String(32), nullable=False),
        sa.Column("segment_key", sa.String(128), server_default="global", nullable=False),
        sa.Column("sample_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("mean_prediction", sa.Numeric(10, 6), nullable=True),
        sa.Column("actual_success_rate", sa.Numeric(10, 6), nullable=True),
        sa.Column("calibration_error", sa.Numeric(10, 6), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "model_id",
            "model_version",
            "metric",
            "probability_bucket",
            "segment_key",
            name="uq_calibration_bucket",
        ),
    )

    op.create_table(
        "learning_signals",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("content_id", sa.String(64), nullable=True),
        sa.Column("prediction_ref", sa.String(64), nullable=True),
        sa.Column("verification_id", sa.String(36), nullable=True),
        sa.Column("signal_type", sa.String(128), nullable=False),
        sa.Column("signal_value", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["verification_id"], ["verification_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_learning_signals_prediction", "learning_signals", ["prediction_ref"])


def downgrade() -> None:
    op.drop_index("idx_learning_signals_prediction", table_name="learning_signals")
    op.drop_table("learning_signals")
    op.drop_table("calibration_buckets")
    op.drop_index("idx_verification_metric_results_run", table_name="verification_metric_results")
    op.drop_table("verification_metric_results")
    op.drop_index("idx_verification_runs_prediction", table_name="verification_runs")
    op.drop_index("idx_verification_runs_publication", table_name="verification_runs")
    op.drop_index("idx_verification_runs_status", table_name="verification_runs")
    op.drop_table("verification_runs")
