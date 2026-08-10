"""storyboard engine schema

Revision ID: 007
Revises: 006
Create Date: 2026-08-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "storyboards",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("story_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(64), nullable=True),
        sa.Column("duration_sec", sa.Numeric(8, 3), nullable=True),
        sa.Column("global_direction", sa.JSON(), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.Column("quality_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("critic_result", sa.JSON(), nullable=True),
        sa.Column("prediction_snapshot", sa.JSON(), nullable=True),
        sa.Column("story_version", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("story_id", "version", name="uq_storyboard_story_version"),
    )
    op.create_index("idx_storyboards_status", "storyboards", ["status"])

    op.create_table(
        "storyboard_scenes",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("storyboard_id", sa.String(36), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("start_time_sec", sa.Numeric(8, 3), nullable=True),
        sa.Column("end_time_sec", sa.Numeric(8, 3), nullable=True),
        sa.Column("narrative_function", sa.String(64), nullable=True),
        sa.Column("emotional_state", sa.JSON(), nullable=True),
        sa.Column("scene_config", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["storyboard_id"], ["storyboards.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_storyboard_scenes_board", "storyboard_scenes", ["storyboard_id"])

    op.create_table(
        "storyboard_shots",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("scene_id", sa.String(36), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("start_time_sec", sa.Numeric(8, 3), nullable=True),
        sa.Column("end_time_sec", sa.Numeric(8, 3), nullable=True),
        sa.Column("shot_config", sa.JSON(), nullable=False),
        sa.Column("generation_config", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["scene_id"], ["storyboard_scenes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_storyboard_shots_scene", "storyboard_shots", ["scene_id"])

    op.create_table(
        "storyboard_assets",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("storyboard_id", sa.String(36), nullable=False),
        sa.Column("shot_id", sa.String(36), nullable=True),
        sa.Column("asset_id", sa.String(36), nullable=True),
        sa.Column("asset_role", sa.String(64), nullable=True),
        sa.Column("required", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["storyboard_id"], ["storyboards.id"]),
        sa.ForeignKeyConstraint(["shot_id"], ["storyboard_shots.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("storyboard_assets")
    op.drop_index("idx_storyboard_shots_scene", table_name="storyboard_shots")
    op.drop_table("storyboard_shots")
    op.drop_index("idx_storyboard_scenes_board", table_name="storyboard_scenes")
    op.drop_table("storyboard_scenes")
    op.drop_index("idx_storyboards_status", table_name="storyboards")
    op.drop_table("storyboards")
