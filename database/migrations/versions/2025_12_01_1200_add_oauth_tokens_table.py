"""add oauth tokens table

Revision ID: add_oauth_tokens_table
Revises: add_is_ai_generated_to_answers
Create Date: 2025-12-01 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_oauth_tokens_table"
down_revision = "add_is_ai_generated_to_answers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oauth_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("account_id", sa.String(length=255), nullable=False),
        sa.Column("access_token_encrypted", sa.String(length=2048), nullable=False),
        sa.Column("refresh_token_encrypted", sa.String(length=2048), nullable=False),
        sa.Column("token_type", sa.String(length=50), nullable=True),
        sa.Column("scope", sa.String(length=1024), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("provider", "account_id", name="uq_oauth_provider_account"),
    )
    op.create_index("ix_oauth_tokens_provider", "oauth_tokens", ["provider"])
    op.create_index("ix_oauth_tokens_account_id", "oauth_tokens", ["account_id"])
    op.create_index("ix_oauth_tokens_provider_account", "oauth_tokens", ["provider", "account_id"])
    op.create_index("ix_oauth_tokens_expires_at", "oauth_tokens", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_oauth_tokens_expires_at", table_name="oauth_tokens")
    op.drop_index("ix_oauth_tokens_provider_account", table_name="oauth_tokens")
    op.drop_index("ix_oauth_tokens_account_id", table_name="oauth_tokens")
    op.drop_index("ix_oauth_tokens_provider", table_name="oauth_tokens")
    op.drop_table("oauth_tokens")
