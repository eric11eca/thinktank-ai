"""Middleware for logging a chronological timeline of thread messages."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime

from src.sandbox.consts import THREAD_DATA_BASE_DIR

_WRITE_LOCK = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_outputs_path(state: AgentState, thread_id: str) -> str:
    thread_data = state.get("thread_data") or {}
    outputs_path = thread_data.get("outputs_path")
    if outputs_path:
        os.makedirs(outputs_path, exist_ok=True)
        return outputs_path
    fallback_path = Path(os.getcwd()) / THREAD_DATA_BASE_DIR / thread_id / "user-data" / "outputs"
    fallback_path.mkdir(parents=True, exist_ok=True)
    return str(fallback_path)


def _serialize_message(message: Any) -> dict:
    if hasattr(message, "model_dump"):
        return message.model_dump()
    if hasattr(message, "dict"):
        return message.dict()
    return {
        "type": getattr(message, "type", None),
        "content": getattr(message, "content", None),
        "additional_kwargs": getattr(message, "additional_kwargs", None),
    }


def _load_timeline(file_path: str, thread_id: str) -> dict:
    if os.path.exists(file_path):
        try:
            with open(file_path, encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict) and "events" in data:
                return data
        except Exception:
            pass
    return {
        "schema_version": 1,
        "thread_id": thread_id,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "last_message_index": 0,
        "events": [],
    }


def _write_timeline(file_path: str, data: dict) -> None:
    temp_path = f"{file_path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=True)
    os.replace(temp_path, file_path)


class TimelineLoggingMiddleware(AgentMiddleware[AgentState]):
    """Logs thread messages (human/ai/tool) as an ordered JSON timeline."""

    def _record_messages(self, state: AgentState, runtime: Runtime, stage: str) -> None:
        thread_id = runtime.context.get("thread_id")
        if not thread_id:
            return

        messages = state.get("messages", [])
        if not isinstance(messages, list):
            return

        outputs_path = _resolve_outputs_path(state, thread_id)
        timeline_path = os.path.join(outputs_path, "agent_timeline.json")

        with _WRITE_LOCK:
            timeline = _load_timeline(timeline_path, thread_id)
            last_index = int(timeline.get("last_message_index", 0) or 0)
            current_len = len(messages)

            if current_len < last_index:
                timeline["events"].append(
                    {
                        "event": "history_truncated",
                        "timestamp": _utc_now(),
                        "stage": stage,
                        "previous_last_index": last_index,
                        "current_length": current_len,
                    }
                )
                last_index = current_len

            if current_len > last_index:
                for idx in range(last_index, current_len):
                    msg = messages[idx]
                    timeline["events"].append(
                        {
                            "event": "message",
                            "timestamp": _utc_now(),
                            "stage": stage,
                            "message_index": idx,
                            "role": getattr(msg, "type", None),
                            "message_id": getattr(msg, "id", None),
                            "message": _serialize_message(msg),
                        }
                    )
                timeline["last_message_index"] = current_len
                timeline["updated_at"] = _utc_now()

            _write_timeline(timeline_path, timeline)

    @override
    def before_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        self._record_messages(state, runtime, "before_model")
        return None

    @override
    def after_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        self._record_messages(state, runtime, "after_model")
        return None

    @override
    def after_agent(self, state: AgentState, runtime: Runtime) -> dict | None:
        self._record_messages(state, runtime, "after_agent")
        return None

    @override
    async def abefore_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        self._record_messages(state, runtime, "before_model")
        return None

    @override
    async def aafter_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        self._record_messages(state, runtime, "after_model")
        return None

    @override
    async def aafter_agent(self, state: AgentState, runtime: Runtime) -> dict | None:
        self._record_messages(state, runtime, "after_agent")
        return None
