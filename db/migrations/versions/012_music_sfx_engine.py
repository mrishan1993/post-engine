"""music & sfx engine schema

Revision ID: 012
Revises: 011
Create Date: 2026-08-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "music_generation_requests",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("content_id", sa.String(64), nullable=True),
        sa.Column("story_id", sa.String(36), nullable=True),
        sa.Column("storyboard_id", sa.String(36), nullable=True),
        sa.Column("prompt_package_id", sa.String(36), nullable=True),
        sa.Column("audio_blueprint", sa.JSON(), nullable=False),
        sa.Column("music_spec", sa.JSON(), nullable=True),
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
        sa.ForeignKeyConstraint(["prompt_package_id"], ["prompt_packages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_music_gen_idempotency"),
    )
    op.create_index("idx_music_gen_requests_status", "music_generation_requests", ["status"])

    op.create_table(
        "music_generation_jobs",
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
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["request_id"], ["music_generation_requests.id"]),
        sa.ForeignKeyConstraint(["prompt_package_id"], ["prompt_packages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_music_gen_jobs_status", "music_generation_jobs", ["status"])

    op.create_table(
        "audio_artifacts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("generation_job_id", sa.String(36), nullable=True),
        sa.Column("artifact_type", sa.String(32), server_default="music", nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("duration_sec", sa.Numeric(8, 3), nullable=True),
        sa.Column("sample_rate", sa.Integer(), nullable=True),
        sa.Column("channels", sa.Integer(), nullable=True),
        sa.Column("loudness_lufs", sa.Numeric(8, 3), nullable=True),
        sa.Column("true_peak_db", sa.Numeric(8, 3), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("technical_qa", sa.JSON(), nullable=True),
        sa.Column("provider", sa.String(128), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("prompt_package_id", sa.String(36), nullable=True),
        sa.Column("sfx_library_id", sa.String(64), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("lineage", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["generation_job_id"], ["music_generation_jobs.id"]),
        sa.ForeignKeyConstraint(["prompt_package_id"], ["prompt_packages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audio_artifacts_job", "audio_artifacts", ["generation_job_id"])

    op.create_table(
        "sfx_library_assets",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("subtype", sa.String(64), nullable=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("duration_sec", sa.Numeric(8, 3), server_default="1.0", nullable=False),
        sa.Column("intensity", sa.Numeric(4, 3), server_default="0.7", nullable=False),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("storage_uri", sa.Text(), nullable=True),
        sa.Column("licensed", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("reuse_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_sfx_library_category", "sfx_library_assets", ["category"])

    op.create_table(
        "audio_timelines",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("storyboard_id", sa.String(36), nullable=True),
        sa.Column("music_request_id", sa.String(36), nullable=True),
        sa.Column("duration_sec", sa.Numeric(8, 3), nullable=False),
        sa.Column("tracks", sa.JSON(), nullable=False),
        sa.Column("beat_grid", sa.JSON(), nullable=True),
        sa.Column("voice_windows", sa.JSON(), nullable=True),
        sa.Column("ducking", sa.JSON(), nullable=True),
        sa.Column("loudness_profile", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(32), server_default="ready", nullable=False),
        sa.Column("lineage", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["storyboard_id"], ["storyboards.id"]),
        sa.ForeignKeyConstraint(["music_request_id"], ["music_generation_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audio_timelines_storyboard", "audio_timelines", ["storyboard_id"])


def downgrade() -> None:
    op.drop_index("idx_audio_timelines_storyboard", table_name="audio_timelines")
    op.drop_table("audio_timelines")
    op.drop_index("idx_sfx_library_category", table_name="sfx_library_assets")
    op.drop_table("sfx_library_assets")
    op.drop_index("idx_audio_artifacts_job", table_name="audio_artifacts")
    op.drop_table("audio_artifacts")
    op.drop_index("idx_music_gen_jobs_status", table_name="music_generation_jobs")
    op.drop_table("music_generation_jobs")
    op.drop_index("idx_music_gen_requests_status", table_name="music_generation_requests")
    op.drop_table("music_generation_requests")
