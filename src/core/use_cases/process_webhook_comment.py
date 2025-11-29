"""Process webhook comment use case - handles comment ingestion from Instagram webhooks."""

import inspect
import logging
from typing import Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError, MissingGreenlet

from ..config import settings
from ..models.instagram_comment import InstagramComment
from ..models.comment_classification import CommentClassification, ProcessingStatus
from ..interfaces.services import IMediaService, ITaskQueue
from ..interfaces.repositories import ICommentRepository, IMediaRepository

logger = logging.getLogger(__name__)


class ProcessWebhookCommentUseCase:
    """
    Process incoming comment from Instagram webhook.

    Follows Dependency Inversion Principle - depends on service protocols.

    Responsibilities:
    - Validate comment doesn't already exist
    - Ensure media exists (or create it)
    - Create comment and classification records
    - Queue classification task via ITaskQueue
    """

    def __init__(
        self,
        session: AsyncSession,
        media_service: IMediaService,
        task_queue: ITaskQueue,
        comment_repository_factory: Callable[..., ICommentRepository],
        media_repository_factory: Callable[..., IMediaRepository],
    ):
        """
        Initialize use case with dependencies.

        Args:
            session: Database session
            media_service: Service implementing IMediaService protocol
            task_queue: Task queue implementing ITaskQueue protocol
            comment_repository_factory: Factory producing CommentRepository instances
            media_repository_factory: Factory producing MediaRepository instances
        """
        self.session = session
        self.comment_repo: ICommentRepository = comment_repository_factory(session=session)
        self.media_repo: IMediaRepository = media_repository_factory(session=session)
        self.media_service = media_service
        self.task_queue = task_queue

    async def execute(
        self,
        comment_id: str,
        media_id: str,
        user_id: str,
        username: str,
        text: str,
        entry_timestamp: int,
        parent_id: Optional[str] = None,
        raw_data: Optional[dict] = None,
        entry_owner_id: Optional[str] = None,
    ) -> dict:
        """
        Process incoming webhook comment.

        Returns:
            {
                "status": "created" | "exists" | "error",
                "comment_id": str,
                "should_classify": bool,
                "reason": str (optional),
            }
        """
        logger.info(
            f"Processing webhook comment | comment_id={comment_id} | media_id={media_id} | "
            f"username={username} | has_parent={bool(parent_id)} | text_length={len(text)}"
        )

        expected_owner_id = settings.instagram.base_account_id

        try:
            # Check if comment already exists
            existing = await self.comment_repo.get_by_id(comment_id)

            if existing:
                classification = None
                try:
                    classification = existing.classification
                except MissingGreenlet:
                    fetch_with_relationship = getattr(self.comment_repo, "get_with_classification", None)
                    if fetch_with_relationship:
                        fetched = fetch_with_relationship(comment_id)
                        existing = await fetched if inspect.isawaitable(fetched) else fetched
                        classification = existing.classification if existing else None

                # Check if needs re-classification
                should_classify = (
                    not classification
                    or classification.processing_status != ProcessingStatus.COMPLETED
                )

                logger.info(
                    f"Comment already exists | comment_id={comment_id} | should_classify={should_classify} | "
                    f"has_classification={bool(classification)} | "
                    f"classification_status={classification.processing_status if classification else 'N/A'}"
                )

                return {
                    "status": "exists",
                    "comment_id": comment_id,
                    "should_classify": should_classify,
                    "reason": "Comment already exists, may need re-classification",
                }

            # Ensure media exists
            media = await self.media_service.get_or_create_media(media_id, self.session)
            if not media:
                logger.error(f"Failed to create media | comment_id={comment_id} | media_id={media_id}")
                return {
                    "status": "error",
                    "comment_id": comment_id,
                    "should_classify": False,
                    "reason": "Failed to create media record",
                }

            # Validate media owner when available
            if expected_owner_id and entry_owner_id and entry_owner_id != expected_owner_id:
                logger.warning(
                    "Webhook account mismatch detected | comment_id=%s | entry_id=%s | expected_id=%s",
                    comment_id,
                    entry_owner_id,
                    expected_owner_id,
                )
                return {
                    "status": "forbidden",
                    "comment_id": comment_id,
                    "should_classify": False,
                    "reason": "Invalid webhook account",
                }

            # Create comment record
            logger.info(
                f"Creating new comment record | comment_id={comment_id} | media_id={media_id} | "
                f"username={username} | text_length={len(text)} | has_parent={bool(parent_id)}"
            )

            from datetime import datetime, timezone

            new_comment = InstagramComment(
                id=comment_id,
                media_id=media_id,
                user_id=user_id,
                username=username,
                text=text,
                # Store timestamps in UTC to keep reaction-time stats accurate
                created_at=datetime.fromtimestamp(entry_timestamp, tz=timezone.utc).replace(tzinfo=None),
                parent_id=parent_id,
                raw_data=raw_data or {},
            )

            # Create classification record
            new_comment.classification = CommentClassification(comment_id=comment_id)

            self.session.add(new_comment)
            await self.session.commit()

            logger.info(f"Comment created successfully | comment_id={comment_id} | should_classify=True")
            return {
                "status": "created",
                "comment_id": comment_id,
                "should_classify": True,
                "reason": "New comment created",
            }

        except IntegrityError:
            await self.session.rollback()
            logger.warning(f"Comment {comment_id} inserted by another process (race condition)")
            return {
                "status": "exists",
                "comment_id": comment_id,
                "should_classify": False,
                "reason": "Race condition - inserted by another process",
            }

        except Exception as e:
            await self.session.rollback()
            logger.exception(f"Error processing comment {comment_id}")
            return {
                "status": "error",
                "comment_id": comment_id,
                "should_classify": False,
                "reason": f"Unexpected error: {str(e)}",
            }
