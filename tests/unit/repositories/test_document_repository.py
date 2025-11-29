"""
Unit tests for DocumentRepository.

Tests data access logic for business documents without external dependencies.
"""

import pytest
import uuid
from datetime import datetime, timedelta

from core.repositories.document import DocumentRepository
from core.models.document import Document


@pytest.mark.unit
@pytest.mark.repository
class TestDocumentRepository:
    """Test DocumentRepository methods."""

    async def test_create_document(self, db_session):
        """Test creating a new document."""
        # Arrange
        repo = DocumentRepository(db_session)
        document_entity = Document(
            document_name="test.pdf",
            document_type="pdf",
            s3_bucket="test-bucket",
            s3_key="documents/test.pdf",
            s3_url="s3://test-bucket/documents/test.pdf",
            processing_status="pending",
            content_hash="abc123hash",
        )

        # Act
        document = await repo.create(document_entity)

        # Assert
        assert document.document_name == "test.pdf"
        assert document.document_type == "pdf"
        assert document.processing_status == "pending"
        assert isinstance(document.id, uuid.UUID)

    async def test_get_document_by_id(self, db_session, document_factory):
        """Test retrieving document by ID."""
        # Arrange
        repo = DocumentRepository(db_session)
        created_doc = await document_factory()

        # Act
        document = await repo.get_by_id(created_doc.id)

        # Assert
        assert document is not None
        assert document.id == created_doc.id

    async def test_get_completed_with_content(self, db_session, document_factory):
        """Test getting completed documents with markdown content."""
        # Arrange
        repo = DocumentRepository(db_session)
        await document_factory(
            processing_status="completed",
            markdown_content="# Document 1\nContent here"
        )
        await document_factory(
            processing_status="completed",
            markdown_content="# Document 2\nMore content"
        )
        await document_factory(
            processing_status="pending",
            markdown_content=None
        )
        await document_factory(
            processing_status="completed",
            markdown_content=None  # Completed but no content
        )

        # Act
        documents = await repo.get_completed_with_content()

        # Assert
        assert len(documents) == 2
        assert all(d.processing_status == "completed" for d in documents)
        assert all(d.markdown_content is not None for d in documents)

    async def test_get_by_status(self, db_session, document_factory):
        """Test getting documents by processing status."""
        # Arrange
        repo = DocumentRepository(db_session)
        await document_factory(processing_status="pending")
        await document_factory(processing_status="pending")
        await document_factory(processing_status="completed")
        await document_factory(processing_status="failed")

        # Act
        pending_docs = await repo.get_by_status("pending", limit=100)
        completed_docs = await repo.get_by_status("completed", limit=100)
        failed_docs = await repo.get_by_status("failed", limit=100)

        # Assert
        assert len(pending_docs) == 2
        assert len(completed_docs) == 1
        assert len(failed_docs) == 1

    async def test_get_by_status_with_limit(self, db_session, document_factory):
        """Test that get_by_status respects limit."""
        # Arrange
        repo = DocumentRepository(db_session)
        for _ in range(5):
            await document_factory(processing_status="pending")

        # Act
        documents = await repo.get_by_status("pending", limit=3)

        # Assert
        assert len(documents) == 3

    async def test_get_pending_documents(self, db_session, document_factory):
        """Test getting pending documents."""
        # Arrange
        repo = DocumentRepository(db_session)
        await document_factory(processing_status="pending")
        await document_factory(processing_status="pending")
        await document_factory(processing_status="completed")

        # Act
        pending = await repo.get_pending_documents(limit=10)

        # Assert
        assert len(pending) == 2
        assert all(d.processing_status == "pending" for d in pending)

    async def test_get_by_type(self, db_session, document_factory):
        """Test getting documents by document type."""
        # Arrange
        repo = DocumentRepository(db_session)
        await document_factory(document_type="pdf")
        await document_factory(document_type="pdf")
        await document_factory(document_type="excel")
        await document_factory(document_type="word")

        # Act
        pdf_docs = await repo.get_by_type("pdf", limit=100)
        excel_docs = await repo.get_by_type("excel", limit=100)

        # Assert
        assert len(pdf_docs) == 2
        assert len(excel_docs) == 1
        assert all(d.document_type == "pdf" for d in pdf_docs)

    async def test_get_summary_stats(self, db_session, document_factory):
        """Test getting document summary statistics."""
        # Arrange
        repo = DocumentRepository(db_session)
        await document_factory(processing_status="completed", document_type="pdf")
        await document_factory(processing_status="completed", document_type="excel")
        await document_factory(processing_status="failed", document_type="pdf")
        await document_factory(processing_status="pending", document_type="word")
        await document_factory(processing_status="processing", document_type="pdf")

        # Act
        stats = await repo.get_summary_stats()

        # Assert
        assert stats["total_documents"] == 5
        assert stats["completed"] == 2
        assert stats["failed"] == 1
        assert stats["pending"] == 2  # pending + processing
        assert set(stats["types"]) == {"pdf", "excel", "word"}

    async def test_exists_by_content_hash_true(self, db_session, document_factory):
        """Test exists_by_content_hash returns True for existing hash."""
        # Arrange
        repo = DocumentRepository(db_session)
        doc = await document_factory(content_hash="unique_hash_123")

        # Act
        exists = await repo.exists_by_content_hash("unique_hash_123")

        # Assert
        assert exists is True

    async def test_exists_by_content_hash_false(self, db_session):
        """Test exists_by_content_hash returns False for non-existent hash."""
        # Arrange
        repo = DocumentRepository(db_session)

        # Act
        exists = await repo.exists_by_content_hash("nonexistent_hash")

        # Assert
        assert exists is False

    async def test_mark_processing(self, db_session, document_factory):
        """Test marking document as processing."""
        # Arrange
        repo = DocumentRepository(db_session)
        doc = await document_factory(processing_status="pending")

        # Act
        await repo.mark_processing(doc)
        await db_session.flush()

        # Assert
        assert doc.processing_status == "processing"

    async def test_mark_completed(self, db_session, document_factory):
        """Test marking document as completed."""
        # Arrange
        repo = DocumentRepository(db_session)
        doc = await document_factory(processing_status="processing")
        markdown_content = "# Processed Document\nContent here"

        # Act
        await repo.mark_completed(doc, markdown_content)
        await db_session.flush()

        # Assert
        assert doc.processing_status == "completed"
        assert doc.markdown_content == markdown_content
        assert doc.processed_at is not None
        assert doc.processing_error is None

    async def test_mark_failed(self, db_session, document_factory):
        """Test marking document as failed."""
        # Arrange
        repo = DocumentRepository(db_session)
        doc = await document_factory(processing_status="processing")
        error_message = "Failed to extract text from PDF"

        # Act
        await repo.mark_failed(doc, error_message)
        await db_session.flush()

        # Assert
        assert doc.processing_status == "failed"
        assert doc.processing_error == error_message
        assert doc.processed_at is not None

    async def test_update_document(self, db_session, document_factory):
        """Test updating a document."""
        # Arrange
        repo = DocumentRepository(db_session)
        doc = await document_factory(filename="old_name.pdf")

        # Act
        doc.document_name = "new_name.pdf"
        updated = await repo.update(doc)

        # Assert
        assert updated.document_name == "new_name.pdf"

    async def test_delete_document(self, db_session, document_factory):
        """Test deleting a document."""
        # Arrange
        repo = DocumentRepository(db_session)
        doc = await document_factory()

        # Act
        await repo.delete(doc)

        # Assert
        deleted = await repo.get_by_id(doc.id)
        assert deleted is None

    async def test_list_all_documents(self, db_session, document_factory):
        """Test listing all documents."""
        # Arrange
        repo = DocumentRepository(db_session)
        await document_factory()
        await document_factory()
        await document_factory()

        # Act
        documents = await repo.get_all()

        # Assert
        assert len(documents) >= 3

    async def test_document_processing_workflow(self, db_session, document_factory):
        """Test full document processing workflow."""
        # Arrange
        repo = DocumentRepository(db_session)
        doc = await document_factory(processing_status="pending")

        # Act & Assert - Mark as processing
        await repo.mark_processing(doc)
        await db_session.flush()
        assert doc.processing_status == "processing"

        # Act & Assert - Mark as completed
        await repo.mark_completed(doc, "# Completed\nContent")
        await db_session.flush()
        assert doc.processing_status == "completed"
        assert doc.markdown_content == "# Completed\nContent"

    async def test_document_processing_failure_workflow(self, db_session, document_factory):
        """Test document processing failure workflow."""
        # Arrange
        repo = DocumentRepository(db_session)
        doc = await document_factory(processing_status="pending")

        # Act - Mark as processing
        await repo.mark_processing(doc)
        await db_session.flush()

        # Act - Mark as failed
        await repo.mark_failed(doc, "Extraction error")
        await db_session.flush()

        # Assert
        assert doc.processing_status == "failed"
        assert doc.processing_error == "Extraction error"

    async def test_mark_completed_clears_previous_error(self, db_session, document_factory):
        """Test that marking as completed clears any previous error."""
        # Arrange
        repo = DocumentRepository(db_session)
        doc = await document_factory(
            processing_status="failed",
            processing_error="Previous error"
        )

        # Act
        await repo.mark_completed(doc, "# Success\nNow it works")
        await db_session.flush()

        # Assert
        assert doc.processing_status == "completed"
        assert doc.processing_error is None
        assert doc.markdown_content == "# Success\nNow it works"

    async def test_get_by_status_empty_result(self, db_session):
        """Test get_by_status returns empty list when no documents match."""
        # Arrange
        repo = DocumentRepository(db_session)

        # Act
        docs = await repo.get_by_status("pending", limit=100)

        # Assert
        assert docs == []

    async def test_get_pending_documents_empty(self, db_session):
        """Test get_pending_documents returns empty list when none pending."""
        # Arrange
        repo = DocumentRepository(db_session)

        # Act
        pending = await repo.get_pending_documents(limit=10)

        # Assert
        assert pending == []

    async def test_get_summary_stats_empty_database(self, db_session):
        """Test get_summary_stats with no documents."""
        # Arrange
        repo = DocumentRepository(db_session)

        # Act
        stats = await repo.get_summary_stats()

        # Assert
        assert stats["total_documents"] == 0
        assert stats["completed"] == 0
        assert stats["failed"] == 0
        assert stats["pending"] == 0
        assert stats["types"] == []

    async def test_exists_by_content_hash_false(self, db_session):
        """Test exists_by_content_hash returns False for nonexistent hash."""
        # Arrange
        repo = DocumentRepository(db_session)

        # Act
        exists = await repo.exists_by_content_hash("nonexistent_hash_123")

        # Assert
        assert exists is False

    async def test_get_by_type_limit_zero(self, db_session, document_factory):
        """Test get_by_type with limit=0."""
        # Arrange
        repo = DocumentRepository(db_session)
        await document_factory(document_type="pdf")

        # Act
        docs = await repo.get_by_type("pdf", limit=0)

        # Assert
        assert len(docs) == 0

    async def test_mark_processing_sets_status(self, db_session, document_factory):
        """Test that mark_processing sets correct status."""
        # Arrange
        repo = DocumentRepository(db_session)
        doc = await document_factory(processing_status="pending")

        # Act
        await repo.mark_processing(doc)
        await db_session.flush()

        # Assert
        assert doc.processing_status == "processing"

    async def test_mark_failed_preserves_error(self, db_session, document_factory):
        """Test that mark_failed stores error message."""
        # Arrange
        repo = DocumentRepository(db_session)
        doc = await document_factory()
        error_msg = "Failed to extract text from corrupted PDF"

        # Act
        await repo.mark_failed(doc, error_msg)
        await db_session.flush()

        # Assert
        assert doc.processing_status == "failed"
        assert doc.processing_error == error_msg
        assert doc.processed_at is not None
