"""
Unit tests for ProcessWebhookCommentUseCase.

Tests cover:
- Happy path: creating new comment with classification
- Edge cases: duplicate comment, race condition, media creation failure
- Re-classification logic
- Exception handling
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.exc import IntegrityError

from core.use_cases.process_webhook_comment import ProcessWebhookCommentUseCase
from core.models.comment_classification import ProcessingStatus


@pytest.mark.unit
@pytest.mark.use_case
class TestProcessWebhookCommentUseCase:
    """Test ProcessWebhookCommentUseCase methods."""

    async def test_execute_new_comment_success(self, db_session, media_factory):
        """Test successfully creating a new comment."""
        # Arrange
        media = await media_factory(media_id="media_1", owner="acct_1")
        from core.config import settings
        original_owner = settings.instagram.base_account_id
        settings.instagram.base_account_id = "acct_1"

        # Mock services
        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=media)

        mock_task_queue = MagicMock()

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=None)

        mock_media_repo = MagicMock()

        # Create use case
        use_case = ProcessWebhookCommentUseCase(
            session=db_session,
            media_service=mock_media_service,
            task_queue=mock_task_queue,
            comment_repository_factory=lambda session: mock_comment_repo,
            media_repository_factory=lambda session: mock_media_repo,
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            media_id="media_1",
            user_id="user_123",
            username="testuser",
            text="Great product!",
            entry_timestamp=1234567890,
            parent_id=None,
            raw_data={"extra": "data"},
        )

        # Assert
        assert result["status"] == "created"
        assert result["comment_id"] == "comment_1"
        assert result["should_classify"] is True
        assert result["reason"] == "New comment created"

        # Verify media service called
        mock_media_service.get_or_create_media.assert_awaited_once_with("media_1", db_session)
        settings.instagram.base_account_id = original_owner

    async def test_execute_existing_comment_needs_classification(
        self, db_session
    ):
        """Test handling existing comment that needs classification."""
        # Arrange - use pure mock without database to avoid lazy loading issues
        from core.models.instagram_comment import InstagramComment

        comment = InstagramComment(
            id="comment_1",
            media_id="media_1",
            user_id="user_123",
            username="testuser",
            text="Existing comment",
        )
        # Comment has no classification
        comment.classification = None

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        # Create use case
        use_case = ProcessWebhookCommentUseCase(
            session=db_session,
            media_service=MagicMock(),
            task_queue=MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
            media_repository_factory=lambda session: MagicMock(),
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            media_id="media_1",
            user_id="user_123",
            username="testuser",
            text="Existing comment",
            entry_timestamp=1234567890,
        )

        # Assert
        assert result["status"] == "exists"
        assert result["comment_id"] == "comment_1"
        assert result["should_classify"] is True

    async def test_execute_existing_comment_classification_completed(
        self, db_session, comment_factory, classification_factory, media_factory
    ):
        """Test handling existing comment with completed classification."""
        # Arrange
        media = await media_factory(media_id="media_1")
        comment = await comment_factory(comment_id="comment_1", media_id=media.id)
        classification = await classification_factory(
            comment_id="comment_1",
            processing_status=ProcessingStatus.COMPLETED,
        )
        comment.classification = classification

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        # Create use case
        use_case = ProcessWebhookCommentUseCase(
            session=db_session,
            media_service=MagicMock(),
            task_queue=MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
            media_repository_factory=lambda session: MagicMock(),
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            media_id="media_1",
            user_id="user_123",
            username="testuser",
            text="Existing comment",
            entry_timestamp=1234567890,
        )

        # Assert
        assert result["status"] == "exists"
        assert result["comment_id"] == "comment_1"
        assert result["should_classify"] is False

    async def test_execute_existing_comment_classification_pending(
        self, db_session, comment_factory, classification_factory
    ):
        """Test handling existing comment with pending classification."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")
        comment.classification = await classification_factory(
            comment_id="comment_1",
            processing_status=ProcessingStatus.PENDING,
        )

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        # Create use case
        use_case = ProcessWebhookCommentUseCase(
            session=db_session,
            media_service=MagicMock(),
            task_queue=MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
            media_repository_factory=lambda session: MagicMock(),
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            media_id="media_1",
            user_id="user_123",
            username="testuser",
            text="Existing comment",
            entry_timestamp=1234567890,
        )

        # Assert
        assert result["status"] == "exists"
        assert result["should_classify"] is True

    async def test_execute_media_creation_failure(self, db_session):
        """Test handling when media creation fails."""
        # Mock services
        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=None)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=None)

        # Create use case
        use_case = ProcessWebhookCommentUseCase(
            session=db_session,
            media_service=mock_media_service,
            task_queue=MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
            media_repository_factory=lambda session: MagicMock(),
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            media_id="media_missing",
            user_id="user_123",
            username="testuser",
            text="Comment text",
            entry_timestamp=1234567890,
        )

        # Assert
        assert result["status"] == "error"
        assert result["comment_id"] == "comment_1"
        assert result["should_classify"] is False
        assert "failed to create media" in result["reason"].lower()

    async def test_execute_account_mismatch_entry_id(self, db_session, media_factory):
        """Webhook entry account mismatch should block processing."""
        media = await media_factory(media_id="media_1")
        from core.config import settings
        original_owner = settings.instagram.base_account_id
        settings.instagram.base_account_id = "expected_owner"

        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=media)
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=None)

        use_case = ProcessWebhookCommentUseCase(
            session=db_session,
            media_service=mock_media_service,
            task_queue=MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
            media_repository_factory=lambda session: MagicMock(),
        )

        result = await use_case.execute(
            comment_id="comment_forbidden",
            media_id="media_1",
            user_id="user_123",
            username="tester",
            text="Should be rejected",
            entry_timestamp=1234567890,
            entry_owner_id="other_owner",
        )

        assert result["status"] == "forbidden"
        assert result["should_classify"] is False
        assert result["reason"] == "Invalid webhook account"
        settings.instagram.base_account_id = original_owner

    async def test_execute_with_parent_comment(self, db_session, media_factory):
        """Test creating comment with parent_id (reply to another comment)."""
        # Arrange
        media = await media_factory(media_id="media_1")

        # Mock services
        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=media)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=None)

        # Create use case
        use_case = ProcessWebhookCommentUseCase(
            session=db_session,
            media_service=mock_media_service,
            task_queue=MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
            media_repository_factory=lambda session: MagicMock(),
        )

        # Act
        result = await use_case.execute(
            comment_id="reply_1",
            media_id="media_1",
            user_id="user_456",
            username="replier",
            text="Replying to parent comment",
            entry_timestamp=1234567890,
            parent_id="parent_comment_123",
        )

        # Assert
        assert result["status"] == "created"
        assert result["should_classify"] is True

    async def test_execute_integrity_error_race_condition(
        self, db_session, media_factory
    ):
        """Test handling IntegrityError (race condition)."""
        # Arrange
        media = await media_factory(media_id="media_1")

        # Mock services
        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=media)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=None)

        # Create use case with mocked session that raises IntegrityError
        from unittest.mock import PropertyMock
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock(side_effect=IntegrityError(None, None, None))
        mock_session.rollback = AsyncMock()

        use_case = ProcessWebhookCommentUseCase(
            session=mock_session,
            media_service=mock_media_service,
            task_queue=MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
            media_repository_factory=lambda session: MagicMock(),
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_race",
            media_id="media_1",
            user_id="user_123",
            username="testuser",
            text="Race condition comment",
            entry_timestamp=1234567890,
        )

        # Assert
        assert result["status"] == "exists"
        assert result["comment_id"] == "comment_race"
        assert result["should_classify"] is False
        assert "race condition" in result["reason"].lower()
        mock_session.rollback.assert_awaited_once()

    async def test_execute_unexpected_exception(self, db_session, media_factory):
        """Test handling unexpected exceptions."""
        # Arrange
        media = await media_factory(media_id="media_1")

        # Mock services
        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=media)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=None)

        # Create use case with mocked session that raises unexpected exception
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock(side_effect=Exception("Database connection lost"))
        mock_session.rollback = AsyncMock()

        use_case = ProcessWebhookCommentUseCase(
            session=mock_session,
            media_service=mock_media_service,
            task_queue=MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
            media_repository_factory=lambda session: MagicMock(),
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_error",
            media_id="media_1",
            user_id="user_123",
            username="testuser",
            text="Error comment",
            entry_timestamp=1234567890,
        )

        # Assert
        assert result["status"] == "error"
        assert result["comment_id"] == "comment_error"
        assert result["should_classify"] is False
        assert "unexpected error" in result["reason"].lower()
        mock_session.rollback.assert_awaited_once()

    async def test_execute_with_raw_data(self, db_session, media_factory):
        """Test creating comment with raw_data."""
        # Arrange
        media = await media_factory(media_id="media_1")

        # Mock services
        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=media)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=None)

        # Create use case
        use_case = ProcessWebhookCommentUseCase(
            session=db_session,
            media_service=mock_media_service,
            task_queue=MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
            media_repository_factory=lambda session: MagicMock(),
        )

        raw_webhook_data = {
            "field": "comments",
            "value": {
                "id": "comment_1",
                "text": "Test comment",
                "from": {"id": "user_123", "username": "testuser"}
            }
        }

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            media_id="media_1",
            user_id="user_123",
            username="testuser",
            text="Test comment",
            entry_timestamp=1234567890,
            raw_data=raw_webhook_data,
        )

        # Assert
        assert result["status"] == "created"
        assert result["should_classify"] is True

    async def test_execute_without_raw_data(self, db_session, media_factory):
        """Test creating comment without raw_data (defaults to empty dict)."""
        # Arrange
        media = await media_factory(media_id="media_1")

        # Mock services
        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=media)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=None)

        # Create use case
        use_case = ProcessWebhookCommentUseCase(
            session=db_session,
            media_service=mock_media_service,
            task_queue=MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
            media_repository_factory=lambda session: MagicMock(),
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            media_id="media_1",
            user_id="user_123",
            username="testuser",
            text="Test comment",
            entry_timestamp=1234567890,
            raw_data=None,  # No raw data
        )

        # Assert
        assert result["status"] == "created"

    async def test_execute_timestamp_conversion(self, db_session, media_factory):
        """Test that entry_timestamp is correctly converted to datetime."""
        # Arrange
        media = await media_factory(media_id="media_1")

        # Mock services
        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=media)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=None)

        # Create use case
        use_case = ProcessWebhookCommentUseCase(
            session=db_session,
            media_service=mock_media_service,
            task_queue=MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
            media_repository_factory=lambda session: MagicMock(),
        )

        # Act
        timestamp = 1705320000  # 2024-01-15 10:00:00 UTC
        result = await use_case.execute(
            comment_id="comment_1",
            media_id="media_1",
            user_id="user_123",
            username="testuser",
            text="Test comment",
            entry_timestamp=timestamp,
        )

        # Assert
        assert result["status"] == "created"

    async def test_execute_media_service_exception(self, db_session):
        """Test handling when media service raises an exception."""
        # Mock services - media service throws exception
        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(
            side_effect=Exception("Instagram API timeout")
        )

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.rollback = AsyncMock()

        # Create use case
        use_case = ProcessWebhookCommentUseCase(
            session=mock_session,
            media_service=mock_media_service,
            task_queue=MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
            media_repository_factory=lambda session: MagicMock(),
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            media_id="media_error",
            user_id="user_123",
            username="testuser",
            text="Comment text",
            entry_timestamp=1234567890,
        )

        # Assert
        assert result["status"] == "error"
        assert result["comment_id"] == "comment_1"
        assert result["should_classify"] is False
        assert "unexpected error" in result["reason"].lower()
        mock_session.rollback.assert_awaited_once()

    async def test_execute_existing_comment_classification_processing(
        self, db_session, comment_factory, classification_factory
    ):
        """Test handling existing comment with classification in PROCESSING status."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")
        comment.classification = await classification_factory(
            comment_id="comment_1",
            processing_status=ProcessingStatus.PROCESSING,
        )

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        # Create use case
        use_case = ProcessWebhookCommentUseCase(
            session=db_session,
            media_service=MagicMock(),
            task_queue=MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
            media_repository_factory=lambda session: MagicMock(),
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            media_id="media_1",
            user_id="user_123",
            username="testuser",
            text="Existing comment",
            entry_timestamp=1234567890,
        )

        # Assert
        assert result["status"] == "exists"
        assert result["should_classify"] is True  # Should retry if processing

    async def test_execute_existing_comment_classification_failed(
        self, db_session, comment_factory, classification_factory
    ):
        """Test handling existing comment with FAILED classification status."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")
        comment.classification = await classification_factory(
            comment_id="comment_1",
            processing_status=ProcessingStatus.FAILED,
        )

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        # Create use case
        use_case = ProcessWebhookCommentUseCase(
            session=db_session,
            media_service=MagicMock(),
            task_queue=MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
            media_repository_factory=lambda session: MagicMock(),
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            media_id="media_1",
            user_id="user_123",
            username="testuser",
            text="Existing comment",
            entry_timestamp=1234567890,
        )

        # Assert
        assert result["status"] == "exists"
        assert result["should_classify"] is True  # Should retry if failed

    async def test_execute_db_commit_generic_exception(self, db_session, media_factory):
        """Test handling when database commit raises a non-IntegrityError exception."""
        # Arrange
        media = await media_factory(media_id="media_1")

        # Mock services
        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=media)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=None)

        # Create use case with mocked session that raises generic exception
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock(
            side_effect=Exception("Database connection lost")
        )
        mock_session.rollback = AsyncMock()

        use_case = ProcessWebhookCommentUseCase(
            session=mock_session,
            media_service=mock_media_service,
            task_queue=MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
            media_repository_factory=lambda session: MagicMock(),
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_db_error",
            media_id="media_1",
            user_id="user_123",
            username="testuser",
            text="DB error comment",
            entry_timestamp=1234567890,
        )

        # Assert
        assert result["status"] == "error"
        assert result["comment_id"] == "comment_db_error"
        assert result["should_classify"] is False
        assert "unexpected error" in result["reason"].lower()
        mock_session.rollback.assert_awaited_once()

    async def test_execute_existing_comment_lazy_load_error(self, db_session, comment_factory, media_factory):
        """Test MissingGreenlet exception when accessing classification relationship."""
        from sqlalchemy.exc import MissingGreenlet
        from core.models.comment_classification import CommentClassification
        
        # Arrange
        media = await media_factory(media_id="media_1", owner="acct_1")
        comment = await comment_factory(comment_id="comment_existing", media_id=media.id)
        
        # Create classification for the comment
        existing_classification = CommentClassification(
            comment_id="comment_existing",
            processing_status=ProcessingStatus.COMPLETED
        )
        
        # Mock services
        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=media)
        
        mock_task_queue = MagicMock()
        
        # Mock comment that raises MissingGreenlet when accessing classification
        mock_existing_comment = MagicMock()
        mock_existing_comment.id = "comment_existing"
        mock_existing_comment.media_id = "media_1"
        
        # When accessing .classification, raise MissingGreenlet
        def raise_missing_greenlet():
            raise MissingGreenlet("greenlet_error")
        
        type(mock_existing_comment).classification = property(lambda self: raise_missing_greenlet())
        
        # Mock the fetched comment with classification loaded
        mock_fetched_comment = MagicMock()
        mock_fetched_comment.classification = existing_classification
        
        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=mock_existing_comment)
        mock_comment_repo.get_with_classification = AsyncMock(return_value=mock_fetched_comment)
        
        mock_media_repo = MagicMock()
        
        # Create use case
        use_case = ProcessWebhookCommentUseCase(
            session=db_session,
            media_service=mock_media_service,
            task_queue=mock_task_queue,
            comment_repository_factory=lambda session: mock_comment_repo,
            media_repository_factory=lambda session: mock_media_repo,
        )
        
        # Act
        result = await use_case.execute(
            comment_id="comment_existing",
            media_id="media_1",
            user_id="user_123",
            username="testuser",
            text="Test comment",
            entry_timestamp=1234567890,
        )
        
        # Assert
        assert result["status"] == "exists"
        assert result["comment_id"] == "comment_existing"
        assert result["should_classify"] is False  # Classification is completed
        # Verify fallback to get_with_classification was called
        mock_comment_repo.get_with_classification.assert_awaited_once_with("comment_existing")
