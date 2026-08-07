"""trend engine v2 viral intelligence schema

Revision ID: 003
Revises: 002
Create Date: 2026-08-07

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "raw_content",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(256), nullable=True),
        sa.Column("url", sa.String(1024), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("creator_handle", sa.String(256), nullable=True),
        sa.Column("platform_metadata", sa.JSON(), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("trend_signal_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["trend_signal_id"], ["trend_signals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_raw_content_source_collected", "raw_content", ["source", "collected_at"])
    op.create_index("idx_raw_content_external", "raw_content", ["source", "external_id"])

    op.create_table(
        "content_features",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("raw_content_id", sa.Integer(), nullable=False),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("hook", sa.JSON(), nullable=True),
        sa.Column("story_arc", sa.JSON(), nullable=True),
        sa.Column("emotion", sa.JSON(), nullable=True),
        sa.Column("visual_style", sa.JSON(), nullable=True),
        sa.Column("audio_style", sa.JSON(), nullable=True),
        sa.Column("editing_style", sa.JSON(), nullable=True),
        sa.Column("format", sa.String(64), nullable=True),
        sa.Column("audience", sa.String(128), nullable=True),
        sa.Column("topics", sa.JSON(), nullable=True),
        sa.Column("hashtags", sa.JSON(), nullable=True),
        sa.Column("cta", sa.Text(), nullable=True),
        sa.Column("velocity", sa.JSON(), nullable=True),
        sa.Column("extracted_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["raw_content_id"], ["raw_content.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("raw_content_id"),
    )

    op.create_table(
        "comment_sentiment",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("raw_content_id", sa.Integer(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("requests", sa.JSON(), nullable=True),
        sa.Column("questions", sa.JSON(), nullable=True),
        sa.Column("sentiment_scores", sa.JSON(), nullable=True),
        sa.Column("future_opportunities", sa.JSON(), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["raw_content_id"], ["raw_content.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    for table, cols in (
        ("hook_library", [
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("hook_type", sa.String(64), nullable=False),
            sa.Column("example_text", sa.Text(), nullable=True),
            sa.Column("emotion", sa.String(64), nullable=True),
            sa.Column("source_feature_id", sa.Integer(), nullable=True),
            sa.Column("use_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        ]),
        ("story_patterns", [
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("pattern_name", sa.String(128), nullable=False),
            sa.Column("beats", sa.JSON(), nullable=True),
            sa.Column("source_feature_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        ]),
        ("visual_patterns", [
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("pattern_name", sa.String(128), nullable=False),
            sa.Column("features", sa.JSON(), nullable=True),
            sa.Column("meme_type", sa.String(64), nullable=True),
            sa.Column("source_feature_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        ]),
        ("audio_patterns", [
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("pattern_name", sa.String(128), nullable=False),
            sa.Column("features", sa.JSON(), nullable=True),
            sa.Column("meme_type", sa.String(64), nullable=True),
            sa.Column("source_feature_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        ]),
    ):
        op.create_table(table, *cols, sa.PrimaryKeyConstraint("id"))
        if table == "hook_library":
            op.create_foreign_key("fk_hook_feature", "hook_library", "content_features", ["source_feature_id"], ["id"])
        elif table == "story_patterns":
            op.create_foreign_key("fk_story_feature", "story_patterns", "content_features", ["source_feature_id"], ["id"])
        elif table == "visual_patterns":
            op.create_foreign_key("fk_visual_feature", "visual_patterns", "content_features", ["source_feature_id"], ["id"])
        elif table == "audio_patterns":
            op.create_foreign_key("fk_audio_feature", "audio_patterns", "content_features", ["source_feature_id"], ["id"])

    op.create_table(
        "emotion_vectors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("raw_content_id", sa.Integer(), nullable=False),
        sa.Column("scores", sa.JSON(), nullable=True),
        sa.Column("dominant", sa.String(64), nullable=True),
        sa.Column("progression", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["raw_content_id"], ["raw_content.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "trend_lifecycle",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("pattern_key", sa.String(256), nullable=False),
        sa.Column("stage", sa.String(32), server_default="emerging", nullable=False),
        sa.Column("confidence", sa.Numeric(5, 3), server_default="0", nullable=False),
        sa.Column("platforms", sa.JSON(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pattern_key"),
    )
    op.create_index("idx_trend_lifecycle_stage", "trend_lifecycle", ["stage", "updated_at"])

    op.create_table(
        "knowledge_graph_nodes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("node_type", sa.String(64), nullable=False),
        sa.Column("label", sa.String(256), nullable=False),
        sa.Column("properties", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_type", "label", name="uq_kg_node_type_label"),
    )

    op.create_table(
        "knowledge_graph_edges",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("from_node_id", sa.Integer(), nullable=False),
        sa.Column("to_node_id", sa.Integer(), nullable=False),
        sa.Column("relation", sa.String(64), nullable=False),
        sa.Column("weight", sa.Numeric(6, 3), server_default="1", nullable=False),
        sa.Column("properties", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["from_node_id"], ["knowledge_graph_nodes.id"]),
        sa.ForeignKeyConstraint(["to_node_id"], ["knowledge_graph_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "opportunity_scores",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vertical_slug", sa.String(64), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("score", sa.Numeric(6, 2), nullable=False),
        sa.Column("score_breakdown", sa.JSON(), nullable=True),
        sa.Column("opportunity", sa.JSON(), nullable=True),
        sa.Column("lifecycle_stage", sa.String(32), nullable=True),
        sa.Column("pattern_key", sa.String(256), nullable=True),
        sa.Column("content_brief_ids", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_opportunity_scores_vertical", "opportunity_scores", ["vertical_slug", "score"])

    op.create_table(
        "viral_predictions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("content_brief_id", sa.Integer(), nullable=True),
        sa.Column("predicted_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("actual_views", sa.Integer(), nullable=True),
        sa.Column("actual_ctr", sa.Numeric(6, 4), nullable=True),
        sa.Column("actual_watch_time_sec", sa.Integer(), nullable=True),
        sa.Column("actual_shares", sa.Integer(), nullable=True),
        sa.Column("actual_comments", sa.Integer(), nullable=True),
        sa.Column("actual_subscribers", sa.Integer(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["content_brief_id"], ["content_briefs.id"]),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunity_scores.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "creator_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("handle", sa.String(256), nullable=False),
        sa.Column("display_name", sa.String(256), nullable=True),
        sa.Column("niche_tags", sa.JSON(), nullable=True),
        sa.Column("posting_cadence", sa.JSON(), nullable=True),
        sa.Column("is_competitor", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_managed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "competitor_channels",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("channel_id", sa.String(256), nullable=False),
        sa.Column("name", sa.String(256), nullable=True),
        sa.Column("vertical_slugs", sa.JSON(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    for table in (
        "competitor_channels",
        "creator_profiles",
        "viral_predictions",
        "opportunity_scores",
        "knowledge_graph_edges",
        "knowledge_graph_nodes",
        "trend_lifecycle",
        "emotion_vectors",
        "audio_patterns",
        "visual_patterns",
        "story_patterns",
        "hook_library",
        "comment_sentiment",
        "content_features",
        "raw_content",
    ):
        op.drop_table(table)
