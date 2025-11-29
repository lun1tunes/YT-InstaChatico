"""Service for generating embeddings and semantic search with OOD detection"""

import asyncio
import logging
from typing import List, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from openai import AsyncOpenAI

from ..config import settings
from ..models import ProductEmbedding
from ..repositories.product_embedding import ProductEmbeddingRepository
from ..utils.comment_context import get_comment_context

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Handles vector embeddings and similarity search with OOD detection"""

    def __init__(self):
        """Initialize with threshold settings"""
        # Load settings from config (can be overridden via environment variables)
        self.EMBEDDING_MODEL = settings.embedding.model
        self.EMBEDDING_DIMENSIONS = settings.embedding.dimensions

        # Cosine similarity threshold for out-of-distribution detection
        # Cosine similarity ranges from -1 to 1, with 1 being identical
        # For normalized vectors, cosine distance = 1 - cosine_similarity
        # A threshold of 0.7 means we only accept results with similarity > 0.7
        # Can be adjusted via EMBEDDING_SIMILARITY_THRESHOLD env variable
        self.SIMILARITY_THRESHOLD = settings.embedding.similarity_threshold

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - no cleanup needed (singleton manages client)"""
        return False

    async def generate_embedding(
        self,
        text: str,
        *,
        comment_id: Optional[str] = None,
        media_id: Optional[str] = None,
    ) -> List[float]:
        """Generate normalized embedding vector using OpenAI API (1536 dims)"""
        try:
            logger.debug(f"Generating embedding for text: {text[:100]}...")

            # Create new client each time to avoid event loop issues in Celery
            ctx = get_comment_context()
            comment_ref = comment_id or ctx.get("comment_id")
            async with AsyncOpenAI(api_key=settings.openai.api_key) as client:
                response = await client.embeddings.create(
                    model=self.EMBEDDING_MODEL, input=text, encoding_format="float"
                )

                embedding = response.data[0].embedding
                logger.debug(f"Generated embedding with {len(embedding)} dimensions")

                usage = getattr(response, "usage", None)
                tokens_in = None
                total_tokens = None
                if usage:
                    tokens_in = getattr(usage, "prompt_tokens", None)
                    total_tokens = getattr(usage, "total_tokens", None)
                    if tokens_in is None and total_tokens is not None:
                        tokens_in = total_tokens

                # Record usage when available (comment/media IDs default to None)
                try:
                    from ..container import get_container  # local import to avoid circular dependency

                    inspector = get_container().tools_token_usage_inspector(session=None)
                    await inspector.record(
                        tool="embedding_service",
                        task="generate_embedding",
                        model=self.EMBEDDING_MODEL,
                        tokens_in=tokens_in,
                        tokens_out=None,
                        comment_id=comment_ref,
                        metadata={
                            "text_length": len(text),
                            "total_tokens": total_tokens,
                        },
                    )
                except Exception:
                    logger.debug("Skipping token usage logging for embedding service", exc_info=True)

                return embedding

        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise

    async def search_similar_products(
        self,
        query: str,
        session: AsyncSession,
        limit: int = 5,
        category_filter: Optional[str] = None,
        include_inactive: bool = False,
        *,
        comment_id: Optional[str] = None,
        media_id: Optional[str] = None,
    ) -> List[Dict]:
        """
        Search products using cosine similarity, marks OOD results (< threshold).
        Returns list of dicts with id, title, description, price, similarity, is_ood.
        """
        try:
            logger.info(f"Searching for products similar to: {query}")

            # Generate embedding for the query
            query_embedding = await self.generate_embedding(query, comment_id=comment_id, media_id=media_id)

            # Use repository for vector search with retry logic
            product_repo = ProductEmbeddingRepository(session)

            # Add retry logic for database concurrency issues
            max_retries = 3
            retry_delay = 0.1

            for attempt in range(max_retries):
                try:
                    results = await product_repo.search_by_similarity(
                        query_embedding=query_embedding,
                        limit=limit,
                        category_filter=category_filter,
                        include_inactive=include_inactive,
                        similarity_threshold=self.SIMILARITY_THRESHOLD,
                        include_low_similarity=True,
                    )
                    break  # Success, exit retry loop
                except Exception as e:
                    if "another operation is in progress" in str(e) and attempt < max_retries - 1:
                        logger.warning(
                            f"Database concurrency issue in search, retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})"
                        )
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                        continue
                    else:
                        # Re-raise if it's not a concurrency issue or we've exhausted retries
                        raise

            logger.info(
                f"Found {len(results)} results for query: {query}, " f"{sum(1 for r in results if r['is_ood'])} are OOD"
            )

            return results

        except Exception as e:
            logger.error(f"Failed to search similar products: {e}")
            raise

    async def add_product(
        self,
        title: str,
        description: str,
        session: AsyncSession,
        category: Optional[str] = None,
        price: Optional[str] = None,
        tags: Optional[str] = None,
        url: Optional[str] = None,
        image_url: Optional[str] = None,
        is_active: bool = True,
    ) -> ProductEmbedding:
        """Add product with auto-generated embedding to database"""
        try:
            logger.info(f"Adding product: {title}")

            # Generate embedding from title + description
            text_to_embed = f"{title}\n{description}"
            embedding = await self.generate_embedding(text_to_embed, media_id=None, comment_id=None)

            # Create product record
            product = ProductEmbedding(
                title=title,
                description=description,
                category=category,
                price=price,
                tags=tags,
                url=url,
                image_url=image_url,
                embedding=embedding,
                is_active=is_active,
            )

            # Use repository to create product
            product_repo = ProductEmbeddingRepository(session)
            product = await product_repo.create(product)
            await session.commit()
            await session.refresh(product)

            logger.info(f"Successfully added product: {title} (ID: {product.id})")

            return product

        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to add product: {e}")
            raise

    async def update_product_embedding(self, product_id: int, session: AsyncSession) -> Optional[ProductEmbedding]:
        """Regenerate and update embedding for existing product"""
        try:
            logger.info(f"Updating embedding for product ID: {product_id}")

            # Use repository to get product
            product_repo = ProductEmbeddingRepository(session)
            product = await product_repo.get_by_id(product_id)

            if not product:
                logger.warning(f"Product {product_id} not found")
                return None

            # Regenerate embedding
            text_to_embed = f"{product.title}\n{product.description}"
            embedding = await self.generate_embedding(text_to_embed, media_id=None, comment_id=None)

            # Update product using repository
            await product_repo.update_embedding(product, embedding)
            await session.commit()
            await session.refresh(product)

            logger.info(f"Successfully updated embedding for product: {product.title}")

            return product

        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to update product embedding: {e}")
            raise
