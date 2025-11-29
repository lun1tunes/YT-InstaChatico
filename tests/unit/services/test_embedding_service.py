"""
Unit tests for EmbeddingService.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from core.services.embedding_service import EmbeddingService
from core.models import ProductEmbedding


@pytest.mark.unit
@pytest.mark.service
class TestEmbeddingService:
    """Test EmbeddingService methods."""

    @pytest.fixture
    def embedding_service(self):
        """Create EmbeddingService instance."""
        return EmbeddingService()

    @patch("core.services.embedding_service.AsyncOpenAI")
    async def test_generate_embedding_success(self, mock_openai_class, embedding_service):
        """Test successful embedding generation."""
        # Arrange
        mock_client = AsyncMock()
        mock_openai_class.return_value.__aenter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.data = [MagicMock()]
        mock_response.data[0].embedding = [0.1] * 1536
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        text = "Test product description"

        # Act
        embedding = await embedding_service.generate_embedding(text)

        # Assert
        assert len(embedding) == 1536
        assert all(isinstance(v, float) for v in embedding)
        mock_client.embeddings.create.assert_called_once_with(
            model=embedding_service.EMBEDDING_MODEL,
            input=text,
            encoding_format="float"
        )

    @patch("core.services.embedding_service.AsyncOpenAI")
    async def test_generate_embedding_failure(self, mock_openai_class, embedding_service):
        """Test embedding generation handles errors."""
        # Arrange
        mock_client = AsyncMock()
        mock_openai_class.return_value.__aenter__.return_value = mock_client
        mock_client.embeddings.create = AsyncMock(side_effect=Exception("API Error"))

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            await embedding_service.generate_embedding("Test text")

        assert "API Error" in str(exc_info.value)

    @patch("core.services.embedding_service.ProductEmbeddingRepository")
    @patch("core.services.embedding_service.AsyncOpenAI")
    async def test_search_similar_products_success(
        self, mock_openai_class, mock_repo_class, embedding_service, db_session
    ):
        """Test successful product similarity search."""
        # Arrange
        # Mock embedding generation
        mock_client = AsyncMock()
        mock_openai_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.data = [MagicMock()]
        mock_response.data[0].embedding = [0.1] * 1536
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        # Mock repository search
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.search_by_similarity = AsyncMock(return_value=[
            {
                "id": 1,
                "title": "Product 1",
                "description": "Description 1",
                "price": "100 @C1",
                "similarity": 0.95,
                "is_ood": False
            },
            {
                "id": 2,
                "title": "Product 2",
                "description": "Description 2",
                "price": "200 @C1",
                "similarity": 0.65,
                "is_ood": True
            }
        ])

        query = "looking for a product"

        # Act
        results = await embedding_service.search_similar_products(
            query=query,
            session=db_session,
            limit=5
        )

        # Assert
        assert len(results) == 2
        assert results[0]["similarity"] == 0.95
        assert results[0]["is_ood"] is False
        assert results[1]["is_ood"] is True
        mock_repo.search_by_similarity.assert_called_once()

    @patch("core.services.embedding_service.ProductEmbeddingRepository")
    @patch("core.services.embedding_service.AsyncOpenAI")
    async def test_search_similar_products_with_filters(
        self, mock_openai_class, mock_repo_class, embedding_service, db_session
    ):
        """Test product search with category filter and inactive products."""
        # Arrange
        mock_client = AsyncMock()
        mock_openai_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.data = [MagicMock()]
        mock_response.data[0].embedding = [0.1] * 1536
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.search_by_similarity = AsyncMock(return_value=[])

        # Act
        await embedding_service.search_similar_products(
            query="test",
            session=db_session,
            limit=3,
            category_filter="electronics",
            include_inactive=True
        )

        # Assert
        call_args = mock_repo.search_by_similarity.call_args
        assert call_args[1]["limit"] == 3
        assert call_args[1]["category_filter"] == "electronics"
        assert call_args[1]["include_inactive"] is True
        assert call_args[1]["similarity_threshold"] == embedding_service.SIMILARITY_THRESHOLD

    @patch("core.services.embedding_service.ProductEmbeddingRepository")
    @patch("core.services.embedding_service.AsyncOpenAI")
    @patch("core.services.embedding_service.asyncio.sleep", new_callable=AsyncMock)
    async def test_search_similar_products_retry_on_concurrency(
        self, mock_sleep, mock_openai_class, mock_repo_class, embedding_service, db_session
    ):
        """Test that search retries on database concurrency issues."""
        # Arrange
        mock_client = AsyncMock()
        mock_openai_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.data = [MagicMock()]
        mock_response.data[0].embedding = [0.1] * 1536
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        # First call raises concurrency error, second succeeds
        mock_repo.search_by_similarity = AsyncMock(
            side_effect=[
                Exception("another operation is in progress"),
                [{"id": 1, "title": "Product", "similarity": 0.9, "is_ood": False}]
            ]
        )

        # Act
        results = await embedding_service.search_similar_products(
            query="test",
            session=db_session
        )

        # Assert
        assert len(results) == 1
        assert mock_repo.search_by_similarity.call_count == 2
        mock_sleep.assert_called_once()  # Should sleep between retries

    @patch("core.services.embedding_service.ProductEmbeddingRepository")
    @patch("core.services.embedding_service.AsyncOpenAI")
    async def test_search_similar_products_exhausts_retries(
        self, mock_openai_class, mock_repo_class, embedding_service, db_session
    ):
        """Test that search raises error after exhausting retries."""
        # Arrange
        mock_client = AsyncMock()
        mock_openai_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.data = [MagicMock()]
        mock_response.data[0].embedding = [0.1] * 1536
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.search_by_similarity = AsyncMock(
            side_effect=Exception("another operation is in progress")
        )

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            await embedding_service.search_similar_products(
                query="test",
                session=db_session
            )

        assert "another operation is in progress" in str(exc_info.value)
        assert mock_repo.search_by_similarity.call_count == 3  # Max retries

    @patch("core.services.embedding_service.ProductEmbeddingRepository")
    @patch("core.services.embedding_service.AsyncOpenAI")
    async def test_add_product_success(
        self, mock_openai_class, mock_repo_class, embedding_service, db_session
    ):
        """Test successful product addition with embedding."""
        # Arrange
        mock_client = AsyncMock()
        mock_openai_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.data = [MagicMock()]
        mock_response.data[0].embedding = [0.1] * 1536
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_product = ProductEmbedding(
            id=1,
            title="Test Product",
            description="Test Description",
            price="100 @C1",
            embedding=[0.1] * 1536
        )
        mock_repo.create = AsyncMock(return_value=mock_product)

        db_session.commit = AsyncMock()
        db_session.refresh = AsyncMock()

        # Act
        product = await embedding_service.add_product(
            title="Test Product",
            description="Test Description",
            session=db_session,
            price="100 @C1",
            category="electronics"
        )

        # Assert
        assert product.id == 1
        assert product.title == "Test Product"
        mock_client.embeddings.create.assert_called_once()
        mock_repo.create.assert_called_once()
        db_session.commit.assert_called_once()

    @patch("core.services.embedding_service.ProductEmbeddingRepository")
    @patch("core.services.embedding_service.AsyncOpenAI")
    async def test_add_product_failure_rollback(
        self, mock_openai_class, mock_repo_class, embedding_service, db_session
    ):
        """Test that add_product rolls back on error."""
        # Arrange
        mock_client = AsyncMock()
        mock_openai_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.data = [MagicMock()]
        mock_response.data[0].embedding = [0.1] * 1536
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.create = AsyncMock(side_effect=Exception("Database error"))

        db_session.commit = AsyncMock()
        db_session.rollback = AsyncMock()

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            await embedding_service.add_product(
                title="Test Product",
                description="Test Description",
                session=db_session
            )

        assert "Database error" in str(exc_info.value)
        db_session.rollback.assert_called_once()

    @patch("core.services.embedding_service.ProductEmbeddingRepository")
    @patch("core.services.embedding_service.AsyncOpenAI")
    async def test_update_product_embedding_success(
        self, mock_openai_class, mock_repo_class, embedding_service, db_session
    ):
        """Test successful product embedding update."""
        # Arrange
        mock_client = AsyncMock()
        mock_openai_class.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.data = [MagicMock()]
        mock_response.data[0].embedding = [0.2] * 1536
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_product = ProductEmbedding(
            id=1,
            title="Test Product",
            description="Updated Description",
            embedding=[0.1] * 1536
        )
        mock_repo.get_by_id = AsyncMock(return_value=mock_product)
        mock_repo.update_embedding = AsyncMock()

        db_session.commit = AsyncMock()
        db_session.refresh = AsyncMock()

        # Act
        product = await embedding_service.update_product_embedding(
            product_id=1,
            session=db_session
        )

        # Assert
        assert product is not None
        assert product.id == 1
        mock_repo.get_by_id.assert_called_once_with(1)
        mock_repo.update_embedding.assert_called_once()
        db_session.commit.assert_called_once()

    @patch("core.services.embedding_service.ProductEmbeddingRepository")
    async def test_update_product_embedding_not_found(
        self, mock_repo_class, embedding_service, db_session
    ):
        """Test update returns None when product not found."""
        # Arrange
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_by_id = AsyncMock(return_value=None)

        # Act
        product = await embedding_service.update_product_embedding(
            product_id=999,
            session=db_session
        )

        # Assert
        assert product is None
        mock_repo.get_by_id.assert_called_once_with(999)

    @patch("core.services.embedding_service.ProductEmbeddingRepository")
    @patch("core.services.embedding_service.AsyncOpenAI")
    async def test_update_product_embedding_failure_rollback(
        self, mock_openai_class, mock_repo_class, embedding_service, db_session
    ):
        """Test that update_product_embedding rolls back on error."""
        # Arrange
        mock_client = AsyncMock()
        mock_openai_class.return_value.__aenter__.return_value = mock_client
        mock_client.embeddings.create = AsyncMock(side_effect=Exception("OpenAI Error"))

        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo
        mock_product = ProductEmbedding(id=1, title="Test", description="Test")
        mock_repo.get_by_id = AsyncMock(return_value=mock_product)

        db_session.rollback = AsyncMock()

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            await embedding_service.update_product_embedding(
                product_id=1,
                session=db_session
            )

        assert "OpenAI Error" in str(exc_info.value)
        db_session.rollback.assert_called_once()

    async def test_async_context_manager(self, embedding_service):
        """Test EmbeddingService works as async context manager."""
        # Act & Assert
        async with embedding_service as service:
            assert service is embedding_service
