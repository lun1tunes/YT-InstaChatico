"""
Unit tests for PollYouTubeCommentsUseCase.

Verifies that recent videos are fetched using configured settings and that the
use case executes end-to-end without raising when polling YouTube comments.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.config import settings
from core.use_cases.poll_youtube_comments import PollYouTubeCommentsUseCase


@pytest.mark.unit
@pytest.mark.use_case
class TestPollYouTubeCommentsUseCase:
    """Tests for polling YouTube comments."""

    async def test_execute_uses_channel_settings(
        self,
        db_session,
        media_factory,
    ):
        """Ensure we fetch recent videos with configured poll limits and no NameError."""
        # Arrange: mock YouTube service responses
        youtube_service = MagicMock()
        youtube_service.list_channel_videos = AsyncMock(
            return_value={"items": [{"id": {"videoId": "video_1"}}]}
        )
        youtube_service.list_comment_threads = AsyncMock(return_value={"items": []})

        # Persist media to avoid None path
        media = await media_factory(media_id="video_1")
        youtube_media_service = MagicMock()
        youtube_media_service.get_or_create_video = AsyncMock(return_value=media)

        task_queue = MagicMock()

        comment_repo = MagicMock()
        comment_repo.get_latest_comment_timestamp = AsyncMock(return_value=None)
        comment_repo.get_by_id = AsyncMock(return_value=None)

        # Factories return pre-configured mocks
        use_case = PollYouTubeCommentsUseCase(
            session=db_session,
            youtube_service=youtube_service,
            youtube_media_service=youtube_media_service,
            task_queue=task_queue,
            comment_repository_factory=lambda session: comment_repo,
            media_repository_factory=lambda session: MagicMock(),
            classification_repository_factory=lambda session: MagicMock(),
        )

        # Act
        result = await use_case.execute()

        # Assert
        youtube_service.list_channel_videos.assert_awaited_once()
        kwargs = youtube_service.list_channel_videos.await_args.kwargs
        assert kwargs["max_results"] == settings.youtube.poll_max_videos
        youtube_media_service.get_or_create_video.assert_awaited_once_with("video_1", db_session)
        youtube_service.list_comment_threads.assert_awaited_once()

        assert result["status"] == "success"
        assert result["video_count"] == 1
