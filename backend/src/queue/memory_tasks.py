"""Redis-backed memory update tasks for distributed processing.

This module defines RQ job functions that run in background worker processes.
Messages must be pre-serialized to JSON-safe dicts before enqueuing.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def process_memory_update(
    user_id: str,
    thread_id: str,
    messages_json: list[dict[str, Any]],
) -> bool:
    """RQ job function: process a single memory update.

    This function runs in the RQ worker process. It creates a MemoryUpdater
    and invokes update_memory with the pre-serialized messages.

    Args:
        user_id: The user whose memory to update.
        thread_id: The conversation thread ID.
        messages_json: Serialized message list (dicts, not LangChain objects).

    Returns:
        True if update succeeded.
    """
    from src.agents.memory.updater import MemoryUpdater

    logger.info(f"Processing memory update for user {user_id}, thread {thread_id}")

    updater = MemoryUpdater()
    success = updater.update_memory(
        messages=messages_json,
        thread_id=thread_id,
        user_id=user_id,
    )

    if success:
        logger.info(f"Memory update completed for user {user_id}, thread {thread_id}")
    else:
        logger.warning(f"Memory update failed/skipped for user {user_id}, thread {thread_id}")

    return success
