"""Celery tasks for Instagram stats aggregation."""

import logging

from ..celery_app import celery_app
from ..container import get_container
from ..use_cases.record_follower_snapshot import FollowersSnapshotError
from ..utils.task_helpers import async_task, get_db_session

logger = logging.getLogger(__name__)


async def record_follower_snapshot_task_async():
    """Core implementation for recording followers snapshot."""
    async with get_db_session() as session:
        container = get_container()
        use_case = container.record_follower_snapshot_use_case(session=session)

        try:
            result = await use_case.execute()
            logger.info("Followers snapshot recorded | snapshot_date=%s", result["snapshot_date"])
            return {"status": "ok", **result}
        except FollowersSnapshotError as exc:
            logger.error("Failed to record followers snapshot | error=%s", exc)
            return {"status": "error", "reason": str(exc)}


@celery_app.task
@async_task
async def record_follower_snapshot_task():
    """Celery task wrapper."""
    return await record_follower_snapshot_task_async()
