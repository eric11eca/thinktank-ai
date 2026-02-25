"""Per-user rate limiting via Redis with graceful fallback.

When Redis is not available, all requests are allowed (no-op).
This complements nginx's IP-based rate limiting with user-scoped limits.
"""

import logging
import os
import time

from fastapi import HTTPException, Request, status

from src.queue.redis_connection import get_redis_client

logger = logging.getLogger(__name__)

# Configurable via environment variables (requests per minute)
API_RATE_LIMIT = int(os.environ.get("API_RATE_LIMIT", "120"))
AUTH_RATE_LIMIT = int(os.environ.get("AUTH_RATE_LIMIT", "10"))
LLM_RATE_LIMIT = int(os.environ.get("LLM_RATE_LIMIT", "30"))
RATE_LIMIT_WINDOW = 60  # seconds


def check_rate_limit(key: str, limit: int) -> bool:
    """Check and increment a rate limit counter.

    Uses a sliding window counter pattern with Redis INCR + EXPIRE.

    Args:
        key: The rate limit key (e.g., "ratelimit:api:user123").
        limit: Maximum requests allowed per window.

    Returns:
        True if the request is allowed, False if rate-limited.
        When Redis is unavailable, always returns True (fail open).
    """
    client = get_redis_client()
    if client is None:
        return True  # Graceful fallback: no Redis = no rate limiting

    window_key = f"{key}:{int(time.time()) // RATE_LIMIT_WINDOW}"
    try:
        pipe = client.pipeline()
        pipe.incr(window_key)
        pipe.expire(window_key, RATE_LIMIT_WINDOW * 2)
        results = pipe.execute()
        count = results[0]
        return count <= limit
    except Exception as e:
        logger.warning(f"Rate limiter error: {e}")
        return True  # Fail open on errors


def check_user_api_rate(user_id: str) -> None:
    """Check API rate limit for a user. Raises 429 if exceeded."""
    if not check_rate_limit(f"ratelimit:api:{user_id}", API_RATE_LIMIT):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="API rate limit exceeded. Please try again later.",
        )


def check_user_llm_rate(user_id: str) -> None:
    """Check LLM rate limit for a user. Raises 429 if exceeded."""
    if not check_rate_limit(f"ratelimit:llm:{user_id}", LLM_RATE_LIMIT):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="LLM rate limit exceeded. Please try again later.",
        )


def check_auth_rate(request: Request) -> None:
    """Check auth rate limit by IP address. Raises 429 if exceeded."""
    ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(f"ratelimit:auth:{ip}", AUTH_RATE_LIMIT):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts. Please try again later.",
        )
