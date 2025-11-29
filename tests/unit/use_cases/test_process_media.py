"""
Unit tests for ProcessMediaUseCase and AnalyzeMediaUseCase.

Tests cover:
- ProcessMediaUseCase: media fetching and creation
- AnalyzeMediaUseCase: image analysis with AI
- Edge cases: media not found, already exists, no images
- Error handling and status tracking
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.use_cases.process_media import ProcessMediaUseCase, AnalyzeMediaUseCase
from core.utils.time import now_db_utc


@pytest.mark.unit
@pytest.mark.use_case
class TestProcessMediaUseCase:
    """Test ProcessMediaUseCase methods."""

    async def test_execute_new_media_success(self, db_session):
        """Test successfully creating new media."""
        # Arrange
        from core.models.media import Media
        new_media = Media(
            id="media_1",
            permalink="https://instagram.com/p/test",
            username="testuser",
            media_type="IMAGE",
            comments_count=10,
            like_count=100,
        )

        # Mock services
        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=new_media)

        # Mock repository
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=None)

        # Create use case
        use_case = ProcessMediaUseCase(
            session=db_session,
            media_service=mock_media_service,
            analysis_service=MagicMock(),
            media_repository_factory=lambda session: mock_media_repo,
        )

        # Act
        result = await use_case.execute(media_id="media_1")

        # Assert
        assert result.status == "success"
        assert result.media_id == "media_1"
        assert result.action == "created"
        assert result.media["id"] == "media_1"
        assert result.media["username"] == "testuser"
        assert result.media["media_type"] == "IMAGE"
        assert result.media["comments_count"] == 10
        assert result.media["like_count"] == 100

        # Verify service called
        mock_media_service.get_or_create_media.assert_awaited_once_with("media_1", db_session)

    async def test_execute_existing_media(self, db_session, media_factory):
        """Test handling existing media."""
        # Arrange
        existing_media = await media_factory(
            media_id="media_existing",
            username="existing_user",
            media_type="VIDEO",
        )

        # Mock repository
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=existing_media)

        # Create use case
        use_case = ProcessMediaUseCase(
            session=db_session,
            media_service=MagicMock(),
            analysis_service=MagicMock(),
            media_repository_factory=lambda session: mock_media_repo,
        )

        # Act
        result = await use_case.execute(media_id="media_existing")

        # Assert
        assert result.status == "success"
        assert result.media_id == "media_existing"
        assert result.action == "already_exists"
        assert result.media["username"] == "existing_user"

    async def test_execute_api_fetch_failed(self, db_session):
        """Test handling when Instagram API fetch fails."""
        # Mock services
        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=None)

        # Mock repository
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=None)

        # Create use case
        use_case = ProcessMediaUseCase(
            session=db_session,
            media_service=mock_media_service,
            analysis_service=MagicMock(),
            media_repository_factory=lambda session: mock_media_repo,
        )

        # Act
        result = await use_case.execute(media_id="media_failed")

        # Assert
        assert result.status == "error"
        assert result.media_id == "media_failed"
        assert result.reason == "api_fetch_failed"

    async def test_execute_unexpected_exception(self, db_session):
        """Test handling unexpected exceptions."""
        # Mock repository that raises exception
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(side_effect=Exception("Database error"))

        # Create use case
        use_case = ProcessMediaUseCase(
            session=db_session,
            media_service=MagicMock(),
            analysis_service=MagicMock(),
            media_repository_factory=lambda session: mock_media_repo,
        )

        # Act
        result = await use_case.execute(media_id="media_error")

        # Assert
        assert result.status == "error"
        assert result.media_id == "media_error"
        assert "Database error" in result.reason

    async def test_execute_with_created_at(self, db_session):
        """Test that created_at is properly serialized."""
        # Arrange
        from datetime import datetime, timezone
        from core.models.media import Media

        media_time = datetime.now(timezone.utc)
        posted_at = datetime.now(timezone.utc)
        new_media = Media(
            id="media_1",
            permalink="https://instagram.com/p/test",
            username="testuser",
            created_at=media_time,
            posted_at=posted_at.replace(tzinfo=None),
        )

        # Mock services
        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=new_media)

        # Mock repository
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=None)

        # Create use case
        use_case = ProcessMediaUseCase(
            session=db_session,
            media_service=mock_media_service,
            analysis_service=MagicMock(),
            media_repository_factory=lambda session: mock_media_repo,
        )

        # Act
        result = await use_case.execute(media_id="media_1")

        # Assert
        assert result.status == "success"
        assert result.media["created_at"] == media_time.isoformat()
        assert result.media["posted_at"] == posted_at.replace(tzinfo=None).isoformat()

    async def test_execute_with_none_created_at(self, db_session):
        """Test handling when created_at is None."""
        # Arrange
        from core.models.media import Media
        new_media = Media(
            id="media_1",
            permalink="https://instagram.com/p/test",
            username="testuser",
            created_at=None,
            posted_at=None,
        )

        # Mock services
        mock_media_service = MagicMock()
        mock_media_service.get_or_create_media = AsyncMock(return_value=new_media)

        # Mock repository
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=None)

        # Create use case
        use_case = ProcessMediaUseCase(
            session=db_session,
            media_service=mock_media_service,
            analysis_service=MagicMock(),
            media_repository_factory=lambda session: mock_media_repo,
        )

        # Act
        result = await use_case.execute(media_id="media_1")

        # Assert
        assert result.status == "success"
        assert result.media["created_at"] is None
        assert result.media["posted_at"] is None


@pytest.mark.unit
@pytest.mark.use_case
class TestAnalyzeMediaUseCase:
    """Test AnalyzeMediaUseCase methods."""

    async def test_execute_single_image_success(self, db_session, media_factory):
        """Test successfully analyzing single image."""
        # Arrange
        media = await media_factory(
            media_id="media_img",
            media_type="IMAGE",
            media_url="https://example.com/image.jpg",
            caption="Beautiful sunset",
            media_context=None,
            analysis_requested_at=now_db_utc(),
        )

        # Mock analysis service
        mock_analysis_service = MagicMock()
        mock_analysis_service.analyze_media_image = AsyncMock(
            return_value="Analysis: Sunset over ocean with warm colors"
        )

        # Mock repository
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=media)

        # Create use case
        use_case = AnalyzeMediaUseCase(
            session=db_session,
            analysis_service=mock_analysis_service,
            media_repository_factory=lambda session: mock_media_repo,
        )

        # Act
        result = await use_case.execute(media_id="media_img")

        # Assert
        assert result.status == "success"
        assert result.media_id == "media_img"
        assert result.media_context == "Analysis: Sunset over ocean with warm colors"
        assert result.images_analyzed == 1

        # Verify analysis service called
        mock_analysis_service.analyze_media_image.assert_awaited_once_with(
            media_url="https://example.com/image.jpg",
            caption="Beautiful sunset"
        )

        # Verify media updated
        assert media.media_context == "Analysis: Sunset over ocean with warm colors"
        assert media.analysis_requested_at is None

    async def test_execute_carousel_images_success(self, db_session, media_factory):
        """Test successfully analyzing carousel images."""
        # Arrange
        media = await media_factory(
            media_id="media_carousel",
            media_type="CAROUSEL_ALBUM",
            media_url="https://example.com/carousel_cover.jpg",
            caption="Product showcase",
            media_context=None,
            analysis_requested_at=now_db_utc(),
        )
        media.children_media_urls = [
            "https://example.com/img1.jpg",
            "https://example.com/img2.jpg",
            "https://example.com/img3.jpg",
        ]

        # Mock analysis service
        mock_analysis_service = MagicMock()
        mock_analysis_service.analyze_carousel_images = AsyncMock(
            return_value="Analysis: Product display from multiple angles"
        )

        # Mock repository
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=media)

        # Create use case
        use_case = AnalyzeMediaUseCase(
            session=db_session,
            analysis_service=mock_analysis_service,
            media_repository_factory=lambda session: mock_media_repo,
        )

        # Act
        result = await use_case.execute(media_id="media_carousel")

        # Assert
        assert result.status == "success"
        assert result.media_id == "media_carousel"
        assert result.images_analyzed == 3

        # Verify carousel analysis called
        mock_analysis_service.analyze_carousel_images.assert_awaited_once_with(
            media_urls=[
                "https://example.com/img1.jpg",
                "https://example.com/img2.jpg",
                "https://example.com/img3.jpg",
            ],
            caption="Product showcase"
        )
        assert media.analysis_requested_at is None

    async def test_execute_media_not_found(self, db_session):
        """Test analysis when media doesn't exist."""
        # Mock repository
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=None)

        # Create use case
        use_case = AnalyzeMediaUseCase(
            session=db_session,
            analysis_service=MagicMock(),
            media_repository_factory=lambda session: mock_media_repo,
        )

        # Act
        result = await use_case.execute(media_id="nonexistent")

        # Assert
        assert result.status == "error"
        assert result.media_id == "nonexistent"
        assert "not found" in result.reason.lower()

    async def test_execute_already_analyzed(self, db_session, media_factory):
        """Test skipping analysis when already done."""
        # Arrange
        media = await media_factory(
            media_id="media_analyzed",
            media_type="IMAGE",
            media_url="https://example.com/image.jpg",
            media_context="Already analyzed",
            analysis_requested_at=now_db_utc(),
        )

        # Mock repository
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=media)

        # Mock analysis service (should NOT be called)
        mock_analysis_service = MagicMock()
        mock_analysis_service.analyze_media_image = AsyncMock()

        # Create use case
        use_case = AnalyzeMediaUseCase(
            session=db_session,
            analysis_service=mock_analysis_service,
            media_repository_factory=lambda session: mock_media_repo,
        )

        # Act
        result = await use_case.execute(media_id="media_analyzed")

        # Assert
        assert result.status == "skipped"
        assert result.reason == "already_analyzed"
        assert media.analysis_requested_at is None

        # Verify analysis NOT called
        mock_analysis_service.analyze_media_image.assert_not_called()

    async def test_execute_video_no_analysis(self, db_session, media_factory):
        """Test skipping analysis for video media."""
        # Arrange
        media = await media_factory(
            media_id="media_video",
            media_type="VIDEO",
            media_url="https://example.com/video.mp4",
            media_context=None,
            analysis_requested_at=now_db_utc(),
        )

        # Mock repository
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=media)

        # Create use case
        use_case = AnalyzeMediaUseCase(
            session=db_session,
            analysis_service=MagicMock(),
            media_repository_factory=lambda session: mock_media_repo,
        )

        # Act
        result = await use_case.execute(media_id="media_video")

        # Assert
        assert result.status == "skipped"
        assert result.reason == "no_image_to_analyze"
        assert media.analysis_requested_at is None

    async def test_execute_image_without_url(self, db_session, media_factory):
        """Test skipping analysis when image has no URL."""
        # Arrange
        media = await media_factory(
            media_id="media_no_url",
            media_type="IMAGE",
            media_url=None,
            media_context=None,
            analysis_requested_at=now_db_utc(),
        )

        # Mock repository
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=media)

        # Create use case
        use_case = AnalyzeMediaUseCase(
            session=db_session,
            analysis_service=MagicMock(),
            media_repository_factory=lambda session: mock_media_repo,
        )

        # Act
        result = await use_case.execute(media_id="media_no_url")

        # Assert
        assert result.status == "skipped"
        assert result.reason == "no_image_to_analyze"
        assert media.analysis_requested_at is None

    async def test_execute_analysis_exception(self, db_session, media_factory):
        """Test handling analysis service exception."""
        # Arrange
        media = await media_factory(
            media_id="media_error",
            media_type="IMAGE",
            media_url="https://example.com/image.jpg",
            media_context=None,
            analysis_requested_at=now_db_utc(),
        )

        # Mock analysis service - raises exception
        mock_analysis_service = MagicMock()
        mock_analysis_service.analyze_media_image = AsyncMock(
            side_effect=Exception("Vision API timeout")
        )

        # Mock repository
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=media)

        # Create use case
        use_case = AnalyzeMediaUseCase(
            session=db_session,
            analysis_service=mock_analysis_service,
            media_repository_factory=lambda session: mock_media_repo,
        )

        # Act
        result = await use_case.execute(media_id="media_error")

        # Assert
        assert result.status == "error"
        assert "Vision API timeout" in result.reason

        # Verify media marked as failed
        assert media.media_context == "ANALYSIS_FAILED"
        assert media.analysis_requested_at is None

    async def test_execute_analysis_returns_none(self, db_session, media_factory):
        """Test handling when analysis service returns None."""
        # Arrange
        media = await media_factory(
            media_id="media_none",
            media_type="IMAGE",
            media_url="https://example.com/image.jpg",
            media_context=None,
            analysis_requested_at=now_db_utc(),
        )

        # Mock analysis service - returns None
        mock_analysis_service = MagicMock()
        mock_analysis_service.analyze_media_image = AsyncMock(return_value=None)

        # Mock repository
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=media)

        # Create use case
        use_case = AnalyzeMediaUseCase(
            session=db_session,
            analysis_service=mock_analysis_service,
            media_repository_factory=lambda session: mock_media_repo,
        )

        # Act
        result = await use_case.execute(media_id="media_none")

        # Assert
        assert result.status == "error"
        assert "no result returned" in result.reason.lower()

        # Verify media marked as failed
        assert media.media_context == "ANALYSIS_FAILED"
        assert media.analysis_requested_at is None

    async def test_execute_carousel_exception(self, db_session, media_factory):
        """Test handling carousel analysis exception."""
        # Arrange
        media = await media_factory(
            media_id="media_carousel",
            media_type="CAROUSEL_ALBUM",
            media_url="https://example.com/carousel.jpg",
            media_context=None,
            analysis_requested_at=now_db_utc(),
        )
        media.children_media_urls = ["url1.jpg", "url2.jpg"]

        # Mock analysis service - raises exception
        mock_analysis_service = MagicMock()
        mock_analysis_service.analyze_carousel_images = AsyncMock(
            side_effect=Exception("Carousel analysis failed")
        )

        # Mock repository
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=media)

        # Create use case
        use_case = AnalyzeMediaUseCase(
            session=db_session,
            analysis_service=mock_analysis_service,
            media_repository_factory=lambda session: mock_media_repo,
        )

        # Act
        result = await use_case.execute(media_id="media_carousel")

        # Assert
        assert result.status == "error"
        assert "Carousel analysis failed" in result.reason

        # Verify media marked as failed
        assert media.media_context == "ANALYSIS_FAILED"
        assert media.analysis_requested_at is None

    async def test_execute_unexpected_exception(self, db_session):
        """Test handling unexpected exceptions."""
        # Mock repository that raises exception
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(side_effect=Exception("Unexpected error"))

        # Create use case
        use_case = AnalyzeMediaUseCase(
            session=db_session,
            analysis_service=MagicMock(),
            media_repository_factory=lambda session: mock_media_repo,
        )

        # Act
        result = await use_case.execute(media_id="media_error")

        # Assert
        assert result.status == "error"
        assert "Unexpected error" in result.reason

    async def test_execute_carousel_without_children_urls(self, db_session, media_factory):
        """Test carousel analysis when children_media_urls is None/empty."""
        # Arrange
        media = await media_factory(
            media_id="media_carousel_empty",
            media_type="CAROUSEL_ALBUM",
            media_url="https://example.com/carousel.jpg",
            media_context=None,
        )
        media.children_media_urls = None

        # Mock analysis service
        mock_analysis_service = MagicMock()
        mock_analysis_service.analyze_media_image = AsyncMock(
            return_value="Single image analysis"
        )

        # Mock repository
        mock_media_repo = MagicMock()
        mock_media_repo.get_by_id = AsyncMock(return_value=media)

        # Create use case
        use_case = AnalyzeMediaUseCase(
            session=db_session,
            analysis_service=mock_analysis_service,
            media_repository_factory=lambda session: mock_media_repo,
        )

        # Act
        result = await use_case.execute(media_id="media_carousel_empty")

        # Assert
        assert result.status == "success"
        # Should fallback to single image analysis
        mock_analysis_service.analyze_media_image.assert_awaited_once()
        assert result.images_analyzed == 1
        assert media.analysis_requested_at is None
