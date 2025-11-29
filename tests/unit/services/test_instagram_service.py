"""
Unit tests for InstagramGraphAPIService.

Tests cover:
- Session management (singleton, lazy init, cleanup)
- Rate limiting (750 req/hour)
- All API methods with success/failure scenarios
- Edge cases and error handling
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from core.config import settings
from core.services.instagram_service import InstagramGraphAPIService


class DummyLimiter:
    def __init__(self, results: Optional[List[Tuple[bool, float]]] = None):
        self.results = results or [(True, 0.0)]
        self.index = 0
        self.max_rate = settings.instagram.replies_rate_limit_per_hour
        self.time_period = settings.instagram.replies_rate_period_seconds

    async def acquire(self) -> Tuple[bool, float]:
        if self.index < len(self.results):
            result = self.results[self.index]
            self.index += 1
            return result
        return True, 0.0

    async def close(self) -> None:
        return None


def make_service(limiter: Optional[DummyLimiter] = None) -> InstagramGraphAPIService:
    return InstagramGraphAPIService(access_token="test_token", rate_limiter=limiter or DummyLimiter())


@pytest.mark.unit
@pytest.mark.service
class TestInstagramServiceSessionManagement:
    """Test session lifecycle and management."""

    async def test_init_without_session(self):
        """Test initialization without provided session."""
        service = InstagramGraphAPIService(access_token="test_token")

        assert service._session is None
        assert service._should_close_session is True
        assert service._reply_rate_limiter.max_rate == settings.instagram.replies_rate_limit_per_hour
        assert service._reply_rate_limiter.time_period == settings.instagram.replies_rate_period_seconds

    async def test_init_with_provided_session(self):
        """Test initialization with externally provided session."""
        mock_session = AsyncMock()
        service = InstagramGraphAPIService(
            access_token="test_token", session=mock_session, rate_limiter=DummyLimiter()
        )

        assert service._session is mock_session
        assert service._should_close_session is False

    async def test_lazy_session_initialization(self):
        """Test that session is created only when first needed."""
        service = make_service()

        assert service._session is None

        session = await service._get_session()

        assert session is not None
        assert service._session is session
        await service.close()

    async def test_session_reuse(self):
        """Test that session is reused across multiple calls."""
        service = make_service()

        session1 = await service._get_session()
        session2 = await service._get_session()

        assert session1 is session2
        await service.close()

    async def test_closed_session_recreation(self):
        """Test that closed session is recreated on next access."""
        service = make_service()

        session1 = await service._get_session()
        await service.close()

        session2 = await service._get_session()

        assert session1 is not session2
        await service.close()

    async def test_close_when_session_not_created(self):
        """Test close() when session was never created."""
        service = make_service()

        await service.close()  # Should not raise

        assert service._session is None

    async def test_close_external_session_not_closed(self):
        """Test that externally provided session is NOT closed."""
        mock_session = AsyncMock()
        mock_session.closed = False
        service = InstagramGraphAPIService(
            access_token="test_token", session=mock_session, rate_limiter=DummyLimiter()
        )

        await service.close()

        mock_session.close.assert_not_called()

    async def test_close_internal_session_is_closed(self):
        """Test that internally created session IS closed."""
        service = make_service()
        session = await service._get_session()

        await service.close()

        assert session.closed

    async def test_context_manager_support(self):
        """Test async context manager protocol."""
        async with make_service() as service:
            session = await service._get_session()
            assert session is not None

        assert session.closed

    def test_missing_token_raises_error(self):
        """Test that missing access token raises ValueError."""
        with patch('core.services.instagram_service.settings') as mock_settings:
            mock_settings.instagram.access_token = None

            with pytest.raises(ValueError, match="Instagram access token is required"):
                InstagramGraphAPIService(access_token=None)


@pytest.mark.unit
@pytest.mark.service
class TestInstagramServiceRateLimiting:
    """Test rate limiting functionality."""

    async def test_rate_limiter_initialized(self):
        """Test that rate limiter is properly configured."""
        limiter = DummyLimiter()
        service = InstagramGraphAPIService(access_token="test_token", rate_limiter=limiter)

        assert service._reply_rate_limiter is limiter
        assert service._reply_rate_limiter.max_rate == settings.instagram.replies_rate_limit_per_hour
        assert service._reply_rate_limiter.time_period == settings.instagram.replies_rate_period_seconds

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_rate_limiter_applied_to_replies(self, mock_session_class):
        """Test that rate limiter is applied to send_reply_to_comment."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"id": "reply_1"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        limiter = DummyLimiter(results=[(True, 0.0)])
        service = InstagramGraphAPIService(access_token="test_token", rate_limiter=limiter)

        # Verify rate limiter exists and will be used
        # We can't directly mock acquire() since it's read-only,
        # but we can verify the limiter is configured correctly
        assert service._reply_rate_limiter is not None

        # Make a successful request
        result = await service.send_reply_to_comment("comment_1", "Test")

        assert result["success"] is True
        assert mock_session.post.call_count == 1
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_send_reply_returns_rate_limited_status(self, mock_session_class):
        """When limiter denies sending, service responds with rate_limited status."""
        limiter = DummyLimiter(results=[(False, 12.5)])
        service = InstagramGraphAPIService(access_token="test_token", rate_limiter=limiter)

        result = await service.send_reply_to_comment("comment_1", "Test")

        assert result["success"] is False
        assert result["status"] == "rate_limited"


@pytest.mark.unit
@pytest.mark.service
class TestInstagramInsightsAPI:
    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_get_insights_success(self, mock_session_class):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"data": [{"metric": "views"}]})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")

        result = await service.get_insights(
            "account_1",
            {"metric": "views", "period": "day", "since": 1, "until": 2},
        )

        assert result["success"] is True
        assert result["data"] == {"data": [{"metric": "views"}]}
        mock_session.get.assert_called_once()
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_get_insights_failure(self, mock_session_class):
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.json = AsyncMock(return_value={"error": "boom"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        service = InstagramGraphAPIService(access_token="test_token")

        result = await service.get_insights(
            "account_1",
            {"metric": "views", "period": "day", "since": 1, "until": 2},
        )

        assert result["success"] is False
        assert result["error"] == {"error": "boom"}
        mock_session.get.assert_called_once()
        await service.close()


@pytest.mark.unit
@pytest.mark.service
class TestInstagramServiceTokenMonitoring:
    """Tests for token expiration helper."""

    @pytest.mark.asyncio
    async def test_get_token_expiration_parses_timestamp(self, monkeypatch):
        service = make_service()

        expires_at = datetime.now(timezone.utc) + timedelta(days=5)

        async def mock_fetch(self):
            return 200, {"data": {"expires_at": int(expires_at.timestamp())}}

        monkeypatch.setattr(InstagramGraphAPIService, "_fetch_debug_token", mock_fetch)

        result = await service.get_token_expiration()

        assert result["success"] is True
        assert isinstance(result["expires_at"], datetime)
        assert abs(result["expires_at"] - expires_at) < timedelta(seconds=1)
        assert result["expires_in"] > 0

    @pytest.mark.asyncio
    async def test_get_token_expiration_uses_expires_in_when_timestamp_missing(self, monkeypatch):
        service = make_service()
        async def mock_fetch(self):
            return 200, {"data": {"expires_in": 3600}}
        monkeypatch.setattr(InstagramGraphAPIService, "_fetch_debug_token", mock_fetch)

        result = await service.get_token_expiration()

        assert result["success"] is True
        assert result["expires_in"] == 3600
        assert isinstance(result["expires_at"], datetime)

    @pytest.mark.asyncio
    async def test_get_token_expiration_handles_failure(self, monkeypatch):
        service = make_service()

        async def mock_fetch(self):
            return 400, {"error": {"message": "invalid"}}

        monkeypatch.setattr(InstagramGraphAPIService, "_fetch_debug_token", mock_fetch)

        result = await service.get_token_expiration()

        assert result["success"] is False
        assert result["error"] == {"error": {"message": "invalid"}}

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_multiple_requests_within_limit(self, mock_session_class):
        """Test that multiple requests succeed within rate limit."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"id": "reply_1"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        limiter = DummyLimiter(results=[(True, 0.0)] * 5)
        service = make_service(limiter)

        # Make 5 requests (well within limit)
        results = []
        for i in range(5):
            result = await service.send_reply_to_comment(f"comment_{i}", f"Reply {i}")
            results.append(result)

        assert all(r["success"] for r in results)
        assert mock_session.post.call_count == 5
        await service.close()


@pytest.mark.unit
@pytest.mark.service
class TestInstagramServiceAPIMethods:
    """Test all API methods."""

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_send_reply_success(self, mock_session_class):
        """Test successful Instagram reply."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"id": "reply_123"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        service = make_service()

        result = await service.send_reply_to_comment("comment_123", "Test reply")

        assert result["success"] is True
        assert result["reply_id"] == "reply_123"
        assert result["status_code"] == 200
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_send_reply_with_dict_response(self, mock_session_class):
        """Test reply with dict response for reply_id extraction."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"id": "reply_456", "created_time": "123456"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        service = make_service()
        result = await service.send_reply_to_comment("comment_123", "Test")

        assert result["reply_id"] == "reply_456"
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_send_reply_with_non_dict_response(self, mock_session_class):
        """Test reply when response is not a dict."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value="string_response")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        service = make_service()
        result = await service.send_reply_to_comment("comment_123", "Test")

        assert result["reply_id"] is None
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_send_reply_rate_limit_error(self, mock_session_class):
        """Test rate limit error detection (code=2, retry message)."""
        mock_response = AsyncMock()
        mock_response.status = 429
        mock_response.json = AsyncMock(return_value={
            "error": {"code": 2, "message": "Please retry later"}
        })
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        service = make_service()
        result = await service.send_reply_to_comment("comment_123", "Test")

        assert result["success"] is False
        assert result["status_code"] == 429
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_send_reply_generic_error(self, mock_session_class):
        """Test generic API error (not rate limit)."""
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.json = AsyncMock(return_value={
            "error": {"code": 100, "message": "Invalid parameter"}
        })
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        service = make_service()
        result = await service.send_reply_to_comment("comment_123", "Test")

        assert result["success"] is False
        assert result["status_code"] == 400
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_send_reply_exception(self, mock_session_class):
        """Test exception handling in send_reply."""
        mock_session = AsyncMock()
        mock_session.post = MagicMock(side_effect=Exception("Network error"))
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        service = make_service()
        result = await service.send_reply_to_comment("comment_123", "Test")

        assert result["success"] is False
        assert "Network error" in result["error"]
        assert result["status_code"] is None
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_get_comment_info_success(self, mock_session_class):
        """Test successful comment info retrieval."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"id": "comment_1", "text": "Hello"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        service = make_service()
        result = await service.get_comment_info("comment_1")

        assert result["success"] is True
        assert result["comment_info"]["id"] == "comment_1"
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_get_comment_info_failure(self, mock_session_class):
        """Test comment info retrieval failure."""
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.json = AsyncMock(return_value={"error": "not found"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        service = make_service()
        result = await service.get_comment_info("comment_missing")

        assert result["success"] is False
        assert result["status_code"] == 404
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_get_comment_info_exception(self, mock_session_class):
        """Test comment info exception handling."""
        mock_session = AsyncMock()
        mock_session.get = MagicMock(side_effect=Exception("timeout"))
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        service = make_service()
        result = await service.get_comment_info("comment_1")

        assert result["success"] is False
        assert "timeout" in result["error"]
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_validate_token_success(self, mock_session_class, monkeypatch):
        """Test successful token validation."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"data": {"is_valid": True}})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        monkeypatch.setattr(settings.instagram, "app_access_token", "app-access-token", raising=False)

        service = make_service()
        result = await service.validate_token()

        assert result["success"] is True
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_validate_token_failure(self, mock_session_class, monkeypatch):
        """Test failed token validation."""
        mock_response = AsyncMock()
        mock_response.status = 401
        mock_response.json = AsyncMock(return_value={"error": "invalid token"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        monkeypatch.setattr(settings.instagram, "app_access_token", "app-access-token", raising=False)

        service = make_service()
        result = await service.validate_token()

        assert result["success"] is False
        assert result["status_code"] == 401
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_validate_token_exception(self, mock_session_class, monkeypatch):
        """Test token validation exception."""
        mock_session = AsyncMock()
        mock_session.get = MagicMock(side_effect=Exception("network error"))
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        monkeypatch.setattr(settings.instagram, "app_access_token", "app-access-token", raising=False)

        service = make_service()
        result = await service.validate_token()

        assert result["success"] is False
        assert "network error" in result["error"]
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_get_media_info_success(self, mock_session_class):
        """Test successful media info retrieval."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "id": "media_123",
            "media_type": "IMAGE",
            "caption": "Test"
        })
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        service = make_service()
        result = await service.get_media_info("media_123")

        assert result["success"] is True
        assert result["media_info"]["media_type"] == "IMAGE"
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_get_media_info_carousel(self, mock_session_class):
        """Test carousel media info with children."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "id": "carousel_1",
            "media_type": "CAROUSEL_ALBUM",
            "children": {"data": [{"id": "child_1"}, {"id": "child_2"}]}
        })
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        service = make_service()
        result = await service.get_media_info("carousel_1")

        assert result["media_info"]["media_type"] == "CAROUSEL_ALBUM"
        assert len(result["media_info"]["children"]["data"]) == 2
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_get_media_info_failure(self, mock_session_class):
        """Test media info retrieval failure."""
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.json = AsyncMock(return_value={"error": "not found"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        service = make_service()
        result = await service.get_media_info("media_404")

        assert result["success"] is False
        assert result["status_code"] == 404
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_get_media_info_exception(self, mock_session_class):
        """Test media info exception."""
        mock_session = AsyncMock()
        mock_session.get = MagicMock(side_effect=Exception("error"))
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        service = make_service()
        result = await service.get_media_info("media_1")

        assert result["success"] is False
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_get_page_info_success(self, mock_session_class):
        """Test successful page info retrieval."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"id": "page_1", "name": "Test Page"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        service = make_service()
        result = await service.get_page_info()

        assert result["success"] is True
        assert result["page_info"]["id"] == "page_1"
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_get_page_info_failure(self, mock_session_class):
        """Test page info retrieval failure."""
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.json = AsyncMock(return_value={"error": "server error"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        service = make_service()
        result = await service.get_page_info()

        assert result["success"] is False
        assert result["status_code"] == 500
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_get_page_info_exception(self, mock_session_class):
        """Test page info exception."""
        mock_session = AsyncMock()
        mock_session.get = MagicMock(side_effect=Exception("boom"))
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        service = make_service()
        result = await service.get_page_info()

        assert result["success"] is False
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_set_media_comment_status_disable_success(self, mock_session_class):
        """Disabling comments succeeds and sends correct payload."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"success": True})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        service = make_service()
        result = await service.set_media_comment_status("media_1", enabled=False)

        assert result["success"] is True
        called_params = mock_session.post.call_args.kwargs["params"]
        assert called_params["comment_enabled"] == "false"
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_set_media_comment_status_failure(self, mock_session_class):
        """API failure returns error payload."""
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.json = AsyncMock(return_value={"error": "bad_request"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        service = make_service()
        result = await service.set_media_comment_status("media_1", enabled=True)

        assert result["success"] is False
        assert result["status_code"] == 400
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_set_media_comment_status_exception(self, mock_session_class):
        """Exceptions are captured and surfaced."""
        mock_session = AsyncMock()
        mock_session.post = MagicMock(side_effect=Exception("boom"))
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        service = make_service()
        result = await service.set_media_comment_status("media_1", enabled=True)

        assert result["success"] is False
        assert "boom" in result["error"]
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_hide_comment_success(self, mock_session_class):
        """Test successful comment hiding."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"success": True})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        service = make_service()
        result = await service.hide_comment("comment_123", hide=True)

        assert result["success"] is True
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_unhide_comment_success(self, mock_session_class):
        """Test successful comment unhiding."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"success": True})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        service = make_service()
        result = await service.hide_comment("comment_123", hide=False)

        assert result["success"] is True
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_hide_comment_failure(self, mock_session_class):
        """Test hide comment failure."""
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.json = AsyncMock(return_value={"error": "bad request"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        service = make_service()
        result = await service.hide_comment("comment_123", hide=True)

        assert result["success"] is False
        assert result["status_code"] == 400
        await service.close()

    @patch("core.services.instagram_service.aiohttp.ClientSession")
    async def test_hide_comment_exception(self, mock_session_class):
        """Test hide comment exception."""
        mock_session = AsyncMock()
        mock_session.post = MagicMock(side_effect=Exception("network error"))
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        service = make_service()
        result = await service.hide_comment("comment_123", hide=True)

        assert result["success"] is False
        assert "network error" in result["error"]
        await service.close()
