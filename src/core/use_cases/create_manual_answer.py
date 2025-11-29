"""Use case for creating or replacing manual Instagram answers."""

from __future__ import annotations

import logging
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.question_answer import QuestionAnswer, AnswerStatus
from ..repositories.answer import AnswerRepository
from ..repositories.comment import CommentRepository
from ..utils.time import now_db_utc
from ..interfaces.agents import IAgentSessionService
from ..services.base_service import BaseService
from .replace_answer import ReplaceAnswerUseCase, ReplaceAnswerError

logger = logging.getLogger(__name__)


class ManualAnswerCreateError(Exception):
    """Raised when manual answer creation cannot be completed."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.status_code = status_code


class CreateManualAnswerUseCase:
    """Creates a new manual answer for a comment, replacing existing reply if necessary."""

    def __init__(
        self,
        session: AsyncSession,
        comment_repository_factory: Callable[..., CommentRepository],
        answer_repository_factory: Callable[..., AnswerRepository],
        instagram_service: Any,
        replace_answer_use_case_factory: Callable[..., ReplaceAnswerUseCase],
        session_service: IAgentSessionService,
    ) -> None:
        self.session = session
        self.comment_repo = comment_repository_factory(session=session)
        self.answer_repo = answer_repository_factory(session=session)
        self.instagram_service = instagram_service
        self._replace_use_case_factory = replace_answer_use_case_factory
        self._answer_repository_factory = answer_repository_factory
        self.session_service = session_service

    async def execute(self, comment_id: str, *, answer_text: str) -> QuestionAnswer:
        logger.info("Manual answer create request | comment_id=%s", comment_id)

        comment = await self.comment_repo.get_by_id(comment_id)
        if not comment:
            logger.warning("Comment not found for manual answer | comment_id=%s", comment_id)
            raise ManualAnswerCreateError("Comment not found", status_code=404)

        conversation_id = self._resolve_conversation_id(comment)
        if conversation_id and not getattr(comment, "conversation_id", None):
            comment.conversation_id = conversation_id

        existing_answer = await self.answer_repo.get_by_comment_id(comment_id)
        if existing_answer:
            logger.info(
                "Existing answer found; delegating to replace use case | comment_id=%s | answer_id=%s",
                comment_id,
                existing_answer.id,
            )
            replace_use_case = self._replace_use_case_factory(session=self.session)
            try:
                new_answer = await replace_use_case.execute(
                    answer_id=existing_answer.id,
                    new_answer_text=answer_text,
                    quality_score=100,
                )
            except ReplaceAnswerError as exc:
                raise ManualAnswerCreateError(str(exc), status_code=502) from exc

            await self._inject_into_conversation(conversation_id, comment, answer_text)
            return new_answer

        # No answer yet: send new reply and create record.
        send_result = await self.instagram_service.send_reply_to_comment(comment_id, answer_text)
        if not send_result.get("success"):
            logger.error(
                "Failed to send manual answer reply | comment_id=%s | response=%s",
                comment_id,
                send_result,
            )
            raise ManualAnswerCreateError("Failed to send Instagram reply", status_code=502)

        reply_id = send_result.get("reply_id")
        now = now_db_utc()

        new_answer = QuestionAnswer(
            comment_id=comment_id,
            processing_status=AnswerStatus.COMPLETED,
            answer=answer_text,
            answer_confidence=1.0,
            answer_quality_score=100,
            retry_count=0,
            max_retries=5,
            reply_sent=True,
            reply_sent_at=now,
            reply_status="sent",
            reply_error=None,
            reply_response=send_result.get("response"),
            reply_id=reply_id,
            is_ai_generated=False,
        )

        try:
            self.session.add(new_answer)
            if not getattr(comment, "conversation_id", None):
                comment.conversation_id = conversation_id
            await self.session.flush()
            await self.session.commit()
            await self.session.refresh(new_answer)
        except Exception:
            logger.exception(
                "Failed to persist manual answer creation | comment_id=%s",
                comment_id,
            )
            await self.session.rollback()
            raise

        logger.info(
            "Manual answer created | comment_id=%s | answer_id=%s",
            comment_id,
            new_answer.id,
        )
        await self._inject_into_conversation(conversation_id, comment, answer_text)
        return new_answer

    def _resolve_conversation_id(self, comment) -> str:
        if getattr(comment, "conversation_id", None):
            return comment.conversation_id
        root_id = comment.parent_id or comment.id
        return f"first_question_comment_{root_id}"

    async def _inject_into_conversation(self, conversation_id: str, comment, answer_text: str) -> None:
        if not conversation_id or not answer_text:
            return

        try:
            session = self.session_service.get_session(conversation_id)
            username = getattr(comment, "username", None)
            user_text = getattr(comment, "text", "") or ""
            if username:
                user_message = f"@{username}: {user_text}"
            else:
                user_message = user_text
            user_message = BaseService._sanitize_input(user_message) if user_message else None

            items = []
            if user_message:
                items.append({"role": "user", "content": user_message})
            items.append({"role": "assistant", "content": answer_text})
            await session.add_items(items)
            logger.debug(
                "Manual answer appended to conversation | conversation_id=%s | user_included=%s",
                conversation_id,
                bool(user_message),
            )
        except Exception as exc:
            logger.warning(
                "Failed to append manual answer to conversation | conversation_id=%s | error=%s",
                conversation_id,
                exc,
            )
