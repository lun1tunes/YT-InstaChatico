"""
Unit tests for ProcessDocumentUseCase.

Tests cover:
- Happy path: successful document processing
- Edge cases: document not found, S3 download failure, processing failure
- Status tracking through lifecycle
- Error handling
"""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock

from core.use_cases.process_document import ProcessDocumentUseCase


@pytest.mark.unit
@pytest.mark.use_case
class TestProcessDocumentUseCase:
    """Test ProcessDocumentUseCase methods."""

    async def test_execute_success(self, db_session, document_factory):
        """Test successfully processing a document."""
        # Arrange
        document = await document_factory(
            filename="test.pdf",
            document_type="pdf",
            s3_key="documents/test.pdf",
            processing_status="pending",
        )

        file_content = b"PDF file content here"
        markdown_result = "# Document Title\n\nDocument content in markdown"
        content_hash = "abc123hash"

        # Mock S3 service
        mock_s3_service = MagicMock()
        mock_s3_service.download_file = MagicMock(
            return_value=(True, file_content, None)
        )

        # Mock document processing service
        mock_doc_processing = MagicMock()
        mock_doc_processing.process_document = MagicMock(
            return_value=(True, markdown_result, content_hash, None)
        )

        # Mock repository
        mock_document_repo = MagicMock()
        mock_document_repo.get_by_id = AsyncMock(return_value=document)
        mock_document_repo.mark_processing = AsyncMock()
        mock_document_repo.mark_completed = AsyncMock()

        # Create use case
        use_case = ProcessDocumentUseCase(
            session=db_session,
            s3_service=mock_s3_service,
            doc_processing_service=mock_doc_processing,
            document_repository_factory=lambda session: mock_document_repo,
        )

        # Act
        result = await use_case.execute(document_id=str(document.id))

        # Assert
        assert result["status"] == "success"
        assert result["document_id"] == str(document.id)
        assert result["markdown_length"] == len(markdown_result)

        # Verify services called
        mock_s3_service.download_file.assert_called_once_with("documents/test.pdf")
        mock_doc_processing.process_document.assert_called_once_with(
            file_content=file_content,
            filename="test.pdf",
            document_type="pdf"
        )

        # Verify repository methods called
        mock_document_repo.mark_processing.assert_awaited_once_with(document)
        mock_document_repo.mark_completed.assert_awaited_once_with(document, markdown_result)

        # Verify document updated
        assert document.content_hash == content_hash

    async def test_execute_document_not_found(self, db_session):
        """Test processing when document doesn't exist."""
        # Mock repository
        mock_document_repo = MagicMock()
        mock_document_repo.get_by_id = AsyncMock(return_value=None)

        # Create use case
        use_case = ProcessDocumentUseCase(
            session=db_session,
            s3_service=MagicMock(),
            doc_processing_service=MagicMock(),
            document_repository_factory=lambda session: mock_document_repo,
        )

        # Act
        result = await use_case.execute(document_id="nonexistent")

        # Assert
        assert result["status"] == "error"
        assert "not found" in result["reason"].lower()

    async def test_execute_s3_download_failure(self, db_session, document_factory):
        """Test processing when S3 download fails."""
        # Arrange
        document = await document_factory(
            s3_key="documents/missing.pdf",
        )

        # Mock S3 service - download failure
        mock_s3_service = MagicMock()
        mock_s3_service.download_file = MagicMock(
            return_value=(False, None, "File not found in S3")
        )

        # Mock repository
        mock_document_repo = MagicMock()
        mock_document_repo.get_by_id = AsyncMock(return_value=document)
        mock_document_repo.mark_processing = AsyncMock()
        mock_document_repo.mark_failed = AsyncMock()

        # Create use case
        use_case = ProcessDocumentUseCase(
            session=db_session,
            s3_service=mock_s3_service,
            doc_processing_service=MagicMock(),
            document_repository_factory=lambda session: mock_document_repo,
        )

        # Act
        result = await use_case.execute(document_id=str(document.id))

        # Assert
        assert result["status"] == "error"
        assert "Failed to download from S3" in result["reason"]

        # Verify document marked as failed
        mock_document_repo.mark_failed.assert_awaited_once()

    async def test_execute_processing_failure(self, db_session, document_factory):
        """Test processing when document processing fails."""
        # Arrange
        document = await document_factory(
            filename="corrupt.pdf",
            s3_key="documents/corrupt.pdf",
        )

        file_content = b"Corrupted PDF content"

        # Mock S3 service
        mock_s3_service = MagicMock()
        mock_s3_service.download_file = MagicMock(
            return_value=(True, file_content, None)
        )

        # Mock document processing service - processing failure
        mock_doc_processing = MagicMock()
        mock_doc_processing.process_document = MagicMock(
            return_value=(False, None, None, "Invalid PDF format")
        )

        # Mock repository
        mock_document_repo = MagicMock()
        mock_document_repo.get_by_id = AsyncMock(return_value=document)
        mock_document_repo.mark_processing = AsyncMock()
        mock_document_repo.mark_failed = AsyncMock()

        # Create use case
        use_case = ProcessDocumentUseCase(
            session=db_session,
            s3_service=mock_s3_service,
            doc_processing_service=mock_doc_processing,
            document_repository_factory=lambda session: mock_document_repo,
        )

        # Act
        result = await use_case.execute(document_id=str(document.id))

        # Assert
        assert result["status"] == "error"
        assert "Failed to process document" in result["reason"]

        # Verify document marked as failed
        mock_document_repo.mark_failed.assert_awaited_once()

    async def test_execute_marks_processing_status(self, db_session, document_factory):
        """Test that document is marked as processing before processing starts."""
        # Arrange
        document = await document_factory(processing_status="pending")

        # Mock services
        mock_s3_service = MagicMock()
        mock_s3_service.download_file = MagicMock(
            return_value=(True, b"content", None)
        )

        mock_doc_processing = MagicMock()
        mock_doc_processing.process_document = MagicMock(
            return_value=(True, "# Markdown", "hash123", None)
        )

        # Mock repository
        mock_document_repo = MagicMock()
        mock_document_repo.get_by_id = AsyncMock(return_value=document)
        mock_document_repo.mark_processing = AsyncMock()
        mock_document_repo.mark_completed = AsyncMock()

        # Create use case
        use_case = ProcessDocumentUseCase(
            session=db_session,
            s3_service=mock_s3_service,
            doc_processing_service=mock_doc_processing,
            document_repository_factory=lambda session: mock_document_repo,
        )

        # Act
        await use_case.execute(document_id=str(document.id))

        # Assert
        # mark_processing should be called before download
        mock_document_repo.mark_processing.assert_awaited_once_with(document)

    async def test_execute_different_document_types(self, db_session, document_factory):
        """Test processing different document types (PDF, DOCX, TXT)."""
        for idx, doc_type in enumerate(["pdf", "docx", "txt"]):
            # Arrange
            document = await document_factory(
                filename=f"test_{idx}.{doc_type}",
                document_type=doc_type,
                content_hash=f"unique_hash_{idx}_{doc_type}",
            )

            # Mock services
            mock_s3_service = MagicMock()
            mock_s3_service.download_file = MagicMock(
                return_value=(True, b"content", None)
            )

            captured_doc_type = None

            def capture_type(file_content, filename, document_type):
                nonlocal captured_doc_type
                captured_doc_type = document_type
                return (True, "# Markdown", f"hash_{idx}", None)

            mock_doc_processing = MagicMock()
            mock_doc_processing.process_document = MagicMock(side_effect=capture_type)

            # Mock repository
            mock_document_repo = MagicMock()
            mock_document_repo.get_by_id = AsyncMock(return_value=document)
            mock_document_repo.mark_processing = AsyncMock()
            mock_document_repo.mark_completed = AsyncMock()

            # Create use case
            use_case = ProcessDocumentUseCase(
                session=db_session,
                s3_service=mock_s3_service,
                doc_processing_service=mock_doc_processing,
                document_repository_factory=lambda session: mock_document_repo,
            )

            # Act
            await use_case.execute(document_id=str(document.id))

            # Assert
            assert captured_doc_type == doc_type

    async def test_execute_passes_filename_to_processor(self, db_session, document_factory):
        """Test that filename is correctly passed to document processor."""
        # Arrange
        document = await document_factory(
            filename="important_document.pdf",
            document_type="pdf",
        )

        # Mock services
        mock_s3_service = MagicMock()
        mock_s3_service.download_file = MagicMock(
            return_value=(True, b"content", None)
        )

        captured_filename = None

        def capture_filename(file_content, filename, document_type):
            nonlocal captured_filename
            captured_filename = filename
            return (True, "# Markdown", "hash", None)

        mock_doc_processing = MagicMock()
        mock_doc_processing.process_document = MagicMock(side_effect=capture_filename)

        # Mock repository
        mock_document_repo = MagicMock()
        mock_document_repo.get_by_id = AsyncMock(return_value=document)
        mock_document_repo.mark_processing = AsyncMock()
        mock_document_repo.mark_completed = AsyncMock()

        # Create use case
        use_case = ProcessDocumentUseCase(
            session=db_session,
            s3_service=mock_s3_service,
            doc_processing_service=mock_doc_processing,
            document_repository_factory=lambda session: mock_document_repo,
        )

        # Act
        await use_case.execute(document_id=str(document.id))

        # Assert
        assert captured_filename == "important_document.pdf"

    async def test_execute_large_file_processing(self, db_session, document_factory):
        """Test processing large files."""
        # Arrange
        document = await document_factory(
            filename="large_file.pdf",
            document_type="pdf",
        )

        # Large file content (10MB)
        large_content = b"x" * (10 * 1024 * 1024)
        long_markdown = "# " + "Content\n" * 10000

        # Mock services
        mock_s3_service = MagicMock()
        mock_s3_service.download_file = MagicMock(
            return_value=(True, large_content, None)
        )

        mock_doc_processing = MagicMock()
        mock_doc_processing.process_document = MagicMock(
            return_value=(True, long_markdown, "hash_large", None)
        )

        # Mock repository
        mock_document_repo = MagicMock()
        mock_document_repo.get_by_id = AsyncMock(return_value=document)
        mock_document_repo.mark_processing = AsyncMock()
        mock_document_repo.mark_completed = AsyncMock()

        # Create use case
        use_case = ProcessDocumentUseCase(
            session=db_session,
            s3_service=mock_s3_service,
            doc_processing_service=mock_doc_processing,
            document_repository_factory=lambda session: mock_document_repo,
        )

        # Act
        result = await use_case.execute(document_id=str(document.id))

        # Assert
        assert result["status"] == "success"
        assert result["markdown_length"] == len(long_markdown)

    async def test_execute_exception_during_processing(self, db_session, document_factory):
        """Test handling exception raised during processing."""
        # Arrange
        document = await document_factory()

        # Mock services
        mock_s3_service = MagicMock()
        mock_s3_service.download_file = MagicMock(
            return_value=(True, b"content", None)
        )

        # Mock doc processing - raises exception
        mock_doc_processing = MagicMock()
        mock_doc_processing.process_document = MagicMock(
            side_effect=Exception("Out of memory")
        )

        # Mock repository
        mock_document_repo = MagicMock()
        mock_document_repo.get_by_id = AsyncMock(return_value=document)
        mock_document_repo.mark_processing = AsyncMock()
        mock_document_repo.mark_failed = AsyncMock()

        # Create use case
        use_case = ProcessDocumentUseCase(
            session=db_session,
            s3_service=mock_s3_service,
            doc_processing_service=mock_doc_processing,
            document_repository_factory=lambda session: mock_document_repo,
        )

        # Act
        result = await use_case.execute(document_id=str(document.id))

        # Assert
        assert result["status"] == "error"
        assert "Out of memory" in result["reason"]

        # Verify document marked as failed with error message
        mock_document_repo.mark_failed.assert_awaited_once()
        call_args = mock_document_repo.mark_failed.call_args
        assert call_args[0][0] == document
        assert "Out of memory" in call_args[0][1]

    async def test_execute_empty_file(self, db_session, document_factory):
        """Test processing empty file."""
        # Arrange
        document = await document_factory(filename="empty.txt", document_type="txt")

        # Mock services
        mock_s3_service = MagicMock()
        mock_s3_service.download_file = MagicMock(
            return_value=(True, b"", None)  # Empty file
        )

        mock_doc_processing = MagicMock()
        mock_doc_processing.process_document = MagicMock(
            return_value=(True, "", "hash_empty", None)
        )

        # Mock repository
        mock_document_repo = MagicMock()
        mock_document_repo.get_by_id = AsyncMock(return_value=document)
        mock_document_repo.mark_processing = AsyncMock()
        mock_document_repo.mark_completed = AsyncMock()

        # Create use case
        use_case = ProcessDocumentUseCase(
            session=db_session,
            s3_service=mock_s3_service,
            doc_processing_service=mock_doc_processing,
            document_repository_factory=lambda session: mock_document_repo,
        )

        # Act
        result = await use_case.execute(document_id=str(document.id))

        # Assert
        assert result["status"] == "success"
        assert result["markdown_length"] == 0

    async def test_execute_db_commit_fails_after_success_re_raises(self, document_factory):
        """Test that DB commit failures after success are re-raised (have should_reraise attribute)."""
        # Arrange
        document = await document_factory(
            filename="test.pdf",
            document_type="pdf",
        )

        # Mock services - all succeed
        mock_s3_service = MagicMock()
        mock_s3_service.download_file = MagicMock(
            return_value=(True, b"content", None)
        )

        mock_doc_processing = MagicMock()
        mock_doc_processing.process_document = MagicMock(
            return_value=(True, "# Markdown", "hash123", None)
        )

        # Mock repository
        mock_document_repo = MagicMock()
        mock_document_repo.get_by_id = AsyncMock(return_value=document)
        mock_document_repo.mark_processing = AsyncMock()
        mock_document_repo.mark_completed = AsyncMock()
        mock_document_repo.mark_failed = AsyncMock()  # For error recovery path

        # Mock session to fail on ALL commits
        mock_session = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock(side_effect=Exception("DB connection lost"))
        mock_session.rollback = AsyncMock()

        # Create use case
        use_case = ProcessDocumentUseCase(
            session=mock_session,
            s3_service=mock_s3_service,
            doc_processing_service=mock_doc_processing,
            document_repository_factory=lambda session: mock_document_repo,
        )

        # Act & Assert - should raise because of should_reraise attribute
        with pytest.raises(Exception) as exc_info:
            await use_case.execute(document_id=str(document.id))

        # The second commit (in error handler) fails and that exception is raised
        assert "DB connection lost" in str(exc_info.value)
        # Rollback should be called twice (once for each commit failure)
        assert mock_session.rollback.await_count == 2
        # Exception should have should_reraise attribute (set on line 94/119)
        assert hasattr(exc_info.value, "should_reraise")

    async def test_execute_db_commit_fails_after_mark_failed_re_raises(self, document_factory):
        """Test that DB commit failures after mark_failed are re-raised (have should_reraise attribute)."""
        # Arrange
        document = await document_factory()

        # Mock S3 service - fails
        mock_s3_service = MagicMock()
        mock_s3_service.download_file = MagicMock(
            return_value=(False, None, "S3 timeout")
        )

        # Mock repository
        mock_document_repo = MagicMock()
        mock_document_repo.get_by_id = AsyncMock(return_value=document)
        mock_document_repo.mark_processing = AsyncMock()
        mock_document_repo.mark_failed = AsyncMock()

        # Mock session to fail on commit
        mock_session = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock(side_effect=Exception("DB commit failed"))
        mock_session.rollback = AsyncMock()

        # Create use case
        use_case = ProcessDocumentUseCase(
            session=mock_session,
            s3_service=mock_s3_service,
            doc_processing_service=MagicMock(),
            document_repository_factory=lambda session: mock_document_repo,
        )

        # Act & Assert - should raise because of should_reraise attribute
        with pytest.raises(Exception) as exc_info:
            await use_case.execute(document_id=str(document.id))

        assert "DB commit failed" in str(exc_info.value)
        # Rollback should be called
        mock_session.rollback.assert_awaited()
        # Exception should have should_reraise attribute
        assert hasattr(exc_info.value, "should_reraise")

    async def test_execute_s3_download_returns_none_content(self, db_session, document_factory):
        """Test handling when S3 download returns None for content."""
        # Arrange
        document = await document_factory()

        # Mock S3 service - returns None content
        mock_s3_service = MagicMock()
        mock_s3_service.download_file = MagicMock(
            return_value=(False, None, "Object not found")
        )

        # Mock repository
        mock_document_repo = MagicMock()
        mock_document_repo.get_by_id = AsyncMock(return_value=document)
        mock_document_repo.mark_processing = AsyncMock()
        mock_document_repo.mark_failed = AsyncMock()

        # Create use case
        use_case = ProcessDocumentUseCase(
            session=db_session,
            s3_service=mock_s3_service,
            doc_processing_service=MagicMock(),
            document_repository_factory=lambda session: mock_document_repo,
        )

        # Act
        result = await use_case.execute(document_id=str(document.id))

        # Assert
        assert result["status"] == "error"
        assert "Failed to download from S3" in result["reason"]

    async def test_execute_processing_returns_none_markdown(self, db_session, document_factory):
        """Test handling when processing returns None for markdown."""
        # Arrange
        document = await document_factory()

        # Mock services
        mock_s3_service = MagicMock()
        mock_s3_service.download_file = MagicMock(
            return_value=(True, b"content", None)
        )

        # Mock doc processing - returns None markdown
        mock_doc_processing = MagicMock()
        mock_doc_processing.process_document = MagicMock(
            return_value=(False, None, None, "Unsupported format")
        )

        # Mock repository
        mock_document_repo = MagicMock()
        mock_document_repo.get_by_id = AsyncMock(return_value=document)
        mock_document_repo.mark_processing = AsyncMock()
        mock_document_repo.mark_failed = AsyncMock()

        # Create use case
        use_case = ProcessDocumentUseCase(
            session=db_session,
            s3_service=mock_s3_service,
            doc_processing_service=mock_doc_processing,
            document_repository_factory=lambda session: mock_document_repo,
        )

        # Act
        result = await use_case.execute(document_id=str(document.id))

        # Assert
        assert result["status"] == "error"
        assert "Failed to process document" in result["reason"]

    async def test_execute_content_hash_is_set(self, db_session, document_factory):
        """Test that content_hash is correctly set on document."""
        # Arrange
        document = await document_factory()

        # Mock services
        mock_s3_service = MagicMock()
        mock_s3_service.download_file = MagicMock(
            return_value=(True, b"content", None)
        )

        expected_hash = "abc123def456"
        mock_doc_processing = MagicMock()
        mock_doc_processing.process_document = MagicMock(
            return_value=(True, "# Markdown", expected_hash, None)
        )

        # Mock repository
        mock_document_repo = MagicMock()
        mock_document_repo.get_by_id = AsyncMock(return_value=document)
        mock_document_repo.mark_processing = AsyncMock()
        mock_document_repo.mark_completed = AsyncMock()

        # Create use case
        use_case = ProcessDocumentUseCase(
            session=db_session,
            s3_service=mock_s3_service,
            doc_processing_service=mock_doc_processing,
            document_repository_factory=lambda session: mock_document_repo,
        )

        # Act
        await use_case.execute(document_id=str(document.id))

        # Assert
        assert document.content_hash == expected_hash

    async def test_execute_session_flush_called(self, db_session, document_factory):
        """Test that session.flush() is called after mark_processing."""
        # Arrange
        document = await document_factory()

        # Mock services
        mock_s3_service = MagicMock()
        mock_s3_service.download_file = MagicMock(
            return_value=(True, b"content", None)
        )

        mock_doc_processing = MagicMock()
        mock_doc_processing.process_document = MagicMock(
            return_value=(True, "# Markdown", "hash", None)
        )

        # Mock repository
        mock_document_repo = MagicMock()
        mock_document_repo.get_by_id = AsyncMock(return_value=document)
        mock_document_repo.mark_processing = AsyncMock()
        mock_document_repo.mark_completed = AsyncMock()

        # Mock session with flush tracking
        mock_session = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        # Create use case
        use_case = ProcessDocumentUseCase(
            session=mock_session,
            s3_service=mock_s3_service,
            doc_processing_service=mock_doc_processing,
            document_repository_factory=lambda session: mock_document_repo,
        )

        # Act
        await use_case.execute(document_id=str(document.id))

        # Assert
        mock_session.flush.assert_awaited_once()

    async def test_execute_mark_completed_with_correct_markdown(self, db_session, document_factory):
        """Test that mark_completed is called with correct markdown content."""
        # Arrange
        document = await document_factory()

        expected_markdown = "# Test Document\n\nThis is the processed content."

        # Mock services
        mock_s3_service = MagicMock()
        mock_s3_service.download_file = MagicMock(
            return_value=(True, b"content", None)
        )

        mock_doc_processing = MagicMock()
        mock_doc_processing.process_document = MagicMock(
            return_value=(True, expected_markdown, "hash", None)
        )

        # Mock repository
        mock_document_repo = MagicMock()
        mock_document_repo.get_by_id = AsyncMock(return_value=document)
        mock_document_repo.mark_processing = AsyncMock()
        mock_document_repo.mark_completed = AsyncMock()

        # Create use case
        use_case = ProcessDocumentUseCase(
            session=db_session,
            s3_service=mock_s3_service,
            doc_processing_service=mock_doc_processing,
            document_repository_factory=lambda session: mock_document_repo,
        )

        # Act
        await use_case.execute(document_id=str(document.id))

        # Assert
        mock_document_repo.mark_completed.assert_awaited_once_with(document, expected_markdown)

    async def test_execute_mark_failed_with_error_message(self, db_session, document_factory):
        """Test that mark_failed is called with correct error message."""
        # Arrange
        document = await document_factory()

        # Mock services - S3 fails with specific error
        error_message = "Access denied: Insufficient permissions"
        mock_s3_service = MagicMock()
        mock_s3_service.download_file = MagicMock(
            return_value=(False, None, error_message)
        )

        # Mock repository
        mock_document_repo = MagicMock()
        mock_document_repo.get_by_id = AsyncMock(return_value=document)
        mock_document_repo.mark_processing = AsyncMock()
        mock_document_repo.mark_failed = AsyncMock()

        # Create use case
        use_case = ProcessDocumentUseCase(
            session=db_session,
            s3_service=mock_s3_service,
            doc_processing_service=MagicMock(),
            document_repository_factory=lambda session: mock_document_repo,
        )

        # Act
        await use_case.execute(document_id=str(document.id))

        # Assert
        # mark_failed should be called with error message containing the S3 error
        mock_document_repo.mark_failed.assert_awaited_once()
        call_args = mock_document_repo.mark_failed.call_args
        assert "Failed to download from S3" in call_args[0][1]
        assert error_message in call_args[0][1]
