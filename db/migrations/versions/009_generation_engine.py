"""generation engine schema

Revision ID: 009
Revises: 008
Create Date: 2026-08-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "generation_requests",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("content_id", sa.String(36), nullable=True),
        sa.Column("storyboard_id", sa.String(36), nullable=True),
        sa.Column("storyboard_shot_id", sa.String(64), nullable=True),
        sa.Column("prompt_package_id", sa.String(36), nullable=True),
        sa.Column("modality", sa.String(32), nullable=False),
        sa.Column("requested_variants", sa.Integer(), server_default="1", nullable=False),
        sa.Column("priority", sa.String(32), server_default="normal", nullable=False),
        sa.Column("budget", sa.JSON(), nullable=True),
        sa.Column("provider_strategy", sa.JSON(), nullable=True),
        sa.Column("quality", sa.JSON(), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("profile", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), server_default="queued", nullable=False),
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
        sa.ForeignKeyConstraint(["storyboard_id"], ["storyboards.id"]),
        sa.ForeignKeyConstraint(["prompt_package_id"], ["prompt_packages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_generation_requests_status", "generation_requests", ["status"])

    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("variant_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("provider", sa.String(128), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("status", sa.String(32), server_default="queued", nullable=False),
        sa.Column("provider_job_id", sa.String(256), nullable=True),
        sa.Column("prompt_package_id", sa.String(36), nullable=True),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("fallback_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("estimated_cost", sa.Numeric(12, 6), nullable=True),
        sa.Column("actual_cost", sa.Numeric(12, 6), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("latency", sa.JSON(), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=True),
        sa.Column("depends_on", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["request_id"], ["generation_requests.id"]),
        sa.ForeignKeyConstraint(["prompt_package_id"], ["prompt_packages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_generation_jobs_status", "generation_jobs", ["status"])

    op.create_table(
        "media_artifacts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("generation_job_id", sa.String(36), nullable=False),
        sa.Column("artifact_type", sa.String(32), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("prompt_package_id", sa.String(36), nullable=True),
        sa.Column("provider", sa.String(128), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("technical_qa", sa.JSON(), nullable=True),
        sa.Column("lineage", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["generation_job_id"], ["generation_jobs.id"]),
        sa.ForeignKeyConstraint(["prompt_package_id"], ["prompt_packages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_media_artifacts_job", "media_artifacts", ["generation_job_id"])

    op.create_table(
        "provider_performance",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("provider", sa.String(128), nullable=False),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("modality", sa.String(32), nullable=False),
        sa.Column("success_rate", sa.Numeric(8, 4), nullable=True),
        sa.Column("avg_latency_ms", sa.Integer(), nullable=True),
        sa.Column("avg_cost", sa.Numeric(12, 6), nullable=True),
        sa.Column("avg_qa_score", sa.Numeric(8, 4), nullable=True),
        sa.Column("fallback_rate", sa.Numeric(8, 4), nullable=True),
        sa.Column("sample_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "model", "modality", name="uq_provider_perf"),
    )

    op.create_table(
        "provider_references",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("internal_asset_id", sa.String(36), nullable=False),
        sa.Column("provider", sa.String(128), nullable=False),
        sa.Column("provider_asset_id", sa.String(256), nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("provider_references")
    op.drop_table("provider_performance")
    op.drop_index("idx_media_artifacts_job", table_name="media_artifacts")
    op.drop_table("media_artifacts")
    op.drop_index("idx_generation_jobs_status", table_name="generation_jobs")
    op.drop_table("generation_jobs")
    op.drop_index("idx_generation_requests_status", table_name="generation_requests")
    op.drop_table("generation_requests")
