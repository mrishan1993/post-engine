"""story engine schema

Revision ID: 006
Revises: 005
Create Date: 2026-08-08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stories",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(256), nullable=True),
        sa.Column("logline", sa.Text(), nullable=True),
        sa.Column("story_type", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("target_duration_sec", sa.Integer(), nullable=True),
        sa.Column("blueprint", sa.JSON(), nullable=False),
        sa.Column("quality_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("originality_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("current_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=True),
        sa.Column("content_brief_id", sa.Integer(), nullable=True),
        sa.Column("character_ids", sa.JSON(), nullable=True),
        sa.Column("platform", sa.String(64), nullable=True),
        sa.Column("prediction_snapshot", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["content_brief_id"], ["content_briefs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_stories_status", "stories", ["status"])

    op.create_table(
        "story_versions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("story_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("blueprint", sa.JSON(), nullable=False),
        sa.Column("critic_result", sa.JSON(), nullable=True),
        sa.Column("quality_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("story_id", "version", name="uq_story_version"),
    )

    # Trend V2 already owns `story_patterns` (feature extraction).
    # Story Engine reusable structures live in `narrative_patterns`.
    op.create_table(
        "narrative_patterns",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("pattern_type", sa.String(64), nullable=True),
        sa.Column("structure", sa.JSON(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("performance_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "story_performance",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("story_id", sa.String(36), nullable=False),
        sa.Column("post_id", sa.String(36), nullable=True),
        sa.Column("video_run_id", sa.Integer(), nullable=True),
        sa.Column("views", sa.Integer(), nullable=True),
        sa.Column("retention", sa.Numeric(8, 4), nullable=True),
        sa.Column("engagement_rate", sa.Numeric(8, 4), nullable=True),
        sa.Column("share_rate", sa.Numeric(8, 4), nullable=True),
        sa.Column("comment_rate", sa.Numeric(8, 4), nullable=True),
        sa.Column("follower_conversion", sa.Numeric(8, 4), nullable=True),
        sa.Column("component_scores", sa.JSON(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"]),
        sa.ForeignKeyConstraint(["video_run_id"], ["video_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("story_performance")
    op.drop_table("narrative_patterns")
    op.drop_table("story_versions")
    op.drop_index("idx_stories_status", table_name="stories")
    op.drop_table("stories")
