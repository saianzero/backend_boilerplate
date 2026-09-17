"""
Shared async Redis client.

One connection pool per process. Import ``redis_client`` anywhere you need
Redis (job status, caching, locks, counters). Closed in the FastAPI lifespan.

Usage
-----
    from src.core.redis_client import redis_client

    await redis_client.set("key", "value", ex=3600)          # TTL in seconds
    await redis_client.hset("job:123", mapping={"status": "queued"})
    await redis_client.hgetall("job:123")                    # -> dict[str, str]
    await redis_client.incr("counter")

``decode_responses=True`` means you get ``str`` back, not ``bytes``.
"""

import redis.asyncio as redis

from src.core.config import REDIS_CACHE_URL

redis_client = redis.from_url(REDIS_CACHE_URL, decode_responses=True)
