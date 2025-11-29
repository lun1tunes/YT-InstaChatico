"""move_conversation_id_from_question_answer_to_instagram_comments

Revision ID: e2a96501d9c0
Revises: f0c8ff6d881d
Create Date: 2025-09-28 09:56:33.393690

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e2a96501d9c0"
down_revision: Union[str, Sequence[str], None] = "f0c8ff6d881d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add conversation_id column to instagram_comments table
    op.add_column("instagram_comments", sa.Column("conversation_id", sa.String(100), nullable=True))

    # Create index on conversation_id
    op.create_index("ix_instagram_comments_conversation_id", "instagram_comments", ["conversation_id"])

    # Migrate existing conversation_id data from question_messages_answers to instagram_comments
    # This will copy conversation_id from question_messages_answers to the corresponding instagram_comments
    op.execute(
        """
        UPDATE instagram_comments 
        SET conversation_id = qa.conversation_id
        FROM question_messages_answers qa
        WHERE instagram_comments.id = qa.comment_id
        AND qa.conversation_id IS NOT NULL
    """
    )

    # Drop conversation_id column from question_messages_answers table
    op.drop_column("question_messages_answers", "conversation_id")


def downgrade() -> None:
    """Downgrade schema."""
    # Add conversation_id column back to question_messages_answers table
    op.add_column("question_messages_answers", sa.Column("conversation_id", sa.String(100), nullable=True))

    # Create index on conversation_id in question_messages_answers
    op.create_index("ix_question_messages_answers_conversation_id", "question_messages_answers", ["conversation_id"])

    # Migrate conversation_id data back from instagram_comments to question_messages_answers
    op.execute(
        """
        UPDATE question_messages_answers 
        SET conversation_id = ic.conversation_id
        FROM instagram_comments ic
        WHERE question_messages_answers.comment_id = ic.id
        AND ic.conversation_id IS NOT NULL
    """
    )

    # Drop conversation_id column from instagram_comments table
    op.drop_index("ix_instagram_comments_conversation_id", "instagram_comments")
    op.drop_column("instagram_comments", "conversation_id")
