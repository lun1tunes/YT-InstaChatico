"""
Document model for storing business context documents.

Stores metadata and processed content from PDF, Excel, CSV, DOCX documents
uploaded to S3 for enhancing AI agent responses.

Single-tenant: Each app instance serves one client, so no client_id needed.
"""

from __future__ import annotations
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, BigInteger, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
import uuid

from .base import Base
from ..utils.time import now_db_utc


class Document(Base):
    """
    Business documents for AI context.

    Stores documents uploaded to S3, processed with pdfplumber/python-docx,
    and converted to markdown for use in AI agent responses.

    Single-tenant architecture: One app instance per client.
    """

    __tablename__ = "documents"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment="Unique document identifier"
    )

    # Document metadata
    document_name: Mapped[str] = mapped_column(String(500), nullable=False, comment="Original document filename")
    document_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True, comment="Document type: pdf, excel, csv, word, txt"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Human-readable document description")

    # S3 storage
    s3_bucket: Mapped[str] = mapped_column(String(200), nullable=False, comment="S3 bucket name")
    s3_key: Mapped[str] = mapped_column(String(500), nullable=False, comment="S3 object key/path")
    s3_url: Mapped[str] = mapped_column(Text, nullable=False, comment="Full S3 URL or presigned URL")
    file_size_bytes: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="Original file size in bytes"
    )

    # Processed content
    markdown_content: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Document content extracted and converted to markdown"
    )
    content_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, comment="SHA-256 hash of content for deduplication"
    )

    # Processing status
    processing_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
        comment="Processing status: pending, processing, completed, failed",
    )
    processing_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Error message if processing failed"
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="When document processing completed"
    )

    # AI/Search metadata
    embedding_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending", comment="Vector embedding status for future semantic search"
    )
    tags: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="Categorization tags and metadata")

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_db_utc, nullable=False, comment="When record was created"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=now_db_utc,
        onupdate=now_db_utc,
        nullable=False,
        comment="When record was last updated",
    )
    created_by: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="User/system who uploaded the document"
    )

    # Table constraints
    __table_args__ = (
        # Prevent duplicate documents by content hash
        Index(
            "idx_document_unique",
            "content_hash",
            unique=True,
            postgresql_where="content_hash IS NOT NULL",
        ),
        # Additional indexes
        Index("idx_documents_status", "processing_status"),
        Index("idx_documents_type", "document_type"),
    )

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, name={self.document_name}, status={self.processing_status})>"

    @property
    def is_processed(self) -> bool:
        """Check if document has been successfully processed."""
        return self.processing_status == "completed" and self.markdown_content is not None

    @property
    def is_failed(self) -> bool:
        """Check if document processing failed."""
        return self.processing_status == "failed"

    @property
    def is_pending(self) -> bool:
        """Check if document is waiting to be processed."""
        return self.processing_status in ("pending", "processing")
