"""
Unit tests for MediaAnalysisService.
"""

import pytest
from unittest.mock import AsyncMock, patch

from core.services.media_analysis_service import MediaAnalysisService


@pytest.mark.unit
@pytest.mark.service
class TestMediaAnalysisService:
    """Test MediaAnalysisService methods."""

    @pytest.fixture
    def media_analysis_service(self):
        """Create MediaAnalysisService instance."""
        return MediaAnalysisService()

    @patch("core.services.media_analysis_service._analyze_image_implementation", new_callable=AsyncMock)
    async def test_analyze_media_image_success(
        self, mock_analyze_impl, media_analysis_service
    ):
        """Test successful media image analysis."""
        # Arrange
        mock_analyze_impl.return_value = "Detailed product description in Russian"
        media_url = "https://example.com/image.jpg"
        caption = "Test caption"

        # Act
        result = await media_analysis_service.analyze_media_image(media_url, caption)

        # Assert
        assert result == "Detailed product description in Russian"
        mock_analyze_impl.assert_called_once()
        call_args = mock_analyze_impl.call_args
        assert call_args[1]["image_url"] == media_url
        assert "Подпись к посту: Test caption" in call_args[1]["additional_context"]

    @patch("core.services.media_analysis_service._analyze_image_implementation", new_callable=AsyncMock)
    async def test_analyze_media_image_without_caption(
        self, mock_analyze_impl, media_analysis_service
    ):
        """Test media image analysis without caption."""
        # Arrange
        mock_analyze_impl.return_value = "Product description"
        media_url = "https://example.com/image.jpg"

        # Act
        result = await media_analysis_service.analyze_media_image(media_url, caption=None)

        # Assert
        assert result == "Product description"
        mock_analyze_impl.assert_called_once()
        call_args = mock_analyze_impl.call_args
        assert "Подпись к посту" not in call_args[1]["additional_context"]

    @patch("core.services.media_analysis_service._analyze_image_implementation", new_callable=AsyncMock)
    async def test_analyze_media_image_empty_result(
        self, mock_analyze_impl, media_analysis_service
    ):
        """Test media image analysis with empty result."""
        # Arrange
        mock_analyze_impl.return_value = ""
        media_url = "https://example.com/image.jpg"

        # Act
        result = await media_analysis_service.analyze_media_image(media_url)

        # Assert
        assert result is None

    @patch("core.services.media_analysis_service._analyze_image_implementation", new_callable=AsyncMock)
    async def test_analyze_media_image_error_result(
        self, mock_analyze_impl, media_analysis_service
    ):
        """Test media image analysis with error message."""
        # Arrange
        mock_analyze_impl.return_value = "Ошибка: Failed to analyze image"
        media_url = "https://example.com/image.jpg"

        # Act
        result = await media_analysis_service.analyze_media_image(media_url)

        # Assert
        assert result is None

    @patch("core.services.media_analysis_service._analyze_image_implementation", new_callable=AsyncMock)
    async def test_analyze_media_image_exception(
        self, mock_analyze_impl, media_analysis_service
    ):
        """Test media image analysis handles exceptions."""
        # Arrange
        mock_analyze_impl.side_effect = Exception("API Error")
        media_url = "https://example.com/image.jpg"

        # Act
        result = await media_analysis_service.analyze_media_image(media_url)

        # Assert
        assert result is None

    @patch("core.services.media_analysis_service._analyze_image_implementation", new_callable=AsyncMock)
    async def test_analyze_carousel_images_success(
        self, mock_analyze_impl, media_analysis_service
    ):
        """Test successful carousel images analysis."""
        # Arrange
        mock_analyze_impl.side_effect = [
            "First image description",
            "Second image description",
            "Third image description"
        ]
        media_urls = [
            "https://example.com/img1.jpg",
            "https://example.com/img2.jpg",
            "https://example.com/img3.jpg"
        ]
        caption = "Carousel caption"

        # Act
        result = await media_analysis_service.analyze_carousel_images(media_urls, caption)

        # Assert
        assert result is not None
        assert "Пост-карусель из 3 изображений" in result
        assert "[Изображение 1]: First image description" in result
        assert "[Изображение 2]: Second image description" in result
        assert "[Изображение 3]: Third image description" in result
        assert mock_analyze_impl.call_count == 3

    @patch("core.services.media_analysis_service._analyze_image_implementation", new_callable=AsyncMock)
    async def test_analyze_carousel_images_without_caption(
        self, mock_analyze_impl, media_analysis_service
    ):
        """Test carousel analysis without caption."""
        # Arrange
        mock_analyze_impl.return_value = "Image description"
        media_urls = ["https://example.com/img1.jpg", "https://example.com/img2.jpg"]

        # Act
        result = await media_analysis_service.analyze_carousel_images(media_urls, caption=None)

        # Assert
        assert result is not None
        assert "Пост-карусель из 2 изображений" in result
        # Verify caption not in context
        for call in mock_analyze_impl.call_args_list:
            assert "Подпись к карусели" not in call[1]["additional_context"]

    @patch("core.services.media_analysis_service._analyze_image_implementation", new_callable=AsyncMock)
    async def test_analyze_carousel_images_empty_list(
        self, mock_analyze_impl, media_analysis_service
    ):
        """Test carousel analysis with empty media list."""
        # Arrange
        media_urls = []

        # Act
        result = await media_analysis_service.analyze_carousel_images(media_urls)

        # Assert
        assert result is None
        mock_analyze_impl.assert_not_called()

    @patch("core.services.media_analysis_service._analyze_image_implementation", new_callable=AsyncMock)
    async def test_analyze_carousel_images_partial_failure(
        self, mock_analyze_impl, media_analysis_service
    ):
        """Test carousel analysis with some images failing."""
        # Arrange
        mock_analyze_impl.side_effect = [
            "First image description",
            Exception("Network error"),
            "Third image description"
        ]
        media_urls = [
            "https://example.com/img1.jpg",
            "https://example.com/img2.jpg",
            "https://example.com/img3.jpg"
        ]

        # Act
        result = await media_analysis_service.analyze_carousel_images(media_urls)

        # Assert
        assert result is not None
        assert "[Изображение 1]: First image description" in result
        assert "[Изображение 2]" not in result  # Failed image not included
        assert "[Изображение 3]: Third image description" in result
        assert mock_analyze_impl.call_count == 3

    @patch("core.services.media_analysis_service._analyze_image_implementation", new_callable=AsyncMock)
    async def test_analyze_carousel_images_all_failures(
        self, mock_analyze_impl, media_analysis_service
    ):
        """Test carousel analysis when all images fail."""
        # Arrange
        mock_analyze_impl.side_effect = [
            Exception("Error 1"),
            Exception("Error 2"),
            Exception("Error 3")
        ]
        media_urls = [
            "https://example.com/img1.jpg",
            "https://example.com/img2.jpg",
            "https://example.com/img3.jpg"
        ]

        # Act
        result = await media_analysis_service.analyze_carousel_images(media_urls)

        # Assert
        assert result is None
        assert mock_analyze_impl.call_count == 3

    @patch("core.services.media_analysis_service._analyze_image_implementation", new_callable=AsyncMock)
    async def test_analyze_carousel_images_error_messages(
        self, mock_analyze_impl, media_analysis_service
    ):
        """Test carousel analysis filters out error messages."""
        # Arrange
        mock_analyze_impl.side_effect = [
            "Valid description",
            "Ошибка: Failed to process",
            "Another valid description"
        ]
        media_urls = [
            "https://example.com/img1.jpg",
            "https://example.com/img2.jpg",
            "https://example.com/img3.jpg"
        ]

        # Act
        result = await media_analysis_service.analyze_carousel_images(media_urls)

        # Assert
        assert result is not None
        assert "[Изображение 1]: Valid description" in result
        assert "[Изображение 2]" not in result  # Error message filtered
        assert "[Изображение 3]: Another valid description" in result

    @patch("core.services.media_analysis_service._analyze_image_implementation")
    async def test_analyze_carousel_images_context_includes_index(
        self, mock_analyze_impl, media_analysis_service
    ):
        """Test that carousel analysis includes image index in context."""
        # Arrange
        mock_analyze_impl.return_value = "Description"
        media_urls = [
            "https://example.com/img1.jpg",
            "https://example.com/img2.jpg"
        ]

        # Act
        await media_analysis_service.analyze_carousel_images(media_urls)

        # Assert
        assert mock_analyze_impl.call_count == 2
        # Check first call has index 1
        first_call_context = mock_analyze_impl.call_args_list[0][1]["additional_context"]
        assert "изображение 1 из 2" in first_call_context
        # Check second call has index 2
        second_call_context = mock_analyze_impl.call_args_list[1][1]["additional_context"]
        assert "изображение 2 из 2" in second_call_context

    @patch("core.services.media_analysis_service._analyze_image_implementation")
    async def test_analyze_carousel_images_exception_in_gather(
        self, mock_analyze_impl, media_analysis_service
    ):
        """Test carousel analysis handles exceptions during parallel execution."""
        # Arrange
        async def mock_error(*args, **kwargs):
            raise RuntimeError("Unexpected error")

        mock_analyze_impl.side_effect = mock_error
        media_urls = ["https://example.com/img1.jpg"]

        # Act
        result = await media_analysis_service.analyze_carousel_images(media_urls)

        # Assert
        assert result is None

    @patch("core.services.media_analysis_service._analyze_image_implementation", new_callable=AsyncMock)
    @patch("core.services.media_analysis_service.asyncio.gather")
    async def test_analyze_carousel_images_general_exception(
        self, mock_gather, mock_analyze_impl, media_analysis_service
    ):
        """Test carousel analysis handles general exceptions in try block."""
        # Arrange
        async def fake_gather(*tasks, **kwargs):
            for task in tasks:
                try:
                    await task
                except Exception:
                    pass
            raise Exception("Unexpected system error")

        mock_gather.side_effect = fake_gather
        mock_analyze_impl.return_value = "desc"
        media_urls = ["https://example.com/img1.jpg"]

        # Act
        result = await media_analysis_service.analyze_carousel_images(media_urls)

        # Assert
        assert result is None

    @patch("core.services.media_analysis_service._analyze_image_implementation")
    async def test_analyze_single_image_success(self, mock_analyze_impl, media_analysis_service):
        """Test _analyze_single_image helper method."""
        # Arrange
        mock_analyze_impl.return_value = "Image analysis result"
        media_url = "https://example.com/image.jpg"
        context = "Test context"

        # Act
        result = await media_analysis_service._analyze_single_image(media_url, context)

        # Assert
        assert result == "Image analysis result"
        mock_analyze_impl.assert_called_once_with(
            image_url=media_url,
            additional_context=context
        )

    @patch("core.services.media_analysis_service._analyze_image_implementation")
    async def test_analyze_single_image_exception(
        self, mock_analyze_impl, media_analysis_service
    ):
        """Test _analyze_single_image raises exceptions."""
        # Arrange
        mock_analyze_impl.side_effect = Exception("Analysis failed")

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            await media_analysis_service._analyze_single_image("url", "context")

        assert "Analysis failed" in str(exc_info.value)
