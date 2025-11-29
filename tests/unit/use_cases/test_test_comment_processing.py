"""
Unit tests for TestCommentProcessingUseCase.

Tests cover:
- Media creation and retrieval
- Comment creation and updating
- Classification execution
- Answer generation for questions
- Error handling at each step
- Container lazy loading
- Full pipeline integration
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from core.use_cases.test_comment_processing import TestCommentProcessingUseCase
from core.models.media import Media
from core.models.instagram_comment import InstagramComment
from core.models.comment_classification import CommentClassification, ProcessingStatus


@pytest.mark.unit
@pytest.mark.use_case
class TestTestCommentProcessingUseCase:
    """Test TestCommentProcessingUseCase methods."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session for testing."""
        session = MagicMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        session.rollback = AsyncMock()
        session.flush = AsyncMock()
        return session

    async def test_execute_full_pipeline_success_non_question(
        self, mock_session, media_factory, comment_factory, classification_factory
    ):
        """Test successful full pipeline for non-question comment."""
        # Arrange
        media = await media_factory(media_id="media_1")
        comment = await comment_factory(comment_id="comment_1", media_id="media_1")
        classification = await classification_factory(
            comment_id="comment_1",
            classification_type="positive feedback",
            reasoning="User expressed satisfaction",
        )
        comment.classification = classification

        # Mock session
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_session.rollback = AsyncMock()

        # Mock repositories
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=media)

        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        # Mock classification use case
        mock_classify_use_case = MagicMock()
        mock_classify_use_case.execute = AsyncMock(
            return_value={
                "status": "success",
                "classification": "positive feedback",
            }
        )

        # Create use case
        use_case = TestCommentProcessingUseCase(
            session=mock_session,
            classify_use_case=mock_classify_use_case,
            answer_use_case=None,
            media_repository_factory=lambda session: mock_media_repo,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            media_id="media_1",
            user_id="user_1",
            username="testuser",
            text="Great post!",
        )

        # Assert
        assert result["status"] == "success"
        assert result["comment_id"] == "comment_1"
        assert result["classification"] == "positive feedback"
        assert result["classification_reasoning"] == "User expressed satisfaction"
        assert result["answer"] is None  # No answer for non-question

    async def test_execute_full_pipeline_question_with_answer(
        self, mock_session, media_factory, comment_factory, classification_factory
    ):
        """Test full pipeline for question with answer generation."""
        # Arrange
        media = await media_factory(media_id="media_1")
        comment = await comment_factory(comment_id="comment_1", media_id="media_1")
        classification = await classification_factory(
            comment_id="comment_1",
            classification_type="question / inquiry",
            reasoning="User asked about product",
        )
        comment.classification = classification

        # Mock repositories
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=media)

        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        # Mock classification use case
        mock_classify_use_case = MagicMock()
        mock_classify_use_case.execute = AsyncMock(
            return_value={
                "status": "success",
                "classification": "question / inquiry",
            }
        )

        # Mock answer use case
        mock_answer_use_case = MagicMock()
        mock_answer_use_case.execute = AsyncMock(
            return_value={
                "status": "success",
                "answer": "The product is available in stock.",
                "confidence": 0.95,
            }
        )

        # Create use case
        use_case = TestCommentProcessingUseCase(
            session=mock_session,
            classify_use_case=mock_classify_use_case,
            answer_use_case=mock_answer_use_case,
            media_repository_factory=lambda session: mock_media_repo,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            media_id="media_1",
            user_id="user_1",
            username="testuser",
            text="Is this available?",
        )

        # Assert
        assert result["status"] == "success"
        assert result["classification"] == "question / inquiry"
        assert result["answer"] == "The product is available in stock."
        assert "answer_result" in result["processing_details"]

    async def test_execute_media_creation_failure(self, db_session):
        """Test handling when media creation fails."""
        # Mock repository that returns None for media
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=None)

        mock_comment_repo = MagicMock()

        # Mock session that fails on add/commit
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock(side_effect=Exception("DB error"))
        mock_session.rollback = AsyncMock()

        # Create use case
        use_case = TestCommentProcessingUseCase(
            session=mock_session,
            media_repository_factory=lambda session: mock_media_repo,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            media_id="media_1",
            user_id="user_1",
            username="testuser",
            text="Test",
        )

        # Assert
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]

    async def test_execute_classification_error(self, mock_session):
        """Test handling when classification fails."""
        # Create mock objects (not real ORM objects to avoid lazy loading issues)
        mock_media = MagicMock()
        mock_media.id = "media_1"

        mock_comment = MagicMock()
        mock_comment.id = "comment_1"
        mock_comment.classification = None  # No classification yet

        # Mock repositories
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=mock_media)

        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=mock_comment)

        # Mock classification use case - returns error
        mock_classify_use_case = MagicMock()
        mock_classify_use_case.execute = AsyncMock(
            return_value={
                "status": "error",
                "reason": "AI service unavailable",
            }
        )

        # Create use case
        use_case = TestCommentProcessingUseCase(
            session=mock_session,
            classify_use_case=mock_classify_use_case,
            media_repository_factory=lambda session: mock_media_repo,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            media_id="media_1",
            user_id="user_1",
            username="testuser",
            text="Test",
        )

        # Assert
        assert result["status"] == "error"
        assert "Classification failed" in result["reason"]
        assert "AI service unavailable" in result["reason"]

    async def test_execute_answer_generation_error(
        self, mock_session, media_factory, comment_factory, classification_factory
    ):
        """Test handling when answer generation fails for a question."""
        # Arrange
        media = await media_factory(media_id="media_1")
        comment = await comment_factory(comment_id="comment_1", media_id="media_1")
        classification = await classification_factory(
            comment_id="comment_1",
            classification_type="question / inquiry",
        )
        comment.classification = classification

        # Mock repositories
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=media)

        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        # Mock classification use case
        mock_classify_use_case = MagicMock()
        mock_classify_use_case.execute = AsyncMock(
            return_value={
                "status": "success",
                "classification": "question / inquiry",
            }
        )

        # Mock answer use case - returns error
        mock_answer_use_case = MagicMock()
        mock_answer_use_case.execute = AsyncMock(
            return_value={
                "status": "error",
                "reason": "No relevant documents found",
            }
        )

        # Create use case
        use_case = TestCommentProcessingUseCase(
            session=mock_session,
            classify_use_case=mock_classify_use_case,
            answer_use_case=mock_answer_use_case,
            media_repository_factory=lambda session: mock_media_repo,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            media_id="media_1",
            user_id="user_1",
            username="testuser",
            text="Where can I buy this?",
        )

        # Assert
        assert result["status"] == "success"  # Classification succeeded
        assert result["classification"] == "question / inquiry"
        assert result["answer"] is None  # Answer failed
        assert "answer_error" in result["processing_details"]
        assert "No relevant documents found" in result["processing_details"]["answer_error"]

    async def test_execute_with_parent_comment(
        self, mock_session, media_factory, comment_factory, classification_factory
    ):
        """Test processing comment with parent_id (reply)."""
        # Arrange
        media = await media_factory(media_id="media_1")
        parent_comment = await comment_factory(comment_id="parent_1", media_id="media_1")
        comment = await comment_factory(
            comment_id="comment_1",
            media_id="media_1",
            parent_id="parent_1"
        )
        classification = await classification_factory(
            comment_id="comment_1",
            classification_type="positive feedback",
        )
        comment.classification = classification

        # Mock repositories
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=media)

        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        # Mock classification use case
        mock_classify_use_case = MagicMock()
        mock_classify_use_case.execute = AsyncMock(
            return_value={
                "status": "success",
                "classification": "positive feedback",
            }
        )

        # Create use case
        use_case = TestCommentProcessingUseCase(
            session=mock_session,
            classify_use_case=mock_classify_use_case,
            media_repository_factory=lambda session: mock_media_repo,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            media_id="media_1",
            user_id="user_1",
            username="testuser",
            text="Thanks!",
            parent_id="parent_1",
        )

        # Assert
        assert result["status"] == "success"
        assert result["comment_id"] == "comment_1"

    async def test_execute_with_custom_media_caption_and_url(
        self, mock_session, media_factory, comment_factory, classification_factory
    ):
        """Test processing with custom media caption and URL."""
        # Arrange
        media = await media_factory(
            media_id="media_1",
            caption="Custom caption",
            media_url="https://example.com/photo.jpg"
        )
        comment = await comment_factory(comment_id="comment_1", media_id="media_1")
        classification = await classification_factory(comment_id="comment_1")
        comment.classification = classification

        # Mock repositories
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=media)

        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        # Mock classification use case
        mock_classify_use_case = MagicMock()
        mock_classify_use_case.execute = AsyncMock(
            return_value={"status": "success", "classification": "positive feedback"}
        )

        # Create use case
        use_case = TestCommentProcessingUseCase(
            session=mock_session,
            classify_use_case=mock_classify_use_case,
            media_repository_factory=lambda session: mock_media_repo,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            media_id="media_1",
            user_id="user_1",
            username="testuser",
            text="Nice!",
            media_caption="Custom caption",
            media_url="https://example.com/photo.jpg",
        )

        # Assert
        assert result["status"] == "success"

    async def test_execute_lazy_loads_classify_use_case_from_container(
        self, mock_session, media_factory, comment_factory, classification_factory
    ):
        """Test that classify use case is lazy loaded from container when not provided."""
        # Arrange
        media = await media_factory(media_id="media_1")
        comment = await comment_factory(comment_id="comment_1", media_id="media_1")
        classification = await classification_factory(comment_id="comment_1")
        comment.classification = classification

        # Mock repositories
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=media)

        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        # Mock container
        mock_classify_use_case = MagicMock()
        mock_classify_use_case.execute = AsyncMock(
            return_value={"status": "success", "classification": "positive feedback"}
        )

        mock_container = MagicMock()
        mock_container.classify_comment_use_case = MagicMock(
            return_value=mock_classify_use_case
        )

        # Create use case WITHOUT classify_use_case
        use_case = TestCommentProcessingUseCase(
            session=mock_session,
            classify_use_case=None,  # Will lazy load from container
            answer_use_case=None,
            media_repository_factory=lambda session: mock_media_repo,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act - patch get_container from core.container module
        with patch('core.container.get_container', return_value=mock_container):
            result = await use_case.execute(
                comment_id="comment_1",
                media_id="media_1",
                user_id="user_1",
                username="testuser",
                text="Test",
            )

        # Assert
        assert result["status"] == "success"
        mock_container.classify_comment_use_case.assert_called_once_with(session=mock_session)
        mock_classify_use_case.execute.assert_awaited_once()

    async def test_execute_lazy_loads_answer_use_case_from_container(
        self, mock_session, media_factory, comment_factory, classification_factory
    ):
        """Test that answer use case is lazy loaded from container for questions."""
        # Arrange
        media = await media_factory(media_id="media_1")
        comment = await comment_factory(comment_id="comment_1", media_id="media_1")
        classification = await classification_factory(
            comment_id="comment_1",
            classification_type="question / inquiry"
        )
        comment.classification = classification

        # Mock repositories
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=media)

        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        # Mock use cases
        mock_classify_use_case = MagicMock()
        mock_classify_use_case.execute = AsyncMock(
            return_value={"status": "success", "classification": "question / inquiry"}
        )

        mock_answer_use_case = MagicMock()
        mock_answer_use_case.execute = AsyncMock(
            return_value={"status": "success", "answer": "Answer text", "confidence": 0.9}
        )

        mock_container = MagicMock()
        mock_container.generate_answer_use_case = MagicMock(
            return_value=mock_answer_use_case
        )

        # Create use case WITHOUT answer_use_case
        use_case = TestCommentProcessingUseCase(
            session=mock_session,
            classify_use_case=mock_classify_use_case,
            answer_use_case=None,  # Will lazy load from container
            media_repository_factory=lambda session: mock_media_repo,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act - patch get_container from core.container module
        with patch('core.container.get_container', return_value=mock_container):
            result = await use_case.execute(
                comment_id="comment_1",
                media_id="media_1",
                user_id="user_1",
                username="testuser",
                text="What is this?",
            )

        # Assert
        assert result["status"] == "success"
        assert result["answer"] == "Answer text"
        mock_container.generate_answer_use_case.assert_called_once_with(session=mock_session)
        mock_answer_use_case.execute.assert_awaited_once()

    async def test_ensure_test_media_creates_new_media(self, db_session):
        """Test _ensure_test_media creates media when it doesn't exist."""
        # Mock repository
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=None)

        # Create use case
        use_case = TestCommentProcessingUseCase(
            session=db_session,
            media_repository_factory=lambda session: mock_media_repo,
            comment_repository_factory=lambda session: MagicMock(),
        )

        # Act
        media = await use_case._ensure_test_media(
            media_id="new_media",
            media_caption="Test caption",
            media_url="https://example.com/photo.jpg"
        )

        # Assert
        assert media is not None
        assert media.id == "new_media"
        assert media.caption == "Test caption"
        assert media.media_url == "https://example.com/photo.jpg"
        assert media.media_type == "IMAGE"

    async def test_ensure_test_media_returns_existing_media(
        self, db_session, media_factory
    ):
        """Test _ensure_test_media returns existing media without creating new."""
        # Arrange
        existing_media = await media_factory(media_id="existing_media")

        # Mock repository
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=existing_media)

        # Create use case
        use_case = TestCommentProcessingUseCase(
            session=db_session,
            media_repository_factory=lambda session: mock_media_repo,
            comment_repository_factory=lambda session: MagicMock(),
        )

        # Act
        media = await use_case._ensure_test_media(
            media_id="existing_media",
            media_caption="New caption",
            media_url="https://example.com/new.jpg"
        )

        # Assert
        assert media.id == "existing_media"
        # Should return existing media, not create new one

    async def test_ensure_test_comment_creates_new_comment(self, db_session):
        """Test _ensure_test_comment creates comment when it doesn't exist."""
        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=None)

        # Create use case
        use_case = TestCommentProcessingUseCase(
            session=db_session,
            media_repository_factory=lambda session: MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        comment = await use_case._ensure_test_comment(
            comment_id="new_comment",
            media_id="media_1",
            user_id="user_1",
            username="testuser",
            text="New comment text",
            parent_id="parent_1"
        )

        # Assert
        assert comment is not None
        assert comment.id == "new_comment"
        assert comment.text == "New comment text"
        assert comment.parent_id == "parent_1"
        assert comment.username == "testuser"

    async def test_ensure_test_comment_updates_existing_comment(
        self, db_session, comment_factory
    ):
        """Test _ensure_test_comment updates text of existing comment."""
        # Arrange
        existing_comment = await comment_factory(
            comment_id="existing_comment",
            text="Old text"
        )

        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=existing_comment)

        # Create use case
        use_case = TestCommentProcessingUseCase(
            session=db_session,
            media_repository_factory=lambda session: MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        comment = await use_case._ensure_test_comment(
            comment_id="existing_comment",
            media_id="media_1",
            user_id="user_1",
            username="testuser",
            text="Updated text",
            parent_id="new_parent"
        )

        # Assert
        assert comment.text == "Updated text"
        assert comment.parent_id == "new_parent"

    async def test_ensure_classification_record_creates_new(self, mock_session):
        """Test _ensure_classification_record creates classification when missing."""
        # Create mock comment without classification
        mock_comment = MagicMock()
        mock_comment.id = "comment_1"
        mock_comment.classification = None  # No classification

        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=mock_comment)

        # Create use case
        use_case = TestCommentProcessingUseCase(
            session=mock_session,
            media_repository_factory=lambda session: MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        await use_case._ensure_classification_record("comment_1")

        # Assert - should have added classification to session
        mock_session.add.assert_called_once()
        # Verify the added object is a CommentClassification
        added_obj = mock_session.add.call_args[0][0]
        assert isinstance(added_obj, CommentClassification)
        assert added_obj.comment_id == "comment_1"

    async def test_ensure_classification_record_skips_if_exists(
        self, db_session, comment_factory, classification_factory
    ):
        """Test _ensure_classification_record skips when classification exists."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1")
        classification = await classification_factory(comment_id="comment_1")
        comment.classification = classification

        # Mock repository
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        # Create use case
        use_case = TestCommentProcessingUseCase(
            session=db_session,
            media_repository_factory=lambda session: MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        await use_case._ensure_classification_record("comment_1")

        # Assert - should not add new classification (no error means success)

    async def test_execute_exception_during_processing_rollback(self, db_session):
        """Test that session is rolled back on exception."""
        # Mock repository that raises exception
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(side_effect=Exception("Database error"))

        mock_session = MagicMock()
        mock_session.rollback = AsyncMock()

        # Create use case
        use_case = TestCommentProcessingUseCase(
            session=mock_session,
            media_repository_factory=lambda session: mock_media_repo,
            comment_repository_factory=lambda session: MagicMock(),
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            media_id="media_1",
            user_id="user_1",
            username="testuser",
            text="Test",
        )

        # Assert
        assert result["status"] == "error"
        assert "Unexpected error" in result["reason"]
        assert "Database error" in result["reason"]
        mock_session.rollback.assert_awaited_once()

    async def test_execute_classification_without_reasoning(
        self, mock_session, media_factory, comment_factory, classification_factory
    ):
        """Test processing when classification has no reasoning field."""
        # Arrange
        media = await media_factory(media_id="media_1")
        comment = await comment_factory(comment_id="comment_1", media_id="media_1")
        classification = await classification_factory(
            comment_id="comment_1",
            classification_type="spam",
            reasoning=None  # No reasoning
        )
        comment.classification = classification

        # Mock repositories
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=media)

        mock_comment_repo = MagicMock()
        mock_comment_repo.get_by_id = AsyncMock(return_value=comment)

        # Mock classification use case
        mock_classify_use_case = MagicMock()
        mock_classify_use_case.execute = AsyncMock(
            return_value={"status": "success", "classification": "spam"}
        )

        # Create use case
        use_case = TestCommentProcessingUseCase(
            session=mock_session,
            classify_use_case=mock_classify_use_case,
            media_repository_factory=lambda session: mock_media_repo,
            comment_repository_factory=lambda session: mock_comment_repo,
        )

        # Act
        result = await use_case.execute(
            comment_id="comment_1",
            media_id="media_1",
            user_id="user_1",
            username="testuser",
            text="Spam text",
        )

        # Assert
        assert result["status"] == "success"
        assert result["classification_reasoning"] is None