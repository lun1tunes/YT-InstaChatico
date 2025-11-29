"""Comment operations tests (hide, unhide, delete, classification) for JSON API endpoints."""

from datetime import datetime, timedelta, timezone
import hashlib

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from core.models import CommentClassification, InstagramComment, Media
from core.models.comment_classification import ProcessingStatus
from core.models.expired_token import ExpiredToken
from core.utils.time import now_db_utc
from tests.integration.json_api_helpers import auth_headers


# ===== Comment Visibility Tests =====


@pytest.mark.asyncio
async def test_hide_comment(integration_environment):
    """Test hiding a comment via API."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    instagram_service = integration_environment["instagram_service"]

    async with session_factory() as session:
        media = Media(
            id="media_hide_test",
            permalink="https://instagram.com/p/media_hide_test",
            media_type="IMAGE",
            media_url="https://cdn.test/hide.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_to_hide",
            media_id=media.id,
            user_id="user_spam",
            username="spammer",
            text="Spam comment",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.commit()

    response = await client.patch(
        "/api/v1/comments/comment_to_hide",
        headers=auth_headers(integration_environment),
        params={"is_hidden": True},
    )
    assert response.status_code == 200
    assert "comment_to_hide" in instagram_service.hidden


@pytest.mark.asyncio
async def test_unhide_comment(integration_environment):
    """Test unhiding a comment via API."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    instagram_service = integration_environment["instagram_service"]

    async with session_factory() as session:
        media = Media(
            id="media_unhide_test",
            permalink="https://instagram.com/p/media_unhide_test",
            media_type="IMAGE",
            media_url="https://cdn.test/unhide.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_to_unhide",
            media_id=media.id,
            user_id="user_ok",
            username="gooduser",
            text="Good comment",
            is_hidden=True,  # Start as hidden
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.commit()

    # Pre-populate as hidden in Instagram service stub
    instagram_service.hidden.append("comment_to_unhide")

    # Then unhide via API
    response = await client.patch(
        "/api/v1/comments/comment_to_unhide",
        headers=auth_headers(integration_environment),
        params={"is_hidden": False},
    )
    assert response.status_code == 200
    assert "comment_to_unhide" not in instagram_service.hidden


@pytest.mark.asyncio
async def test_hide_comment_not_found(integration_environment):
    """Test hiding non-existent comment returns 502 (use case returns error, then 404 when fetching after)."""
    client: AsyncClient = integration_environment["client"]
    response = await client.patch(
        "/api/v1/comments/nonexistent_comment",
        headers=auth_headers(integration_environment),
        params={"is_hidden": True},
    )
    # The use case returns error status first, causing 502
    assert response.status_code == 502
    data = response.json()
    assert data["meta"]["error"]["code"] == 5003


# ===== Comment Deletion Tests =====


@pytest.mark.asyncio
async def test_delete_comment(integration_environment):
    """Test deleting a comment via API."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    instagram_service = integration_environment["instagram_service"]

    async with session_factory() as session:
        media = Media(
            id="media_delete_test",
            permalink="https://instagram.com/p/media_delete_test",
            media_type="IMAGE",
            media_url="https://cdn.test/delete.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_to_delete",
            media_id=media.id,
            user_id="user_del",
            username="deluser",
            text="Will be deleted",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        child = InstagramComment(
            id="child_comment",
            media_id=media.id,
            user_id="user_child",
            username="childuser",
            text="Child reply",
            parent_id=comment.id,
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(child)
        await session.commit()

    response = await client.delete(
        "/api/v1/comments/comment_to_delete",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    assert response.json()["payload"] is None

    assert "comment_to_delete" in instagram_service.deleted

    # Verify deleted from database
    async with session_factory() as session:
        deleted = await session.get(InstagramComment, "comment_to_delete")
        assert deleted is not None
        assert deleted.is_deleted is True
        child = await session.get(InstagramComment, "child_comment")
        assert child is not None
        assert child.is_deleted is True


@pytest.mark.asyncio
async def test_deleted_comments_excluded_from_listing(integration_environment):
    """Deleted comments should not appear in listings."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_deleted_list",
            permalink="https://instagram.com/p/media_deleted_list",
            media_type="IMAGE",
            media_url="https://cdn.test/list.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_list_hidden",
            media_id=media.id,
            user_id="user_list",
            username="listuser",
            text="Hidden",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.commit()

    await client.delete(
        "/api/v1/comments/comment_list_hidden",
        headers=auth_headers(integration_environment),
    )

    response = await client.get(
        "/api/v1/media/media_deleted_list/comments",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert len(payload) == 1
    assert payload[0]["id"] == "comment_list_hidden"
    assert payload[0]["is_deleted"] is True

    response = await client.get(
        "/api/v1/media/media_deleted_list/comments?include_deleted=false",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert payload == []


# ===== Status Filter Tests =====


@pytest.mark.asyncio
async def test_media_comments_filter_by_csv_status(integration_environment):
    """Test filtering comments by CSV status parameter."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_csv_filter",
            permalink="https://instagram.com/p/media_csv_filter",
            media_type="IMAGE",
            media_url="https://cdn.test/csv.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        # Add comment with PENDING status
        comment = InstagramComment(
            id="comment_csv_pending",
            media_id=media.id,
            user_id="user",
            username="tester",
            text="Pending comment",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        classification = CommentClassification(
            comment_id=comment.id,
            type="question / inquiry",
            processing_status="PENDING",
        )
        session.add(classification)
        await session.commit()

    # Use CSV format for status filter
    response = await client.get(
        "/api/v1/media/media_csv_filter/comments?status=1",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert len(payload) == 1


@pytest.mark.asyncio
async def test_media_comments_filter_invalid_status(integration_environment):
    """Test filtering comments with invalid status returns error."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_invalid_filter",
            permalink="https://instagram.com/p/media_invalid_filter",
            media_type="IMAGE",
            media_url="https://cdn.test/invalid.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.commit()

    response = await client.get(
        "/api/v1/media/media_invalid_filter/comments?status=999",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 400
    data = response.json()
    assert data["meta"]["error"]["code"] == 4006


@pytest.mark.asyncio
async def test_media_comments_filter_by_classification_type(integration_environment):
    """Test filtering comments by classification type parameter."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_type_filter",
            permalink="https://instagram.com/p/media_type_filter",
            media_type="IMAGE",
            media_url="https://cdn.test/type.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        comment_question = InstagramComment(
            id="comment_type_question",
            media_id=media.id,
            user_id="user_question",
            username="asker",
            text="Is this available?",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment_question)
        session.add(
            CommentClassification(
                comment_id=comment_question.id,
                type="question / inquiry",
                processing_status=ProcessingStatus.COMPLETED.value,
            )
        )

        comment_positive = InstagramComment(
            id="comment_type_positive",
            media_id=media.id,
            user_id="user_positive",
            username="fan",
            text="Love it!",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment_positive)
        session.add(
            CommentClassification(
                comment_id=comment_positive.id,
                type="positive feedback",
                processing_status=ProcessingStatus.COMPLETED.value,
            )
        )
        await session.commit()

    # Filter for question/inquiry (code 4)
    response = await client.get(
        "/api/v1/media/media_type_filter/comments?type=4",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert len(payload) == 1
    assert payload[0]["id"] == "comment_type_question"
    assert payload[0]["classification"]["classification_type"] == 4

    # Filter for both question and positive using array syntax
    response = await client.get(
        "/api/v1/media/media_type_filter/comments?type[]=4&type[]=1",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert {item["id"] for item in payload} == {
        "comment_type_question",
        "comment_type_positive",
    }

    # Filter using classification_type alias
    response = await client.get(
        "/api/v1/media/media_type_filter/comments?classification_type=1",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert len(payload) == 1
    assert payload[0]["id"] == "comment_type_positive"
    assert payload[0]["classification"]["classification_type"] == 1


@pytest.mark.asyncio
async def test_media_comments_filter_invalid_classification(integration_environment):
    """Test filtering comments with invalid classification returns error."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_invalid_type_filter",
            permalink="https://instagram.com/p/media_invalid_type_filter",
            media_type="IMAGE",
            media_url="https://cdn.test/invalid_type.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.commit()

    response = await client.get(
        "/api/v1/media/media_invalid_type_filter/comments?type=999",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 400
    data = response.json()
    assert data["meta"]["error"]["code"] == 4007


@pytest.mark.asyncio
async def test_media_comments_pagination(integration_environment):
    """Test comment listing pagination."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_comment_pagination",
            permalink="https://instagram.com/p/media_comment_pagination",
            media_type="IMAGE",
            media_url="https://cdn.test/pagination.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        # Create 50 comments
        for i in range(50):
            comment = InstagramComment(
                id=f"comment_page_{i}",
                media_id=media.id,
                user_id=f"user_{i}",
                username=f"user{i}",
                text=f"Comment {i}",
                created_at=now_db_utc(),
                raw_data={},
            )
            session.add(comment)
        await session.commit()

    # Default pagination
    response = await client.get(
        "/api/v1/media/media_comment_pagination/comments",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["per_page"] == 30  # Default for comments
    assert data["meta"]["total"] >= 50
    assert len(data["payload"]) == 30

    # Custom per_page
    response = await client.get(
        "/api/v1/media/media_comment_pagination/comments?per_page=10",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["per_page"] == 10
    assert len(data["payload"]) == 10


# ===== Classification Edge Cases =====


@pytest.mark.asyncio
async def test_patch_classification_invalid_type(integration_environment):
    """Test patching classification with invalid type."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_invalid_class",
            permalink="https://instagram.com/p/media_invalid_class",
            media_type="IMAGE",
            media_url="https://cdn.test/invalid_class.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_invalid_class",
            media_id=media.id,
            user_id="user",
            username="tester",
            text="Test",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.commit()

    response = await client.patch(
        "/api/v1/comments/comment_invalid_class/classification",
        headers=auth_headers(integration_environment),
        json={"type": "invalid_classification_type", "reasoning": "test"},
    )
    assert response.status_code == 400
    data = response.json()
    assert data["meta"]["error"]["code"] == 4009


@pytest.mark.asyncio
async def test_patch_classification_creates_if_missing(integration_environment):
    """Test patching classification creates new record if missing."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_create_class",
            permalink="https://instagram.com/p/media_create_class",
            media_type="IMAGE",
            media_url="https://cdn.test/create_class.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_create_class",
            media_id=media.id,
            user_id="user",
            username="tester",
            text="New classification",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.commit()

    response = await client.patch(
        "/api/v1/comments/comment_create_class/classification",
        headers=auth_headers(integration_environment),
        json={"type": "question / inquiry", "reasoning": "manual"},
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert payload["classification"]["classification_type"] == 4  # question / inquiry
    assert payload["classification"]["reasoning"] == "manual"


@pytest.mark.asyncio
async def test_patch_classification_accepts_numeric_code(integration_environment):
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_numeric_class",
            permalink="https://instagram.com/p/media_numeric_class",
            media_type="IMAGE",
            media_url="https://cdn.test/numeric_class.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        comment = InstagramComment(
            id="comment_numeric_class",
            media_id=media.id,
            user_id="user",
            username="tester",
            text="Numeric classification",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        await session.commit()

    response = await client.patch(
        "/api/v1/comments/comment_numeric_class/classification",
        headers=auth_headers(integration_environment),
        json={"type": 4, "reasoning": "manual numeric"},
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert payload["classification"]["classification_type"] == 4
    assert payload["classification"]["reasoning"] == "manual numeric"


@pytest.mark.asyncio
async def test_expired_token_is_recorded(integration_environment):
    client: AsyncClient = integration_environment["client"]
    secret = integration_environment["json_api_secret"]
    algorithm = integration_environment["json_api_algorithm"]
    session_factory = integration_environment["session_factory"]

    now = datetime.now(timezone.utc)
    payload = {
        "sub": "expired-user",
        "role": "admin",
        "scopes": ["me", "admin"],
        "iat": int((now - timedelta(minutes=2)).timestamp()),
        "exp": int((now - timedelta(minutes=1)).timestamp()),
    }
    token = jwt.encode(payload, secret, algorithm=algorithm)

    response = await client.get(
        "/api/v1/comments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    body = response.json()
    assert body["meta"]["error"]["code"] == 4005

    token_id = hashlib.sha256(token.encode("utf-8")).hexdigest()

    async with session_factory() as session:
        result = await session.execute(
            select(ExpiredToken).where(ExpiredToken.jti == token_id)
        )
        stored = result.scalar_one_or_none()
        assert stored is not None
