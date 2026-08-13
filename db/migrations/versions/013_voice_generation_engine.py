"""voice generation engine schema

Revision ID: 013
Revises: 012
Create Date: 2026-08-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "voice_generation_requests",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("content_id", sa.String(64), nullable=True),
        sa.Column("story_id", sa.String(36), nullable=True),
        sa.Column("storyboard_id", sa.String(36), nullable=True),
        sa.Column("character_id", sa.String(36), nullable=True),
        sa.Column("voice_profile_id", sa.String(36), nullable=True),
        sa.Column("prompt_package_id", sa.String(36), nullable=True),
        sa.Column("script", sa.JSON(), nullable=False),
        sa.Column("voice_spec", sa.JSON(), nullable=True),
        sa.Column("provider_strategy", sa.JSON(), nullable=True),
        sa.Column("variant_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("budget", sa.JSON(), nullable=True),
        sa.Column("quality", sa.JSON(), nullable=True),
        sa.Column("priority", sa.String(32), server_default="normal", nullable=False),
        sa.Column("status", sa.String(32), server_default="queued", nullable=False),
        sa.Column("idempotency_key", sa.String(256), nullable=True),
        sa.Column("lineage", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"]),
        sa.ForeignKeyConstraint(["storyboard_id"], ["storyboards.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["voice_profile_id"], ["voice_profiles.id"]),
        sa.ForeignKeyConstraint(["prompt_package_id"], ["prompt_packages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_voice_gen_idempotency"),
    )
    op.create_index("idx_voice_gen_requests_status", "voice_generation_requests", ["status"])

    op.create_table(
        "voice_generation_jobs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("variant_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("provider", sa.String(128), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("provider_job_id", sa.String(256), nullable=True),
        sa.Column("provider_voice_id", sa.String(256), nullable=True),
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
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["request_id"], ["voice_generation_requests.id"]),
        sa.ForeignKeyConstraint(["prompt_package_id"], ["prompt_packages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_voice_gen_jobs_status", "voice_generation_jobs", ["status"])

    op.create_table(
        "voice_artifacts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("generation_job_id", sa.String(36), nullable=False),
        sa.Column("parent_artifact_id", sa.String(36), nullable=True),
        sa.Column("character_id", sa.String(36), nullable=True),
        sa.Column("voice_profile_id", sa.String(36), nullable=True),
        sa.Column("artifact_type", sa.String(32), server_default="dialogue", nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("duration_sec", sa.Numeric(8, 3), nullable=True),
        sa.Column("sample_rate", sa.Integer(), nullable=True),
        sa.Column("channels", sa.Integer(), nullable=True),
        sa.Column("loudness_lufs", sa.Numeric(8, 3), nullable=True),
        sa.Column("true_peak_db", sa.Numeric(8, 3), nullable=True),
        sa.Column("script_hash", sa.String(64), nullable=True),
        sa.Column("timestamps", sa.JSON(), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("technical_qa", sa.JSON(), nullable=True),
        sa.Column("provider", sa.String(128), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("prompt_package_id", sa.String(36), nullable=True),
        sa.Column("lineage", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["generation_job_id"], ["voice_generation_jobs.id"]),
        sa.ForeignKeyConstraint(["parent_artifact_id"], ["voice_artifacts.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["voice_profile_id"], ["voice_profiles.id"]),
        sa.ForeignKeyConstraint(["prompt_package_id"], ["prompt_packages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_voice_artifacts_job", "voice_artifacts", ["generation_job_id"])

    op.create_table(
        "voice_timelines",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("storyboard_id", sa.String(36), nullable=True),
        sa.Column("duration_sec", sa.Numeric(8, 3), nullable=False),
        sa.Column("segments", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), server_default="ready", nullable=False),
        sa.Column("lineage", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["storyboard_id"], ["storyboards.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_voice_timelines_storyboard", "voice_timelines", ["storyboard_id"])

    op.create_table(
        "pronunciation_entries",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("term", sa.String(256), nullable=False),
        sa.Column("language", sa.String(32), server_default="en", nullable=False),
        sa.Column("pronunciation", sa.String(512), nullable=True),
        sa.Column("phoneme", sa.String(512), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("term", "language", name="uq_pronunciation_term_lang"),
    )


def downgrade() -> None:
    op.drop_table("pronunciation_entries")
    op.drop_index("idx_voice_timelines_storyboard", table_name="voice_timelines")
    op.drop_table("voice_timelines")
    op.drop_index("idx_voice_artifacts_job", table_name="voice_artifacts")
    op.drop_table("voice_artifacts")
    op.drop_index("idx_voice_gen_jobs_status", table_name="voice_generation_jobs")
    op.drop_table("voice_generation_jobs")
    op.drop_index("idx_voice_gen_requests_status", table_name="voice_generation_requests")
    op.drop_table("voice_generation_requests")
