"""rename_client_documents_to_documents_and_remove_client_id

Revision ID: 009dc27cce2b
Revises: b92884ea1bf0
Create Date: 2025-10-04 20:14:00.529381

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "009dc27cce2b"
down_revision: Union[str, Sequence[str], None] = "b92884ea1bf0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - rename table and remove client_id while preserving data."""

    # Drop old indexes that reference client_id
    op.drop_index(
        "idx_client_document_unique", table_name="client_documents", postgresql_where="content_hash IS NOT NULL"
    )
    op.drop_index("idx_client_documents_client_id", table_name="client_documents")
    op.drop_index("ix_client_documents_client_id", table_name="client_documents")

    # Remove client_id and client_name columns
    op.drop_column("client_documents", "client_id")
    op.drop_column("client_documents", "client_name")

    # Rename the table
    op.rename_table("client_documents", "documents")

    # Drop old indexes (they still have old names)
    op.drop_index("idx_client_documents_status", table_name="documents")
    op.drop_index("idx_client_documents_type", table_name="documents")
    op.drop_index("ix_client_documents_content_hash", table_name="documents")
    op.drop_index("ix_client_documents_document_type", table_name="documents")
    op.drop_index("ix_client_documents_processing_status", table_name="documents")

    # Create new indexes with new names
    op.create_index(
        "idx_document_unique", "documents", ["content_hash"], unique=True, postgresql_where="content_hash IS NOT NULL"
    )
    op.create_index("idx_documents_status", "documents", ["processing_status"], unique=False)
    op.create_index("idx_documents_type", "documents", ["document_type"], unique=False)
    op.create_index(op.f("ix_documents_content_hash"), "documents", ["content_hash"], unique=False)
    op.create_index(op.f("ix_documents_document_type"), "documents", ["document_type"], unique=False)
    op.create_index(op.f("ix_documents_processing_status"), "documents", ["processing_status"], unique=False)

    # Rename the primary key constraint
    op.execute("ALTER TABLE documents RENAME CONSTRAINT client_documents_pkey TO documents_pkey")


def downgrade() -> None:
    """Downgrade schema - restore old structure."""

    # Rename table back
    op.rename_table("documents", "client_documents")

    # Rename primary key back
    op.execute("ALTER TABLE client_documents RENAME CONSTRAINT documents_pkey TO client_documents_pkey")

    # Add back client_id and client_name columns
    op.add_column(
        "client_documents",
        sa.Column("client_id", sa.VARCHAR(length=100), nullable=True, comment="Instagram business account ID"),
    )
    op.add_column(
        "client_documents", sa.Column("client_name", sa.VARCHAR(length=200), nullable=True, comment="Business name")
    )

    # Make client_id NOT NULL after adding (requires manual data population if needed)
    op.execute("UPDATE client_documents SET client_id = 'default_client' WHERE client_id IS NULL")
    op.alter_column("client_documents", "client_id", nullable=False)

    # Drop new indexes
    op.drop_index(op.f("ix_documents_processing_status"), table_name="client_documents")
    op.drop_index(op.f("ix_documents_document_type"), table_name="client_documents")
    op.drop_index(op.f("ix_documents_content_hash"), table_name="client_documents")
    op.drop_index("idx_documents_type", table_name="client_documents")
    op.drop_index("idx_documents_status", table_name="client_documents")
    op.drop_index("idx_document_unique", table_name="client_documents", postgresql_where="content_hash IS NOT NULL")

    # Create old indexes
    op.create_index(
        op.f("ix_client_documents_processing_status"), "client_documents", ["processing_status"], unique=False
    )
    op.create_index(op.f("ix_client_documents_document_type"), "client_documents", ["document_type"], unique=False)
    op.create_index(op.f("ix_client_documents_content_hash"), "client_documents", ["content_hash"], unique=False)
    op.create_index(op.f("ix_client_documents_client_id"), "client_documents", ["client_id"], unique=False)
    op.create_index(op.f("idx_client_documents_type"), "client_documents", ["document_type"], unique=False)
    op.create_index(op.f("idx_client_documents_status"), "client_documents", ["processing_status"], unique=False)
    op.create_index(op.f("idx_client_documents_client_id"), "client_documents", ["client_id"], unique=False)
    op.create_index(
        op.f("idx_client_document_unique"),
        "client_documents",
        ["client_id", "content_hash"],
        unique=True,
        postgresql_where="content_hash IS NOT NULL",
    )
