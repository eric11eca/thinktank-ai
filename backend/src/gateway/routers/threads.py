"""Thread router for thread-level operations."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import RemoveMessage
from langgraph_sdk import get_client
from pydantic import BaseModel

from src.gateway.auth.middleware import get_current_user
from src.gateway.auth.ownership import verify_thread_ownership

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/threads/{thread_id}", tags=["threads"])


class TruncateMessagesRequest(BaseModel):
    """Request model for truncating messages."""

    message_index: int


class TruncateMessagesResponse(BaseModel):
    """Response model for message truncation."""

    success: bool
    messages_kept: int
    messages_removed: int
    checkpoint_id: str | None = None
    checkpoint_ns: str | None = None


@router.post("/truncate-messages", response_model=TruncateMessagesResponse)
async def truncate_messages(
    thread_id: str,
    request: TruncateMessagesRequest,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> TruncateMessagesResponse:
    """Truncate thread messages up to a specific index.

    This endpoint removes all messages after the specified index and prepares
    the thread for regenerating responses from that point.

    Args:
        thread_id: The thread ID
        request: Request containing the message_index to truncate from
        current_user: The authenticated user (injected by dependency).

    Returns:
        Response with truncation results

    Raises:
        HTTPException: If truncation fails
    """
    verify_thread_ownership(thread_id, current_user["id"])

    try:
        # Get LangGraph client
        client = get_client(url="http://localhost:2024")

        # Get current thread state
        state = await client.threads.get_state(thread_id)

        # state is a dict with keys like 'values', 'next', 'checkpoint', etc.
        # The actual thread data is in state['values']
        if not state or "values" not in state or "messages" not in state["values"]:
            raise HTTPException(status_code=404, detail="Thread or messages not found")

        raw_messages = state["values"]["messages"]
        message_index = request.message_index

        # Validate index
        if message_index < 0 or message_index >= len(raw_messages):
            raise HTTPException(status_code=400, detail=f"Invalid message index: {message_index}. Valid range: 0-{len(raw_messages) - 1}")

        # Remove the selected message and everything after it.
        messages_to_remove = raw_messages[message_index:]
        messages_kept = message_index
        messages_removed = len(messages_to_remove)

        remove_message_updates: list[RemoveMessage] = []
        for msg in messages_to_remove:
            msg_id = msg.get("id") if isinstance(msg, dict) else getattr(msg, "id", None)
            if msg_id:
                remove_message_updates.append(RemoveMessage(id=msg_id))
            else:
                logger.warning(f"Skipping message without id during truncation for thread {thread_id}: {msg}")

        if not remove_message_updates:
            raise HTTPException(status_code=400, detail="No valid messages found to remove")

        # Use RemoveMessage updates so LangGraph's add_messages reducer actually
        # deletes messages instead of merging/appending.
        update_result = await client.threads.update_state(
            thread_id,
            {
                "messages": remove_message_updates,
            },
        )

        checkpoint = update_result.get("checkpoint", {}) if isinstance(update_result, dict) else {}
        checkpoint_id = checkpoint.get("checkpoint_id") if isinstance(checkpoint, dict) else None
        checkpoint_ns = checkpoint.get("checkpoint_ns") if isinstance(checkpoint, dict) else None

        logger.info(f"Truncated thread {thread_id}: kept {messages_kept} messages, removed {messages_removed}")

        return TruncateMessagesResponse(
            success=True,
            messages_kept=messages_kept,
            messages_removed=messages_removed,
            checkpoint_id=checkpoint_id,
            checkpoint_ns=checkpoint_ns,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error truncating messages for thread {thread_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to truncate messages: {str(e)}")
