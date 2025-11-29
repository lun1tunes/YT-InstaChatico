"""
Unit tests for HideCommentUseCase.

Tests cover:
- Happy path: successful hiding and unhiding
- Edge cases: comment not found, already hidden/visible
- API failures
- Database state management
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from core.use_cases.hide_comment import HideCommentUseCase


@pytest.mark.unit
@pytest.mark.use_case
class TestHideCommentUseCase:
    """Test HideCommentUseCase methods."""

    async def test_execute_hide_success(self, db_session, comment_factory):
        """Test successfully hiding a visible comment."""
        # Arrange
        comment = await comment_factory(
            comment_id="comment_1",
            text="Inappropriate comment",
            is_hidden=False,
            hidden_at=None,
        )

        # Mock Instagram service
        mock_instagram_service = MagicMock()
        mock_instagram_service.hide_comment = AsyncMock(
            return_value={"success": True, "is_hidden": True}
        )

        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        # Create use case
        use_case = HideCommentUseCase(
            session=db_session,
            instagram_service=mock_instagram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", hide=True)

        # Assert
        assert result["status"] == "success"
        assert result["action"] == "hidden"
        assert result["is_hidden"] is True
        assert result["hidden_at"] is not None

        # Verify Instagram API called
        mock_instagram_service.hide_comment.assert_awaited_once_with("comment_1", hide=True)

        # Verify database updated
        assert comment.is_hidden is True
        assert comment.hidden_at is not None

    async def test_execute_unhide_success(self, db_session, comment_factory):
        """Test successfully unhiding a hidden comment."""
        # Arrange
        comment = await comment_factory(
            comment_id="comment_1",
            text="Comment to unhide",
            is_hidden=True,
            hidden_at=datetime.now(timezone.utc),
        )

        # Mock Instagram service
        mock_instagram_service = MagicMock()
        mock_instagram_service.hide_comment = AsyncMock(
            return_value={"success": True, "is_hidden": False}
        )

        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        # Create use case
        use_case = HideCommentUseCase(
            session=db_session,
            instagram_service=mock_instagram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", hide=False)

        # Assert
        assert result["status"] == "success"
        assert result["action"] == "unhidden"
        assert result["is_hidden"] is False
        assert result["hidden_at"] is None

        # Verify Instagram API called
        mock_instagram_service.hide_comment.assert_awaited_once_with("comment_1", hide=False)

        # Verify database updated
        assert comment.is_hidden is False
        assert comment.hidden_at is None

    async def test_execute_comment_not_found(self, db_session):
        """Test hiding when comment doesn't exist."""
        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=None)

        # Create use case
        use_case = HideCommentUseCase(
            session=db_session,
            instagram_service=MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(comment_id="nonexistent", hide=True)

        # Assert
        assert result["status"] == "error"
        assert "not found" in result["reason"].lower()

    async def test_execute_already_hidden(self, db_session, comment_factory):
        """Test hiding a comment that is already hidden."""
        # Arrange
        comment = await comment_factory(
            comment_id="comment_1",
            is_hidden=True,
            hidden_at=datetime.now(timezone.utc),
        )

        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        # Mock Instagram service (should NOT be called)
        mock_instagram_service = MagicMock()
        mock_instagram_service.hide_comment = AsyncMock()

        # Create use case
        use_case = HideCommentUseCase(
            session=db_session,
            instagram_service=mock_instagram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", hide=True)

        # Assert
        assert result["status"] == "skipped"
        assert "already hidden" in result["reason"].lower()
        assert result["is_hidden"] is True

        # Verify Instagram API NOT called (optimization)
        mock_instagram_service.hide_comment.assert_not_called()

    async def test_execute_already_visible(self, db_session, comment_factory):
        """Test unhiding a comment that is already visible."""
        # Arrange
        comment = await comment_factory(
            comment_id="comment_1",
            is_hidden=False,
            hidden_at=None,
        )

        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        # Mock Instagram service (should NOT be called)
        mock_instagram_service = MagicMock()
        mock_instagram_service.hide_comment = AsyncMock()

        # Create use case
        use_case = HideCommentUseCase(
            session=db_session,
            instagram_service=mock_instagram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", hide=False)

        # Assert
        assert result["status"] == "skipped"
        assert "already visible" in result["reason"].lower()
        assert result["is_hidden"] is False

        # Verify Instagram API NOT called
        mock_instagram_service.hide_comment.assert_not_called()

    async def test_execute_api_failure(self, db_session, comment_factory):
        """Test hiding when Instagram API fails."""
        # Arrange
        comment = await comment_factory(
            comment_id="comment_1",
            is_hidden=False,
        )

        # Mock Instagram service - API failure
        mock_instagram_service = MagicMock()
        mock_instagram_service.hide_comment = AsyncMock(
            return_value={
                "success": False,
                "error": "Instagram API rate limit exceeded"
            }
        )

        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        # Create use case
        use_case = HideCommentUseCase(
            session=db_session,
            instagram_service=mock_instagram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", hide=True)

        # Assert
        assert result["status"] == "error"
        assert "rate limit" in result["reason"].lower()
        assert "api_response" in result

        # Verify database NOT updated
        assert comment.is_hidden is False
        assert comment.hidden_at is None

    async def test_execute_api_failure_without_error_message(self, db_session, comment_factory):
        """Test hiding when API fails without specific error message."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1", is_hidden=False)

        # Mock Instagram service - API failure without error
        mock_instagram_service = MagicMock()
        mock_instagram_service.hide_comment = AsyncMock(
            return_value={"success": False}
        )

        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        # Create use case
        use_case = HideCommentUseCase(
            session=db_session,
            instagram_service=mock_instagram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", hide=True)

        # Assert
        assert result["status"] == "error"
        assert "failed to hide comment" in result["reason"].lower()

    async def test_execute_api_transient_error_returns_retry(self, db_session, comment_factory):
        """Transient Instagram errors should signal retry instead of failure."""
        comment = await comment_factory(comment_id="comment_1", is_hidden=False)

        mock_instagram_service = MagicMock()
        mock_instagram_service.hide_comment = AsyncMock(
            return_value={
                "success": False,
                "error": {
                    "error": {
                        "message": "Try again later",
                        "is_transient": True,
                        "code": 2,
                        "retry_after": "3.5",
                    }
                },
            }
        )

        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        use_case = HideCommentUseCase(
            session=db_session,
            instagram_service=mock_instagram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        result = await use_case.execute(comment_id="comment_1", hide=True)

        assert result["status"] == "retry"
        assert "try again later" in result["reason"].lower()
        assert pytest.approx(result.get("retry_after"), 0.01) == 3.5
        assert comment.is_hidden is False

    async def test_execute_api_error_code_retry(self, db_session, comment_factory):
        """Certain error codes (e.g., 2) should also trigger retry."""
        comment = await comment_factory(comment_id="comment_1", is_hidden=False)

        mock_instagram_service = MagicMock()
        mock_instagram_service.hide_comment = AsyncMock(
            return_value={
                "success": False,
                "error": {"message": "Generic error", "code": 2},
            }
        )

        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        use_case = HideCommentUseCase(
            session=db_session,
            instagram_service=mock_instagram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        result = await use_case.execute(comment_id="comment_1", hide=True)

        assert result["status"] == "retry"
        assert "generic error" in result["reason"].lower()
        assert comment.is_hidden is False

    async def test_execute_hide_default_parameter(self, db_session, comment_factory):
        """Test that hide parameter defaults to True."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1", is_hidden=False)

        # Mock Instagram service
        mock_instagram_service = MagicMock()
        mock_instagram_service.hide_comment = AsyncMock(
            return_value={"success": True}
        )

        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        # Create use case
        use_case = HideCommentUseCase(
            session=db_session,
            instagram_service=mock_instagram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act - don't specify hide parameter
        result = await use_case.execute(comment_id="comment_1")

        # Assert
        mock_instagram_service.hide_comment.assert_awaited_once_with("comment_1", hide=True)
        assert comment.is_hidden is True

    async def test_execute_returns_api_response(self, db_session, comment_factory):
        """Test that API response is included in success result."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1", is_hidden=False)

        # Mock Instagram service
        api_response = {
            "success": True,
            "is_hidden": True,
            "api_version": "v1.0",
            "timestamp": "2024-01-15T10:00:00Z"
        }
        mock_instagram_service = MagicMock()
        mock_instagram_service.hide_comment = AsyncMock(return_value=api_response)

        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        # Create use case
        use_case = HideCommentUseCase(
            session=db_session,
            instagram_service=mock_instagram_service,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", hide=True)

        # Assert
        assert result["status"] == "success"
        assert result["api_response"] == api_response
        assert result["api_response"]["api_version"] == "v1.0"
