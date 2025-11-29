"""add_unique_constraint_to_prevent_duplicate_replies

Revision ID: 5fdaddf292ca
Revises: 29a5d71fb868
Create Date: 2025-09-23 22:55:15.128155

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5fdaddf292ca"
down_revision: Union[str, Sequence[str], None] = "29a5d71fb868"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add unique constraint on reply_id to prevent duplicate replies
    op.create_unique_constraint("uq_question_answers_reply_id", "question_messages_answers", ["reply_id"])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop unique constraint on reply_id
    op.drop_constraint("uq_question_answers_reply_id", "question_messages_answers", type_="unique")
