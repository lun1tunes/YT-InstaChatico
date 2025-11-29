"""Send YouTube reply use case."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from core.interfaces.services import IYouTubeService
from core.repositories.comment import CommentRepository
from core.repositories.answer import AnswerRepository
from core.utils.time import now_db_utc

logger = logging.getLogger(__name__)


class SendYouTubeReplyUseCase:
    """
    Use case for sending replies to YouTube comments.
    """

    def __init__(
        self,
        session: AsyncSession,
        youtube_service: IYouTubeService,
        comment_repository_factory: Callable[..., CommentRepository],
        answer_repository_factory: Callable[..., AnswerRepository],
    ):
        self.session = session
        self.youtube_service = youtube_service
        self.comment_repo: CommentRepository = comment_repository_factory(session=session)
        self.answer_repo: AnswerRepository = answer_repository_factory(session=session)

    async def execute(
        self,
        comment_id: str,
        reply_text: str = None,
        use_generated_answer: bool = True,
    ) -> Dict[str, Any]:
        logger.info(
            "Starting YouTube reply send | comment_id=%s | use_generated_answer=%s | has_custom_text=%s",
            comment_id,
            use_generated_answer,
            bool(reply_text),
        )

        comment = await self.comment_repo.get_by_id(comment_id)
        if not comment:
            logger.error("Comment not found | comment_id=%s | operation=send_youtube_reply", comment_id)
            return {"status": "error", "reason": f"Comment {comment_id} not found"}

        if use_generated_answer and not reply_text:
            answer_record = await self.answer_repo.get_by_comment_id(comment_id)
            if not answer_record or not answer_record.answer:
                logger.error("No generated answer available | comment_id=%s", comment_id)
                return {"status": "error", "reason": "No generated answer available"}
            reply_text = answer_record.answer
            logger.info("Using generated answer | comment_id=%s | answer_length=%s", comment_id, len(reply_text))
        elif not reply_text:
            logger.error("No reply text provided | comment_id=%s", comment_id)
            return {"status": "error", "reason": "No reply text provided"}
        else:
            logger.info("Using custom reply text | comment_id=%s | text_length=%s", comment_id, len(reply_text))

        # Ensure answer record exists for tracking
        answer_record = await self.answer_repo.get_by_comment_id(comment_id)
        if not answer_record:
            answer_record = await self.answer_repo.create_for_comment(comment_id)

        try:
            result = await self.youtube_service.reply_to_comment(parent_id=comment_id, text=reply_text)
        except Exception as exc:  # noqa: BLE001
            logger.error("YouTube reply failed | comment_id=%s | error=%s", comment_id, exc, exc_info=True)
            return {"status": "error", "reason": str(exc)}

        reply_id = result.get("id")
        answer_record.reply_sent = True
        answer_record.reply_sent_at = now_db_utc()
        answer_record.reply_status = "sent"
        answer_record.reply_response = result
        answer_record.reply_id = reply_id

        try:
            await self.session.commit()
        except Exception:
            logger.exception("Failed to persist reply metadata | comment_id=%s", comment_id)
            await self.session.rollback()
            raise

        logger.info("YouTube reply sent | comment_id=%s | reply_id=%s", comment_id, reply_id)
        return {
            "status": "success",
            "reply_text": reply_text,
            "reply_sent": True,
            "reply_id": reply_id,
            "api_response": result,
        }
