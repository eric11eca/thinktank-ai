"""Middleware to track and emit token usage metrics per model call."""

import logging
import threading
from typing import override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langgraph.config import get_stream_writer
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)

# Thread-safe accumulator for subagent usage that hasn't been drained yet.
# Keyed by thread_id so each conversation accumulates independently.
_pending_subagent_usage: dict[str, dict[str, int]] = {}
_pending_lock = threading.Lock()


def add_subagent_usage(thread_id: str, usage: dict[str, int] | None) -> None:
    """Register subagent token usage for later draining by the lead agent."""
    if not usage or not thread_id:
        return
    with _pending_lock:
        existing = _pending_subagent_usage.get(thread_id)
        if existing is None:
            _pending_subagent_usage[thread_id] = {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            }
        else:
            existing["input_tokens"] += usage.get("input_tokens", 0)
            existing["output_tokens"] += usage.get("output_tokens", 0)


def drain_subagent_usage(thread_id: str) -> dict[str, int] | None:
    """Pop and return any pending subagent usage for a thread."""
    if not thread_id:
        return None
    with _pending_lock:
        return _pending_subagent_usage.pop(thread_id, None)


class UsageTrackingMiddleware(AgentMiddleware[AgentState]):
    """Extracts token usage after each model call and emits a custom SSE event.

    - Reads ``usage_metadata`` from the latest ``AIMessage``
    - Drains any pending subagent usage accumulated via :func:`add_subagent_usage`
    - Emits a ``usage_update`` custom event for real-time frontend display
    - Returns ``{token_usage: delta}`` so the ``merge_token_usage`` reducer accumulates totals
    """

    def _extract_and_emit(self, state: AgentState, runtime: Runtime) -> dict | None:
        messages = state.get("messages", [])
        if not messages:
            return None

        last_msg = messages[-1]
        if getattr(last_msg, "type", None) != "ai":
            return None

        usage = getattr(last_msg, "usage_metadata", None)
        if not usage:
            return None

        delta = {
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
        }

        # Drain pending subagent usage
        thread_id = runtime.context.get("thread_id")
        if thread_id:
            sub_usage = drain_subagent_usage(thread_id)
            if sub_usage:
                delta["input_tokens"] += sub_usage["input_tokens"]
                delta["output_tokens"] += sub_usage["output_tokens"]

        # Emit custom SSE event for real-time frontend display
        try:
            writer = get_stream_writer()
            writer({
                "type": "usage_update",
                "input_tokens": delta["input_tokens"],
                "output_tokens": delta["output_tokens"],
            })
        except Exception:
            # Stream writer may not be available in all contexts (e.g. tests)
            logger.debug("Could not emit usage_update event (no stream writer)")

        return {"token_usage": delta}

    @override
    def after_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._extract_and_emit(state, runtime)

    @override
    async def aafter_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        return self._extract_and_emit(state, runtime)
