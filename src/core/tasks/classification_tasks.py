"""Classification tasks - refactored using Clean Architecture."""

import logging

from ..celery_app import celery_app
from ..utils.task_helpers import async_task, get_db_session, DEFAULT_RETRY_SCHEDULE, get_retry_delay
from ..container import get_container

logger = logging.getLogger(__name__)


MAX_RETRIES = len(DEFAULT_RETRY_SCHEDULE)

ANSWER_QUEUE_CLASSIFICATIONS = {"question / inquiry"}
DELETE_QUEUE_CLASSIFICATIONS = {"urgent issue / complaint", "toxic / abusive", "critical feedback"}
TELEGRAM_QUEUE_CLASSIFICATIONS = {"urgent issue / complaint", "critical feedback", "partnership proposal"}


@celery_app.task(bind=True, max_retries=MAX_RETRIES)
@async_task
async def classify_comment_task(self, comment_id: str):
    """Classify Instagram comment using AI - orchestration only."""
    logger.info(f"Task started | comment_id={comment_id} | retry={self.request.retries}/{self.max_retries}")

    async with get_db_session() as session:
        container = get_container()
        use_case = container.classify_comment_use_case(session=session)
        result = await use_case.execute(comment_id, retry_count=self.request.retries)

        # Handle retry logic
        if result["status"] == "retry" and self.request.retries < self.max_retries:
            delay = get_retry_delay(self.request.retries)
            logger.warning(
                f"Retrying task | comment_id={comment_id} | retry={self.request.retries} | "
                f"reason={result.get('reason', 'unknown')} | next_delay={delay}s"
            )
            raise self.retry(countdown=delay)

        # Trigger post-classification actions
        if result["status"] == "success":
            logger.info(
                f"Comment classified | comment_id={comment_id} | "
                f"classification={result.get('classification')} | confidence={result.get('confidence')}"
            )
            await _trigger_post_classification_actions(result)
        elif result["status"] == "error":
            logger.error(f"Task failed | comment_id={comment_id} | reason={result.get('reason', 'unknown')}")

        logger.info(f"Task completed | comment_id={comment_id} | status={result['status']}")
        return result


async def _trigger_post_classification_actions(classification_result: dict):
    """
    Trigger follow-up actions based on classification.

    Uses DI container to get task queue - follows SOLID principles.
    """
    comment_id = classification_result["comment_id"]
    classification = (classification_result.get("classification") or "").strip().lower()

    # Get task queue from container
    container = get_container()
    task_queue = container.task_queue()

    # Answer generation for questions
    if classification in ANSWER_QUEUE_CLASSIFICATIONS:
        logger.info(f"Queuing answer task | comment_id={comment_id} | classification={classification}")
        try:
            task_id = task_queue.enqueue(
                "core.tasks.answer_tasks.generate_answer_task",
                comment_id,
            )
            logger.debug(f"Answer task queued | task_id={task_id} | comment_id={comment_id}")
        except Exception as e:
            logger.error(f"Failed to queue answer task | comment_id={comment_id} | error={str(e)}", exc_info=True)

    # Delete toxic/complaint comments (YouTube)
    if classification in DELETE_QUEUE_CLASSIFICATIONS:
        logger.info(f"Queuing delete task | comment_id={comment_id} | classification={classification}")
        try:
            task_id = task_queue.enqueue(
                "core.tasks.youtube_tasks.delete_youtube_comment_task",
                comment_id,
            )
            logger.debug(f"Delete task queued | task_id={task_id} | comment_id={comment_id}")
        except Exception as e:
            logger.error(f"Failed to queue delete task | comment_id={comment_id} | error={str(e)}", exc_info=True)

    # Telegram notifications (excluding toxic)
    if classification in TELEGRAM_QUEUE_CLASSIFICATIONS:
        logger.info(f"Queuing Telegram task | comment_id={comment_id} | classification={classification}")
        try:
            task_id = task_queue.enqueue(
                "core.tasks.telegram_tasks.send_telegram_notification_task",
                comment_id,
            )
            logger.debug(f"Telegram task queued | task_id={task_id} | comment_id={comment_id}")
        except Exception as e:
            logger.error(f"Failed to queue Telegram task | comment_id={comment_id} | error={str(e)}", exc_info=True)


@celery_app.task
@async_task
async def retry_failed_classifications():
    """Retry failed classifications."""
    return await retry_failed_classifications_async()


async def retry_failed_classifications_async():
    """
    Async retry failed classifications.

    Uses DI container to get task queue - follows SOLID principles.
    """
    from ..repositories.classification import ClassificationRepository

    async with get_db_session() as session:
        try:
            # Get task queue from container
            container = get_container()
            task_queue = container.task_queue()

            # Use repository instead of direct SQL
            classification_repo = ClassificationRepository(session)
            retry_classifications = await classification_repo.get_pending_retries()

            logger.info(f"Starting classification retry | count={len(retry_classifications)}")

            for classification in retry_classifications:
                task_queue.enqueue(
                    "core.tasks.classification_tasks.classify_comment_task",
                    classification.comment_id,
                )
                logger.debug(f"Retry queued | comment_id={classification.comment_id}")

            logger.info(f"Classification retry completed | queued_count={len(retry_classifications)}")
            return {"retried_count": len(retry_classifications)}
        except Exception as e:
            logger.error(f"Classification retry failed | error={str(e)}", exc_info=True)
            return {"error": str(e)}
