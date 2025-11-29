import logging
from typing import Optional, Dict, Any
from datetime import datetime
from ..utils.time import now_db_utc

from sqlalchemy.ext.asyncio import AsyncSession

from ..interfaces.services import IInstagramService, ITaskQueue
from ..models import Media
from ..repositories.media import MediaRepository

logger = logging.getLogger(__name__)


class MediaService:
    """
    Manage Instagram media information.

    Follows SOLID principles - depends on abstractions (IInstagramService, ITaskQueue),
    not concretions.
    """

    def __init__(
        self,
        instagram_service: IInstagramService,
        task_queue: ITaskQueue,
    ):
        """
        Initialize MediaService with dependencies.

        Args:
            instagram_service: Service implementing IInstagramService protocol
            task_queue: Task queue implementing ITaskQueue protocol
        """
        self.instagram_service = instagram_service
        self.task_queue = task_queue

    async def get_or_create_media(self, media_id: str, session: AsyncSession) -> Optional[Media]:
        """Get media from DB or fetch from Instagram API."""
        try:
            # Use repository for data access
            media_repo = MediaRepository(session)

            # First, check if media already exists in database
            media = await media_repo.get_by_id(media_id)

            if media:
                logger.debug(f"Media {media_id} already exists in database")

                await self._queue_analysis_if_needed(media, session)
                return media

            # Media doesn't exist, fetch from Instagram API
            logger.debug(f"Media {media_id} not found in database, fetching from Instagram API")
            api_response = await self.instagram_service.get_media_info(media_id)

            if not api_response.get("success"):
                logger.error(f"Failed to fetch media info for {media_id}: {api_response.get('error')}")
                return None

            media_info = api_response["media_info"]

            # Extract and process children media URLs for carousels
            children_media_urls = self._extract_carousel_children_urls(media_info)

            # For carousels, use first child URL as media_url if not present
            media_url = media_info.get("media_url")
            if media_info.get("media_type") == "CAROUSEL_ALBUM" and children_media_urls and not media_url:
                media_url = children_media_urls[0] if children_media_urls else None
                logger.info(f"Using first child URL as media_url for carousel {media_id}")

            # Create new Media object
            media = Media(
                id=media_id,
                permalink=media_info.get("permalink"),
                caption=media_info.get("caption"),
                media_url=media_url,
                media_type=media_info.get("media_type"),
                children_media_urls=children_media_urls,  # Store all carousel URLs
                comments_count=media_info.get("comments_count"),
                like_count=media_info.get("like_count"),
                shortcode=media_info.get("shortcode"),
                posted_at=self._parse_posted_at(media_info.get("timestamp")),
                is_comment_enabled=media_info.get("is_comment_enabled"),
                is_processing_enabled=media_info.get("is_processing_enabled", True),
                username=media_info.get("username"),
                owner=self._parse_owner(media_info.get("owner")),
                raw_data=media_info,
                created_at=now_db_utc(),
                updated_at=now_db_utc(),
            )

            # Use repository to create media
            media = await media_repo.create(media)
            await session.commit()
            await session.refresh(media)

            logger.info(f"Created media record for {media_id}")

            # Queue image analysis task if media is an image
            await self._queue_analysis_if_needed(media, session)

            return media

        except Exception:
            logger.exception(f"Exception while getting/creating media {media_id}")
            await session.rollback()
            return None

    async def _queue_analysis_if_needed(self, media: Media, session: AsyncSession) -> None:
        """Queue image analysis task once per media while tracking request timestamp."""
        if media.media_type not in ["IMAGE", "CAROUSEL_ALBUM"]:
            return
        if not media.media_url:
            return
        if media.media_context:
            return
        if media.analysis_requested_at:
            logger.debug(
                "Analysis already requested | media_id=%s | requested_at=%s",
                media.id,
                media.analysis_requested_at,
            )
            return

        try:
            self.task_queue.enqueue(
                "core.tasks.media_tasks.analyze_media_image_task",
                media.id,
            )
            logger.info(f"Queued image analysis task for media {media.id}")
        except Exception as e:
            logger.warning(f"Failed to queue image analysis for {media.id}: {e}")
            return

        media.analysis_requested_at = now_db_utc()
        try:
            await session.commit()
            await session.refresh(media)
        except Exception:
            logger.exception(
                "Failed to persist analysis request flag | media_id=%s",
                media.id,
            )
            await session.rollback()

    def _extract_carousel_children_urls(self, media_info: dict) -> Optional[list]:
        """
        Extract media URLs from carousel children.

        Args:
            media_info: Raw media info from Instagram API

        Returns:
            List of media URLs or None if not a carousel or no children
        """
        if media_info.get("media_type") != "CAROUSEL_ALBUM":
            return None

        if "children" not in media_info:
            return None

        children_data = media_info.get("children", {}).get("data", [])
        if not children_data:
            return None

        children_urls = [
            child.get("media_url")
            for child in children_data
            if child.get("media_url")
        ]

        if children_urls:
            logger.info(f"Extracted {len(children_urls)} children media URLs from carousel")
            return children_urls

        return None

    def _parse_posted_at(self, timestamp_str: Optional[str]) -> Optional[datetime]:
        """Parse ISO posted_at string to datetime."""
        if not timestamp_str:
            return None

        try:
            # Instagram timestamps are typically in ISO format
            dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            # Convert to timezone-naive datetime for database storage
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            return dt
        except (ValueError, AttributeError) as e:
            logger.warning(f"Failed to parse posted_at '{timestamp_str}': {e}")
            return None

    def _parse_timestamp(self, timestamp_str: Optional[str]) -> Optional[datetime]:
        """Backward-compatible wrapper for posted_at parsing."""
        return self._parse_posted_at(timestamp_str)

    def _parse_owner(self, owner_data: Optional[dict]) -> Optional[str]:
        """Parse owner data to owner ID string."""
        if not owner_data:
            return None
        return owner_data.get("id") if isinstance(owner_data, dict) else (owner_data if isinstance(owner_data, str) else None)

    async def refresh_media_urls(self, media_id: str, session: AsyncSession) -> Optional[Media]:
        """Refresh media URLs by fetching latest data from Instagram."""
        logger.debug("Refreshing media URLs | media_id=%s", media_id)

        media_repo = MediaRepository(session)
        media = await media_repo.get_by_id(media_id)
        if not media:
            logger.warning("Cannot refresh media URLs; media not found | media_id=%s", media_id)
            return None

        try:
            api_response = await self.instagram_service.get_media_info(media_id)
            if not api_response.get("success"):
                logger.error(
                    "Failed to refresh media info from Instagram | media_id=%s | error=%s",
                    media_id,
                    api_response.get("error"),
                )
                return None

            media_info = api_response["media_info"]
            children_media_urls = self._extract_carousel_children_urls(media_info)

            media_url = media_info.get("media_url")
            if media_info.get("media_type") == "CAROUSEL_ALBUM" and children_media_urls and not media_url:
                media_url = children_media_urls[0]

            media.media_url = media_url
            media.children_media_urls = children_media_urls
            media.media_type = media_info.get("media_type") or media.media_type
            media.permalink = media_info.get("permalink", media.permalink)
            media.caption = media_info.get("caption", media.caption)
            media.comments_count = media_info.get("comments_count", media.comments_count)
            media.like_count = media_info.get("like_count", media.like_count)
            media.username = media_info.get("username", media.username)
            new_owner = self._parse_owner(media_info.get("owner"))
            if new_owner:
                media.owner = new_owner
            if posted_at := self._parse_posted_at(media_info.get("timestamp")):
                media.posted_at = posted_at

            media.updated_at = now_db_utc()

            await session.commit()
            await session.refresh(media)

            logger.info("Media URLs refreshed successfully | media_id=%s", media_id)
            return media
        except Exception:
            logger.exception("Error refreshing media URLs | media_id=%s", media_id)
            await session.rollback()
            return None

    async def ensure_media_exists(self, media_id: str, session: AsyncSession) -> bool:
        """Ensure media exists in DB, queue task if not found."""
        try:
            # Use repository for data access
            media_repo = MediaRepository(session)

            # Check if media already exists
            if await media_repo.exists_by_id(media_id):
                logger.debug(f"Media {media_id} already exists in database")
                return True

            # Media doesn't exist, queue task for background processing
            logger.info(f"Media {media_id} not found, queuing background task")
            self.task_queue.enqueue(
                "core.tasks.media_tasks.process_media_task",
                media_id,
            )

            return True

        except Exception as e:
            logger.error(f"Exception while ensuring media {media_id} exists: {e}")
            return False

    async def set_comment_status(
        self,
        media_id: str,
        enabled: bool,
        session: AsyncSession,
    ) -> Dict[str, Any]:
        """Enable or disable comments for a media item and persist the change."""
        logger.info(
            f"Setting comment status | media_id={media_id} | enabled={enabled}"
        )

        try:
            api_result = await self.instagram_service.set_media_comment_status(media_id, enabled)
            if not api_result.get("success"):
                logger.error(
                    f"Failed to update remote comment status | media_id={media_id} | error={api_result.get('error')}"
                )
                return api_result

            media_repo = MediaRepository(session)
            media = await media_repo.get_by_id(media_id)
            if not media:
                logger.debug(f"Media {media_id} missing locally, attempting to create")
                media = await self.get_or_create_media(media_id, session)

            if not media:
                logger.error(f"Unable to update comment status; media {media_id} not found")
                await session.rollback()
                return {
                    "success": False,
                    "error": "media_not_found",
                }

            media.is_comment_enabled = enabled
            media.updated_at = now_db_utc()
            await media_repo.update(media)
            await session.commit()
            await session.refresh(media)

            logger.info(
                f"Media comment status updated | media_id={media_id} | enabled={enabled}"
            )
            return {
                "success": True,
                "media_id": media_id,
                "is_comment_enabled": enabled,
            }

        except Exception as exc:
            logger.exception(
                f"Exception while updating media comment status | media_id={media_id} | error={exc}"
            )
            await session.rollback()
            return {"success": False, "error": str(exc)}
