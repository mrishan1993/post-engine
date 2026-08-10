"""asset and character management engine

Revision ID: 005
Revises: 004
Create Date: 2026-08-08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "universes",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("rules", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "characters",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("universe_id", sa.String(36), nullable=True),
        sa.Column("canonical_data", sa.JSON(), nullable=False),
        sa.Column("current_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["universe_id"], ["universes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("idx_characters_status", "characters", ["status"])

    op.create_table(
        "character_versions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("character_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("canonical_data", sa.JSON(), nullable=False),
        sa.Column("change_log", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("character_id", "version", name="uq_character_version"),
    )

    op.create_table(
        "voice_profiles",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("characteristics", sa.JSON(), nullable=True),
        sa.Column("provider_mappings", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "creative_styles",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "assets",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("asset_type", sa.String(64), nullable=False),
        sa.Column("name", sa.String(256), nullable=True),
        sa.Column("storage_uri", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("provider", sa.String(128), nullable=True),
        sa.Column("provider_asset_id", sa.String(256), nullable=True),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("parent_asset_id", sa.String(36), nullable=True),
        sa.Column("quality", sa.JSON(), nullable=True),
        sa.Column("owner", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["parent_asset_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_assets_type_status", "assets", ["asset_type", "status"])
    op.create_index("idx_assets_name", "assets", ["name"])

    op.create_table(
        "asset_relationships",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("relationship_type", sa.String(64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_asset_rel_source", "asset_relationships", ["source_id", "relationship_type"])
    op.create_index("idx_asset_rel_target", "asset_relationships", ["target_id", "relationship_type"])

    op.create_table(
        "scenes",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("story_id", sa.String(36), nullable=True),
        sa.Column("sequence_number", sa.Integer(), nullable=True),
        sa.Column("scene_config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "creative_configurations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(256), nullable=True),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "asset_packs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_type", sa.String(64), nullable=True),
        sa.Column("owner_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "asset_pack_members",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("pack_id", sa.String(36), nullable=False),
        sa.Column("asset_id", sa.String(36), nullable=False),
        sa.Column("role", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["pack_id"], ["asset_packs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pack_id", "asset_id", name="uq_pack_asset"),
    )

    op.create_table(
        "character_memory",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("character_id", sa.String(36), nullable=False),
        sa.Column("episode_key", sa.String(128), nullable=False),
        sa.Column("memory_text", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_character_memory_char", "character_memory", ["character_id", "episode_key"])

    op.create_table(
        "universe_memory",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("universe_id", sa.String(36), nullable=False),
        sa.Column("memory_key", sa.String(128), nullable=False),
        sa.Column("memory_text", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["universe_id"], ["universes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "asset_performance",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("asset_id", sa.String(36), nullable=False),
        sa.Column("character_id", sa.String(36), nullable=True),
        sa.Column("posts_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("avg_views", sa.Numeric(14, 2), nullable=True),
        sa.Column("avg_retention", sa.Numeric(6, 4), nullable=True),
        sa.Column("total_views", sa.Integer(), server_default="0", nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_asset_perf", "asset_performance", ["asset_id", "updated_at"])


def downgrade() -> None:
    for table in (
        "asset_performance",
        "universe_memory",
        "character_memory",
        "asset_pack_members",
        "asset_packs",
        "creative_configurations",
        "scenes",
        "asset_relationships",
        "assets",
        "creative_styles",
        "voice_profiles",
        "character_versions",
        "characters",
        "universes",
    ):
        op.drop_table(table)
