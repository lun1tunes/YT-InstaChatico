"""rename classification field to type in comment_classification

Revision ID: 354c49e45a72
Revises: increase_url_field_lengths
Create Date: 2025-10-25 11:46:20.898820

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '354c49e45a72'
down_revision: Union[str, Sequence[str], None] = 'increase_url_field_lengths'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename classification field to type in comments_classification table."""
    op.alter_column(
        'comments_classification',
        'classification',
        new_column_name='type',
        existing_type=sa.String(length=50),
        existing_nullable=True
    )


def downgrade() -> None:
    """Revert type field back to classification."""
    op.alter_column(
        'comments_classification',
        'type',
        new_column_name='classification',
        existing_type=sa.String(length=50),
        existing_nullable=True
    )
