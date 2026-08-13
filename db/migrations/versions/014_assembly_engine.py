"""assembly engine schema

Revision ID: 014
Revises: 013
Create Date: 2026-08-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assemblies",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("content_id", sa.String(64), nullable=False),
        sa.Column("storyboard_id", sa.String(36), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("specification", sa.JSON(), nullable=False),
        sa.Column("timeline", sa.JSON(), nullable=True),
        sa.Column("duration_sec", sa.Numeric(8, 3), nullable=True),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("platform_profile", sa.String(128), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_id", "version", name="uq_assembly_content_version"),
    )
    op.create_index("idx_assemblies_status", "assemblies", ["status"])

    op.create_table(
        "render_jobs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("assembly_id", sa.String(36), nullable=False),
        sa.Column("render_profile", sa.String(128), server_default="instagram_reels_v1", nullable=False),
        sa.Column("quality", sa.String(32), server_default="final", nullable=False),
        sa.Column("status", sa.String(32), server_default="queued", nullable=False),
        sa.Column("progress", sa.Numeric(5, 2), server_default="0", nullable=False),
        sa.Column("attempt", sa.Integer(), server_default="0", nullable=False),
        sa.Column("ffmpeg_version", sa.String(64), nullable=True),
        sa.Column("ffmpeg_used", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["assembly_id"], ["assemblies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_render_jobs_status", "render_jobs", ["status"])

    op.create_table(
        "rendered_artifacts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("render_id", sa.String(36), nullable=False),
        sa.Column("assembly_id", sa.String(36), nullable=True),
        sa.Column("artifact_type", sa.String(32), server_default="final_video", nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("fps", sa.Numeric(8, 3), nullable=True),
        sa.Column("duration_sec", sa.Numeric(8, 3), nullable=True),
        sa.Column("video_codec", sa.String(64), nullable=True),
        sa.Column("audio_codec", sa.String(64), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("technical_qa", sa.JSON(), nullable=True),
        sa.Column("render_metadata", sa.JSON(), nullable=True),
        sa.Column("lineage", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["render_id"], ["render_jobs.id"]),
        sa.ForeignKeyConstraint(["assembly_id"], ["assemblies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_rendered_artifacts_render", "rendered_artifacts", ["render_id"])


def downgrade() -> None:
    op.drop_index("idx_rendered_artifacts_render", table_name="rendered_artifacts")
    op.drop_table("rendered_artifacts")
    op.drop_index("idx_render_jobs_status", table_name="render_jobs")
    op.drop_table("render_jobs")
    op.drop_index("idx_assemblies_status", table_name="assemblies")
    op.drop_table("assemblies")
