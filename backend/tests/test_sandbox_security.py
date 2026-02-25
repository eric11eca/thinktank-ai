"""Tests for provisioner Pod template security hardening.

Verifies that the provisioner creates Pods with proper security constraints:
- Non-root user, no privilege escalation
- Read-only root filesystem with writable tmpfs
- Correct resource limits (CPU, memory, ephemeral storage)
- Configurable limits via environment variables
"""

import importlib.util
import os
import sys
from unittest.mock import patch

# Load provisioner app.py directly by file path to avoid conflict with the
# 'docker' pip package (the provisioner lives in <repo>/docker/provisioner/).
_provisioner_app_path = os.path.join(os.path.dirname(__file__), "..", "..", "docker", "provisioner", "app.py")


def _load_provisioner(module_name: str = "provisioner_app"):
    """Load (or reload) the provisioner module from file path."""
    spec = importlib.util.spec_from_file_location(module_name, _provisioner_app_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


provisioner_app = _load_provisioner()
_build_pod = provisioner_app._build_pod


class TestPodSecurityContext:
    """Tests for the Pod security context configuration."""

    def test_no_privilege_escalation(self):
        pod = _build_pod("test-sandbox", "test-thread")
        sc = pod.spec.containers[0].security_context
        assert sc.allow_privilege_escalation is False

    def test_not_privileged(self):
        pod = _build_pod("test-sandbox", "test-thread")
        sc = pod.spec.containers[0].security_context
        assert sc.privileged is False

    def test_read_only_root_filesystem(self):
        pod = _build_pod("test-sandbox", "test-thread")
        sc = pod.spec.containers[0].security_context
        assert sc.read_only_root_filesystem is True

    def test_runs_as_non_root(self):
        pod = _build_pod("test-sandbox", "test-thread")
        sc = pod.spec.containers[0].security_context
        assert sc.run_as_non_root is True
        assert sc.run_as_user == 1000
        assert sc.run_as_group == 1000

    def test_capabilities_dropped(self):
        pod = _build_pod("test-sandbox", "test-thread")
        sc = pod.spec.containers[0].security_context
        assert "ALL" in sc.capabilities.drop
        assert "NET_BIND_SERVICE" in sc.capabilities.add


class TestPodResourceLimits:
    """Tests for Pod resource limits matching design doc."""

    def test_default_memory_limit(self):
        pod = _build_pod("test-sandbox", "test-thread")
        limits = pod.spec.containers[0].resources.limits
        assert limits["memory"] == "512Mi"

    def test_default_cpu_limit(self):
        pod = _build_pod("test-sandbox", "test-thread")
        limits = pod.spec.containers[0].resources.limits
        assert limits["cpu"] == "1000m"

    def test_default_ephemeral_storage_limit(self):
        pod = _build_pod("test-sandbox", "test-thread")
        limits = pod.spec.containers[0].resources.limits
        assert limits["ephemeral-storage"] == "5Gi"

    def test_resource_requests(self):
        pod = _build_pod("test-sandbox", "test-thread")
        requests = pod.spec.containers[0].resources.requests
        assert requests["cpu"] == "100m"
        assert requests["memory"] == "256Mi"
        assert requests["ephemeral-storage"] == "1Gi"

    @patch.dict(
        os.environ,
        {
            "SANDBOX_CPU_LIMIT": "2000m",
            "SANDBOX_MEMORY_LIMIT": "1Gi",
            "SANDBOX_EPHEMERAL_LIMIT": "10Gi",
        },
    )
    def test_configurable_limits_via_env(self):
        # Reload module to pick up env vars (they're module-level constants)
        reloaded = _load_provisioner("provisioner_app_env_test")

        pod = reloaded._build_pod("test-sandbox", "test-thread")
        limits = pod.spec.containers[0].resources.limits
        assert limits["cpu"] == "2000m"
        assert limits["memory"] == "1Gi"
        assert limits["ephemeral-storage"] == "10Gi"


class TestPodTmpfsVolumes:
    """Tests for writable tmpfs volumes supporting read-only root."""

    def test_tmp_volume_exists(self):
        pod = _build_pod("test-sandbox", "test-thread")
        volume_names = [v.name for v in pod.spec.volumes]
        assert "tmp" in volume_names

    def test_run_volume_exists(self):
        pod = _build_pod("test-sandbox", "test-thread")
        volume_names = [v.name for v in pod.spec.volumes]
        assert "run" in volume_names

    def test_tmp_volume_is_memory_backed(self):
        pod = _build_pod("test-sandbox", "test-thread")
        tmp_vol = next(v for v in pod.spec.volumes if v.name == "tmp")
        assert tmp_vol.empty_dir is not None
        assert tmp_vol.empty_dir.medium == "Memory"
        assert tmp_vol.empty_dir.size_limit == "100Mi"

    def test_run_volume_is_memory_backed(self):
        pod = _build_pod("test-sandbox", "test-thread")
        run_vol = next(v for v in pod.spec.volumes if v.name == "run")
        assert run_vol.empty_dir is not None
        assert run_vol.empty_dir.medium == "Memory"
        assert run_vol.empty_dir.size_limit == "10Mi"

    def test_tmp_mount_in_container(self):
        pod = _build_pod("test-sandbox", "test-thread")
        container = pod.spec.containers[0]
        tmp_mount = next(m for m in container.volume_mounts if m.name == "tmp")
        assert tmp_mount.mount_path == "/tmp"
        assert tmp_mount.read_only is False

    def test_run_mount_in_container(self):
        pod = _build_pod("test-sandbox", "test-thread")
        container = pod.spec.containers[0]
        run_mount = next(m for m in container.volume_mounts if m.name == "run")
        assert run_mount.mount_path == "/run"
        assert run_mount.read_only is False


class TestPodLabelsAndAnnotations:
    """Tests for pod labels and annotations."""

    def test_sandbox_labels(self):
        pod = _build_pod("test-sandbox", "test-thread")
        labels = pod.metadata.labels
        assert labels["app"] == "deer-flow-sandbox"
        assert labels["sandbox-id"] == "test-sandbox"

    def test_user_id_label_when_provided(self):
        pod = _build_pod("test-sandbox", "test-thread", user_id="user-123")
        labels = pod.metadata.labels
        assert labels["user-id"] == "user-123"

    def test_no_user_id_label_when_not_provided(self):
        pod = _build_pod("test-sandbox", "test-thread")
        labels = pod.metadata.labels
        assert "user-id" not in labels

    def test_pid_limit_annotation(self):
        pod = _build_pod("test-sandbox", "test-thread")
        annotations = pod.metadata.annotations
        assert "sandbox.thinktank.ai/pid-limit" in annotations

    def test_thread_id_annotation(self):
        pod = _build_pod("test-sandbox", "test-thread")
        annotations = pod.metadata.annotations
        assert annotations["sandbox.thinktank.ai/thread-id"] == "test-thread"


class TestPodVolumeMounts:
    """Tests for existing volume mounts still work."""

    def test_skills_mount_read_only(self):
        pod = _build_pod("test-sandbox", "test-thread")
        container = pod.spec.containers[0]
        skills_mount = next(m for m in container.volume_mounts if m.name == "skills")
        assert skills_mount.mount_path == "/mnt/skills"
        assert skills_mount.read_only is True

    def test_user_data_mount_writable(self):
        pod = _build_pod("test-sandbox", "test-thread")
        container = pod.spec.containers[0]
        data_mount = next(m for m in container.volume_mounts if m.name == "user-data")
        assert data_mount.mount_path == "/mnt/user-data"
        assert data_mount.read_only is False
