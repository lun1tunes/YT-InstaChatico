"""
Unit tests for SendTelegramNotificationUseCase.

Tests cover:
- Happy path: sending notification for urgent classifications
- Edge cases: comment not found, no classification, non-urgent comments
- Notification data building
- API failures
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.use_cases.send_telegram_notification import SendTelegramNotificationUseCase


@pytest.mark.unit
@pytest.mark.use_case
class TestSendTelegramNotificationUseCase:
    """Test SendTelegramNotificationUseCase methods."""

    async def test_execute_urgent_issue_success(
        self, db_session, comment_factory, classification_factory
    ):
        """Test sending notification for urgent issue."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1", text="Product is broken!")
        comment.classification = await classification_factory(
            comment_id="comment_1",
            classification="urgent issue / complaint",
            confidence=98,
            reasoning="Customer reporting product defect",
        )

        # Mock Telegram service
        mock_telegram_service = MagicMock()
        mock_telegram_service.send_notification = AsyncMock(
            return_value={"success": True, "message_id": "msg_123"}
        )

        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        # Create use case
        use_case = SendTelegramNotificationUseCase(
            session=db_session,
            telegram_service=mock_telegram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1")

        # Assert
        assert result["status"] == "success"
        assert result["comment_id"] == "comment_1"
        assert result["classification"] == "urgent issue / complaint"

        # Verify Telegram service called with correct data
        mock_telegram_service.send_notification.assert_awaited_once()
        call_args = mock_telegram_service.send_notification.call_args[0][0]
        assert call_args["comment_id"] == "comment_1"
        assert call_args["comment_text"] == "Product is broken!"
        assert call_args["classification"] == "urgent issue / complaint"
        assert call_args["confidence"] == 98

    async def test_execute_critical_feedback_success(
        self, db_session, comment_factory, classification_factory
    ):
        """Test sending notification for critical feedback."""
        # Arrange
        comment = await comment_factory(
            comment_id="comment_2",
            text="Terrible service, never ordering again!",
        )
        comment.classification = await classification_factory(
            comment_id="comment_2",
            classification="critical feedback",
            confidence=95,
        )

        # Mock Telegram service
        mock_telegram_service = MagicMock()
        mock_telegram_service.send_notification = AsyncMock(
            return_value={"success": True}
        )

        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        # Create use case
        use_case = SendTelegramNotificationUseCase(
            session=db_session,
            telegram_service=mock_telegram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_2")

        # Assert
        assert result["status"] == "success"
        assert result["classification"] == "critical feedback"

    async def test_execute_partnership_proposal_success(
        self, db_session, comment_factory, classification_factory
    ):
        """Test sending notification for partnership proposal."""
        # Arrange
        comment = await comment_factory(
            comment_id="comment_3",
            text="Interested in collaboration!",
        )
        comment.classification = await classification_factory(
            comment_id="comment_3",
            classification="partnership proposal",
            confidence=92,
        )

        # Mock Telegram service
        mock_telegram_service = MagicMock()
        mock_telegram_service.send_notification = AsyncMock(
            return_value={"success": True}
        )

        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        # Create use case
        use_case = SendTelegramNotificationUseCase(
            session=db_session,
            telegram_service=mock_telegram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_3")

        # Assert
        assert result["status"] == "success"
        assert result["classification"] == "partnership proposal"

    async def test_execute_comment_not_found(self, db_session):
        """Test notification when comment doesn't exist."""
        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=None)

        # Create use case
        use_case = SendTelegramNotificationUseCase(
            session=db_session,
            telegram_service=MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(comment_id="nonexistent")

        # Assert
        assert result["status"] == "error"
        assert "not found" in result["reason"].lower()

    async def test_execute_no_classification(self, db_session, comment_factory):
        """Test notification when comment has no classification."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")
        comment.classification = None

        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        # Create use case
        use_case = SendTelegramNotificationUseCase(
            session=db_session,
            telegram_service=MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1")

        # Assert
        assert result["status"] == "error"
        assert result["reason"] == "no_classification"

    async def test_execute_non_urgent_classification_skipped(
        self, db_session, comment_factory, classification_factory
    ):
        """Test that non-urgent classifications are skipped."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")
        comment.classification = await classification_factory(
            comment_id="comment_1",
            classification="question / inquiry",  # Not urgent
            confidence=90,
        )

        # Mock Telegram service (should NOT be called)
        mock_telegram_service = MagicMock()
        mock_telegram_service.send_notification = AsyncMock()

        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        # Create use case
        use_case = SendTelegramNotificationUseCase(
            session=db_session,
            telegram_service=mock_telegram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1")

        # Assert
        assert result["status"] == "skipped"
        assert result["reason"] == "no_notification_needed"
        assert result["classification"] == "question / inquiry"

        # Verify Telegram service NOT called
        mock_telegram_service.send_notification.assert_not_called()

    async def test_execute_case_insensitive_classification(
        self, db_session, comment_factory, classification_factory
    ):
        """Test that classification matching is case-insensitive."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")
        comment.classification = await classification_factory(
            comment_id="comment_1",
            classification="URGENT ISSUE / COMPLAINT",  # Uppercase
            confidence=99,
        )

        # Mock Telegram service
        mock_telegram_service = MagicMock()
        mock_telegram_service.send_notification = AsyncMock(
            return_value={"success": True}
        )

        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        # Create use case
        use_case = SendTelegramNotificationUseCase(
            session=db_session,
            telegram_service=mock_telegram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1")

        # Assert
        assert result["status"] == "success"
        # Lowercase comparison should work
        mock_telegram_service.send_notification.assert_awaited_once()

    async def test_execute_telegram_api_failure(
        self, db_session, comment_factory, classification_factory
    ):
        """Test handling Telegram API failure."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")
        comment.classification = await classification_factory(
            comment_id="comment_1",
            classification="urgent issue / complaint",
        )

        # Mock Telegram service - API failure
        mock_telegram_service = MagicMock()
        mock_telegram_service.send_notification = AsyncMock(
            return_value={
                "success": False,
                "error": "Telegram bot token invalid"
            }
        )

        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        # Create use case
        use_case = SendTelegramNotificationUseCase(
            session=db_session,
            telegram_service=mock_telegram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1")

        # Assert
        assert result["status"] == "error"
        assert "bot token" in result["reason"].lower()

    async def test_execute_notification_data_complete(
        self, db_session, comment_factory, classification_factory
    ):
        """Test that all comment data is included in notification."""
        # Arrange
        from datetime import datetime, timezone
        comment_time = datetime.now(timezone.utc)

        comment = await comment_factory(
            comment_id="comment_full",
            text="Full comment text",
            username="alice_smith",
            user_id="user_456",
            media_id="media_789",
            created_at=comment_time,
        )
        comment.classification = await classification_factory(
            comment_id="comment_full",
            classification="urgent issue / complaint",
            confidence=97,
            reasoning="Urgent customer complaint detected",
        )

        # Capture notification data
        captured_data = None

        async def capture_notification(data):
            nonlocal captured_data
            captured_data = data
            return {"success": True}

        # Mock Telegram service
        mock_telegram_service = MagicMock()
        mock_telegram_service.send_notification = AsyncMock(side_effect=capture_notification)

        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        # Create use case
        use_case = SendTelegramNotificationUseCase(
            session=db_session,
            telegram_service=mock_telegram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        await use_case.execute(comment_id="comment_full")

        # Assert - verify all fields
        assert captured_data is not None
        assert captured_data["comment_id"] == "comment_full"
        assert captured_data["comment_text"] == "Full comment text"
        assert captured_data["classification"] == "urgent issue / complaint"
        assert captured_data["confidence"] == 97
        assert captured_data["reasoning"] == "Urgent customer complaint detected"
        assert captured_data["media_id"] == "media_789"
        assert captured_data["username"] == "alice_smith"
        assert captured_data["user_id"] == "user_456"
        # SQLite loses timezone info, so just check datetime is present
        assert captured_data["created_at"] is not None
        assert comment_time.strftime("%Y-%m-%d") in captured_data["created_at"]

    async def test_execute_notification_data_with_none_created_at(
        self, db_session, classification_factory
    ):
        """Test notification data when created_at is None (mocked comment)."""
        # Arrange - use mocked comment with None created_at
        from core.models.instagram_comment import InstagramComment

        comment = InstagramComment(
            id="comment_mock",
            media_id="media_1",
            user_id="user_1",
            username="testuser",
            text="Test",
            created_at=None,  # Mock with None
        )
        comment.classification = await classification_factory(
            comment_id="comment_mock",
            classification="urgent issue / complaint",
        )

        # Capture notification data
        captured_data = None

        async def capture_notification(data):
            nonlocal captured_data
            captured_data = data
            return {"success": True}

        # Mock Telegram service
        mock_telegram_service = MagicMock()
        mock_telegram_service.send_notification = AsyncMock(side_effect=capture_notification)

        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        # Create use case
        use_case = SendTelegramNotificationUseCase(
            session=db_session,
            telegram_service=mock_telegram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        await use_case.execute(comment_id="comment_mock")

        # Assert
        assert captured_data["created_at"] is None

    async def test_execute_spam_not_notified(
        self, db_session, comment_factory, classification_factory
    ):
        """Test that spam classification doesn't trigger notification."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")
        comment.classification = await classification_factory(
            comment_id="comment_1",
            classification="spam",
        )

        # Mock Telegram service
        mock_telegram_service = MagicMock()
        mock_telegram_service.send_notification = AsyncMock()

        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        # Create use case
        use_case = SendTelegramNotificationUseCase(
            session=db_session,
            telegram_service=mock_telegram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1")

        # Assert
        assert result["status"] == "skipped"
        mock_telegram_service.send_notification.assert_not_called()

    async def test_execute_positive_feedback_not_notified(
        self, db_session, comment_factory, classification_factory
    ):
        """Test that positive feedback doesn't trigger notification."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")
        comment.classification = await classification_factory(
            comment_id="comment_1",
            classification="positive feedback / appreciation",
        )

        # Mock Telegram service
        mock_telegram_service = MagicMock()
        mock_telegram_service.send_notification = AsyncMock()

        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        # Create use case
        use_case = SendTelegramNotificationUseCase(
            session=db_session,
            telegram_service=mock_telegram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1")

        # Assert
        assert result["status"] == "skipped"
        mock_telegram_service.send_notification.assert_not_called()
