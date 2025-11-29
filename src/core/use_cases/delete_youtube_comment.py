"""Delete YouTube comment use case."""

from __future__ import annotations

import logging
from typing import Any, Dict, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from core.interfaces.services import IYouTubeService
from core.repositories.comment import CommentRepository
from core.utils.decorators import handle_task_errors

logger = logging.getLogger(__name__)


class DeleteYouTubeCommentUseCase:
    """
    Use case for deleting YouTube comments.
    """

    def __init__(
        self,
        session: AsyncSession,
        youtube_service: IYouTubeService,
        comment_repository_factory: Callable[..., CommentRepository],
    ):
        self.session = session
        self.youtube_service = youtube_service
        self.comment_repo: CommentRepository = comment_repository_factory(session=session)

    @handle_task_errors()
    async def execute(self, comment_id: str, initiator: str = "ai") -> Dict[str, Any]:
        logger.info("Starting delete comment flow (YouTube) | comment_id=%s", comment_id)

        comment = await self.comment_repo.get_by_id(comment_id)
        if not comment:
            logger.error("Comment not found | comment_id=%s | operation=delete_youtube_comment", comment_id)
            return {"status": "error", "reason": f"Comment {comment_id} not found"}

        if comment.is_deleted:
            logger.info("Comment already marked deleted | comment_id=%s", comment_id)
            return {"status": "skipped", "reason": "Comment already deleted"}

        try:
            await self.youtube_service.delete_comment(comment_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to delete comment via YouTube API | comment_id=%s | error=%s", comment_id, exc)
            return {"status": "error", "reason": str(exc)}

        affected = await self.comment_repo.mark_deleted_with_descendants(
            comment_id, deleted_by_ai=(initiator == "ai")
        )
        await self.session.commit()

        logger.info("Comment deleted in DB | comment_id=%s | affected_rows=%s", comment_id, affected)
        return {
            "status": "success",
            "deleted_count": affected,
        }
