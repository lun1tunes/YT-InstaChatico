"""Telegram notification tasks - refactored using Clean Architecture."""

import logging

from ..celery_app import celery_app
from ..use_cases.send_telegram_notification import SendTelegramNotificationUseCase
from ..utils.task_helpers import async_task, get_db_session, DEFAULT_RETRY_SCHEDULE, get_retry_delay
from ..container import get_container

logger = logging.getLogger(__name__)


MAX_RETRIES = len(DEFAULT_RETRY_SCHEDULE)


@celery_app.task(bind=True, max_retries=MAX_RETRIES)
@async_task
async def send_telegram_notification_task(self, comment_id: str):
    """Send Telegram notification - orchestration only."""
    task_id = self.request.id
    logger.info(
        f"Task started: send_telegram_notification_task | task_id={task_id} | "
        f"comment_id={comment_id} | retry={self.request.retries}/{self.max_retries}"
    )

    try:
        async with get_db_session() as session:
            container = get_container()
            use_case = container.send_telegram_notification_use_case(session=session)
            result = await use_case.execute(comment_id)

            if result["status"] == "retry" and self.request.retries < self.max_retries:
                delay = get_retry_delay(self.request.retries)
                logger.warning(
                    f"Task retry scheduled: send_telegram_notification_task | task_id={task_id} | "
                    f"comment_id={comment_id} | retry={self.request.retries + 1}/{self.max_retries} | countdown={delay}s"
                )
                raise self.retry(countdown=delay)

            logger.info(
                f"Task completed: send_telegram_notification_task | task_id={task_id} | "
                f"comment_id={comment_id} | status={result['status']}"
            )
            return result
    except Exception as exc:
        logger.error(
            f"Task failed: send_telegram_notification_task | task_id={task_id} | "
            f"comment_id={comment_id} | retry={self.request.retries}/{self.max_retries} | error={str(exc)}",
            exc_info=True
        )
        raise
