"""YouTube video persistence service using MediaRepository."""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.interfaces.services import IYouTubeService
from core.models import Media
from core.repositories.media import MediaRepository
from core.utils.time import now_db_utc

logger = logging.getLogger(__name__)


def _parse_iso8601(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        logger.debug("Failed to parse datetime: %s", value)
        return None


class YouTubeMediaService:
    """Stores YouTube video metadata in the Media table for LLM context."""

    def __init__(self, youtube_service: IYouTubeService):
        self.youtube_service = youtube_service

    async def get_or_create_media(self, media_id: str, session: AsyncSession) -> Optional[Media]:
        """Compatibility wrapper for existing use cases (media == video)."""
        return await self.get_or_create_video(media_id, session)

    async def get_or_create_video(self, video_id: str, session: AsyncSession) -> Optional[Media]:
        repo = MediaRepository(session)
        existing = await repo.get_by_id(video_id)
        if existing:
            return existing

        try:
            details = await self.youtube_service.get_video_details(video_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to fetch video details | video_id=%s | error=%s", video_id, exc)
            return None

        items = details.get("items") or []
        if not items:
            logger.warning("Video not found on YouTube | video_id=%s", video_id)
            return None

        video = items[0]
        snippet: Dict[str, Any] = video.get("snippet", {})
        stats: Dict[str, Any] = video.get("statistics", {})
        thumbnails = snippet.get("thumbnails", {}) or {}
        # Pick high-res thumbnail if available
        thumb_url = (
            thumbnails.get("high", {}).get("url")
            or thumbnails.get("medium", {}).get("url")
            or thumbnails.get("default", {}).get("url")
        )

        media = Media(
            id=video_id,
            permalink=f"https://www.youtube.com/watch?v={video_id}",
            caption=snippet.get("description"),
            media_url=thumb_url,
            media_type="VIDEO",
            comments_count=_safe_int(stats.get("commentCount")),
            like_count=_safe_int(stats.get("likeCount")),
            shortcode=None,
            posted_at=_parse_iso8601(snippet.get("publishedAt")),
            is_comment_enabled=True,
            is_processing_enabled=True,
            username=snippet.get("channelTitle"),
            owner=snippet.get("channelId"),
            raw_data=video,
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )

        media = await repo.create(media)
        await session.commit()
        await session.refresh(media)
        return media


def _safe_int(value) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return None
