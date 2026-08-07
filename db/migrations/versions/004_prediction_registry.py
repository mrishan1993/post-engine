"""prediction registry + verification schema

Revision ID: 004
Revises: 003
Create Date: 2026-08-07

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "predictions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subsystem", sa.String(64), nullable=False),
        sa.Column("decision_type", sa.String(64), nullable=False),
        sa.Column("content_brief_id", sa.Integer(), nullable=True),
        sa.Column("video_run_id", sa.Integer(), nullable=True),
        sa.Column("opportunity_id", sa.Integer(), nullable=True),
        sa.Column("vertical_slug", sa.String(64), nullable=True),
        sa.Column("platform", sa.String(32), nullable=True),
        sa.Column("model_version", sa.String(64), server_default="rule_v1", nullable=False),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("virality_probability", sa.Numeric(5, 4), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("predicted_views", sa.Integer(), nullable=True),
        sa.Column("predicted_views_low", sa.Integer(), nullable=True),
        sa.Column("predicted_views_high", sa.Integer(), nullable=True),
        sa.Column("predicted_reach", sa.Integer(), nullable=True),
        sa.Column("predicted_ctr", sa.Numeric(6, 4), nullable=True),
        sa.Column("predicted_watch_time_sec", sa.Numeric(8, 2), nullable=True),
        sa.Column("predicted_retention", sa.Numeric(5, 4), nullable=True),
        sa.Column("predicted_engagement_rate", sa.Numeric(6, 4), nullable=True),
        sa.Column("predicted_shares", sa.Integer(), nullable=True),
        sa.Column("predicted_saves", sa.Integer(), nullable=True),
        sa.Column("predicted_comments", sa.Integer(), nullable=True),
        sa.Column("predicted_followers", sa.Integer(), nullable=True),
        sa.Column("predicted_revenue_usd", sa.Numeric(10, 2), nullable=True),
        sa.Column("predicted_roi", sa.Numeric(8, 3), nullable=True),
        sa.Column("expected_cost_usd", sa.Numeric(8, 4), nullable=True),
        sa.Column("final_opportunity_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("risk_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=True),
        sa.Column("reasoning_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["content_brief_id"], ["content_briefs.id"]),
        sa.ForeignKeyConstraint(["video_run_id"], ["video_runs.id"]),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunity_scores.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_predictions_brief", "predictions", ["content_brief_id"])
    op.create_index("idx_predictions_subsystem", "predictions", ["subsystem", "created_at"])
    op.create_index("idx_predictions_status", "predictions", ["status"])

    op.create_table(
        "prediction_features",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("prediction_id", sa.Integer(), nullable=False),
        sa.Column("feature_name", sa.String(128), nullable=False),
        sa.Column("feature_value", sa.Numeric(12, 6), nullable=True),
        sa.Column("feature_raw", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["prediction_id"], ["predictions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prediction_id", "feature_name", name="uq_prediction_feature"),
    )
    op.create_index("idx_prediction_features_pred", "prediction_features", ["prediction_id"])

    op.create_table(
        "verification_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("prediction_id", sa.Integer(), nullable=False),
        sa.Column("actual_views", sa.Integer(), nullable=True),
        sa.Column("actual_ctr", sa.Numeric(6, 4), nullable=True),
        sa.Column("actual_retention", sa.Numeric(5, 4), nullable=True),
        sa.Column("actual_watch_time_sec", sa.Numeric(8, 2), nullable=True),
        sa.Column("actual_comments", sa.Integer(), nullable=True),
        sa.Column("actual_shares", sa.Integer(), nullable=True),
        sa.Column("actual_saves", sa.Integer(), nullable=True),
        sa.Column("actual_followers", sa.Integer(), nullable=True),
        sa.Column("actual_revenue_usd", sa.Numeric(10, 2), nullable=True),
        sa.Column("actual_engagement_rate", sa.Numeric(6, 4), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=True),
        sa.Column("explanation", sa.JSON(), nullable=True),
        sa.Column("mape", sa.Numeric(8, 4), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["prediction_id"], ["predictions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prediction_id"),
    )

    op.create_table(
        "prediction_errors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("prediction_id", sa.Integer(), nullable=False),
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("predicted", sa.Numeric(14, 4), nullable=True),
        sa.Column("actual", sa.Numeric(14, 4), nullable=True),
        sa.Column("absolute_error", sa.Numeric(14, 4), nullable=True),
        sa.Column("percentage_error", sa.Numeric(10, 4), nullable=True),
        sa.ForeignKeyConstraint(["prediction_id"], ["predictions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_prediction_errors_pred", "prediction_errors", ["prediction_id"])

    op.create_table(
        "model_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("subsystem", sa.String(64), server_default="probability_engine", nullable=False),
        sa.Column("weights", sa.JSON(), nullable=True),
        sa.Column("calibration", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "prediction_lessons",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("prediction_id", sa.Integer(), nullable=False),
        sa.Column("primary_cause", sa.Text(), nullable=True),
        sa.Column("secondary_causes", sa.JSON(), nullable=True),
        sa.Column("suggested_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("lesson", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["prediction_id"], ["predictions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("prediction_lessons")
    op.drop_table("model_versions")
    op.drop_index("idx_prediction_errors_pred", table_name="prediction_errors")
    op.drop_table("prediction_errors")
    op.drop_table("verification_results")
    op.drop_index("idx_prediction_features_pred", table_name="prediction_features")
    op.drop_table("prediction_features")
    op.drop_index("idx_predictions_status", table_name="predictions")
    op.drop_index("idx_predictions_subsystem", table_name="predictions")
    op.drop_index("idx_predictions_brief", table_name="predictions")
    op.drop_table("predictions")
