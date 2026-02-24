"""Thread ownership validation helpers."""

from __future__ import annotations

from fastapi import HTTPException, status

from src.gateway.auth.thread_store import claim_thread


def verify_thread_ownership(thread_id: str, user_id: str) -> None:
    """Verify that a user owns a thread.

    Uses lazy claiming: if the thread is unclaimed, it is assigned to the user.
    If it belongs to a different user, raises 403.

    Args:
        thread_id: The thread identifier.
        user_id: The user to verify.

    Raises:
        HTTPException: 403 if the thread belongs to a different user.
    """
    if not claim_thread(thread_id, user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this thread",
        )
