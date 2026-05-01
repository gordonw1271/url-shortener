"""Redis cache for short_code -> long_url mappings.

Phase 3 pattern: read-through cache.
- Redirect handler asks the cache first.
- On miss: handler reads the DB, populates the cache, returns.
- On hit: DB never touched.

Mappings are immutable (a short code, once issued, always points to the same
long URL), so we don't need cache invalidation. We do set a TTL anyway,
mostly to evict cold entries naturally so we don't pay to keep memory full
of links nobody clicks.

Graceful degradation: every Redis call is wrapped in try/except. A Redis
outage degrades latency (every request goes to the DB) but never causes a
user-facing failure. The cache is an optimization, not a dependency.
"""
import logging
import os

import redis

log = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", str(60 * 60 * 24)))  # 1 day

# from_url returns a connection-pool-backed client. It's lazy: it doesn't
# actually open a socket until the first command runs, so an import-time
# Redis outage doesn't prevent the app from starting.
_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)


def _key(short_code: str) -> str:
    return f"mapping:{short_code}"


def get(short_code: str) -> str | None:
    """Return the cached long URL, or None on miss / Redis error."""
    try:
        return _client.get(_key(short_code))
    except redis.RedisError as e:
        log.warning("redis GET failed (%s) - degrading to DB", e)
        return None


def put(short_code: str, long_url: str, ttl: int = CACHE_TTL_SECONDS) -> None:
    """Populate cache with TTL. Errors are logged and swallowed."""
    try:
        _client.setex(_key(short_code), ttl, long_url)
    except redis.RedisError as e:
        log.warning("redis SETEX failed (%s) - skipping cache populate", e)
