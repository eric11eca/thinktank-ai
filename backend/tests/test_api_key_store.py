"""Tests for API key store (user_id migration, encryption, CRUD)."""

import json

from src.security.api_key_store import delete_api_key, get_api_key, has_api_key, set_api_key


class TestApiKeyStoreCRUD:
    """Tests for basic CRUD operations."""

    def test_set_and_get_key(self, tmp_store_dir):
        """Storing and retrieving a key returns the original value."""
        set_api_key("user-1", "openai", "sk-test-123")
        result = get_api_key("user-1", "openai")
        assert result == "sk-test-123"

    def test_has_key(self, tmp_store_dir):
        """has_api_key returns True when key exists, False otherwise."""
        assert has_api_key("user-1", "openai") is False

        set_api_key("user-1", "openai", "sk-test-123")
        assert has_api_key("user-1", "openai") is True

    def test_get_nonexistent_key(self, tmp_store_dir):
        """Getting a key that doesn't exist returns None."""
        assert get_api_key("user-1", "openai") is None

    def test_delete_key(self, tmp_store_dir):
        """Deleting a key removes it from the store."""
        set_api_key("user-1", "openai", "sk-test-123")
        assert has_api_key("user-1", "openai") is True

        delete_api_key("user-1", "openai")
        assert has_api_key("user-1", "openai") is False
        assert get_api_key("user-1", "openai") is None

    def test_multiple_users_isolated(self, tmp_store_dir):
        """Keys are isolated per user."""
        set_api_key("user-1", "openai", "sk-user1")
        set_api_key("user-2", "openai", "sk-user2")

        assert get_api_key("user-1", "openai") == "sk-user1"
        assert get_api_key("user-2", "openai") == "sk-user2"

    def test_multiple_providers_per_user(self, tmp_store_dir):
        """A single user can store keys for multiple providers."""
        set_api_key("user-1", "openai", "sk-openai")
        set_api_key("user-1", "anthropic", "sk-anthropic")

        assert get_api_key("user-1", "openai") == "sk-openai"
        assert get_api_key("user-1", "anthropic") == "sk-anthropic"

    def test_overwrite_key(self, tmp_store_dir):
        """Setting a key for the same user/provider overwrites the old value."""
        set_api_key("user-1", "openai", "sk-old")
        set_api_key("user-1", "openai", "sk-new")
        assert get_api_key("user-1", "openai") == "sk-new"

    def test_empty_user_id_raises(self, tmp_store_dir):
        """Empty user_id raises ValueError."""
        import pytest

        with pytest.raises(ValueError):
            set_api_key("", "openai", "sk-test")

    def test_empty_api_key_raises(self, tmp_store_dir):
        """Empty api_key raises ValueError."""
        import pytest

        with pytest.raises(ValueError):
            set_api_key("user-1", "openai", "   ")

    def test_keys_encrypted_on_disk(self, tmp_store_dir):
        """Keys stored on disk are encrypted (not plaintext)."""
        set_api_key("user-1", "openai", "sk-plaintext-secret")

        data_file = tmp_store_dir / "api-keys.json"
        raw = data_file.read_text(encoding="utf-8")

        # The plaintext key should NOT appear in the file
        assert "sk-plaintext-secret" not in raw


class TestLegacyMigration:
    """Tests for legacy 'devices' -> 'users' migration."""

    def test_legacy_devices_key_migrated(self, tmp_store_dir):
        """A store file with 'devices' key is migrated to 'users'."""
        from src.security.api_key_store import _load_store

        # Write a legacy-format file with "devices" key
        data_file = tmp_store_dir / "api-keys.json"
        legacy_data = {
            "schema_version": 1,
            "devices": {
                "device-abc": {"openai": "encrypted-token-here"},
            },
        }
        data_file.write_text(json.dumps(legacy_data), encoding="utf-8")

        # Load store - should migrate
        store = _load_store()
        assert "users" in store
        assert "devices" not in store
        assert "device-abc" in store["users"]
        assert store["schema_version"] == 2

    def test_new_store_uses_users_key(self, tmp_store_dir):
        """A fresh store uses 'users' key with schema_version 2."""
        from src.security.api_key_store import _load_store

        store = _load_store()
        assert "users" in store
        assert store["schema_version"] == 2
