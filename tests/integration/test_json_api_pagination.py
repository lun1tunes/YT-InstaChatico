"""Pagination and filtering tests for JSON API endpoints."""

from datetime import timedelta

import pytest
from httpx import AsyncClient

from core.models import CommentClassification, InstagramComment, Media
from core.models.comment_classification import ProcessingStatus
from core.utils.time import now_db_utc
from tests.integration.json_api_helpers import auth_headers


# ===== Media Endpoints Tests =====


@pytest.mark.asyncio
async def test_get_media_by_id(integration_environment):
    """Test getting a single media by ID."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_detail_test",
            permalink="https://instagram.com/p/media_detail_test",
            media_type="VIDEO",
            media_url="https://cdn.test/video.mp4",
            caption="Test video caption",
            is_processing_enabled=True,
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.commit()

    response = await client.get("/api/v1/media/media_detail_test", headers=auth_headers(integration_environment))
    assert response.status_code == 200
    data = response.json()
    assert data["payload"]["id"] == "media_detail_test"
    assert data["payload"]["type"] == 2  # VIDEO = 2
    assert data["payload"]["caption"] == "Test video caption"
    assert data["payload"]["is_processing_enabled"] is True


@pytest.mark.asyncio
async def test_get_media_not_found(integration_environment):
    """Test getting non-existent media returns 404."""
    client: AsyncClient = integration_environment["client"]
    response = await client.get("/api/v1/media/nonexistent_media", headers=auth_headers(integration_environment))
    assert response.status_code == 404
    data = response.json()
    assert data["meta"]["error"]["code"] == 4040
    assert "Media not found" in data["meta"]["error"]["message"]


@pytest.mark.asyncio
async def test_patch_media_processing_enabled(integration_environment):
    """Test toggling media is_processing_enabled field."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_toggle_processing",
            permalink="https://instagram.com/p/media_toggle_processing",
            media_type="IMAGE",
            media_url="https://cdn.test/toggle.jpg",
            is_processing_enabled=True,
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.commit()

    # Disable processing
    response = await client.patch(
        "/api/v1/media/media_toggle_processing",
        headers=auth_headers(integration_environment),
        json={"is_processing_enabled": False},
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert payload["is_processing_enabled"] is False

    # Verify in database
    async with session_factory() as session:
        media = await session.get(Media, "media_toggle_processing")
        assert media.is_processing_enabled is False


@pytest.mark.asyncio
async def test_patch_media_context(integration_environment):
    """Test updating media context field."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_context_test",
            permalink="https://instagram.com/p/media_context_test",
            media_type="IMAGE",
            media_url="https://cdn.test/context.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.commit()

    response = await client.patch(
        "/api/v1/media/media_context_test",
        headers=auth_headers(integration_environment),
        json={"context": "This is a promotional post for our new product"},
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert payload["context"] == "This is a promotional post for our new product"


@pytest.mark.asyncio
async def test_patch_media_comment_status(integration_environment):
    """Test toggling media comment enabled status via Instagram API."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    instagram_service = integration_environment["instagram_service"]

    async with session_factory() as session:
        media = Media(
            id="media_comment_toggle",
            permalink="https://instagram.com/p/media_comment_toggle",
            media_type="IMAGE",
            media_url="https://cdn.test/comment_toggle.jpg",
            is_comment_enabled=True,
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.commit()

    response = await client.patch(
        "/api/v1/media/media_comment_toggle",
        headers=auth_headers(integration_environment),
        json={"is_comment_enabled": False},
    )
    assert response.status_code == 200
    payload = response.json()["payload"]
    assert payload["is_comment_enabled"] is False


# ===== Pagination Tests =====


@pytest.mark.asyncio
async def test_media_list_pagination_default(integration_environment):
    """Test media listing with default pagination."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    # Create 15 media items
    async with session_factory() as session:
        for i in range(15):
            media = Media(
                id=f"pagination_media_{i}",
                permalink=f"https://instagram.com/p/pagination_media_{i}",
                media_type="IMAGE",
                media_url=f"https://cdn.test/page{i}.jpg",
                created_at=now_db_utc(),
                updated_at=now_db_utc(),
            )
            session.add(media)
        await session.commit()

    response = await client.get("/api/v1/media", headers=auth_headers(integration_environment))
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["page"] == 1
    assert data["meta"]["per_page"] == 10  # Default
    assert data["meta"]["total"] >= 15
    assert len(data["payload"]) == 10


@pytest.mark.asyncio
async def test_media_list_pagination_custom_per_page(integration_environment):
    """Test media listing with custom per_page parameter."""
    client: AsyncClient = integration_environment["client"]
    response = await client.get("/api/v1/media?per_page=5", headers=auth_headers(integration_environment))
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["per_page"] == 5
    assert len(data["payload"]) <= 5


@pytest.mark.asyncio
async def test_media_list_pagination_max_clamped(integration_environment):
    """Test media listing clamps per_page to maximum."""
    client: AsyncClient = integration_environment["client"]
    response = await client.get("/api/v1/media?per_page=1000", headers=auth_headers(integration_environment))
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["per_page"] == 30  # Max for media


@pytest.mark.asyncio
async def test_media_list_includes_quick_stats(integration_environment):
    """Ensure media list response includes quick stats calculated over the last hour."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    now = now_db_utc()

    async with session_factory() as session:
        media = Media(
            id="stats_media",
            permalink="https://instagram.com/p/stats_media",
            media_type="IMAGE",
            media_url="https://cdn.test/stats.jpg",
            created_at=now,
            updated_at=now,
        )
        session.add(media)

        recent_comment = InstagramComment(
            id="stats_comment_recent",
            media_id="stats_media",
            user_id="user_recent",
            username="recent_user",
            text="Great job!",
            created_at=now,
            raw_data={},
        )
        old_comment = InstagramComment(
            id="stats_comment_old",
            media_id="stats_media",
            user_id="user_old",
            username="old_user",
            text="Needs work",
            created_at=now - timedelta(hours=3),
            raw_data={},
        )
        session.add_all([recent_comment, old_comment])

        session.add_all(
            [
                CommentClassification(
                    comment_id="stats_comment_recent",
                    processing_status=ProcessingStatus.COMPLETED,
                    processing_completed_at=now,
                    type="positive feedback",
                ),
                CommentClassification(
                    comment_id="stats_comment_old",
                    processing_status=ProcessingStatus.COMPLETED,
                    processing_completed_at=now - timedelta(hours=3),
                    type="critical feedback",
                ),
            ]
        )
        await session.commit()

    response = await client.get("/api/v1/media", headers=auth_headers(integration_environment))
    assert response.status_code == 200
    payload = response.json()["payload"]
    media_entry = next(item for item in payload if item["id"] == "stats_media")
    stats = media_entry["stats"]

    assert stats["positive_feedback_total"] == 1
    assert stats["positive_feedback_increment"] == 1
    assert stats["negative_feedback_total"] == 1
    assert stats["negative_feedback_increment"] == 0
    assert "questions_total" in stats


@pytest.mark.asyncio
async def test_media_list_page_2(integration_environment):
    """Test media listing on page 2."""
    client: AsyncClient = integration_environment["client"]
    response = await client.get("/api/v1/media?page=2&per_page=5", headers=auth_headers(integration_environment))
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["page"] == 2


@pytest.mark.asyncio
async def test_media_list_invalid_page_returns_422(integration_environment):
    """Requesting page=0 should trigger validation error wrapped in JSON API envelope."""
    client: AsyncClient = integration_environment["client"]
    response = await client.get("/api/v1/media?page=0", headers=auth_headers(integration_environment))
    assert response.status_code == 422
    body = response.json()
    assert body["meta"]["error"]["code"] == 4000
    assert body["payload"] is None


@pytest.mark.asyncio
async def test_comment_list_per_page_clamped(integration_environment):
    """Comments listing should enforce MAX_PER_PAGE of 100."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    media_id = "media_comments_pagination"
    async with session_factory() as session:
        media = Media(
            id=media_id,
            permalink="https://instagram.com/p/media_comments_pagination",
            media_type="IMAGE",
            media_url="https://cdn.test/comments_pag.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        # Add a handful of comments to ensure payload is non-empty
        for idx in range(5):
            comment = InstagramComment(
                id=f"comment_pag_{idx}",
                media_id=media_id,
                user_id=f"user_{idx}",
                username=f"user_{idx}",
                text=f"Comment {idx}",
                created_at=now_db_utc(),
                raw_data={},
            )
            session.add(comment)
            session.add(
                CommentClassification(
                    comment_id=comment.id,
                    processing_status=ProcessingStatus.COMPLETED,
                )
            )
        await session.commit()

    response = await client.get(
        f"/api/v1/media/{media_id}/comments?per_page=500",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["per_page"] == 100  # MAX_PER_PAGE for comments
    assert len(payload["payload"]) <= 100


# ===== Recent Comments Endpoint Tests =====


@pytest.mark.asyncio
async def test_recent_comments_returns_newest_first(integration_environment):
    """Ensure /api/v1/comments returns most recent comments across media."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    base_time = now_db_utc() + timedelta(days=1)

    async with session_factory() as session:
        media_a = Media(
            id="recent_media_a",
            permalink="https://instagram.com/p/recent_media_a",
            media_type="IMAGE",
            media_url="https://cdn.test/recent_a.jpg",
            created_at=base_time,
            updated_at=base_time,
        )
        media_b = Media(
            id="recent_media_b",
            permalink="https://instagram.com/p/recent_media_b",
            media_type="IMAGE",
            media_url="https://cdn.test/recent_b.jpg",
            created_at=base_time,
            updated_at=base_time,
        )
        session.add_all([media_a, media_b])

        oldest = InstagramComment(
            id="recent_comment_oldest",
            media_id=media_a.id,
            user_id="user_old",
            username="old",
            text="Old comment",
            created_at=base_time - timedelta(hours=2),
            raw_data={},
        )
        middle = InstagramComment(
            id="recent_comment_middle",
            media_id=media_b.id,
            user_id="user_mid",
            username="mid",
            text="Middle comment",
            created_at=base_time - timedelta(hours=1),
            raw_data={},
        )
        newest = InstagramComment(
            id="recent_comment_newest",
            media_id=media_a.id,
            user_id="user_new",
            username="new",
            text="Newest comment",
            created_at=base_time,
            raw_data={},
        )
        session.add_all([oldest, middle, newest])

        for comment in (oldest, middle, newest):
            session.add(
                CommentClassification(
                    comment_id=comment.id,
                    type="question / inquiry",
                    processing_status=ProcessingStatus.COMPLETED,
                    processing_completed_at=base_time,
                )
            )

        await session.commit()

    response = await client.get("/api/v1/comments", headers=auth_headers(integration_environment))
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["total"] == 3
    ids = [item["id"] for item in data["payload"]]
    assert ids[:3] == [
        "recent_comment_newest",
        "recent_comment_middle",
        "recent_comment_oldest",
    ]
    media_map = {item["id"]: item["media_id"] for item in data["payload"]}
    assert media_map["recent_comment_newest"] == "recent_media_a"
    assert media_map["recent_comment_middle"] == "recent_media_b"
    assert media_map["recent_comment_oldest"] == "recent_media_a"


@pytest.mark.asyncio
async def test_recent_comments_includes_stats(integration_environment):
    """Ensure /api/v1/comments returns aggregated quick stats block."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]
    now = now_db_utc()

    async with session_factory() as session:
        media = Media(
            id="comments_stats_media",
            permalink="https://instagram.com/p/comments_stats_media",
            media_type="IMAGE",
            media_url="https://cdn.test/comments_stats.jpg",
            created_at=now,
            updated_at=now,
        )
        session.add(media)
        comment = InstagramComment(
            id="comments_stats_comment",
            media_id=media.id,
            user_id="stats_user",
            username="stats_user",
            text="Is this available?",
            created_at=now,
            raw_data={},
        )
        session.add(comment)
        session.add(
            CommentClassification(
                comment_id=comment.id,
                processing_status=ProcessingStatus.COMPLETED,
                processing_completed_at=now,
                type="question / inquiry",
            )
        )
        await session.commit()

    response = await client.get("/api/v1/comments", headers=auth_headers(integration_environment))
    assert response.status_code == 200
    stats = response.json()["stats"]
    assert stats["questions_total"] >= 1
    assert stats["questions_increment"] >= 1


@pytest.mark.asyncio
async def test_recent_comments_filters_by_status(integration_environment):
    """Status filters should apply to aggregated comments endpoint."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="recent_filter_media",
            permalink="https://instagram.com/p/recent_filter_media",
            media_type="IMAGE",
            media_url="https://cdn.test/recent_filter.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        pending_comment = InstagramComment(
            id="recent_filter_pending",
            media_id=media.id,
            user_id="pending_user",
            username="pending",
            text="Pending comment",
            created_at=now_db_utc(),
            raw_data={},
        )
        completed_comment = InstagramComment(
            id="recent_filter_completed",
            media_id=media.id,
            user_id="completed_user",
            username="completed",
            text="Completed comment",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add_all([pending_comment, completed_comment])

        session.add(
            CommentClassification(
                comment_id=pending_comment.id,
                type="question / inquiry",
                processing_status=ProcessingStatus.PENDING,
            )
        )
        session.add(
            CommentClassification(
                comment_id=completed_comment.id,
                type="question / inquiry",
                processing_status=ProcessingStatus.COMPLETED,
                processing_completed_at=now_db_utc(),
            )
        )

        await session.commit()

    response = await client.get(
        "/api/v1/comments?status=3",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()
    payload_ids = [item["id"] for item in data["payload"]]
    assert "recent_filter_completed" in payload_ids
    assert "recent_filter_pending" not in payload_ids
    target = next(item for item in data["payload"] if item["id"] == "recent_filter_completed")
    assert target["media_id"] == "recent_filter_media"
    assert target["classification"]["processing_status"] == 3


@pytest.mark.asyncio
async def test_recent_comments_excludes_deleted_when_requested(integration_environment):
    """include_deleted flag should hide soft-deleted comments when false."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="recent_deleted_media",
            permalink="https://instagram.com/p/recent_deleted_media",
            media_type="IMAGE",
            media_url="https://cdn.test/recent_deleted.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        active_comment = InstagramComment(
            id="recent_deleted_active",
            media_id=media.id,
            user_id="active_user",
            username="active",
            text="Active comment",
            created_at=now_db_utc(),
            raw_data={},
        )
        deleted_comment = InstagramComment(
            id="recent_deleted_soft",
            media_id=media.id,
            user_id="deleted_user",
            username="deleted",
            text="Soft deleted comment",
            created_at=now_db_utc(),
            raw_data={},
            is_deleted=True,
        )
        session.add_all([active_comment, deleted_comment])

        for comment in (active_comment, deleted_comment):
            session.add(
                CommentClassification(
                    comment_id=comment.id,
                    type="question / inquiry",
                    processing_status=ProcessingStatus.COMPLETED,
                    processing_completed_at=now_db_utc(),
                )
            )

        await session.commit()

    # Default (include_deleted=True) should return both
    default_response = await client.get("/api/v1/comments", headers=auth_headers(integration_environment))
    assert default_response.status_code == 200
    default_data = default_response.json()
    default_ids = {item["id"] for item in default_data["payload"]}
    assert "recent_deleted_active" in default_ids
    assert "recent_deleted_soft" in default_ids

    # Explicit include_deleted=false should hide the soft-deleted comment
    filtered_response = await client.get(
        "/api/v1/comments?include_deleted=false",
        headers=auth_headers(integration_environment),
    )
    assert filtered_response.status_code == 200
    filtered_data = filtered_response.json()
    filtered_ids = {item["id"] for item in filtered_data["payload"]}
    assert "recent_deleted_active" in filtered_ids
    assert "recent_deleted_soft" not in filtered_ids
    media_ids_filtered = {item["id"]: item["media_id"] for item in filtered_data["payload"]}
    assert media_ids_filtered["recent_deleted_active"] == "recent_deleted_media"
