"""
Unit tests for TelegramAlertService.
"""

import pytest
import aiohttp
from unittest.mock import AsyncMock, patch, MagicMock

from core.services.telegram_alert_service import TelegramAlertService, get_telegram_service


@pytest.mark.unit
@pytest.mark.service
class TestTelegramAlertService:
    """Test TelegramAlertService methods."""

    async def test_send_urgent_issue_notification_success(self):
        """Test sending urgent issue notification."""
        # Arrange
        service = TelegramAlertService(bot_token="test_token", chat_id="test_chat")
        service._send_message = AsyncMock(return_value={
            "ok": True,
            "result": {"message_id": 123}
        })

        comment_data = {
            "comment_id": "comment_123",
            "comment_text": "Urgent problem!",
            "classification": "urgent issue / complaint",
            "confidence": 95,
            "reasoning": "Contains urgent complaint",
            "media_id": "media_123",
            "username": "user123",
            "timestamp": "2025-01-01 12:00:00"
        }

        # Act
        result = await service.send_urgent_issue_notification(comment_data)

        # Assert
        assert result["success"] is True
        assert result["message_id"] == 123
        service._send_message.assert_called_once()

    async def test_send_critical_feedback_notification(self):
        """Test sending critical feedback notification."""
        # Arrange
        service = TelegramAlertService(bot_token="test_token", chat_id="test_chat")
        service._send_message = AsyncMock(return_value={
            "ok": True,
            "result": {"message_id": 456}
        })

        comment_data = {
            "comment_id": "comment_456",
            "comment_text": "Critical feedback",
            "classification": "critical feedback",
            "confidence": 90,
            "reasoning": "Important feedback",
            "media_id": "media_456",
            "username": "user456",
            "timestamp": "2025-01-01 12:00:00"
        }

        # Act
        result = await service.send_critical_feedback_notification(comment_data)

        # Assert
        assert result["success"] is True
        assert result["message_id"] == 456

    @patch("core.services.telegram_alert_service.settings")
    async def test_send_notification_missing_config(self, mock_settings):
        """Test notification fails with missing configuration."""
        # Arrange
        mock_settings.telegram.bot_token = None
        mock_settings.telegram.chat_id = None

        service = TelegramAlertService(bot_token=None, chat_id=None)
        comment_data = {"comment_id": "test"}

        # Act
        result = await service.send_urgent_issue_notification(comment_data)

        # Assert
        assert result["success"] is False
        assert "configuration missing" in result["error"].lower()

    async def test_send_notification_api_error(self):
        """Test notification handles API error."""
        # Arrange
        service = TelegramAlertService(bot_token="test_token", chat_id="test_chat")
        service._send_message = AsyncMock(return_value={
            "ok": False,
            "description": "Bad request"
        })

        comment_data = {"comment_id": "test", "comment_text": "Test"}

        # Act
        result = await service.send_urgent_issue_notification(comment_data)

        # Assert
        assert result["success"] is False
        assert "Bad request" in result["error"]

    async def test_send_urgent_issue_notification_exception(self):
        service = TelegramAlertService(bot_token="token", chat_id="chat")
        service._send_message = AsyncMock(side_effect=RuntimeError("err"))

        result = await service.send_urgent_issue_notification({"comment_id": "c"})

        assert result["success"] is False
        assert "err" in result["error"]

    async def test_send_critical_feedback_failure(self):
        service = TelegramAlertService(bot_token="token", chat_id="chat")
        service._send_message = AsyncMock(return_value={"ok": False, "description": "bad"})

        result = await service.send_critical_feedback_notification({"comment_id": "c"})

        assert result["success"] is False
        assert "bad" in result["error"]

    @patch("core.services.telegram_alert_service.settings")
    async def test_send_critical_missing_config(self, mock_settings):
        mock_settings.telegram.bot_token = None
        mock_settings.telegram.chat_id = None

        service = TelegramAlertService(bot_token=None, chat_id=None)
        result = await service.send_critical_feedback_notification({"comment_id": "c"})

        assert result["success"] is False

    def test_escape_html(self):
        """Test HTML escaping."""
        # Arrange
        text_with_html = "<script>alert('test')</script>"

        # Act
        escaped = TelegramAlertService._escape_html(text_with_html)

        # Assert
        assert "&lt;" in escaped
        assert "&gt;" in escaped
        assert "<script>" not in escaped

    def test_prepare_message_data_truncates_long_text(self):
        """Test that long text is truncated."""
        # Arrange
        service = TelegramAlertService(bot_token="test", chat_id="test")
        long_text = "a" * 1500
        comment_data = {
            "comment_text": long_text,
            "reasoning": "b" * 600
        }

        # Act
        result = service._prepare_message_data(comment_data)

        # Assert
        assert len(result["comment_text"]) <= 1000
        assert result["comment_text"].endswith("...")
        assert len(result["reasoning"]) <= 500

    def test_prepare_message_data_preserves_numeric_confidence(self):
        """Numeric confidence should survive HTML escaping."""
        service = TelegramAlertService(bot_token="test", chat_id="test")
        comment_data = {
            "comment_id": 42,
            "comment_text": "Short text",
            "confidence": 88.7,
        }

        result = service._prepare_message_data(comment_data)

        assert result["comment_text"] == "Short text"
        assert isinstance(result["confidence"], float)
        assert result["confidence"] == pytest.approx(88.7)
        assert result["comment_id"] == "42"

    @patch("core.services.telegram_alert_service.aiohttp.ClientSession")
    async def test_send_message_http_failure(self, mock_session_class):
        """_send_message should surface non-200 responses."""
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_response.text = AsyncMock(return_value="server exploded")
        mock_response.json = AsyncMock(return_value={})

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_session_class.return_value = mock_session

        service = TelegramAlertService(bot_token="test_token", chat_id="test_chat")

        result = await service._send_message("Test body")

        assert result["ok"] is False
        assert "HTTP 500" in result["description"]
        mock_session.post.assert_called_once()

    @patch("core.services.telegram_alert_service.aiohttp.ClientSession")
    async def test_send_message_success(self, mock_session_class):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"ok": True})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        service = TelegramAlertService(bot_token="token", chat_id="chat")
        result = await service._send_message("hello")

        assert result == {"ok": True}

    async def test_send_partnership_proposal_notification(self):
        """Test sending partnership proposal notification."""
        # Arrange
        service = TelegramAlertService(bot_token="test_token", chat_id="test_chat")
        service._send_message = AsyncMock(return_value={
            "ok": True,
            "result": {"message_id": 789}
        })

        comment_data = {
            "comment_id": "comment_789",
            "comment_text": "Partnership opportunity",
            "classification": "partnership proposal"
        }

        # Act
        result = await service.send_partnership_proposal_notification(comment_data)

        # Assert
        assert result["success"] is True
        assert result["message_id"] == 789

    async def test_send_partnership_proposal_notification_failure(self):
        service = TelegramAlertService(bot_token="token", chat_id="chat")
        service._send_message = AsyncMock(return_value={
            "ok": False,
            "description": "oops"
        })

        result = await service.send_partnership_proposal_notification({"comment_id": "c"})

        assert result["success"] is False
        assert "oops" in result["error"]

    async def test_send_log_alert(self):
        """Test sending log alert."""
        # Arrange
        service = TelegramAlertService(bot_token="test_token", chat_id="test_chat")
        service._send_message = AsyncMock(return_value={"ok": True, "result": {}})

        log_data = {
            "level": "ERROR",
            "message": "Test error",
            "logger": "test_logger",
            "trace_id": "trace_123"
        }

        # Act
        result = await service.send_log_alert(log_data)

        # Assert
        assert result["ok"] is True

    async def test_send_notification_routes_by_classification(self):
        """Test that send_notification routes to correct handler."""
        # Arrange
        service = TelegramAlertService(bot_token="test", chat_id="test")

        # Mock the specific handlers
        service.send_urgent_issue_notification = AsyncMock(return_value={"success": True})
        service.send_critical_feedback_notification = AsyncMock(return_value={"success": True})
        service.send_partnership_proposal_notification = AsyncMock(return_value={"success": True})
        service.send_toxic_abusive_notification = AsyncMock(return_value={"success": True})

        # Act & Assert - urgent issue
        await service.send_notification({"classification": "urgent issue / complaint"})
        service.send_urgent_issue_notification.assert_called_once()

        # Act & Assert - critical feedback
        await service.send_notification({"classification": "critical feedback"})
        service.send_critical_feedback_notification.assert_called_once()

        # Act & Assert - partnership
        await service.send_notification({"classification": "partnership proposal"})
        service.send_partnership_proposal_notification.assert_called_once()

        # Act & Assert - toxic
        await service.send_notification({"classification": "toxic / abusive"})
        service.send_toxic_abusive_notification.assert_called_once()

        # Unknown classification returns error
        result = await service.send_notification({"classification": "other"})
        assert result["success"] is False
        assert "No notification configured" in result["error"]

    @patch("core.services.telegram_alert_service.settings")
    async def test_send_log_alert_missing_configuration(self, mock_settings):
        """send_log_alert should fail gracefully when config absent."""
        mock_settings.telegram.bot_token = None
        mock_settings.telegram.chat_id = None
        service = TelegramAlertService(bot_token=None, chat_id=None)
        result = await service.send_log_alert({"level": "ERROR", "message": "boom"})
        assert result["success"] is False

    async def test_send_log_alert_handles_exception(self):
        service = TelegramAlertService(bot_token="token", chat_id="chat")
        service._send_message = AsyncMock(side_effect=Exception("fail"))

        result = await service.send_log_alert({"level": "ERROR", "message": "oops"})

        assert result["success"] is False
        assert "fail" in result["error"]

    async def test_send_notification_unknown_classification(self):
        """Test that send_notification handles unknown classification."""
        # Arrange
        service = TelegramAlertService(bot_token="test", chat_id="test")

        # Act
        result = await service.send_notification({"classification": "unknown type"})

        # Assert
        assert result["success"] is False
        assert "No notification configured" in result["error"]

    async def test_send_notification_missing_classification(self):
        service = TelegramAlertService(bot_token="test", chat_id="test")

        result = await service.send_notification({})

        assert result["success"] is False
        assert "No notification configured" in result["error"]

    async def test_send_toxic_abusive_notification(self):
        """Test sending toxic/abusive notification."""
        # Arrange
        service = TelegramAlertService(bot_token="test_token", chat_id="test_chat")
        service._send_message = AsyncMock(return_value={
            "ok": True,
            "result": {"message_id": 999}
        })

        comment_data = {
            "comment_id": "comment_999",
            "comment_text": "Abusive content",
            "classification": "toxic / abusive",
            "confidence": 98,
            "reasoning": "Contains toxic language",
            "media_id": "media_999",
            "username": "user999",
            "timestamp": "2025-01-01 12:00:00"
        }

        # Act
        result = await service.send_toxic_abusive_notification(comment_data)

        # Assert
        assert result["success"] is True
        assert result["message_id"] == 999

    async def test_send_toxic_abusive_notification_failure(self):
        service = TelegramAlertService(bot_token="test_token", chat_id="test_chat")
        service._send_message = AsyncMock(return_value={
            "ok": False,
            "description": "rate limited"
        })

        result = await service.send_toxic_abusive_notification({"comment_id": "c1"})

        assert result["success"] is False
        assert "rate limited" in result["error"]

    async def test_send_log_alert_truncates_html(self):
        service = TelegramAlertService(bot_token="token", chat_id="chat")
        captured = {}

        async def capture(message, parse_mode="HTML"):
            captured["message"] = message
            captured["parse_mode"] = parse_mode
            return {"ok": True}

        service._send_message = AsyncMock(side_effect=capture)

        long_msg = "a" * 5000
        long_exc = "b" * 5000
        log_data = {
            "level": "ERROR",
            "message": long_msg,
            "exception": long_exc,
            "logger": "logger",
            "trace_id": "trace",
            "timestamp": "now",
        }

        result = await service.send_log_alert(log_data)

        assert result["ok"] is True
        assert captured["parse_mode"] == "HTML"
        payload = captured["message"]
        assert "a" * 2000 in payload
        assert "a" * 2500 not in payload
        assert "b" * 1500 in payload
        assert "b" * 2000 not in payload
        assert payload.count("...") >= 2

    @patch("core.services.telegram_alert_service.settings")
    def test_thread_id_selection(self, mock_settings):
        mock_settings.telegram.bot_token = "token"
        mock_settings.telegram.chat_id = "chat"
        mock_settings.telegram.tg_chat_alerts_thread_id = 101
        mock_settings.telegram.tg_chat_logs_thread_id = 202

        alerts = TelegramAlertService(alert_type="instagram_comment_alerts")
        logs = TelegramAlertService(alert_type="app_logs")
        misc = TelegramAlertService(alert_type="other")

        assert alerts.thread_id == 101
        assert logs.thread_id == 202
        assert misc.thread_id is None

    async def test_send_critical_notification_exception(self):
        service = TelegramAlertService(bot_token="token", chat_id="chat")
        service._send_message = AsyncMock(side_effect=Exception("oops"))

        result = await service.send_critical_feedback_notification({"comment_id": "c"})

        assert result["success"] is False
        assert "oops" in result["error"]

    async def test_send_partnership_exception(self):
        service = TelegramAlertService(bot_token="token", chat_id="chat")
        service._send_message = AsyncMock(side_effect=Exception("fail"))

        result = await service.send_partnership_proposal_notification({"comment_id": "c"})

        assert result["success"] is False
        assert "fail" in result["error"]

    async def test_send_toxic_notification_exception(self):
        service = TelegramAlertService(bot_token="token", chat_id="chat")
        service._send_message = AsyncMock(side_effect=Exception("bad"))

        result = await service.send_toxic_abusive_notification({"comment_id": "c"})

        assert result["success"] is False
        assert "bad" in result["error"]

    @patch("core.services.telegram_alert_service.settings")
    async def test_send_partnership_missing_config(self, mock_settings):
        mock_settings.telegram.bot_token = None
        mock_settings.telegram.chat_id = None

        service = TelegramAlertService(bot_token=None, chat_id=None)
        result = await service.send_partnership_proposal_notification({"comment_id": "c"})

        assert result["success"] is False

    @patch("core.services.telegram_alert_service.settings")
    async def test_send_toxic_missing_config(self, mock_settings):
        mock_settings.telegram.bot_token = None
        mock_settings.telegram.chat_id = None

        service = TelegramAlertService(bot_token=None, chat_id=None)
        result = await service.send_toxic_abusive_notification({"comment_id": "c"})

        assert result["success"] is False

    @patch("core.services.telegram_alert_service.aiohttp.ClientSession")
    async def test_send_message_client_error(self, mock_session_class):
        failing_context = AsyncMock()
        failing_context.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("network"))
        failing_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=failing_context)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        service = TelegramAlertService(bot_token="token", chat_id="chat")
        result = await service._send_message("hello")

        assert result["ok"] is False
        assert "network" in result["description"]

    @patch("core.services.telegram_alert_service.aiohttp.ClientSession")
    async def test_send_message_unexpected_exception(self, mock_session_class):
        failing_context = AsyncMock()
        failing_context.__aenter__ = AsyncMock(side_effect=RuntimeError("unexpected"))
        failing_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=failing_context)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        service = TelegramAlertService(bot_token="token", chat_id="chat")
        result = await service._send_message("hello")

        assert result["ok"] is False
        assert "unexpected" in result["description"]

    @patch("core.services.telegram_alert_service.aiohttp.ClientSession")
    async def test_test_connection_success(self, mock_session_class):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"ok": True, "result": {"id": 1}})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        service = TelegramAlertService(bot_token="token", chat_id="chat")
        result = await service.test_connection()

        assert result["success"] is True
        assert result["bot_info"] == {"id": 1}

    @patch("core.services.telegram_alert_service.aiohttp.ClientSession")
    async def test_test_connection_non_ok_payload(self, mock_session_class):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"ok": False, "description": "bad"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        service = TelegramAlertService(bot_token="token", chat_id="chat")
        result = await service.test_connection()

        assert result["success"] is False
        assert "bad" in result["error"]

    @patch("core.services.telegram_alert_service.aiohttp.ClientSession")
    async def test_test_connection_http_error(self, mock_session_class):
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="fail")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        service = TelegramAlertService(bot_token="token", chat_id="chat")
        result = await service.test_connection()

        assert result["success"] is False
        assert result["error"] == "HTTP 500: fail"

    @patch("core.services.telegram_alert_service.settings")
    async def test_test_connection_missing_config(self, mock_settings):
        mock_settings.telegram.bot_token = None
        mock_settings.telegram.chat_id = None

        service = TelegramAlertService(bot_token=None, chat_id=None)
        result = await service.test_connection()
        assert result["success"] is False

    @patch("core.services.telegram_alert_service.aiohttp.ClientSession")
    async def test_test_connection_exception(self, mock_session_class):
        failing_context = AsyncMock()
        failing_context.__aenter__ = AsyncMock(side_effect=Exception("boom"))
        failing_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=failing_context)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session_class.return_value = mock_session

        service = TelegramAlertService(bot_token="token", chat_id="chat")
        result = await service.test_connection()

        assert result["success"] is False
        assert "boom" in result["error"]

    def test_get_telegram_service_factory(self):
        service = get_telegram_service()
        assert isinstance(service, TelegramAlertService)
