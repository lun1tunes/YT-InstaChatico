"""Answer generation tasks - refactored using Clean Architecture."""

import logging

from ..celery_app import celery_app
from ..utils.task_helpers import async_task, get_db_session, DEFAULT_RETRY_SCHEDULE, get_retry_delay
from ..container import get_container

logger = logging.getLogger(__name__)


MAX_RETRIES = len(DEFAULT_RETRY_SCHEDULE)


@celery_app.task(bind=True, max_retries=MAX_RETRIES)
@async_task
async def generate_answer_task(self, comment_id: str):
    """Generate answer for YouTube comment question - orchestration only."""
    logger.info(f"Task started | comment_id={comment_id} | retry={self.request.retries}/{self.max_retries}")

    async with get_db_session() as session:
        container = get_container()
        use_case = container.generate_answer_use_case(session=session)
        result = await use_case.execute(comment_id, retry_count=self.request.retries)

        # Handle retry logic
        if result["status"] == "retry" and self.request.retries < self.max_retries:
            delay = get_retry_delay(self.request.retries)
            logger.warning(
                f"Retrying task | comment_id={comment_id} | retry={self.request.retries} | "
                f"reason={result.get('reason', 'unknown')} | next_delay={delay}s"
            )
            raise self.retry(countdown=delay)

        # Trigger reply if answer generated successfully
        if result["status"] == "success" and result.get("answer"):
            logger.info(
                f"Answer generated | comment_id={comment_id} | confidence={result.get('confidence')} | "
                f"quality_score={result.get('quality_score')} | triggering_reply=True"
            )
            try:
                task_queue = container.task_queue()
                task_id = task_queue.enqueue(
                    "core.tasks.instagram_reply_tasks.send_instagram_reply_task",
                    comment_id,
                    result["answer"],
                )
                logger.debug(f"Reply task queued | task_id={task_id} | comment_id={comment_id}")
            except Exception as e:
                logger.error(
                    f"Failed to queue reply | comment_id={comment_id} | error={str(e)}",
                    exc_info=True
                )
        elif result["status"] == "error":
            logger.error(
                f"Task failed | comment_id={comment_id} | reason={result.get('reason', 'unknown')}"
            )

        logger.info(f"Task completed | comment_id={comment_id} | status={result['status']}")
        return result
