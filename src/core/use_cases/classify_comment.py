"""Use case for comment classification (Business Logic Layer)."""

import logging
from typing import Any, Callable, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.comment_classification import CommentClassification
from ..constants.retry_policy import DEFAULT_RETRY_SCHEDULE
from ..interfaces.services import IClassificationService, IMediaService
from ..utils.decorators import handle_task_errors
from ..interfaces.repositories import ICommentRepository, IClassificationRepository

logger = logging.getLogger(__name__)


class ClassifyCommentUseCase:
    """
    Business logic for comment classification.

    Follows Single Responsibility Principle (SRP) and Dependency Inversion Principle (DIP).
    Depends on abstractions (protocols) rather than concrete implementations.
    """

    def __init__(
        self,
        session: AsyncSession,
        classification_service: IClassificationService,
        media_service: IMediaService,
        comment_repository_factory: Callable[..., ICommentRepository],
        classification_repository_factory: Callable[..., IClassificationRepository],
    ):
        """
        Initialize use case with dependencies.

        Args:
            session: Database session
            classification_service: Service implementing IClassificationService protocol
            media_service: Service implementing IMediaService protocol
            comment_repository_factory: Factory producing CommentRepository instances
            classification_repository_factory: Factory producing ClassificationRepository instances
        """
        self.session = session
        self.comment_repo: ICommentRepository = comment_repository_factory(session=session)
        self.classification_repo: IClassificationRepository = classification_repository_factory(session=session)
        self.classification_service = classification_service
        self.media_service = media_service

    @handle_task_errors()
    async def execute(self, comment_id: str, retry_count: int = 0) -> Dict[str, Any]:
        """
        Execute comment classification use case.

        Simplified logic - no infrastructure concerns.
        """
        logger.info(f"Starting classification | comment_id={comment_id} | retry_count={retry_count}")

        # 1. Get comment with classification
        comment = await self.comment_repo.get_with_classification(comment_id)
        if not comment:
            logger.warning(f"Comment not found | comment_id={comment_id} | operation=classify_comment")
            return {"status": "error", "reason": "comment_not_found"}

        # 2. Ensure media exists
        media = await self.media_service.get_or_create_media(comment.media_id, self.session)
        if not media:
            logger.error(
                f"Media unavailable | comment_id={comment_id} | media_id={comment.media_id} | "
                f"operation=get_or_create_media"
            )
            return {"status": "error", "reason": "media_unavailable"}

        if media.is_processing_enabled is False:
            logger.info(
                f"Media processing disabled | comment_id={comment_id} | media_id={media.id} | "
                f"operation=classify_comment"
            )
            return {"status": "skipped", "reason": "media_processing_disabled"}

        # 3. Wait for media context if needed
        if await self._should_wait_for_media_context(media):
            logger.info(
                f"Waiting for media context | comment_id={comment_id} | media_id={media.id} | "
                f"media_type={media.media_type} | has_url={bool(media.media_url)}"
            )
            return {"status": "retry", "reason": "waiting_for_media_context"}

        # 4. Get or create classification record
        classification = await self._get_or_create_classification(comment_id)

        try:
            # 5. Update status to processing (no commit yet)
            await self.classification_repo.mark_processing(classification, retry_count)
            await self.session.flush()  # persist status within transaction

            # 6. Generate conversation ID
            conversation_id = self.classification_service.generate_conversation_id(comment.id, comment.parent_id)
            comment.conversation_id = conversation_id

            # 7. Build media context
            media_context = self._build_media_context(media)

            # 8. Classify comment
            result = await self.classification_service.classify_comment(comment.text, conversation_id, media_context)
        except Exception as exc:
            logger.error(
                f"Classification exception | comment_id={comment_id} | error={str(exc)} | "
                f"retry_count={retry_count}"
            )
            return await self._handle_failure(classification, str(exc), retry_count)

        # 9. Save results
        if result.error:
            logger.error(
                f"Classification failed | comment_id={comment_id} | error={result.error} | "
                f"retry_count={retry_count}"
            )
            return await self._handle_failure(classification, result.error, retry_count)

        classification.type = result.type
        classification.confidence = result.confidence
        classification.reasoning = result.reasoning
        classification.input_tokens = result.input_tokens
        classification.output_tokens = result.output_tokens

        await self.classification_repo.mark_completed(classification)

        try:
            await self.session.commit()
        except Exception as commit_exc:
            setattr(commit_exc, "should_reraise", True)
            await self.session.rollback()
            raise

        logger.info(
            f"Classification completed | comment_id={comment_id} | "
            f"classification={result.type} | confidence={result.confidence} | "
            f"input_tokens={result.input_tokens} | output_tokens={result.output_tokens} | "
            f"has_error={bool(result.error)}"
        )

        return {
            "status": "success",
            "comment_id": comment_id,
            "classification": result.type,
            "confidence": result.confidence,
        }


    def _calculate_max_retries(self, classification: CommentClassification) -> int:
        """Return configured max retries or fall back to default schedule length."""
        raw_value = getattr(classification, "max_retries", None)
        if isinstance(raw_value, int) and raw_value > 0:
            return raw_value
        fallback = len(DEFAULT_RETRY_SCHEDULE)
        classification.max_retries = fallback
        return fallback

    async def _handle_failure(self, classification: CommentClassification, error: str, retry_count: int) -> Dict[str, Any]:
        """Handle retry vs failure logic for classification errors."""
        max_retries = self._calculate_max_retries(classification)
        classification.retry_count = retry_count

        if retry_count < max_retries:
            await self.classification_repo.mark_retry(classification, error)
            try:
                await self.session.commit()
            except Exception as commit_exc:
                setattr(commit_exc, "should_reraise", True)
                await self.session.rollback()
                raise
            return {"status": "retry", "reason": error}

        await self.classification_repo.mark_failed(classification, error)
        try:
            await self.session.commit()
        except Exception as commit_exc:
            setattr(commit_exc, "should_reraise", True)
            await self.session.rollback()
            raise
        return {"status": "error", "reason": error}

    async def _get_or_create_classification(self, comment_id: str) -> CommentClassification:
        """Get existing or create new classification record."""
        classification = await self.classification_repo.get_by_comment_id(comment_id)

        if not classification:
            logger.debug(f"Creating new classification record | comment_id={comment_id}")
            classification = CommentClassification(comment_id=comment_id)
            await self.classification_repo.create(classification)

        return classification

    async def _should_wait_for_media_context(self, media) -> bool:
        """
        Check if we need to wait for media context analysis.

        We should wait if:
        1. Media has images (IMAGE or CAROUSEL_ALBUM)
        2. Media has URL for analysis
        3. Media context is not yet available
        4. Analysis task hasn't failed (we don't wait indefinitely for failed tasks)
        """
        has_image = media.media_type in ["IMAGE", "CAROUSEL_ALBUM"]
        has_url = bool(media.media_url)
        no_context = not media.media_context

        # If we have images but no context, we should wait
        # The analysis task will either succeed (add context) or fail (we'll proceed without context)
        should_wait = has_image and has_url and no_context

        if should_wait:
            logger.debug(
                f"Media context check | media_id={media.id} | media_type={media.media_type} | "
                f"has_url={has_url} | has_context={bool(media.media_context)} | should_wait={should_wait}"
            )

        return should_wait

    def _build_media_context(self, media) -> Dict[str, Any]:
        """Build media context dictionary."""
        return {
            "caption": media.caption,
            "media_type": media.media_type,
            "media_context": media.media_context,
            "username": media.username,
            "comments_count": media.comments_count,
            "like_count": media.like_count,
            "permalink": media.permalink,
            "media_url": media.media_url,
            "is_comment_enabled": media.is_comment_enabled,
        }
