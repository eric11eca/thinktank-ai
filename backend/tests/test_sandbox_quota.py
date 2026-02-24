"""Tests for per-user sandbox quota enforcement.

Verifies that AioSandboxProvider correctly:
- Allows sandbox acquisition within quota
- Blocks acquisition when quota is exceeded
- Frees quota slots on release
- Isolates quotas between users
- Disables quota when max_sandboxes_per_user=0
- LocalSandboxProvider accepts user_id without error
"""

import threading
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_config():
    """Mock app config with sandbox settings."""
    config = MagicMock()
    config.sandbox.image = "test-image:latest"
    config.sandbox.port = 8080
    config.sandbox.base_url = None
    config.sandbox.auto_start = True
    config.sandbox.container_prefix = "test-sandbox"
    config.sandbox.idle_timeout = 0  # Disable idle checker for tests
    config.sandbox.mounts = []
    config.sandbox.environment = {}
    config.sandbox.provisioner_url = None
    config.sandbox.max_sandboxes_per_user = 3
    config.skills.get_skills_path.return_value = MagicMock(exists=lambda: False)
    config.skills.container_path = "/mnt/skills"
    return config


@pytest.fixture
def mock_backend():
    """Mock sandbox backend that succeeds immediately."""
    backend = MagicMock()
    # Each call returns a unique SandboxInfo
    call_count = {"n": 0}

    def create_side_effect(thread_id, sandbox_id, extra_mounts=None, user_id=None):
        from src.community.aio_sandbox.sandbox_info import SandboxInfo

        call_count["n"] += 1
        return SandboxInfo(
            sandbox_id=sandbox_id,
            sandbox_url=f"http://localhost:{8080 + call_count['n']}",
            container_name=f"test-container-{call_count['n']}",
        )

    backend.create.side_effect = create_side_effect
    backend.discover.return_value = None
    backend.is_alive.return_value = True
    return backend


@pytest.fixture
def provider(mock_config, mock_backend):
    """Create an AioSandboxProvider with mocked dependencies."""
    with (
        patch("src.community.aio_sandbox.aio_sandbox_provider.get_app_config", return_value=mock_config),
        patch("src.community.aio_sandbox.aio_sandbox_provider.wait_for_sandbox_ready", return_value=True),
        patch("src.community.aio_sandbox.aio_sandbox_provider.FileSandboxStateStore") as mock_store_cls,
        patch("src.community.aio_sandbox.aio_sandbox_provider.LocalContainerBackend", return_value=mock_backend),
        patch("src.community.aio_sandbox.aio_sandbox_provider.signal"),
    ):
        mock_store = MagicMock()
        mock_store.load.return_value = None
        mock_store.lock.return_value.__enter__ = lambda s: None
        mock_store.lock.return_value.__exit__ = lambda s, *a: None
        mock_store_cls.return_value = mock_store

        from src.community.aio_sandbox.aio_sandbox_provider import AioSandboxProvider

        p = AioSandboxProvider()
        yield p
        # Avoid shutdown side effects
        p._shutdown_called = True


class TestQuotaEnforcement:
    """Tests for per-user sandbox quota logic."""

    def test_acquire_within_quota_succeeds(self, provider):
        """User can acquire sandboxes up to the quota limit."""
        sandbox_id = provider.acquire("thread-1", user_id="user-a")
        assert sandbox_id is not None

    def test_acquire_multiple_within_quota(self, provider):
        """User can acquire multiple sandboxes within quota."""
        id1 = provider.acquire("thread-1", user_id="user-a")
        id2 = provider.acquire("thread-2", user_id="user-a")
        id3 = provider.acquire("thread-3", user_id="user-a")
        assert id1 is not None
        assert id2 is not None
        assert id3 is not None

    def test_acquire_exceeding_quota_raises(self, provider):
        """Acquiring beyond quota raises RuntimeError."""
        provider.acquire("thread-1", user_id="user-a")
        provider.acquire("thread-2", user_id="user-a")
        provider.acquire("thread-3", user_id="user-a")

        with pytest.raises(RuntimeError, match="maximum of 3"):
            provider.acquire("thread-4", user_id="user-a")

    def test_release_frees_quota_slot(self, provider):
        """Releasing a sandbox frees a quota slot for new acquisition."""
        id1 = provider.acquire("thread-1", user_id="user-a")
        provider.acquire("thread-2", user_id="user-a")
        provider.acquire("thread-3", user_id="user-a")

        # At quota limit — release one
        provider.release(id1)

        # Should now be able to acquire again
        id4 = provider.acquire("thread-4", user_id="user-a")
        assert id4 is not None

    def test_per_user_isolation(self, provider):
        """User A at max quota does not block user B."""
        provider.acquire("thread-1", user_id="user-a")
        provider.acquire("thread-2", user_id="user-a")
        provider.acquire("thread-3", user_id="user-a")

        # User A is at limit, but user B should still work
        id_b = provider.acquire("thread-4", user_id="user-b")
        assert id_b is not None

    def test_no_user_id_bypasses_quota(self, provider):
        """Acquisition without user_id is not subject to quota."""
        # Acquire many sandboxes with no user_id
        for i in range(5):
            sid = provider.acquire(f"thread-{i}")
            assert sid is not None


class TestQuotaDisabled:
    """Tests for quota behavior when disabled."""

    def test_zero_quota_disables_limit(self, mock_config, mock_backend):
        """Setting max_sandboxes_per_user=0 disables quota enforcement."""
        mock_config.sandbox.max_sandboxes_per_user = 0

        with (
            patch("src.community.aio_sandbox.aio_sandbox_provider.get_app_config", return_value=mock_config),
            patch("src.community.aio_sandbox.aio_sandbox_provider.wait_for_sandbox_ready", return_value=True),
            patch("src.community.aio_sandbox.aio_sandbox_provider.FileSandboxStateStore") as mock_store_cls,
            patch("src.community.aio_sandbox.aio_sandbox_provider.LocalContainerBackend", return_value=mock_backend),
            patch("src.community.aio_sandbox.aio_sandbox_provider.signal"),
        ):
            mock_store = MagicMock()
            mock_store.load.return_value = None
            mock_store.lock.return_value.__enter__ = lambda s: None
            mock_store.lock.return_value.__exit__ = lambda s, *a: None
            mock_store_cls.return_value = mock_store

            from src.community.aio_sandbox.aio_sandbox_provider import AioSandboxProvider

            p = AioSandboxProvider()
            try:
                # Should be able to create more than default limit
                for i in range(5):
                    sid = p.acquire(f"thread-{i}", user_id="user-a")
                    assert sid is not None
            finally:
                p._shutdown_called = True


class TestQuotaTracking:
    """Tests for internal user tracking bookkeeping."""

    def test_user_sandboxes_tracked(self, provider):
        """User-sandbox mapping is maintained internally."""
        provider.acquire("thread-1", user_id="user-a")
        provider.acquire("thread-2", user_id="user-a")

        assert "user-a" in provider._user_sandboxes
        assert len(provider._user_sandboxes["user-a"]) == 2

    def test_release_cleans_user_tracking(self, provider):
        """Releasing all sandboxes removes user from tracking."""
        id1 = provider.acquire("thread-1", user_id="user-a")

        provider.release(id1)

        assert "user-a" not in provider._user_sandboxes

    def test_reuse_same_thread_no_double_count(self, provider):
        """Acquiring same thread_id twice returns same sandbox (no double count)."""
        id1 = provider.acquire("thread-1", user_id="user-a")
        id2 = provider.acquire("thread-1", user_id="user-a")

        assert id1 == id2
        assert len(provider._user_sandboxes.get("user-a", set())) == 1


class TestLocalSandboxProviderUserIdCompat:
    """Tests that LocalSandboxProvider accepts user_id without error."""

    def test_acquire_with_user_id(self):
        """LocalSandboxProvider.acquire() works with user_id parameter."""
        import src.sandbox.local.local_sandbox_provider as lsp_module

        original_singleton = lsp_module._singleton
        lsp_module._singleton = None

        try:
            # _setup_path_mappings catches exceptions internally, so
            # even without a valid config it won't fail.
            p = lsp_module.LocalSandboxProvider()
            sid = p.acquire("thread-1", user_id="user-a")
            assert sid == "local"
        finally:
            lsp_module._singleton = original_singleton

    def test_acquire_without_user_id(self):
        """LocalSandboxProvider.acquire() still works without user_id."""
        import src.sandbox.local.local_sandbox_provider as lsp_module

        original_singleton = lsp_module._singleton
        lsp_module._singleton = None

        try:
            p = lsp_module.LocalSandboxProvider()
            sid = p.acquire("thread-1")
            assert sid == "local"
        finally:
            lsp_module._singleton = original_singleton
