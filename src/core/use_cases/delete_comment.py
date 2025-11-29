"""Delete comment use case - orchestrates Instagram deletion and soft delete in DB."""

import logging
from typing import Any, Dict, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from ..interfaces.repositories import ICommentRepository
from ..interfaces.services import IInstagramService
from ..utils.decorators import handle_task_errors

logger = logging.getLogger(__name__)


class DeleteCommentUseCase:
    """
    Use case for deleting Instagram comments.

    Ensures Instagram API deletion succeeds before soft-deleting the comment
    and all descendants in the database.
    """

    def __init__(
        self,
        session: AsyncSession,
        instagram_service: IInstagramService,
        comment_repository_factory: Callable[..., ICommentRepository],
    ):
        self.session = session
        self.instagram_service = instagram_service
        self.comment_repo: ICommentRepository = comment_repository_factory(session=session)

    @handle_task_errors()
    async def execute(self, comment_id: str, initiator: str = "manual") -> Dict[str, Any]:
        logger.info("Starting delete comment flow | comment_id=%s", comment_id)

        comment = await self.comment_repo.get_by_id(comment_id)
        if not comment:
            logger.error("Comment not found | comment_id=%s | operation=delete_comment", comment_id)
            return {"status": "error", "reason": f"Comment {comment_id} not found"}

        if comment.is_deleted:
            logger.info("Comment already marked deleted | comment_id=%s", comment_id)
            return {"status": "skipped", "reason": "Comment already deleted"}

        api_result = await self.instagram_service.delete_comment(comment_id)
        if not api_result.get("success"):
            error_payload = api_result.get("error")
            logger.error(
                "Failed to delete comment via Instagram API | comment_id=%s | error=%s",
                comment_id,
                error_payload,
            )
            error_reason: str = "Failed to delete comment"
            if isinstance(error_payload, dict):
                nested_error = error_payload.get("error") if isinstance(error_payload.get("error"), dict) else None
                message = (
                    error_payload.get("message")
                    or (nested_error.get("message") if nested_error else None)
                )
                if message:
                    error_reason = message
            elif isinstance(error_payload, str):
                error_reason = error_payload

            return {
                "status": "error",
                "reason": error_reason,
                "api_response": api_result,
                "details": error_payload,
            }

        affected = await self.comment_repo.mark_deleted_with_descendants(
            comment_id, deleted_by_ai=(initiator == "ai")
        )
        await self.session.commit()

        logger.info(
            "Comment soft-deleted in database | comment_id=%s | affected_rows=%s",
            comment_id,
            affected,
        )

        return {
            "status": "success",
            "deleted_count": affected,
            "api_response": api_result,
        }
