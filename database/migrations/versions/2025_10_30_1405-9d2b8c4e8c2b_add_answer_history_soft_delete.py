"""Add soft-delete tracking to question answers and allow history."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9d2b8c4e8c2b"
down_revision: Union[str, Sequence[str], None] = "fd9d4bb89e83"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("question_messages_answers")
    }
    should_drop_unique = "question_messages_answers_comment_id_key" in unique_constraints

    indexes = inspector.get_indexes("question_messages_answers")
    drop_base_index = any(idx["name"] == "ix_question_messages_answers_comment_id" for idx in indexes)

    with op.batch_alter_table("question_messages_answers") as batch:
        if should_drop_unique:
            batch.drop_constraint("question_messages_answers_comment_id_key", type_="unique")
        batch.add_column(
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    if drop_base_index:
        op.drop_index("ix_question_messages_answers_comment_id", table_name="question_messages_answers")

    op.create_index(
        "uq_question_messages_answers_comment_active",
        "question_messages_answers",
        ["comment_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        sqlite_where=sa.text("is_deleted = 0"),
    )

    op.execute("UPDATE question_messages_answers SET is_deleted = FALSE WHERE is_deleted IS NULL;")
    with op.batch_alter_table("question_messages_answers") as batch:
        batch.alter_column("is_deleted", server_default=None)


def downgrade() -> None:
    op.drop_index(
        "uq_question_messages_answers_comment_active",
        table_name="question_messages_answers",
    )

    with op.batch_alter_table("question_messages_answers") as batch:
        batch.drop_column("is_deleted")
        batch.create_unique_constraint(
            "question_messages_answers_comment_id_key",
            ["comment_id"],
        )
