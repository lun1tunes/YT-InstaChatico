"""Unit tests for ClassificationRepository - FIXED"""

import pytest
from core.repositories.classification import ClassificationRepository
from core.models.comment_classification import CommentClassification, ProcessingStatus


@pytest.mark.unit
@pytest.mark.repository
class TestClassificationRepository:
    """Test ClassificationRepository methods."""

    async def test_create_classification(self, db_session, instagram_comment_factory):
        """Test creating a classification."""
        # Arrange
        comment = await instagram_comment_factory()
        repo = ClassificationRepository(db_session)
        clf_entity = CommentClassification(
            comment_id=comment.id,
            type="question / inquiry",
            confidence=95,
            reasoning="Contains question mark",
            input_tokens=100,
            output_tokens=50,
        )

        # Act
        classification = await repo.create(clf_entity)

        # Assert
        assert classification.comment_id == comment.id
        assert classification.type == "question / inquiry"
        assert classification.confidence == 95
        assert classification.reasoning == "Contains question mark"
        assert classification.input_tokens == 100
        assert classification.output_tokens == 50

    async def test_get_by_comment_id(self, db_session, instagram_comment_factory, classification_factory):
        """Test getting classification by comment ID."""
        # Arrange
        comment = await instagram_comment_factory()
        await classification_factory(comment_id=comment.id, classification="positive")
        repo = ClassificationRepository(db_session)

        # Act
        classification = await repo.get_by_comment_id(comment.id)

        # Assert
        assert classification is not None
        assert classification.comment_id == comment.id
        assert classification.type == "positive"

    async def test_get_by_comment_id_nonexistent(self, db_session):
        """Test getting classification for non-existent comment returns None."""
        # Arrange
        repo = ClassificationRepository(db_session)

        # Act
        classification = await repo.get_by_comment_id("nonexistent_id")

        # Assert
        assert classification is None

    async def test_get_pending_retries(self, db_session, instagram_comment_factory, classification_factory):
        """Test getting classifications that need retry."""
        # Arrange
        comment1 = await instagram_comment_factory()
        comment2 = await instagram_comment_factory()
        comment3 = await instagram_comment_factory()

        await classification_factory(comment_id=comment1.id, classification="retry", retry_count=1, processing_status=ProcessingStatus.RETRY)
        await classification_factory(comment_id=comment2.id, classification="retry", retry_count=2, processing_status=ProcessingStatus.RETRY)
        await classification_factory(comment_id=comment3.id, classification="positive", retry_count=0)

        repo = ClassificationRepository(db_session)

        # Act
        pending = await repo.get_pending_retries()

        # Assert
        assert len(pending) == 2
        assert all(c.processing_status == ProcessingStatus.RETRY for c in pending)

    async def test_mark_processing(self, db_session, instagram_comment_factory, classification_factory):
        """Test marking classification as processing."""
        # Arrange
        comment = await instagram_comment_factory()
        clf = await classification_factory(comment_id=comment.id, retry_count=0)
        repo = ClassificationRepository(db_session)

        # Act
        await repo.mark_processing(clf, retry_count=1)
        await db_session.flush()

        # Assert
        assert clf.processing_status == ProcessingStatus.PROCESSING
        assert clf.retry_count == 1
        assert clf.processing_started_at is not None

    async def test_mark_completed(self, db_session, instagram_comment_factory, classification_factory):
        """Test marking classification as completed."""
        # Arrange
        comment = await instagram_comment_factory()
        clf = await classification_factory(comment_id=comment.id)
        clf.last_error = "Some error"
        repo = ClassificationRepository(db_session)

        # Act
        await repo.mark_completed(clf)
        await db_session.flush()

        # Assert
        assert clf.processing_status == ProcessingStatus.COMPLETED
        assert clf.processing_completed_at is not None
        assert clf.last_error is None

    async def test_mark_failed(self, db_session, instagram_comment_factory, classification_factory):
        """Test marking classification as failed."""
        # Arrange
        comment = await instagram_comment_factory()
        clf = await classification_factory(comment_id=comment.id)
        repo = ClassificationRepository(db_session)
        error_message = "Processing failed due to timeout"

        # Act
        await repo.mark_failed(clf, error_message)
        await db_session.flush()

        # Assert
        assert clf.processing_status == ProcessingStatus.FAILED
        assert clf.last_error == error_message
        assert clf.processing_completed_at is not None

    async def test_mark_retry(self, db_session, instagram_comment_factory, classification_factory):
        """Test marking classification as retry."""
        comment = await instagram_comment_factory()
        clf = await classification_factory(comment_id=comment.id)
        repo = ClassificationRepository(db_session)
        error_message = "Temporary upstream error"

        await repo.mark_retry(clf, error_message)
        await db_session.flush()

        assert clf.processing_status == ProcessingStatus.RETRY
        assert clf.last_error == error_message
        assert clf.processing_completed_at is not None

    async def test_update_classification(self, db_session, instagram_comment_factory, classification_factory):
        """Test updating a classification."""
        # Arrange
        comment = await instagram_comment_factory()
        clf = await classification_factory(comment_id=comment.id, confidence=80)
        repo = ClassificationRepository(db_session)

        # Act
        clf.confidence = 95
        updated = await repo.update(clf)

        # Assert
        assert updated.confidence == 95

    async def test_delete_classification(self, db_session, instagram_comment_factory, classification_factory):
        """Test deleting a classification."""
        # Arrange
        comment = await instagram_comment_factory()
        clf = await classification_factory(comment_id=comment.id)
        repo = ClassificationRepository(db_session)

        # Act
        await repo.delete(clf)

        # Assert
        deleted = await repo.get_by_id(clf.id)
        assert deleted is None

    async def test_list_all_classifications(self, db_session, instagram_comment_factory, classification_factory):
        """Test listing all classifications."""
        # Arrange
        comment1 = await instagram_comment_factory()
        comment2 = await instagram_comment_factory()
        await classification_factory(comment_id=comment1.id)
        await classification_factory(comment_id=comment2.id)
        repo = ClassificationRepository(db_session)

        # Act
        classifications = await repo.get_all()

        # Assert
        assert len(classifications) >= 2

    async def test_processing_status_workflow(self, db_session, instagram_comment_factory, classification_factory):
        """Test full processing status workflow."""
        # Arrange
        comment = await instagram_comment_factory()
        clf = await classification_factory(comment_id=comment.id)
        repo = ClassificationRepository(db_session)

        # Act & Assert - Mark as processing
        await repo.mark_processing(clf, retry_count=0)
        await db_session.flush()
        assert clf.processing_status == ProcessingStatus.PROCESSING
        assert clf.processing_started_at is not None

        # Act & Assert - Mark as completed
        await repo.mark_completed(clf)
        await db_session.flush()
        assert clf.processing_status == ProcessingStatus.COMPLETED
        assert clf.processing_completed_at is not None

    async def test_retry_increment_workflow(self, db_session, instagram_comment_factory, classification_factory):
        """Test retry count increments properly."""
        # Arrange
        comment = await instagram_comment_factory()
        clf = await classification_factory(comment_id=comment.id, retry_count=0)
        repo = ClassificationRepository(db_session)

        # Act - First retry
        await repo.mark_processing(clf, retry_count=1)
        await db_session.flush()

        # Assert
        assert clf.retry_count == 1

        # Act - Second retry
        await repo.mark_failed(clf, "First retry failed")
        await repo.mark_processing(clf, retry_count=2)
        await db_session.flush()

        # Assert
        assert clf.retry_count == 2

    async def test_multiple_classifications_for_different_comments(self, db_session, instagram_comment_factory, classification_factory):
        """Test creating classifications for multiple comments."""
        # Arrange
        comment1 = await instagram_comment_factory()
        comment2 = await instagram_comment_factory()
        await classification_factory(comment_id=comment1.id, classification="positive")
        await classification_factory(comment_id=comment2.id, classification="question / inquiry")
        repo = ClassificationRepository(db_session)

        # Act
        clf1 = await repo.get_by_comment_id(comment1.id)
        clf2 = await repo.get_by_comment_id(comment2.id)

        # Assert
        assert clf1.type == "positive"
        assert clf2.type == "question / inquiry"

    async def test_get_pending_retries_empty_result(self, db_session):
        """Test get_pending_retries returns empty list when no retries pending."""
        # Arrange
        repo = ClassificationRepository(db_session)

        # Act
        pending = await repo.get_pending_retries()

        # Assert
        assert pending == []

    async def test_get_pending_retries_excludes_max_retries(self, db_session, instagram_comment_factory, classification_factory):
        """Test get_pending_retries excludes classifications that hit max retries."""
        # Arrange
        comment = await instagram_comment_factory()
        clf = await classification_factory(
            comment_id=comment.id,
            retry_count=5,
            max_retries=5,
            processing_status=ProcessingStatus.RETRY
        )
        repo = ClassificationRepository(db_session)

        # Act
        pending = await repo.get_pending_retries()

        # Assert - Should be empty because retry_count == max_retries
        assert len(pending) == 0

    async def test_mark_completed_clears_error(self, db_session, instagram_comment_factory, classification_factory):
        """Test mark_completed clears last_error field."""
        # Arrange
        comment = await instagram_comment_factory()
        clf = await classification_factory(comment_id=comment.id)
        clf.last_error = "Previous error message"
        repo = ClassificationRepository(db_session)

        # Act
        await repo.mark_completed(clf)
        await db_session.flush()

        # Assert
        assert clf.processing_status == ProcessingStatus.COMPLETED
        assert clf.last_error is None

    async def test_get_by_comment_id_with_empty_string(self, db_session):
        """Test get_by_comment_id with empty string returns None."""
        # Arrange
        repo = ClassificationRepository(db_session)

        # Act
        result = await repo.get_by_comment_id("")

        # Assert
        assert result is None

    async def test_mark_processing_updates_timestamp(self, db_session, instagram_comment_factory, classification_factory):
        """Test mark_processing sets processing_started_at timestamp."""
        # Arrange
        comment = await instagram_comment_factory()
        clf = await classification_factory(comment_id=comment.id)
        repo = ClassificationRepository(db_session)
        assert clf.processing_started_at is None

        # Act
        await repo.mark_processing(clf, retry_count=0)
        await db_session.flush()

        # Assert
        assert clf.processing_started_at is not None

    async def test_mark_failed_preserves_error_message(self, db_session, instagram_comment_factory, classification_factory):
        """Test mark_failed stores error message correctly."""
        # Arrange
        comment = await instagram_comment_factory()
        clf = await classification_factory(comment_id=comment.id)
        repo = ClassificationRepository(db_session)
        error_msg = "Connection timeout after 30 seconds"

        # Act
        await repo.mark_failed(clf, error_msg)
        await db_session.flush()

        # Assert
        assert clf.processing_status == ProcessingStatus.FAILED
        assert clf.last_error == error_msg
        assert clf.processing_completed_at is not None

    async def test_classification_with_minimal_fields(self, db_session, instagram_comment_factory):
        """Test creating classification with only required fields."""
        # Arrange
        comment = await instagram_comment_factory()
        repo = ClassificationRepository(db_session)
        clf_entity = CommentClassification(
            comment_id=comment.id,
            type="positive",
        )

        # Act
        clf = await repo.create(clf_entity)
        await db_session.flush()

        # Assert
        assert clf.comment_id == comment.id
        assert clf.type == "positive"
        assert clf.confidence is None
        assert clf.reasoning is None
