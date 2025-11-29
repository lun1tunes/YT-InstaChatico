"""Use case for replacing an Instagram answer with a manual update."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.question_answer import AnswerStatus, QuestionAnswer
from ..repositories.answer import AnswerRepository
from ..utils.time import now_db_utc

logger = logging.getLogger(__name__)


class ReplaceAnswerError(Exception):
    """Domain-level error raised when the replace-answer flow fails."""


class ReplaceAnswerUseCase:
    """
    Handles manual replacement of an existing Instagram answer.

    Steps:
        1. Delete the previously sent reply on Instagram (if any).
        2. Send the new reply text to Instagram.
        3. Soft-delete the old answer and persist a new QuestionAnswer record.
    """

    def __init__(
        self,
        session: AsyncSession,
        answer_repository_factory: Callable[..., AnswerRepository],
        instagram_service: Any,
    ):
        self.session = session
        self.answer_repo = answer_repository_factory(session=session)
        self.instagram_service = instagram_service

    async def execute(
        self,
        answer_id: int,
        *,
        new_answer_text: str,
        quality_score: Optional[int] = None,
    ) -> QuestionAnswer:
        """Replace an existing answer with a new Instagram reply."""
        logger.info("Starting manual answer replacement | answer_id=%s", answer_id)

        answer = await self.answer_repo.get_for_update(answer_id)
        if not answer:
            logger.warning("Answer not found or already replaced | answer_id=%s", answer_id)
            raise ReplaceAnswerError("Answer not found")

        comment_id = answer.comment_id
        if not comment_id:
            logger.error("Answer missing comment_id | answer_id=%s", answer_id)
            raise ReplaceAnswerError("Answer is not linked to a comment")

        # Step 1: Delete previous reply on Instagram (if any)
        if answer.reply_id:
            delete_result = await self.instagram_service.delete_comment_reply(answer.reply_id)
            if not delete_result.get("success"):
                logger.error(
                    "Failed to delete Instagram reply | answer_id=%s | reply_id=%s | response=%s",
                    answer_id,
                    answer.reply_id,
                    delete_result,
                )
                await self.session.rollback()
                raise ReplaceAnswerError("Failed to delete existing Instagram reply")
            logger.info(
                "Previous Instagram reply deleted | answer_id=%s | reply_id=%s",
                answer_id,
                answer.reply_id,
            )

        # Step 2: Send the new reply
        send_result = await self.instagram_service.send_reply_to_comment(comment_id, new_answer_text)
        if not send_result.get("success"):
            logger.error(
                "Failed to send new Instagram reply | answer_id=%s | comment_id=%s | response=%s",
                answer_id,
                comment_id,
                send_result,
            )
            await self.session.rollback()
            raise ReplaceAnswerError("Failed to send new Instagram reply")

        reply_id = send_result.get("reply_id")
        now = now_db_utc()
        logger.debug(
            "New Instagram reply sent | answer_id=%s | comment_id=%s | reply_id=%s",
            answer_id,
            comment_id,
            reply_id,
        )

        # Step 3: Soft-delete old answer and create the new one
        try:
            answer.is_deleted = True
            answer.reply_sent = False
            answer.reply_status = "deleted"
            answer.reply_error = None

            new_answer = QuestionAnswer(
                comment_id=comment_id,
                processing_status=AnswerStatus.COMPLETED,
                answer=new_answer_text,
                answer_confidence=1.0,  # 100%
                answer_quality_score=100,
                last_error=None,
                retry_count=0,
                max_retries=answer.max_retries,
                reply_sent=True,
                reply_sent_at=now,
                reply_status="sent",
                reply_error=None,
                reply_response=send_result.get("response"),
                reply_id=reply_id,
                is_ai_generated=False,
            )

            self.session.add(new_answer)
            await self.session.flush()
            await self.session.commit()
            await self.session.refresh(new_answer)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to persist manual answer replacement | answer_id=%s", answer_id)
            await self.session.rollback()
            raise

        logger.info(
            "Manual answer replacement completed | answer_id=%s | new_answer_id=%s | comment_id=%s",
            answer_id,
            new_answer.id,
            comment_id,
        )
        return new_answer
