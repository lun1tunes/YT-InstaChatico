"""add expired tokens table

Revision ID: 7d4e00d4831a
Revises: 928264980162
Create Date: 2025-11-04 09:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d4e00d4831a'
down_revision: Union[str, Sequence[str], None] = '928264980162'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'expired_tokens',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('jti', sa.String(length=255), nullable=False),
        sa.Column('expired_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ux_expired_tokens_jti', 'expired_tokens', ['jti'], unique=True)


def downgrade() -> None:
    op.drop_index('ux_expired_tokens_jti', table_name='expired_tokens')
    op.drop_table('expired_tokens')
