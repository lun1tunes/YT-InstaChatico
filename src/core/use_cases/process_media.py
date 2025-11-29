"""Process media use case - handles media processing business logic."""

import logging
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from ..interfaces.services import IMediaService, IMediaAnalysisService
from ..schemas.media import MediaCreateResult, MediaAnalysisResult
from ..interfaces.repositories import IMediaRepository

logger = logging.getLogger(__name__)


class ProcessMediaUseCase:
    """
    Use case for processing Instagram media (fetch + analyze).

    Follows Dependency Inversion Principle - depends on service protocols.
    """

    def __init__(
        self,
        session: AsyncSession,
        media_service: IMediaService,
        analysis_service: IMediaAnalysisService,
        media_repository_factory: Callable[..., IMediaRepository],
    ):
        """
        Initialize use case with dependencies.

        Args:
            session: Database session
            media_service: Service implementing IMediaService protocol
            analysis_service: Service implementing IMediaAnalysisService protocol
            media_repository_factory: Factory producing MediaRepository instances
        """
        self.session = session
        self.media_repo: IMediaRepository = media_repository_factory(session=session)
        self.media_service = media_service
        self.analysis_service = analysis_service

    async def execute(self, media_id: str) -> MediaCreateResult:
        """Execute media processing use case."""
        logger.info(f"Starting media processing | media_id={media_id}")

        try:
            # 1. Check if media exists using repository
            existing_media = await self.media_repo.get_by_id(media_id)

            if existing_media:
                logger.info(
                    f"Media already exists | media_id={media_id} | username={existing_media.username} | "
                    f"media_type={existing_media.media_type}"
                )
                return MediaCreateResult(
                    status="success",
                    media_id=media_id,
                    action="already_exists",
                    media={
                        "id": existing_media.id,
                        "permalink": existing_media.permalink,
                        "username": existing_media.username,
                        "created_at": (
                            existing_media.created_at.isoformat() if existing_media.created_at else None
                        ),
                        "posted_at": (
                            existing_media.posted_at.isoformat() if existing_media.posted_at else None
                        ),
                    },
                )

            # 2. Fetch from Instagram API
            logger.info(f"Fetching media from Instagram API | media_id={media_id}")
            media = await self.media_service.get_or_create_media(media_id, self.session)

            if not media:
                logger.error(f"Failed to fetch media from API | media_id={media_id}")
                return MediaCreateResult(
                    status="error",
                    media_id=media_id,
                    reason="api_fetch_failed",
                )

            logger.info(
                f"Media processing completed | media_id={media_id} | action=created | "
                f"media_type={media.media_type} | comments_count={media.comments_count} | like_count={media.like_count}"
            )

            return MediaCreateResult(
                status="success",
                media_id=media_id,
                action="created",
                media={
                    "id": media.id,
                    "permalink": media.permalink,
                    "username": media.username,
                    "media_type": media.media_type,
                    "comments_count": media.comments_count,
                    "like_count": media.like_count,
                    "created_at": media.created_at.isoformat() if media.created_at else None,
                    "posted_at": media.posted_at.isoformat() if media.posted_at else None,
                },
            )
        except Exception as exc:
            logger.exception(f"Unexpected error processing media | media_id={media_id}")
            await self.session.rollback()
            return MediaCreateResult(
                status="error",
                media_id=media_id,
                reason=str(exc) or "unexpected_error",
            )


class AnalyzeMediaUseCase:
    """
    Use case for analyzing media images with AI.

    Follows Dependency Inversion Principle - depends on IMediaAnalysisService protocol.
    """

    def __init__(
        self,
        session: AsyncSession,
        analysis_service: IMediaAnalysisService,
        media_repository_factory: Callable[..., IMediaRepository],
    ):
        """
        Initialize use case with dependencies.

        Args:
            session: Database session
            analysis_service: Service implementing IMediaAnalysisService protocol
        """
        self.session = session
        self.media_repo: IMediaRepository = media_repository_factory(session=session)
        self.analysis_service = analysis_service

    async def execute(self, media_id: str) -> MediaAnalysisResult:
        """Execute media analysis use case."""
        logger.info(f"Starting media analysis | media_id={media_id}")

        try:
            # 1. Get media using repository
            media = await self.media_repo.get_by_id(media_id)

            if not media:
                logger.error(f"Media not found | media_id={media_id} | operation=analyze_media")
                return MediaAnalysisResult(status="error", media_id=media_id, reason=f"Media {media_id} not found")

            # 2. Check if already analyzed
            if media.media_context:
                if media.analysis_requested_at:
                    media.analysis_requested_at = None
                    await self.session.commit()
                logger.info(f"Media already analyzed | media_id={media_id} | skipping analysis")
                return MediaAnalysisResult(
                    status="skipped",
                    media_id=media_id,
                    reason="already_analyzed",
                )

            # 3. Check if media has image(s)
            if media.media_type not in ["IMAGE", "CAROUSEL_ALBUM"] or not media.media_url:
                if media.analysis_requested_at:
                    media.analysis_requested_at = None
                    await self.session.commit()
                logger.info(
                    f"No image to analyze | media_id={media_id} | media_type={media.media_type} | "
                    f"has_url={bool(media.media_url)}"
                )
                return MediaAnalysisResult(
                    status="skipped",
                    media_id=media_id,
                    reason="no_image_to_analyze",
                )

            # 4. Analyze image(s)
            try:
                if media.media_type == "CAROUSEL_ALBUM" and media.children_media_urls:
                    logger.info(
                        f"Analyzing carousel | media_id={media_id} | images_count={len(media.children_media_urls)}"
                    )
                    analysis_result = await self.analysis_service.analyze_carousel_images(
                        media_urls=media.children_media_urls,
                        caption=media.caption,
                    )
                else:
                    logger.info(f"Analyzing single image | media_id={media_id}")
                    analysis_result = await self.analysis_service.analyze_media_image(
                        media_url=media.media_url,
                        caption=media.caption,
                    )
            except Exception as analysis_exc:
                logger.exception(f"Exception during media analysis | media_id={media_id}")
                media.media_context = "ANALYSIS_FAILED"
                media.analysis_requested_at = None
                await self.session.commit()

                return MediaAnalysisResult(
                    status="error",
                    media_id=media_id,
                    reason=f"Analysis failed with exception: {analysis_exc}",
                )

            if analysis_result:
                media.media_context = analysis_result
                media.analysis_requested_at = None
                await self.session.commit()

                logger.info(
                    f"Media analysis completed | media_id={media_id} | "
                    f"images_analyzed={len(media.children_media_urls) if media.children_media_urls else 1} | "
                    f"context_length={len(analysis_result)}"
                )

                return MediaAnalysisResult(
                    status="success",
                    media_id=media_id,
                    media_context=media.media_context,
                    images_analyzed=len(media.children_media_urls) if media.children_media_urls else 1,
                )

            logger.error(
                f"Media analysis failed | media_id={media_id} | media_type={media.media_type} | "
                f"images_count={len(media.children_media_urls) if media.children_media_urls else 1} | "
                f"reason=no_result_returned"
            )

            media.media_context = "ANALYSIS_FAILED"
            media.analysis_requested_at = None
            await self.session.commit()

            return MediaAnalysisResult(
                status="error",
                media_id=media_id,
                reason="Analysis failed - no result returned",
            )
        except Exception as exc:
            logger.exception(f"Unexpected error during media analysis | media_id={media_id}")
            await self.session.rollback()
            return MediaAnalysisResult(
                status="error",
                media_id=media_id,
                reason=str(exc) or "unexpected_error",
            )
