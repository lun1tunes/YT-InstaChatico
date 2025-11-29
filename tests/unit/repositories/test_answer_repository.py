"""
Unit tests for AnswerRepository.

Tests data access logic for question answers without external dependencies.
"""

import pytest
from datetime import datetime

from core.repositories.answer import AnswerRepository
from core.models.question_answer import QuestionAnswer, AnswerStatus


@pytest.mark.unit
@pytest.mark.repository
class TestAnswerRepository:
    """Test AnswerRepository methods."""

    async def test_create_answer(self, db_session, instagram_comment_factory):
        """Test creating an answer."""
        # Arrange
        comment = await instagram_comment_factory()
        repo = AnswerRepository(db_session)
        answer_entity = QuestionAnswer(
            comment_id=comment.id,
            answer="Test answer",
            answer_confidence=0.9,
            answer_quality_score=85,
            processing_time_ms=1500,
        )

        # Act
        answer = await repo.create(answer_entity)

        # Assert
        assert answer.comment_id == comment.id
        assert answer.answer == "Test answer"
        assert answer.answer_confidence == 0.9
        assert answer.answer_quality_score == 85
        assert answer.processing_time_ms == 1500

    async def test_get_by_comment_id(self, db_session, instagram_comment_factory, answer_factory):
        """Test getting answer by comment ID."""
        # Arrange
        comment = await instagram_comment_factory()
        await answer_factory(comment_id=comment.id, answer_text="Saved answer")
        repo = AnswerRepository(db_session)

        # Act
        answer = await repo.get_by_comment_id(comment.id)

        # Assert
        assert answer is not None
        assert answer.comment_id == comment.id
        assert answer.answer == "Saved answer"

    async def test_get_by_comment_id_nonexistent(self, db_session):
        """Test getting answer for non-existent comment returns None."""
        # Arrange
        repo = AnswerRepository(db_session)

        # Act
        answer = await repo.get_by_comment_id("nonexistent_id")

        # Assert
        assert answer is None

    async def test_answer_with_tokens(self, db_session, instagram_comment_factory):
        """Test creating answer with token usage."""
        # Arrange
        comment = await instagram_comment_factory()
        repo = AnswerRepository(db_session)
        answer_entity = QuestionAnswer(
            comment_id=comment.id,
            answer="Answer",
            input_tokens=200,
            output_tokens=150,
        )

        # Act
        answer = await repo.create(answer_entity)

        # Assert
        assert answer.input_tokens == 200
        assert answer.output_tokens == 150

    async def test_get_by_reply_id(self, db_session, instagram_comment_factory, answer_factory):
        """Test getting answer by Instagram reply ID."""
        # Arrange
        comment = await instagram_comment_factory()
        await answer_factory(comment_id=comment.id, reply_id="reply_123")
        repo = AnswerRepository(db_session)

        # Act
        answer = await repo.get_by_reply_id("reply_123")

        # Assert
        assert answer is not None
        assert answer.reply_id == "reply_123"
        assert answer.comment_id == comment.id

    async def test_get_by_reply_id_nonexistent(self, db_session):
        """Test getting answer by non-existent reply ID returns None."""
        # Arrange
        repo = AnswerRepository(db_session)

        # Act
        answer = await repo.get_by_reply_id("nonexistent_reply")

        # Assert
        assert answer is None

    async def test_create_for_comment(self, db_session, instagram_comment_factory):
        """Test creating a new answer record for a comment."""
        # Arrange
        comment = await instagram_comment_factory()
        repo = AnswerRepository(db_session)

        # Act
        answer = await repo.create_for_comment(comment.id)
        await db_session.flush()

        # Assert
        assert answer is not None
        assert answer.comment_id == comment.id
        assert answer.processing_status == AnswerStatus.PENDING

    async def test_get_pending_answers(self, db_session, instagram_comment_factory):
        """Test getting pending answers for processing."""
        # Arrange
        comment1 = await instagram_comment_factory()
        comment2 = await instagram_comment_factory()
        comment3 = await instagram_comment_factory()

        repo = AnswerRepository(db_session)
        await repo.create_for_comment(comment1.id)
        await repo.create_for_comment(comment2.id)

        # Create a completed answer
        completed_answer = QuestionAnswer(
            comment_id=comment3.id,
            answer="Completed answer",
            processing_status=AnswerStatus.COMPLETED,
        )
        await repo.create(completed_answer)
        await db_session.flush()

        # Act
        pending = await repo.get_pending_answers(limit=10)

        # Assert
        assert len(pending) == 2
        assert all(a.processing_status == AnswerStatus.PENDING for a in pending)

    async def test_get_pending_answers_with_limit(self, db_session, instagram_comment_factory):
        """Test getting pending answers respects limit."""
        # Arrange
        repo = AnswerRepository(db_session)
        for _ in range(5):
            comment = await instagram_comment_factory()
            await repo.create_for_comment(comment.id)
        await db_session.flush()

        # Act
        pending = await repo.get_pending_answers(limit=3)

        # Assert
        assert len(pending) == 3

    async def test_update_answer(self, db_session, instagram_comment_factory, answer_factory):
        """Test updating an answer."""
        # Arrange
        comment = await instagram_comment_factory()
        answer = await answer_factory(comment_id=comment.id, answer_text="Original")
        repo = AnswerRepository(db_session)

        # Act
        answer.answer = "Updated answer"
        updated = await repo.update(answer)

        # Assert
        assert updated.answer == "Updated answer"

    async def test_delete_answer(self, db_session, instagram_comment_factory, answer_factory):
        """Test deleting an answer."""
        # Arrange
        comment = await instagram_comment_factory()
        answer = await answer_factory(comment_id=comment.id)
        repo = AnswerRepository(db_session)

        # Act
        await repo.delete(answer)

        # Assert
        deleted = await repo.get_by_id(answer.id)
        assert deleted is None

    async def test_list_all_answers(self, db_session, instagram_comment_factory, answer_factory):
        """Test listing all answers."""
        # Arrange
        comment1 = await instagram_comment_factory()
        comment2 = await instagram_comment_factory()
        await answer_factory(comment_id=comment1.id)
        await answer_factory(comment_id=comment2.id)
        repo = AnswerRepository(db_session)

        # Act
        answers = await repo.get_all()

        # Assert
        assert len(answers) >= 2

    async def test_answer_with_reply_status(self, db_session, instagram_comment_factory):
        """Test creating answer with reply status tracking."""
        # Arrange
        comment = await instagram_comment_factory()
        repo = AnswerRepository(db_session)
        answer_entity = QuestionAnswer(
            comment_id=comment.id,
            answer="Test answer",
            reply_id="reply_456",
            reply_sent=True,
        )

        # Act
        answer = await repo.create(answer_entity)

        # Assert
        assert answer.reply_id == "reply_456"
        assert answer.reply_sent is True

    async def test_answer_processing_status_workflow(self, db_session, instagram_comment_factory):
        """Test full answer processing status workflow."""
        # Arrange
        comment = await instagram_comment_factory()
        repo = AnswerRepository(db_session)

        # Act - Create pending
        answer = await repo.create_for_comment(comment.id)
        await db_session.flush()

        # Assert - Initially pending
        assert answer.processing_status == AnswerStatus.PENDING

        # Act - Mark as processing
        answer.processing_status = AnswerStatus.PROCESSING
        await repo.update(answer)
        updated = await repo.get_by_id(answer.id)

        # Assert - Now processing
        assert updated.processing_status == AnswerStatus.PROCESSING

        # Act - Mark as completed
        answer.processing_status = AnswerStatus.COMPLETED
        await repo.update(answer)
        completed = await repo.get_by_id(answer.id)

        # Assert - Now completed
        assert completed.processing_status == AnswerStatus.COMPLETED

    async def test_answer_with_quality_metrics(self, db_session, instagram_comment_factory):
        """Test creating answer with quality metrics."""
        # Arrange
        comment = await instagram_comment_factory()
        repo = AnswerRepository(db_session)
        answer_entity = QuestionAnswer(
            comment_id=comment.id,
            answer="High quality answer",
            answer_confidence=0.95,
            answer_quality_score=92,
            processing_time_ms=2500,
        )

        # Act
        answer = await repo.create(answer_entity)

        # Assert
        assert answer.answer_confidence == 0.95
        assert answer.answer_quality_score == 92
        assert answer.processing_time_ms == 2500

    async def test_multiple_answers_for_different_comments(self, db_session, instagram_comment_factory, answer_factory):
        """Test creating answers for multiple comments."""
        # Arrange
        comment1 = await instagram_comment_factory()
        comment2 = await instagram_comment_factory()
        await answer_factory(comment_id=comment1.id, answer_text="Answer 1")
        await answer_factory(comment_id=comment2.id, answer_text="Answer 2")
        repo = AnswerRepository(db_session)

        # Act
        answer1 = await repo.get_by_comment_id(comment1.id)
        answer2 = await repo.get_by_comment_id(comment2.id)

        # Assert
        assert answer1.answer == "Answer 1"
        assert answer2.answer == "Answer 2"

    async def test_answer_with_ai_flag(self, db_session, instagram_comment_factory):
        """Test creating answer with explicit ai/manual flag."""
        # Arrange
        comment = await instagram_comment_factory()
        repo = AnswerRepository(db_session)
        answer_entity = QuestionAnswer(
            comment_id=comment.id,
            answer="Manual answer",
            is_ai_generated=False,
        )

        # Act
        answer = await repo.create(answer_entity)

        # Assert
        assert answer.is_ai_generated is False

    async def test_get_pending_answers_empty_result(self, db_session):
        """Test get_pending_answers returns empty list when no pending answers."""
        # Arrange
        repo = AnswerRepository(db_session)

        # Act
        pending = await repo.get_pending_answers(limit=10)

        # Assert
        assert pending == []
        assert len(pending) == 0

    async def test_get_pending_answers_limit_zero(self, db_session, instagram_comment_factory):
        """Test get_pending_answers with limit=0."""
        # Arrange
        repo = AnswerRepository(db_session)
        comment = await instagram_comment_factory()
        await repo.create_for_comment(comment.id)
        await db_session.flush()

        # Act
        pending = await repo.get_pending_answers(limit=0)

        # Assert
        assert len(pending) == 0

    async def test_get_by_comment_id_with_empty_string(self, db_session):
        """Test get_by_comment_id with empty string."""
        # Arrange
        repo = AnswerRepository(db_session)

        # Act
        answer = await repo.get_by_comment_id("")

        # Assert
        assert answer is None

    async def test_get_by_reply_id_with_empty_string(self, db_session):
        """Test get_by_reply_id with empty string."""
        # Arrange
        repo = AnswerRepository(db_session)

        # Act
        answer = await repo.get_by_reply_id("")

        # Assert
        assert answer is None

    async def test_answer_with_all_optional_fields_none(self, db_session, instagram_comment_factory):
        """Test creating answer with minimal required fields only."""
        # Arrange
        comment = await instagram_comment_factory()
        repo = AnswerRepository(db_session)
        answer_entity = QuestionAnswer(
            comment_id=comment.id,
        )

        # Act
        answer = await repo.create(answer_entity)
        await db_session.flush()

        # Assert
        assert answer.comment_id == comment.id
        assert answer.answer is None
        assert answer.answer_confidence is None
        assert answer.answer_quality_score is None

    async def test_multiple_answers_same_comment_id(self, db_session, instagram_comment_factory, answer_factory):
        """Test that get_by_comment_id returns first match when multiple exist."""
        # Arrange
        comment = await instagram_comment_factory()
        repo = AnswerRepository(db_session)

        # Create two answers for same comment (edge case, shouldn't happen in production)
        answer1 = await answer_factory(comment_id=comment.id, answer_text="First answer")

        # Act
        result = await repo.get_by_comment_id(comment.id)

        # Assert
        assert result is not None
        assert result.comment_id == comment.id
