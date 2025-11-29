"""increase url field lengths for long Instagram URLs with parameters

Revision ID: increase_url_field_lengths
Revises: add_children_media_urls
Create Date: 2025-10-06 17:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'increase_url_field_lengths'
down_revision: Union[str, None] = 'add_children_media_urls'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Increase URL field sizes to TEXT to handle long Instagram URLs with query parameters"""

    # Change permalink from VARCHAR(500) to TEXT
    op.alter_column(
        'media',
        'permalink',
        existing_type=sa.String(length=500),
        type_=sa.Text(),
        existing_nullable=False,
        existing_comment='Instagram post permalink URL'
    )

    # Change media_url from VARCHAR(500) to TEXT
    op.alter_column(
        'media',
        'media_url',
        existing_type=sa.String(length=500),
        type_=sa.Text(),
        existing_nullable=True,
        existing_comment='URL to the media file (first image for carousels)'
    )


def downgrade() -> None:
    """Revert URL fields back to VARCHAR(500)"""

    # Revert media_url to VARCHAR(500)
    op.alter_column(
        'media',
        'media_url',
        existing_type=sa.Text(),
        type_=sa.String(length=500),
        existing_nullable=True,
        existing_comment='URL to the media file (first image for carousels)'
    )

    # Revert permalink to VARCHAR(500)
    op.alter_column(
        'media',
        'permalink',
        existing_type=sa.Text(),
        type_=sa.String(length=500),
        existing_nullable=False,
        existing_comment='Instagram post permalink URL'
    )
