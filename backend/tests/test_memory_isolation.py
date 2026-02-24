"""Tests for per-user memory isolation."""

import json
from pathlib import Path
from unittest.mock import patch

from src.agents.memory.updater import (
    DEFAULT_USER_ID,
    _create_empty_memory,
    _get_memory_file_path,
    _memory_data,
    _memory_file_mtime,
    get_memory_data,
    reload_memory_data,
)


class TestMemoryFilePath:
    """Tests for per-user memory file path resolution."""

    def test_default_user_id(self):
        """Default user ID is 'local'."""
        assert DEFAULT_USER_ID == "local"

    def test_path_includes_user_id(self):
        """Memory file path includes the user ID."""
        path = _get_memory_file_path("user-123")
        assert "user-123.json" in str(path)

    def test_default_user_path(self):
        """Default user path uses 'local.json'."""
        path = _get_memory_file_path()
        assert "local.json" in str(path)

    def test_different_users_different_paths(self):
        """Different users get different file paths."""
        path_a = _get_memory_file_path("user-A")
        path_b = _get_memory_file_path("user-B")
        assert path_a != path_b


class TestMemoryDataIsolation:
    """Tests for memory data isolation between users."""

    def setup_method(self):
        """Clear the module-level caches before each test."""
        _memory_data.clear()
        _memory_file_mtime.clear()

    def test_empty_memory_structure(self):
        """Empty memory has the expected structure."""
        memory = _create_empty_memory()
        assert memory["version"] == "1.0"
        assert "user" in memory
        assert "history" in memory
        assert "facts" in memory
        assert isinstance(memory["facts"], list)

    def test_get_memory_returns_empty_for_new_user(self):
        """Getting memory for a user with no file returns empty memory."""
        memory = get_memory_data("nonexistent-user")
        assert memory["version"] == "1.0"
        assert memory["facts"] == []

    def test_memory_cached_per_user(self):
        """Memory data is cached separately per user."""
        mem_a = get_memory_data("user-A")
        mem_b = get_memory_data("user-B")

        # Both should be separate objects
        assert mem_a is not mem_b

        # Modify one; the other should not change
        mem_a["facts"].append({"id": "test-fact"})
        assert len(mem_b["facts"]) == 0

    def test_reload_memory_forces_cache_invalidation(self):
        """reload_memory_data forces a fresh read from disk."""
        import uuid

        unique_user = f"reload-user-{uuid.uuid4().hex[:8]}"

        # Get initial memory (empty, cached)
        mem = get_memory_data(unique_user)
        assert mem["facts"] == []

        # Directly write to the memory file
        file_path = _get_memory_file_path(unique_user)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        custom_memory = _create_empty_memory()
        custom_memory["facts"].append({"id": "disk-fact", "content": "from disk"})
        file_path.write_text(json.dumps(custom_memory), encoding="utf-8")

        # Force reload - should pick up the file change.
        reloaded = reload_memory_data(unique_user)
        assert len(reloaded["facts"]) == 1
        assert reloaded["facts"][0]["id"] == "disk-fact"
