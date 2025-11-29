"""
Unit tests for CommentClassificationService.
"""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from core.services.classification_service import CommentClassificationService


class DummySession:
    async def add_items(self, items):
        self.items = items


class DummySessionService:
    def __init__(self):
        self.session = DummySession()
        self.messages = False
        self.ensure_context_calls = AsyncMock(side_effect=self._ensure_context_impl)

    def get_session(self, conversation_id: str):
        return self.session

    async def has_messages(self, conversation_id: str) -> bool:
        return self.messages

    async def _ensure_context_impl(self, conversation_id: str, context_items):
        await self.session.add_items(context_items)
        self.messages = True
        return self.session

    async def ensure_context(self, conversation_id: str, context_items):
        return await self.ensure_context_calls(conversation_id, context_items)


def make_service(executor=None, session_service=None):
    if session_service is None:
        session_service = DummySessionService()

    if executor is None:
        class NoOpExecutor:
            async def run(self, *args, **kwargs):
                mock = MagicMock()
                mock.final_output = MagicMock(type="", confidence=0, reasoning="")
                mock.raw_responses = []
                return mock

        executor = NoOpExecutor()

    return CommentClassificationService(
        api_key="test_key",
        agent_executor=executor,
        session_service=session_service,
    )


@pytest.mark.unit
@pytest.mark.service
class TestCommentClassificationService:
    """Test CommentClassificationService methods."""

    async def test_classify_comment_success(self):
        """Test successful comment classification."""
        # Arrange
        mock_result = MagicMock()
        mock_result.final_output.type = "question / inquiry"
        mock_result.final_output.confidence = 95
        mock_result.final_output.reasoning = "Contains question mark"
        mock_result.raw_responses = [MagicMock()]
        mock_result.raw_responses[0].usage.input_tokens = 100
        mock_result.raw_responses[0].usage.output_tokens = 50
        executor = SimpleNamespace(run=AsyncMock(return_value=mock_result))
        session_service = DummySessionService()

        service = make_service(executor=executor, session_service=session_service)

        # Act
        result = await service.classify_comment(
            comment_text="Сколько стоит доставка?",
            conversation_id="conv_123"
        )

        # Assert
        assert result.status == "success"
        assert result.type == "question / inquiry"
        assert result.confidence == 95
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        executor.run.assert_called_once()
        assert session_service.ensure_context_calls.await_count == 0

    async def test_classify_comment_with_media_context(self):
        """Test classification with media context."""
        # Arrange
        mock_result = MagicMock()
        mock_result.final_output.type = "positive"
        mock_result.final_output.confidence = 90
        mock_result.final_output.reasoning = "Positive feedback"
        mock_result.raw_responses = []
        executor = SimpleNamespace(run=AsyncMock(return_value=mock_result))
        session_service = DummySessionService()

        service = make_service(executor=executor, session_service=session_service)
        media_context = {
            "caption": "New product launch!",
            "media_type": "IMAGE",
            "username": "test_user"
        }

        # Act
        result = await service.classify_comment(
            comment_text="Отличный товар!",
            conversation_id="conv_123",
            media_context=media_context
        )

        # Assert
        assert result.status == "success"
        assert result.type == "positive"
        executor.run.assert_called_once()
        assert session_service.ensure_context_calls.await_count == 1

    @pytest.mark.asyncio
    async def test_classify_comment_uses_default_executor(self):
        mock_result = MagicMock()
        mock_result.final_output.type = "neutral"
        mock_result.final_output.confidence = 50
        mock_result.final_output.reasoning = ""
        mock_result.raw_responses = []

        session_service = DummySessionService()
        service = CommentClassificationService(api_key="test_key", session_service=session_service)

        service.agent_executor.run = AsyncMock(return_value=mock_result)

        await service.classify_comment("Test", conversation_id="conv_1", media_context={"caption": "hi"})

        service.agent_executor.run.assert_awaited()
        assert session_service.ensure_context_calls.await_count == 1

    @pytest.mark.asyncio
    async def test_classify_comment_stateless(self):
        mock_result = MagicMock()
        mock_result.final_output.type = "positive"
        mock_result.final_output.confidence = 90
        mock_result.final_output.reasoning = ""
        mock_result.raw_responses = []

        executor = SimpleNamespace(run=AsyncMock(return_value=mock_result))
        session_service = DummySessionService()
        service = make_service(executor=executor, session_service=session_service)

        result = await service.classify_comment("Nice product")

        executor.run.assert_awaited_once()
        assert session_service.ensure_context_calls.await_count == 0
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_classify_comment_truncates_long_input(self):
        long_text = "a" * 2100
        mock_result = MagicMock()
        mock_result.final_output.type = "neutral"
        mock_result.final_output.confidence = 10
        mock_result.final_output.reasoning = ""
        mock_result.raw_responses = []

        executor = SimpleNamespace(run=AsyncMock(return_value=mock_result))
        session_service = DummySessionService()
        service = make_service(executor=executor, session_service=session_service)

        await service.classify_comment(long_text, conversation_id="conv", media_context=None)

        args, kwargs = executor.run.await_args
        assert len(kwargs["input"]) == 2003

    @pytest.mark.asyncio
    async def test_classify_comment_error_path(self):
        executor = SimpleNamespace(run=AsyncMock(side_effect=Exception("boom")))
        session_service = DummySessionService()
        service = make_service(executor=executor, session_service=session_service)

        result = await service.classify_comment("text", conversation_id="conv")

        assert result.status == "error"
        assert result.type == "spam / irrelevant"
        assert result.error == "boom"

    def test_create_media_description_handles_missing_fields(self):
        service = make_service()
        description = service._create_media_description({})
        assert description == ""

        description = service._create_media_description({
            "media_type": "CAROUSEL_ALBUM",
            "children_media_urls": ["u1"],
            "username": "author",
            "is_comment_enabled": False,
        })
        assert "CAROUSEL_ALBUM" in description
        assert "@author" in description
        assert "disabled" in description
        assert "Engagement" not in description
        assert "Post URL" not in description

    def test_create_media_description_truncates_caption_and_metrics(self):
        service = make_service()
        long_caption = "a" * 600
        description = service._create_media_description(
            {
                "media_type": "IMAGE",
                "caption": long_caption,
                "media_url": "http://example.com",
                "comments_count": 7,
                "like_count": 15,
                "is_comment_enabled": True,
                "permalink": "http://permalink",
            }
        )

        assert "Post Type: IMAGE" in description
        assert long_caption[:500] in description
        assert long_caption[:500] + "..." in description
        assert "Media URL: http://example.com" in description
        assert "7 comments" in description
        assert "15 likes" in description
        assert "Comments: enabled" in description
        assert "Post URL: http://permalink" in description

    def test_format_input_with_context_includes_media_analysis(self):
        service = make_service()
        formatted = service._format_input_with_context(
            "Nice!",
            conversation_id="conv123",
            media_context={
                "caption": "short",
                "media_type": "IMAGE",
                "media_context": "analysis text",
                "username": "user",
                "comments_count": 4,
                "like_count": 9,
            },
        )

        assert "Media context:" in formatted
        assert "Image analysis: analysis text" in formatted
        assert "Post has 4 comments" in formatted
        assert "Post has 9 likes" in formatted
        assert "Conversation ID: conv123" in formatted

    @pytest.mark.asyncio
    async def test_classify_comment_no_usage_data(self):
        mock_result = MagicMock()
        mock_result.final_output.type = "neutral"
        mock_result.final_output.confidence = 42
        mock_result.final_output.reasoning = ""
        mock_result.raw_responses = [SimpleNamespace(usage=None)]

        executor = SimpleNamespace(run=AsyncMock(return_value=mock_result))
        session_service = DummySessionService()
        service = make_service(executor=executor, session_service=session_service)

        result = await service.classify_comment("Test", conversation_id="conv")

        assert result.status == "success"

    async def test_classify_comment_error_handling(self):
        """Test error handling when API fails."""
        # Arrange
        executor = SimpleNamespace(run=AsyncMock(side_effect=Exception("API Error")))
        session_service = DummySessionService()
        service = make_service(executor=executor, session_service=session_service)

        # Act
        result = await service.classify_comment(comment_text="Test comment")

        # Assert
        assert result.status == "error"
        assert result.type == "spam / irrelevant"  # Fallback
        assert result.confidence == 0

    def test_generate_conversation_id_top_level(self):
        """Test conversation ID generation for top-level comment."""
        # Arrange
        service = make_service()

        # Act
        conv_id = service.generate_conversation_id("comment_123")

        # Assert
        assert conv_id == "first_question_comment_comment_123"

    def test_generate_conversation_id_reply(self):
        """Test conversation ID generation for reply comment."""
        # Arrange
        service = make_service()

        # Act
        conv_id = service.generate_conversation_id("comment_456", parent_id="comment_123")

        # Assert
        assert conv_id == "first_question_comment_comment_123"

    def test_create_media_description_simple(self):
        """Test media description formatting."""
        # Arrange
        service = make_service()
        media_context = {
            "media_type": "IMAGE",
            "username": "test_user",
            "caption": "Test caption"
        }

        # Act
        description = service._create_media_description(media_context)

        # Assert
        assert "IMAGE" in description
        assert "@test_user" in description
        assert "Test caption" in description

    def test_create_media_description_carousel(self):
        """Test media description for carousel posts."""
        # Arrange
        service = make_service()
        media_context = {
            "media_type": "CAROUSEL_ALBUM",
            "children_media_urls": ["url1", "url2", "url3"],
            "username": "test_user"
        }

        # Act
        description = service._create_media_description(media_context)

        # Assert
        assert "CAROUSEL_ALBUM" in description
        assert "3 изображений" in description
        assert "@test_user" in description
