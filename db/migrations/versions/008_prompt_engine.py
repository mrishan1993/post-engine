"""prompt engine schema

Revision ID: 008
Revises: 007
Create Date: 2026-08-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prompt_specs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("modality", sa.String(32), nullable=False),
        sa.Column("canonical_spec", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("storyboard_id", sa.String(36), nullable=True),
        sa.Column("storyboard_shot_id", sa.String(64), nullable=True),
        sa.Column("story_id", sa.String(36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["storyboard_id"], ["storyboards.id"]),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_prompt_specs_modality", "prompt_specs", ["modality"])

    op.create_table(
        "prompt_packages",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("prompt_spec_id", sa.String(36), nullable=True),
        sa.Column("provider", sa.String(128), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("modality", sa.String(32), nullable=True),
        sa.Column("provider_prompt", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("quality_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("estimated_cost", sa.Numeric(12, 6), nullable=True),
        sa.Column("estimated_latency_sec", sa.Numeric(10, 3), nullable=True),
        sa.Column("validation_result", sa.JSON(), nullable=True),
        sa.Column("critic_result", sa.JSON(), nullable=True),
        sa.Column("lineage", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(32), server_default="compiled", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["prompt_spec_id"], ["prompt_specs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_prompt_packages_provider", "prompt_packages", ["provider"])

    op.create_table(
        "prompt_components",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("component_type", sa.String(64), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("performance_metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "prompt_experiments",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("storyboard_shot_id", sa.String(64), nullable=True),
        sa.Column("variants", sa.JSON(), nullable=False),
        sa.Column("selected_variant", sa.String(36), nullable=True),
        sa.Column("results", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("prompt_experiments")
    op.drop_table("prompt_components")
    op.drop_index("idx_prompt_packages_provider", table_name="prompt_packages")
    op.drop_table("prompt_packages")
    op.drop_index("idx_prompt_specs_modality", table_name="prompt_specs")
    op.drop_table("prompt_specs")
