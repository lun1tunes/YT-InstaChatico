"""add stats reports table

Revision ID: 2fddf8f2e4ab
Revises: 7d4e00d4831a
Create Date: 2025-11-16 15:38:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '2fddf8f2e4ab'
down_revision: Union[str, Sequence[str], None] = '7d4e00d4831a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stats_reports",
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
    op.create_index("idx_stats_reports_period", "stats_reports", ["period_label"])
    op.create_index("idx_stats_reports_range_start", "stats_reports", ["range_start"])


def downgrade() -> None:
    op.drop_index('idx_stats_reports_range_start', table_name='stats_reports')
    op.drop_index('idx_stats_reports_period', table_name='stats_reports')
    op.drop_table('stats_reports')
