from __future__ import annotations
from typing import TYPE_CHECKING
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column, relationship, foreign
from sqlalchemy import String, ForeignKey, Boolean, and_
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base
from .question_answer import QuestionAnswer

if TYPE_CHECKING:
    from .comment_classification import CommentClassification
    from .question_answer import QuestionAnswer
    from .media import Media


class InstagramComment(Base):
    __tablename__ = "instagram_comments"

    id: Mapped[str] = mapped_column(primary_key=True)
    media_id: Mapped[str] = mapped_column(String(100), ForeignKey("media.id"), comment="Foreign key to media table")
    user_id: Mapped[str]
    username: Mapped[str]
    text: Mapped[str]
    created_at: Mapped[datetime]
    raw_data = mapped_column(JSONB)

    # Comment hiding fields
    is_hidden: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="Whether comment is hidden on Instagram"
    )
    hidden_at: Mapped[datetime | None] = mapped_column(nullable=True, comment="Timestamp when comment was hidden")
    hidden_by_ai: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Parent comment ID for replies (nullable)
    parent_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="ID of the parent comment if this is a reply, NULL if it's a top-level comment",
    )

    # Session management for chained conversations
    conversation_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Conversation ID for session management - first_question_comment_{id} format",
    )

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Soft delete flag to track comments removed from Instagram",
    )

    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True, comment="Timestamp when comment was deleted")
    deleted_by_ai: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationship to classification
    classification: Mapped[CommentClassification] = relationship(
        "CommentClassification",
        back_populates="comment",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Relationship to question answer
    question_answer: Mapped[QuestionAnswer] = relationship(
        "QuestionAnswer",
        foreign_keys=[QuestionAnswer.comment_id],
        primaryjoin=lambda: and_(
            InstagramComment.id == foreign(QuestionAnswer.comment_id),
            QuestionAnswer.is_deleted.is_(False),
        ),
        uselist=False,
        passive_deletes=True,
        overlaps="classification",
    )

    # Relationship to media
    media: Mapped[Media] = relationship(
        "Media",
        foreign_keys="InstagramComment.media_id",
        primaryjoin="InstagramComment.media_id == Media.id",
        back_populates="comments",
        passive_deletes=False,  # Don't delete media when comment is deleted
    )
