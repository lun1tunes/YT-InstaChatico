"""
Unit tests for ClassifyCommentUseCase.

Tests cover:
- Happy path: successful classification
- Edge cases: comment not found, media unavailable, waiting for media context
- Classification creation and retrieval
- Error handling and retry logic
- Media context building
- Token tracking and status updates
- Database transaction errors and rollback
- Conversation ID generation for replies
- Field assignment validation
- Debug logging paths
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace
from sqlalchemy.exc import IntegrityError

from core.use_cases.classify_comment import ClassifyCommentUseCase
from core.models.comment_classification import CommentClassification, ProcessingStatus


@pytest.mark.unit
@pytest.mark.use_case
class TestClassifyCommentUseCase:
    """Test ClassifyCommentUseCase methods."""

    async def test_execute_success(
        self, db_session, comment_factory, media_factory, classification_factory
    ):
        """Test successful comment classification."""
        # Arrange
        media = await media_factory(
            media_id="media_1",
            media_type="IMAGE",
            media_url="https://example.com/image.jpg",
            media_context="Product display image",
            caption="New product launch!"
        )
        comment = await comment_factory(
            comment_id="comment_1",
            media_id=media.id,
            text="What is the price?",
        )

        # Mock services
        mock_classification_service = MagicMock()
        mock_classification_result = SimpleNamespace(
            type="question / inquiry",
            confidence=95,
            reasoning="User asking about pricing",
            input_tokens=100,
            output_tokens=50,
            error=None,
        )
        mock_classification_service.classify_comment = AsyncMock(return_value=mock_classification_result)
        mock_classification_service.generate_conversation_id = MagicMock(return_value="conv_123")

        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=media)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        mock_classification_repo = MagicMock()
        mock_classification_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_classification_repo.create = AsyncMock()
        mock_classification_repo.mark_processing = AsyncMock()
        mock_classification_repo.mark_completed = AsyncMock()

        # Create use case
        use_case = ClassifyCommentUseCase(
            session=db_session,
            classification_service=mock_classification_service,
            media_service=mock_media_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            classification_repository_factory=lambda session: mock_classification_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", retry_count=0)

        # Assert
        assert result["status"] == "success"
        assert result["comment_id"] == "comment_1"
        assert result["classification"] == "question / inquiry"
        assert result["confidence"] == 95

        # Verify service calls
        mock_comment_repo.get_with_classification.assert_awaited_once_with("comment_1")
        mock_media_service.get_or_create_media.assert_awaited_once_with("media_1", db_session)
        mock_classification_service.generate_conversation_id.assert_called_once()
        mock_classification_service.classify_comment.assert_awaited_once()
        mock_classification_repo.mark_completed.assert_awaited_once()

    async def test_execute_comment_not_found(self, db_session):
        """Test classification when comment doesn't exist."""
        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=None)

        mock_classification_repo = MagicMock()

        # Create use case
        use_case = ClassifyCommentUseCase(
            session=db_session,
            classification_service=MagicMock(),
            media_service=MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
            classification_repository_factory=lambda session: mock_classification_repo,
        )

        # Act
        result = await use_case.execute(comment_id="nonexistent", retry_count=0)

        # Assert
        assert result["status"] == "error"
        assert result["reason"] == "comment_not_found"
        mock_comment_repo.get_with_classification.assert_awaited_once_with("nonexistent")

    async def test_execute_media_unavailable(self, db_session, comment_factory):
        """Test classification when media cannot be fetched."""
        # Arrange
        comment = await comment_factory(
            comment_id="comment_1",
            media_id="media_missing",
            text="Test comment",
        )

        # Mock services
        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=None)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        # Create use case
        use_case = ClassifyCommentUseCase(
            session=db_session,
            classification_service=MagicMock(),
            media_service=mock_media_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            classification_repository_factory=lambda session: MagicMock(),
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", retry_count=0)

        # Assert
        assert result["status"] == "error"
        assert result["reason"] == "media_unavailable"

    async def test_execute_waiting_for_media_context(
        self, db_session, comment_factory, media_factory
    ):
        """Test classification when media context is not yet available."""
        # Arrange - media with IMAGE type but no context yet
        media = await media_factory(
            media_id="media_1",
            media_type="IMAGE",
            media_url="https://example.com/image.jpg",
            media_context=None,  # Context not yet available
        )
        comment = await comment_factory(
            comment_id="comment_1",
            media_id=media.id,
            text="What's in the image?",
        )

        # Mock services
        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=media)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        # Create use case
        use_case = ClassifyCommentUseCase(
            session=db_session,
            classification_service=MagicMock(),
            media_service=mock_media_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            classification_repository_factory=lambda session: MagicMock(),
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", retry_count=0)

        # Assert
        assert result["status"] == "retry"
        assert result["reason"] == "waiting_for_media_context"

    async def test_execute_with_existing_classification(
        self, db_session, comment_factory, media_factory
    ):
        """Test classification when classification record already exists."""
        # Arrange
        media = await media_factory(media_id="media_1", media_context="Context")
        comment = await comment_factory(comment_id="comment_1", media_id=media.id)

        # Create existing classification
        from core.models.comment_classification import CommentClassification
        existing_classification = CommentClassification(
            comment_id="comment_1",
            processing_status=ProcessingStatus.PENDING,
        )

        # Mock services
        mock_classification_service = MagicMock()
        mock_classification_result = SimpleNamespace(
            type="spam",
            confidence=99,
            reasoning="Spam detected",
            input_tokens=50,
            output_tokens=20,
            error=None,
        )
        mock_classification_service.classify_comment = AsyncMock(return_value=mock_classification_result)
        mock_classification_service.generate_conversation_id = MagicMock(return_value="conv_123")

        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=media)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        mock_classification_repo = MagicMock()
        mock_classification_repo.get_by_comment_id = AsyncMock(return_value=existing_classification)
        mock_classification_repo.mark_processing = AsyncMock()
        mock_classification_repo.mark_completed = AsyncMock()

        # Create use case
        use_case = ClassifyCommentUseCase(
            session=db_session,
            classification_service=mock_classification_service,
            media_service=mock_media_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            classification_repository_factory=lambda session: mock_classification_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", retry_count=0)

        # Assert
        assert result["status"] == "success"
        assert result["classification"] == "spam"
        mock_classification_repo.get_by_comment_id.assert_awaited_once_with("comment_1")
        # Should NOT create new classification
        mock_classification_repo.create.assert_not_called()

    async def test_execute_classification_error(
        self, db_session, comment_factory, media_factory
    ):
        """Test classification when service returns error."""
        # Arrange
        media = await media_factory(media_id="media_1", media_context="Context")
        comment = await comment_factory(comment_id="comment_1", media_id=media.id)

        # Mock services
        mock_classification_service = MagicMock()
        mock_classification_result = SimpleNamespace(
            type=None,
            confidence=0,
            reasoning=None,
            input_tokens=100,
            output_tokens=0,
            error="API timeout",
        )
        mock_classification_service.classify_comment = AsyncMock(return_value=mock_classification_result)
        mock_classification_service.generate_conversation_id = MagicMock(return_value="conv_123")

        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=media)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        mock_classification_repo = MagicMock()
        mock_classification_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_classification_repo.create = AsyncMock()
        mock_classification_repo.mark_processing = AsyncMock()
        mock_classification_repo.mark_failed = AsyncMock()
        mock_classification_repo.mark_retry = AsyncMock()

        # Create use case
        use_case = ClassifyCommentUseCase(
            session=db_session,
            classification_service=mock_classification_service,
            media_service=mock_media_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            classification_repository_factory=lambda session: mock_classification_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", retry_count=0)

        # Assert
        assert result["status"] == "retry"
        mock_classification_repo.mark_retry.assert_awaited_once()
        mock_classification_repo.mark_failed.assert_not_called()

    async def test_execute_with_carousel_media(
        self, db_session, comment_factory, media_factory
    ):
        """Test classification with carousel media type."""
        # Arrange
        media = await media_factory(
            media_id="media_carousel",
            media_type="CAROUSEL_ALBUM",
            media_url="https://example.com/carousel.jpg",
            media_context="Multiple product images",
        )
        comment = await comment_factory(
            comment_id="comment_carousel",
            media_id=media.id,
            text="Love these products!",
        )

        # Mock services
        mock_classification_service = MagicMock()
        mock_classification_result = SimpleNamespace(
            type="positive feedback / appreciation",
            confidence=98,
            reasoning="Positive sentiment",
            input_tokens=150,
            output_tokens=60,
            error=None,
        )
        mock_classification_service.classify_comment = AsyncMock(return_value=mock_classification_result)
        mock_classification_service.generate_conversation_id = MagicMock(return_value="conv_carousel")

        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=media)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        mock_classification_repo = MagicMock()
        mock_classification_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_classification_repo.create = AsyncMock()
        mock_classification_repo.mark_processing = AsyncMock()
        mock_classification_repo.mark_completed = AsyncMock()

        # Create use case
        use_case = ClassifyCommentUseCase(
            session=db_session,
            classification_service=mock_classification_service,
            media_service=mock_media_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            classification_repository_factory=lambda session: mock_classification_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_carousel", retry_count=0)

        # Assert
        assert result["status"] == "success"
        assert result["classification"] == "positive feedback / appreciation"

    async def test_execute_with_video_media_no_wait(
        self, db_session, comment_factory, media_factory
    ):
        """Test classification with video media - should not wait for context."""
        # Arrange
        media = await media_factory(
            media_id="media_video",
            media_type="VIDEO",
            media_url="https://example.com/video.mp4",
            media_context=None,  # No context for video
        )
        comment = await comment_factory(
            comment_id="comment_video",
            media_id=media.id,
            text="Great video!",
        )

        # Mock services
        mock_classification_service = MagicMock()
        mock_classification_result = SimpleNamespace(
            type="positive feedback / appreciation",
            confidence=97,
            reasoning="Positive feedback on video",
            input_tokens=80,
            output_tokens=40,
            error=None,
        )
        mock_classification_service.classify_comment = AsyncMock(return_value=mock_classification_result)
        mock_classification_service.generate_conversation_id = MagicMock(return_value="conv_video")

        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=media)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        mock_classification_repo = MagicMock()
        mock_classification_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_classification_repo.create = AsyncMock()
        mock_classification_repo.mark_processing = AsyncMock()
        mock_classification_repo.mark_completed = AsyncMock()

        # Create use case
        use_case = ClassifyCommentUseCase(
            session=db_session,
            classification_service=mock_classification_service,
            media_service=mock_media_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            classification_repository_factory=lambda session: mock_classification_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_video", retry_count=0)

        # Assert - should NOT wait for video context
        assert result["status"] == "success"
        assert result["classification"] == "positive feedback / appreciation"

    async def test_execute_with_retry_count(
        self, db_session, comment_factory, media_factory
    ):
        """Test classification with retry count tracking."""
        # Arrange
        media = await media_factory(media_id="media_1", media_context="Context")
        comment = await comment_factory(comment_id="comment_1", media_id=media.id)

        # Mock services
        mock_classification_service = MagicMock()
        mock_classification_result = SimpleNamespace(
            type="question / inquiry",
            confidence=90,
            reasoning="Question detected",
            input_tokens=100,
            output_tokens=50,
            error=None,
        )
        mock_classification_service.classify_comment = AsyncMock(return_value=mock_classification_result)
        mock_classification_service.generate_conversation_id = MagicMock(return_value="conv_123")

        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=media)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        captured_retry_count = None

        async def capture_retry_count(classification, retry_count):
            nonlocal captured_retry_count
            captured_retry_count = retry_count

        mock_classification_repo = MagicMock()
        mock_classification_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_classification_repo.create = AsyncMock()
        mock_classification_repo.mark_processing = AsyncMock(side_effect=capture_retry_count)
        mock_classification_repo.mark_completed = AsyncMock()

        # Create use case
        use_case = ClassifyCommentUseCase(
            session=db_session,
            classification_service=mock_classification_service,
            media_service=mock_media_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            classification_repository_factory=lambda session: mock_classification_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", retry_count=2)

        # Assert
        assert result["status"] == "success"
        assert captured_retry_count == 2

    async def test_execute_skips_when_processing_disabled(
        self, db_session, comment_factory, media_factory
    ):
        media = await media_factory(
            media_id="media_disabled",
            media_context="Context",
            is_processing_enabled=False,
        )
        comment = await comment_factory(comment_id="comment_disabled", media_id=media.id)

        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=media)

        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        mock_classification_repo = MagicMock()

        use_case = ClassifyCommentUseCase(
            session=db_session,
            classification_service=MagicMock(),
            media_service=mock_media_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            classification_repository_factory=lambda session: mock_classification_repo,
        )

        result = await use_case.execute(comment_id="comment_disabled", retry_count=0)

        assert result == {"status": "skipped", "reason": "media_processing_disabled"}
        mock_classification_repo.get_by_comment_id.assert_not_called()

    async def test_build_media_context(
        self, db_session, comment_factory, media_factory
    ):
        """Test media context building with all fields."""
        # Arrange
        media = await media_factory(
            media_id="media_full",
            media_type="IMAGE",
            caption="Full media test",
            media_context="Detailed context",
            username="testuser",
            comments_count=42,
            like_count=1337,
            permalink="https://instagram.com/p/test",
            media_url="https://example.com/image.jpg",
            is_comment_enabled=True,
        )
        comment = await comment_factory(comment_id="comment_1", media_id=media.id)

        # Mock services
        mock_classification_service = MagicMock()
        mock_classification_result = SimpleNamespace(
            type="test",
            confidence=50,
            reasoning="test",
            input_tokens=100,
            output_tokens=50,
            error=None,
        )
        mock_classification_service.classify_comment = AsyncMock(return_value=mock_classification_result)
        mock_classification_service.generate_conversation_id = MagicMock(return_value="conv_123")

        # Capture media context passed to classify_comment
        captured_media_context = None

        async def capture_media_context(text, conv_id, media_ctx):
            nonlocal captured_media_context
            captured_media_context = media_ctx
            return mock_classification_result

        mock_classification_service.classify_comment = AsyncMock(side_effect=capture_media_context)

        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=media)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        mock_classification_repo = MagicMock()
        mock_classification_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_classification_repo.create = AsyncMock()
        mock_classification_repo.mark_processing = AsyncMock()
        mock_classification_repo.mark_completed = AsyncMock()

        # Create use case
        use_case = ClassifyCommentUseCase(
            session=db_session,
            classification_service=mock_classification_service,
            media_service=mock_media_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            classification_repository_factory=lambda session: mock_classification_repo,
        )

        # Act
        await use_case.execute(comment_id="comment_1", retry_count=0)

        # Assert - verify all media context fields
        assert captured_media_context is not None
        assert captured_media_context["caption"] == "Full media test"
        assert captured_media_context["media_type"] == "IMAGE"
        assert captured_media_context["media_context"] == "Detailed context"
        assert captured_media_context["username"] == "testuser"
        assert captured_media_context["comments_count"] == 42
        assert captured_media_context["like_count"] == 1337
        assert captured_media_context["permalink"] == "https://instagram.com/p/test"
        assert captured_media_context["media_url"] == "https://example.com/image.jpg"
        assert captured_media_context["is_comment_enabled"] is True

    async def test_should_wait_for_media_context_image_without_context(
        self, db_session, media_factory
    ):
        """Test _should_wait_for_media_context returns True for IMAGE without context."""
        # Arrange
        media = await media_factory(
            media_id="media_1",
            media_type="IMAGE",
            media_url="https://example.com/image.jpg",
            media_context=None,
        )

        use_case = ClassifyCommentUseCase(
            session=db_session,
            classification_service=MagicMock(),
            media_service=MagicMock(),
            comment_repository_factory=lambda session: MagicMock(),
            classification_repository_factory=lambda session: MagicMock(),
        )

        # Act
        should_wait = await use_case._should_wait_for_media_context(media)

        # Assert
        assert should_wait is True

    async def test_should_wait_for_media_context_carousel_without_context(
        self, db_session, media_factory
    ):
        """Test _should_wait_for_media_context returns True for CAROUSEL_ALBUM without context."""
        # Arrange
        media = await media_factory(
            media_id="media_1",
            media_type="CAROUSEL_ALBUM",
            media_url="https://example.com/carousel.jpg",
            media_context=None,
        )

        use_case = ClassifyCommentUseCase(
            session=db_session,
            classification_service=MagicMock(),
            media_service=MagicMock(),
            comment_repository_factory=lambda session: MagicMock(),
            classification_repository_factory=lambda session: MagicMock(),
        )

        # Act
        should_wait = await use_case._should_wait_for_media_context(media)

        # Assert
        assert should_wait is True

    async def test_should_wait_for_media_context_image_with_context(
        self, db_session, media_factory
    ):
        """Test _should_wait_for_media_context returns False for IMAGE with context."""
        # Arrange
        media = await media_factory(
            media_id="media_1",
            media_type="IMAGE",
            media_url="https://example.com/image.jpg",
            media_context="Analysis complete",
        )

        use_case = ClassifyCommentUseCase(
            session=db_session,
            classification_service=MagicMock(),
            media_service=MagicMock(),
            comment_repository_factory=lambda session: MagicMock(),
            classification_repository_factory=lambda session: MagicMock(),
        )

        # Act
        should_wait = await use_case._should_wait_for_media_context(media)

        # Assert
        assert should_wait is False

    async def test_should_wait_for_media_context_video(
        self, db_session, media_factory
    ):
        """Test _should_wait_for_media_context returns False for VIDEO."""
        # Arrange
        media = await media_factory(
            media_id="media_1",
            media_type="VIDEO",
            media_url="https://example.com/video.mp4",
            media_context=None,
        )

        use_case = ClassifyCommentUseCase(
            session=db_session,
            classification_service=MagicMock(),
            media_service=MagicMock(),
            comment_repository_factory=lambda session: MagicMock(),
            classification_repository_factory=lambda session: MagicMock(),
        )

        # Act
        should_wait = await use_case._should_wait_for_media_context(media)

        # Assert
        assert should_wait is False

    async def test_should_wait_for_media_context_image_without_url(
        self, db_session, media_factory
    ):
        """Test _should_wait_for_media_context returns False for IMAGE without URL."""
        # Arrange
        media = await media_factory(
            media_id="media_1",
            media_type="IMAGE",
            media_url=None,
            media_context=None,
        )

        use_case = ClassifyCommentUseCase(
            session=db_session,
            classification_service=MagicMock(),
            media_service=MagicMock(),
            comment_repository_factory=lambda session: MagicMock(),
            classification_repository_factory=lambda session: MagicMock(),
        )

        # Act
        should_wait = await use_case._should_wait_for_media_context(media)

        # Assert
        assert should_wait is False

    async def test_execute_database_exception_during_commit(
        self, db_session, comment_factory, media_factory
    ):
        """Test rollback when database exception occurs during commit."""
        # Arrange
        media = await media_factory(media_id="media_1", media_context="Context")
        comment = await comment_factory(comment_id="comment_1", media_id=media.id)

        # Mock services
        mock_classification_service = MagicMock()
        mock_classification_result = SimpleNamespace(
            type="question / inquiry",
            confidence=95,
            reasoning="Test",
            input_tokens=100,
            output_tokens=50,
            error=None,
        )
        mock_classification_service.classify_comment = AsyncMock(return_value=mock_classification_result)
        mock_classification_service.generate_conversation_id = MagicMock(return_value="conv_123")

        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=media)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        # Create a mock session that raises exception on commit
        mock_session = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock(side_effect=IntegrityError("test", "test", "test"))
        mock_session.rollback = AsyncMock()

        mock_classification_repo = MagicMock()
        mock_classification_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_classification_repo.create = AsyncMock()
        mock_classification_repo.mark_processing = AsyncMock()
        mock_classification_repo.mark_completed = AsyncMock()

        # Create use case with mock session
        use_case = ClassifyCommentUseCase(
            session=mock_session,
            classification_service=mock_classification_service,
            media_service=mock_media_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            classification_repository_factory=lambda session: mock_classification_repo,
        )

        # Act & Assert
        with pytest.raises(IntegrityError) as exc_info:
            await use_case.execute(comment_id="comment_1", retry_count=0)

        # Verify exception has should_reraise attribute set
        assert hasattr(exc_info.value, "should_reraise")
        assert exc_info.value.should_reraise is True

        # Verify rollback was called
        mock_session.rollback.assert_awaited_once()

    async def test_get_or_create_classification_creates_new(
        self, db_session, comment_factory, media_factory
    ):
        """Test _get_or_create_classification creates new record when none exists."""
        # Arrange
        media = await media_factory(media_id="media_1", media_context="Context")
        comment = await comment_factory(comment_id="comment_new", media_id=media.id)

        # Mock services
        mock_classification_service = MagicMock()
        mock_classification_result = SimpleNamespace(
            type="spam",
            confidence=99,
            reasoning="Spam",
            input_tokens=50,
            output_tokens=20,
            error=None,
        )
        mock_classification_service.classify_comment = AsyncMock(return_value=mock_classification_result)
        mock_classification_service.generate_conversation_id = MagicMock(return_value="conv_new")

        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=media)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        created_classification = None

        async def capture_create(clf):
            nonlocal created_classification
            created_classification = clf
            return clf

        mock_classification_repo = MagicMock()
        mock_classification_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_classification_repo.create = AsyncMock(side_effect=capture_create)
        mock_classification_repo.mark_processing = AsyncMock()
        mock_classification_repo.mark_completed = AsyncMock()

        # Create use case
        use_case = ClassifyCommentUseCase(
            session=db_session,
            classification_service=mock_classification_service,
            media_service=mock_media_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            classification_repository_factory=lambda session: mock_classification_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_new", retry_count=0)

        # Assert
        assert result["status"] == "success"
        assert created_classification is not None
        assert created_classification.comment_id == "comment_new"
        mock_classification_repo.create.assert_awaited_once()

    async def test_should_wait_logs_debug_when_waiting(
        self, db_session, media_factory, caplog
    ):
        """Test _should_wait_for_media_context logs debug info when waiting."""
        import logging

        # Arrange
        media = await media_factory(
            media_id="media_debug",
            media_type="IMAGE",
            media_url="https://example.com/image.jpg",
            media_context=None,
        )

        use_case = ClassifyCommentUseCase(
            session=db_session,
            classification_service=MagicMock(),
            media_service=MagicMock(),
            comment_repository_factory=lambda session: MagicMock(),
            classification_repository_factory=lambda session: MagicMock(),
        )

        # Act
        with caplog.at_level(logging.DEBUG, logger="core.use_cases.classify_comment"):
            should_wait = await use_case._should_wait_for_media_context(media)

        # Assert
        assert should_wait is True
        assert any("Media context check" in record.message for record in caplog.records)

    async def test_execute_with_parent_comment_conversation_id(
        self, db_session, comment_factory, media_factory
    ):
        """Test conversation ID generation for reply comments (with parent_id)."""
        # Arrange
        media = await media_factory(media_id="media_1", media_context="Context")
        comment = await comment_factory(
            comment_id="comment_reply",
            media_id=media.id,
            text="This is a reply",
            parent_id="parent_comment_123",
        )

        # Mock services
        mock_classification_service = MagicMock()
        mock_classification_result = SimpleNamespace(
            type="question / inquiry",
            confidence=85,
            reasoning="Follow-up question",
            input_tokens=120,
            output_tokens=60,
            error=None,
        )
        mock_classification_service.classify_comment = AsyncMock(return_value=mock_classification_result)

        captured_comment_id = None
        captured_parent_id = None

        def capture_conversation_id(comment_id, parent_id):
            nonlocal captured_comment_id, captured_parent_id
            captured_comment_id = comment_id
            captured_parent_id = parent_id
            return f"first_question_comment_{parent_id}" if parent_id else f"first_question_comment_{comment_id}"

        mock_classification_service.generate_conversation_id = MagicMock(side_effect=capture_conversation_id)

        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=media)

        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        mock_classification_repo = MagicMock()
        mock_classification_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_classification_repo.create = AsyncMock()
        mock_classification_repo.mark_processing = AsyncMock()
        mock_classification_repo.mark_completed = AsyncMock()

        use_case = ClassifyCommentUseCase(
            session=db_session,
            classification_service=mock_classification_service,
            media_service=mock_media_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            classification_repository_factory=lambda session: mock_classification_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_reply", retry_count=0)

        # Assert
        assert result["status"] == "success"
        assert captured_comment_id == "comment_reply"
        assert captured_parent_id == "parent_comment_123"
        assert comment.conversation_id is not None

    async def test_execute_sets_conversation_id_on_comment(
        self, db_session, comment_factory, media_factory
    ):
        """Test that conversation_id is properly set on comment object."""
        # Arrange
        media = await media_factory(media_id="media_1", media_context="Context")
        comment = await comment_factory(comment_id="comment_1", media_id=media.id)
        original_conv_id = comment.conversation_id

        # Mock services
        mock_classification_service = MagicMock()
        mock_classification_result = SimpleNamespace(
            type="positive feedback",
            confidence=92,
            reasoning="Positive",
            input_tokens=80,
            output_tokens=40,
            error=None,
        )
        mock_classification_service.classify_comment = AsyncMock(return_value=mock_classification_result)
        mock_classification_service.generate_conversation_id = MagicMock(return_value="generated_conv_id_123")

        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=media)

        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        mock_classification_repo = MagicMock()
        mock_classification_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_classification_repo.create = AsyncMock()
        mock_classification_repo.mark_processing = AsyncMock()
        mock_classification_repo.mark_completed = AsyncMock()

        use_case = ClassifyCommentUseCase(
            session=db_session,
            classification_service=mock_classification_service,
            media_service=mock_media_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            classification_repository_factory=lambda session: mock_classification_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", retry_count=0)

        # Assert
        assert result["status"] == "success"
        assert comment.conversation_id == "generated_conv_id_123"
        assert comment.conversation_id != original_conv_id

    async def test_execute_saves_all_classification_fields(
        self, db_session, comment_factory, media_factory
    ):
        """Test that all classification result fields are properly saved."""
        # Arrange
        media = await media_factory(media_id="media_1", media_context="Context")
        comment = await comment_factory(comment_id="comment_1", media_id=media.id)

        classification = CommentClassification(comment_id="comment_1")

        # Mock services
        mock_classification_service = MagicMock()
        mock_classification_result = SimpleNamespace(
            type="urgent issue / complaint",
            confidence=97,
            reasoning="Customer complaint detected",
            input_tokens=150,
            output_tokens=75,
            error=None,
        )
        mock_classification_service.classify_comment = AsyncMock(return_value=mock_classification_result)
        mock_classification_service.generate_conversation_id = MagicMock(return_value="conv_123")

        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=media)

        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        mock_classification_repo = MagicMock()
        mock_classification_repo.get_by_comment_id = AsyncMock(return_value=classification)
        mock_classification_repo.mark_processing = AsyncMock()
        mock_classification_repo.mark_completed = AsyncMock()

        use_case = ClassifyCommentUseCase(
            session=db_session,
            classification_service=mock_classification_service,
            media_service=mock_media_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            classification_repository_factory=lambda session: mock_classification_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", retry_count=0)

        # Assert
        assert result["status"] == "success"
        assert classification.type == "urgent issue / complaint"
        assert classification.confidence == 97
        assert classification.reasoning == "Customer complaint detected"
        assert classification.input_tokens == 150
        assert classification.output_tokens == 75

    async def test_execute_marks_failed_when_error_returned(
        self, db_session, comment_factory, media_factory
    ):
        """Test that classification is marked as failed when service returns error."""
        # Arrange
        media = await media_factory(media_id="media_1", media_context="Context")
        comment = await comment_factory(comment_id="comment_1", media_id=media.id)

        classification = CommentClassification(comment_id="comment_1")

        # Mock services with error
        mock_classification_service = MagicMock()
        mock_classification_result = SimpleNamespace(
            type=None,
            confidence=0,
            reasoning=None,
            input_tokens=100,
            output_tokens=0,
            error="OpenAI API timeout after 30 seconds",
        )
        mock_classification_service.classify_comment = AsyncMock(return_value=mock_classification_result)
        mock_classification_service.generate_conversation_id = MagicMock(return_value="conv_123")

        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=media)

        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        captured_error = None

        async def capture_failed(clf, error):
            nonlocal captured_error
            captured_error = error

        mock_classification_repo = MagicMock()
        mock_classification_repo.get_by_comment_id = AsyncMock(return_value=classification)
        mock_classification_repo.mark_processing = AsyncMock()
        mock_classification_repo.mark_failed = AsyncMock(side_effect=capture_failed)
        mock_classification_repo.mark_retry = AsyncMock()

        use_case = ClassifyCommentUseCase(
            session=db_session,
            classification_service=mock_classification_service,
            media_service=mock_media_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            classification_repository_factory=lambda session: mock_classification_repo,
        )

        # Act
        classification.max_retries = 2
        final_retry_count = classification.max_retries
        result = await use_case.execute(comment_id="comment_1", retry_count=final_retry_count)

        # Assert
        assert result["status"] == "error"
        mock_classification_repo.mark_failed.assert_awaited_once()
        mock_classification_repo.mark_retry.assert_not_called()
        assert captured_error == "OpenAI API timeout after 30 seconds"
        mock_classification_repo.mark_completed.assert_not_called()
