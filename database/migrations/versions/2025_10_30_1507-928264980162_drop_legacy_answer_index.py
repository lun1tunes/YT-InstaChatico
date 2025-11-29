"""drop legacy answer index

Revision ID: 928264980162
Revises: 9d2b8c4e8c2b
Create Date: 2025-10-30 15:07:39.386815

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '928264980162'
down_revision: Union[str, Sequence[str], None] = '9d2b8c4e8c2b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {idx["name"] for idx in inspector.get_indexes("question_messages_answers")}
    if "ix_question_messages_answers_comment_id" in indexes:
        op.drop_index("ix_question_messages_answers_comment_id", table_name="question_messages_answers")


def downgrade() -> None:
    op.create_index(
        "ix_question_messages_answers_comment_id",
        "question_messages_answers",
        ["comment_id"],
        unique=True,
    )
