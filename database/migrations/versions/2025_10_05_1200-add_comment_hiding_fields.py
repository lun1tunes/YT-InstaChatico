"""add comment hiding fields to instagram_comments

Revision ID: add_comment_hiding_fields
Revises: 009dc27cce2b
Create Date: 2025-10-05 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_comment_hiding_fields'
down_revision: Union[str, None] = '009dc27cce2b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add comment hiding tracking fields to instagram_comments table"""

    # Add is_hidden field (default False)
    op.add_column('instagram_comments', sa.Column('is_hidden', sa.Boolean(), nullable=False, server_default=sa.false(), comment='Whether comment is hidden on Instagram'))

    # Add hidden_at timestamp field
    op.add_column('instagram_comments', sa.Column('hidden_at', sa.DateTime(), nullable=True, comment='Timestamp when comment was hidden'))


def downgrade() -> None:
    """Remove comment hiding tracking fields"""

    # Remove columns
    op.drop_column('instagram_comments', 'hidden_at')
    op.drop_column('instagram_comments', 'is_hidden')
