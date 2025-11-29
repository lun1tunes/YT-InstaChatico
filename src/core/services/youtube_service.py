"""YouTube Data API service: comments, replies, video metadata."""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any, Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError

from core.config import settings

logger = logging.getLogger(__name__)

YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"


class YouTubeService:
    """Lightweight async wrapper around YouTube Data API v3."""

    def __init__(
        self,
        *,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        refresh_token: Optional[str] = None,
        api_key: Optional[str] = None,
        channel_id: Optional[str] = None,
    ) -> None:
        self.client_id = client_id or settings.youtube.client_id
        self.client_secret = client_secret or settings.youtube.client_secret
        self.refresh_token = refresh_token or settings.youtube.refresh_token
        self.api_key = api_key or settings.youtube.api_key
        self.channel_id = channel_id or settings.youtube.channel_id
        self._credentials: Credentials | None = None
        self._youtube: Resource | None = None

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _build_credentials(self) -> Credentials:
        creds = Credentials(
            None,
            refresh_token=self.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=[YOUTUBE_SCOPE],
        )
        return creds

    def _get_youtube(self) -> Resource:
        if self._credentials is None:
            self._credentials = self._build_credentials()

        # Refresh if needed
        if not self._credentials.valid:
            try:
                self._credentials.refresh(Request())
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to refresh YouTube credentials: %s", exc, exc_info=True)
                raise

        if self._youtube is None:
            self._youtube = build("youtube", "v3", credentials=self._credentials, cache_discovery=False)

        return self._youtube

    async def _run(self, func, *args, **kwargs) -> Any:
        """Run blocking Google client calls in a thread."""
        return await asyncio.to_thread(func, *args, **kwargs)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    async def list_channel_videos(
        self,
        channel_id: Optional[str] = None,
        page_token: Optional[str] = None,
        max_results: int = 50,
    ) -> dict:
        """List videos for a channel (latest first)."""
        youtube = self._get_youtube()

        def _call():
            return (
                youtube.search()
                .list(
                    part="id",
                    channelId=channel_id or self.channel_id,
                    type="video",
                    order="date",
                    maxResults=max_results,
                    pageToken=page_token,
                )
                .execute()
            )

        return await self._execute(_call)

    async def list_comment_threads(
        self,
        video_id: str,
        page_token: Optional[str] = None,
        max_results: int = 50,
        order: str = "time",
    ) -> dict:
        """Fetch top-level comment threads (includes replies summary)."""
        youtube = self._get_youtube()

        def _call():
            return (
                youtube.commentThreads()
                .list(
                    part="snippet,replies",
                    videoId=video_id,
                    textFormat="plainText",
                    order=order,
                    maxResults=max_results,
                    pageToken=page_token,
                )
                .execute()
            )

        return await self._execute(_call)

    async def reply_to_comment(self, parent_id: str, text: str) -> dict:
        """Post a reply to an existing comment."""
        youtube = self._get_youtube()

        body = {"snippet": {"parentId": parent_id, "textOriginal": text}}

        def _call():
            return youtube.comments().insert(part="snippet", body=body).execute()

        return await self._execute(_call)

    async def delete_comment(self, comment_id: str) -> None:
        """Delete a comment (moderation action)."""
        youtube = self._get_youtube()

        def _call():
            return youtube.comments().delete(id=comment_id).execute()

        await self._execute(_call)

    async def get_video_details(self, video_id: str) -> dict:
        """Fetch video metadata + stats for media context."""
        youtube = self._get_youtube()

        def _call():
            return (
                youtube.videos()
                .list(
                    part="snippet,statistics,contentDetails",
                    id=video_id,
                )
                .execute()
            )

        return await self._execute(_call)

    async def _execute(self, call):
        """Execute Google API call with uniform error handling."""
        try:
            return await self._run(call)
        except HttpError as http_err:
            logger.error("YouTube API error: %s | status=%s", http_err, getattr(http_err, "status_code", None))
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("YouTube service unexpected error: %s", exc, exc_info=True)
            raise
