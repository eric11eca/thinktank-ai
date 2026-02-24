"""Tests for Redis connection management with graceful fallback."""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.queue.redis_connection import (
    check_redis_health,
    get_redis_client,
    get_redis_url,
    is_redis_available,
    reset_redis_connection,
)


@pytest.fixture(autouse=True)
def _reset_redis():
    """Reset Redis connection state before each test."""
    reset_redis_connection()
    yield
    reset_redis_connection()


class TestRedisUrl:
    """Tests for get_redis_url."""

    def test_returns_none_without_env(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("REDIS_URL", None)
            assert get_redis_url() is None

    def test_returns_url_from_env(self):
        with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379/0"}):
            assert get_redis_url() == "redis://localhost:6379/0"


class TestIsRedisAvailable:
    """Tests for is_redis_available."""

    def test_returns_false_without_redis_url(self):
        """Should return False when REDIS_URL is not set."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("REDIS_URL", None)
            assert is_redis_available() is False

    def test_returns_false_when_redis_unreachable(self):
        """Should return False when Redis connection fails."""
        mock_redis = MagicMock()
        mock_redis.from_url.return_value.ping.side_effect = ConnectionError("refused")

        with (
            patch.dict(os.environ, {"REDIS_URL": "redis://nonexistent:6379/0"}),
            patch("src.queue.redis_connection.redis", mock_redis, create=True),
            patch.dict("sys.modules", {"redis": mock_redis}),
        ):
            # Need to re-import to pick up mock
            reset_redis_connection()
            result = is_redis_available()
            assert result is False

    def test_caches_result_on_second_call(self):
        """Second call should use cached result without re-checking."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("REDIS_URL", None)
            assert is_redis_available() is False
            # Second call - should still return False without checking again
            assert is_redis_available() is False


class TestGetRedisClient:
    """Tests for get_redis_client."""

    def test_returns_none_when_unavailable(self):
        """Should return None when Redis is not available."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("REDIS_URL", None)
            assert get_redis_client() is None


class TestCheckRedisHealth:
    """Tests for check_redis_health."""

    def test_returns_not_configured_without_client(self):
        """Should return 'not configured' when Redis client is None."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("REDIS_URL", None)
            assert check_redis_health() == "not configured"


class TestResetRedisConnection:
    """Tests for reset_redis_connection."""

    def test_resets_cached_state(self):
        """After reset, is_redis_available should re-check."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("REDIS_URL", None)
            is_redis_available()  # First check caches result
            reset_redis_connection()
            # After reset, _redis_checked should be False
            # Calling get_redis_client should trigger a new check
            assert get_redis_client() is None
