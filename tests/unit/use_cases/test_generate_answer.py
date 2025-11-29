"""
Unit tests for GenerateAnswerUseCase.

Tests cover:
- Happy path: successful answer generation
- Edge cases: comment not found, max retries, service exceptions
- Answer record creation and updates
- Retry logic and error handling
- Token and timing tracking
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace

from core.use_cases.generate_answer import GenerateAnswerUseCase
from core.models.question_answer import AnswerStatus
from core.utils.task_helpers import DEFAULT_RETRY_SCHEDULE

TASK_MAX_RETRIES = len(DEFAULT_RETRY_SCHEDULE)


@pytest.mark.unit
@pytest.mark.use_case
class TestGenerateAnswerUseCase:
    """Test GenerateAnswerUseCase methods."""

    async def test_execute_success(self, db_session, comment_factory):
        """Test successful answer generation."""
        # Arrange
        comment = await comment_factory(
            comment_id="comment_1",
            text="What is your return policy?",
            conversation_id="conv_123",
            username="user123",
        )

        # Mock answer result from service
        mock_answer_result = SimpleNamespace(
            answer="Our return policy is 30 days from purchase date.",
            answer_confidence=0.95,
            answer_quality_score=88,
            llm_raw_response="Full LLM response here",
            input_tokens=200,
            output_tokens=150,
            processing_time_ms=1200,
        )

        # Mock services
        mock_qa_service = MagicMock()
        mock_qa_service.generate_answer = AsyncMock(return_value=mock_answer_result)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        from core.models.question_answer import QuestionAnswer
        answer_record = QuestionAnswer(comment_id="comment_1")

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_answer_repo.create_for_comment = AsyncMock(return_value=answer_record)

        # Create use case
        use_case = GenerateAnswerUseCase(
            session=db_session,
            qa_service=mock_qa_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", retry_count=0)

        # Assert
        assert result["status"] == "success"
        assert result["answer"] == "Our return policy is 30 days from purchase date."
        assert result["confidence"] == 0.95
        assert result["quality_score"] == 88

        # Verify service calls
        mock_comment_repo.get_with_classification.assert_awaited_once_with("comment_1")
        mock_qa_service.generate_answer.assert_awaited_once_with(
            question_text="What is your return policy?",
            conversation_id="conv_123",
            username="user123",
        )

        # Verify answer record updated
        assert answer_record.answer == "Our return policy is 30 days from purchase date."
        assert answer_record.answer_confidence == 0.95
        assert answer_record.answer_quality_score == 88
        assert answer_record.input_tokens == 200
        assert answer_record.output_tokens == 150
        assert answer_record.processing_time_ms == 1200
        assert answer_record.processing_status == AnswerStatus.COMPLETED

    async def test_execute_comment_not_found(self, db_session):
        """Test answer generation when comment doesn't exist."""
        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=None)

        # Create use case
        use_case = GenerateAnswerUseCase(
            session=db_session,
            qa_service=MagicMock(),
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: MagicMock(),
        )

        # Act
        result = await use_case.execute(comment_id="nonexistent", retry_count=0)

        # Assert
        assert result["status"] == "error"
        assert "not found" in result["reason"].lower()

    async def test_execute_with_existing_answer_record(self, db_session, comment_factory):
        """Test answer generation when answer record already exists."""
        # Arrange
        comment = await comment_factory(
            comment_id="comment_1",
            text="Question?",
            conversation_id="conv_123",
        )

        from core.models.question_answer import QuestionAnswer
        existing_answer = QuestionAnswer(
            comment_id="comment_1",
            processing_status=AnswerStatus.PENDING,
        )

        # Mock answer result
        mock_answer_result = SimpleNamespace(
            answer="Test answer",
            answer_confidence=0.9,
            answer_quality_score=85,
            input_tokens=100,
            output_tokens=50,
            processing_time_ms=1000,
        )

        # Mock services
        mock_qa_service = MagicMock()
        mock_qa_service.generate_answer = AsyncMock(return_value=mock_answer_result)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=existing_answer)

        # Create use case
        use_case = GenerateAnswerUseCase(
            session=db_session,
            qa_service=mock_qa_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", retry_count=0)

        # Assert
        assert result["status"] == "success"
        # Should NOT create new answer record
        mock_answer_repo.create_for_comment.assert_not_called()
        # Should use existing record
        assert existing_answer.answer == "Test answer"

    async def test_execute_service_exception_with_retry(self, db_session, comment_factory):
        """Test answer generation when service raises exception (should retry)."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1", conversation_id="conv_1")

        from core.models.question_answer import QuestionAnswer
        answer_record = QuestionAnswer(comment_id="comment_1", max_retries=TASK_MAX_RETRIES)

        # Mock services
        mock_qa_service = MagicMock()
        mock_qa_service.generate_answer = AsyncMock(side_effect=Exception("API timeout"))

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_answer_repo.create_for_comment = AsyncMock(return_value=answer_record)

        # Create use case
        use_case = GenerateAnswerUseCase(
            session=db_session,
            qa_service=mock_qa_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", retry_count=1)

        # Assert
        assert result["status"] == "retry"
        assert "API timeout" in result["reason"]
        assert answer_record.processing_status == AnswerStatus.FAILED
        assert answer_record.last_error == "API timeout"

    async def test_execute_service_exception_max_retries_exceeded(
        self, db_session, comment_factory
    ):
        """Test answer generation when max retries exceeded."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1", conversation_id="conv_1")

        from core.models.question_answer import QuestionAnswer
        answer_record = QuestionAnswer(comment_id="comment_1", max_retries=TASK_MAX_RETRIES)

        # Mock services
        mock_qa_service = MagicMock()
        mock_qa_service.generate_answer = AsyncMock(side_effect=Exception("Persistent error"))

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_answer_repo.create_for_comment = AsyncMock(return_value=answer_record)

        # Create use case
        use_case = GenerateAnswerUseCase(
            session=db_session,
            qa_service=mock_qa_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act - retry_count = TASK_MAX_RETRIES, equals max_retries
        result = await use_case.execute(comment_id="comment_1", retry_count=TASK_MAX_RETRIES)

        # Assert
        assert result["status"] == "error"
        assert "Persistent error" in result["reason"]
        assert answer_record.processing_status == AnswerStatus.FAILED

    async def test_execute_updates_retry_count(self, db_session, comment_factory):
        """Test that retry_count is properly tracked."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1", conversation_id="conv_1")

        from core.models.question_answer import QuestionAnswer
        answer_record = QuestionAnswer(comment_id="comment_1")

        mock_answer_result = SimpleNamespace(
            answer="Answer",
            answer_confidence=0.9,
            answer_quality_score=85,
            input_tokens=100,
            output_tokens=50,
            processing_time_ms=1000,
        )

        # Mock services
        mock_qa_service = MagicMock()
        mock_qa_service.generate_answer = AsyncMock(return_value=mock_answer_result)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_answer_repo.create_for_comment = AsyncMock(return_value=answer_record)

        # Create use case
        use_case = GenerateAnswerUseCase(
            session=db_session,
            qa_service=mock_qa_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act
        await use_case.execute(comment_id="comment_1", retry_count=2)

        # Assert
        assert answer_record.retry_count == 2

    async def test_execute_answer_without_optional_fields(self, db_session, comment_factory):
        """Test answer generation when result doesn't have optional fields."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1", conversation_id="conv_1")

        # Mock answer result WITHOUT optional fields
        mock_answer_result = SimpleNamespace(
            answer="Simple answer",
            answer_confidence=0.8,
            answer_quality_score=75,
            input_tokens=50,
            output_tokens=30,
            processing_time_ms=800,
        )

        from core.models.question_answer import QuestionAnswer
        answer_record = QuestionAnswer(comment_id="comment_1")

        # Mock services
        mock_qa_service = MagicMock()
        mock_qa_service.generate_answer = AsyncMock(return_value=mock_answer_result)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_answer_repo.create_for_comment = AsyncMock(return_value=answer_record)

        # Create use case
        use_case = GenerateAnswerUseCase(
            session=db_session,
            qa_service=mock_qa_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", retry_count=0)

        # Assert
        assert result["status"] == "success"
        assert answer_record.llm_raw_response is None
        assert answer_record.is_ai_generated is True

    async def test_execute_marks_processing_status(self, db_session, comment_factory):
        """Test that processing status is correctly updated throughout execution."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1", conversation_id="conv_1")

        from core.models.question_answer import QuestionAnswer
        answer_record = QuestionAnswer(comment_id="comment_1")

        mock_answer_result = SimpleNamespace(
            answer="Answer",
            answer_confidence=0.9,
            answer_quality_score=85,
            input_tokens=100,
            output_tokens=50,
            processing_time_ms=1000,
        )

        # Mock services
        mock_qa_service = MagicMock()
        mock_qa_service.generate_answer = AsyncMock(return_value=mock_answer_result)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_answer_repo.create_for_comment = AsyncMock(return_value=answer_record)

        # Create use case
        use_case = GenerateAnswerUseCase(
            session=db_session,
            qa_service=mock_qa_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act
        await use_case.execute(comment_id="comment_1", retry_count=0)

        # Assert
        assert answer_record.processing_status == AnswerStatus.COMPLETED
        assert answer_record.processing_started_at is not None
        assert answer_record.processing_completed_at is not None

    async def test_execute_username_passed_to_service(self, db_session, comment_factory):
        """Test that username is correctly passed to QA service."""
        # Arrange
        comment = await comment_factory(
            comment_id="comment_1",
            conversation_id="conv_1",
            username="alice_wonderland",
        )

        from core.models.question_answer import QuestionAnswer
        answer_record = QuestionAnswer(comment_id="comment_1")

        mock_answer_result = SimpleNamespace(
            answer="Answer",
            answer_confidence=0.9,
            answer_quality_score=85,
            input_tokens=100,
            output_tokens=50,
            processing_time_ms=1000,
        )

        # Capture username passed to service
        captured_username = None

        async def capture_username(question_text, conversation_id, username):
            nonlocal captured_username
            captured_username = username
            return mock_answer_result

        # Mock services
        mock_qa_service = MagicMock()
        mock_qa_service.generate_answer = AsyncMock(side_effect=capture_username)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_answer_repo.create_for_comment = AsyncMock(return_value=answer_record)

        # Create use case
        use_case = GenerateAnswerUseCase(
            session=db_session,
            qa_service=mock_qa_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act
        await use_case.execute(comment_id="comment_1", retry_count=0)

        # Assert
        assert captured_username == "alice_wonderland"

    async def test_execute_db_commit_fails_after_success(self, db_session, comment_factory):
        """Test handling when database commit fails after successful answer generation."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1", conversation_id="conv_1")

        from core.models.question_answer import QuestionAnswer
        answer_record = QuestionAnswer(comment_id="comment_1")

        mock_answer_result = SimpleNamespace(
            answer="Answer",
            answer_confidence=0.9,
            answer_quality_score=85,
            input_tokens=100,
            output_tokens=50,
            processing_time_ms=1000,
        )

        # Mock services
        mock_qa_service = MagicMock()
        mock_qa_service.generate_answer = AsyncMock(return_value=mock_answer_result)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_answer_repo.create_for_comment = AsyncMock(return_value=answer_record)

        # Mock session that fails on commit
        mock_session = MagicMock()
        mock_session.commit = AsyncMock(side_effect=Exception("DB commit failed"))
        mock_session.rollback = AsyncMock()

        # Create use case
        use_case = GenerateAnswerUseCase(
            session=mock_session,
            qa_service=mock_qa_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            await use_case.execute(comment_id="comment_1", retry_count=0)

        assert "DB commit failed" in str(exc_info.value)
        mock_session.rollback.assert_awaited_once()

    async def test_execute_db_commit_fails_after_error(self, db_session, comment_factory):
        """Test handling when database commit fails after service error."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1", conversation_id="conv_1")

        from core.models.question_answer import QuestionAnswer
        answer_record = QuestionAnswer(comment_id="comment_1", max_retries=TASK_MAX_RETRIES)

        # Mock services - raises exception
        mock_qa_service = MagicMock()
        mock_qa_service.generate_answer = AsyncMock(side_effect=Exception("Service error"))

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_answer_repo.create_for_comment = AsyncMock(return_value=answer_record)

        # Mock session that fails on commit
        mock_session = MagicMock()
        mock_session.commit = AsyncMock(side_effect=Exception("DB commit failed"))
        mock_session.rollback = AsyncMock()

        # Create use case
        use_case = GenerateAnswerUseCase(
            session=mock_session,
            qa_service=mock_qa_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            await use_case.execute(comment_id="comment_1", retry_count=0)

        assert "DB commit failed" in str(exc_info.value)
        mock_session.rollback.assert_awaited_once()

    async def test_execute_retry_count_zero(self, db_session, comment_factory):
        """Test that retry_count=0 means first attempt."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1", conversation_id="conv_1")

        from core.models.question_answer import QuestionAnswer
        answer_record = QuestionAnswer(comment_id="comment_1")

        mock_answer_result = SimpleNamespace(
            answer="Answer",
            answer_confidence=0.9,
            answer_quality_score=85,
            input_tokens=100,
            output_tokens=50,
            processing_time_ms=1000,
        )

        # Mock services
        mock_qa_service = MagicMock()
        mock_qa_service.generate_answer = AsyncMock(return_value=mock_answer_result)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_answer_repo.create_for_comment = AsyncMock(return_value=answer_record)

        # Create use case
        use_case = GenerateAnswerUseCase(
            session=db_session,
            qa_service=mock_qa_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act
        await use_case.execute(comment_id="comment_1", retry_count=0)

        # Assert
        assert answer_record.retry_count == 0
        assert answer_record.processing_status == AnswerStatus.COMPLETED

    async def test_execute_service_exception_at_max_retries_boundary(
        self, db_session, comment_factory
    ):
        """Test that retry_count equal to max_retries results in error status."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1", conversation_id="conv_1")

        from core.models.question_answer import QuestionAnswer
        answer_record = QuestionAnswer(comment_id="comment_1", max_retries=TASK_MAX_RETRIES)

        # Mock services - raises exception
        mock_qa_service = MagicMock()
        mock_qa_service.generate_answer = AsyncMock(side_effect=Exception("API error"))

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_answer_repo.create_for_comment = AsyncMock(return_value=answer_record)

        # Create use case
        use_case = GenerateAnswerUseCase(
            session=db_session,
            qa_service=mock_qa_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act - retry_count = TASK_MAX_RETRIES, which equals max_retries
        result = await use_case.execute(comment_id="comment_1", retry_count=TASK_MAX_RETRIES)

        # Assert - should return error, not retry
        assert result["status"] == "error"
        assert "API error" in result["reason"]
        assert answer_record.processing_status == AnswerStatus.FAILED

    async def test_execute_service_exception_one_less_than_max_retries(
        self, db_session, comment_factory
    ):
        """Test that retry_count < max_retries results in retry status."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1", conversation_id="conv_1")

        from core.models.question_answer import QuestionAnswer
        answer_record = QuestionAnswer(comment_id="comment_1", max_retries=TASK_MAX_RETRIES)

        # Mock services - raises exception
        mock_qa_service = MagicMock()
        mock_qa_service.generate_answer = AsyncMock(side_effect=Exception("Transient error"))

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_answer_repo.create_for_comment = AsyncMock(return_value=answer_record)

        # Create use case
        use_case = GenerateAnswerUseCase(
            session=db_session,
            qa_service=mock_qa_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act - retry_count = TASK_MAX_RETRIES - 1, which is less than max_retries
        result = await use_case.execute(comment_id="comment_1", retry_count=TASK_MAX_RETRIES - 1)

        # Assert - should return retry
        assert result["status"] == "retry"
        assert "Transient error" in result["reason"]
        assert answer_record.processing_status == AnswerStatus.FAILED

    async def test_execute_processing_timestamps_set_correctly(
        self, db_session, comment_factory
    ):
        """Test that processing timestamps are set at the right times."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1", conversation_id="conv_1")

        from core.models.question_answer import QuestionAnswer
        answer_record = QuestionAnswer(comment_id="comment_1")

        mock_answer_result = SimpleNamespace(
            answer="Answer",
            answer_confidence=0.9,
            answer_quality_score=85,
            input_tokens=100,
            output_tokens=50,
            processing_time_ms=1000,
        )

        # Mock services
        mock_qa_service = MagicMock()
        mock_qa_service.generate_answer = AsyncMock(return_value=mock_answer_result)

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_answer_repo.create_for_comment = AsyncMock(return_value=answer_record)

        # Create use case
        use_case = GenerateAnswerUseCase(
            session=db_session,
            qa_service=mock_qa_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act
        await use_case.execute(comment_id="comment_1", retry_count=0)

        # Assert
        assert answer_record.processing_started_at is not None
        assert answer_record.processing_completed_at is not None
        # Started should be before or equal to completed
        assert answer_record.processing_started_at <= answer_record.processing_completed_at

    async def test_execute_service_exception_updates_timestamps_and_error(
        self, db_session, comment_factory
    ):
        """Test that error information is captured when service fails."""
        # Arrange
        comment = await comment_factory(comment_id="comment_1", conversation_id="conv_1")

        from core.models.question_answer import QuestionAnswer
        answer_record = QuestionAnswer(comment_id="comment_1", max_retries=1)

        # Mock services - raises exception
        mock_qa_service = MagicMock()
        mock_qa_service.generate_answer = AsyncMock(
            side_effect=Exception("OpenAI API rate limit exceeded")
        )

        # Mock repositories
        mock_comment_repo = MagicMock()
        mock_comment_repo.get_with_classification = AsyncMock(return_value=comment)

        mock_answer_repo = MagicMock()
        mock_answer_repo.get_by_comment_id = AsyncMock(return_value=None)
        mock_answer_repo.create_for_comment = AsyncMock(return_value=answer_record)

        # Create use case
        use_case = GenerateAnswerUseCase(
            session=db_session,
            qa_service=mock_qa_service,
            comment_repository_factory=lambda session: mock_comment_repo,
            answer_repository_factory=lambda session: mock_answer_repo,
        )

        # Act
        result = await use_case.execute(comment_id="comment_1", retry_count=0)

        # Assert
        assert result["status"] == "retry"
        assert answer_record.processing_started_at is not None
        assert answer_record.last_error == "OpenAI API rate limit exceeded"
        assert answer_record.processing_status == AnswerStatus.FAILED
