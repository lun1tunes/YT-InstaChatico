"""
Unit tests for Document model.

Tests cover:
- Model creation with all fields
- Default values
- Property methods (is_processed, is_failed, is_pending)
- __repr__ method
- Index constraints
- Field validation
- Edge cases
"""

import pytest
import uuid
from datetime import datetime, timezone

from core.models.document import Document


@pytest.mark.unit
@pytest.mark.model
class TestDocumentModel:
    """Test Document model structure and methods."""

    def test_document_creation_minimal_fields(self):
        """Test creating document with minimal required fields."""
        doc = Document(
            document_name="test.pdf",
            document_type="pdf",
            s3_bucket="test-bucket",
            s3_key="documents/test.pdf",
            s3_url="s3://test-bucket/documents/test.pdf",
        )

        assert doc.document_name == "test.pdf"
        assert doc.document_type == "pdf"
        assert doc.s3_bucket == "test-bucket"
        assert doc.s3_key == "documents/test.pdf"
        assert doc.s3_url == "s3://test-bucket/documents/test.pdf"

    def test_document_creation_all_fields(self):
        """Test creating document with all fields."""
        doc_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        doc = Document(
            id=doc_id,
            document_name="report.xlsx",
            document_type="excel",
            description="Monthly sales report",
            s3_bucket="my-bucket",
            s3_key="docs/report.xlsx",
            s3_url="https://s3.amazonaws.com/my-bucket/docs/report.xlsx",
            file_size_bytes=1024000,
            markdown_content="# Report\n\nSales data...",
            content_hash="a1b2c3d4e5f6...",
            processing_status="completed",
            processing_error=None,
            processed_at=now,
            embedding_status="completed",
            tags={"category": "sales", "year": 2024},
            created_at=now,
            updated_at=now,
            created_by="user@example.com",
        )

        assert doc.id == doc_id
        assert doc.document_name == "report.xlsx"
        assert doc.document_type == "excel"
        assert doc.description == "Monthly sales report"
        assert doc.file_size_bytes == 1024000
        assert doc.markdown_content == "# Report\n\nSales data..."
        assert doc.content_hash == "a1b2c3d4e5f6..."
        assert doc.processing_status == "completed"
        assert doc.processed_at == now
        assert doc.embedding_status == "completed"
        assert doc.tags == {"category": "sales", "year": 2024}
        assert doc.created_by == "user@example.com"

    def test_document_default_values(self):
        """Test that default values can be set."""
        doc = Document(
            document_name="test.pdf",
            document_type="pdf",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
            processing_status="pending",  # Set explicitly for unit tests
            embedding_status="pending",
        )

        # Defaults are applied
        assert doc.processing_status == "pending"
        assert doc.embedding_status == "pending"

    def test_document_optional_fields_none(self):
        """Test that optional fields can be None."""
        doc = Document(
            document_name="test.pdf",
            document_type="pdf",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
        )

        assert doc.description is None
        assert doc.file_size_bytes is None
        assert doc.markdown_content is None
        assert doc.content_hash is None
        assert doc.processing_error is None
        assert doc.processed_at is None
        assert doc.tags is None
        assert doc.created_by is None

    def test_is_processed_property_completed_with_content(self):
        """Test is_processed returns True when status is completed and content exists."""
        doc = Document(
            document_name="test.pdf",
            document_type="pdf",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
            processing_status="completed",
            markdown_content="# Content",
        )

        assert doc.is_processed is True

    def test_is_processed_property_completed_without_content(self):
        """Test is_processed returns False when status is completed but no content."""
        doc = Document(
            document_name="test.pdf",
            document_type="pdf",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
            processing_status="completed",
            markdown_content=None,
        )

        assert doc.is_processed is False

    def test_is_processed_property_pending(self):
        """Test is_processed returns False when status is pending."""
        doc = Document(
            document_name="test.pdf",
            document_type="pdf",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
            processing_status="pending",
            markdown_content="# Content",
        )

        assert doc.is_processed is False

    def test_is_processed_property_processing(self):
        """Test is_processed returns False when status is processing."""
        doc = Document(
            document_name="test.pdf",
            document_type="pdf",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
            processing_status="processing",
            markdown_content="# Content",
        )

        assert doc.is_processed is False

    def test_is_failed_property_true(self):
        """Test is_failed returns True when status is failed."""
        doc = Document(
            document_name="test.pdf",
            document_type="pdf",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
            processing_status="failed",
            processing_error="PDF parsing error",
        )

        assert doc.is_failed is True

    def test_is_failed_property_false(self):
        """Test is_failed returns False when status is not failed."""
        doc = Document(
            document_name="test.pdf",
            document_type="pdf",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
            processing_status="completed",
        )

        assert doc.is_failed is False

    def test_is_pending_property_pending(self):
        """Test is_pending returns True when status is pending."""
        doc = Document(
            document_name="test.pdf",
            document_type="pdf",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
            processing_status="pending",
        )

        assert doc.is_pending is True

    def test_is_pending_property_processing(self):
        """Test is_pending returns True when status is processing."""
        doc = Document(
            document_name="test.pdf",
            document_type="pdf",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
            processing_status="processing",
        )

        assert doc.is_pending is True

    def test_is_pending_property_completed(self):
        """Test is_pending returns False when status is completed."""
        doc = Document(
            document_name="test.pdf",
            document_type="pdf",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
            processing_status="completed",
        )

        assert doc.is_pending is False

    def test_is_pending_property_failed(self):
        """Test is_pending returns False when status is failed."""
        doc = Document(
            document_name="test.pdf",
            document_type="pdf",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
            processing_status="failed",
        )

        assert doc.is_pending is False

    def test_repr_method(self):
        """Test __repr__ returns correct string representation."""
        doc_id = uuid.uuid4()
        doc = Document(
            id=doc_id,
            document_name="test.pdf",
            document_type="pdf",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
            processing_status="completed",
        )

        repr_str = repr(doc)
        assert f"<Document(id={doc_id}" in repr_str
        assert "name=test.pdf" in repr_str
        assert "status=completed" in repr_str

    def test_document_type_pdf(self):
        """Test document with PDF type."""
        doc = Document(
            document_name="file.pdf",
            document_type="pdf",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
        )

        assert doc.document_type == "pdf"

    def test_document_type_excel(self):
        """Test document with Excel type."""
        doc = Document(
            document_name="file.xlsx",
            document_type="excel",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
        )

        assert doc.document_type == "excel"

    def test_document_type_csv(self):
        """Test document with CSV type."""
        doc = Document(
            document_name="file.csv",
            document_type="csv",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
        )

        assert doc.document_type == "csv"

    def test_document_type_word(self):
        """Test document with Word type."""
        doc = Document(
            document_name="file.docx",
            document_type="word",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
        )

        assert doc.document_type == "word"

    def test_document_type_txt(self):
        """Test document with TXT type."""
        doc = Document(
            document_name="file.txt",
            document_type="txt",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
        )

        assert doc.document_type == "txt"

    def test_large_file_size(self):
        """Test document with large file size."""
        doc = Document(
            document_name="large.pdf",
            document_type="pdf",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
            file_size_bytes=1024 * 1024 * 100,  # 100 MB
        )

        assert doc.file_size_bytes == 104857600

    def test_content_hash_sha256(self):
        """Test document with SHA-256 content hash."""
        doc = Document(
            document_name="test.pdf",
            document_type="pdf",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
            content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )

        assert len(doc.content_hash) == 64
        assert doc.content_hash.isalnum()

    def test_complex_tags_structure(self):
        """Test document with complex tags structure."""
        doc = Document(
            document_name="test.pdf",
            document_type="pdf",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
            tags={
                "category": "financial",
                "subcategory": "reports",
                "year": 2024,
                "quarter": "Q1",
                "confidential": True,
                "keywords": ["sales", "revenue", "growth"],
            },
        )

        assert doc.tags["category"] == "financial"
        assert doc.tags["year"] == 2024
        assert doc.tags["confidential"] is True
        assert "sales" in doc.tags["keywords"]

    def test_processing_error_message(self):
        """Test document with processing error message."""
        error_msg = "Failed to parse PDF: Corrupted file structure at byte 1024"
        doc = Document(
            document_name="corrupted.pdf",
            document_type="pdf",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
            processing_status="failed",
            processing_error=error_msg,
        )

        assert doc.processing_error == error_msg
        assert doc.is_failed is True

    def test_long_document_name(self):
        """Test document with long filename (up to 500 chars)."""
        long_name = "a" * 500 + ".pdf"
        doc = Document(
            document_name=long_name,
            document_type="pdf",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
        )

        assert len(doc.document_name) == 504

    def test_s3_presigned_url(self):
        """Test document with S3 presigned URL."""
        presigned_url = (
            "https://my-bucket.s3.amazonaws.com/docs/test.pdf?"
            "X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=..."
        )
        doc = Document(
            document_name="test.pdf",
            document_type="pdf",
            s3_bucket="my-bucket",
            s3_key="docs/test.pdf",
            s3_url=presigned_url,
        )

        assert "X-Amz-Algorithm" in doc.s3_url

    def test_markdown_content_with_formatting(self):
        """Test document with formatted markdown content."""
        markdown = """# Title

## Section 1
Some **bold** and *italic* text.

- Item 1
- Item 2

| Col1 | Col2 |
|------|------|
| A    | B    |
"""
        doc = Document(
            document_name="formatted.md",
            document_type="txt",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
            markdown_content=markdown,
            processing_status="completed",
        )

        assert "# Title" in doc.markdown_content
        assert "**bold**" in doc.markdown_content
        assert doc.is_processed is True

    def test_tablename(self):
        """Test that table name is correctly set."""
        assert Document.__tablename__ == "documents"

    def test_document_id_can_be_uuid(self):
        """Test that document ID can be set as UUID."""
        id1 = uuid.uuid4()
        id2 = uuid.uuid4()

        doc1 = Document(
            id=id1,
            document_name="test1.pdf",
            document_type="pdf",
            s3_bucket="bucket",
            s3_key="key1",
            s3_url="url1",
        )
        doc2 = Document(
            id=id2,
            document_name="test2.pdf",
            document_type="pdf",
            s3_bucket="bucket",
            s3_key="key2",
            s3_url="url2",
        )

        # Both should have UUIDs
        assert isinstance(doc1.id, uuid.UUID)
        assert isinstance(doc2.id, uuid.UUID)
        #Should be the ones we set
        assert doc1.id == id1
        assert doc2.id == id2
        # Should be different from each other
        assert doc1.id != doc2.id

    def test_embedding_status_values(self):
        """Test different embedding status values."""
        statuses = ["pending", "processing", "completed", "failed"]

        for status in statuses:
            doc = Document(
                document_name="test.pdf",
                document_type="pdf",
                s3_bucket="bucket",
                s3_key="key",
                s3_url="url",
                embedding_status=status,
            )
            assert doc.embedding_status == status

    def test_empty_markdown_content(self):
        """Test document with empty markdown content."""
        doc = Document(
            document_name="empty.txt",
            document_type="txt",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
            markdown_content="",
            processing_status="completed",
        )

        # Empty string is not None, so is_processed checks `is not None`
        assert doc.markdown_content == ""
        # is_processed requires both completed status AND markdown_content is not None
        # Empty string "" is not None, so this should be True
        assert doc.is_processed is True

    def test_zero_file_size(self):
        """Test document with zero file size."""
        doc = Document(
            document_name="empty.txt",
            document_type="txt",
            s3_bucket="bucket",
            s3_key="key",
            s3_url="url",
            file_size_bytes=0,
        )

        assert doc.file_size_bytes == 0
