"""Tests for database-backed store implementations.

These tests run the store functions in DB mode using an in-memory SQLite database.
They verify that the same public API works correctly with the database backend.
"""

from __future__ import annotations

import pytest

from src.agents.memory.updater import (
    _create_empty_memory,
    _memory_data,
    _memory_file_mtime,
)


class TestDBUserStore:
    """Tests for user_store in database mode."""

    def setup_method(self):
        """Clear any cached state."""
        pass

    def test_create_user(self, db_enabled):
        """Creating a user in DB mode returns the user record."""
        from src.gateway.auth.user_store import create_user

        result = create_user("db@example.com", "$2b$12$hash123", "DB User")
        assert result["email"] == "db@example.com"
        assert result["display_name"] == "DB User"
        assert "id" in result
        assert "password_hash" not in result

    def test_create_user_duplicate_email(self, db_enabled):
        """Creating a user with a duplicate email raises ValueError."""
        from src.gateway.auth.user_store import create_user

        create_user("dup-db@example.com", "$2b$12$hash1")
        with pytest.raises(ValueError, match="already registered"):
            create_user("dup-db@example.com", "$2b$12$hash2")

    def test_get_user_by_email(self, db_enabled):
        """A user can be retrieved by email."""
        from src.gateway.auth.user_store import create_user, get_user_by_email

        create_user("find-db@example.com", "$2b$12$hash")
        user = get_user_by_email("find-db@example.com")
        assert user is not None
        assert user["email"] == "find-db@example.com"
        assert "password_hash" in user

    def test_get_user_by_email_not_found(self, db_enabled):
        """Getting a nonexistent user by email returns None."""
        from src.gateway.auth.user_store import get_user_by_email

        assert get_user_by_email("ghost@example.com") is None

    def test_get_user_by_id(self, db_enabled):
        """A user can be retrieved by ID."""
        from src.gateway.auth.user_store import create_user, get_user_by_id

        result = create_user("id-db@example.com", "$2b$12$hash")
        user = get_user_by_id(result["id"])
        assert user is not None
        assert user["email"] == "id-db@example.com"

    def test_get_user_by_id_not_found(self, db_enabled):
        """Getting a nonexistent user by ID returns None."""
        from src.gateway.auth.user_store import get_user_by_id

        assert get_user_by_id("nonexistent-id") is None

    def test_email_case_insensitive(self, db_enabled):
        """Email lookup is case-insensitive."""
        from src.gateway.auth.user_store import create_user, get_user_by_email

        create_user("MiXeD@Example.COM", "$2b$12$hash")
        user = get_user_by_email("mixed@example.com")
        assert user is not None
        assert user["email"] == "mixed@example.com"


class TestDBThreadStore:
    """Tests for thread_store in database mode."""

    def test_claim_unclaimed_thread(self, db_enabled):
        """Claiming an unclaimed thread succeeds."""
        from src.gateway.auth.thread_store import claim_thread

        assert claim_thread("db-thread-1", "user-A") is True

    def test_claim_own_thread(self, db_enabled):
        """Re-claiming your own thread returns True."""
        from src.gateway.auth.thread_store import claim_thread

        claim_thread("db-thread-2", "user-A")
        assert claim_thread("db-thread-2", "user-A") is True

    def test_claim_other_users_thread(self, db_enabled):
        """Claiming another user's thread returns False."""
        from src.gateway.auth.thread_store import claim_thread

        claim_thread("db-thread-3", "user-A")
        assert claim_thread("db-thread-3", "user-B") is False

    def test_get_thread_owner(self, db_enabled):
        """Getting the owner of a thread returns the correct user."""
        from src.gateway.auth.thread_store import claim_thread, get_thread_owner

        claim_thread("db-thread-4", "user-X")
        assert get_thread_owner("db-thread-4") == "user-X"

    def test_get_thread_owner_unclaimed(self, db_enabled):
        """Getting the owner of an unclaimed thread returns None."""
        from src.gateway.auth.thread_store import get_thread_owner

        assert get_thread_owner("nonexistent-thread") is None

    def test_is_thread_owner(self, db_enabled):
        """is_thread_owner returns True for the owner and for unclaimed threads."""
        from src.gateway.auth.thread_store import claim_thread, is_thread_owner

        claim_thread("db-thread-5", "user-A")
        assert is_thread_owner("db-thread-5", "user-A") is True
        assert is_thread_owner("db-thread-5", "user-B") is False
        assert is_thread_owner("unclaimed-thread", "anyone") is True

    def test_get_user_threads(self, db_enabled):
        """Getting all threads for a user returns the correct list."""
        from src.gateway.auth.thread_store import claim_thread, get_user_threads

        claim_thread("db-t1", "user-list")
        claim_thread("db-t2", "user-other")
        claim_thread("db-t3", "user-list")

        threads = get_user_threads("user-list")
        assert set(threads) == {"db-t1", "db-t3"}

    def test_delete_thread(self, db_enabled):
        """Deleting a thread removes it from the store."""
        from src.gateway.auth.thread_store import (
            claim_thread,
            delete_thread,
            get_thread_owner,
        )

        claim_thread("db-del-1", "user-A")
        assert get_thread_owner("db-del-1") == "user-A"
        delete_thread("db-del-1")
        assert get_thread_owner("db-del-1") is None


class TestDBApiKeyStore:
    """Tests for api_key_store in database mode."""

    def test_set_and_get_api_key(self, db_enabled, tmp_store_dir):
        """An API key can be stored and retrieved."""
        from src.security.api_key_store import get_api_key, set_api_key

        set_api_key("user-key-db", "openai", "sk-test-12345")
        result = get_api_key("user-key-db", "openai")
        assert result == "sk-test-12345"

    def test_has_api_key(self, db_enabled, tmp_store_dir):
        """has_api_key returns True when a key is stored."""
        from src.security.api_key_store import has_api_key, set_api_key

        assert has_api_key("user-has-db", "openai") is False
        set_api_key("user-has-db", "openai", "sk-test")
        assert has_api_key("user-has-db", "openai") is True

    def test_delete_api_key(self, db_enabled, tmp_store_dir):
        """Deleting an API key removes it."""
        from src.security.api_key_store import (
            delete_api_key,
            get_api_key,
            has_api_key,
            set_api_key,
        )

        set_api_key("user-del-db", "anthropic", "sk-ant-test")
        assert has_api_key("user-del-db", "anthropic") is True
        delete_api_key("user-del-db", "anthropic")
        assert has_api_key("user-del-db", "anthropic") is False
        assert get_api_key("user-del-db", "anthropic") is None

    def test_update_api_key(self, db_enabled, tmp_store_dir):
        """Updating an API key replaces the old value."""
        from src.security.api_key_store import get_api_key, set_api_key

        set_api_key("user-upd-db", "openai", "sk-old")
        set_api_key("user-upd-db", "openai", "sk-new")
        assert get_api_key("user-upd-db", "openai") == "sk-new"

    def test_user_isolation(self, db_enabled, tmp_store_dir):
        """API keys are isolated per user."""
        from src.security.api_key_store import get_api_key, has_api_key, set_api_key

        set_api_key("user-A-db", "openai", "sk-A")
        set_api_key("user-B-db", "openai", "sk-B")

        assert get_api_key("user-A-db", "openai") == "sk-A"
        assert get_api_key("user-B-db", "openai") == "sk-B"
        assert has_api_key("user-A-db", "anthropic") is False

    def test_empty_validation(self, db_enabled, tmp_store_dir):
        """Empty user_id or provider raises ValueError."""
        from src.security.api_key_store import set_api_key

        with pytest.raises(ValueError):
            set_api_key("", "openai", "sk-test")
        with pytest.raises(ValueError):
            set_api_key("user", "", "sk-test")
        with pytest.raises(ValueError):
            set_api_key("user", "openai", "  ")


class TestDBMemoryStore:
    """Tests for memory/updater.py in database mode."""

    def setup_method(self):
        """Clear the module-level caches before each test."""
        _memory_data.clear()
        _memory_file_mtime.clear()

    def test_get_memory_returns_empty_for_new_user(self, db_enabled):
        """Getting memory for a nonexistent user returns empty memory."""
        from src.agents.memory.updater import get_memory_data

        memory = get_memory_data("db-new-user")
        assert memory["version"] == "1.0"
        assert memory["facts"] == []
        assert "user" in memory
        assert "history" in memory

    def test_save_and_get_memory(self, db_enabled):
        """Memory can be saved and retrieved from the database."""
        from src.agents.memory.updater import _save_memory, get_memory_data

        custom_memory = _create_empty_memory()
        custom_memory["facts"].append(
            {"id": "db-fact-1", "content": "User likes Python", "confidence": 0.9}
        )

        success = _save_memory("db-save-user", custom_memory)
        assert success is True

        # Clear cache to force DB read
        _memory_data.clear()

        retrieved = get_memory_data("db-save-user")
        assert len(retrieved["facts"]) == 1
        assert retrieved["facts"][0]["id"] == "db-fact-1"

    def test_reload_memory_invalidates_cache(self, db_enabled):
        """reload_memory_data forces a re-read from database."""
        from src.agents.memory.updater import (
            _save_memory,
            get_memory_data,
            reload_memory_data,
        )

        # Save initial memory
        mem1 = _create_empty_memory()
        _save_memory("db-reload-user", mem1)

        # Get (caches it)
        get_memory_data("db-reload-user")
        assert "db-reload-user" in _memory_data

        # Directly update in DB
        from src.db.engine import get_db_session
        from src.db.models import UserMemoryModel

        with get_db_session() as session:
            record = (
                session.query(UserMemoryModel)
                .filter(UserMemoryModel.user_id == "db-reload-user")
                .first()
            )
            updated = dict(record.memory_json)
            updated["facts"] = [{"id": "sneaky-fact"}]
            record.memory_json = updated

        # Reload should pick up the change
        reloaded = reload_memory_data("db-reload-user")
        assert len(reloaded["facts"]) == 1
        assert reloaded["facts"][0]["id"] == "sneaky-fact"

    def test_memory_isolation_between_users(self, db_enabled):
        """Different users have isolated memory."""
        from src.agents.memory.updater import _save_memory, get_memory_data

        mem_a = _create_empty_memory()
        mem_a["facts"].append({"id": "fact-A", "content": "A's fact"})
        _save_memory("db-user-A", mem_a)

        mem_b = _create_empty_memory()
        mem_b["facts"].append({"id": "fact-B", "content": "B's fact"})
        _save_memory("db-user-B", mem_b)

        _memory_data.clear()

        result_a = get_memory_data("db-user-A")
        result_b = get_memory_data("db-user-B")

        assert result_a["facts"][0]["id"] == "fact-A"
        assert result_b["facts"][0]["id"] == "fact-B"

    def test_memory_upsert(self, db_enabled):
        """Saving memory for the same user twice updates the record."""
        from src.agents.memory.updater import _save_memory, get_memory_data

        mem1 = _create_empty_memory()
        mem1["facts"] = [{"id": "old-fact"}]
        _save_memory("db-upsert-user", mem1)

        mem2 = _create_empty_memory()
        mem2["facts"] = [{"id": "new-fact-1"}, {"id": "new-fact-2"}]
        _save_memory("db-upsert-user", mem2)

        _memory_data.clear()
        result = get_memory_data("db-upsert-user")
        assert len(result["facts"]) == 2
        assert result["facts"][0]["id"] == "new-fact-1"


class TestDBHealthCheck:
    """Tests for the health check endpoint with database."""

    @pytest.mark.asyncio
    async def test_health_check_with_db(self, db_enabled):
        """Health check includes database status when DB is enabled."""
        from httpx import ASGITransport, AsyncClient

        from src.gateway.app import create_app

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            body = resp.json()
            assert "checks" in body
            assert "database" in body["checks"]
            assert body["checks"]["gateway"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_check_without_db(self):
        """Health check works without database (file mode)."""
        from unittest.mock import patch

        from httpx import ASGITransport, AsyncClient

        from src.gateway.app import create_app

        with patch("src.db.engine.is_db_enabled", return_value=False):
            app = create_app()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/health")
                assert resp.status_code == 200
                body = resp.json()
                assert body["status"] == "healthy"
                assert "database" not in body.get("checks", {})
