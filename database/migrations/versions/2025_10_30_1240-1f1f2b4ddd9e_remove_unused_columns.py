"""Remove unused columns and indexes from instrument token usage

Revision ID: 1f1f2b4ddd9e
Revises: 6c4b7e23ad9f
Create Date: 2025-10-30 12:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(idx["name"] == index_name for idx in inspector.get_indexes(table_name))


# revision identifiers, used by Alembic.
revision: str = "1f1f2b4ddd9e"
down_revision: Union[str, Sequence[str], None] = "6c4b7e23ad9f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if _index_exists("instrument_token_usage", "ix_instrument_token_usage_media_id"):
        op.drop_index("ix_instrument_token_usage_media_id", table_name="instrument_token_usage")

    for column in ("media_id", "request_id", "tokens_total"):
        if _column_exists("instrument_token_usage", column):
            op.drop_column("instrument_token_usage", column)


def downgrade() -> None:
    op.add_column(
        "instrument_token_usage",
        sa.Column("tokens_total", sa.Integer(), nullable=True),
    )
    op.add_column(
        "instrument_token_usage",
        sa.Column("request_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "instrument_token_usage",
        sa.Column("media_id", sa.String(length=100), nullable=True),
    )
    op.create_index(
        "ix_instrument_token_usage_media_id",
        "instrument_token_usage",
        ["media_id"],
    )
