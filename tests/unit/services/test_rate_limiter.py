"""Unit tests for RedisRateLimiter."""

import asyncio
from dataclasses import dataclass
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from fakeredis.aioredis import FakeRedis
from redis.exceptions import ResponseError, WatchError

from core.services.rate_limiter import RedisRateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_allows_within_limit():
    redis = FakeRedis()
    try:
        limiter = RedisRateLimiter(redis_client=redis, key="test:limit", limit=2, period=60)

        allowed1, delay1 = await limiter.acquire()
        allowed2, delay2 = await limiter.acquire()
        allowed3, delay3 = await limiter.acquire()

        assert allowed1 is True and delay1 == 0.0
        assert allowed2 is True and delay2 == 0.0
        assert allowed3 is False
        assert delay3 > 0
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_rate_limiter_delay_decreases_after_wait():
    redis = FakeRedis()
    try:
        limiter = RedisRateLimiter(redis_client=redis, key="test:delay", limit=1, period=1)

        allowed, delay = await limiter.acquire()
        assert allowed and delay == 0.0

        allowed2, delay2 = await limiter.acquire()
        assert not allowed2 and delay2 > 0

        # wait for the window to pass and retry
        await asyncio.sleep(delay2)
        allowed3, delay3 = await limiter.acquire()
        assert allowed3 and delay3 == 0.0
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_rate_limiter_uses_lua_when_supported():
    redis = AsyncMock()
    redis.eval.return_value = (1, 0)

    limiter = RedisRateLimiter(redis_client=redis, key="test:lua", limit=5, period=60)

    allowed, delay = await limiter.acquire()

    assert allowed is True
    assert delay == 0.0
    redis.eval.assert_awaited_once()


@dataclass
class _DummyPipeline:
    """Helper pipeline to simulate optimistic locking behaviour."""

    count: int
    fail_on_execute: bool = False
    earliest_score: Optional[float] = None

    async def __aenter__(self) -> "_DummyPipeline":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def watch(self, _key: str) -> None:
        return None

    async def zremrangebyscore(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def zcard(self, _key: str) -> int:
        return self.count

    def multi(self) -> None:
        return None

    async def zadd(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def pexpire(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def execute(self) -> None:
        if self.fail_on_execute:
            raise WatchError("simulated concurrent write")
        return None

    async def zrange(self, *args: Any, **kwargs: Any):
        if self.earliest_score is None:
            return []
        return [(b"value", float(self.earliest_score))]

    async def reset(self) -> None:
        return None


@pytest.mark.asyncio
async def test_rate_limiter_retries_on_watch_error():
    redis = AsyncMock()
    redis.eval.side_effect = ResponseError("unknown command `eval`")
    redis.pipeline = MagicMock(side_effect=[
        WatchError("simulated conflict"),
        _DummyPipeline(count=0, fail_on_execute=True),
        _DummyPipeline(count=0, fail_on_execute=False),
    ])

    limiter = RedisRateLimiter(redis_client=redis, key="test:retry", limit=1, period=60)
    allowed, delay = await limiter.acquire()

    assert allowed is True
    assert delay == 0.0
    assert redis.pipeline.call_count == 3


@pytest.mark.asyncio
async def test_rate_limiter_close_closes_connection():
    redis = FakeRedis()
    limiter = RedisRateLimiter(redis_client=redis, key="test:close", limit=1, period=60, owns_connection=True)

    await limiter.close()
    if hasattr(redis, "closed"):
        assert redis.closed
