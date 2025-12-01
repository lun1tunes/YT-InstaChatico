"""YouTube polling and moderation/reply tasks."""

import logging

from core.celery_app import celery_app
from core.utils.task_helpers import async_task, get_db_session, DEFAULT_RETRY_SCHEDULE, get_retry_delay
from core.container import get_container
from core.config import settings

logger = logging.getLogger(__name__)

MAX_RETRIES = len(DEFAULT_RETRY_SCHEDULE)


@celery_app.task(bind=True, max_retries=MAX_RETRIES, queue="youtube_queue")
@async_task
async def poll_youtube_comments_task(self, channel_id: str | None = None):
    """Poll YouTube comments for configured channel or provided channel_id."""
    target_channel = channel_id or settings.youtube.channel_id
    task_id = self.request.id
    logger.info(
        "Task started: poll_youtube_comments_task | task_id=%s | channel_id=%s | retry=%s/%s",
        task_id,
        target_channel,
        self.request.retries,
        self.max_retries,
    )

    async with get_db_session() as session:
        container = get_container()

        # Guard: skip polling if no OAuth tokens and no env refresh token
        oauth_service = container.oauth_token_service(session=session)
        tokens = await oauth_service.get_tokens("google")
        if not tokens and not settings.youtube.refresh_token:
            logger.warning("YouTube polling skipped: no OAuth tokens configured and no refresh token in env.")
            return {"status": "skipped", "reason": "missing_auth", "video_count": 0, "new_comments": 0, "api_errors": 0}

        use_case = container.poll_youtube_comments_use_case(session=session)
        result = await use_case.execute(channel_id=target_channel)

        status = result.get("status")
        if status == "quota_exceeded":
            logger.warning(
                "YouTube quota exceeded; skipping retries for poll task | task_id=%s | reason=%s",
                task_id,
                result.get("reason"),
            )
        elif status == "error" and self.request.retries < self.max_retries:
            delay = get_retry_delay(self.request.retries)
            logger.warning(
                "Task retry scheduled: poll_youtube_comments_task | task_id=%s | reason=%s | countdown=%ss",
                task_id,
                result.get("reason"),
                delay,
            )
            raise self.retry(countdown=delay)

    logger.info(
        "Task completed: poll_youtube_comments_task | task_id=%s | status=%s | new_comments=%s",
        task_id,
        result.get("status"),
        result.get("new_comments"),
    )
    return result


@celery_app.task(bind=True, max_retries=MAX_RETRIES, queue="youtube_queue")
@async_task
async def send_youtube_reply_task(self, comment_id: str, answer_text: str = None):
    """Send a reply to a YouTube comment."""
    task_id = self.request.id
    logger.info(
        "Task started: send_youtube_reply_task | task_id=%s | comment_id=%s | retry=%s/%s",
        task_id,
        comment_id,
        self.request.retries,
        self.max_retries,
    )

    async with get_db_session() as session:
        container = get_container()
        use_case = container.send_youtube_reply_use_case(session=session)
        result = await use_case.execute(comment_id=comment_id, reply_text=answer_text)

        if result.get("status") == "retry" and self.request.retries < self.max_retries:
            delay = get_retry_delay(self.request.retries)
            logger.warning(
                "Task retry scheduled: send_youtube_reply_task | task_id=%s | comment_id=%s | countdown=%ss",
                task_id,
                comment_id,
                delay,
            )
            raise self.retry(countdown=delay)

    logger.info(
        "Task completed: send_youtube_reply_task | task_id=%s | comment_id=%s | status=%s",
        task_id,
        comment_id,
        result.get("status"),
    )
    return result


@celery_app.task(bind=True, max_retries=MAX_RETRIES, queue="youtube_queue")
@async_task
async def delete_youtube_comment_task(self, comment_id: str):
    """Delete a YouTube comment."""
    task_id = self.request.id
    logger.info(
        "Task started: delete_youtube_comment_task | task_id=%s | comment_id=%s | retry=%s/%s",
        task_id,
        comment_id,
        self.request.retries,
        self.max_retries,
    )

    async with get_db_session() as session:
        container = get_container()
        use_case = container.delete_youtube_comment_use_case(session=session)
        result = await use_case.execute(comment_id)

        if result.get("status") == "retry" and self.request.retries < self.max_retries:
            delay = get_retry_delay(self.request.retries)
            logger.warning(
                "Task retry scheduled: delete_youtube_comment_task | task_id=%s | comment_id=%s | countdown=%ss",
                task_id,
                comment_id,
                delay,
            )
            raise self.retry(countdown=delay)

    logger.info(
        "Task completed: delete_youtube_comment_task | task_id=%s | comment_id=%s | status=%s",
        task_id,
        comment_id,
        result.get("status"),
    )
    return result
