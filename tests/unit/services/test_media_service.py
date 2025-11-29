"""
Unit tests for MediaService.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from core.services.media_service import MediaService
from core.models import Media
from core.utils.time import now_db_utc


@pytest.mark.unit
@pytest.mark.service
class TestMediaService:
    """Test MediaService methods."""

    @pytest.fixture
    def mock_instagram_service(self):
        """Create mock Instagram service."""
        return AsyncMock()

    @pytest.fixture
    def mock_task_queue(self):
        """Create mock task queue."""
        return MagicMock()

    @pytest.fixture
    def media_service(self, mock_instagram_service, mock_task_queue):
        """Create MediaService instance with mocked dependencies."""
        return MediaService(
            instagram_service=mock_instagram_service,
            task_queue=mock_task_queue
        )

    async def test_get_or_create_media_exists_in_db(
        self, media_service, mock_task_queue, db_session
    ):
        """Test get_or_create_media when media already exists in database."""
        # Arrange
        existing_media = Media(
            id="media_123",
            permalink="https://instagram.com/p/VIDEO123",
            media_type="VIDEO",
            media_url="https://example.com/video.mp4",
            caption="Test video"
        )
        db_session.add(existing_media)
        await db_session.commit()

        # Act
        media = await media_service.get_or_create_media("media_123", db_session)

        # Assert
        assert media is not None
        assert media.id == "media_123"
        assert media.media_type == "VIDEO"
        # Should not queue analysis for VIDEO type
        mock_task_queue.enqueue.assert_not_called()

    async def test_get_or_create_media_exists_queues_analysis(
        self, media_service, mock_task_queue, db_session
    ):
        """Test that existing media without context queues analysis task."""
        # Arrange
        existing_media = Media(
            id="media_456",
            permalink="https://instagram.com/p/IMG456",
            media_type="IMAGE",
            media_url="https://example.com/image.jpg",
            caption="Test image",
            media_context=None  # No context yet
        )
        db_session.add(existing_media)
        await db_session.commit()

        # Act
        media = await media_service.get_or_create_media("media_456", db_session)

        # Assert
        assert media is not None
        assert media.id == "media_456"
        mock_task_queue.enqueue.assert_called_once_with(
            "core.tasks.media_tasks.analyze_media_image_task",
            "media_456"
        )
        assert media.analysis_requested_at is not None

    async def test_get_or_create_media_exists_with_context_no_queue(
        self, media_service, mock_task_queue, db_session
    ):
        """Test that existing media with context doesn't queue analysis."""
        # Arrange
        existing_media = Media(
            id="media_789",
            permalink="https://instagram.com/p/IMG789",
            media_type="IMAGE",
            media_url="https://example.com/image.jpg",
            caption="Test image",
            media_context="Existing context"
        )
        db_session.add(existing_media)
        await db_session.commit()

        # Act
        media = await media_service.get_or_create_media("media_789", db_session)

        # Assert
        assert media is not None
        assert media.media_context == "Existing context"
        mock_task_queue.enqueue.assert_not_called()

    async def test_get_or_create_media_existing_queue_failure(
        self, media_service, mock_task_queue, db_session
    ):
        """Test that task queue failure for existing media is handled gracefully."""
        # Arrange
        existing_media = Media(
            id="media_999",
            permalink="https://instagram.com/p/IMG999",
            media_type="IMAGE",
            media_url="https://example.com/image.jpg",
            caption="Test image",
            media_context=None
        )
        db_session.add(existing_media)
        await db_session.commit()

        mock_task_queue.enqueue.side_effect = Exception("Queue error")

        # Act
        media = await media_service.get_or_create_media("media_999", db_session)

        # Assert
        assert media is not None
        assert media.id == "media_999"
        # Should return media despite queue failure
        mock_task_queue.enqueue.assert_called_once()
        assert media.analysis_requested_at is None

    async def test_get_or_create_media_skips_when_analysis_already_requested(
        self, media_service, mock_task_queue, db_session
    ):
        """Do not enqueue analysis again when a request was already queued."""
        existing_media = Media(
            id="media_200",
            permalink="https://instagram.com/p/IMG200",
            media_type="IMAGE",
            media_url="https://example.com/image.jpg",
            caption="Test image",
            media_context=None,
            analysis_requested_at=now_db_utc(),
        )
        db_session.add(existing_media)
        await db_session.commit()

        media = await media_service.get_or_create_media("media_200", db_session)

        assert media is not None
        mock_task_queue.enqueue.assert_not_called()

    async def test_get_or_create_media_fetches_from_api(
        self, media_service, mock_instagram_service, mock_task_queue, db_session
    ):
        """Test get_or_create_media fetches from Instagram API when not in DB."""
        # Arrange
        mock_instagram_service.get_media_info = AsyncMock(return_value={
            "success": True,
            "media_info": {
                "id": "new_media_123",
                "media_type": "IMAGE",
                "media_url": "https://example.com/new_image.jpg",
                "caption": "New image caption",
                "permalink": "https://instagram.com/p/ABC123",
                "comments_count": 10,
                "like_count": 100,
                "timestamp": "2025-01-15T10:00:00Z"
            }
        })

        # Act
        media = await media_service.get_or_create_media("new_media_123", db_session)

        # Assert
        assert media is not None
        assert media.id == "new_media_123"
        assert media.media_type == "IMAGE"
        assert media.caption == "New image caption"
        assert media.posted_at is not None
        mock_instagram_service.get_media_info.assert_called_once_with("new_media_123")
        mock_task_queue.enqueue.assert_called_once()
        assert media.analysis_requested_at is not None

    async def test_refresh_media_urls_success(
        self, media_service, mock_instagram_service, db_session
    ):
        """Refreshing media URLs updates the stored media record."""
        existing_media = Media(
            id="media_refresh",
            permalink="https://instagram.com/p/refresh",
            media_type="IMAGE",
            media_url="https://old-url",
            caption="Old",
        )
        db_session.add(existing_media)
        await db_session.commit()

        mock_instagram_service.get_media_info = AsyncMock(
            return_value={
                "success": True,
                "media_info": {
                    "id": "media_refresh",
                    "media_type": "IMAGE",
                    "media_url": "https://new-url",
                    "caption": "New caption",
                    "permalink": "https://instagram.com/p/refresh",
                    "timestamp": "2025-01-01T00:00:00Z",
                    "children": {"data": []},
                },
            }
        )

        refreshed = await media_service.refresh_media_urls("media_refresh", db_session)

        assert refreshed is not None
        assert refreshed.media_url == "https://new-url"
        assert refreshed.caption == "New caption"
        assert refreshed.posted_at is not None
        mock_instagram_service.get_media_info.assert_awaited_once_with("media_refresh")

    async def test_refresh_media_urls_failure(
        self, media_service, mock_instagram_service, db_session
    ):
        """When API refresh fails, original media remains unchanged."""
        existing_media = Media(
            id="media_refresh_fail",
            permalink="https://instagram.com/p/refresh",
            media_type="IMAGE",
            media_url="https://old-url",
        )
        db_session.add(existing_media)
        await db_session.commit()

        mock_instagram_service.get_media_info = AsyncMock(
            return_value={"success": False, "error": "invalid"}
        )

        refreshed = await media_service.refresh_media_urls("media_refresh_fail", db_session)

        assert refreshed is None
        stored = await db_session.get(Media, "media_refresh_fail")
        assert stored.media_url == "https://old-url"

    async def test_get_or_create_media_api_failure(
        self, media_service, mock_instagram_service, db_session
    ):
        """Test get_or_create_media handles API failure."""
        # Arrange
        mock_instagram_service.get_media_info = AsyncMock(return_value={
            "success": False,
            "error": "Media not found"
        })

        # Act
        media = await media_service.get_or_create_media("invalid_media", db_session)

        # Assert
        assert media is None
        mock_instagram_service.get_media_info.assert_called_once_with("invalid_media")

    async def test_get_or_create_media_carousel(
        self, media_service, mock_instagram_service, mock_task_queue, db_session
    ):
        """Test get_or_create_media with carousel album."""
        # Arrange
        mock_instagram_service.get_media_info = AsyncMock(return_value={
            "success": True,
            "media_info": {
                "id": "carousel_123",
                "media_type": "CAROUSEL_ALBUM",
                "caption": "Carousel post",
                "permalink": "https://instagram.com/p/CAR123",
                "children": {
                    "data": [
                        {"media_url": "https://example.com/img1.jpg"},
                        {"media_url": "https://example.com/img2.jpg"},
                        {"media_url": "https://example.com/img3.jpg"}
                    ]
                }
            }
        })

        # Act
        media = await media_service.get_or_create_media("carousel_123", db_session)

        # Assert
        assert media is not None
        assert media.media_type == "CAROUSEL_ALBUM"
        assert media.children_media_urls is not None
        assert len(media.children_media_urls) == 3
        assert media.media_url == "https://example.com/img1.jpg"  # First child used
        mock_task_queue.enqueue.assert_called_once()

    async def test_set_comment_status_updates_existing_media(
        self, media_service, mock_instagram_service, db_session
    ):
        """set_comment_status updates DB when API succeeds."""
        mock_instagram_service.set_media_comment_status = AsyncMock(return_value={"success": True})

        media = Media(
            id="media_toggle",
            permalink="https://instagram.com/p/toggle",
            media_type="IMAGE",
            media_url="https://cdn/img.jpg",
            caption="caption",
            is_comment_enabled=True,
        )
        db_session.add(media)
        await db_session.commit()

        result = await media_service.set_comment_status("media_toggle", False, db_session)

        assert result["success"] is True
        refreshed = await db_session.get(Media, "media_toggle")
        assert refreshed.is_comment_enabled is False
        mock_instagram_service.set_media_comment_status.assert_awaited_once_with("media_toggle", False)

    async def test_set_comment_status_returns_api_error(
        self, media_service, mock_instagram_service, db_session
    ):
        """API failure is propagated and DB remains unchanged."""
        mock_instagram_service.set_media_comment_status = AsyncMock(
            return_value={"success": False, "error": "bad"}
        )

        media = Media(
            id="media_toggle2",
            permalink="https://instagram.com/p/toggle2",
            media_type="IMAGE",
            media_url="https://cdn/img2.jpg",
            caption="caption",
            is_comment_enabled=True,
        )
        db_session.add(media)
        await db_session.commit()

        result = await media_service.set_comment_status("media_toggle2", False, db_session)

        assert result["success"] is False
        refreshed = await db_session.get(Media, "media_toggle2")
        assert refreshed.is_comment_enabled is True

    async def test_set_comment_status_media_created_when_missing(
        self, media_service, mock_instagram_service, db_session, monkeypatch
    ):
        """Missing media triggers get_or_create_media helper."""
        mock_instagram_service.set_media_comment_status = AsyncMock(return_value={"success": True})

        new_media = Media(
            id="media_new",
            permalink="https://instagram.com/p/new",
            media_type="IMAGE",
            media_url="https://cdn/new.jpg",
            caption="new",
            is_comment_enabled=True,
        )

        async def fake_get_or_create(media_id, session):
            session.add(new_media)
            await session.flush()
            return new_media

        mock_get_or_create = AsyncMock(side_effect=fake_get_or_create)
        monkeypatch.setattr(media_service, "get_or_create_media", mock_get_or_create)

        result = await media_service.set_comment_status("media_new", False, db_session)

        assert result["success"] is True
        refreshed = await db_session.get(Media, "media_new")
        assert refreshed.is_comment_enabled is False
        mock_get_or_create.assert_awaited_once()

    async def test_set_comment_status_media_missing_failure(
        self, media_service, mock_instagram_service, db_session, monkeypatch
    ):
        """If media cannot be created, method returns error."""
        mock_instagram_service.set_media_comment_status = AsyncMock(return_value={"success": True})
        monkeypatch.setattr(media_service, "get_or_create_media", AsyncMock(return_value=None))

        result = await media_service.set_comment_status("ghost_media", True, db_session)

        assert result["success"] is False
        assert result["error"] == "media_not_found"

    async def test_get_or_create_media_new_queue_failure(
        self, media_service, mock_instagram_service, mock_task_queue, db_session
    ):
        """Test that task queue failure for new media is handled gracefully."""
        # Arrange
        mock_instagram_service.get_media_info = AsyncMock(return_value={
            "success": True,
            "media_info": {
                "id": "new_media_888",
                "media_type": "IMAGE",
                "media_url": "https://example.com/image.jpg",
                "caption": "New image",
                "permalink": "https://instagram.com/p/NEW888",
                "timestamp": "2025-01-15T10:00:00Z"
            }
        })

        mock_task_queue.enqueue.side_effect = Exception("Queue error")

        # Act
        media = await media_service.get_or_create_media("new_media_888", db_session)

        # Assert
        assert media is not None
        assert media.id == "new_media_888"
        # Should return media despite queue failure
        mock_task_queue.enqueue.assert_called_once()

    async def test_get_or_create_media_exception_rollback(
        self, media_service, mock_instagram_service, db_session
    ):
        """Test that get_or_create_media rolls back on exception."""
        # Arrange
        mock_instagram_service.get_media_info = AsyncMock(
            side_effect=Exception("Unexpected error")
        )

        db_session.rollback = AsyncMock()

        # Act
        media = await media_service.get_or_create_media("error_media", db_session)

        # Assert
        assert media is None
        db_session.rollback.assert_called_once()

    async def test_ensure_media_exists_already_exists(
        self, media_service, mock_task_queue, db_session
    ):
        """Test ensure_media_exists when media already in DB."""
        # Arrange
        existing_media = Media(
            id="existing_media",
            permalink="https://instagram.com/p/EXIST",
            media_type="IMAGE",
            caption="Existing"
        )
        db_session.add(existing_media)
        await db_session.commit()

        # Act
        result = await media_service.ensure_media_exists("existing_media", db_session)

        # Assert
        assert result is True
        mock_task_queue.enqueue.assert_not_called()

    async def test_ensure_media_exists_queues_task(
        self, media_service, mock_task_queue, db_session
    ):
        """Test ensure_media_exists queues task when media not found."""
        # Arrange
        # No media in DB

        # Act
        result = await media_service.ensure_media_exists("new_media", db_session)

        # Assert
        assert result is True
        mock_task_queue.enqueue.assert_called_once_with(
            "core.tasks.media_tasks.process_media_task",
            "new_media"
        )

    async def test_ensure_media_exists_handles_exception(
        self, media_service, db_session
    ):
        """Test ensure_media_exists handles exceptions gracefully."""
        # Arrange
        # Force an exception by passing invalid session
        db_session.execute = AsyncMock(side_effect=Exception("Database error"))

        # Act
        result = await media_service.ensure_media_exists("error_media", db_session)

        # Assert
        assert result is False

    def test_extract_carousel_children_urls_success(self, media_service):
        """Test extracting children URLs from carousel."""
        # Arrange
        media_info = {
            "media_type": "CAROUSEL_ALBUM",
            "children": {
                "data": [
                    {"media_url": "https://example.com/img1.jpg"},
                    {"media_url": "https://example.com/img2.jpg"},
                    {"media_url": None},  # Missing URL
                    {"media_url": "https://example.com/img3.jpg"}
                ]
            }
        }

        # Act
        urls = media_service._extract_carousel_children_urls(media_info)

        # Assert
        assert urls is not None
        assert len(urls) == 3  # None is filtered out
        assert "https://example.com/img1.jpg" in urls

    def test_extract_carousel_children_urls_not_carousel(self, media_service):
        """Test extracting URLs from non-carousel returns None."""
        # Arrange
        media_info = {
            "media_type": "IMAGE",
            "media_url": "https://example.com/image.jpg"
        }

        # Act
        urls = media_service._extract_carousel_children_urls(media_info)

        # Assert
        assert urls is None

    def test_extract_carousel_children_urls_no_children(self, media_service):
        """Test extracting URLs from carousel without children."""
        # Arrange
        media_info = {
            "media_type": "CAROUSEL_ALBUM"
        }

        # Act
        urls = media_service._extract_carousel_children_urls(media_info)

        # Assert
        assert urls is None

    def test_extract_carousel_children_urls_empty_data(self, media_service):
        """Test extracting URLs from carousel with empty data list."""
        # Arrange
        media_info = {
            "media_type": "CAROUSEL_ALBUM",
            "children": {
                "data": []
            }
        }

        # Act
        urls = media_service._extract_carousel_children_urls(media_info)

        # Assert
        assert urls is None

    def test_extract_carousel_children_urls_no_valid_urls(self, media_service):
        """Test extracting URLs from carousel with no valid media_url values."""
        # Arrange
        media_info = {
            "media_type": "CAROUSEL_ALBUM",
            "children": {
                "data": [
                    {"media_url": None},
                    {"media_url": None},
                    {"other_field": "value"}  # No media_url field
                ]
            }
        }

        # Act
        urls = media_service._extract_carousel_children_urls(media_info)

        # Assert
        assert urls is None

    def test_parse_posted_at_success(self, media_service):
        """Test parsing valid posted_at string."""
        # Arrange
        timestamp_str = "2025-01-15T10:30:00Z"

        # Act
        dt = media_service._parse_posted_at(timestamp_str)

        # Assert
        assert dt is not None
        assert isinstance(dt, datetime)
        assert dt.year == 2025
        assert dt.month == 1
        assert dt.day == 15
        assert dt.tzinfo is None  # Should be timezone-naive

    def test_parse_posted_at_none(self, media_service):
        """Test parsing None posted_at string."""
        # Act
        dt = media_service._parse_posted_at(None)

        # Assert
        assert dt is None

    def test_parse_posted_at_invalid(self, media_service):
        """Test parsing invalid posted_at string."""
        # Arrange
        invalid_timestamp = "not a timestamp"

        # Act
        dt = media_service._parse_posted_at(invalid_timestamp)

        # Assert
        assert dt is None

    def test_parse_owner_dict(self, media_service):
        """Test parsing owner from dictionary."""
        # Arrange
        owner_data = {"id": "owner_123", "username": "testuser"}

        # Act
        owner_id = media_service._parse_owner(owner_data)

        # Assert
        assert owner_id == "owner_123"

    def test_parse_owner_string(self, media_service):
        """Test parsing owner from string."""
        # Arrange
        owner_data = "owner_456"

        # Act
        owner_id = media_service._parse_owner(owner_data)

        # Assert
        assert owner_id == "owner_456"

    def test_parse_owner_none(self, media_service):
        """Test parsing None owner."""
        # Act
        owner_id = media_service._parse_owner(None)

        # Assert
        assert owner_id is None

    def test_parse_owner_invalid_type(self, media_service):
        """Test parsing owner with invalid type."""
        # Arrange
        owner_data = 12345  # Invalid type

        # Act
        owner_id = media_service._parse_owner(owner_data)

        # Assert
        assert owner_id is None

    async def test_set_comment_status_generic_exception(
        self, media_service, mock_instagram_service, db_session
    ):
        """Test set_comment_status handles generic exceptions properly."""
        # Arrange
        media_id = "media_exception"

        # Mock Instagram service to succeed
        mock_instagram_service.set_media_comment_status.return_value = {
            "success": True
        }

        # Create existing media
        existing_media = Media(
            id=media_id,
            permalink="https://instagram.com/p/TEST",
            media_type="IMAGE",
            is_comment_enabled=True
        )
        db_session.add(existing_media)
        await db_session.commit()

        # Mock session.commit to raise an exception
        original_commit = db_session.commit
        async def mock_commit():
            raise RuntimeError("Database commit failed")
        db_session.commit = mock_commit

        # Act
        result = await media_service.set_comment_status(media_id, False, db_session)

        # Restore original commit
        db_session.commit = original_commit

        # Assert
        assert result["success"] is False
        assert "Database commit failed" in result["error"]
