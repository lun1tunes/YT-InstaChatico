"""add deleted_at column to instagram_comments

Revision ID: add_comment_deleted_at
Revises: 8a2f1a7a2c9b
Create Date: 2025-11-18 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_comment_deleted_at"
down_revision: Union[str, Sequence[str], None] = "8a2f1a7a2c9b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "instagram_comments",
        sa.Column("deleted_at", sa.DateTime(), nullable=True, comment="Timestamp when comment was deleted"),
    )


def downgrade() -> None:
    op.drop_column("instagram_comments", "deleted_at")
