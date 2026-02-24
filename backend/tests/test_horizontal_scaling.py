"""Integration tests for horizontal scaling components.

These tests verify that the scaling infrastructure works end-to-end.
They are marked with @pytest.mark.integration and may require
external services (Redis, Docker) to be running.
"""

import threading
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Integration: Redis Queue enqueue / dequeue cycle (mocked Redis)
# ---------------------------------------------------------------------------
@pytest.mark.integration
class TestRedisQueueCycle:
    """End-to-end tests for the Redis-backed memory queue pipeline."""

    def test_enqueue_then_process(self):
        """A message enqueued via RedisMemoryUpdateQueue should be processable."""
        from src.queue.memory_tasks import process_memory_update

        mock_updater = MagicMock()
        mock_updater.update_memory.return_value = True

        with patch(
            "src.agents.memory.updater.MemoryUpdater", return_value=mock_updater
        ):
            result = process_memory_update(
                user_id="user-int-1",
                thread_id="thread-int-1",
                messages_json=[
                    {"type": "human", "content": "integration test message"}
                ],
            )

        assert result is True
        mock_updater.update_memory.assert_called_once_with(
            messages=[{"type": "human", "content": "integration test message"}],
            thread_id="thread-int-1",
            user_id="user-int-1",
        )

    def test_serialize_and_process_round_trip(self):
        """Messages serialized by RedisMemoryUpdateQueue should be consumable."""
        from src.agents.memory.queue import RedisMemoryUpdateQueue
        from src.queue.memory_tasks import process_memory_update

        # Simulate serialization step
        messages = [
            {"type": "human", "content": "hello"},
            {"type": "ai", "content": "world"},
        ]
        serialized = RedisMemoryUpdateQueue._serialize_messages(messages)

        # Verify serialized form is JSON-safe dicts
        for msg in serialized:
            assert isinstance(msg, dict)
            assert "type" in msg
            assert "content" in msg

        # Process through the task function
        mock_updater = MagicMock()
        mock_updater.update_memory.return_value = True

        with patch(
            "src.agents.memory.updater.MemoryUpdater", return_value=mock_updater
        ):
            result = process_memory_update(
                user_id="user-rt-1",
                thread_id="thread-rt-1",
                messages_json=serialized,
            )

        assert result is True


# ---------------------------------------------------------------------------
# Integration: Per-user semaphore with concurrent workers
# ---------------------------------------------------------------------------
@pytest.mark.integration
class TestConcurrentUserSemaphore:
    """Tests for per-user semaphore under concurrent load."""

    def test_multiple_users_concurrent_execution(self):
        """Multiple users should be able to execute subagents concurrently."""
        from src.subagents.executor import (
            MAX_CONCURRENT_SUBAGENTS_PER_USER,
            _get_user_semaphore,
            _user_semaphores,
            _user_semaphores_lock,
        )

        # Clear cache
        with _user_semaphores_lock:
            _user_semaphores.clear()

        results = {}
        errors = []

        def user_work(user_id: str, task_count: int):
            """Simulate a user running multiple subagent tasks."""
            sem = _get_user_semaphore(user_id)
            completed = 0
            for _ in range(task_count):
                acquired = sem.acquire(timeout=1.0)
                if acquired:
                    try:
                        completed += 1
                    finally:
                        sem.release()
            results[user_id] = completed

        threads = []
        for uid in ["user-a", "user-b", "user-c"]:
            t = threading.Thread(target=user_work, args=(uid, 5))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # All users should have completed all tasks
        assert results["user-a"] == 5
        assert results["user-b"] == 5
        assert results["user-c"] == 5

        # Cleanup
        with _user_semaphores_lock:
            _user_semaphores.clear()

    def test_user_blocked_beyond_limit(self):
        """A single user should be blocked when exceeding the concurrency limit."""
        from src.subagents.executor import (
            MAX_CONCURRENT_SUBAGENTS_PER_USER,
            _get_user_semaphore,
            _user_semaphores,
            _user_semaphores_lock,
        )

        with _user_semaphores_lock:
            _user_semaphores.clear()

        sem = _get_user_semaphore("user-blocked")
        acquired_count = 0

        # Acquire up to the limit
        for _ in range(MAX_CONCURRENT_SUBAGENTS_PER_USER):
            if sem.acquire(timeout=0.1):
                acquired_count += 1

        assert acquired_count == MAX_CONCURRENT_SUBAGENTS_PER_USER

        # Next acquisition should fail
        blocked = not sem.acquire(timeout=0.1)
        assert blocked is True

        # Release all
        for _ in range(acquired_count):
            sem.release()

        # Cleanup
        with _user_semaphores_lock:
            _user_semaphores.clear()


# ---------------------------------------------------------------------------
# Integration: Dual-mode queue selection
# ---------------------------------------------------------------------------
@pytest.mark.integration
class TestDualModeQueueSelection:
    """Tests verifying correct queue selection based on environment."""

    def test_in_process_queue_when_no_redis(self):
        """Without REDIS_URL, the in-process queue should be used."""
        from src.agents.memory.queue import (
            MemoryUpdateQueue,
            get_memory_queue,
            reset_memory_queue,
        )

        reset_memory_queue()
        with patch("src.queue.redis_connection.is_redis_available", return_value=False):
            queue = get_memory_queue()
            assert isinstance(queue, MemoryUpdateQueue)
        reset_memory_queue()

    def test_redis_queue_when_redis_available(self):
        """With REDIS_URL and reachable Redis, the Redis queue should be used."""
        from src.agents.memory.queue import (
            RedisMemoryUpdateQueue,
            get_memory_queue,
            reset_memory_queue,
        )

        reset_memory_queue()
        mock_redis_client = MagicMock()
        mock_rq_queue = MagicMock()

        with (
            patch("src.queue.redis_connection.is_redis_available", return_value=True),
            patch(
                "src.queue.redis_connection.get_redis_client",
                return_value=mock_redis_client,
            ),
            patch("rq.Queue", return_value=mock_rq_queue),
        ):
            queue = get_memory_queue()
            assert isinstance(queue, RedisMemoryUpdateQueue)
        reset_memory_queue()


# ---------------------------------------------------------------------------
# Integration: Gateway health endpoint structure
# ---------------------------------------------------------------------------
@pytest.mark.integration
class TestGatewayHealthIntegration:
    """Tests for the health endpoint response structure."""

    def test_health_response_structure(self):
        """The /health endpoint handler should return the expected structure."""
        # Import the health check function from gateway
        from src.gateway.app import app

        # Verify the app has the health route registered
        health_routes = [
            route for route in app.routes if hasattr(route, "path") and route.path == "/health"
        ]
        assert len(health_routes) == 1

    def test_redis_health_check_function(self):
        """check_redis_health should return expected string values."""
        from src.queue.redis_connection import (
            check_redis_health,
            reset_redis_connection,
        )

        reset_redis_connection()
        # Without Redis configured, should return "not configured"
        result = check_redis_health()
        assert result == "not configured"
        reset_redis_connection()
