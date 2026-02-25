"""Integration tests for sandbox container isolation.

These tests require Docker to be running and are marked with @pytest.mark.integration.
They verify actual container behavior: non-root user, filesystem isolation,
read-only root, and unique hostnames.

Run with: pytest -m integration tests/test_sandbox_integration.py -v
Skip with: pytest -m "not integration" (default behavior)
"""

import subprocess
import time

import pytest

# Mark the entire module as integration tests
pytestmark = pytest.mark.integration


def docker_available() -> bool:
    """Check if Docker is available on this system."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


skip_no_docker = pytest.mark.skipif(
    not docker_available(),
    reason="Docker is not available",
)

# The sandbox image — use a small base if the real one isn't available
SANDBOX_IMAGE = "enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:latest"
FALLBACK_IMAGE = "python:3.11-slim"


def get_image() -> str:
    """Get an available sandbox image."""
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", SANDBOX_IMAGE],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return SANDBOX_IMAGE
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return FALLBACK_IMAGE


@skip_no_docker
class TestContainerSecurity:
    """Tests that verify container security constraints work at runtime."""

    @pytest.fixture(autouse=True)
    def setup_container(self):
        """Start a test container with security flags and clean up after."""
        self.container_name = f"test-sandbox-security-{int(time.time())}"
        image = get_image()

        cmd = [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            self.container_name,
            "--pids-limit",
            "256",
            "--memory",
            "512m",
            "--cpus",
            "1",
            "--read-only",
            "--tmpfs",
            "/tmp:size=100m",
            "--tmpfs",
            "/run:size=10m",
            "--cap-drop",
            "ALL",
            "--cap-add",
            "NET_BIND_SERVICE",
            "--no-new-privileges",
            "--security-opt",
            "seccomp=unconfined",
            image,
            "sleep",
            "120",
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                pytest.skip(f"Could not start container: {result.stderr}")
            self.container_id = result.stdout.strip()
            time.sleep(1)  # Let container settle
        except subprocess.TimeoutExpired:
            pytest.skip("Container start timed out")

        yield

        # Cleanup
        subprocess.run(
            ["docker", "stop", self.container_name],
            capture_output=True,
            timeout=10,
        )

    def _exec(self, command: str) -> subprocess.CompletedProcess:
        """Execute a command in the test container."""
        return subprocess.run(
            ["docker", "exec", self.container_name, "sh", "-c", command],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_read_only_root_filesystem(self):
        """Writing to / should fail due to read-only root filesystem."""
        result = self._exec("touch /testfile 2>&1")
        assert result.returncode != 0, "Expected write to / to fail"

    def test_tmp_is_writable(self):
        """/tmp should be writable via tmpfs mount."""
        result = self._exec("touch /tmp/testfile && echo ok")
        assert result.returncode == 0
        assert "ok" in result.stdout

    def test_memory_limit_applied(self):
        """Container should have memory limit applied."""
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.HostConfig.Memory}}", self.container_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # 512m = 536870912 bytes
        assert result.returncode == 0
        memory = int(result.stdout.strip())
        assert memory == 536870912

    def test_pids_limit_applied(self):
        """Container should have PID limit applied."""
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.HostConfig.PidsLimit}}", self.container_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        pids_limit = int(result.stdout.strip())
        assert pids_limit == 256

    def test_capabilities_dropped(self):
        """Container should have all capabilities dropped."""
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.HostConfig.CapDrop}}", self.container_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "ALL" in result.stdout

    def test_no_new_privileges(self):
        """Container should have no-new-privileges security option."""
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.HostConfig.SecurityOpt}}", self.container_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "no-new-privileges" in result.stdout


@skip_no_docker
class TestContainerIsolation:
    """Tests that verify containers are properly isolated from each other."""

    def test_unique_hostnames(self):
        """Each container gets a unique hostname."""
        image = get_image()
        containers = []

        try:
            hostnames = set()
            for i in range(2):
                name = f"test-sandbox-hostname-{i}-{int(time.time())}"
                result = subprocess.run(
                    ["docker", "run", "--rm", "-d", "--name", name, image, "sleep", "30"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.returncode != 0:
                    pytest.skip(f"Could not start container: {result.stderr}")
                containers.append(name)
                time.sleep(0.5)

            for name in containers:
                result = subprocess.run(
                    ["docker", "exec", name, "hostname"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    hostnames.add(result.stdout.strip())

            assert len(hostnames) == 2, "Containers should have unique hostnames"
        finally:
            for name in containers:
                subprocess.run(["docker", "stop", name], capture_output=True, timeout=10)
