"""add token usage fields to classifications and answers

Revision ID: add_token_usage_fields
Revises: add_product_embeddings
Create Date: 2025-10-02 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_token_usage_fields'
down_revision: Union[str, None] = 'add_product_embeddings'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add token usage tracking fields"""

    # Add token fields to comments_classification table
    op.add_column('comments_classification', sa.Column('input_tokens', sa.Integer(), nullable=True))
    op.add_column('comments_classification', sa.Column('output_tokens', sa.Integer(), nullable=True))

    # Add token fields to question_messages_answers table (input_tokens and output_tokens)
    # Note: question_messages_answers already has 'tokens_used' which we'll keep for backward compatibility
    op.add_column('question_messages_answers', sa.Column('input_tokens', sa.Integer(), nullable=True))
    op.add_column('question_messages_answers', sa.Column('output_tokens', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Remove token usage tracking fields"""

    # Remove from question_messages_answers
    op.drop_column('question_messages_answers', 'output_tokens')
    op.drop_column('question_messages_answers', 'input_tokens')

    # Remove from comments_classification
    op.drop_column('comments_classification', 'output_tokens')
    op.drop_column('comments_classification', 'input_tokens')