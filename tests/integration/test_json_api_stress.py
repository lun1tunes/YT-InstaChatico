"""Large batch operations and stress tests for JSON API endpoints."""

import time

import pytest
from httpx import AsyncClient

from core.models import CommentClassification, InstagramComment, Media
from core.models.comment_classification import ProcessingStatus
from core.utils.time import now_db_utc
from tests.integration.json_api_helpers import auth_headers


# ============================================================================


@pytest.mark.asyncio
async def test_large_batch_media_pagination_1000_items(integration_environment):
    """Stress test: Paginate through 1000 media items."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    # Setup: Create 1000 media items
    async with session_factory() as session:
        media_batch = []
        for i in range(1000):
            media = Media(
                id=f"media_stress_1000_{i:04d}",
                permalink=f"https://instagram.com/p/stress_1000_{i:04d}",
                media_type="IMAGE",
                media_url=f"https://cdn.test/stress_1000_{i:04d}.jpg",
                owner="stress_test",
                created_at=now_db_utc(),
                updated_at=now_db_utc(),
            )
            media_batch.append(media)
        
        session.add_all(media_batch)
        await session.commit()

    # Test: Fetch first page
    response = await client.get(
        "/api/v1/media?page=1&per_page=30",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["total"] >= 1000
    assert data["meta"]["page"] == 1
    assert data["meta"]["per_page"] == 30
    assert len(data["payload"]) == 30

    # Test: Fetch middle page (page 17 = items 481-510)
    response = await client.get(
        "/api/v1/media?page=17&per_page=30",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["page"] == 17
    assert len(data["payload"]) == 30

    # Test: Fetch last page (1000 / 30 = 34 pages, last page has 10 items)
    last_page = (1000 // 30) + 1
    response = await client.get(
        f"/api/v1/media?page={last_page}&per_page=30",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["page"] == last_page
    assert len(data["payload"]) == 10  # 1000 % 30 = 10

    # Test: Page beyond last should return empty
    response = await client.get(
        f"/api/v1/media?page={last_page + 10}&per_page=30",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["payload"]) == 0


@pytest.mark.asyncio
async def test_large_batch_comments_pagination_2000_items(integration_environment):
    """Stress test: Paginate through 2000 comments on a single media."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    # Setup: Create media with 2000 comments
    async with session_factory() as session:
        media = Media(
            id="media_stress_2000",
            permalink="https://instagram.com/p/media_stress_2000",
            media_type="IMAGE",
            media_url="https://cdn.test/media_stress_2000.jpg",
            owner="stress_test",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.flush()

        comments_batch = []
        for i in range(2000):
            comment = InstagramComment(
                id=f"comment_stress_2000_{i:04d}",
                media_id=media.id,
                user_id=f"user_{i % 100}",  # 100 unique users
                username=f"user_{i % 100}",
                text=f"Comment number {i}",
                created_at=now_db_utc(),
                raw_data={},
            )
            comments_batch.append(comment)
        
        session.add_all(comments_batch)
        await session.commit()

    # Test: Fetch first page (max 100 per page for comments)
    response = await client.get(
        "/api/v1/media/media_stress_2000/comments?page=1&per_page=100",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["total"] == 2000
    assert data["meta"]["page"] == 1
    assert data["meta"]["per_page"] == 100
    assert len(data["payload"]) == 100

    # Test: Fetch middle page (page 10 = items 901-1000)
    response = await client.get(
        "/api/v1/media/media_stress_2000/comments?page=10&per_page=100",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["page"] == 10
    assert len(data["payload"]) == 100

    # Test: Fetch last page (2000 / 100 = 20 pages exactly)
    response = await client.get(
        "/api/v1/media/media_stress_2000/comments?page=20&per_page=100",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["page"] == 20
    assert len(data["payload"]) == 100

    # Test: Small page size with deep pagination
    response = await client.get(
        "/api/v1/media/media_stress_2000/comments?page=50&per_page=25",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["page"] == 50
    assert data["meta"]["per_page"] == 25
    assert len(data["payload"]) == 25


@pytest.mark.asyncio
async def test_large_batch_pagination_consistency(integration_environment):
    """Test pagination consistency: all items retrieved exactly once."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    # Setup: Create 250 media items with known IDs
    async with session_factory() as session:
        media_batch = []
        for i in range(250):
            media = Media(
                id=f"media_consistency_{i:03d}",
                permalink=f"https://instagram.com/p/consistency_{i:03d}",
                media_type="IMAGE",
                media_url=f"https://cdn.test/consistency_{i:03d}.jpg",
                owner="consistency_test",
                created_at=now_db_utc(),
                updated_at=now_db_utc(),
            )
            media_batch.append(media)
        
        session.add_all(media_batch)
        await session.commit()

    # Fetch all items across pages
    all_media_ids = set()
    per_page = 30
    total_pages = (250 // per_page) + 1

    for page in range(1, total_pages + 1):
        response = await client.get(
            f"/api/v1/media?page={page}&per_page={per_page}",
            headers=auth_headers(integration_environment),
        )
        assert response.status_code == 200
        data = response.json()
        
        for media in data["payload"]:
            if media["id"].startswith("media_consistency_"):
                all_media_ids.add(media["id"])

    # Verify: All 250 items retrieved exactly once
    expected_ids = {f"media_consistency_{i:03d}" for i in range(250)}
    retrieved_consistency_ids = {mid for mid in all_media_ids if mid.startswith("media_consistency_")}
    assert len(retrieved_consistency_ids) == 250
    assert retrieved_consistency_ids == expected_ids


@pytest.mark.asyncio
async def test_large_batch_deep_pagination_page_100(integration_environment):
    """Stress test: Deep pagination to page 100."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    # Setup: Create 1500 comments on single media
    async with session_factory() as session:
        media = Media(
            id="media_deep_page",
            permalink="https://instagram.com/p/media_deep_page",
            media_type="IMAGE",
            media_url="https://cdn.test/media_deep_page.jpg",
            owner="deep_test",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.flush()

        comments_batch = []
        for i in range(1500):
            comment = InstagramComment(
                id=f"comment_deep_{i:04d}",
                media_id=media.id,
                user_id=f"user_{i % 50}",
                username=f"user_{i % 50}",
                text=f"Deep comment {i}",
                created_at=now_db_utc(),
                raw_data={},
            )
            comments_batch.append(comment)
        
        session.add_all(comments_batch)
        await session.commit()

    # Test: Page 100 with per_page=15 (fetches items 1486-1500)
    response = await client.get(
        "/api/v1/media/media_deep_page/comments?page=100&per_page=15",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["page"] == 100
    assert data["meta"]["total"] == 1500
    assert len(data["payload"]) == 15  # Items 1486-1500

    # Test: Page 101 should be empty
    response = await client.get(
        "/api/v1/media/media_deep_page/comments?page=101&per_page=15",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["payload"]) == 0


@pytest.mark.asyncio
async def test_large_batch_pagination_with_filters_1000_items(integration_environment):
    """Stress test: Pagination with status filters on 1000+ comments."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    # Setup: Create media with 1200 comments across all statuses
    async with session_factory() as session:
        media = Media(
            id="media_filter_stress",
            permalink="https://instagram.com/p/media_filter_stress",
            media_type="IMAGE",
            media_url="https://cdn.test/media_filter_stress.jpg",
            owner="filter_stress",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.flush()

        # Create 1200 comments: 400 PENDING, 400 PROCESSING, 400 COMPLETED
        comments_batch = []
        statuses = [ProcessingStatus.PENDING, ProcessingStatus.PROCESSING, ProcessingStatus.COMPLETED]
        
        for i in range(1200):
            comment = InstagramComment(
                id=f"comment_filter_stress_{i:04d}",
                media_id=media.id,
                user_id=f"user_{i}",
                username=f"user_{i}",
                text=f"Filter stress comment {i}",
                created_at=now_db_utc(),
                raw_data={},
            )
            comments_batch.append(comment)
            session.add(comment)
        
        await session.flush()

        # Add classifications
        classifications_batch = []
        for i, comment in enumerate(comments_batch):
            classification = CommentClassification(
                comment_id=comment.id,
                processing_status=statuses[i % 3],  # Cycle through statuses
            )
            classifications_batch.append(classification)
        
        session.add_all(classifications_batch)
        await session.commit()

    # Test: Filter by PENDING (should be ~400 items)
    response = await client.get(
        "/api/v1/media/media_filter_stress/comments?status[]=1&page=1&per_page=100",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["total"] == 400
    assert len(data["payload"]) == 100

    # Test: Second page of PENDING
    response = await client.get(
        "/api/v1/media/media_filter_stress/comments?status[]=1&page=2&per_page=100",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["payload"]) == 100

    # Test: Multi-status filter (PENDING + COMPLETED = 800 items)
    response = await client.get(
        "/api/v1/media/media_filter_stress/comments?status[]=1&status[]=3&page=1&per_page=100",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["total"] == 800
    assert len(data["payload"]) == 100

    # Test: Last page of multi-status filter (page 8 = items 701-800)
    response = await client.get(
        "/api/v1/media/media_filter_stress/comments?status[]=1&status[]=3&page=8&per_page=100",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["page"] == 8
    assert len(data["payload"]) == 100


@pytest.mark.asyncio
async def test_large_batch_boundary_conditions(integration_environment):
    """Test pagination boundary conditions with exact multiples."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    # Setup: Create exactly 300 media items (10 pages * 30 per page)
    async with session_factory() as session:
        media_batch = []
        for i in range(300):
            media = Media(
                id=f"media_boundary_{i:03d}",
                permalink=f"https://instagram.com/p/boundary_{i:03d}",
                media_type="IMAGE",
                media_url=f"https://cdn.test/boundary_{i:03d}.jpg",
                owner="boundary_test",
                created_at=now_db_utc(),
                updated_at=now_db_utc(),
            )
            media_batch.append(media)
        
        session.add_all(media_batch)
        await session.commit()

    # Test: Page 10 should have exactly 30 items (last full page)
    response = await client.get(
        "/api/v1/media?page=10&per_page=30",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()
    boundary_items = [m for m in data["payload"] if m["id"].startswith("media_boundary_")]
    assert len(boundary_items) == 30

    # Test: Page 11 should be empty
    response = await client.get(
        "/api/v1/media?page=11&per_page=30",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()
    boundary_items = [m for m in data["payload"] if m["id"].startswith("media_boundary_")]
    assert len(boundary_items) == 0


@pytest.mark.asyncio
async def test_large_batch_performance_sequential_pages(integration_environment):
    """Performance test: Sequential access through 50 pages."""
    import time
    
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    # Setup: Create 1000 comments
    async with session_factory() as session:
        media = Media(
            id="media_performance",
            permalink="https://instagram.com/p/media_performance",
            media_type="IMAGE",
            media_url="https://cdn.test/media_performance.jpg",
            owner="performance_test",
            created_at=now_db_utc(),
            updated_at=now_db_utc(),
        )
        session.add(media)
        await session.flush()

        comments_batch = []
        for i in range(1000):
            comment = InstagramComment(
                id=f"comment_perf_{i:04d}",
                media_id=media.id,
                user_id=f"user_{i}",
                username=f"user_{i}",
                text=f"Performance comment {i}",
                created_at=now_db_utc(),
                raw_data={},
            )
            comments_batch.append(comment)
        
        session.add_all(comments_batch)
        await session.commit()

    # Test: Fetch 50 pages sequentially (20 items per page)
    start_time = time.time()
    pages_fetched = 0
    total_items = 0

    for page in range(1, 51):
        response = await client.get(
            f"/api/v1/media/media_performance/comments?page={page}&per_page=20",
            headers=auth_headers(integration_environment),
        )
        assert response.status_code == 200
        data = response.json()
        total_items += len(data["payload"])
        pages_fetched += 1

    elapsed = time.time() - start_time

    # Verify: All pages fetched successfully
    assert pages_fetched == 50
    assert total_items == 1000

    # Performance check: Should complete in reasonable time (< 10 seconds for 50 requests)
    # This is a very generous limit for integration tests
    assert elapsed < 10.0, f"Sequential pagination took {elapsed:.2f}s, expected < 10s"


@pytest.mark.asyncio
async def test_large_batch_empty_pages_beyond_data(integration_environment):
    """Test requesting pages far beyond available data."""
    client: AsyncClient = integration_environment["client"]
    session_factory = integration_environment["session_factory"]

    # Setup: Create only 50 media items
    async with session_factory() as session:
        media_batch = []
        for i in range(50):
            media = Media(
                id=f"media_sparse_{i:02d}",
                permalink=f"https://instagram.com/p/sparse_{i:02d}",
                media_type="IMAGE",
                media_url=f"https://cdn.test/sparse_{i:02d}.jpg",
                owner="sparse_test",
                created_at=now_db_utc(),
                updated_at=now_db_utc(),
            )
            media_batch.append(media)
        
        session.add_all(media_batch)
        await session.commit()

    # Test: Page 1000 (far beyond available data)
    response = await client.get(
        "/api/v1/media?page=1000&per_page=30",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["page"] == 1000
    sparse_items = [m for m in data["payload"] if m["id"].startswith("media_sparse_")]
    assert len(sparse_items) == 0  # No items on this page

    # Test: Page 10000
    response = await client.get(
        "/api/v1/media?page=10000&per_page=30",
        headers=auth_headers(integration_environment),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["page"] == 10000
    assert len([m for m in data["payload"] if m["id"].startswith("media_sparse_")]) == 0
