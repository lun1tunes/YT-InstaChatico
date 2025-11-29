"""Unit tests for DeleteCommentUseCase."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.repositories.comment import CommentRepository
from core.models import InstagramComment
from core.use_cases.delete_comment import DeleteCommentUseCase


@pytest.mark.unit
@pytest.mark.use_case
class TestDeleteCommentUseCase:
    """Test DeleteCommentUseCase behaviour."""

    async def test_execute_success(self, db_session, comment_factory):
        """Deleting a comment should mark it and descendants as deleted when API succeeds."""
        parent = await comment_factory(comment_id="delete_parent")
        await comment_factory(comment_id="delete_child", parent_id=parent.id)

        mock_service = MagicMock()
        mock_service.delete_comment = AsyncMock(return_value={"success": True})

        use_case = DeleteCommentUseCase(
            session=db_session,
            instagram_service=mock_service,
            comment_repository_factory=lambda session: CommentRepository(session),
        )

        result = await use_case.execute("delete_parent")

        assert result["status"] == "success"
        assert result["deleted_count"] >= 2
        mock_service.delete_comment.assert_awaited_once_with("delete_parent")

        parent_row = await db_session.get(InstagramComment, "delete_parent")
        child_row = await db_session.get(InstagramComment, "delete_child")
        assert parent_row.is_deleted is True
        assert child_row.is_deleted is True

    async def test_execute_not_found(self, db_session):
        """Attempting to delete a missing comment returns error status."""
        mock_service = MagicMock()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        use_case = DeleteCommentUseCase(
            session=db_session,
            instagram_service=mock_service,
            comment_repository_factory=lambda session: mock_repo,
        )

        result = await use_case.execute("missing")

        assert result["status"] == "error"
        assert "not found" in result["reason"].lower()
        mock_service.delete_comment.assert_not_called()

    async def test_execute_api_failure(self, db_session, comment_factory):
        """API failure should surface error without marking records deleted."""
        comment = await comment_factory(comment_id="api_fail")

        mock_service = MagicMock()
        mock_service.delete_comment = AsyncMock(return_value={"success": False, "error": {"code": 2}})

        use_case = DeleteCommentUseCase(
            session=db_session,
            instagram_service=mock_service,
            comment_repository_factory=lambda session: CommentRepository(session),
        )

        result = await use_case.execute("api_fail")

        assert result["status"] == "error"
        assert "Failed" in str(result["reason"])
        mock_service.delete_comment.assert_awaited_once_with("api_fail")

        db_comment = await db_session.get(InstagramComment, comment.id)
        assert db_comment.is_deleted is False
