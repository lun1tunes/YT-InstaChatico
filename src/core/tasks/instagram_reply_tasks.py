"""Instagram reply and hide tasks - refactored using Clean Architecture."""

import logging
import math

from ..celery_app import celery_app
from ..utils.task_helpers import async_task, get_db_session, DEFAULT_RETRY_SCHEDULE, get_retry_delay
from ..utils.lock_manager import LockManager
from ..config import settings
from ..container import get_container

logger = logging.getLogger(__name__)

# Initialize lock manager
lock_manager = LockManager(settings.celery.broker_url)


MAX_RETRIES = len(DEFAULT_RETRY_SCHEDULE)


@celery_app.task(bind=True, max_retries=MAX_RETRIES)
@async_task
async def send_instagram_reply_task(self, comment_id: str, answer_text: str = None):
    """Send Instagram reply - orchestration only."""
    task_id = self.request.id
    logger.info(
        f"Task started: send_instagram_reply_task | task_id={task_id} | "
        f"comment_id={comment_id} | has_answer_text={bool(answer_text)} | "
        f"retry={self.request.retries}/{self.max_retries}"
    )

    async with lock_manager.acquire(f"instagram_reply_lock:{comment_id}") as acquired:
        if not acquired:
            logger.warning(
                f"Task skipped: send_instagram_reply_task | task_id={task_id} | "
                f"comment_id={comment_id} | reason=lock_already_acquired"
            )
            return {"status": "skipped", "reason": "already_processing"}

        try:
            async with get_db_session() as session:
                container = get_container()
                use_case = container.send_reply_use_case(session=session)
                result = await use_case.execute(
                    comment_id=comment_id, reply_text=answer_text, use_generated_answer=not answer_text
                )

                if result["status"] == "retry" and self.request.retries < self.max_retries:
                    fallback_delay = get_retry_delay(self.request.retries)
                    retry_after = result.get("retry_after")
                    countdown = fallback_delay
                    if retry_after is not None:
                        countdown = max(int(math.ceil(retry_after)), fallback_delay)
                    logger.warning(
                        f"Task retry scheduled: send_instagram_reply_task | task_id={task_id} | "
                        f"comment_id={comment_id} | retry={self.request.retries + 1}/{self.max_retries} | countdown={countdown}s"
                    )
                    raise self.retry(countdown=countdown)

                logger.info(
                    f"Task completed: send_instagram_reply_task | task_id={task_id} | "
                    f"comment_id={comment_id} | status={result['status']}"
                )
                return result
        except Exception as exc:
            logger.error(
                f"Task failed: send_instagram_reply_task | task_id={task_id} | "
                f"comment_id={comment_id} | retry={self.request.retries}/{self.max_retries} | error={str(exc)}",
                exc_info=True
            )
            raise


@celery_app.task(bind=True, max_retries=MAX_RETRIES)
@async_task
async def hide_instagram_comment_task(self, comment_id: str):
    """Hide Instagram comment - orchestration only."""
    task_id = self.request.id
    logger.info(
        f"Task started: hide_instagram_comment_task | task_id={task_id} | "
        f"comment_id={comment_id} | retry={self.request.retries}/{self.max_retries}"
    )

    async with lock_manager.acquire(f"instagram_hide_lock:{comment_id}") as acquired:
        if not acquired:
            logger.warning(
                f"Task skipped: hide_instagram_comment_task | task_id={task_id} | "
                f"comment_id={comment_id} | reason=lock_already_acquired"
            )
            return {"status": "skipped", "reason": "already_processing"}

        try:
            async with get_db_session() as session:
                container = get_container()
                use_case = container.hide_comment_use_case(session=session)
                result = await use_case.execute(comment_id, hide=True, initiator="ai")

                if result["status"] == "retry" and self.request.retries < self.max_retries:
                    delay = get_retry_delay(self.request.retries)
                    logger.warning(
                        f"Task retry scheduled: hide_instagram_comment_task | task_id={task_id} | "
                        f"comment_id={comment_id} | retry={self.request.retries + 1}/{self.max_retries} | countdown={delay}s"
                    )
                    raise self.retry(countdown=delay)

                logger.info(
                    f"Task completed: hide_instagram_comment_task | task_id={task_id} | "
                    f"comment_id={comment_id} | status={result['status']}"
                )
                return result
        except Exception as exc:
            logger.error(
                f"Task failed: hide_instagram_comment_task | task_id={task_id} | "
                f"comment_id={comment_id} | retry={self.request.retries}/{self.max_retries} | error={str(exc)}",
                exc_info=True
            )
            raise
