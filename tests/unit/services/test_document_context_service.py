"""
Unit tests for DocumentContextService.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from core.services.document_context_service import DocumentContextService
from core.models import Document


@pytest.mark.unit
@pytest.mark.service
class TestDocumentContextService:
    """Test DocumentContextService methods."""

    @pytest.fixture
    def service(self):
        """Create DocumentContextService instance."""
        return DocumentContextService()

    @pytest.fixture
    def mock_documents(self):
        """Create mock documents."""
        doc1 = MagicMock()
        doc1.id = 1
        doc1.document_name = "Product Catalog"
        doc1.description = "List of all products"
        doc1.markdown_content = "## Products\n\n- Product 1\n- Product 2"

        doc2 = MagicMock()
        doc2.id = 2
        doc2.document_name = "Pricing Info"
        doc2.description = "Pricing and discounts"
        doc2.markdown_content = "## Pricing\n\n- Item A: 100\n- Item B: 200"

        doc3 = MagicMock()
        doc3.id = 3
        doc3.document_name = "Company Info"
        doc3.description = None  # No description
        doc3.markdown_content = "## About Us\n\nWe are a company"

        return [doc1, doc2, doc3]

    @patch("core.services.document_context_service.DocumentRepository")
    async def test_get_client_context_success(
        self, mock_repo_class, service, mock_documents, db_session
    ):
        """Test successful retrieval of client context."""
        # Arrange
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_completed_with_content = AsyncMock(return_value=mock_documents)

        # Act
        context = await service.get_client_context(db_session)

        # Assert
        assert context != ""
        assert "# Business Information" in context
        assert "Product Catalog" in context
        assert "List of all products" in context
        assert "## Products" in context
        assert "Pricing Info" in context
        assert "Company Info" in context
        assert "---" in context  # Separator
        mock_repo.get_completed_with_content.assert_called_once()

    @patch("core.services.document_context_service.DocumentRepository")
    async def test_get_client_context_no_documents(
        self, mock_repo_class, service, db_session
    ):
        """Test get_client_context with no documents."""
        # Arrange
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_completed_with_content = AsyncMock(return_value=[])

        # Act
        context = await service.get_client_context(db_session)

        # Assert
        assert context == ""
        mock_repo.get_completed_with_content.assert_called_once()

    @patch("core.services.document_context_service.DocumentRepository")
    async def test_get_client_context_includes_description(
        self, mock_repo_class, service, db_session
    ):
        """Test that context includes document descriptions when present."""
        # Arrange
        doc_with_desc = MagicMock()
        doc_with_desc.id = 1
        doc_with_desc.document_name = "Test Doc"
        doc_with_desc.description = "Important document"
        doc_with_desc.markdown_content = "Content here"

        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_completed_with_content = AsyncMock(return_value=[doc_with_desc])

        # Act
        context = await service.get_client_context(db_session)

        # Assert
        assert "*Important document*" in context

    @patch("core.services.document_context_service.DocumentRepository")
    async def test_get_client_context_no_description(
        self, mock_repo_class, service, db_session
    ):
        """Test that context works without descriptions."""
        # Arrange
        doc_no_desc = MagicMock()
        doc_no_desc.id = 1
        doc_no_desc.document_name = "Test Doc"
        doc_no_desc.description = None
        doc_no_desc.markdown_content = "Content"

        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_completed_with_content = AsyncMock(return_value=[doc_no_desc])

        # Act
        context = await service.get_client_context(db_session)

        # Assert
        assert "Test Doc" in context
        assert "Content" in context
        # Description section should not appear
        assert context.count("*") == 0

    @patch("core.services.document_context_service.DocumentRepository")
    async def test_get_client_context_multiple_documents(
        self, mock_repo_class, service, mock_documents, db_session
    ):
        """Test context with multiple documents."""
        # Arrange
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_completed_with_content = AsyncMock(return_value=mock_documents)

        # Act
        context = await service.get_client_context(db_session)

        # Assert
        # Should contain all document names
        assert "Product Catalog" in context
        assert "Pricing Info" in context
        assert "Company Info" in context
        # Should have separators between documents
        assert context.count("---") == 3

    @patch("core.services.document_context_service.DocumentRepository")
    async def test_get_client_context_exception_handling(
        self, mock_repo_class, service, db_session
    ):
        """Test that get_client_context handles exceptions gracefully."""
        # Arrange
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_completed_with_content = AsyncMock(
            side_effect=Exception("Database error")
        )

        # Act
        context = await service.get_client_context(db_session)

        # Assert
        assert context == ""

    @patch("core.services.document_context_service.DocumentRepository")
    async def test_get_document_summary_success(
        self, mock_repo_class, service, db_session
    ):
        """Test successful retrieval of document summary."""
        # Arrange
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        expected_summary = {
            "total_documents": 5,
            "completed": 3,
            "processing": 1,
            "failed": 1
        }
        mock_repo.get_summary_stats = AsyncMock(return_value=expected_summary)

        # Act
        summary = await service.get_document_summary(db_session)

        # Assert
        assert summary == expected_summary
        mock_repo.get_summary_stats.assert_called_once()

    @patch("core.services.document_context_service.DocumentRepository")
    async def test_get_document_summary_exception(
        self, mock_repo_class, service, db_session
    ):
        """Test get_document_summary handles exceptions."""
        # Arrange
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_summary_stats = AsyncMock(
            side_effect=Exception("Database connection lost")
        )

        # Act
        summary = await service.get_document_summary(db_session)

        # Assert
        assert "error" in summary
        assert "Database connection lost" in summary["error"]

    @patch("core.services.document_context_service.DocumentRepository")
    async def test_format_context_for_agent(
        self, mock_repo_class, service, mock_documents, db_session
    ):
        """Test format_context_for_agent is alias for get_client_context."""
        # Arrange
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_completed_with_content = AsyncMock(return_value=mock_documents)

        # Act
        context1 = await service.get_client_context(db_session)
        context2 = await service.format_context_for_agent(db_session)

        # Assert
        assert context1 == context2
        assert "# Business Information" in context2
        assert mock_repo.get_completed_with_content.call_count == 2

    @patch("core.services.document_context_service.DocumentRepository")
    async def test_get_client_context_formats_markdown_correctly(
        self, mock_repo_class, service, db_session
    ):
        """Test that context is properly formatted as markdown."""
        # Arrange
        doc = MagicMock()
        doc.id = 1
        doc.document_name = "Test Document"
        doc.description = "Test description"
        doc.markdown_content = "## Section 1\n\nParagraph text.\n\n## Section 2\n\nMore text."

        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_completed_with_content = AsyncMock(return_value=[doc])

        # Act
        context = await service.get_client_context(db_session)

        # Assert
        assert "# Business Information\n" in context
        assert "## Test Document\n" in context
        assert "*Test description*\n" in context
        assert "## Section 1" in context
        assert "---" in context

    @patch("core.services.document_context_service.DocumentRepository")
    async def test_get_client_context_preserves_markdown_formatting(
        self, mock_repo_class, service, db_session
    ):
        """Test that original markdown formatting is preserved."""
        # Arrange
        doc = MagicMock()
        doc.id = 1
        doc.document_name = "Formatted Doc"
        doc.description = None
        doc.markdown_content = "# Heading\n\n**Bold text**\n\n- List item 1\n- List item 2"

        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_completed_with_content = AsyncMock(return_value=[doc])

        # Act
        context = await service.get_client_context(db_session)

        # Assert
        assert "**Bold text**" in context
        assert "- List item 1" in context
        assert "- List item 2" in context

    @patch("core.services.document_context_service.DocumentRepository")
    async def test_get_client_context_logs_statistics(
        self, mock_repo_class, service, mock_documents, db_session
    ):
        """Test that get_client_context logs context statistics."""
        # Arrange
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_completed_with_content = AsyncMock(return_value=mock_documents)

        with patch("core.services.document_context_service.logger") as mock_logger:
            # Act
            context = await service.get_client_context(db_session)

            # Assert
            # Should log info about retrieved context
            assert mock_logger.info.called
            # Check that logging includes character count and document count
            log_calls = [str(call) for call in mock_logger.info.call_args_list]
            assert any("characters" in call and "documents" in call for call in log_calls)

    @patch("core.services.document_context_service.DocumentRepository")
    async def test_get_client_context_empty_markdown(
        self, mock_repo_class, service, db_session
    ):
        """Test context with documents that have empty markdown content."""
        # Arrange
        doc = MagicMock()
        doc.id = 1
        doc.document_name = "Empty Doc"
        doc.description = "Has no content"
        doc.markdown_content = ""

        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_completed_with_content = AsyncMock(return_value=[doc])

        # Act
        context = await service.get_client_context(db_session)

        # Assert
        assert "Empty Doc" in context
        assert "Has no content" in context
        # Should still format properly even with empty content
        assert "---" in context
