"""Redis lock manager for distributed task coordination (DRY principle)."""

import logging
from contextlib import asynccontextmanager
from typing import Optional

import redis

from ..config import settings

logger = logging.getLogger(__name__)


class LockManager:
    """
    Centralized Redis lock management.

    Eliminates duplicate locking logic across tasks (DRY principle).
    """

    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or settings.celery.broker_url
        self._client: Optional[redis.Redis] = None

    @property
    def client(self) -> redis.Redis:
        """Lazy Redis client initialization."""
        if self._client is None:
            self._client = redis.Redis.from_url(self.redis_url)
        return self._client

    @asynccontextmanager
    async def acquire(self, lock_key: str, timeout: int = 30, wait: bool = False):
        """
        Acquire distributed lock with automatic release.

        Args:
            lock_key: Unique lock identifier
            timeout: Lock expiration in seconds
            wait: Whether to wait for lock if unavailable

        Usage:
            async with lock_manager.acquire(f"process:{comment_id}"):
                # Protected code
        """
        acquired = self.client.set(lock_key, "processing", nx=True, ex=timeout)

        if not acquired and not wait:
            logger.info(f"Lock {lock_key} already held, skipping")
            yield False
            return

        try:
            yield True
        finally:
            if acquired:
                self.client.delete(lock_key)
                logger.debug(f"Released lock: {lock_key}")

    def is_locked(self, lock_key: str) -> bool:
        """Check if lock is currently held."""
        return self.client.exists(lock_key) > 0


# Global instance (singleton pattern)
lock_manager = LockManager()
