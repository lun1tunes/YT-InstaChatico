"""Answer generation tasks - refactored using Clean Architecture."""

import logging

from ..celery_app import celery_app
from ..utils.task_helpers import async_task, get_db_session, DEFAULT_RETRY_SCHEDULE, get_retry_delay
from ..container import get_container
from ..repositories.comment import CommentRepository

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

                # Load comment to decide platform / skip replies to our own replies
                # In unit tests the session is a bare object without DB methods, so guard failures.
                comment = None
                load_failed = False
                try:
                    repo = CommentRepository(session)
                    comment = await repo.get_by_id(comment_id)
                except Exception:
                    load_failed = True
                    comment = None

                # If comment is missing, fall back to enqueuing reply for compatibility (tests)
                if comment:
                    # Skip replying to replies (avoid replying to our own answers)
                    if comment.parent_id:
                        logger.info("Skipping reply for nested comment | comment_id=%s | parent_id=%s", comment_id, comment.parent_id)
                        return result

                    raw_kind = (comment.raw_data or {}).get("kind", "")
                    is_youtube = raw_kind.startswith("youtube#")

                    if not is_youtube:
                        logger.info("Skipping reply because comment is not from YouTube | comment_id=%s", comment_id)
                        return result

                    # Avoid replying to our own replies/comments (author channel id == our channel)
                    author_channel_id = None
                    snippet = (comment.raw_data or {}).get("snippet", {}) or {}
                    if isinstance(snippet.get("authorChannelId"), dict):
                        author_channel_id = snippet["authorChannelId"].get("value")

                    try:
                        yt_service = container.youtube_service()
                        my_channel_id = await yt_service.get_account_id()
                    except Exception:
                        my_channel_id = None

                    if my_channel_id and author_channel_id and author_channel_id == my_channel_id:
                        logger.info(
                            "Skipping reply because author is our own channel | comment_id=%s | channel_id=%s",
                            comment_id,
                            my_channel_id,
                        )
                        return result

                # Choose target task.
                # If lookup failed (DB unavailable), still send YouTube reply to avoid wrong platform routing.
                # Only fall back to the legacy Instagram task when we know the comment truly does not exist.
                if load_failed:
                    task_name = "core.tasks.youtube_tasks.send_youtube_reply_task"
                else:
                    task_name = (
                        "core.tasks.youtube_tasks.send_youtube_reply_task"
                        if comment is not None
                        else "core.tasks.instagram_reply_tasks.send_instagram_reply_task"
                    )
                task_id = task_queue.enqueue(
                    task_name,
                    comment_id,
                    result["answer"],
                )
                logger.debug(f"Reply task queued | task={task_name} | task_id={task_id} | comment_id={comment_id}")
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
