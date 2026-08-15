"""character & content universe intelligence schema

Revision ID: 024
Revises: 023
Create Date: 2026-08-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Version existing universes table (asset-layer) for intelligence versioning
    with op.batch_alter_table("universes") as batch:
        batch.add_column(sa.Column("version", sa.Integer(), server_default="1", nullable=False))
        batch.add_column(sa.Column("canon_mode", sa.String(32), server_default="canon", nullable=False))

    op.create_table(
        "character_states",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("character_id", sa.String(36), nullable=False),
        sa.Column("emotional_state", sa.JSON(), nullable=True),
        sa.Column("goals", sa.JSON(), nullable=True),
        sa.Column("fears", sa.JSON(), nullable=True),
        sa.Column("relationships_snapshot", sa.JSON(), nullable=True),
        sa.Column("unresolved_conflicts", sa.JSON(), nullable=True),
        sa.Column("recent_events", sa.JSON(), nullable=True),
        sa.Column("development_stage", sa.String(64), nullable=True),
        sa.Column("personality_scores", sa.JSON(), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_character_states_char", "character_states", ["character_id"])

    op.create_table(
        "universe_entities",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("universe_id", sa.String(36), nullable=False),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("slug", sa.String(128), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("canon_status", sa.String(32), server_default="canon", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["universe_id"], ["universes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_universe_entities_universe", "universe_entities", ["universe_id"])

    op.create_table(
        "universe_relationships",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("universe_id", sa.String(36), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("relationship_type", sa.String(64), nullable=False),
        sa.Column("strength", sa.Numeric(5, 4), nullable=True),
        sa.Column("traits", sa.JSON(), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canon_status", sa.String(32), server_default="canon", nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("history", sa.JSON(), nullable=True),
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
        sa.ForeignKeyConstraint(["universe_id"], ["universes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_universe_relationships_universe", "universe_relationships", ["universe_id"])
    op.create_index("idx_universe_relationships_source", "universe_relationships", ["source_id"])

    op.create_table(
        "universe_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("universe_id", sa.String(36), nullable=False),
        sa.Column("story_id", sa.String(36), nullable=True),
        sa.Column("episode_key", sa.String(128), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("participants", sa.JSON(), nullable=True),
        sa.Column("location", sa.String(256), nullable=True),
        sa.Column("action", sa.String(256), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("consequences", sa.JSON(), nullable=True),
        sa.Column("emotional_impact", sa.Numeric(5, 4), nullable=True),
        sa.Column("affected_relationships", sa.JSON(), nullable=True),
        sa.Column("canon_status", sa.String(32), server_default="provisional", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["universe_id"], ["universes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_universe_events_universe", "universe_events", ["universe_id"])

    op.create_table(
        "creative_memories",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("universe_id", sa.String(36), nullable=False),
        sa.Column("character_id", sa.String(36), nullable=True),
        sa.Column("event_id", sa.String(36), nullable=True),
        sa.Column("memory_type", sa.String(64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("importance", sa.Numeric(5, 4), nullable=True),
        sa.Column("emotional_weight", sa.Numeric(5, 4), nullable=True),
        sa.Column("recency", sa.Numeric(5, 4), nullable=True),
        sa.Column("recall_probability", sa.Numeric(5, 4), nullable=True),
        sa.Column("canon_status", sa.String(32), server_default="canon", nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["universe_id"], ["universes.id"]),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["universe_events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_creative_memories_char", "creative_memories", ["character_id"])

    op.create_table(
        "canon_facts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("universe_id", sa.String(36), nullable=False),
        sa.Column("subject", sa.String(256), nullable=False),
        sa.Column("predicate", sa.String(128), nullable=False),
        sa.Column("object", sa.String(512), nullable=False),
        sa.Column("source", sa.String(256), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("status", sa.String(32), server_default="canon", nullable=False),
        sa.Column("authority", sa.String(64), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=True),
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
        sa.ForeignKeyConstraint(["universe_id"], ["universes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_canon_facts_universe", "canon_facts", ["universe_id"])
    op.create_index("idx_canon_facts_subject", "canon_facts", ["subject"])

    op.create_table(
        "story_threads",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("universe_id", sa.String(36), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("participants", sa.JSON(), nullable=True),
        sa.Column("importance", sa.Numeric(5, 4), nullable=True),
        sa.Column("audience_interest", sa.Numeric(5, 4), nullable=True),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("potential_payoff", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["universe_id"], ["universes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_story_threads_universe", "story_threads", ["universe_id"])

    op.create_table(
        "universe_snapshots",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("universe_id", sa.String(36), nullable=False),
        sa.Column("campaign_id", sa.String(36), nullable=True),
        sa.Column("episode_id", sa.String(36), nullable=True),
        sa.Column("label", sa.String(256), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["universe_id"], ["universes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_universe_snapshots_universe", "universe_snapshots", ["universe_id"])

    op.create_table(
        "continuity_conflicts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("universe_id", sa.String(36), nullable=False),
        sa.Column("severity", sa.String(16), server_default="warning", nullable=False),
        sa.Column("conflict_type", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("proposed", sa.JSON(), nullable=True),
        sa.Column("existing", sa.JSON(), nullable=True),
        sa.Column("suggested_revision", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), server_default="open", nullable=False),
        sa.Column("resolution", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["universe_id"], ["universes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_continuity_conflicts_universe", "continuity_conflicts", ["universe_id"])

    op.create_table(
        "creative_decisions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("universe_id", sa.String(36), nullable=True),
        sa.Column("entity_id", sa.String(36), nullable=True),
        sa.Column("change", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("approved_by", sa.String(64), nullable=True),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_creative_decisions_universe", "creative_decisions", ["universe_id"])

    op.create_table(
        "character_perceptions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("character_id", sa.String(36), nullable=False),
        sa.Column("universe_id", sa.String(36), nullable=True),
        sa.Column("perceived_traits", sa.JSON(), nullable=True),
        sa.Column("affinity", sa.Numeric(8, 4), nullable=True),
        sa.Column("sentiment", sa.JSON(), nullable=True),
        sa.Column("theories", sa.JSON(), nullable=True),
        sa.Column("requests", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(64), server_default="audience", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["universe_id"], ["universes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_character_perceptions_char", "character_perceptions", ["character_id"])

    op.create_table(
        "character_appearances",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("character_id", sa.String(36), nullable=False),
        sa.Column("universe_id", sa.String(36), nullable=True),
        sa.Column("content_id", sa.String(64), nullable=True),
        sa.Column("episode_key", sa.String(128), nullable=True),
        sa.Column("role", sa.String(64), nullable=True),
        sa.Column(
            "appeared_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["character_id"], ["characters.id"]),
        sa.ForeignKeyConstraint(["universe_id"], ["universes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_character_appearances_char", "character_appearances", ["character_id"])


def downgrade() -> None:
    op.drop_index("idx_character_appearances_char", table_name="character_appearances")
    op.drop_table("character_appearances")
    op.drop_index("idx_character_perceptions_char", table_name="character_perceptions")
    op.drop_table("character_perceptions")
    op.drop_index("idx_creative_decisions_universe", table_name="creative_decisions")
    op.drop_table("creative_decisions")
    op.drop_index("idx_continuity_conflicts_universe", table_name="continuity_conflicts")
    op.drop_table("continuity_conflicts")
    op.drop_index("idx_universe_snapshots_universe", table_name="universe_snapshots")
    op.drop_table("universe_snapshots")
    op.drop_index("idx_story_threads_universe", table_name="story_threads")
    op.drop_table("story_threads")
    op.drop_index("idx_canon_facts_subject", table_name="canon_facts")
    op.drop_index("idx_canon_facts_universe", table_name="canon_facts")
    op.drop_table("canon_facts")
    op.drop_index("idx_creative_memories_char", table_name="creative_memories")
    op.drop_table("creative_memories")
    op.drop_index("idx_universe_events_universe", table_name="universe_events")
    op.drop_table("universe_events")
    op.drop_index("idx_universe_relationships_source", table_name="universe_relationships")
    op.drop_index("idx_universe_relationships_universe", table_name="universe_relationships")
    op.drop_table("universe_relationships")
    op.drop_index("idx_universe_entities_universe", table_name="universe_entities")
    op.drop_table("universe_entities")
    op.drop_index("idx_character_states_char", table_name="character_states")
    op.drop_table("character_states")
    with op.batch_alter_table("universes") as batch:
        batch.drop_column("canon_mode")
        batch.drop_column("version")
