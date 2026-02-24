"""Tests for the file-based thread ownership store."""

import json

from src.gateway.auth.thread_store import (
    claim_thread,
    delete_thread,
    get_thread_owner,
    get_user_threads,
    is_thread_owner,
)


class TestClaimThread:
    """Tests for thread claiming (lazy ownership)."""

    def test_claim_unclaimed_thread(self, tmp_store_dir):
        """Claiming an unclaimed thread succeeds and returns True."""
        assert claim_thread("thread-1", "user-A") is True

    def test_claim_own_thread(self, tmp_store_dir):
        """Re-claiming a thread the user already owns returns True."""
        claim_thread("thread-1", "user-A")
        assert claim_thread("thread-1", "user-A") is True

    def test_claim_other_users_thread(self, tmp_store_dir):
        """Claiming a thread owned by another user returns False."""
        claim_thread("thread-1", "user-A")
        assert claim_thread("thread-1", "user-B") is False

    def test_claim_persists_to_disk(self, tmp_store_dir):
        """Thread ownership is persisted to disk."""
        claim_thread("thread-persist", "user-X")

        data_file = tmp_store_dir / "thread-ownership.json"
        assert data_file.exists()

        data = json.loads(data_file.read_text(encoding="utf-8"))
        assert "thread-persist" in data["threads"]
        assert data["threads"]["thread-persist"]["user_id"] == "user-X"


class TestGetThreadOwner:
    """Tests for querying thread ownership."""

    def test_unclaimed_thread(self, tmp_store_dir):
        """An unclaimed thread has no owner (None)."""
        assert get_thread_owner("unclaimed-thread") is None

    def test_claimed_thread(self, tmp_store_dir):
        """A claimed thread returns the correct owner."""
        claim_thread("claimed-thread", "user-A")
        assert get_thread_owner("claimed-thread") == "user-A"


class TestIsThreadOwner:
    """Tests for ownership check."""

    def test_unclaimed_thread(self, tmp_store_dir):
        """Any user is considered an owner of an unclaimed thread."""
        assert is_thread_owner("unclaimed", "user-A") is True
        assert is_thread_owner("unclaimed", "user-B") is True

    def test_owned_by_same_user(self, tmp_store_dir):
        """The actual owner is recognized."""
        claim_thread("thread-1", "user-A")
        assert is_thread_owner("thread-1", "user-A") is True

    def test_owned_by_different_user(self, tmp_store_dir):
        """A non-owner is rejected."""
        claim_thread("thread-1", "user-A")
        assert is_thread_owner("thread-1", "user-B") is False


class TestGetUserThreads:
    """Tests for listing threads owned by a user."""

    def test_no_threads(self, tmp_store_dir):
        """A user with no threads gets an empty list."""
        assert get_user_threads("user-A") == []

    def test_single_thread(self, tmp_store_dir):
        """A user with one thread gets a list with one ID."""
        claim_thread("thread-1", "user-A")
        assert get_user_threads("user-A") == ["thread-1"]

    def test_multiple_threads(self, tmp_store_dir):
        """A user with multiple threads gets all their IDs."""
        claim_thread("thread-1", "user-A")
        claim_thread("thread-2", "user-A")
        claim_thread("thread-3", "user-B")  # Different user

        user_a_threads = get_user_threads("user-A")
        assert set(user_a_threads) == {"thread-1", "thread-2"}

    def test_does_not_include_other_users_threads(self, tmp_store_dir):
        """Only threads owned by the requested user are returned."""
        claim_thread("thread-1", "user-A")
        claim_thread("thread-2", "user-B")
        assert get_user_threads("user-B") == ["thread-2"]


class TestDeleteThread:
    """Tests for thread ownership deletion."""

    def test_delete_existing_thread(self, tmp_store_dir):
        """Deleting an existing thread removes its ownership record."""
        claim_thread("thread-del", "user-A")
        assert get_thread_owner("thread-del") == "user-A"

        delete_thread("thread-del")
        assert get_thread_owner("thread-del") is None

    def test_delete_nonexistent_thread(self, tmp_store_dir):
        """Deleting a nonexistent thread is a no-op (no error)."""
        delete_thread("nonexistent-thread")  # Should not raise
