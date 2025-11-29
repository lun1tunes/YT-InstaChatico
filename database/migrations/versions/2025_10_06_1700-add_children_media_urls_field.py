"""add children_media_urls field to media table for carousel support

Revision ID: add_children_media_urls
Revises: add_comment_hiding_fields
Create Date: 2025-10-06 17:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'add_children_media_urls'
down_revision: Union[str, None] = 'add_comment_hiding_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add children_media_urls JSONB field to media table for storing carousel image URLs"""

    # Add children_media_urls field (JSONB array)
    op.add_column(
        'media',
        sa.Column(
            'children_media_urls',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment='Array of all media URLs for CAROUSEL_ALBUM (includes all children images/videos)'
        )
    )

    # Update comment for media_url to clarify it's first image for carousels
    op.alter_column(
        'media',
        'media_url',
        existing_type=sa.String(length=500),
        comment='URL to the media file (first image for carousels)',
        existing_nullable=True,
        existing_comment='URL to the media file'
    )


def downgrade() -> None:
    """Remove children_media_urls field"""

    # Remove comment update from media_url
    op.alter_column(
        'media',
        'media_url',
        existing_type=sa.String(length=500),
        comment='URL to the media file',
        existing_nullable=True,
        existing_comment='URL to the media file (first image for carousels)'
    )

    # Remove children_media_urls column
    op.drop_column('media', 'children_media_urls')
