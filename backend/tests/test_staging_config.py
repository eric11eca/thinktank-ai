"""Tests for staging environment configuration.

Validates the staging Docker Compose file mirrors production services
and has appropriate staging-specific settings.
"""

from pathlib import Path

import yaml
import pytest


DOCKER_DIR = Path(__file__).parent.parent.parent / "docker"
STAGING_COMPOSE = DOCKER_DIR / "docker-compose-staging.yaml"
PROD_COMPOSE = DOCKER_DIR / "docker-compose-prod.yaml"
STAGING_ENV = DOCKER_DIR / ".env.staging.example"


def _load_compose(path: Path) -> dict:
    """Load and parse a Docker Compose YAML file."""
    assert path.exists(), f"Compose file not found: {path}"
    with open(path) as f:
        return yaml.safe_load(f)


class TestStagingComposeExists:
    """Verify staging configuration files exist."""

    def test_staging_compose_exists(self):
        assert STAGING_COMPOSE.exists(), "docker-compose-staging.yaml not found"

    def test_staging_env_example_exists(self):
        assert STAGING_ENV.exists(), ".env.staging.example not found"

    def test_staging_script_exists(self):
        path = Path(__file__).parent.parent.parent / "scripts" / "staging.sh"
        assert path.exists(), "scripts/staging.sh not found"

    def test_staging_script_is_executable(self):
        path = Path(__file__).parent.parent.parent / "scripts" / "staging.sh"
        import os
        assert os.access(path, os.X_OK), "staging.sh should be executable"


class TestStagingMirrorsProduction:
    """Staging should mirror all production services."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.staging = _load_compose(STAGING_COMPOSE)
        self.prod = _load_compose(PROD_COMPOSE)

    def test_staging_is_valid_compose(self):
        """Staging compose should be a valid Docker Compose file."""
        assert "services" in self.staging
        assert isinstance(self.staging["services"], dict)

    def test_has_all_production_services(self):
        """Staging should contain every service from production."""
        prod_services = set(self.prod.get("services", {}).keys())
        staging_services = set(self.staging.get("services", {}).keys())

        missing = prod_services - staging_services
        assert not missing, (
            f"Staging is missing production services: {missing}"
        )

    def test_has_postgres(self):
        assert "postgres" in self.staging["services"]

    def test_has_redis(self):
        assert "redis" in self.staging["services"]

    def test_has_gateway(self):
        assert "gateway" in self.staging["services"]

    def test_has_langgraph(self):
        assert "langgraph" in self.staging["services"]

    def test_has_worker(self):
        assert "worker" in self.staging["services"]

    def test_has_nginx(self):
        assert "nginx" in self.staging["services"]

    def test_has_backup(self):
        assert "backup" in self.staging["services"]


class TestStagingSpecificSettings:
    """Staging should have development-friendly settings."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.staging = _load_compose(STAGING_COMPOSE)

    def test_has_minio_service(self):
        """Staging should include MinIO for S3-compatible storage testing."""
        assert "minio" in self.staging["services"]

    def test_postgres_port_exposed(self):
        """Staging should expose PostgreSQL port for debugging."""
        pg = self.staging["services"]["postgres"]
        ports = pg.get("ports", [])
        assert len(ports) > 0, "PostgreSQL port should be exposed in staging"

    def test_redis_port_exposed(self):
        """Staging should expose Redis port for debugging."""
        redis = self.staging["services"]["redis"]
        ports = redis.get("ports", [])
        assert len(ports) > 0, "Redis port should be exposed in staging"

    def test_single_replicas(self):
        """Staging should use single replicas to save resources."""
        for service_name in ["gateway", "langgraph", "worker"]:
            service = self.staging["services"].get(service_name, {})
            deploy = service.get("deploy", {})
            replicas = deploy.get("replicas", 1)
            assert replicas == 1, (
                f"Staging service '{service_name}' should have 1 replica, got {replicas}"
            )

    def test_containers_have_staging_prefix(self):
        """Staging containers should be named with 'staging' prefix."""
        for name, service in self.staging["services"].items():
            container_name = service.get("container_name", "")
            if container_name:
                assert "staging" in container_name, (
                    f"Container '{container_name}' should include 'staging' in name"
                )

    def test_uses_unless_stopped_restart(self):
        """Staging should use 'unless-stopped' restart (not 'always')."""
        for name, service in self.staging["services"].items():
            restart = service.get("restart", "")
            if restart:
                assert restart == "unless-stopped", (
                    f"Staging service '{name}' should use 'unless-stopped', not '{restart}'"
                )

    def test_volumes_have_staging_prefix(self):
        """Staging volumes should be prefixed to avoid conflicts with production."""
        volumes = self.staging.get("volumes", {})
        for vol_name in volumes:
            assert "staging" in vol_name, (
                f"Volume '{vol_name}' should include 'staging' prefix"
            )

    def test_uses_separate_network(self):
        """Staging should use a separate Docker network from production."""
        networks = self.staging.get("networks", {})
        assert len(networks) > 0
        network_names = list(networks.keys())
        assert any("staging" in n for n in network_names), (
            "Staging should use a network with 'staging' in its name"
        )


class TestStagingEnvExample:
    """Validate the staging .env.example file."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.content = STAGING_ENV.read_text()

    def test_has_db_password(self):
        assert "DB_PASSWORD" in self.content

    def test_has_jwt_secret(self):
        assert "JWT_SECRET_KEY" in self.content

    def test_has_log_level(self):
        assert "LOG_LEVEL" in self.content

    def test_default_log_level_is_debug(self):
        """Staging should default to DEBUG logging."""
        assert "LOG_LEVEL=DEBUG" in self.content

    def test_has_minio_credentials(self):
        assert "MINIO_ROOT_USER" in self.content
        assert "MINIO_ROOT_PASSWORD" in self.content

    def test_has_port_configuration(self):
        """Staging should have configurable port offsets."""
        assert "NGINX_HTTP_PORT" in self.content

    def test_no_real_secrets(self):
        """Example file should not contain real secrets."""
        # Check for common patterns that indicate real secrets
        lines = self.content.split("\n")
        for line in lines:
            if "=" in line and not line.strip().startswith("#"):
                key, _, value = line.partition("=")
                # Values should be clearly placeholder/staging defaults
                if key.strip() in ("JWT_SECRET_KEY", "ENCRYPTION_KEY"):
                    assert "staging" in value.lower() or "not-for-prod" in value.lower() or len(value.strip()) < 50, (
                        f"Env var {key.strip()} may contain a real secret"
                    )


class TestStagingScript:
    """Validate the staging management script."""

    @pytest.fixture(autouse=True)
    def setup(self):
        path = Path(__file__).parent.parent.parent / "scripts" / "staging.sh"
        self.script = path.read_text()

    def test_has_start_command(self):
        assert "cmd_start" in self.script

    def test_has_stop_command(self):
        assert "cmd_stop" in self.script

    def test_has_health_command(self):
        assert "cmd_health" in self.script

    def test_has_test_command(self):
        assert "cmd_test" in self.script

    def test_has_seed_command(self):
        """Staging should support test data seeding."""
        assert "cmd_seed" in self.script or "seed" in self.script

    def test_has_reset_command(self):
        """Staging should support full reset."""
        assert "cmd_reset" in self.script or "reset" in self.script

    def test_references_staging_compose(self):
        """Script should use the staging compose file."""
        assert "docker-compose-staging.yaml" in self.script
