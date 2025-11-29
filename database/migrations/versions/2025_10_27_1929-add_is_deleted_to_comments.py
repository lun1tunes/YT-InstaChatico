"""Add is_deleted flag to instagram comments

Revision ID: 4fa7cb6995e2
Revises: sync_retry_defaults
Create Date: 2025-10-27 19:29:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '4fa7cb6995e2'
down_revision: Union[str, Sequence[str], None] = 'sync_retry_defaults'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'instagram_comments',
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('instagram_comments', 'is_deleted')
