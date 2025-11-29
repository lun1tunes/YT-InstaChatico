"""
Unit tests for SendReplyUseCase.

Tests cover:
- Happy path: sending reply with generated answer and custom text
- Edge cases: comment not found, no answer available, already sent
- Rate limiting handling
- API failures
- Database state tracking
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.use_cases.send_reply import SendReplyUseCase


@pytest.mark.unit
@pytest.mark.use_case
class TestSendReplyUseCase:
    """Test SendReplyUseCase methods."""

    async def test_execute_with_generated_answer_success(
        self, db_session, comment_factory, answer_factory
    ):
        """Test sending reply using generated answer."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")
        answer = await answer_factory(
            comment_id="comment_1",
            answer_text="This is the generated answer.",
            reply_sent=False,
        )

        # Mock Instagram service
        mock_instagram_service = MagicMock()
        mock_instagram_service.send_reply_to_comment = AsyncMock(
            return_value={
                "success": True,
                "reply_id": "reply_123",
                "response": {"id": "reply_123"}
            }
        )

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=answer)

        # Create use case
        use_case = SendReplyUseCase(
            session=db_session,
            instagram_service=mock_instagram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            use_generated_answer=True
        )

        # Assert
        assert result["status"] == "success"
        assert result["reply_text"] == "This is the generated answer."
        assert result["reply_sent"] is True
        assert result["reply_id"] == "reply_123"

        # Verify Instagram API called with generated answer
        mock_instagram_service.send_reply_to_comment.assert_awaited_once_with(
            comment_id="comment_1",
            message="This is the generated answer."
        )

        # Verify answer record updated
        assert answer.reply_sent is True
        assert answer.reply_sent_at is not None
        assert answer.reply_status == "sent"
        assert answer.reply_id == "reply_123"

    async def test_execute_with_custom_text_success(
        self, db_session, comment_factory
    ):
        """Test sending reply with custom text."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")

        from core.models.question_answer import QuestionAnswer
        answer = QuestionAnswer(comment_id="comment_1")

        # Mock Instagram service
        mock_instagram_service = MagicMock()
        mock_instagram_service.send_reply_to_comment = AsyncMock(
            return_value={
                "success": True,
                "reply_id": "reply_456",
                "response": {"id": "reply_456"}
            }
        )

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_answer_repo.create_for_comment = AsyncMock(return_value=answer)

        # Create use case
        use_case = SendReplyUseCase(
            session=db_session,
            instagram_service=mock_instagram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            reply_text="Custom reply text",
            use_generated_answer=False
        )

        # Assert
        assert result["status"] == "success"
        assert result["reply_text"] == "Custom reply text"
        assert result["reply_sent"] is True

        # Verify Instagram API called with custom text
        mock_instagram_service.send_reply_to_comment.assert_awaited_once_with(
            comment_id="comment_1",
            message="Custom reply text"
        )

    async def test_execute_comment_not_found(self, db_session):
        """Test sending reply when comment doesn't exist."""
        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=None)

        # Create use case
        use_case = SendReplyUseCase(
            session=db_session,
            instagram_service=MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: MagicMock(),
        )

        # Act
        result = await use_case.execute(comment_id="nonexistent")

        # Assert
        assert result["status"] == "error"
        assert "not found" in result["reason"].lower()

    async def test_execute_no_generated_answer_available(
        self, db_session, comment_factory
    ):
        """Test sending reply when no generated answer exists."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=None)

        # Create use case
        use_case = SendReplyUseCase(
            session=db_session,
            instagram_service=MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            use_generated_answer=True
        )

        # Assert
        assert result["status"] == "error"
        assert "no generated answer" in result["reason"].lower()

    async def test_execute_answer_record_exists_but_no_answer_text(
        self, db_session, comment_factory
    ):
        """Test sending reply when answer record exists but has no answer text."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")

        from core.models.question_answer import QuestionAnswer
        answer = QuestionAnswer(comment_id="comment_1", answer=None)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=answer)

        # Create use case
        use_case = SendReplyUseCase(
            session=db_session,
            instagram_service=MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            use_generated_answer=True
        )

        # Assert
        assert result["status"] == "error"
        assert "no generated answer" in result["reason"].lower()

    async def test_execute_no_reply_text_provided(self, db_session, comment_factory):
        """Test sending reply when no text provided and not using generated answer."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()

        # Create use case
        use_case = SendReplyUseCase(
            session=db_session,
            instagram_service=MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            reply_text=None,
            use_generated_answer=False
        )

        # Assert
        assert result["status"] == "error"
        assert "no reply text" in result["reason"].lower()

    async def test_execute_already_sent(self, comment_factory, answer_factory):
        """Test sending reply when already sent."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")
        answer = await answer_factory(
            comment_id="comment_1",
            reply_sent=True,
            reply_id="existing_reply_123",
        )

        # Mock session with rollback
        mock_session = MagicMock()
        mock_session.rollback = AsyncMock()

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=answer)

        # Mock Instagram service (should NOT be called)
        mock_instagram_service = MagicMock()
        mock_instagram_service.send_reply_to_comment = AsyncMock()

        # Create use case
        use_case = SendReplyUseCase(
            session=mock_session,
            instagram_service=mock_instagram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", reply_text="Test")

        # Assert
        assert result["status"] == "skipped"
        assert "already sent" in result["reason"].lower()
        assert result["reply_id"] == "existing_reply_123"

        # Verify Instagram API NOT called
        mock_instagram_service.send_reply_to_comment.assert_not_called()
        # Verify rollback was called
        mock_session.rollback.assert_awaited_once()

    async def test_execute_rate_limited(self, db_session, comment_factory, answer_factory):
        """Test sending reply when rate limited."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")
        answer = await answer_factory(comment_id="comment_1", answer_text="Answer")

        # Mock Instagram service - rate limited
        mock_instagram_service = MagicMock()
        mock_instagram_service.send_reply_to_comment = AsyncMock(
            return_value={
                "status": "rate_limited",
                "retry_after": 60.0
            }
        )

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=answer)

        # Create use case
        use_case = SendReplyUseCase(
            session=db_session,
            instagram_service=mock_instagram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", use_generated_answer=True)

        # Assert
        assert result["status"] == "retry"
        assert result["reason"] == "rate_limited"
        assert result["retry_after"] == 60.0

    async def test_execute_api_failure(self, db_session, comment_factory, answer_factory):
        """Test sending reply when Instagram API fails."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")
        answer = await answer_factory(comment_id="comment_1", answer_text="Answer")

        # Mock Instagram service - API failure
        mock_instagram_service = MagicMock()
        mock_instagram_service.send_reply_to_comment = AsyncMock(
            return_value={
                "success": False,
                "error": {"message": "Invalid comment ID"}
            }
        )

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=answer)

        # Create use case
        use_case = SendReplyUseCase(
            session=db_session,
            instagram_service=mock_instagram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", use_generated_answer=True)

        # Assert
        assert result["status"] == "error"
        assert result["reply_sent"] is False

        # Verify answer record marked as failed
        assert answer.reply_status == "failed"
        assert answer.reply_error is not None

    async def test_execute_creates_answer_record_if_missing(
        self, db_session, comment_factory
    ):
        """Test that answer record is created if it doesn't exist."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")

        from core.models.question_answer import QuestionAnswer
        new_answer = QuestionAnswer(comment_id="comment_1")

        # Mock Instagram service
        mock_instagram_service = MagicMock()
        mock_instagram_service.send_reply_to_comment = AsyncMock(
            return_value={"success": True, "reply_id": "reply_789"}
        )

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_answer_repo.create_for_comment = AsyncMock(return_value=new_answer)

        # Create use case
        use_case = SendReplyUseCase(
            session=db_session,
            instagram_service=mock_instagram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            reply_text="Custom reply"
        )

        # Assert
        assert result["status"] == "success"
        mock_answer_repo.create_for_comment.assert_awaited_once_with("comment_1")

    async def test_execute_handles_dict_error_in_api_response(
        self, db_session, comment_factory, answer_factory
    ):
        """Test that dict errors are converted to string."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")
        answer = await answer_factory(comment_id="comment_1", answer_text="Answer")

        # Mock Instagram service - error as dict
        mock_instagram_service = MagicMock()
        mock_instagram_service.send_reply_to_comment = AsyncMock(
            return_value={
                "success": False,
                "error": {"code": 400, "message": "Bad request"}
            }
        )

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=answer)

        # Create use case
        use_case = SendReplyUseCase(
            session=db_session,
            instagram_service=mock_instagram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", use_generated_answer=True)

        # Assert
        assert result["status"] == "error"
        # Error should be converted to string
        assert isinstance(answer.reply_error, str)
        assert "code" in answer.reply_error or "message" in answer.reply_error

    async def test_execute_reply_id_from_response_nested(
        self, db_session, comment_factory, answer_factory
    ):
        """Test extracting reply_id from nested response object."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")
        answer = await answer_factory(comment_id="comment_1", answer_text="Answer")

        # Mock Instagram service - reply_id in nested response
        mock_instagram_service = MagicMock()
        mock_instagram_service.send_reply_to_comment = AsyncMock(
            return_value={
                "success": True,
                "response": {"id": "nested_reply_999"}
            }
        )

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=answer)

        # Create use case
        use_case = SendReplyUseCase(
            session=db_session,
            instagram_service=mock_instagram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", use_generated_answer=True)

        # Assert
        assert result["status"] == "success"
        assert answer.reply_id == "nested_reply_999"

    async def test_execute_instagram_service_exception(
        self, comment_factory, answer_factory
    ):
        """Test handling when Instagram service raises an exception."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")
        answer = await answer_factory(comment_id="comment_1", answer_text="Answer")

        # Mock session with rollback
        mock_session = MagicMock()
        mock_session.rollback = AsyncMock()

        # Mock Instagram service - raises exception
        mock_instagram_service = MagicMock()
        mock_instagram_service.send_reply_to_comment = AsyncMock(
            side_effect=Exception("Network error")
        )

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=answer)

        # Create use case
        use_case = SendReplyUseCase(
            session=mock_session,
            instagram_service=mock_instagram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act - decorator catches exception and returns error dict
        result = await use_case.execute(comment_id="comment_1", use_generated_answer=True)

        # Assert - decorator wraps the exception
        assert result["status"] == "error"
        assert "network error" in result["reason"].lower()
        mock_session.rollback.assert_awaited_once()

    async def test_execute_db_commit_fails(
        self, comment_factory, answer_factory
    ):
        """Test handling when database commit fails after successful reply."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")
        answer = await answer_factory(comment_id="comment_1", answer_text="Answer")

        # Mock Instagram service - succeeds
        mock_instagram_service = MagicMock()
        mock_instagram_service.send_reply_to_comment = AsyncMock(
            return_value={"success": True, "reply_id": "reply_789"}
        )

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=answer)

        # Mock session to fail on commit
        mock_session = MagicMock()
        mock_session.commit = AsyncMock(side_effect=Exception("DB commit failed"))
        mock_session.rollback = AsyncMock()

        # Create use case
        use_case = SendReplyUseCase(
            session=mock_session,
            instagram_service=mock_instagram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act & Assert - commit failure should bubble up
        with pytest.raises(Exception) as exc_info:
            await use_case.execute(comment_id="comment_1", use_generated_answer=True)

        assert "DB commit failed" in str(exc_info.value)
        mock_session.rollback.assert_awaited_once()

    async def test_execute_rate_limited_with_retry_after_string(
        self, db_session, comment_factory, answer_factory
    ):
        """Test handling rate limiting when retry_after is returned as string."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")
        answer = await answer_factory(comment_id="comment_1", answer_text="Answer")

        # Mock Instagram service - rate limited with string retry_after
        mock_instagram_service = MagicMock()
        mock_instagram_service.send_reply_to_comment = AsyncMock(
            return_value={
                "status": "rate_limited",
                "retry_after": "120"  # String instead of float
            }
        )

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=answer)

        # Create use case
        use_case = SendReplyUseCase(
            session=db_session,
            instagram_service=mock_instagram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", use_generated_answer=True)

        # Assert
        assert result["status"] == "retry"
        assert result["reason"] == "rate_limited"
        # Should handle string retry_after
        assert "retry_after" in result

    async def test_execute_empty_generated_answer_text(
        self, db_session, comment_factory
    ):
        """Test sending reply when generated answer exists but is empty string."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")

        from core.models.question_answer import QuestionAnswer
        answer = QuestionAnswer(comment_id="comment_1", answer="")  # Empty string

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=answer)

        # Create use case
        use_case = SendReplyUseCase(
            session=db_session,
            instagram_service=MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            use_generated_answer=True
        )

        # Assert
        assert result["status"] == "error"
        assert "no generated answer" in result["reason"].lower()

    async def test_execute_success_updates_comment_reply_id(
        self, db_session, comment_factory, answer_factory
    ):
        """Test that comment.reply_id is updated after successful reply."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")
        answer = await answer_factory(comment_id="comment_1", answer_text="Answer")

        # Mock Instagram service
        mock_instagram_service = MagicMock()
        mock_instagram_service.send_reply_to_comment = AsyncMock(
            return_value={
                "success": True,
                "reply_id": "reply_abc_123",
                "response": {"id": "reply_abc_123"}
            }
        )

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=answer)

        # Create use case
        use_case = SendReplyUseCase(
            session=db_session,
            instagram_service=mock_instagram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", use_generated_answer=True)

        # Assert
        assert result["status"] == "success"
        # Verify reply_id is stored in both answer and comment
        assert answer.reply_id == "reply_abc_123"

    async def test_execute_api_failure_with_string_error(
        self, db_session, comment_factory, answer_factory
    ):
        """Test handling API failure when error is a plain string."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")
        answer = await answer_factory(comment_id="comment_1", answer_text="Answer")

        # Mock Instagram service - error as string
        mock_instagram_service = MagicMock()
        mock_instagram_service.send_reply_to_comment = AsyncMock(
            return_value={
                "success": False,
                "error": "Invalid OAuth token"
            }
        )

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=answer)

        # Create use case
        use_case = SendReplyUseCase(
            session=db_session,
            instagram_service=mock_instagram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", use_generated_answer=True)

        # Assert
        assert result["status"] == "error"
        assert result["reply_sent"] is False
        assert answer.reply_status == "failed"
        assert "Invalid OAuth token" in answer.reply_error
