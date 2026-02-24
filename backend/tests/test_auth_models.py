"""Tests for auth Pydantic models (validation)."""

import pytest
from pydantic import ValidationError

from src.gateway.auth.models import TokenResponse, UserLoginRequest, UserRegisterRequest, UserResponse


class TestUserRegisterRequest:
    """Tests for registration request validation."""

    def test_valid_request(self):
        """A valid registration request parses successfully."""
        req = UserRegisterRequest(
            email="user@example.com",
            password="SecurePass1",
            display_name="Test User",
        )
        assert req.email == "user@example.com"
        assert req.password == "SecurePass1"
        assert req.display_name == "Test User"

    def test_invalid_email(self):
        """An invalid email is rejected."""
        with pytest.raises(ValidationError):
            UserRegisterRequest(email="not-an-email", password="SecurePass1")

    def test_password_too_short(self):
        """A password shorter than 8 characters is rejected."""
        with pytest.raises(ValidationError):
            UserRegisterRequest(email="user@example.com", password="Short1")

    def test_password_no_digit(self):
        """A password without any digit is rejected."""
        with pytest.raises(ValidationError):
            UserRegisterRequest(email="user@example.com", password="NoDigitsHere")

    def test_password_no_letter(self):
        """A password without any letter is rejected."""
        with pytest.raises(ValidationError):
            UserRegisterRequest(email="user@example.com", password="12345678")

    def test_password_at_minimum_length(self):
        """A password at exactly 8 characters with digit and letter passes."""
        req = UserRegisterRequest(email="user@example.com", password="Abcdefg1")
        assert req.password == "Abcdefg1"

    def test_display_name_optional(self):
        """Display name is optional and defaults to None."""
        req = UserRegisterRequest(email="user@example.com", password="SecurePass1")
        assert req.display_name is None


class TestUserLoginRequest:
    """Tests for login request validation."""

    def test_valid_login(self):
        """A valid login request parses successfully."""
        req = UserLoginRequest(email="user@example.com", password="any-password")
        assert req.email == "user@example.com"

    def test_invalid_email(self):
        """An invalid email is rejected."""
        with pytest.raises(ValidationError):
            UserLoginRequest(email="bad-email", password="password")


class TestUserResponse:
    """Tests for user response serialization."""

    def test_user_response(self):
        """UserResponse serializes correctly."""
        resp = UserResponse(
            id="user-123",
            email="user@example.com",
            display_name="Test",
            created_at="2024-01-01T00:00:00+00:00",
        )
        assert resp.id == "user-123"
        assert resp.model_dump()["email"] == "user@example.com"


class TestTokenResponse:
    """Tests for token response serialization."""

    def test_token_response(self):
        """TokenResponse serializes correctly."""
        user = UserResponse(
            id="user-123",
            email="user@example.com",
            created_at="2024-01-01T00:00:00+00:00",
        )
        resp = TokenResponse(access_token="abc.def.ghi", user=user)
        assert resp.access_token == "abc.def.ghi"
        assert resp.token_type == "bearer"
        assert resp.user.id == "user-123"
