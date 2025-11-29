"""Send Telegram notification use case - handles notification business logic."""

import logging
from typing import Any, Callable, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from ..interfaces.services import ITelegramService
from ..utils.decorators import handle_task_errors
from ..interfaces.repositories import ICommentRepository

logger = logging.getLogger(__name__)


class SendTelegramNotificationUseCase:
    """
    Use case for sending Telegram notifications for urgent/critical comments.

    Follows Dependency Inversion Principle - depends on ITelegramService protocol.
    """

    def __init__(
        self,
        session: AsyncSession,
        telegram_service: ITelegramService,
        comment_repository_factory: Callable[..., ICommentRepository],
    ):
        """
        Initialize use case with dependencies.

        Args:
            session: Database session
            telegram_service: Service implementing ITelegramService protocol
            comment_repository_factory: Factory producing CommentRepository instances
        """
        self.session = session
        self.comment_repo: ICommentRepository = comment_repository_factory(session=session)
        self.telegram_service = telegram_service

    @handle_task_errors()
    async def execute(self, comment_id: str) -> Dict[str, Any]:
        """Execute Telegram notification use case."""
        logger.info(f"Starting Telegram notification | comment_id={comment_id}")

        # 1. Get comment with classification
        comment = await self.comment_repo.get_with_classification(comment_id)
        if not comment:
            logger.error(f"Comment not found | comment_id={comment_id} | operation=send_telegram_notification")
            return {"status": "error", "reason": f"Comment {comment_id} not found"}

        if not comment.classification:
            logger.warning(f"Comment has no classification | comment_id={comment_id}")
            return {"status": "error", "reason": "no_classification"}

        # 2. Check if notification is needed
        classification = comment.classification.type.lower()
        notify_classifications = [
            "urgent issue / complaint",
            "critical feedback",
            "partnership proposal",
        ]

        logger.debug(
            f"Checking notification requirement | comment_id={comment_id} | "
            f"classification={classification} | requires_notification={classification in notify_classifications}"
        )

        if classification not in notify_classifications:
            logger.info(
                f"Notification not needed | comment_id={comment_id} | "
                f"classification={classification} | notify_classifications={notify_classifications}"
            )
            return {
                "status": "skipped",
                "reason": "no_notification_needed",
                "classification": classification,
            }

        # 3. Prepare notification data
        logger.info(
            f"Preparing Telegram notification | comment_id={comment_id} | "
            f"classification={comment.classification.type} | username={comment.username}"
        )
        comment_data = {
            "comment_id": comment.id,
            "comment_text": comment.text,
            "classification": comment.classification.type,
            "confidence": comment.classification.confidence,
            "reasoning": comment.classification.reasoning,
            "media_id": comment.media_id,
            "username": comment.username,
            "user_id": comment.user_id,
            "created_at": comment.created_at.isoformat() if comment.created_at else None,
        }

        # 4. Send notification via Telegram
        logger.info(f"Sending Telegram notification | comment_id={comment_id}")
        result = await self.telegram_service.send_notification(comment_data)

        if result.get("success"):
            logger.info(
                f"Telegram notification sent successfully | comment_id={comment_id} | "
                f"classification={classification}"
            )
            return {
                "status": "success",
                "comment_id": comment_id,
                "classification": classification,
                "telegram_result": result,
            }
        else:
            logger.error(
                f"Telegram notification failed | comment_id={comment_id} | "
                f"error={result.get('error', 'Unknown error')}"
            )
            return {
                "status": "error",
                "reason": result.get("error", "Unknown error"),
                "telegram_result": result,
            }
