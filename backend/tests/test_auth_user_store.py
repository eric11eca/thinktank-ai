"""Tests for the file-based user store."""

import json

import pytest

from src.gateway.auth.user_store import create_user, get_user_by_email, get_user_by_id


class TestCreateUser:
    """Tests for user creation."""

    def test_create_user_returns_user_dict(self, tmp_store_dir):
        """Creating a user returns a dict with expected fields."""
        user = create_user("test@example.com", "hashed-pw", "Test User")

        assert "id" in user
        assert user["email"] == "test@example.com"
        assert user["display_name"] == "Test User"
        assert "created_at" in user
        # Password hash should NOT be in the returned dict
        assert "password_hash" not in user

    def test_create_user_generates_unique_id(self, tmp_store_dir):
        """Each created user gets a unique ID."""
        u1 = create_user("user1@example.com", "hashed-pw1")
        u2 = create_user("user2@example.com", "hashed-pw2")
        assert u1["id"] != u2["id"]

    def test_create_user_normalizes_email(self, tmp_store_dir):
        """Email is lowercased and trimmed."""
        user = create_user("  TEST@EXAMPLE.COM  ", "hashed-pw")
        assert user["email"] == "test@example.com"

    def test_create_user_duplicate_email_raises(self, tmp_store_dir):
        """Creating a user with a duplicate email raises ValueError."""
        create_user("dup@example.com", "hashed-pw")

        with pytest.raises(ValueError, match="Email already registered"):
            create_user("dup@example.com", "hashed-pw-2")

    def test_create_user_case_insensitive_duplicate(self, tmp_store_dir):
        """Duplicate detection is case-insensitive."""
        create_user("user@example.com", "hashed-pw")

        with pytest.raises(ValueError, match="Email already registered"):
            create_user("USER@EXAMPLE.COM", "hashed-pw-2")

    def test_create_user_persists_to_disk(self, tmp_store_dir):
        """User data is written to the JSON file on disk."""
        user = create_user("persist@example.com", "hashed-pw")

        data_file = tmp_store_dir / "users.json"
        assert data_file.exists()

        data = json.loads(data_file.read_text(encoding="utf-8"))
        assert user["id"] in data["users"]
        assert data["users"][user["id"]]["email"] == "persist@example.com"
        assert data["users"][user["id"]]["password_hash"] == "hashed-pw"

    def test_create_user_optional_display_name(self, tmp_store_dir):
        """Display name defaults to None if not provided."""
        user = create_user("nodisplay@example.com", "hashed-pw")
        assert user["display_name"] is None


class TestGetUserByEmail:
    """Tests for user lookup by email."""

    def test_existing_user(self, tmp_store_dir):
        """Looking up an existing user by email returns the full record."""
        created = create_user("lookup@example.com", "hashed-pw", "Lookup User")
        found = get_user_by_email("lookup@example.com")

        assert found is not None
        assert found["id"] == created["id"]
        assert found["email"] == "lookup@example.com"
        assert "password_hash" in found  # Full record includes hash

    def test_nonexistent_user(self, tmp_store_dir):
        """Looking up a nonexistent email returns None."""
        result = get_user_by_email("ghost@example.com")
        assert result is None

    def test_case_insensitive_lookup(self, tmp_store_dir):
        """Email lookup is case-insensitive."""
        created = create_user("case@example.com", "hashed-pw")
        found = get_user_by_email("CASE@EXAMPLE.COM")
        assert found is not None
        assert found["id"] == created["id"]


class TestGetUserById:
    """Tests for user lookup by ID."""

    def test_existing_user(self, tmp_store_dir):
        """Looking up a user by ID returns the full record."""
        created = create_user("byid@example.com", "hashed-pw")
        found = get_user_by_id(created["id"])

        assert found is not None
        assert found["email"] == "byid@example.com"

    def test_nonexistent_user(self, tmp_store_dir):
        """Looking up a nonexistent ID returns None."""
        result = get_user_by_id("nonexistent-id-12345")
        assert result is None
