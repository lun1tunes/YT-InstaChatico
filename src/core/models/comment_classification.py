from __future__ import annotations
from typing import TYPE_CHECKING
from datetime import datetime
from enum import Enum
from sqlalchemy import ForeignKey, String, Integer, Text, JSON, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

if TYPE_CHECKING:
    from .instagram_comment import InstagramComment


class ProcessingStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRY = "RETRY"


class CommentClassification(Base):
    __tablename__ = "comments_classification"

    id: Mapped[int] = mapped_column(primary_key=True)
    comment_id: Mapped[str] = mapped_column(
        ForeignKey("instagram_comments.id", ondelete="CASCADE"), unique=True, index=True
    )

    processing_status: Mapped[ProcessingStatus] = mapped_column(
        SQLEnum(ProcessingStatus, name="processingstatus"), default=ProcessingStatus.PENDING
    )
    processing_started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    processing_completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    retry_count: Mapped[int] = mapped_column(default=0)
    max_retries: Mapped[int] = mapped_column(default=5)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence: Mapped[int | None] = mapped_column(nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Token usage tracking
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationship
    comment: Mapped[InstagramComment] = relationship(
        back_populates="classification",
        passive_deletes=True,
    )
