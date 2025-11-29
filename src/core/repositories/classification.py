"""Classification repository for comment classification data access."""

import logging
from datetime import datetime
from typing import Optional, List
from sqlalchemy import select, and_, case, func, join
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseRepository
from ..models.comment_classification import CommentClassification, ProcessingStatus
from ..models.instagram_comment import InstagramComment

logger = logging.getLogger(__name__)


class ClassificationRepository(BaseRepository[CommentClassification]):
    """Repository for comment classifications."""

    def __init__(self, session: AsyncSession):
        super().__init__(CommentClassification, session)

    async def get_by_comment_id(self, comment_id: str) -> Optional[CommentClassification]:
        """Get classification by comment ID."""
        result = await self.session.execute(
            select(CommentClassification).where(
                CommentClassification.comment_id == comment_id
            )
        )
        return result.scalar_one_or_none()

    async def get_pending_retries(self) -> List[CommentClassification]:
        """Get classifications pending retry."""
        result = await self.session.execute(
            select(CommentClassification).where(
                and_(
                    CommentClassification.processing_status == ProcessingStatus.RETRY,
                    CommentClassification.retry_count < CommentClassification.max_retries
                )
            )
        )
        return list(result.scalars().all())

    async def mark_processing(self, classification: CommentClassification, retry_count: int = 0):
        """Update classification to processing status."""
        from ..utils.time import now_db_utc
        classification.processing_status = ProcessingStatus.PROCESSING
        classification.processing_started_at = now_db_utc()
        classification.retry_count = retry_count
        await self.session.flush()

    async def mark_completed(self, classification: CommentClassification):
        """Update classification to completed status."""
        from ..utils.time import now_db_utc
        classification.processing_status = ProcessingStatus.COMPLETED
        classification.processing_completed_at = now_db_utc()
        classification.last_error = None
        await self.session.flush()

    async def mark_retry(self, classification: CommentClassification, error: str):
        """Update classification to retry status with error message."""
        from ..utils.time import now_db_utc
        classification.processing_status = ProcessingStatus.RETRY
        classification.processing_completed_at = now_db_utc()
        classification.last_error = error
        await self.session.flush()

    async def mark_failed(self, classification: CommentClassification, error: str):
        """Update classification to failed status."""
        from ..utils.time import now_db_utc
        classification.processing_status = ProcessingStatus.FAILED
        classification.last_error = error
        classification.processing_completed_at = now_db_utc()
        await self.session.flush()

    async def get_completed_stats_since(self, since: datetime) -> list[tuple[str | None, int, int]]:
        """
        Return aggregated counts of completed classifications grouped by type.

        Args:
            since: Datetime threshold used to compute "increment" counts

        Returns:
            List of tuples: (classification_type, total_count, recent_count)
        """
        recent_case = case(
            (CommentClassification.processing_completed_at >= since, 1),
            else_=0,
        )
        stmt = (
            select(
                CommentClassification.type,
                func.count().label("total_count"),
                func.sum(recent_case).label("recent_count"),
            )
            .where(CommentClassification.processing_status == ProcessingStatus.COMPLETED)
            .group_by(CommentClassification.type)
        )
        result = await self.session.execute(stmt)
        return [
            (row[0], int(row[1] or 0), int(row[2] or 0))
            for row in result.all()
        ]

    async def get_completed_stats_since_by_media(
        self,
        media_ids: list[str],
        since: datetime,
    ) -> list[tuple[str, str | None, int, int]]:
        """
        Return aggregated counts grouped by media + classification type.

        Args:
            media_ids: List of media IDs to include
            since: Datetime threshold for increment counts

        Returns:
            Tuples: (media_id, classification_type, total_count, recent_count)
        """
        if not media_ids:
            return []

        recent_case = case(
            (CommentClassification.processing_completed_at >= since, 1),
            else_=0,
        )

        stmt = (
            select(
                InstagramComment.media_id,
                CommentClassification.type,
                func.count().label("total_count"),
                func.sum(recent_case).label("recent_count"),
            )
            .join(InstagramComment, InstagramComment.id == CommentClassification.comment_id)
            .where(
                InstagramComment.media_id.in_(media_ids),
                CommentClassification.processing_status == ProcessingStatus.COMPLETED,
            )
            .group_by(InstagramComment.media_id, CommentClassification.type)
        )
        result = await self.session.execute(stmt)
        return [
            (row[0], row[1], int(row[2] or 0), int(row[3] or 0))
            for row in result.all()
        ]
