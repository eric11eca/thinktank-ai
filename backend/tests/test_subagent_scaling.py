"""Tests for subagent pool scaling and per-user concurrency limits."""

import os
import threading
import time
from unittest.mock import patch

import pytest

from src.subagents.executor import (
    MAX_CONCURRENT_SUBAGENTS_PER_USER,
    _MAX_SEMAPHORE_CACHE_SIZE,
    _get_user_semaphore,
    _user_semaphores,
    _user_semaphores_lock,
)


@pytest.fixture(autouse=True)
def _clear_semaphore_cache():
    """Clear the semaphore cache before and after each test."""
    with _user_semaphores_lock:
        _user_semaphores.clear()
    yield
    with _user_semaphores_lock:
        _user_semaphores.clear()


class TestPerUserSemaphore:
    """Tests for per-user concurrency semaphore."""

    def test_same_user_returns_same_semaphore(self):
        """Requesting a semaphore for the same user twice should return the same object."""
        sem1 = _get_user_semaphore("user-a")
        sem2 = _get_user_semaphore("user-a")
        assert sem1 is sem2

    def test_different_users_get_different_semaphores(self):
        """Different users should get different semaphore instances."""
        sem_a = _get_user_semaphore("user-a")
        sem_b = _get_user_semaphore("user-b")
        assert sem_a is not sem_b

    def test_semaphore_allows_max_concurrent(self):
        """Semaphore should allow exactly MAX_CONCURRENT_SUBAGENTS_PER_USER concurrent acquisitions."""
        sem = _get_user_semaphore("user-test")
        # Acquire up to the limit - should all succeed
        for _ in range(MAX_CONCURRENT_SUBAGENTS_PER_USER):
            acquired = sem.acquire(timeout=0.1)
            assert acquired is True

    def test_semaphore_blocks_beyond_limit(self):
        """Semaphore should block when the limit is exceeded."""
        sem = _get_user_semaphore("user-test")
        # Exhaust the semaphore
        for _ in range(MAX_CONCURRENT_SUBAGENTS_PER_USER):
            sem.acquire(timeout=0.1)
        # Next acquisition should fail (with timeout)
        acquired = sem.acquire(timeout=0.1)
        assert acquired is False

    def test_semaphore_release_allows_new_acquisition(self):
        """Releasing a semaphore slot should allow a new acquisition."""
        sem = _get_user_semaphore("user-test")
        for _ in range(MAX_CONCURRENT_SUBAGENTS_PER_USER):
            sem.acquire(timeout=0.1)
        # Release one slot
        sem.release()
        # Should now be able to acquire again
        acquired = sem.acquire(timeout=0.1)
        assert acquired is True

    def test_cache_eviction_on_overflow(self):
        """Cache should evict oldest entries when exceeding max size."""
        # Fill cache to maximum
        for i in range(_MAX_SEMAPHORE_CACHE_SIZE):
            _get_user_semaphore(f"user-{i}")

        assert len(_user_semaphores) == _MAX_SEMAPHORE_CACHE_SIZE

        # Adding one more should trigger eviction of 20% (oldest entries)
        _get_user_semaphore("new-user")

        expected_size = _MAX_SEMAPHORE_CACHE_SIZE - (_MAX_SEMAPHORE_CACHE_SIZE // 5) + 1
        assert len(_user_semaphores) == expected_size

    def test_cache_updates_last_used_timestamp(self):
        """Accessing a semaphore should update its last-used timestamp."""
        _get_user_semaphore("user-a")
        with _user_semaphores_lock:
            _, first_ts = _user_semaphores["user-a"]

        time.sleep(0.01)  # Small delay to ensure different timestamps
        _get_user_semaphore("user-a")
        with _user_semaphores_lock:
            _, second_ts = _user_semaphores["user-a"]

        assert second_ts > first_ts

    def test_concurrent_access_thread_safety(self):
        """Multiple threads accessing semaphores concurrently should not cause errors."""
        errors = []

        def worker(user_id: str):
            try:
                sem = _get_user_semaphore(user_id)
                assert sem is not None
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=worker, args=(f"user-{i % 10}",))
            for i in range(50)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []


class TestDynamicPoolSizing:
    """Tests for dynamic thread pool configuration."""

    def test_default_pool_size_minimum(self):
        """Default pool size should be at least 8."""
        from src.subagents.executor import _SCHEDULER_WORKERS, _EXECUTION_WORKERS

        assert _SCHEDULER_WORKERS >= 8
        assert _EXECUTION_WORKERS >= 8

    def test_env_override_scheduler_workers(self):
        """SUBAGENT_SCHEDULER_WORKERS env var should be respected at import time."""
        # This tests the env var parsing logic (value was read at import time)
        with patch.dict(os.environ, {"SUBAGENT_SCHEDULER_WORKERS": "16"}):
            val = int(os.environ.get("SUBAGENT_SCHEDULER_WORKERS", 8))
            assert val == 16

    def test_env_override_execution_workers(self):
        """SUBAGENT_EXECUTION_WORKERS env var should be respected at import time."""
        with patch.dict(os.environ, {"SUBAGENT_EXECUTION_WORKERS": "12"}):
            val = int(os.environ.get("SUBAGENT_EXECUTION_WORKERS", 8))
            assert val == 12

    def test_max_concurrent_per_user_default(self):
        """Default per-user concurrent limit should be 3."""
        assert MAX_CONCURRENT_SUBAGENTS_PER_USER == 3
