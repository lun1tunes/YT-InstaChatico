"""add moderation stats reports table

Revision ID: add_moderation_stats_reports
Revises: add_comment_deleted_at
Create Date: 2025-11-18 13:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "add_moderation_stats_reports"
down_revision: Union[str, Sequence[str], None] = "add_comment_deleted_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "moderation_stats_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("period_label", sa.String(length=50), nullable=False),
        sa.Column("range_start", sa.DateTime(), nullable=False),
        sa.Column("range_end", sa.DateTime(), nullable=False),
        sa.Column("payload", JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("timezone('UTC', now())"),
            nullable=False,
        ),
    )
    op.create_index("idx_moderation_stats_period", "moderation_stats_reports", ["period_label"])
    op.create_index("idx_moderation_stats_range_start", "moderation_stats_reports", ["range_start"])


def downgrade() -> None:
    op.drop_index("idx_moderation_stats_range_start", table_name="moderation_stats_reports")
    op.drop_index("idx_moderation_stats_period", table_name="moderation_stats_reports")
    op.drop_table("moderation_stats_reports")
