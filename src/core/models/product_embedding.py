from __future__ import annotations
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, Index
from pgvector.sqlalchemy import Vector
from .base import Base
from ..utils.time import now_db_utc


class ProductEmbedding(Base):
    """Product/service with vector embeddings for semantic search via pgvector"""

    __tablename__ = "product_embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Product/service information
    title: Mapped[str] = mapped_column(String(500), nullable=False, comment="Product or service name/title")
    description: Mapped[str] = mapped_column(Text, nullable=False, comment="Detailed description")
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="Product category")
    price: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="Price information")

    # Vector embedding (OpenAI text-embedding-3-small = 1536 dimensions)
    embedding: Mapped[list] = mapped_column(
        Vector(1536), nullable=False, comment="Normalized embedding vector for semantic search"
    )

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_db_utc, comment="When this record was created"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_db_utc, onupdate=now_db_utc, comment="When this record was last updated"
    )
    is_active: Mapped[bool] = mapped_column(default=True, comment="Whether this product is active")

    # Additional metadata fields
    tags: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Comma-separated tags")
    url: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="Link to product page")
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="Product image URL")

    # Index for vector similarity search using cosine distance
    # Cosine distance is ideal for normalized vectors (1 - cosine_similarity)
    __table_args__ = (
        Index(
            "idx_product_embedding_cosine",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("idx_product_active", "is_active"),
        Index("idx_product_category", "category"),
    )
