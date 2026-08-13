"""publishing engine schema

Revision ID: 015
Revises: 014
Create Date: 2026-08-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "social_accounts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("platform", sa.String(64), nullable=False),
        sa.Column("external_account_id", sa.String(256), nullable=False),
        sa.Column("display_name", sa.String(256), nullable=True),
        sa.Column("username", sa.String(256), nullable=True),
        sa.Column("timezone", sa.String(64), server_default="UTC", nullable=False),
        sa.Column("status", sa.String(32), server_default="connected", nullable=False),
        sa.Column("token_status", sa.String(32), server_default="active", nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=True),
        sa.Column("capabilities", sa.JSON(), nullable=True),
        sa.Column("default_settings", sa.JSON(), nullable=True),
        sa.Column("character_slug", sa.String(128), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform", "external_account_id", name="uq_social_platform_external"),
    )
    op.create_index("idx_social_accounts_platform", "social_accounts", ["platform"])

    op.create_table(
        "social_credentials",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("social_account_id", sa.String(36), nullable=False),
        sa.Column("credential_reference", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_status", sa.String(32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["social_account_id"], ["social_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_social_credentials_account", "social_credentials", ["social_account_id"])

    op.create_table(
        "publishing_plans",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("content_id", sa.String(64), nullable=False),
        sa.Column("assembly_id", sa.String(36), nullable=True),
        sa.Column("master_artifact_id", sa.String(36), nullable=True),
        sa.Column("cover_artifact_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("schedule", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("approval", sa.JSON(), nullable=True),
        sa.Column("policy", sa.JSON(), nullable=True),
        sa.Column("platforms", sa.JSON(), nullable=True),
        sa.Column("lineage", sa.JSON(), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
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
        sa.ForeignKeyConstraint(["assembly_id"], ["assemblies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_publishing_plan_idempotency"),
    )
    op.create_index("idx_publishing_plans_status", "publishing_plans", ["status"])
    op.create_index("idx_publishing_plans_content", "publishing_plans", ["content_id"])

    op.create_table(
        "publishing_jobs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("publishing_plan_id", sa.String(36), nullable=False),
        sa.Column("platform", sa.String(64), nullable=False),
        sa.Column("social_account_id", sa.String(36), nullable=False),
        sa.Column("platform_package", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(32), server_default="queued", nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt", sa.Integer(), server_default="0", nullable=False),
        sa.Column("external_media_id", sa.String(256), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["publishing_plan_id"], ["publishing_plans.id"]),
        sa.ForeignKeyConstraint(["social_account_id"], ["social_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_publishing_job_idempotency"),
    )
    op.create_index("idx_publishing_jobs_status", "publishing_jobs", ["status"])
    op.create_index("idx_publishing_jobs_plan", "publishing_jobs", ["publishing_plan_id"])

    op.create_table(
        "publication_receipts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("publishing_job_id", sa.String(36), nullable=False),
        sa.Column("publishing_plan_id", sa.String(36), nullable=True),
        sa.Column("content_id", sa.String(64), nullable=True),
        sa.Column("platform", sa.String(64), nullable=False),
        sa.Column("social_account_id", sa.String(36), nullable=True),
        sa.Column("external_post_id", sa.String(256), nullable=True),
        sa.Column("external_media_id", sa.String(256), nullable=True),
        sa.Column("post_url", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_response", sa.JSON(), nullable=True),
        sa.Column("lineage", sa.JSON(), nullable=True),
        sa.Column("legacy_publication_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["publishing_job_id"], ["publishing_jobs.id"]),
        sa.ForeignKeyConstraint(["publishing_plan_id"], ["publishing_plans.id"]),
        sa.ForeignKeyConstraint(["social_account_id"], ["social_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "platform", "external_post_id", name="uq_publication_platform_external_post"
        ),
    )
    op.create_index("idx_publication_receipts_job", "publication_receipts", ["publishing_job_id"])


def downgrade() -> None:
    op.drop_index("idx_publication_receipts_job", table_name="publication_receipts")
    op.drop_table("publication_receipts")
    op.drop_index("idx_publishing_jobs_plan", table_name="publishing_jobs")
    op.drop_index("idx_publishing_jobs_status", table_name="publishing_jobs")
    op.drop_table("publishing_jobs")
    op.drop_index("idx_publishing_plans_content", table_name="publishing_plans")
    op.drop_index("idx_publishing_plans_status", table_name="publishing_plans")
    op.drop_table("publishing_plans")
    op.drop_index("idx_social_credentials_account", table_name="social_credentials")
    op.drop_table("social_credentials")
    op.drop_index("idx_social_accounts_platform", table_name="social_accounts")
    op.drop_table("social_accounts")
