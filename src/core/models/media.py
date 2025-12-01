from __future__ import annotations
from typing import TYPE_CHECKING
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base
from ..utils.time import now_db_utc

if TYPE_CHECKING:
    from .instagram_comment import InstagramComment


class Media(Base):
    __tablename__ = "media"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, comment="Instagram media ID")
    permalink: Mapped[str] = mapped_column(Text, nullable=False, comment="Instagram post permalink URL")
    title: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="Post/video title")
    caption: Mapped[str | None] = mapped_column(String, nullable=True, comment="Post caption text")
    media_url: Mapped[str | None] = mapped_column(Text, nullable=True, comment="URL to the media file (first image for carousels)")
    media_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="Type of media (IMAGE, VIDEO, CAROUSEL_ALBUM)"
    )
    media_context: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="AI-generated detailed description and context of the media image"
    )
    children_media_urls = mapped_column(
        JSONB, nullable=True, comment="Array of all media URLs for CAROUSEL_ALBUM (includes all children images/videos)"
    )
    comments_count: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Number of comments on the post")
    like_count: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Number of likes on the post")
    shortcode: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="Instagram shortcode")
    posted_at: Mapped[datetime | None] = mapped_column(
        "timestamp",
        DateTime,
        nullable=True,
        comment="When the media was posted on Instagram",
    )
    analysis_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="When an AI image analysis job was last queued",
    )
    is_comment_enabled: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, comment="Whether comments are enabled"
    )
    is_processing_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether automated processing/classification is enabled",
    )
    username: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="Username of the media owner")
    owner: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="Owner account ID")

    # Additional metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_db_utc, comment="When this record was created"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_db_utc, onupdate=now_db_utc, comment="When this record was last updated"
    )
    raw_data = mapped_column(JSONB, nullable=True, comment="Raw Instagram API response data")

    # Relationship to comments (one-to-many, no cascade delete)
    comments: Mapped[list[InstagramComment]] = relationship(
        "InstagramComment",
        foreign_keys="InstagramComment.media_id",
        primaryjoin="Media.id == InstagramComment.media_id",
        back_populates="media",
        passive_deletes=False,  # Don't delete media when comments are deleted
    )
