"""Tests for per-user rate limiting module (Phase 6.5)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from src.gateway.rate_limiter import (
    API_RATE_LIMIT,
    AUTH_RATE_LIMIT,
    LLM_RATE_LIMIT,
    check_auth_rate,
    check_rate_limit,
    check_user_api_rate,
    check_user_llm_rate,
)


class TestCheckRateLimit:
    """Test the core rate limiting function."""

    def test_allows_when_no_redis(self):
        """When Redis is unavailable, all requests should be allowed."""
        with patch("src.gateway.rate_limiter.get_redis_client", return_value=None):
            assert check_rate_limit("test:key", 10) is True

    def test_allows_under_limit(self):
        """Requests under the limit should be allowed."""
        mock_client = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [5, True]  # count=5, expire=True
        mock_client.pipeline.return_value = mock_pipe

        with patch("src.gateway.rate_limiter.get_redis_client", return_value=mock_client):
            assert check_rate_limit("test:key", 10) is True

    def test_blocks_over_limit(self):
        """Requests over the limit should be blocked."""
        mock_client = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [11, True]  # count=11, expire=True
        mock_client.pipeline.return_value = mock_pipe

        with patch("src.gateway.rate_limiter.get_redis_client", return_value=mock_client):
            assert check_rate_limit("test:key", 10) is False

    def test_allows_at_exact_limit(self):
        """Requests at exactly the limit should be allowed."""
        mock_client = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [10, True]  # count=10 == limit
        mock_client.pipeline.return_value = mock_pipe

        with patch("src.gateway.rate_limiter.get_redis_client", return_value=mock_client):
            assert check_rate_limit("test:key", 10) is True

    def test_fails_open_on_redis_error(self):
        """Redis errors should fail open (allow the request)."""
        mock_client = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute.side_effect = ConnectionError("Redis down")
        mock_client.pipeline.return_value = mock_pipe

        with patch("src.gateway.rate_limiter.get_redis_client", return_value=mock_client):
            assert check_rate_limit("test:key", 10) is True


class TestCheckUserApiRate:
    """Test API rate limit helper."""

    def test_passes_when_allowed(self):
        """Should not raise when under limit."""
        with patch("src.gateway.rate_limiter.check_rate_limit", return_value=True):
            check_user_api_rate("user1")  # Should not raise

    def test_raises_429_when_exceeded(self):
        """Should raise 429 when rate limit exceeded."""
        with patch("src.gateway.rate_limiter.check_rate_limit", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                check_user_api_rate("user1")
            assert exc_info.value.status_code == 429
            assert "rate limit" in exc_info.value.detail.lower()


class TestCheckUserLlmRate:
    """Test LLM rate limit helper."""

    def test_passes_when_allowed(self):
        """Should not raise when under limit."""
        with patch("src.gateway.rate_limiter.check_rate_limit", return_value=True):
            check_user_llm_rate("user1")

    def test_raises_429_when_exceeded(self):
        """Should raise 429 when rate limit exceeded."""
        with patch("src.gateway.rate_limiter.check_rate_limit", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                check_user_llm_rate("user1")
            assert exc_info.value.status_code == 429


class TestCheckAuthRate:
    """Test auth rate limit helper (IP-based)."""

    def _make_request(self, ip: str = "127.0.0.1") -> MagicMock:
        """Create a mock Request with a client IP."""
        request = MagicMock()
        request.client = MagicMock()
        request.client.host = ip
        return request

    def test_passes_when_allowed(self):
        """Should not raise when under limit."""
        with patch("src.gateway.rate_limiter.check_rate_limit", return_value=True):
            check_auth_rate(self._make_request())

    def test_raises_429_when_exceeded(self):
        """Should raise 429 when auth rate limit exceeded."""
        with patch("src.gateway.rate_limiter.check_rate_limit", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                check_auth_rate(self._make_request())
            assert exc_info.value.status_code == 429

    def test_uses_ip_address_in_key(self):
        """Should use the client IP address for rate limiting."""
        with patch("src.gateway.rate_limiter.check_rate_limit", return_value=True) as mock_check:
            check_auth_rate(self._make_request("10.0.0.1"))
            mock_check.assert_called_once_with("ratelimit:auth:10.0.0.1", AUTH_RATE_LIMIT)

    def test_handles_missing_client(self):
        """Should handle requests without client info."""
        request = MagicMock()
        request.client = None
        with patch("src.gateway.rate_limiter.check_rate_limit", return_value=True) as mock_check:
            check_auth_rate(request)
            mock_check.assert_called_once_with("ratelimit:auth:unknown", AUTH_RATE_LIMIT)


class TestRateLimitDefaults:
    """Test default rate limit values."""

    def test_api_rate_limit_default(self):
        assert API_RATE_LIMIT == 120

    def test_auth_rate_limit_default(self):
        assert AUTH_RATE_LIMIT == 10

    def test_llm_rate_limit_default(self):
        assert LLM_RATE_LIMIT == 30
