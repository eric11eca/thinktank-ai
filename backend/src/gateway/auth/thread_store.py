"""File-based thread ownership store.

Tracks which user owns which thread. Uses lazy claiming: the first
authenticated request that touches a thread claims ownership.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_STORE_DIR = Path(os.getcwd()) / ".think-tank"
_DATA_FILE = _STORE_DIR / "thread-ownership.json"


def _ensure_store_dir() -> None:
    _STORE_DIR.mkdir(parents=True, exist_ok=True)


def _load_store() -> dict[str, Any]:
    _ensure_store_dir()
    if not _DATA_FILE.exists():
        return {"schema_version": 1, "threads": {}}
    try:
        raw = _DATA_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError):
        return {"schema_version": 1, "threads": {}}
    if not isinstance(data, dict) or "threads" not in data:
        return {"schema_version": 1, "threads": {}}
    return data


def _save_store(data: dict[str, Any]) -> None:
    _ensure_store_dir()
    tmp_path = _DATA_FILE.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp_path, _DATA_FILE)
    try:
        os.chmod(_DATA_FILE, 0o600)
    except OSError:
        pass


def claim_thread(thread_id: str, user_id: str) -> bool:
    """Claim ownership of a thread.

    If the thread is unclaimed, assigns it to user_id.
    If it's already claimed by user_id, returns True.
    If it's claimed by a different user, returns False.

    Args:
        thread_id: The thread identifier.
        user_id: The user claiming the thread.

    Returns:
        True if the user owns the thread (either newly claimed or already owned).
        False if the thread belongs to a different user.
    """
    now = datetime.now(timezone.utc).isoformat()
    with _LOCK:
        data = _load_store()
        threads = data["threads"]

        existing = threads.get(thread_id)
        if existing is None:
            threads[thread_id] = {"user_id": user_id, "created_at": now}
            _save_store(data)
            return True

        return existing["user_id"] == user_id


def get_thread_owner(thread_id: str) -> str | None:
    """Get the owner of a thread.

    Args:
        thread_id: The thread identifier.

    Returns:
        The user_id of the owner, or None if the thread is unclaimed.
    """
    with _LOCK:
        data = _load_store()
        entry = data["threads"].get(thread_id)
        return entry["user_id"] if entry else None


def is_thread_owner(thread_id: str, user_id: str) -> bool:
    """Check if a user owns a thread.

    Args:
        thread_id: The thread identifier.
        user_id: The user to check.

    Returns:
        True if the user owns the thread or the thread is unclaimed.
    """
    owner = get_thread_owner(thread_id)
    return owner is None or owner == user_id


def get_user_threads(user_id: str) -> list[str]:
    """Get all thread IDs owned by a user.

    Args:
        user_id: The user identifier.

    Returns:
        List of thread IDs.
    """
    with _LOCK:
        data = _load_store()
        return [
            tid
            for tid, entry in data["threads"].items()
            if entry["user_id"] == user_id
        ]


def delete_thread(thread_id: str) -> None:
    """Remove thread ownership record.

    Args:
        thread_id: The thread identifier to remove.
    """
    with _LOCK:
        data = _load_store()
        data["threads"].pop(thread_id, None)
        _save_store(data)
