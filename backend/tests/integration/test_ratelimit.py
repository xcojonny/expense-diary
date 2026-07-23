import pytest
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.ratelimit import RateLimiter

pytestmark = pytest.mark.integration


async def test_rearms_key_without_ttl() -> None:
    """Regression: a counter key left without a TTL (e.g. a transient failure
    during the first expire) must not block forever — hit() re-arms the window."""
    redis = Redis.from_url(get_settings().redis_url)
    await redis.delete("rl:selfheal")
    await redis.set("rl:selfheal", 3)  # stuck counter, no expiry
    assert await redis.ttl("rl:selfheal") == -1

    limiter = RateLimiter(redis)
    allowed = await limiter.hit("selfheal", limit=5, window_seconds=900)

    assert allowed is True
    assert await redis.ttl("rl:selfheal") > 0  # window re-armed → will expire
    await redis.delete("rl:selfheal")
    await redis.aclose()


async def test_blocks_after_limit() -> None:
    redis = Redis.from_url(get_settings().redis_url)
    await redis.delete("rl:cap")
    limiter = RateLimiter(redis)
    results = [await limiter.hit("cap", limit=3, window_seconds=900) for _ in range(4)]
    assert results == [True, True, True, False]
    await redis.delete("rl:cap")
    await redis.aclose()
