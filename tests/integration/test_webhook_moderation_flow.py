import asyncio
import json

import pytest
from dependency_injector import providers
from httpx import AsyncClient
from sqlalchemy import select

from core.container import get_container
from core.models import CommentClassification, InstagramComment, Media
from core.models.comment_classification import ProcessingStatus
from core.repositories.classification import ClassificationRepository
from core.tasks.classification_tasks import retry_failed_classifications_async, _trigger_post_classification_actions
from core.utils.time import now_db_utc

from tests.integration.helpers import fetch_classification, fetch_comment


REQUEST_TIMEOUT_SECONDS = 5


class _StubClassificationUseCase:
    def __init__(self, session, label: str):
        self.session = session
        self.label = label

    async def execute(self, comment_id: str, retry_count: int = 0):
        repo = ClassificationRepository(self.session)
        classification = await repo.get_by_comment_id(comment_id)
        if not classification:
            result = await self.session.execute(
                select(CommentClassification).where(CommentClassification.comment_id == comment_id)
            )
            classification = result.scalar_one()
        classification.type = self.label
        classification.processing_status = ProcessingStatus.COMPLETED
        classification.processing_completed_at = now_db_utc()
        classification.confidence = 95
        await self.session.commit()
        return {
            "status": "success",
            "comment_id": comment_id,
            "classification": self.label,
            "confidence": 0.95,
        }


async def _with_timeout(awaitable):
    return await asyncio.wait_for(awaitable, timeout=REQUEST_TIMEOUT_SECONDS)


def _base_payload(comment_id: str, media_id: str, text: str, username: str = "user") -> dict:
    return {
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
                            "text": text,
                            "from": {"id": "user_id", "username": username},
                        },
                    }
                ],
            }
        ],
    }


async def _post_webhook(client: AsyncClient, sign_payload, payload: dict):
    body = json.dumps(payload).encode()
    signature = sign_payload(body)
    return await _with_timeout(
        client.post(
            "/api/v1/webhook/",
            content=body,
            headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"},
        )
    )


async def _seed_media(session_factory, media_id: str):
    async with session_factory() as session:
        media = Media(
            id=media_id,
            permalink=f"https://instagram.com/p/{media_id}",
            media_type="IMAGE",
            media_url=f"https://cdn.test/{media_id}.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.commit()


async def _run_classification(comment_id: str, label: str):
    container = get_container()
    override = providers.Factory(lambda session, _label=label: _StubClassificationUseCase(session=session, label=_label))
    container.classify_comment_use_case.override(override)
    try:
        session_factory = container.db_session_factory()
        async with session_factory() as session:
            use_case = container.classify_comment_use_case(session=session)
            result = await use_case.execute(comment_id, retry_count=0)
        await _trigger_post_classification_actions(result)
    finally:
        container.classify_comment_use_case.reset_override()


async def _run_hide_tasks(task_queue):
    container = get_container()
    session_factory = container.db_session_factory()
    for entry in list(task_queue.enqueued):
        if entry["task"] == "core.tasks.instagram_reply_tasks.hide_instagram_comment_task":
            comment_id = entry["args"][0]
            async with session_factory() as session:
                use_case = container.hide_comment_use_case(session=session)
                await use_case.execute(comment_id, hide=True)
    task_queue.enqueued.clear()


@pytest.mark.asyncio
async def test_webhook_happy_path_enqueues_classification(integration_environment, sign_payload):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    task_queue = integration_environment["task_queue"]

    payload = _base_payload("comment_happy", "media_happy", "Hello")

    response = await _post_webhook(client, sign_payload, payload)

    assert response.status_code == 200
    assert response.json()["status"] == "success"

    comment = await fetch_comment(session_factory, "comment_happy")
    assert comment is not None
    assert comment.text == "Hello"

    classification = await fetch_classification(session_factory, "comment_happy")
    assert classification is not None
    assert classification.processing_status == ProcessingStatus.PENDING

    assert any(
        entry["task"] == "core.tasks.classification_tasks.classify_comment_task"
        and entry["args"][0] == "comment_happy"
        for entry in task_queue.enqueued
    )


@pytest.mark.asyncio
async def test_webhook_toxic_comment_auto_hide(integration_environment, sign_payload):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    task_queue = integration_environment["task_queue"]
    instagram_service = integration_environment["instagram_service"]

    await _seed_media(session_factory, "media_toxic")

    comment_payload = _base_payload("comment_toxic", "media_toxic", "Offensive text")
    await _post_webhook(client, sign_payload, comment_payload)

    task_queue.enqueued.clear()
    await _run_classification("comment_toxic", "toxic / abusive")

    classification = await fetch_classification(session_factory, "comment_toxic")
    assert classification.type == "toxic / abusive"
    assert classification.processing_status == ProcessingStatus.COMPLETED

    await _run_hide_tasks(task_queue)

    comment = await fetch_comment(session_factory, "comment_toxic")
    assert comment.is_hidden is True
    assert "comment_toxic" in instagram_service.hidden


@pytest.mark.asyncio
async def test_webhook_urgent_issue_auto_hide(integration_environment, sign_payload):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    task_queue = integration_environment["task_queue"]
    instagram_service = integration_environment["instagram_service"]

    await _seed_media(session_factory, "media_urgent")

    comment_payload = _base_payload("comment_urgent", "media_urgent", "Help! urgent issue")
    await _post_webhook(client, sign_payload, comment_payload)

    task_queue.enqueued.clear()
    await _run_classification("comment_urgent", "urgent issue / complaint")

    classification = await fetch_classification(session_factory, "comment_urgent")
    assert classification.type == "urgent issue / complaint"

    await _run_hide_tasks(task_queue)

    comment = await fetch_comment(session_factory, "comment_urgent")
    assert comment.is_hidden is True
    assert "comment_urgent" in instagram_service.hidden


@pytest.mark.asyncio
async def test_webhook_classification_retry_flow(integration_environment, sign_payload):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    task_queue = integration_environment["task_queue"]

    payload = _base_payload("comment_retry", "media_retry", "Needs retry")
    await _post_webhook(client, sign_payload, payload)

    async with session_factory() as session:
        repo = ClassificationRepository(session)
        classification = await repo.get_by_comment_id("comment_retry")
        classification.processing_status = ProcessingStatus.RETRY
        classification.retry_count = 1
        await session.commit()

    task_queue.enqueued.clear()
    result = await retry_failed_classifications_async()
    assert result == {"retried_count": 1}
    assert any(
        entry["task"] == "core.tasks.classification_tasks.classify_comment_task"
        and entry["args"][0] == "comment_retry"
        for entry in task_queue.enqueued
    )


@pytest.mark.asyncio
async def test_webhook_validation_failure_returns_422(integration_environment, sign_payload):
    client: AsyncClient = integration_environment["client"]

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
                            "id": "comment_invalid",
                            "media": {"id": "media_invalid"},
                            "text": "",
                            "from": {"id": "user", "username": "user"},
                        },
                    }
                ],
            }
        ],
    }

    response = await _post_webhook(client, sign_payload, payload)
    assert response.status_code == 422
