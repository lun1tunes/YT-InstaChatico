"""add product embeddings table

Revision ID: add_product_embeddings
Revises:
Create Date: 2025-10-01 18:24:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = 'add_product_embeddings'
down_revision: Union[str, None] = '46e554b1b3e6'  # add_foreign_key_constraint_media_id
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create product_embeddings table with pgvector support"""

    # Create product_embeddings table
    op.create_table(
        'product_embeddings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False, comment='Product or service name/title'),
        sa.Column('description', sa.Text(), nullable=False, comment='Detailed description'),
        sa.Column('category', sa.String(length=100), nullable=True, comment='Product category'),
        sa.Column('price', sa.String(length=100), nullable=True, comment='Price information'),
        sa.Column('embedding', Vector(1536), nullable=False, comment='Normalized embedding vector for semantic search'),
        sa.Column('created_at', sa.DateTime(), nullable=False, comment='When this record was created'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, comment='When this record was last updated'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true', comment='Whether this product is active'),
        sa.Column('tags', sa.Text(), nullable=True, comment='Comma-separated tags'),
        sa.Column('url', sa.String(length=500), nullable=True, comment='Link to product page'),
        sa.Column('image_url', sa.String(length=500), nullable=True, comment='Product image URL'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index('idx_product_active', 'product_embeddings', ['is_active'], unique=False)
    op.create_index('idx_product_category', 'product_embeddings', ['category'], unique=False)

    # Create IVFFlat index for vector similarity search using cosine distance
    # Note: IVFFlat requires training data, so we create it manually with SQL
    op.execute("""
        CREATE INDEX idx_product_embedding_cosine
        ON product_embeddings
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);
    """)


def downgrade() -> None:
    """Drop product_embeddings table"""
    op.drop_index('idx_product_embedding_cosine', table_name='product_embeddings')
    op.drop_index('idx_product_category', table_name='product_embeddings')
    op.drop_index('idx_product_active', table_name='product_embeddings')
    op.drop_table('product_embeddings')
