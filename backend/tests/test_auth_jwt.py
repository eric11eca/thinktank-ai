"""Tests for JWT token creation and validation."""

import time

import jwt as pyjwt
import pytest

from src.gateway.auth.jwt import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token,
    decode_token,
)


class TestAccessToken:
    """Tests for access token creation and decoding."""

    def test_create_access_token_returns_string(self, jwt_secret):
        """Access token is a non-empty string."""
        token = create_access_token("user-123", "user@example.com")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_access_token_payload(self, jwt_secret):
        """Access token contains correct claims."""
        token = create_access_token("user-123", "user@example.com")
        payload = decode_token(token)

        assert payload["sub"] == "user-123"
        assert payload["email"] == "user@example.com"
        assert payload["type"] == "access"
        assert "iat" in payload
        assert "exp" in payload

    def test_access_token_expiry(self, jwt_secret):
        """Access token expires after the configured time."""
        token = create_access_token("user-123", "user@example.com")
        payload = decode_token(token)

        exp = payload["exp"]
        iat = payload["iat"]
        diff_seconds = exp - iat
        expected_seconds = ACCESS_TOKEN_EXPIRE_MINUTES * 60

        # Allow a small tolerance (1 second)
        assert abs(diff_seconds - expected_seconds) <= 1


class TestRefreshToken:
    """Tests for refresh token creation and decoding."""

    def test_create_refresh_token_returns_string(self, jwt_secret):
        """Refresh token is a non-empty string."""
        token = create_refresh_token("user-123")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_refresh_token_payload(self, jwt_secret):
        """Refresh token contains correct claims."""
        token = create_refresh_token("user-123")
        payload = decode_token(token)

        assert payload["sub"] == "user-123"
        assert payload["type"] == "refresh"
        assert "email" not in payload
        assert "iat" in payload
        assert "exp" in payload

    def test_refresh_token_expiry(self, jwt_secret):
        """Refresh token expires after the configured time."""
        token = create_refresh_token("user-123")
        payload = decode_token(token)

        exp = payload["exp"]
        iat = payload["iat"]
        diff_seconds = exp - iat
        expected_seconds = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60

        assert abs(diff_seconds - expected_seconds) <= 1


class TestDecodeToken:
    """Tests for token decoding and error handling."""

    def test_decode_valid_token(self, jwt_secret):
        """Decoding a valid token returns the payload."""
        token = create_access_token("user-123", "user@example.com")
        payload = decode_token(token)
        assert payload["sub"] == "user-123"

    def test_decode_invalid_token(self, jwt_secret):
        """Decoding an invalid token raises an error."""
        with pytest.raises(pyjwt.InvalidTokenError):
            decode_token("invalid.token.string")

    def test_decode_expired_token(self, jwt_secret):
        """Decoding an expired token raises ExpiredSignatureError."""
        # Create a token that expired 1 second ago
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        payload = {
            "sub": "user-123",
            "email": "user@example.com",
            "type": "access",
            "iat": now - timedelta(hours=1),
            "exp": now - timedelta(seconds=1),
        }
        token = pyjwt.encode(payload, jwt_secret, algorithm=ALGORITHM)

        with pytest.raises(pyjwt.ExpiredSignatureError):
            decode_token(token)

    def test_decode_wrong_secret(self, jwt_secret):
        """Decoding a token signed with a different secret fails."""
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        payload = {
            "sub": "user-123",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=15),
        }
        token = pyjwt.encode(payload, "wrong-secret-key", algorithm=ALGORITHM)

        with pytest.raises(pyjwt.InvalidSignatureError):
            decode_token(token)

    def test_access_and_refresh_tokens_differ(self, jwt_secret):
        """Access and refresh tokens for the same user are different."""
        access = create_access_token("user-123", "user@example.com")
        refresh = create_refresh_token("user-123")
        assert access != refresh
