"""Redis connection management with graceful fallback.

When REDIS_URL is configured and Redis is reachable, provides a shared
Redis client. Otherwise, callers should fall back to in-process alternatives.
"""

import logging
import os

logger = logging.getLogger(__name__)

_redis_client = None
_redis_checked = False


def get_redis_url() -> str | None:
    """Get Redis URL from environment."""
    return os.environ.get("REDIS_URL")


def is_redis_available() -> bool:
    """Check if Redis is configured and reachable.

    Results are cached after the first check. Use reset_redis_connection()
    to force a re-check (useful for testing).
    """
    global _redis_checked, _redis_client

    if _redis_checked:
        return _redis_client is not None

    _redis_checked = True
    url = get_redis_url()
    if not url:
        logger.info("REDIS_URL not configured, using in-process queue")
        return False

    try:
        import redis

        client = redis.from_url(url, socket_connect_timeout=2)
        client.ping()
        _redis_client = client
        logger.info(f"Redis connection established: {url}")
        return True
    except Exception as e:
        logger.warning(f"Redis not available ({e}), falling back to in-process queue")
        _redis_client = None
        return False


def get_redis_client():
    """Get the Redis client. Returns None if Redis is not available."""
    if not _redis_checked:
        is_redis_available()
    return _redis_client


def check_redis_health() -> str:
    """Check if Redis is reachable.

    Returns:
        "healthy" if ping succeeds, error description otherwise.
    """
    client = get_redis_client()
    if client is None:
        return "not configured"
    try:
        client.ping()
        return "healthy"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return f"unhealthy: {e}"


def reset_redis_connection() -> None:
    """Reset the Redis connection state. Used for testing."""
    global _redis_client, _redis_checked
    _redis_client = None
    _redis_checked = False
