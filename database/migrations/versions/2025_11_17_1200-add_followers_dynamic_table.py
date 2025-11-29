"""add followers dynamic table

Revision ID: 8a2f1a7a2c9b
Revises: 2fddf8f2e4ab
Create Date: 2025-11-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '8a2f1a7a2c9b'
down_revision: Union[str, Sequence[str], None] = '2fddf8f2e4ab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "followers_dynamic",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False, unique=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("followers_count", sa.Integer(), nullable=False),
        sa.Column("follows_count", sa.Integer(), nullable=True),
        sa.Column("media_count", sa.Integer(), nullable=True),
        sa.Column(
            "raw_payload",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("timezone('UTC', now())"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_followers_dynamic_snapshot_date",
        "followers_dynamic",
        ["snapshot_date"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("idx_followers_dynamic_snapshot_date", table_name="followers_dynamic")
    op.drop_table("followers_dynamic")
