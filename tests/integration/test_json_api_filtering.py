"""Multi-status filtering tests for JSON API endpoints."""

import pytest
from httpx import AsyncClient

from core.models import CommentClassification, InstagramComment, Media
from core.models.comment_classification import ProcessingStatus
from core.utils.time import now_db_utc
from tests.integration.json_api_helpers import auth_headers


# ===== Multi-Status Filtering Tests =====


@pytest.mark.asyncio
async def test_multi_status_filter_array_format(integration_environment):
    """Test filtering comments by multiple statuses using array format ?status[]=1&status[]=3."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    # Create media with comments in different statuses
    async with session_factory() as session:
        media = Media(
            id="media_multi_status",
            permalink="https://instagram.com/p/media_multi_status",
            media_type="IMAGE",
            media_url="https://cdn.test/multi_status.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        # PENDING status (1)
        comment1 = InstagramComment(
            id="comment_pending_1",
            media_id=media.id,
            user_id="user1",
            username="user1",
            text="Pending comment 1",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment1)
        session.add(CommentClassification(
            comment_id=comment1.id,
            type="question / inquiry",
            processing_status="PENDING",
        ))

        # PROCESSING status (2)
        comment2 = InstagramComment(
            id="comment_processing",
            media_id=media.id,
            user_id="user2",
            username="user2",
            text="Processing comment",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment2)
        session.add(CommentClassification(
            comment_id=comment2.id,
            type="positive feedback",
            processing_status="PROCESSING",
        ))

        # COMPLETED status (3)
        comment3 = InstagramComment(
            id="comment_completed",
            media_id=media.id,
            user_id="user3",
            username="user3",
            text="Completed comment",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment3)
        session.add(CommentClassification(
            comment_id=comment3.id,
            type="critical feedback",
            processing_status="COMPLETED",
            processing_completed_at=now_db_utc(),
        ))

        # FAILED status (4)
        comment4 = InstagramComment(
            id="comment_failed",
            media_id=media.id,
            user_id="user4",
            username="user4",
            text="Failed comment",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment4)
        session.add(CommentClassification(
            comment_id=comment4.id,
            type="spam / irrelevant",
            processing_status="FAILED",
            last_error="Processing error",
        ))

        # Another PENDING
        comment5 = InstagramComment(
            id="comment_pending_2",
            media_id=media.id,
            user_id="user5",
            username="user5",
            text="Pending comment 2",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment5)
        session.add(CommentClassification(
            comment_id=comment5.id,
            type="urgent issue / complaint",
            processing_status="PENDING",
        ))

        await session.commit()

    # Filter for PENDING (1) and COMPLETED (3) statuses
    response = await client.get(
        "/api/v1/media/media_multi_status/comments?status[]=1&status[]=3",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()

    # Should return 3 comments (2 PENDING + 1 COMPLETED)
    assert data["meta"]["total"] == 3
    assert len(data["payload"]) == 3

    # Verify all returned comments have correct status
    statuses = {comment["classification"]["processing_status"] for comment in data["payload"]}
    assert statuses == {1, 3}  # Only PENDING and COMPLETED


@pytest.mark.asyncio
async def test_multi_status_filter_csv_format(integration_environment):
    """Test filtering comments by multiple statuses using CSV format ?status=1,3."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_csv_multi",
            permalink="https://instagram.com/p/media_csv_multi",
            media_type="IMAGE",
            media_url="https://cdn.test/csv_multi.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        # Create comments with various statuses
        for i, status in enumerate(["PENDING", "PROCESSING", "COMPLETED", "FAILED", "RETRY"]):
            comment = InstagramComment(
                id=f"comment_csv_{status.lower()}",
                media_id=media.id,
                user_id=f"user_{i}",
                username=f"user{i}",
                text=f"{status} comment",
                created_at=now_db_utc(),
                raw_data={},
            )
            session.add(comment)
            session.add(CommentClassification(
                comment_id=comment.id,
                type="question / inquiry",
                processing_status=status,
            ))
        await session.commit()

    # Filter using CSV format: PROCESSING (2) and FAILED (4)
    response = await client.get(
        "/api/v1/media/media_csv_multi/comments?status=2,4",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()

    assert data["meta"]["total"] == 2
    statuses = {comment["classification"]["processing_status"] for comment in data["payload"]}
    assert statuses == {2, 4}


@pytest.mark.asyncio
async def test_multi_status_filter_mixed_formats(integration_environment):
    """Test combining array and CSV formats: ?status[]=1&status=3,4."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_mixed_format",
            permalink="https://instagram.com/p/media_mixed_format",
            media_type="IMAGE",
            media_url="https://cdn.test/mixed.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        for i, status in enumerate(["PENDING", "PROCESSING", "COMPLETED", "FAILED", "RETRY"]):
            comment = InstagramComment(
                id=f"comment_mixed_{i}",
                media_id=media.id,
                user_id=f"user_{i}",
                username=f"user{i}",
                text=f"Comment {i}",
                created_at=now_db_utc(),
                raw_data={},
            )
            session.add(comment)
            session.add(CommentClassification(
                comment_id=comment.id,
                type="positive feedback",
                processing_status=status,
            ))
        await session.commit()

    # Mix formats: array (1) + CSV (3,4) = PENDING, COMPLETED, FAILED
    response = await client.get(
        "/api/v1/media/media_mixed_format/comments?status[]=1&status=3,4",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()

    assert data["meta"]["total"] == 3
    statuses = {comment["classification"]["processing_status"] for comment in data["payload"]}
    assert statuses == {1, 3, 4}


@pytest.mark.asyncio
async def test_multi_status_filter_all_statuses(integration_environment):
    """Test filtering with all 5 status codes."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_all_statuses",
            permalink="https://instagram.com/p/media_all_statuses",
            media_type="IMAGE",
            media_url="https://cdn.test/all_statuses.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        for i, status in enumerate(["PENDING", "PROCESSING", "COMPLETED", "FAILED", "RETRY"]):
            comment = InstagramComment(
                id=f"comment_all_{status.lower()}",
                media_id=media.id,
                user_id=f"user_{i}",
                username=f"user{i}",
                text=f"{status} test",
                created_at=now_db_utc(),
                raw_data={},
            )
            session.add(comment)
            session.add(CommentClassification(
                comment_id=comment.id,
                type="question / inquiry",
                processing_status=status,
            ))
        await session.commit()

    # Request all statuses: 1,2,3,4,5
    response = await client.get(
        "/api/v1/media/media_all_statuses/comments?status=1,2,3,4,5",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()

    assert data["meta"]["total"] == 5
    statuses = {comment["classification"]["processing_status"] for comment in data["payload"]}
    assert statuses == {1, 2, 3, 4, 5}


@pytest.mark.asyncio
async def test_multi_status_filter_empty_result(integration_environment):
    """Test multi-status filter that matches no comments."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_empty_filter",
            permalink="https://instagram.com/p/media_empty_filter",
            media_type="IMAGE",
            media_url="https://cdn.test/empty.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        # Only create COMPLETED comments
        for i in range(3):
            comment = InstagramComment(
                id=f"comment_only_completed_{i}",
                media_id=media.id,
                user_id=f"user_{i}",
                username=f"user{i}",
                text=f"Completed {i}",
                created_at=now_db_utc(),
                raw_data={},
            )
            session.add(comment)
            session.add(CommentClassification(
                comment_id=comment.id,
                type="positive feedback",
                processing_status="COMPLETED",
            ))
        await session.commit()

    # Filter for PENDING and FAILED (none exist)
    response = await client.get(
        "/api/v1/media/media_empty_filter/comments?status[]=1&status[]=4",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()

    assert data["meta"]["total"] == 0
    assert len(data["payload"]) == 0


@pytest.mark.asyncio
async def test_multi_status_filter_duplicate_statuses(integration_environment):
    """Test that duplicate status values are handled correctly."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_duplicate_status",
            permalink="https://instagram.com/p/media_duplicate_status",
            media_type="IMAGE",
            media_url="https://cdn.test/duplicate.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        comment = InstagramComment(
            id="comment_dup_pending",
            media_id=media.id,
            user_id="user",
            username="user",
            text="Pending",
            created_at=now_db_utc(),
            raw_data={},
        )
        session.add(comment)
        session.add(CommentClassification(
            comment_id=comment.id,
            type="question / inquiry",
            processing_status="PENDING",
        ))
        await session.commit()

    # Duplicate status 1 multiple times
    response = await client.get(
        "/api/v1/media/media_duplicate_status/comments?status[]=1&status[]=1&status=1,1",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()

    # Should still return only 1 comment (duplicates ignored)
    assert data["meta"]["total"] == 1
    assert data["payload"][0]["classification"]["processing_status"] == 1


@pytest.mark.asyncio
async def test_multi_status_filter_invalid_status_in_list(integration_environment):
    """Test that invalid status code in list returns error."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_invalid_multi",
            permalink="https://instagram.com/p/media_invalid_multi",
            media_type="IMAGE",
            media_url="https://cdn.test/invalid_multi.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.commit()

    # Mix valid (1, 3) with invalid (999)
    response = await client.get(
        "/api/v1/media/media_invalid_multi/comments?status[]=1&status[]=999&status[]=3",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 400
    data = response.json()
    assert data["meta"]["error"]["code"] == 4006


@pytest.mark.asyncio
async def test_multi_status_filter_with_pagination(integration_environment):
    """Test multi-status filtering combined with pagination."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_multi_pagination",
            permalink="https://instagram.com/p/media_multi_pagination",
            media_type="IMAGE",
            media_url="https://cdn.test/multi_page.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        # Create 15 PENDING and 10 COMPLETED comments
        for i in range(15):
            comment = InstagramComment(
                id=f"comment_page_pending_{i}",
                media_id=media.id,
                user_id=f"user_p_{i}",
                username=f"user{i}",
                text=f"Pending {i}",
                created_at=now_db_utc(),
                raw_data={},
            )
            session.add(comment)
            session.add(CommentClassification(
                comment_id=comment.id,
                type="question / inquiry",
                processing_status="PENDING",
            ))

        for i in range(10):
            comment = InstagramComment(
                id=f"comment_page_completed_{i}",
                media_id=media.id,
                user_id=f"user_c_{i}",
                username=f"userc{i}",
                text=f"Completed {i}",
                created_at=now_db_utc(),
                raw_data={},
            )
            session.add(comment)
            session.add(CommentClassification(
                comment_id=comment.id,
                type="positive feedback",
                processing_status="COMPLETED",
            ))

        await session.commit()

    # Page 1: Filter PENDING + COMPLETED, 10 per page
    response = await client.get(
        "/api/v1/media/media_multi_pagination/comments?status[]=1&status[]=3&per_page=10&page=1",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()

    assert data["meta"]["total"] == 25  # 15 + 10
    assert data["meta"]["page"] == 1
    assert data["meta"]["per_page"] == 10
    assert len(data["payload"]) == 10

    # Page 2
    response = await client.get(
        "/api/v1/media/media_multi_pagination/comments?status[]=1&status[]=3&per_page=10&page=2",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()

    assert data["meta"]["page"] == 2
    assert len(data["payload"]) == 10

    # Page 3 (last 5)
    response = await client.get(
        "/api/v1/media/media_multi_pagination/comments?status[]=1&status[]=3&per_page=10&page=3",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()

    assert data["meta"]["page"] == 3
    assert len(data["payload"]) == 5


@pytest.mark.asyncio
async def test_multi_status_filter_whitespace_handling(integration_environment):
    """Test that whitespace in CSV values is handled correctly."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_whitespace",
            permalink="https://instagram.com/p/media_whitespace",
            media_type="IMAGE",
            media_url="https://cdn.test/whitespace.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        for status in ["PENDING", "COMPLETED"]:
            comment = InstagramComment(
                id=f"comment_ws_{status.lower()}",
                media_id=media.id,
                user_id="user",
                username="user",
                text=status,
                created_at=now_db_utc(),
                raw_data={},
            )
            session.add(comment)
            session.add(CommentClassification(
                comment_id=comment.id,
                type="question / inquiry",
                processing_status=status,
            ))
        await session.commit()

    # CSV with spaces: " 1 , 3 "
    response = await client.get(
        "/api/v1/media/media_whitespace/comments?status= 1 , 3 ",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()

    assert data["meta"]["total"] == 2
    statuses = {comment["classification"]["processing_status"] for comment in data["payload"]}
    assert statuses == {1, 3}


@pytest.mark.asyncio
async def test_multi_status_filter_non_numeric_csv(integration_environment):
    """Test that non-numeric values in CSV return error."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_non_numeric",
            permalink="https://instagram.com/p/media_non_numeric",
            media_type="IMAGE",
            media_url="https://cdn.test/non_numeric.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.commit()

    # CSV with non-numeric: "1,invalid,3"
    response = await client.get(
        "/api/v1/media/media_non_numeric/comments?status=1,invalid,3",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 400
    data = response.json()
    assert data["meta"]["error"]["code"] == 4006


@pytest.mark.asyncio
async def test_multi_status_filter_empty_csv_values(integration_environment):
    """Test handling of empty values in CSV (e.g., '1,,3')."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_empty_csv",
            permalink="https://instagram.com/p/media_empty_csv",
            media_type="IMAGE",
            media_url="https://cdn.test/empty_csv.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        for status in ["PENDING", "COMPLETED"]:
            comment = InstagramComment(
                id=f"comment_empty_{status.lower()}",
                media_id=media.id,
                user_id="user",
                username="user",
                text=status,
                created_at=now_db_utc(),
                raw_data={},
            )
            session.add(comment)
            session.add(CommentClassification(
                comment_id=comment.id,
                type="question / inquiry",
                processing_status=status,
            ))
        await session.commit()

    # CSV with empty values: "1,,3"
    response = await client.get(
        "/api/v1/media/media_empty_csv/comments?status=1,,3",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()

    # Empty values should be ignored, process 1 and 3
    assert data["meta"]["total"] == 2
    statuses = {comment["classification"]["processing_status"] for comment in data["payload"]}
    assert statuses == {1, 3}


@pytest.mark.asyncio
async def test_multi_status_filter_single_value_array(integration_environment):
    """Test array format with single value ?status[]=1."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    async with session_factory() as session:
        media = Media(
            id="media_single_array",
            permalink="https://instagram.com/p/media_single_array",
            media_type="IMAGE",
            media_url="https://cdn.test/single.jpg",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)

        for status in ["PENDING", "COMPLETED"]:
            comment = InstagramComment(
                id=f"comment_single_{status.lower()}",
                media_id=media.id,
                user_id="user",
                username="user",
                text=status,
                created_at=now_db_utc(),
                raw_data={},
            )
            session.add(comment)
            session.add(CommentClassification(
                comment_id=comment.id,
                type="question / inquiry",
                processing_status=status,
            ))
        await session.commit()

    # Single value in array format
    response = await client.get(
        "/api/v1/media/media_single_array/comments?status[]=1",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()

    assert data["meta"]["total"] == 1
    assert data["payload"][0]["classification"]["processing_status"] == 1


