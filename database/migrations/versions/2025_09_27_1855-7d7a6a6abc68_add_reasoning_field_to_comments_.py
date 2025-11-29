"""add_reasoning_field_to_comments_classification

Revision ID: 7d7a6a6abc68
Revises: e8e210e581a0
Create Date: 2025-09-27 18:55:46.114923

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7d7a6a6abc68"
down_revision: Union[str, Sequence[str], None] = "e8e210e581a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add reasoning field to comments_classification table
    op.add_column("comments_classification", sa.Column("reasoning", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove reasoning field from comments_classification table
    op.drop_column("comments_classification", "reasoning")
