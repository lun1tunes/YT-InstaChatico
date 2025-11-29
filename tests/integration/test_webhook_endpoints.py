import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from core.config import settings
from core.models import (
    CommentClassification,
    InstagramComment,
    Media,
)
from core.models.comment_classification import ProcessingStatus
from core.utils.time import now_db_utc

from tests.integration.helpers import fetch_classification, fetch_comment


REQUEST_TIMEOUT_SECONDS = 5


async def _with_timeout(awaitable):
    """Ensure HTTPX requests fail fast inside tests."""
    return await asyncio.wait_for(awaitable, timeout=REQUEST_TIMEOUT_SECONDS)


@pytest.mark.asyncio
async def test_webhook_verification_success(integration_environment):
    client: AsyncClient = integration_environment["client"]
    response = await _with_timeout(
        client.get(
            "/api/v1/webhook/",
            params={
                "hub.mode": "subscribe",
                "hub.challenge": "challenge-token",
                "hub.verify_token": "verify_token",
            },
        )
    )
    assert response.status_code == 200, response.json()
    assert response.text == "challenge-token"


@pytest.mark.asyncio
async def test_webhook_verification_invalid_token(integration_environment):
    client: AsyncClient = integration_environment["client"]
    response = await _with_timeout(
        client.get(
            "/api/v1/webhook/",
            params={
                "hub.mode": "subscribe",
                "hub.challenge": "challenge-token",
                "hub.verify_token": "wrong",
            },
        )
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_webhook_missing_signature_rejected(integration_environment):
    client: AsyncClient = integration_environment["client"]
    payload = {"object": "instagram", "entry": []}
    response = await _with_timeout(client.post("/api/v1/webhook/", json=payload))
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webhook_invalid_payload_returns_422(integration_environment, sign_payload):
    client: AsyncClient = integration_environment["client"]
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": "acct",
                "time": 10,
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": "c1",
                            "media": {"id": "m1"},
                            "text": "",
                            "from": {"id": "u1", "username": "user!"},
                        },
                    }
                ],
            }
        ],
    }
    body = json.dumps(payload).encode()
    signature = sign_payload(body)
    response = await client.post(
        "/api/v1/webhook/",
        content=body,
        headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_webhook_process_comment_success(integration_environment, sign_payload):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    task_queue = integration_environment["task_queue"]

    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": "acct",
                "time": int(now_db_utc().timestamp()),
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": "comment_123",
                            "media": {"id": "media_123", "media_product_type": "FEED"},
                            "text": "Test comment",
                            "from": {"id": "user_123", "username": "testuser"},
                        },
                    }
                ],
            }
        ],
    }

    body = json.dumps(payload).encode()
    signature = sign_payload(body)
    response = await _with_timeout(
        client.post(
            "/api/v1/webhook/",
            content=body,
            headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"},
        )
    )

    assert response.status_code == 200, response.json()
    data = response.json()
    assert data["status"] == "success"

    comment = await fetch_comment(session_factory, "comment_123")
    assert comment is not None
    assert comment.media_id == "media_123"
    assert comment.text == "Test comment"

    classification = await fetch_classification(session_factory, "comment_123")
    assert classification is not None
    assert classification.processing_status.name == "PENDING"

    assert any(
        entry["task"] == "core.tasks.classification_tasks.classify_comment_task"
        and entry["args"][0] == "comment_123"
        for entry in task_queue.enqueued
    )


@pytest.mark.asyncio
async def test_webhook_invalid_signature(integration_environment):
    client: AsyncClient = integration_environment["client"]
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": "acct",
                "time": int(now_db_utc().timestamp()),
                "changes": [],
            }
        ],
    }
    body = json.dumps(payload).encode()
    response = await _with_timeout(
        client.post(
            "/api/v1/webhook/",
            content=body,
            headers={"X-Hub-Signature-256": "sha256=deadbeef", "Content-Type": "application/json"},
        )
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webhook_media_owner_mismatch(integration_environment, sign_payload):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_mismatch",
            permalink="https://instagram.com/p/media_mismatch",
            media_type="IMAGE",
            media_url="https://cdn.test/media_mismatch.jpg",
            owner="other_account",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        await session.merge(media)
        await session.commit()
    async with session_factory() as session:
        stored = await session.get(Media, "media_mismatch")
        assert stored is not None
        assert stored.owner == "other_account"
    from core.config import settings
    assert settings.instagram.base_account_id == "acct"

    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": "wrong_acct",
                "time": int(now_db_utc().timestamp()),
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": "comment_forbidden",
                            "media": {"id": "media_mismatch"},
                            "text": "Should be rejected",
                            "from": {"id": "user_1", "username": "tester"},
                        },
                    }
                ],
            }
        ],
    }

    body = json.dumps(payload).encode()
    signature = sign_payload(body)
    response = await _with_timeout(
        client.post(
            "/api/v1/webhook/",
            content=body,
            headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"},
        )
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid webhook account"


@pytest.mark.asyncio
async def test_webhook_existing_comment_triggers_reclassification(integration_environment, sign_payload):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    task_queue = integration_environment["task_queue"]

    comment_id = "existing_comment"
    media_id = "media_existing"

    async with session_factory() as session:
        media = Media(
            id=media_id,
            permalink="https://instagram.com/p/media_existing",
            media_type="IMAGE",
            media_url="https://cdn.test/media_existing.jpg",
            owner="acct",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id=comment_id,
            media_id=media_id,
            user_id="user_existing",
            username="existing_user",
            text="Need follow-up",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.commit()

        classification = CommentClassification(
            comment_id=comment_id,
            processing_status=ProcessingStatus.PENDING,
        )
        session.add(classification)
        await session.commit()

    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": "acct",
                "time": int(now_db_utc().timestamp()),
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": comment_id,
                            "media": {"id": media_id, "media_product_type": "FEED"},
                            "text": "Need follow-up",
                            "from": {"id": "user_existing", "username": "existing_user"},
                        },
                    }
                ],
            }
        ],
    }

    body = json.dumps(payload).encode()
    signature = sign_payload(body)
    response = await _with_timeout(
        client.post(
            "/api/v1/webhook/",
            content=body,
            headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"},
        )
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Processed 0 new comments, skipped 1"
    assert len(task_queue.enqueued) == 1
    assert task_queue.enqueued[0]["task"] == "core.tasks.classification_tasks.classify_comment_task"
    assert task_queue.enqueued[0]["args"] == (comment_id,)

    stored_comment = await fetch_comment(session_factory, comment_id)
    assert stored_comment is not None
    stored_classification = await fetch_classification(session_factory, comment_id)
    assert stored_classification.processing_status == ProcessingStatus.PENDING


@pytest.mark.asyncio
async def test_webhook_existing_comment_completed_skips_reclassification(integration_environment, sign_payload):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    task_queue = integration_environment["task_queue"]

    comment_id = "completed_comment"
    media_id = "media_completed"

    async with session_factory() as session:
        media = Media(
            id=media_id,
            permalink="https://instagram.com/p/media_completed",
            media_type="IMAGE",
            media_url="https://cdn.test/media_completed.jpg",
            owner="acct",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id=comment_id,
            media_id=media_id,
            user_id="user_completed",
            username="already_done",
            text="Thanks already handled",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.commit()

        classification = CommentClassification(
            comment_id=comment_id,
            processing_status=ProcessingStatus.COMPLETED,
        )
        session.add(classification)
        await session.commit()

    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": "acct",
                "time": int(now_db_utc().timestamp()),
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": comment_id,
                            "media": {"id": media_id, "media_product_type": "FEED"},
                            "text": "Thanks already handled",
                            "from": {"id": "user_completed", "username": "already_done"},
                        },
                    }
                ],
            }
        ],
    }

    body = json.dumps(payload).encode()
    signature = sign_payload(body)
    response = await _with_timeout(
        client.post(
            "/api/v1/webhook/",
            content=body,
            headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"},
        )
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Processed 0 new comments, skipped 1"
    assert task_queue.enqueued == []


@pytest.mark.asyncio
async def test_webhook_skips_bot_comment(integration_environment, sign_payload):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    task_queue = integration_environment["task_queue"]

    bot_username = "insta_bot_account"
    previous_bot_username = settings.instagram.bot_username
    settings.instagram.bot_username = bot_username
    try:
        payload = {
            "object": "instagram",
            "entry": [
                {
                    "id": "acct",
                    "time": int(now_db_utc().timestamp()),
                    "changes": [
                        {
                            "field": "comments",
                            "value": {
                                "id": "bot_comment",
                                "media": {"id": "bot_media", "media_product_type": "FEED"},
                                "text": "Auto reply",
                                "from": {"id": "bot_user", "username": bot_username},
                            },
                        }
                    ],
                }
            ],
        }

        body = json.dumps(payload).encode()
        signature = sign_payload(body)
        response = await _with_timeout(
            client.post(
                "/api/v1/webhook/",
                content=body,
                headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"},
            )
        )
    finally:
        settings.instagram.bot_username = previous_bot_username

    assert response.status_code == 200
    assert response.json()["message"] == "Processed 0 new comments, skipped 1"
    assert task_queue.enqueued == []
    assert await fetch_comment(session_factory, "bot_comment") is None


@pytest.mark.asyncio
async def test_webhook_media_creation_failure_skips_comment(integration_environment, sign_payload):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    task_queue = integration_environment["task_queue"]
    media_service = integration_environment["media_service"]

    media_service.get_or_create_media = AsyncMock(return_value=None)

    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": "acct",
                "time": int(now_db_utc().timestamp()),
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": "media_failure_comment",
                            "media": {"id": "media_failure", "media_product_type": "FEED"},
                            "text": "Will fail due to media",
                            "from": {"id": "user_media", "username": "user_media"},
                        },
                    }
                ],
            }
        ],
    }

    body = json.dumps(payload).encode()
    signature = sign_payload(body)
    response = await _with_timeout(
        client.post(
            "/api/v1/webhook/",
            content=body,
            headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"},
        )
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Processed 0 new comments, skipped 1"
    assert task_queue.enqueued == []
    assert await fetch_comment(session_factory, "media_failure_comment") is None


@pytest.mark.asyncio
async def test_webhook_processes_multiple_comments(integration_environment, sign_payload):
    client: AsyncClient = integration_environment["client"]
    task_queue = integration_environment["task_queue"]

    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": "acct",
                "time": int(now_db_utc().timestamp()),
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": "multi_comment_1",
                            "media": {"id": "multi_media_1", "media_product_type": "FEED"},
                            "text": "First comment",
                            "from": {"id": "user_1", "username": "user_1"},
                        },
                    },
                    {
                        "field": "comments",
                        "value": {
                            "id": "multi_comment_2",
                            "media": {"id": "multi_media_2", "media_product_type": "FEED"},
                            "text": "Second comment",
                            "from": {"id": "user_2", "username": "user_2"},
                        },
                    },
                ],
            }
        ],
    }

    body = json.dumps(payload).encode()
    signature = sign_payload(body)
    response = await _with_timeout(
        client.post(
            "/api/v1/webhook/",
            content=body,
            headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"},
        )
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Processed 2 new comments, skipped 0"
    assert len(task_queue.enqueued) == 2
    queued_ids = {entry["args"][0] for entry in task_queue.enqueued}
    assert queued_ids == {"multi_comment_1", "multi_comment_2"}
