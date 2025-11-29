"""Send reply use case - handles Instagram reply business logic."""

import logging
from typing import Any, Callable, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from ..interfaces.services import IInstagramService
from ..utils.decorators import handle_task_errors
from ..utils.time import now_db_utc
from ..interfaces.repositories import ICommentRepository, IAnswerRepository

logger = logging.getLogger(__name__)


class SendReplyUseCase:
    """
    Use case for sending replies to Instagram comments.

    Follows Dependency Inversion Principle - depends on IInstagramService protocol.
    """

    def __init__(
        self,
        session: AsyncSession,
        instagram_service: IInstagramService,
        comment_repository_factory: Callable[..., ICommentRepository],
        answer_repository_factory: Callable[..., IAnswerRepository],
    ):
        """
        Initialize use case with dependencies.

        Args:
            session: Database session
            instagram_service: Service implementing IInstagramService protocol
            comment_repository_factory: Factory producing CommentRepository instances
            answer_repository_factory: Factory producing AnswerRepository instances
        """
        self.session = session
        self.comment_repo: ICommentRepository = comment_repository_factory(session=session)
        self.answer_repo: IAnswerRepository = answer_repository_factory(session=session)
        self.instagram_service = instagram_service

    @handle_task_errors()
    async def execute(
        self,
        comment_id: str,
        reply_text: str = None,
        use_generated_answer: bool = True
    ) -> Dict[str, Any]:
        """Execute send reply use case."""
        logger.info(
            f"Starting reply send | comment_id={comment_id} | "
            f"use_generated_answer={use_generated_answer} | has_custom_text={bool(reply_text)}"
        )

        # 1. Get comment
        comment = await self.comment_repo.get_by_id(comment_id)
        if not comment:
            logger.error(f"Comment not found | comment_id={comment_id} | operation=send_reply")
            return {"status": "error", "reason": f"Comment {comment_id} not found"}

        # 2. Determine reply text
        if use_generated_answer and not reply_text:
            answer_record = await self.answer_repo.get_by_comment_id(comment_id)
            if not answer_record or not answer_record.answer:
                logger.error(f"No generated answer available | comment_id={comment_id}")
                return {"status": "error", "reason": "No generated answer available"}
            reply_text = answer_record.answer
            logger.info(f"Using generated answer | comment_id={comment_id} | answer_length={len(reply_text)}")
        elif not reply_text:
            logger.error(f"No reply text provided | comment_id={comment_id}")
            return {"status": "error", "reason": "No reply text provided"}
        else:
            logger.info(f"Using custom reply text | comment_id={comment_id} | text_length={len(reply_text)}")

        try:
            # 3. Get answer record for tracking
            answer_record = await self.answer_repo.get_by_comment_id(comment_id)
            if not answer_record:
                answer_record = await self.answer_repo.create_for_comment(comment_id)

            # 4. Check if already sent
            if answer_record.reply_sent:
                logger.info(
                    f"Reply already sent | comment_id={comment_id} | reply_id={answer_record.reply_id} | "
                    f"sent_at={answer_record.reply_sent_at.isoformat() if answer_record.reply_sent_at else None}"
                )
                await self.session.rollback()
                return {
                    "status": "skipped",
                    "reason": "Reply already sent",
                    "reply_id": answer_record.reply_id,
                    "reply_sent_at": answer_record.reply_sent_at.isoformat() if answer_record.reply_sent_at else None,
                }

            # 5. Send reply via Instagram API
            logger.info(f"Sending reply to Instagram | comment_id={comment_id} | reply_length={len(reply_text)}")
            result = await self.instagram_service.send_reply_to_comment(
                comment_id=comment_id,
                message=reply_text
            )

            if result.get("status") == "rate_limited":
                retry_after = float(result.get("retry_after", 10.0))
                logger.warning(
                    f"Reply deferred due to Instagram rate limit | comment_id={comment_id} | retry_after={retry_after:.2f}s"
                )
                await self.session.rollback()
                return {
                    "status": "retry",
                    "reason": "rate_limited",
                    "retry_after": retry_after,
                }

            # 6. Update tracking
            if result.get("success"):
                logger.info(
                    f"Reply sent successfully | comment_id={comment_id} | "
                    f"reply_id={result.get('reply_id') or result.get('response', {}).get('id')}"
                )
                answer_record.reply_sent = True
                answer_record.reply_sent_at = now_db_utc()
                answer_record.reply_status = "sent"
                answer_record.reply_response = result.get("response", {})
                answer_record.reply_id = result.get("reply_id") or result.get("response", {}).get("id")
            else:
                logger.error(
                    f"Reply send failed | comment_id={comment_id} | "
                    f"error={result.get('error', 'Unknown error')}"
                )
                answer_record.reply_status = "failed"
                # Convert error to string if it's a dict
                error = result.get("error", "Unknown error")
                answer_record.reply_error = str(error) if isinstance(error, dict) else error
                answer_record.reply_response = result

            try:
                await self.session.commit()
            except Exception as commit_exc:
                setattr(commit_exc, "should_reraise", True)
                raise
        except Exception:
            await self.session.rollback()
            raise

        return {
            "status": "success" if result.get("success") else "error",
            "reply_text": reply_text,
            "reply_sent": answer_record.reply_sent,
            "reply_id": answer_record.reply_id,
            "api_response": result,
        }
