"""Poll YouTube comments and persist them, enqueuing classification tasks."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from core.interfaces.services import IYouTubeService
from core.repositories.comment import CommentRepository
from core.repositories.media import MediaRepository
from core.repositories.classification import ClassificationRepository
from core.models.instagram_comment import InstagramComment
from core.models.comment_classification import CommentClassification
from core.utils.time import now_db_utc

logger = logging.getLogger(__name__)


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return now_db_utc()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return now_db_utc()


class PollYouTubeCommentsUseCase:
    """Fetch latest YouTube comments for channel/videos and queue classification."""

    def __init__(
        self,
        session: AsyncSession,
        youtube_service: IYouTubeService,
        youtube_media_service,
        task_queue,
        comment_repository_factory: Callable[..., CommentRepository],
        media_repository_factory: Callable[..., MediaRepository],
        classification_repository_factory: Callable[..., ClassificationRepository],
    ):
        self.session = session
        self.youtube_service = youtube_service
        self.youtube_media_service = youtube_media_service
        self.task_queue = task_queue
        self.comment_repo = comment_repository_factory(session=session)
        self.media_repo = media_repository_factory(session=session)
        self.classification_repo = classification_repository_factory(session=session)

    async def execute(
        self,
        channel_id: Optional[str] = None,
        video_ids: Optional[Sequence[str]] = None,
        page_token: Optional[str] = None,
    ) -> dict:
        """Poll comments for provided videos or latest channel uploads."""
        try:
            videos = list(video_ids) if video_ids else await self._fetch_recent_video_ids(channel_id, page_token)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to fetch video list | error=%s", exc)
            return {"status": "error", "reason": str(exc)}

        new_comments = 0
        for video_id in videos:
            media = await self.youtube_media_service.get_or_create_video(video_id, self.session)
            if not media:
                continue
            fetched = await self._process_video_comments(video_id)
            new_comments += fetched

        return {"status": "success", "video_count": len(videos), "new_comments": new_comments}

    async def _fetch_recent_video_ids(self, channel_id: Optional[str], page_token: Optional[str]) -> list[str]:
        resp = await self.youtube_service.list_channel_videos(channel_id=channel_id, page_token=page_token)
        ids: list[str] = []
        for item in resp.get("items", []):
            id_block = item.get("id", {})
            video_id = id_block.get("videoId")
            if video_id:
                ids.append(video_id)
        return ids

    async def _process_video_comments(self, video_id: str) -> int:
        page_token = None
        added = 0
        while True:
            resp = await self.youtube_service.list_comment_threads(video_id=video_id, page_token=page_token)
            threads = resp.get("items", [])
            for thread in threads:
                added += await self._persist_thread(thread, video_id)

            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return added

    async def _persist_thread(self, thread: dict, video_id: str) -> int:
        top = thread.get("snippet", {}).get("topLevelComment", {})
        top_snippet = top.get("snippet", {}) if top else {}
        top_id = top.get("id")
        added = 0

        if top_id:
            created = await self._persist_comment(
                comment_id=top_id,
                video_id=video_id,
                snippet=top_snippet,
                parent_id=None,
                raw=top,
            )
            added += int(created)

        # Replies (if expanded)
        for reply in thread.get("replies", {}).get("comments", []) or []:
            reply_snippet = reply.get("snippet", {})
            reply_id = reply.get("id")
            if reply_id:
                created = await self._persist_comment(
                    comment_id=reply_id,
                    video_id=video_id,
                    snippet=reply_snippet,
                    parent_id=top_id,
                    raw=reply,
                )
                added += int(created)

        return added

    async def _persist_comment(
        self,
        comment_id: str,
        video_id: str,
        snippet: dict,
        parent_id: Optional[str],
        raw: dict,
    ) -> bool:
        existing = await self.comment_repo.get_by_id(comment_id)
        if existing:
            return False

        author_channel_id = None
        author_channel_obj = snippet.get("authorChannelId") or {}
        if isinstance(author_channel_obj, dict):
            author_channel_id = author_channel_obj.get("value")

        new_comment = InstagramComment(
            id=comment_id,
            media_id=video_id,
            user_id=author_channel_id or snippet.get("authorDisplayName") or "unknown",
            username=snippet.get("authorDisplayName") or "unknown",
            text=snippet.get("textOriginal") or snippet.get("textDisplay") or "",
            created_at=_parse_datetime(snippet.get("publishedAt")),
            parent_id=parent_id,
            raw_data=raw,
        )
        new_comment.classification = CommentClassification(comment_id=comment_id)

        self.session.add(new_comment)
        await self.session.commit()

        # Enqueue classification
        try:
            self.task_queue.enqueue(
                "core.tasks.classification_tasks.classify_comment_task",
                comment_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to enqueue classification | comment_id=%s | error=%s", comment_id, exc)
        return True
