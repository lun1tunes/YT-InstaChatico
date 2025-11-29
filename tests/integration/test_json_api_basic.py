"""Basic CRUD operations tests for JSON API endpoints."""

import re
from datetime import datetime

import pytest
from httpx import AsyncClient

from core.models import CommentClassification, InstagramComment, Media
from core.utils.time import now_db_utc
from tests.integration.json_api_helpers import auth_headers


@pytest.mark.asyncio
async def test_media_listing(integration_environment):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_list",
            permalink="https://instagram.com/p/media_list",
            media_type="IMAGE",
            media_url="https://cdn.test/list.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.commit()

    response = await client.get("/api/v1/media", headers=auth_headers(integration_environment))
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["page"] == 1
    assert len(data["payload"]) >= 1
    first = data["payload"][0]
    assert "is_processing_enabled" in first


@pytest.mark.asyncio
async def test_media_comments_with_status_filter(integration_environment):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_comments",
            permalink="https://instagram.com/p/media_comments",
            media_type="IMAGE",
            media_url="https://cdn.test/comments.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        comment = InstagramComment(
            id="comment_status",
            media_id=media.id,
            user_id="user",
            username="tester",
            text="Needs attention",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)

        classification = CommentClassification(
            comment_id=comment.id,
            type="question / inquiry",
            processing_status="COMPLETED",
            processing_completed_at=now_db_utc(),
        )
        session.add(classification)
        await session.commit()

    response = await client.get(
        "/api/v1/media/media_comments/comments?status[]=3",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert len(payload) == 1
    assert payload[0]["classification"]["classification_type"] == 4
    ts = payload[0]["classification"]["processing_completed_at"]
    assert ts and ts.endswith("Z")
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$", ts)
    datetime.fromisoformat(ts.replace("Z", "+00:00"))


@pytest.mark.asyncio
async def test_media_comments_with_multiple_status_filters(integration_environment):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_comments_multi",
            permalink="https://instagram.com/p/media_comments_multi",
            media_type="IMAGE",
            media_url="https://cdn.test/comments_multi.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.flush()

        for idx, status in enumerate(["PENDING", "PROCESSING", "COMPLETED"]):
            comment = InstagramComment(
                id=f"comment_multi_{idx}",
                media_id=media.id,
                user_id=f"user_{idx}",
                username=f"tester_{idx}",
                text=f"Comment {idx}",
                created_at=now_db_utc(),
                raw_data={},
            )
            session.add(comment)
            await session.flush()

            classification = CommentClassification(
                comment_id=comment.id,
                processing_status=status,
            )
            session.add(classification)

        await session.commit()

    response = await client.get(
        "/api/v1/media/media_comments_multi/comments?status[]=1&status[]=3",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert len(payload) == 2


@pytest.mark.asyncio
async def test_patch_comment_classification(integration_environment):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_patch",
            permalink="https://instagram.com/p/media_patch",
            media_type="IMAGE",
            media_url="https://cdn.test/patch.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        comment = InstagramComment(
            id="comment_patch_classification",
            media_id=media.id,
            user_id="user",
            username="tester",
            text="Test comment",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.flush()

        classification = CommentClassification(
            comment_id=comment.id,
            type="positive feedback",
            processing_status="COMPLETED",
        )
        session.add(classification)
        await session.commit()

    response = await client.patch(
        "/api/v1/comments/comment_patch_classification/classification",
        headers=auth_headers(integration_environment),
        json={"type": "critical feedback", "reasoning": "manual review"},
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert payload["classification"]["classification_type"] == 2
    assert payload["classification"]["confidence"] is None
    patched_ts = payload["classification"]["processing_completed_at"]
    assert patched_ts and patched_ts.endswith("Z")
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$", patched_ts)
    datetime.fromisoformat(patched_ts.replace("Z", "+00:00"))


@pytest.mark.asyncio
async def test_answer_management(integration_environment):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_answer",
            permalink="https://instagram.com/p/media_answer",
            media_type="IMAGE",
            media_url="https://cdn.test/answer.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        comment = InstagramComment(
            id="comment_answer_management",
            media_id=media.id,
            user_id="user",
            username="tester",
            text="Test question?",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.flush()

        from core.models import QuestionAnswer

        classification = CommentClassification(
            comment_id=comment.id,
            processing_status="COMPLETED",
        )
        session.add(classification)

        answer = QuestionAnswer(
            comment_id=comment.id,
            answer="Initial answer",
        )
        session.add(answer)
        await session.commit()
        answer_id = answer.id

    # Try to update non-existent answer
    update = await client.patch(
        "/api/v1/answers/999",
        headers=auth_headers(integration_environment),
        json={"answer": "New answer"},
    )
    assert update.status_code == 404

