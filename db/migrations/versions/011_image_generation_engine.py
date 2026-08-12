"""image generation engine schema

Revision ID: 011
Revises: 010
Create Date: 2026-08-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "image_generation_requests",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("purpose", sa.String(64), nullable=True),
        sa.Column("storyboard_shot_id", sa.String(64), nullable=True),
        sa.Column("storyboard_id", sa.String(36), nullable=True),
        sa.Column("prompt_package_id", sa.String(36), nullable=False),
        sa.Column("provider_strategy", sa.JSON(), nullable=True),
        sa.Column("variant_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("budget", sa.JSON(), nullable=True),
        sa.Column("quality", sa.JSON(), nullable=True),
        sa.Column("priority", sa.String(32), server_default="normal", nullable=False),
        sa.Column("status", sa.String(32), server_default="queued", nullable=False),
        sa.Column("idempotency_key", sa.String(256), nullable=True),
        sa.Column("image_prompt_package", sa.JSON(), nullable=True),
        sa.Column("lineage", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["storyboard_id"], ["storyboards.id"]),
        sa.ForeignKeyConstraint(["prompt_package_id"], ["prompt_packages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_image_gen_idempotency"),
    )
    op.create_index("idx_image_gen_requests_status", "image_generation_requests", ["status"])

    op.create_table(
        "image_generation_jobs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("variant_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("provider", sa.String(128), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("provider_job_id", sa.String(256), nullable=True),
        sa.Column("status", sa.String(32), server_default="queued", nullable=False),
        sa.Column("attempt", sa.Integer(), server_default="0", nullable=False),
        sa.Column("fallback_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("estimated_cost", sa.Numeric(12, 6), nullable=True),
        sa.Column("actual_cost", sa.Numeric(12, 6), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("prompt_package_id", sa.String(36), nullable=True),
        sa.Column("parent_artifact_id", sa.String(36), nullable=True),
        sa.Column("depends_on", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["request_id"], ["image_generation_requests.id"]),
        sa.ForeignKeyConstraint(["prompt_package_id"], ["prompt_packages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_image_gen_jobs_status", "image_generation_jobs", ["status"])

    op.create_table(
        "image_artifacts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("generation_job_id", sa.String(36), nullable=False),
        sa.Column("parent_artifact_id", sa.String(36), nullable=True),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("phash", sa.String(128), nullable=True),
        sa.Column("technical_qa", sa.JSON(), nullable=True),
        sa.Column("provider", sa.String(128), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("prompt_package_id", sa.String(36), nullable=True),
        sa.Column("purpose", sa.String(64), nullable=True),
        sa.Column("lineage", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["generation_job_id"], ["image_generation_jobs.id"]),
        sa.ForeignKeyConstraint(["parent_artifact_id"], ["image_artifacts.id"]),
        sa.ForeignKeyConstraint(["prompt_package_id"], ["prompt_packages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_image_artifacts_job", "image_artifacts", ["generation_job_id"])


def downgrade() -> None:
    op.drop_index("idx_image_artifacts_job", table_name="image_artifacts")
    op.drop_table("image_artifacts")
    op.drop_index("idx_image_gen_jobs_status", table_name="image_generation_jobs")
    op.drop_table("image_generation_jobs")
    op.drop_index("idx_image_gen_requests_status", table_name="image_generation_requests")
    op.drop_table("image_generation_requests")
