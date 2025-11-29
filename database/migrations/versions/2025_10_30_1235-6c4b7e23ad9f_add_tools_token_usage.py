"""Add instrument token usage table

Revision ID: 6c4b7e23ad9f
Revises: 4fa7cb6995e2
Create Date: 2025-10-30 12:35:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "6c4b7e23ad9f"
down_revision: Union[str, Sequence[str], None] = "4fa7cb6995e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "instrument_token_usage",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("timezone('UTC', now())"),
            nullable=False,
        ),
        sa.Column("tool", sa.String(length=64), nullable=False),
        sa.Column("task", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("comment_id", sa.String(length=100), nullable=True),
        sa.Column("details", JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(("comment_id",), ["instagram_comments.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_instrument_token_usage_tool_created_at",
        "instrument_token_usage",
        ["tool", "created_at"],
    )
    op.create_index(
        "ix_instrument_token_usage_comment_id",
        "instrument_token_usage",
        ["comment_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_instrument_token_usage_comment_id", table_name="instrument_token_usage")
    op.drop_index("ix_instrument_token_usage_tool_created_at", table_name="instrument_token_usage")
    op.drop_table("instrument_token_usage")
