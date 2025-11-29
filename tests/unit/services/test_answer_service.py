"""
Unit tests for QuestionAnswerService.
"""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from core.services.answer_service import QuestionAnswerService


class DummySession:
    async def add_items(self, items):
        self.items = items


class DummySessionService:
    def __init__(self):
        self.session = DummySession()
        self.messages = False

    def get_session(self, conversation_id: str):
        return self.session

    async def has_messages(self, conversation_id: str) -> bool:
        return self.messages

    async def ensure_context(self, conversation_id: str, context_items):
        return self.session


@pytest.mark.unit
@pytest.mark.service
class TestQuestionAnswerService:
    """Test QuestionAnswerService methods."""

    @patch("core.services.answer_service.time.time")
    async def test_generate_answer_success(self, mock_time):
        """Test successful answer generation."""
        # Arrange
        # Mock time to simulate 100ms processing time
        mock_time.side_effect = [1000.0, 1000.1]  # Start and end times

        mock_result = MagicMock()
        mock_result.final_output.answer = "Доставка стоит 300 рублей"
        mock_result.final_output.confidence = 0.95
        mock_result.final_output.quality_score = 85
        mock_result.raw_responses = [MagicMock()]
        mock_result.raw_responses[0].usage.input_tokens = 200
        mock_result.raw_responses[0].usage.output_tokens = 150
        executor = SimpleNamespace(run=AsyncMock(return_value=mock_result))
        session_service = DummySessionService()

        service = QuestionAnswerService(
            api_key="test_key",
            agent_executor=executor,
            session_service=session_service,
        )

        # Act
        result = await service.generate_answer(
            question_text="Сколько стоит доставка?",
            username="test_user"
        )

        # Assert
        assert result.status == "success"
        assert result.answer == "Доставка стоит 300 рублей"
        assert result.input_tokens == 200
        assert result.output_tokens == 150
        assert result.processing_time_ms == 100  # 1000.1 - 1000.0 = 0.1s = 100ms

    async def test_generate_answer_with_username_attribution(self):
        """Test that username is added to question text."""
        # Arrange
        mock_result = MagicMock()
        mock_result.final_output.answer = "Answer"
        mock_result.final_output.confidence = 0.80
        mock_result.final_output.quality_score = 70
        mock_result.raw_responses = []
        executor = SimpleNamespace(run=AsyncMock(return_value=mock_result))
        session_service = DummySessionService()

        service = QuestionAnswerService(
            api_key="test_key",
            agent_executor=executor,
            session_service=session_service,
        )

        # Act
        await service.generate_answer(
            question_text="Test question",
            username="john_doe"
        )

        # Assert
        call_args = executor.run.call_args
        input_text = call_args.kwargs.get("input") or call_args.args[1]
        assert "@john_doe:" in input_text

    async def test_generate_answer_truncates_long_text(self):
        """Test that long questions are truncated to 1000 chars."""
        # Arrange
        mock_result = MagicMock()
        mock_result.final_output.answer = "Answer"
        mock_result.final_output.confidence = 0.80
        mock_result.final_output.quality_score = 70
        mock_result.raw_responses = []
        executor = SimpleNamespace(run=AsyncMock(return_value=mock_result))
        session_service = DummySessionService()

        service = QuestionAnswerService(
            api_key="test_key",
            agent_executor=executor,
            session_service=session_service,
        )
        long_question = "a" * 1500

        # Act
        await service.generate_answer(question_text=long_question)

        # Assert
        call_args = executor.run.call_args
        input_text = call_args.kwargs.get("input") or call_args.args[1]
        assert len(input_text) <= 1003  # 1000 + "..."

    async def test_generate_answer_with_conversation_id(self):
        """Test answer generation with conversation_id uses session."""
        # Arrange
        mock_result = MagicMock()
        mock_result.final_output.answer = "Answer with session"
        mock_result.final_output.confidence = 0.90
        mock_result.final_output.quality_score = 80
        mock_result.raw_responses = []
        executor = SimpleNamespace(run=AsyncMock(return_value=mock_result))
        session_service = DummySessionService()

        service = QuestionAnswerService(
            api_key="test_key",
            agent_executor=executor,
            session_service=session_service,
        )

        # Act
        result = await service.generate_answer(
            question_text="Test question",
            conversation_id="conv_123"
        )

        # Assert
        assert result.status == "success"
        assert result.comment_id == "conv_123"
        # Verify session was passed to Runner.run
        call_args = executor.run.call_args
        assert "session" in call_args.kwargs
        assert session_service.session.items == [
            {"role": "user", "content": "Test question"},
            {"role": "assistant", "content": "Answer with session"},
        ]

    async def test_generate_answer_without_usage_data(self):
        """Test answer generation when raw_responses has no usage data."""
        # Arrange
        mock_result = MagicMock()
        mock_result.final_output.answer = "Answer"
        mock_result.final_output.confidence = 0.85
        mock_result.final_output.quality_score = 75
        # Mock raw_responses with no usage attribute
        mock_response = MagicMock()
        del mock_response.usage  # Remove usage attribute
        mock_result.raw_responses = [mock_response]
        executor = SimpleNamespace(run=AsyncMock(return_value=mock_result))
        session_service = DummySessionService()

        service = QuestionAnswerService(
            api_key="test_key",
            agent_executor=executor,
            session_service=session_service,
        )

        # Act
        result = await service.generate_answer(question_text="Test question")

        # Assert
        assert result.status == "success"
        assert result.input_tokens is None
        assert result.output_tokens is None

    async def test_generate_answer_error_handling(self):
        """Test error handling when answer generation fails."""
        # Arrange
        executor = SimpleNamespace(run=AsyncMock(side_effect=Exception("API Error")))
        session_service = DummySessionService()
        service = QuestionAnswerService(
            api_key="test_key",
            agent_executor=executor,
            session_service=session_service,
        )

        # Act
        result = await service.generate_answer(question_text="Test question")

        # Assert
        assert result.status == "error"
        assert result.error == "API Error"
        assert result.answer is None
        assert result.answer_confidence == 0.0
        assert result.comment_id == "unknown"

    @patch("core.services.agent_executor.AgentExecutor")
    async def test_default_executor_initialization(self, mock_agent_executor):
        """Ensure service falls back to AgentExecutor when not provided."""
        dummy_executor = SimpleNamespace(run=AsyncMock())
        mock_agent_executor.return_value = dummy_executor

        service = QuestionAnswerService(api_key="key", session_service=DummySessionService())

        assert service.agent_executor is dummy_executor
        mock_agent_executor.assert_called_once()
