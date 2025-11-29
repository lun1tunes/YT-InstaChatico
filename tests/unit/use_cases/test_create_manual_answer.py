"""Unit tests for CreateManualAnswerUseCase conversation behaviour."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.use_cases.create_manual_answer import CreateManualAnswerUseCase
from core.models.question_answer import QuestionAnswer, AnswerStatus
from core.repositories.comment import CommentRepository
from core.repositories.answer import AnswerRepository


@pytest.mark.unit
@pytest.mark.use_case
class TestCreateManualAnswerUseCase:
    async def test_execute_injects_conversation_for_new_answer(
        self,
        db_session,
        comment_factory,
    ):
        comment = await comment_factory(
            comment_id="comment_manual_1",
            text="Do you ship internationally?",
            username="customer1",
            conversation_id=None,
        )

        instagram_service = MagicMock()
        instagram_service.send_reply_to_comment = AsyncMock(
            return_value={"success": True, "reply_id": "reply123", "response": {"id": "reply123"}}
        )

        session_mock = AsyncMock()
        session_mock.add_items = AsyncMock()

        session_service = MagicMock()
        session_service.get_session.return_value = session_mock

        use_case = CreateManualAnswerUseCase(
            session=db_session,
            comment_repository_factory=lambda session: CommentRepository(session),
            answer_repository_factory=lambda session: AnswerRepository(session),
            instagram_service=instagram_service,
            replace_answer_use_case_factory=lambda session: MagicMock(),
            session_service=session_service,
        )

        result = await use_case.execute(comment_id="comment_manual_1", answer_text="Yes, worldwide shipping is available.")

        assert result.answer == "Yes, worldwide shipping is available."
        session_service.get_session.assert_called_once_with("first_question_comment_comment_manual_1")
        session_mock.add_items.assert_awaited_once()
        exchange = session_mock.add_items.await_args.args[0]
        assert exchange == [
            {"role": "user", "content": "@customer1: Do you ship internationally?"},
            {"role": "assistant", "content": "Yes, worldwide shipping is available."},
        ]

    async def test_execute_existing_answer_uses_replace_and_injects_conversation(
        self,
        db_session,
        comment_factory,
    ):
        comment = await comment_factory(
            comment_id="comment_manual_2",
            text="Can I cancel my order?",
            username="customer2",
            conversation_id=None,
        )

        existing_answer = QuestionAnswer(
            comment_id="comment_manual_2",
            processing_status=AnswerStatus.COMPLETED,
        )
        db_session.add(existing_answer)
        await db_session.commit()

        mock_replace_use_case = MagicMock()
        mock_replace_use_case.execute = AsyncMock(
            return_value=QuestionAnswer(
                comment_id="comment_manual_2",
                answer="Updated answer",
            )
        )

        instagram_service = MagicMock()
        instagram_service.send_reply_to_comment = AsyncMock()

        session_mock = AsyncMock()
        session_mock.add_items = AsyncMock()

        session_service = MagicMock()
        session_service.get_session.return_value = session_mock

        use_case = CreateManualAnswerUseCase(
            session=db_session,
            comment_repository_factory=lambda session: CommentRepository(session),
            answer_repository_factory=lambda session: AnswerRepository(session),
            instagram_service=instagram_service,
            replace_answer_use_case_factory=lambda session: mock_replace_use_case,
            session_service=session_service,
        )

        result = await use_case.execute(comment_id="comment_manual_2", answer_text="You can cancel within 2 hours.")

        assert result is mock_replace_use_case.execute.return_value
        mock_replace_use_case.execute.assert_awaited_once()
        instagram_service.send_reply_to_comment.assert_not_awaited()
        session_service.get_session.assert_called_once_with("first_question_comment_comment_manual_2")
        session_mock.add_items.assert_awaited_once()
        items = session_mock.add_items.await_args.args[0]
        assert items[-1]["content"] == "You can cancel within 2 hours."
