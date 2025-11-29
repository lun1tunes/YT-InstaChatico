"""Document processing tasks - refactored using Clean Architecture."""

import logging

from core.celery_app import celery_app
from core.utils.task_helpers import async_task, get_db_session, DEFAULT_RETRY_SCHEDULE, get_retry_delay
from core.container import get_container

logger = logging.getLogger(__name__)


MAX_RETRIES = len(DEFAULT_RETRY_SCHEDULE)


@celery_app.task(bind=True, max_retries=MAX_RETRIES, queue="llm_queue")
@async_task
async def process_document_task(self, document_id: str):
    """Process document - orchestration only."""
    task_id = self.request.id
    logger.info(
        f"Task started: process_document_task | task_id={task_id} | "
        f"document_id={document_id} | retry={self.request.retries}/{self.max_retries} | queue=llm_queue"
    )

    try:
        async with get_db_session() as session:
            container = get_container()
            use_case = container.process_document_use_case(session=session)
            result = await use_case.execute(document_id)

            if result["status"] == "retry" and self.request.retries < self.max_retries:
                delay = get_retry_delay(self.request.retries)
                logger.warning(
                    f"Task retry scheduled: process_document_task | task_id={task_id} | "
                    f"document_id={document_id} | retry={self.request.retries + 1}/{self.max_retries} | countdown={delay}s"
                )
                raise self.retry(countdown=delay)

            logger.info(
                f"Task completed: process_document_task | task_id={task_id} | "
                f"document_id={document_id} | status={result['status']}"
            )
            return result
    except Exception as exc:
        logger.error(
            f"Task failed: process_document_task | task_id={task_id} | "
            f"document_id={document_id} | retry={self.request.retries}/{self.max_retries} | error={str(exc)}",
            exc_info=True
        )
        raise
