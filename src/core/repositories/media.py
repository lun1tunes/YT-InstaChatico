"""Media repository for Instagram media data access."""

import logging
from typing import Optional
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseRepository
from ..models.media import Media

logger = logging.getLogger(__name__)


class MediaRepository(BaseRepository[Media]):
    """Repository for Instagram media with relationships."""

    def __init__(self, session: AsyncSession):
        super().__init__(Media, session)

    async def get_with_comments(self, media_id: str) -> Optional[Media]:
        """Get media with comments eagerly loaded."""
        result = await self.session.execute(
            select(Media)
            .options(selectinload(Media.comments))
            .where(Media.id == media_id)
        )
        return result.scalar_one_or_none()

    async def get_media_needing_analysis(self, limit: int = 10) -> list[Media]:
        """
        Get media that has images but no AI-generated context yet.

        Args:
            limit: Maximum number of media records to return

        Returns:
            List of Media objects needing image analysis
        """
        result = await self.session.execute(
            select(Media)
            .where(
                Media.media_type.in_(["IMAGE", "CAROUSEL_ALBUM"]),
                Media.media_url.isnot(None),
                Media.media_context.is_(None)
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def exists_by_id(self, media_id: str) -> bool:
        """Check if media exists by ID."""
        media = await self.get_by_id(media_id)
        return media is not None

    async def count_all(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(Media))
        return result.scalar() or 0

    async def list_paginated(self, *, offset: int, limit: int) -> list[Media]:
        stmt = (
            select(Media)
            .order_by(Media.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
