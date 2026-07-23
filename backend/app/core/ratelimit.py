from redis.asyncio import Redis


class RateLimiter:
    """Fixed-window rate limiter on Redis. Fails open if Redis is unavailable —
    for a homelab, availability of the login flow beats strictness."""

    def __init__(self, redis: Redis | None) -> None:
        self._redis = redis

    async def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        """Record one hit; return True if the action is still allowed."""
        if self._redis is None:
            return True
        try:
            full_key = f"rl:{key}"
            count = await self._redis.incr(full_key)
            # Always ensure the key has a TTL. If a transient failure once left a
            # key without expiry, it would otherwise count up forever and block
            # the action permanently — so (re)arm the window whenever it's missing.
            if count == 1 or await self._redis.ttl(full_key) < 0:
                await self._redis.expire(full_key, window_seconds)
            return int(count) <= limit
        except Exception:
            return True
