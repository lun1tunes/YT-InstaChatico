"""Media processing tasks - refactored using Clean Architecture."""

import logging

from ..celery_app import celery_app
from ..utils.task_helpers import async_task, get_db_session, DEFAULT_RETRY_SCHEDULE, get_retry_delay
from ..container import get_container

logger = logging.getLogger(__name__)


MAX_RETRIES = len(DEFAULT_RETRY_SCHEDULE)


@celery_app.task(bind=True, max_retries=MAX_RETRIES, queue="llm_queue")
@async_task
async def process_media_task(self, media_id: str):
    """Process media - orchestration only."""
    logger.info(f"Task started | media_id={media_id} | retry={self.request.retries}/{self.max_retries}")

    async with get_db_session() as session:
        container = get_container()
        use_case = container.process_media_use_case(session=session)
        result = await use_case.execute(media_id)

        # Handle retry logic - MediaCreateResult is a Pydantic model, not a dict
        if result.status == "retry" and self.request.retries < self.max_retries:
            delay = get_retry_delay(self.request.retries)
            logger.warning(
                f"Retrying task | media_id={media_id} | retry={self.request.retries} | "
                f"reason={result.reason or 'unknown'} | next_delay={delay}s"
            )
            raise self.retry(countdown=delay)

        if result.status == "success":
            logger.info(
                f"Media processed | media_id={media_id} | action={result.action} | "
                f"media_type={result.media.get('media_type') if result.media else 'unknown'}"
            )
        elif result.status == "error":
            logger.error(f"Task failed | media_id={media_id} | reason={result.reason or 'unknown'}")

        logger.info(f"Task completed | media_id={media_id} | status={result.status}")

        # Convert Pydantic model to dict for Celery serialization
        return result.model_dump()


@celery_app.task(bind=True, max_retries=MAX_RETRIES, queue="llm_queue")
@async_task
async def analyze_media_image_task(self, media_id: str):
    """Analyze media image - orchestration only."""
    logger.info(f"Task started | media_id={media_id} | retry={self.request.retries}/{self.max_retries}")

    async with get_db_session() as session:
        container = get_container()
        use_case = container.analyze_media_use_case(session=session)
        result = await use_case.execute(media_id)

        # Handle retry logic - MediaAnalysisResult is a Pydantic model, not a dict
        if result.status == "retry" and self.request.retries < self.max_retries:
            delay = get_retry_delay(self.request.retries)
            logger.warning(
                f"Retrying task | media_id={media_id} | retry={self.request.retries} | "
                f"reason={result.reason or 'unknown'} | next_delay={delay}s"
            )
            raise self.retry(countdown=delay)

        if result.status == "success":
            logger.info(
                f"Media analyzed | media_id={media_id} | images_count={result.images_analyzed} | "
                f"context_length={len(result.media_context) if result.media_context else 0}"
            )
        elif result.status == "skipped":
            logger.info(f"Analysis skipped | media_id={media_id} | reason={result.reason or 'unknown'}")
        elif result.status == "error":
            logger.error(f"Task failed | media_id={media_id} | reason={result.reason or 'unknown'}")

        logger.info(f"Task completed | media_id={media_id} | status={result.status}")

        # Convert Pydantic model to dict for Celery serialization
        return result.model_dump()
