"""sync retry defaults with task policy

Revision ID: sync_retry_defaults
Revises: 8cd0ae1f2f8d
Create Date: 2025-10-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'sync_retry_defaults'
down_revision: Union[str, Sequence[str], None] = '8cd0ae1f2f8d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_DEFAULT = sa.text('5')
OLD_DEFAULT = sa.text('3')


def upgrade() -> None:
    op.alter_column(
        'comments_classification',
        'max_retries',
        existing_type=sa.Integer(),
        server_default=NEW_DEFAULT,
    )
    op.alter_column(
        'question_messages_answers',
        'max_retries',
        existing_type=sa.Integer(),
        server_default=NEW_DEFAULT,
    )
    op.execute("UPDATE comments_classification SET max_retries = 5 WHERE max_retries IS NULL OR max_retries < 5")
    op.execute("UPDATE question_messages_answers SET max_retries = 5 WHERE max_retries IS NULL OR max_retries < 5")


def downgrade() -> None:
    op.alter_column(
        'comments_classification',
        'max_retries',
        existing_type=sa.Integer(),
        server_default=OLD_DEFAULT,
    )
    op.alter_column(
        'question_messages_answers',
        'max_retries',
        existing_type=sa.Integer(),
        server_default=OLD_DEFAULT,
    )
    op.execute("UPDATE comments_classification SET max_retries = 3 WHERE max_retries > 5")
    op.execute("UPDATE question_messages_answers SET max_retries = 3 WHERE max_retries > 5")
