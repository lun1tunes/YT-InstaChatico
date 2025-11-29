"""Add analysis_requested_at column to media

Revision ID: fd9d4bb89e83
Revises: 1f1f2b4ddd9e
Create Date: 2025-10-30 13:35:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fd9d4bb89e83"
down_revision: Union[str, Sequence[str], None] = "1f1f2b4ddd9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "media",
        sa.Column("analysis_requested_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("media", "analysis_requested_at")

