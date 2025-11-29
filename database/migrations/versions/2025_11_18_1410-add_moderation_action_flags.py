"""add moderation action flags

Revision ID: add_moderation_action_flags
Revises: add_moderation_stats_reports
Create Date: 2025-11-18 14:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_moderation_action_flags"
down_revision: Union[str, Sequence[str], None] = "add_moderation_stats_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "instagram_comments",
        sa.Column("hidden_by_ai", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "instagram_comments",
        sa.Column("deleted_by_ai", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("instagram_comments", "hidden_by_ai", server_default=None)
    op.alter_column("instagram_comments", "deleted_by_ai", server_default=None)


def downgrade() -> None:
    op.drop_column("instagram_comments", "deleted_by_ai")
    op.drop_column("instagram_comments", "hidden_by_ai")
