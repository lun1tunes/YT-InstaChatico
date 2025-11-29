"""
Task queue implementation using Celery.

This adapter decouples business logic from Celery infrastructure.
"""

import logging
from typing import Any, Dict, List, Optional

from celery import Celery
from ..interfaces.services import ITaskQueue
from ..logging_config import trace_id_ctx

logger = logging.getLogger(__name__)


class CeleryTaskQueue(ITaskQueue):
    """Celery-based implementation of ITaskQueue."""

    def __init__(self, celery_app: Celery):
        """
        Initialize with Celery app instance.

        Args:
            celery_app: Celery application instance
        """
        self.celery_app = celery_app

    def enqueue(
        self,
        task_name: str,
        *args,
        countdown: Optional[int] = None,
        **kwargs,
    ) -> str:
        """
        Enqueue a task for background processing.

        Args:
            task_name: Full task name (e.g., "core.tasks.classification_tasks.classify_comment_task")
            *args: Positional arguments for the task
            countdown: Optional delay in seconds before execution
            **kwargs: Keyword arguments for the task

        Returns:
            Task ID
        """
        try:
            trace_id = trace_id_ctx.get()
            logger.debug(
                f"Enqueueing task | name={task_name} | trace_id={trace_id or '-'} | args={args} | kwargs={kwargs}"
            )

            task_kwargs = {}
            if countdown is not None:
                task_kwargs["countdown"] = countdown

            result = self.celery_app.send_task(
                task_name,
                args=args,
                kwargs=kwargs,
                headers={"trace_id": trace_id} if trace_id else None,
                **task_kwargs,
            )

            logger.info(
                "Task enqueued | name=%s | id=%s | trace_id=%s",
                task_name,
                result.id,
                trace_id or "-",
            )
            return result.id

        except Exception as e:
            logger.error(
                "Failed to enqueue task | name=%s | trace_id=%s | error=%s",
                task_name,
                trace_id or "-",
                e,
            )
            raise

    def enqueue_batch(self, tasks: List[Dict[str, Any]]) -> List[str]:
        """
        Enqueue multiple tasks at once.

        Args:
            tasks: List of task dictionaries with 'name', 'args', 'kwargs', and optional 'countdown'

        Returns:
            List of task IDs
        """
        task_ids = []

        for task_info in tasks:
            task_name = task_info["name"]
            args = task_info.get("args", ())
            kwargs = task_info.get("kwargs", {})
            countdown = task_info.get("countdown")

            task_id = self.enqueue(task_name, *args, countdown=countdown, **kwargs)
            task_ids.append(task_id)

        logger.info(f"Enqueued {len(task_ids)} tasks in batch")
        return task_ids
