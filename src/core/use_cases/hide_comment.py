"""Hide comment use case - handles comment hiding business logic."""

import logging
from typing import Any, Callable, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from ..interfaces.services import IInstagramService
from ..utils.decorators import handle_task_errors
from ..utils.time import now_db_utc
from ..interfaces.repositories import ICommentRepository

logger = logging.getLogger(__name__)


class HideCommentUseCase:
    """
    Use case for hiding Instagram comments.

    Follows Dependency Inversion Principle - depends on IInstagramService protocol.
    """

    def __init__(
        self,
        session: AsyncSession,
        instagram_service: IInstagramService,
        comment_repository_factory: Callable[..., ICommentRepository],
    ):
        """
        Initialize use case with dependencies.

        Args:
            session: Database session
            instagram_service: Service implementing IInstagramService protocol
            comment_repository_factory: Factory producing CommentRepository instances
        """
        self.session = session
        self.comment_repo: ICommentRepository = comment_repository_factory(session=session)
        self.instagram_service = instagram_service

    @handle_task_errors()
    async def execute(self, comment_id: str, hide: bool = True, initiator: str = "manual") -> Dict[str, Any]:
        """Execute hide/unhide comment use case."""
        logger.info(f"Starting hide/unhide comment | comment_id={comment_id} | hide={hide}")

        # 1. Get comment
        comment = await self.comment_repo.get_by_id(comment_id)
        if not comment:
            logger.error(f"Comment not found | comment_id={comment_id} | operation=hide_comment")
            return {"status": "error", "reason": f"Comment {comment_id} not found"}

        previous_state = bool(comment.is_hidden)
        logger.debug(
            "Hide comment request prepared | comment_id=%s | previous_state=%s | target_state=%s",
            comment_id,
            previous_state,
            hide,
        )

        # 2. Check current state
        if comment.is_hidden == hide:
            status = "hidden" if hide else "visible"
            logger.info(f"Comment already in desired state | comment_id={comment_id} | status={status}")
            return {
                "status": "skipped",
                "reason": f"Comment already {status}",
                "is_hidden": comment.is_hidden,
            }

        # 3. Hide/unhide via Instagram API
        logger.info(f"Calling Instagram API to hide comment | comment_id={comment_id} | hide={hide}")
        result = await self.instagram_service.hide_comment(comment_id, hide=hide)

        if not result.get("success"):
            error_payload = result.get("error")
            error_info = error_payload
            if isinstance(error_payload, dict):
                error_info = error_payload.get("error", error_payload)

            is_transient = False
            retry_after = None
            error_message = "Failed to hide comment"

            if isinstance(error_info, dict):
                is_transient = bool(error_info.get("is_transient")) or error_info.get("code") in {1, 2}
                retry_after = error_info.get("retry_after")
                if error_info.get("message"):
                    error_message = error_info["message"]
            elif isinstance(error_info, str):
                error_message = error_info

            if is_transient:
                logger.warning(
                    "Transient Instagram API error while hiding comment | comment_id=%s | hide=%s | error=%s",
                    comment_id,
                    hide,
                    error_payload,
                )
                retry_payload: Dict[str, Any] = {
                    "status": "retry",
                    "reason": error_message,
                }
                try:
                    if retry_after is not None:
                        retry_payload["retry_after"] = float(retry_after)
                except (TypeError, ValueError):
                    pass
                return retry_payload

            logger.error(
                f"Failed to hide comment via API | comment_id={comment_id} | "
                f"hide={hide} | error={error_payload or 'Failed to hide comment'}"
            )
            return {
                "status": "error",
                "reason": error_payload or "Failed to hide comment",
                "api_response": result,
            }

        # 4. Update database
        logger.info(f"Updating comment hidden status in database | comment_id={comment_id} | hide={hide}")
        comment.is_hidden = hide
        comment.hidden_at = now_db_utc() if hide else None
        comment.hidden_by_ai = hide and initiator == "ai"
        await self.session.commit()

        logger.info(
            "Comment hidden status updated | comment_id=%s | previous_state=%s | target_state=%s | resulting_state=%s",
            comment_id,
            previous_state,
            hide,
            comment.is_hidden,
        )

        return {
            "status": "success",
            "action": "hidden" if hide else "unhidden",
            "is_hidden": comment.is_hidden,
            "hidden_at": comment.hidden_at.isoformat() if comment.hidden_at else None,
            "api_response": result,
        }
