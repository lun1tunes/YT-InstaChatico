"""add title column to media

Revision ID: add_title_to_media
Revises: add_oauth_tokens_table
Create Date: 2025-12-02 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_title_to_media"
down_revision = "add_oauth_tokens_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("media", sa.Column("title", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("media", "title")
