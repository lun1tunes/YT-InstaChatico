"""Product embedding repository for semantic search data access."""

import asyncio
import logging
from typing import Optional, List, Dict

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseRepository
from ..models.product_embedding import ProductEmbedding

logger = logging.getLogger(__name__)


class ProductEmbeddingRepository(BaseRepository[ProductEmbedding]):
    """Repository for ProductEmbedding operations with vector search."""

    def __init__(self, session: AsyncSession):
        super().__init__(ProductEmbedding, session)

    async def search_by_similarity(
        self,
        query_embedding: List[float],
        limit: int = 5,
        category_filter: Optional[str] = None,
        include_inactive: bool = False,
        similarity_threshold: float = 0.0,
        include_low_similarity: bool = False,
    ) -> List[Dict]:
        """
        Search products using cosine similarity with pgvector.

        Args:
            query_embedding: Query vector (1536 dimensions)
            limit: Maximum number of results to return
            category_filter: Optional category to filter by
            include_inactive: Whether to include inactive products
            similarity_threshold: Minimum similarity score (0-1)

        Returns:
            List of dicts with product info and similarity scores
        """
        limit = max(1, limit)

        column_type = (
            getattr(ProductEmbedding.embedding.type, "dimensions", None)
            or getattr(ProductEmbedding.embedding.type, "dims", None)
            or getattr(ProductEmbedding.embedding.type, "dim", None)
        )
        embedding_type = Vector(column_type or 1536)
        embedding_param = sa.bindparam("query_embedding", type_=embedding_type)
        distance_expr = ProductEmbedding.embedding.cosine_distance(embedding_param)
        similarity_expr = (1 - distance_expr).label("similarity")

        stmt = select(
            ProductEmbedding.id,
            ProductEmbedding.title,
            ProductEmbedding.description,
            ProductEmbedding.category,
            ProductEmbedding.price,
            ProductEmbedding.tags,
            ProductEmbedding.url,
            ProductEmbedding.image_url,
            similarity_expr,
        )

        if not include_inactive:
            stmt = stmt.where(ProductEmbedding.is_active.is_(True))

        if category_filter:
            stmt = stmt.where(ProductEmbedding.category == category_filter)

        stmt = stmt.order_by(distance_expr).limit(limit)

        rows = []
        max_retries = 3
        retry_delay = 0.1

        for attempt in range(max_retries):
            try:
                result = await self.session.execute(stmt, {"query_embedding": query_embedding})
                rows = result.fetchall()
                break
            except Exception as e:
                if "another operation is in progress" in str(e).lower() and attempt < max_retries - 1:
                    logger.warning(
                        "Database concurrency issue in product search, retrying in %.2fs (attempt %s/%s)",
                        retry_delay,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                raise

        results: List[Dict] = []
        for row in rows:
            similarity = float(row.similarity or 0)
            result_dict = {
                "id": row.id,
                "title": row.title,
                "description": row.description,
                "category": row.category,
                "price": row.price,
                "tags": row.tags,
                "url": row.url,
                "image_url": row.image_url,
                "similarity": round(similarity, 4),
                "is_ood": similarity < similarity_threshold,
            }
            if include_low_similarity or similarity >= similarity_threshold:
                results.append(result_dict)

        logger.debug("Found %s similar products", len(results))
        return results

    async def get_by_category(self, category: str, include_inactive: bool = False) -> List[ProductEmbedding]:
        """
        Get all products in a category.

        Args:
            category: Category name
            include_inactive: Whether to include inactive products

        Returns:
            List of products in the category
        """
        stmt = select(ProductEmbedding).where(ProductEmbedding.category == category)

        if not include_inactive:
            stmt = stmt.where(ProductEmbedding.is_active == True)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_products(self, limit: int = 100) -> List[ProductEmbedding]:
        """
        Get all active products.

        Args:
            limit: Maximum number of products to return

        Returns:
            List of active products
        """
        result = await self.session.execute(
            select(ProductEmbedding)
            .where(ProductEmbedding.is_active == True)
            .order_by(ProductEmbedding.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def deactivate(self, product: ProductEmbedding) -> None:
        """Mark product as inactive."""
        product.is_active = False
        await self.session.flush()

    async def activate(self, product: ProductEmbedding) -> None:
        """Mark product as active."""
        product.is_active = True
        await self.session.flush()

    async def update_embedding(self, product: ProductEmbedding, embedding: List[float]) -> None:
        """
        Update product embedding vector.

        Args:
            product: Product to update
            embedding: New embedding vector
        """
        product.embedding = embedding
        await self.session.flush()
