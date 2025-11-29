"""Unit-style tests for comment webhook views."""

from datetime import datetime
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api_v1.comment_webhooks.views import router as webhooks_router
from core.config import settings
from core.models import db_helper
from core.dependencies import (
    get_process_webhook_comment_use_case,
    get_test_comment_processing_use_case,
    get_answer_repository,
    get_task_queue,
)


class StubProcessWebhookUseCase:
    def __init__(self, result=None, error: Exception | None = None):
        self._result = result or {"status": "created", "should_classify": False}
        self._error = error
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return self._result


class StubAnswerRepository:
    def __init__(self, reply_map=None):
        self.reply_map = reply_map or {}
        self.calls = []

    async def get_by_reply_id(self, reply_id: str):
        self.calls.append(reply_id)
        return self.reply_map.get(reply_id)


class StubTaskQueue:
    def __init__(self):
        self.enqueued = []

    def enqueue(self, task_name: str, *args, **kwargs):
        self.enqueued.append((task_name, args, kwargs))
        return f"task-{len(self.enqueued)}"


class StubTestCommentUseCase:
    def __init__(self, result=None):
        self._result = result or {
            "status": "success",
            "classification": "positive feedback",
            "answer": "Thanks!",
            "processing_details": {"step": "done"},
        }
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return self._result


@pytest.fixture
def make_client(monkeypatch):
    def _create():
        app = FastAPI()
        app.include_router(webhooks_router, prefix="/webhook")
        client = TestClient(app)
        monkeypatch.setattr(settings, "app_webhook_verify_token", "test-token", raising=False)
        return app, client

    return _create


def _build_payload(comment_id: str = "comment-1", username: str = "user1"):
    now = int(datetime.utcnow().timestamp())
    return {
        "object": "instagram",
        "entry": [
            {
                "id": "entry1",
                "time": now,
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": comment_id,
                            "from": {"id": "user-123", "username": username},
                            "media": {"id": "media-123"},
                            "text": "Great post!",
                            "parent_id": None,
                        },
                    }
                ],
            }
        ],
    }


def test_webhook_verification_success(make_client, monkeypatch):
    app, client = make_client()
    monkeypatch.setattr(settings, "app_webhook_verify_token", "secret", raising=False)

    response = client.get(
        "/webhook/",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "challenge-token",
            "hub.verify_token": "secret",
        },
    )

    assert response.status_code == 200
    assert response.text == "challenge-token"


def test_webhook_verification_invalid_token(make_client, monkeypatch):
    app, client = make_client()
    monkeypatch.setattr(settings, "app_webhook_verify_token", "expected", raising=False)

    response = client.get(
        "/webhook/",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "challenge-token",
            "hub.verify_token": "wrong",
        },
    )

    assert response.status_code == 403


def test_process_webhook_happy_path_enqueues_classification(make_client, monkeypatch):
    app, client = make_client()
    monkeypatch.setattr(settings.instagram, "bot_username", "", raising=False)

    use_case = StubProcessWebhookUseCase({"status": "created", "should_classify": True})
    answer_repo = StubAnswerRepository()
    task_queue = StubTaskQueue()

    app.dependency_overrides[get_process_webhook_comment_use_case] = lambda: use_case
    app.dependency_overrides[get_answer_repository] = lambda: answer_repo
    app.dependency_overrides[get_task_queue] = lambda: task_queue

    response = client.post("/webhook", json=_build_payload())

    assert response.status_code == 200
    assert response.json()["message"] == "Processed 1 new comments, skipped 0"
    assert len(use_case.calls) == 1
    assert task_queue.enqueued == [
        ("core.tasks.classification_tasks.classify_comment_task", ("comment-1",), {})
    ]


def test_process_webhook_skips_bot_comment(make_client, monkeypatch):
    app, client = make_client()
    monkeypatch.setattr(settings.instagram, "bot_username", "bot_user", raising=False)

    use_case = StubProcessWebhookUseCase()
    answer_repo = StubAnswerRepository()
    task_queue = StubTaskQueue()

    app.dependency_overrides[get_process_webhook_comment_use_case] = lambda: use_case
    app.dependency_overrides[get_answer_repository] = lambda: answer_repo
    app.dependency_overrides[get_task_queue] = lambda: task_queue

    payload = _build_payload(comment_id="bot-comment", username="bot_user")
    response = client.post("/webhook", json=payload)

    assert response.status_code == 200
    assert response.json()["message"] == "Processed 0 new comments, skipped 1"
    assert use_case.calls == []
    assert task_queue.enqueued == []


def test_process_webhook_forbidden_media_owner(make_client, monkeypatch):
    app, client = make_client()
    monkeypatch.setattr(settings.instagram, "bot_username", "", raising=False)

    use_case = StubProcessWebhookUseCase({"status": "forbidden", "reason": "owner mismatch"})
    app.dependency_overrides[get_process_webhook_comment_use_case] = lambda: use_case
    app.dependency_overrides[get_answer_repository] = lambda: StubAnswerRepository()
    app.dependency_overrides[get_task_queue] = lambda: StubTaskQueue()

    response = client.post("/webhook", json=_build_payload())

    assert response.status_code == 403
    assert "owner mismatch" in response.json()["detail"]


def test_process_webhook_handles_processing_errors(make_client, monkeypatch):
    app, client = make_client()
    monkeypatch.setattr(settings.instagram, "bot_username", "", raising=False)

    error_use_case = StubProcessWebhookUseCase(error=RuntimeError("boom"))
    task_queue = StubTaskQueue()

    app.dependency_overrides[get_process_webhook_comment_use_case] = lambda: error_use_case
    app.dependency_overrides[get_answer_repository] = lambda: StubAnswerRepository()
    app.dependency_overrides[get_task_queue] = lambda: task_queue

    response = client.post("/webhook", json=_build_payload())

    assert response.status_code == 200
    assert response.json()["message"] == "Processed 0 new comments, skipped 1"
    assert task_queue.enqueued == []


async def _dummy_session():
    class DummySession:
        async def close(self):
            pass

    yield DummySession()


def test_test_endpoint_requires_dev_mode(make_client, monkeypatch):
    app, client = make_client()
    monkeypatch.setenv("DEVELOPMENT_MODE", "false")

    test_use_case = StubTestCommentUseCase()
    app.dependency_overrides[get_test_comment_processing_use_case] = lambda: test_use_case
    app.dependency_overrides[db_helper.scoped_session_dependency] = _dummy_session

    payload = {
        "comment_id": "c-1",
        "media_id": "m-1",
        "user_id": "u-1",
        "username": "tester",
        "text": "Hello",
    }

    response = client.post("/webhook/test", json=payload)

    assert response.status_code == 403
    assert test_use_case.calls == []


def test_test_endpoint_happy_path(make_client, monkeypatch):
    app, client = make_client()
    monkeypatch.setenv("DEVELOPMENT_MODE", "true")

    test_use_case = StubTestCommentUseCase()
    app.dependency_overrides[get_test_comment_processing_use_case] = lambda: test_use_case
    app.dependency_overrides[db_helper.scoped_session_dependency] = _dummy_session

    payload = {
        "comment_id": "c-1",
        "media_id": "m-1",
        "user_id": "u-1",
        "username": "tester",
        "text": "Hello",
    }

    response = client.post("/webhook/test", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["comment_id"] == "c-1"
    assert test_use_case.calls
