"""
Unit tests for ProductEmbeddingRepository.

Tests data access logic for product embeddings without external dependencies.
Note: Vector similarity search tests are simplified for SQLite compatibility.
"""

import pytest
from datetime import datetime, timedelta, timezone

from core.repositories.product_embedding import ProductEmbeddingRepository
from core.models.product_embedding import ProductEmbedding


@pytest.mark.unit
@pytest.mark.repository
class TestProductEmbeddingRepository:
    """Test ProductEmbeddingRepository methods."""

    async def test_create_product_embedding(self, db_session):
        """Test creating a new product embedding."""
        # Arrange
        repo = ProductEmbeddingRepository(db_session)
        embedding_vector = [0.1] * 1536
        product_entity = ProductEmbedding(
            title="Test Product",
            description="A great product",
            category="electronics",
            price="299.99",
            embedding=embedding_vector,
        )

        # Act
        product = await repo.create(product_entity)

        # Assert
        assert product.id is not None
        assert product.title == "Test Product"
        assert product.category == "electronics"
        assert len(product.embedding) == 1536

    async def test_get_product_by_id(self, db_session, product_embedding_factory):
        """Test retrieving product by ID."""
        # Arrange
        repo = ProductEmbeddingRepository(db_session)
        created_product = await product_embedding_factory()

        # Act
        product = await repo.get_by_id(created_product.id)

        # Assert
        assert product is not None
        assert product.id == created_product.id

    async def test_get_by_category(self, db_session, product_embedding_factory):
        """Test getting products by category."""
        # Arrange
        repo = ProductEmbeddingRepository(db_session)
        await product_embedding_factory(category="electronics", is_active=True)
        await product_embedding_factory(category="electronics", is_active=True)
        await product_embedding_factory(category="clothing", is_active=True)

        # Act
        electronics = await repo.get_by_category("electronics")

        # Assert
        assert len(electronics) == 2
        assert all(p.category == "electronics" for p in electronics)

    async def test_get_by_category_include_inactive(self, db_session, product_embedding_factory):
        """Test getting products by category including inactive ones."""
        # Arrange
        repo = ProductEmbeddingRepository(db_session)
        await product_embedding_factory(category="books", is_active=True)
        await product_embedding_factory(category="books", is_active=False)

        # Act
        active_only = await repo.get_by_category("books", include_inactive=False)
        all_products = await repo.get_by_category("books", include_inactive=True)

        # Assert
        assert len(active_only) == 1
        assert len(all_products) == 2

    async def test_get_active_products(self, db_session, product_embedding_factory):
        """Test getting all active products."""
        # Arrange
        repo = ProductEmbeddingRepository(db_session)
        await product_embedding_factory(is_active=True)
        await product_embedding_factory(is_active=True)
        await product_embedding_factory(is_active=False)

        # Act
        active_products = await repo.get_active_products(limit=100)

        # Assert
        assert len(active_products) == 2
        assert all(p.is_active for p in active_products)

    async def test_get_active_products_with_limit(self, db_session, product_embedding_factory):
        """Test that get_active_products respects limit."""
        # Arrange
        repo = ProductEmbeddingRepository(db_session)
        for _ in range(5):
            await product_embedding_factory(is_active=True)

        # Act
        products = await repo.get_active_products(limit=3)

        # Assert
        assert len(products) == 3

    async def test_deactivate_product(self, db_session, product_embedding_factory):
        """Test deactivating a product."""
        # Arrange
        repo = ProductEmbeddingRepository(db_session)
        product = await product_embedding_factory(is_active=True)

        # Act
        await repo.deactivate(product)
        await db_session.flush()

        # Assert
        assert product.is_active is False

    async def test_activate_product(self, db_session, product_embedding_factory):
        """Test activating a product."""
        # Arrange
        repo = ProductEmbeddingRepository(db_session)
        product = await product_embedding_factory(is_active=False)

        # Act
        await repo.activate(product)
        await db_session.flush()

        # Assert
        assert product.is_active is True

    async def test_update_embedding(self, db_session, product_embedding_factory):
        """Test updating product embedding vector."""
        # Arrange
        repo = ProductEmbeddingRepository(db_session)
        old_embedding = [0.1] * 1536
        new_embedding = [0.5] * 1536
        product = await product_embedding_factory(embedding=old_embedding)

        # Act
        await repo.update_embedding(product, new_embedding)
        await db_session.flush()

        # Assert
        assert product.embedding == new_embedding
        assert product.embedding[0] == 0.5

    async def test_update_product(self, db_session, product_embedding_factory):
        """Test updating a product."""
        # Arrange
        repo = ProductEmbeddingRepository(db_session)
        product = await product_embedding_factory(title="Old Title")

        # Act
        product.title = "New Title"
        updated = await repo.update(product)

        # Assert
        assert updated.title == "New Title"

    async def test_delete_product(self, db_session, product_embedding_factory):
        """Test deleting a product."""
        # Arrange
        repo = ProductEmbeddingRepository(db_session)
        product = await product_embedding_factory()

        # Act
        await repo.delete(product)

        # Assert
        deleted = await repo.get_by_id(product.id)
        assert deleted is None

    async def test_list_all_products(self, db_session, product_embedding_factory):
        """Test listing all products."""
        # Arrange
        repo = ProductEmbeddingRepository(db_session)
        await product_embedding_factory()
        await product_embedding_factory()
        await product_embedding_factory()

        # Act
        products = await repo.get_all()

        # Assert
        assert len(products) >= 3

    async def test_create_product_with_tags(self, db_session):
        """Test creating product with tags."""
        # Arrange
        repo = ProductEmbeddingRepository(db_session)
        product_entity = ProductEmbedding(
            title="Tagged Product",
            description="Product with tags",
            category="test",
            price="99.99",
            tags="tag1,tag2,tag3",
            embedding=[0.1] * 1536,
        )

        # Act
        product = await repo.create(product_entity)

        # Assert
        assert product.tags == "tag1,tag2,tag3"

    async def test_create_product_with_urls(self, db_session):
        """Test creating product with URL and image URL."""
        # Arrange
        repo = ProductEmbeddingRepository(db_session)
        product_entity = ProductEmbedding(
            title="Product with URLs",
            description="Test",
            category="test",
            price="50",
            url="https://example.com/product",
            image_url="https://example.com/image.jpg",
            embedding=[0.1] * 1536,
        )

        # Act
        product = await repo.create(product_entity)

        # Assert
        assert product.url == "https://example.com/product"
        assert product.image_url == "https://example.com/image.jpg"

    async def test_get_active_products_ordered_by_date(self, db_session, product_embedding_factory):
        """Test that active products are ordered by creation date desc."""
        # Arrange
        repo = ProductEmbeddingRepository(db_session)

        prod1 = await product_embedding_factory(
            created_at=datetime.now(timezone.utc) - timedelta(days=2)
        )
        prod2 = await product_embedding_factory(
            created_at=datetime.now(timezone.utc) - timedelta(days=1)
        )
        prod3 = await product_embedding_factory(
            created_at=datetime.now(timezone.utc)
        )

        # Act
        products = await repo.get_active_products(limit=100)

        # Assert
        assert len(products) == 3
        # Most recent first
        assert products[0].id == prod3.id
        assert products[2].id == prod1.id

    async def test_multiple_categories(self, db_session, product_embedding_factory):
        """Test creating products in different categories."""
        # Arrange
        repo = ProductEmbeddingRepository(db_session)
        await product_embedding_factory(category="electronics")
        await product_embedding_factory(category="clothing")
        await product_embedding_factory(category="books")
        await product_embedding_factory(category="food")

        # Act
        electronics = await repo.get_by_category("electronics")
        clothing = await repo.get_by_category("clothing")

        # Assert
        assert len(electronics) == 1
        assert len(clothing) == 1

    async def test_activate_deactivate_workflow(self, db_session, product_embedding_factory):
        """Test full activate/deactivate workflow."""
        # Arrange
        repo = ProductEmbeddingRepository(db_session)
        product = await product_embedding_factory(is_active=True)

        # Act & Assert - Deactivate
        await repo.deactivate(product)
        await db_session.flush()
        assert product.is_active is False

        # Act & Assert - Reactivate
        await repo.activate(product)
        await db_session.flush()
        assert product.is_active is True

    @pytest.mark.skipif(
        True,
        reason="Vector search requires PostgreSQL with pgvector extension"
    )
    async def test_search_by_similarity(self, db_session, product_embedding_factory):
        """Test semantic similarity search using pgvector.

        Note: This test is skipped in SQLite as it requires PostgreSQL with pgvector.
        """
        # Arrange
        repo = ProductEmbeddingRepository(db_session)
        query_embedding = [0.9] * 1536

        await product_embedding_factory(
            title="Similar Product",
            embedding=[0.85] * 1536
        )
        await product_embedding_factory(
            title="Different Product",
            embedding=[0.1] * 1536
        )

        # Act
        results = await repo.search_by_similarity(
            query_embedding=query_embedding,
            limit=5,
            similarity_threshold=0.0
        )

        # Assert
        assert len(results) > 0
        assert "similarity" in results[0]
        assert "title" in results[0]

    async def test_search_by_similarity_with_mock(self, db_session, product_embedding_factory):
        """Test search_by_similarity method logic with mocked database response."""
        from unittest.mock import AsyncMock, MagicMock, patch

        # Arrange
        repo = ProductEmbeddingRepository(db_session)
        query_embedding = [0.9] * 1536

        # Mock the database result
        mock_row = MagicMock()
        mock_row.id = 1
        mock_row.title = "Test Product"
        mock_row.description = "Description"
        mock_row.category = "electronics"
        mock_row.price = "99.99"
        mock_row.tags = "tag1,tag2"
        mock_row.url = "https://example.com"
        mock_row.image_url = "https://example.com/image.jpg"
        mock_row.similarity = 0.95

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]

        # Act
        with patch.object(db_session, 'execute', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_result
            results = await repo.search_by_similarity(
                query_embedding=query_embedding,
                limit=5,
                similarity_threshold=0.0
            )

        # Assert
        assert len(results) == 1
        assert results[0]["title"] == "Test Product"
        assert results[0]["similarity"] == 0.95
        assert results[0]["category"] == "electronics"
        assert results[0]["price"] == "99.99"
        assert results[0]["is_ood"] is False

    async def test_search_by_similarity_with_threshold(self, db_session):
        """Test search_by_similarity respects similarity threshold."""
        from unittest.mock import AsyncMock, MagicMock, patch

        # Arrange
        repo = ProductEmbeddingRepository(db_session)
        query_embedding = [0.9] * 1536

        # Mock results with varying similarity scores
        mock_row1 = MagicMock()
        mock_row1.id = 1
        mock_row1.title = "High Similarity"
        mock_row1.description = "Test"
        mock_row1.category = "test"
        mock_row1.price = "10"
        mock_row1.tags = None
        mock_row1.url = None
        mock_row1.image_url = None
        mock_row1.similarity = 0.95

        mock_row2 = MagicMock()
        mock_row2.id = 2
        mock_row2.title = "Low Similarity"
        mock_row2.description = "Test"
        mock_row2.category = "test"
        mock_row2.price = "10"
        mock_row2.tags = None
        mock_row2.url = None
        mock_row2.image_url = None
        mock_row2.similarity = 0.3

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row1, mock_row2]

        # Act
        with patch.object(db_session, 'execute', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_result
            results = await repo.search_by_similarity(
                query_embedding=query_embedding,
                limit=5,
                similarity_threshold=0.5
            )

        # Assert - only high similarity result should be included
        assert len(results) == 1
        assert results[0]["title"] == "High Similarity"
        assert results[0]["similarity"] == 0.95

    async def test_search_by_similarity_with_category_filter(self, db_session):
        """Test search_by_similarity with category filter."""
        from unittest.mock import AsyncMock, MagicMock, patch

        # Arrange
        repo = ProductEmbeddingRepository(db_session)
        query_embedding = [0.9] * 1536

        mock_row = MagicMock()
        mock_row.id = 1
        mock_row.title = "Electronics Product"
        mock_row.description = "Test"
        mock_row.category = "electronics"
        mock_row.price = "99.99"
        mock_row.tags = None
        mock_row.url = None
        mock_row.image_url = None
        mock_row.similarity = 0.92

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]

        # Act
        with patch.object(db_session, 'execute', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_result
            results = await repo.search_by_similarity(
                query_embedding=query_embedding,
                limit=5,
                category_filter="electronics"
            )

        # Assert
        assert len(results) == 1
        assert results[0]["category"] == "electronics"

    async def test_search_by_similarity_include_inactive(self, db_session):
        """Test search_by_similarity can include inactive products."""
        from unittest.mock import AsyncMock, MagicMock, patch

        # Arrange
        repo = ProductEmbeddingRepository(db_session)
        query_embedding = [0.9] * 1536

        mock_row = MagicMock()
        mock_row.id = 1
        mock_row.title = "Inactive Product"
        mock_row.description = "Test"
        mock_row.category = "test"
        mock_row.price = "50"
        mock_row.tags = None
        mock_row.url = None
        mock_row.image_url = None
        mock_row.similarity = 0.88

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]

        # Act
        with patch.object(db_session, 'execute', new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = mock_result
            results = await repo.search_by_similarity(
                query_embedding=query_embedding,
                limit=5,
                include_inactive=True
            )

        # Assert
        assert len(results) == 1

    async def test_search_by_similarity_retry_on_concurrency_error(self, db_session):
        """Test search_by_similarity retries on database concurrency issues."""
        from unittest.mock import AsyncMock, MagicMock, patch
        import asyncio

        # Arrange
        repo = ProductEmbeddingRepository(db_session)
        query_embedding = [0.9] * 1536

        mock_row = MagicMock()
        mock_row.id = 1
        mock_row.title = "Test Product"
        mock_row.description = "Test"
        mock_row.category = "test"
        mock_row.price = "10"
        mock_row.tags = None
        mock_row.url = None
        mock_row.image_url = None
        mock_row.similarity = 0.9

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]

        # Mock that fails first, then succeeds
        call_count = 0
        async def mock_execute_with_retry(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("another operation is in progress")
            return mock_result

        # Act
        with patch.object(db_session, 'execute', side_effect=mock_execute_with_retry):
            with patch('asyncio.sleep', new_callable=AsyncMock):
                results = await repo.search_by_similarity(
                    query_embedding=query_embedding,
                    limit=5
                )

        # Assert
        assert call_count == 2  # Failed once, then succeeded
        assert len(results) == 1

    async def test_search_by_similarity_max_retries_exhausted(self, db_session):
        """Test search_by_similarity raises error when max retries exhausted."""
        from unittest.mock import AsyncMock, patch

        # Arrange
        repo = ProductEmbeddingRepository(db_session)
        query_embedding = [0.9] * 1536

        # Mock that always fails with concurrency error
        async def mock_execute_always_fails(*args, **kwargs):
            raise Exception("another operation is in progress")

        # Act & Assert
        with patch.object(db_session, 'execute', side_effect=mock_execute_always_fails):
            with patch('asyncio.sleep', new_callable=AsyncMock):
                with pytest.raises(Exception, match="another operation is in progress"):
                    await repo.search_by_similarity(
                        query_embedding=query_embedding,
                        limit=5
                    )

    async def test_search_by_similarity_non_concurrency_error_raises_immediately(self, db_session):
        """Test search_by_similarity raises non-concurrency errors immediately."""
        from unittest.mock import AsyncMock, patch

        # Arrange
        repo = ProductEmbeddingRepository(db_session)
        query_embedding = [0.9] * 1536

        # Mock that fails with different error
        async def mock_execute_fails(*args, **kwargs):
            raise ValueError("Invalid SQL query")

        # Act & Assert
        with patch.object(db_session, 'execute', side_effect=mock_execute_fails):
            with pytest.raises(ValueError, match="Invalid SQL query"):
                await repo.search_by_similarity(
                    query_embedding=query_embedding,
                    limit=5
                )
