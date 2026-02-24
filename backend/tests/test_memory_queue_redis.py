"""Tests for Redis-backed memory queue with graceful fallback."""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.agents.memory.queue import (
    DEFAULT_USER_ID,
    MemoryUpdateQueue,
    RedisMemoryUpdateQueue,
    get_memory_queue,
    reset_memory_queue,
)


@pytest.fixture(autouse=True)
def _reset_queue():
    """Reset the global memory queue before and after each test."""
    reset_memory_queue()
    yield
    reset_memory_queue()


class TestGetMemoryQueueFallback:
    """Tests for dual-mode queue selection."""

    def test_returns_in_process_queue_without_redis(self):
        """Should return MemoryUpdateQueue when Redis is not available."""
        with patch("src.queue.redis_connection.is_redis_available", return_value=False):
            queue = get_memory_queue()
            assert isinstance(queue, MemoryUpdateQueue)

    def test_returns_redis_queue_when_available(self):
        """Should return RedisMemoryUpdateQueue when Redis is available."""
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

    def test_singleton_returns_same_instance(self):
        """Calling get_memory_queue twice should return the same instance."""
        with patch("src.queue.redis_connection.is_redis_available", return_value=False):
            queue1 = get_memory_queue()
            queue2 = get_memory_queue()
            assert queue1 is queue2


class TestRedisMemoryUpdateQueueSerialize:
    """Tests for message serialization."""

    def test_serialize_plain_dicts(self):
        """Plain dicts should pass through unchanged."""
        messages = [{"type": "human", "content": "hello"}]
        result = RedisMemoryUpdateQueue._serialize_messages(messages)
        assert result == [{"type": "human", "content": "hello"}]

    def test_serialize_objects_with_model_dump(self):
        """Objects with model_dump() should be serialized via that method."""
        mock_msg = MagicMock()
        mock_msg.model_dump.return_value = {"type": "ai", "content": "hi"}
        # Ensure hasattr check for model_dump succeeds
        mock_msg.__class__ = type("MockMessage", (), {"model_dump": lambda s: {"type": "ai", "content": "hi"}})

        messages = [mock_msg]
        result = RedisMemoryUpdateQueue._serialize_messages(messages)
        assert result[0] == {"type": "ai", "content": "hi"}

    def test_serialize_fallback_for_unknown_types(self):
        """Unknown types should be serialized as {type, content} dicts."""
        messages = ["plain string message"]
        result = RedisMemoryUpdateQueue._serialize_messages(messages)
        assert result[0]["type"] == "str"
        assert result[0]["content"] == "plain string message"

    def test_serialize_mixed_messages(self):
        """Mixed message types should all be serialized correctly."""
        messages = [
            {"type": "human", "content": "hello"},
            42,  # unexpected type
        ]
        result = RedisMemoryUpdateQueue._serialize_messages(messages)
        assert len(result) == 2
        assert result[0] == {"type": "human", "content": "hello"}
        assert result[1]["type"] == "int"


class TestRedisMemoryUpdateQueueAdd:
    """Tests for Redis queue add with debounce."""

    def _make_queue(self):
        """Create a RedisMemoryUpdateQueue with mocked Redis and RQ."""
        mock_redis = MagicMock()
        mock_rq_queue = MagicMock()
        mock_job = MagicMock()
        mock_job.id = "job-123"
        mock_rq_queue.enqueue_in.return_value = mock_job

        with (
            patch(
                "src.queue.redis_connection.get_redis_client",
                return_value=mock_redis,
            ),
            patch("rq.Queue", return_value=mock_rq_queue),
        ):
            queue = RedisMemoryUpdateQueue()

        # Override internals for testing
        queue._rq_queue = mock_rq_queue
        queue._redis = mock_redis
        return queue, mock_rq_queue

    def test_add_enqueues_delayed_job(self):
        """add() should enqueue a delayed job via RQ."""
        queue, mock_rq = self._make_queue()

        with patch("src.config.memory_config.get_memory_config") as mock_config:
            mock_config.return_value.enabled = True
            mock_config.return_value.debounce_seconds = 30

            queue.add("thread-1", [{"content": "hello"}], user_id="user-1")

        mock_rq.enqueue_in.assert_called_once()
        call_args = mock_rq.enqueue_in.call_args
        # Verify debounce delay is passed
        assert call_args[0][0].total_seconds() == 30
        # Verify job function path
        assert call_args[0][1] == "src.queue.memory_tasks.process_memory_update"

    def test_add_cancels_existing_job_for_same_key(self):
        """add() should cancel the previous pending job for the same (user_id, thread_id)."""
        queue, mock_rq = self._make_queue()

        mock_job_1 = MagicMock()
        mock_job_1.id = "job-1"
        mock_job_1.get_status.return_value = "scheduled"

        mock_job_2 = MagicMock()
        mock_job_2.id = "job-2"
        mock_rq.enqueue_in.side_effect = [mock_job_1, mock_job_2]

        with (
            patch("src.config.memory_config.get_memory_config") as mock_config,
            patch("rq.job.Job.fetch", return_value=mock_job_1),
        ):
            mock_config.return_value.enabled = True
            mock_config.return_value.debounce_seconds = 30

            # First add
            queue.add("thread-1", [{"content": "v1"}], user_id="user-1")
            # Second add for same key should cancel first
            queue.add("thread-1", [{"content": "v2"}], user_id="user-1")

        # The first job should have been cancelled
        mock_job_1.cancel.assert_called_once()

    def test_pending_count(self):
        """pending_count should track number of pending jobs."""
        queue, mock_rq = self._make_queue()

        with patch("src.config.memory_config.get_memory_config") as mock_config:
            mock_config.return_value.enabled = True
            mock_config.return_value.debounce_seconds = 30

            queue.add("thread-1", [], user_id="user-1")
            assert queue.pending_count == 1

            new_job = MagicMock()
            new_job.id = "job-456"
            mock_rq.enqueue_in.return_value = new_job
            queue.add("thread-2", [], user_id="user-1")
            assert queue.pending_count == 2

    def test_is_processing_always_false(self):
        """is_processing should be False (processing happens in workers)."""
        queue, _ = self._make_queue()
        assert queue.is_processing is False


class TestMemoryTaskFunction:
    """Tests for the RQ job function."""

    def test_process_memory_update_calls_updater(self):
        """process_memory_update should create MemoryUpdater and call update_memory."""
        from src.queue.memory_tasks import process_memory_update

        mock_updater = MagicMock()
        mock_updater.update_memory.return_value = True

        with patch(
            "src.agents.memory.updater.MemoryUpdater", return_value=mock_updater
        ):
            result = process_memory_update(
                user_id="user-1",
                thread_id="thread-1",
                messages_json=[{"type": "human", "content": "hello"}],
            )

        assert result is True
        mock_updater.update_memory.assert_called_once_with(
            messages=[{"type": "human", "content": "hello"}],
            thread_id="thread-1",
            user_id="user-1",
        )

    def test_process_memory_update_handles_failure(self):
        """process_memory_update should return False on failure."""
        from src.queue.memory_tasks import process_memory_update

        mock_updater = MagicMock()
        mock_updater.update_memory.return_value = False

        with patch(
            "src.agents.memory.updater.MemoryUpdater", return_value=mock_updater
        ):
            result = process_memory_update(
                user_id="user-1",
                thread_id="thread-1",
                messages_json=[],
            )

        assert result is False
