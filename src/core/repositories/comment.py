"""Comment repository for Instagram comment data access."""

import logging
from datetime import datetime
from typing import Optional
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from .base import BaseRepository
from ..models.instagram_comment import InstagramComment
from ..models.comment_classification import CommentClassification, ProcessingStatus
from ..utils.time import now_db_utc

logger = logging.getLogger(__name__)


def _exclude_deleted(stmt: Select, include_deleted: bool = False) -> Select:
    """Optionally filter out soft-deleted comments."""
    if include_deleted:
        return stmt
    return stmt.where(InstagramComment.is_deleted.is_(False))


class CommentRepository(BaseRepository[InstagramComment]):
    """Repository for Instagram comments with relationships."""

    def __init__(self, session: AsyncSession):
        super().__init__(InstagramComment, session)

    async def get_by_id(self, comment_id: str) -> Optional[InstagramComment]:
        result = await self.session.execute(
            select(InstagramComment).where(
                InstagramComment.id == comment_id,
                InstagramComment.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_with_classification(self, comment_id: str) -> Optional[InstagramComment]:
        """Get comment with classification eagerly loaded."""
        result = await self.session.execute(
            _exclude_deleted(
                select(InstagramComment).options(selectinload(InstagramComment.classification))
            ).where(InstagramComment.id == comment_id)
        )
        return result.scalar_one_or_none()

    async def get_with_answer(self, comment_id: str) -> Optional[InstagramComment]:
        """Get comment with answer eagerly loaded."""
        result = await self.session.execute(
            _exclude_deleted(
                select(InstagramComment).options(selectinload(InstagramComment.question_answer))
            ).where(InstagramComment.id == comment_id)
        )
        return result.scalar_one_or_none()

    async def get_full(self, comment_id: str) -> Optional[InstagramComment]:
        """Get comment with all relationships eagerly loaded."""
        result = await self.session.execute(
            _exclude_deleted(
                select(InstagramComment).options(
                    selectinload(InstagramComment.classification),
                    selectinload(InstagramComment.question_answer),
                    selectinload(InstagramComment.media),
                )
            ).where(InstagramComment.id == comment_id)
        )
        return result.scalar_one_or_none()

    def _apply_filters(
        self,
        stmt: Select,
        *,
        statuses: Optional[list[ProcessingStatus]] = None,
        classification_types: Optional[list[str]] = None,
    ) -> Select:
        if statuses or classification_types:
            stmt = stmt.join(InstagramComment.classification)
            if statuses:
                stmt = stmt.where(CommentClassification.processing_status.in_(statuses))
            if classification_types:
                stmt = stmt.where(CommentClassification.type.in_(classification_types))
        return stmt

    async def list_recent(
        self,
        *,
        offset: int,
        limit: int,
        statuses: Optional[list[ProcessingStatus]] = None,
        classification_types: Optional[list[str]] = None,
        include_deleted: bool = True,
    ) -> list[InstagramComment]:
        stmt = select(InstagramComment).options(
            selectinload(InstagramComment.classification),
            selectinload(InstagramComment.question_answer),
        )
        stmt = _exclude_deleted(stmt, include_deleted=include_deleted)
        stmt = self._apply_filters(
            stmt,
            statuses=statuses,
            classification_types=classification_types,
        )
        stmt = stmt.order_by(
            InstagramComment.created_at.desc(),
            InstagramComment.id.desc(),
        ).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_media(
        self,
        media_id: str,
        *,
        offset: int,
        limit: int,
        statuses: Optional[list[ProcessingStatus]] = None,
        classification_types: Optional[list[str]] = None,
        include_deleted: bool = True,
    ) -> list[InstagramComment]:
        stmt = select(InstagramComment).options(
            selectinload(InstagramComment.classification),
            selectinload(InstagramComment.question_answer),
        )
        stmt = stmt.where(InstagramComment.media_id == media_id)
        stmt = _exclude_deleted(stmt, include_deleted=include_deleted)
        stmt = self._apply_filters(
            stmt,
            statuses=statuses,
            classification_types=classification_types,
        )
        stmt = stmt.order_by(
            InstagramComment.created_at.desc(),
            InstagramComment.id.desc(),
        ).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_all(
        self,
        *,
        statuses: Optional[list[ProcessingStatus]] = None,
        classification_types: Optional[list[str]] = None,
        include_deleted: bool = True,
    ) -> int:
        stmt = select(func.count()).select_from(InstagramComment)
        if not include_deleted:
            stmt = stmt.where(InstagramComment.is_deleted.is_(False))
        stmt = self._apply_filters(
            stmt,
            statuses=statuses,
            classification_types=classification_types,
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def count_for_media(
        self,
        media_id: str,
        *,
        statuses: Optional[list[ProcessingStatus]] = None,
        classification_types: Optional[list[str]] = None,
        include_deleted: bool = True,
    ) -> int:
        stmt = select(func.count()).select_from(InstagramComment).where(
            InstagramComment.media_id == media_id,
        )
        if not include_deleted:
            stmt = stmt.where(InstagramComment.is_deleted.is_(False))
        stmt = self._apply_filters(
            stmt,
            statuses=statuses,
            classification_types=classification_types,
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def mark_deleted_with_descendants(self, comment_id: str, deleted_by_ai: bool = False) -> int:
        """
        Soft-delete a comment and all of its descendants.

        Returns:
            Number of rows affected.
        """
        descendants = (
            select(InstagramComment.id)
            .where(InstagramComment.id == comment_id)
            .cte(name="comment_descendants", recursive=True)
        )

        descendants = descendants.union_all(
            select(InstagramComment.id).where(InstagramComment.parent_id == descendants.c.id)
        )

        result_ids = await self.session.execute(select(descendants.c.id))
        ids = list(result_ids.scalars().all())
        if not ids:
            return 0

        comments_result = await self.session.execute(
            select(InstagramComment).where(InstagramComment.id.in_(ids))
        )
        comments = list(comments_result.scalars().all())
        timestamp = now_db_utc()
        for comment in comments:
            comment.is_deleted = True
            comment.is_hidden = False
            comment.hidden_at = None
            comment.deleted_at = timestamp
            comment.deleted_by_ai = deleted_by_ai

        return len(comments)

    async def get_latest_comment_timestamp(self, media_id: str) -> Optional[datetime]:
        """Return latest created_at for a media/video or None if none exist."""
        stmt = select(func.max(InstagramComment.created_at)).where(InstagramComment.media_id == media_id)
        result = await self.session.execute(stmt)
        return result.scalar()
