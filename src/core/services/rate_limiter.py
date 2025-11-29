"""Redis-backed rate limiter with atomic acquisition."""

from __future__ import annotations

import time
from typing import Tuple

from redis import asyncio as redis_async
from redis.exceptions import ResponseError, WatchError

_RATE_LIMIT_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])

redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)

if count < limit then
    redis.call('ZADD', key, now, now)
    redis.call('PEXPIRE', key, window)
    return {1, 0}
else
    local earliest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    if earliest == nil or #earliest == 0 then
        return {0, window}
    end
    local earliest_score = tonumber(earliest[2])
    local delay = (earliest_score + window) - now
    if delay < 0 then
        delay = 0
    end
    return {0, delay}
end
"""


class RedisRateLimiter:
    """Rate limiter using Redis sorted set for distributed throttling."""

    def __init__(
        self,
        redis_client: redis_async.Redis,
        key: str,
        limit: int,
        period: int,
        owns_connection: bool = False,
    ):
        self._redis = redis_client
        self._key = key
        self.max_rate = limit
        self.time_period = period
        self._owns_connection = owns_connection

    async def acquire(self) -> Tuple[bool, float]:
        """Attempt to acquire a slot. Returns (allowed, delay_in_seconds)."""
        now_ms = int(time.time() * 1000)
        window_ms = int(self.time_period * 1000)

        try:
            allowed, delay_ms = await self._redis.eval(
                _RATE_LIMIT_LUA,
                1,
                self._key,
                now_ms,
                window_ms,
                self.max_rate,
            )

            return bool(allowed), float(delay_ms) / 1000.0
        except ResponseError as exc:
            # Some test doubles (fakeredis) or managed services may not support Lua scripting.
            message = str(exc).lower()
            if "unknown command" not in message and "noscript" not in message:
                raise
            return await self._acquire_without_lua(now_ms, window_ms)

    async def _acquire_without_lua(self, now_ms: int, window_ms: int) -> Tuple[bool, float]:
        """Fallback implementation using optimistic locking when Lua is unavailable."""
        key = self._key

        while True:
            try:
                async with self._redis.pipeline(transaction=True) as pipe:
                    await pipe.watch(key)
                    await pipe.zremrangebyscore(key, 0, now_ms - window_ms)
                    current_count = await pipe.zcard(key)

                    if current_count < self.max_rate:
                        pipe.multi()
                        pipe.zadd(key, {now_ms: now_ms})
                        pipe.pexpire(key, window_ms)
                        await pipe.execute()
                        return True, 0.0

                    earliest = await pipe.zrange(key, 0, 0, withscores=True)
                    await pipe.reset()

                    if not earliest:
                        return False, window_ms / 1000.0

                    _, earliest_score = earliest[0]
                    delay_ms = max((float(earliest_score) + window_ms) - now_ms, 0.0)
                    return False, delay_ms / 1000.0
            except WatchError:
                # Retry if the sorted set changed while we were reading it.
                continue

    async def close(self) -> None:
        """Close Redis connection if owned by this limiter."""
        if self._owns_connection:
            aclose = getattr(self._redis, "aclose", None)
            if callable(aclose):
                await aclose()
            else:
                await self._redis.close()
