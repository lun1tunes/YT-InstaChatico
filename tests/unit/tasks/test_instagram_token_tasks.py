from datetime import datetime, timedelta, timezone
import pytest

from core.tasks.instagram_token_tasks import (
    TOKEN_EXPIRY_WARNING_DAYS,
    check_instagram_token_expiration_task,
)


class StubInstagramService:
    def __init__(self, result, should_raise: bool = False):
        self.result = result
        self.should_raise = should_raise

    async def get_token_expiration(self):
        if self.should_raise:
            raise RuntimeError("network failure")
        return self.result

    async def set_media_comment_status(self, media_id: str, enabled: bool):
        return {"success": True, "media_id": media_id, "is_comment_enabled": enabled}


class StubAlertService:
    def __init__(self):
        self.messages = []

    async def send_log_alert(self, payload):
        self.messages.append(payload)


class StubContainer:
    def __init__(self, instagram_result, should_raise=False):
        self.instagram_stub = StubInstagramService(instagram_result, should_raise=should_raise)
        self.alert_stub = StubAlertService()

    def instagram_service(self):
        return self.instagram_stub

    def log_alert_service(self):
        return self.alert_stub


@pytest.mark.unit
class TestInstagramTokenTask:
    def test_alert_sent_when_token_near_expiration(self, monkeypatch):
        expires_at = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRY_WARNING_DAYS - 1)
        seconds_remaining = int((expires_at - datetime.now(timezone.utc)).total_seconds())
        container = StubContainer(
            {
                "success": True,
                "expires_at": expires_at,
                "expires_in": seconds_remaining,
                "status_code": 200,
            }
        )
        monkeypatch.setattr("core.tasks.instagram_token_tasks.get_container", lambda: container)

        result = check_instagram_token_expiration_task()

        assert result["status"] == "ok"
        assert result["alert_sent"] is True
        assert len(container.alert_stub.messages) == 1
        message = container.alert_stub.messages[0]["message"]
        assert "expires in approximately" in message

    def test_no_alert_when_token_far_from_expiration(self, monkeypatch):
        expires_at = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRY_WARNING_DAYS + 10)
        seconds_remaining = int((expires_at - datetime.now(timezone.utc)).total_seconds())
        container = StubContainer(
            {
                "success": True,
                "expires_at": expires_at,
                "expires_in": seconds_remaining,
                "status_code": 200,
            }
        )
        monkeypatch.setattr("core.tasks.instagram_token_tasks.get_container", lambda: container)

        result = check_instagram_token_expiration_task()

        assert result["status"] == "ok"
        assert result["alert_sent"] is False
        assert len(container.alert_stub.messages) == 1
        assert container.alert_stub.messages[0]["level"] == "INFO"

    def test_error_alert_when_fetch_fails(self, monkeypatch):
        container = StubContainer(None, should_raise=True)
        monkeypatch.setattr("core.tasks.instagram_token_tasks.get_container", lambda: container)

        result = check_instagram_token_expiration_task()

        assert result["status"] == "error"
        assert len(container.alert_stub.messages) == 1
        assert container.alert_stub.messages[0]["level"] == "ERROR"

    def test_error_alert_when_service_returns_failure(self, monkeypatch):
        container = StubContainer(
            {
                "success": False,
                "error": {"message": "invalid"},
                "status_code": 400,
            }
        )
        monkeypatch.setattr("core.tasks.instagram_token_tasks.get_container", lambda: container)

        result = check_instagram_token_expiration_task()

        assert result["status"] == "error"
        assert len(container.alert_stub.messages) == 1
        assert container.alert_stub.messages[0]["level"] == "WARNING"
