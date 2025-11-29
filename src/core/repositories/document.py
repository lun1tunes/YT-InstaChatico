"""Document repository for business document data access."""

import logging
from typing import Optional, List
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseRepository
from ..models.document import Document

logger = logging.getLogger(__name__)


class DocumentRepository(BaseRepository[Document]):
    """Repository for Document operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(Document, session)

    async def get_completed_with_content(self) -> List[Document]:
        """
        Get all completed documents that have markdown content.

        Returns:
            List of successfully processed documents with content
        """
        result = await self.session.execute(
            select(Document)
            .where(
                and_(
                    Document.processing_status == "completed",
                    Document.markdown_content.isnot(None)
                )
            )
            .order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_status(self, status: str, limit: int = 100) -> List[Document]:
        """
        Get documents by processing status.

        Args:
            status: Processing status (pending, processing, completed, failed)
            limit: Maximum number of documents to return

        Returns:
            List of documents with the specified status
        """
        result = await self.session.execute(
            select(Document)
            .where(Document.processing_status == status)
            .order_by(Document.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_pending_documents(self, limit: int = 10) -> List[Document]:
        """
        Get documents pending processing.

        Args:
            limit: Maximum number of documents to return

        Returns:
            List of documents needing processing
        """
        return await self.get_by_status("pending", limit)

    async def get_by_type(self, document_type: str, limit: int = 100) -> List[Document]:
        """
        Get documents by document type.

        Args:
            document_type: Type of document (pdf, excel, csv, word, txt)
            limit: Maximum number of documents to return

        Returns:
            List of documents of the specified type
        """
        result = await self.session.execute(
            select(Document)
            .where(Document.document_type == document_type)
            .order_by(Document.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_summary_stats(self) -> dict:
        """
        Get summary statistics about documents.

        Returns:
            Dict with document counts by status and type
        """
        result = await self.session.execute(select(Document))
        documents = list(result.scalars().all())

        total = len(documents)
        completed = sum(1 for d in documents if d.processing_status == "completed")
        failed = sum(1 for d in documents if d.processing_status == "failed")
        pending = sum(1 for d in documents if d.processing_status in ("pending", "processing"))

        return {
            "total_documents": total,
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "types": list(set(d.document_type for d in documents if d.document_type)),
        }

    async def exists_by_content_hash(self, content_hash: str) -> bool:
        """
        Check if a document with the given content hash exists.

        Args:
            content_hash: SHA-256 hash of document content

        Returns:
            True if document with this hash exists
        """
        result = await self.session.execute(
            select(Document).where(Document.content_hash == content_hash)
        )
        return result.scalar_one_or_none() is not None

    async def mark_processing(self, document: Document) -> None:
        """Update document to processing status."""
        from ..utils.time import now_db_utc
        document.processing_status = "processing"
        await self.session.flush()

    async def mark_completed(self, document: Document, markdown_content: str) -> None:
        """Update document to completed status with content."""
        from ..utils.time import now_db_utc
        document.processing_status = "completed"
        document.markdown_content = markdown_content
        document.processed_at = now_db_utc()
        document.processing_error = None
        await self.session.flush()

    async def mark_failed(self, document: Document, error: str) -> None:
        """Update document to failed status with error message."""
        from ..utils.time import now_db_utc
        document.processing_status = "failed"
        document.processing_error = error
        document.processed_at = now_db_utc()
        await self.session.flush()
