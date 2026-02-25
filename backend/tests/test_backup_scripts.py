"""Tests for database backup infrastructure.

Validates the backup/restore scripts, Dockerfile, and configuration.
"""

from pathlib import Path

import pytest


BACKUP_DIR = Path(__file__).parent.parent.parent / "docker" / "backup"
COMPOSE_PROD = Path(__file__).parent.parent.parent / "docker" / "docker-compose-prod.yaml"


class TestBackupScriptExists:
    """Verify backup infrastructure files exist and are properly structured."""

    def test_backup_script_exists(self):
        path = BACKUP_DIR / "backup.sh"
        assert path.exists(), "backup.sh not found"
        assert path.stat().st_size > 0, "backup.sh is empty"

    def test_restore_script_exists(self):
        path = BACKUP_DIR / "restore.sh"
        assert path.exists(), "restore.sh not found"
        assert path.stat().st_size > 0, "restore.sh is empty"

    def test_dockerfile_exists(self):
        path = BACKUP_DIR / "Dockerfile"
        assert path.exists(), "Backup Dockerfile not found"
        assert path.stat().st_size > 0, "Backup Dockerfile is empty"

    def test_entrypoint_exists(self):
        path = BACKUP_DIR / "entrypoint.sh"
        assert path.exists(), "entrypoint.sh not found"

    def test_wal_config_exists(self):
        path = BACKUP_DIR / "postgresql-backup.conf"
        assert path.exists(), "postgresql-backup.conf not found"


class TestBackupScriptContent:
    """Validate backup.sh script content and logic."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.script = (BACKUP_DIR / "backup.sh").read_text()

    def test_uses_bash_strict_mode(self):
        """Script should use strict error handling."""
        assert "set -euo pipefail" in self.script

    def test_has_pg_dump_command(self):
        """Script should use pg_dump for backups."""
        assert "pg_dump" in self.script

    def test_uses_gzip_compression(self):
        """Backups should be compressed with gzip."""
        assert "gzip" in self.script

    def test_supports_s3_upload(self):
        """Script should support S3 upload (aws s3 cp)."""
        assert "aws s3 cp" in self.script

    def test_has_verification_step(self):
        """Script should verify backup integrity."""
        assert "verify_backup" in self.script or "gzip -t" in self.script

    def test_implements_retention_policy(self):
        """Script should implement backup retention (daily, weekly, monthly)."""
        assert "RETENTION_DAILY" in self.script
        assert "RETENTION_WEEKLY" in self.script
        assert "RETENTION_MONTHLY" in self.script

    def test_creates_daily_backups(self):
        """Script should always create daily backups."""
        assert "daily" in self.script

    def test_creates_weekly_backups_on_sunday(self):
        """Script should create weekly backups on Sundays."""
        assert "weekly" in self.script
        # Day 7 = Sunday in ISO format
        assert "7" in self.script

    def test_creates_monthly_backups_on_first(self):
        """Script should create monthly backups on the 1st."""
        assert "monthly" in self.script
        assert "01" in self.script

    def test_default_retention_values(self):
        """Default retention should be 7 daily, 4 weekly, 3 monthly."""
        assert "RETENTION_DAILY:-7" in self.script or 'RETENTION_DAILY="${RETENTION_DAILY:-7}"' in self.script
        assert "RETENTION_WEEKLY:-4" in self.script or 'RETENTION_WEEKLY="${RETENTION_WEEKLY:-4}"' in self.script
        assert "RETENTION_MONTHLY:-3" in self.script or 'RETENTION_MONTHLY="${RETENTION_MONTHLY:-3}"' in self.script

    def test_checks_pg_isready(self):
        """Script should verify PostgreSQL is reachable before backup."""
        assert "pg_isready" in self.script

    def test_supports_s3_endpoint_url(self):
        """Script should support custom S3 endpoint (for MinIO)."""
        assert "S3_ENDPOINT_URL" in self.script


class TestRestoreScriptContent:
    """Validate restore.sh script content."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.script = (BACKUP_DIR / "restore.sh").read_text()

    def test_uses_bash_strict_mode(self):
        assert "set -euo pipefail" in self.script

    def test_supports_local_file_restore(self):
        """Should accept a local backup file path."""
        assert "restore_database" in self.script

    def test_supports_latest_option(self):
        """Should support --latest to restore most recent backup."""
        assert "--latest" in self.script

    def test_supports_s3_download(self):
        """Should support --from-s3 to download and restore from S3."""
        assert "--from-s3" in self.script

    def test_supports_list_command(self):
        """Should support --list to show available backups."""
        assert "--list" in self.script

    def test_creates_safety_backup(self):
        """Should create a safety backup before restoring."""
        assert "safety" in self.script.lower() or "pre_restore" in self.script

    def test_has_confirmation_prompt(self):
        """Should prompt for confirmation before destructive restore."""
        assert "confirm" in self.script.lower() or "Are you sure" in self.script

    def test_verifies_gzip_integrity(self):
        """Should verify gzip integrity before restoring."""
        assert "gzip -t" in self.script


class TestBackupDockerfile:
    """Validate the backup Dockerfile."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.dockerfile = (BACKUP_DIR / "Dockerfile").read_text()

    def test_based_on_postgres_alpine(self):
        """Should be based on postgres:16-alpine (includes pg_dump)."""
        assert "postgres:16-alpine" in self.dockerfile

    def test_installs_aws_cli(self):
        """Should install aws-cli for S3 uploads."""
        assert "aws-cli" in self.dockerfile

    def test_copies_backup_scripts(self):
        """Should copy backup.sh and restore.sh."""
        assert "backup.sh" in self.dockerfile
        assert "restore.sh" in self.dockerfile

    def test_creates_backup_dir(self):
        """Should create /backups directory."""
        assert "/backups" in self.dockerfile

    def test_has_volume_for_backups(self):
        """Should declare /backups as a volume."""
        assert "VOLUME" in self.dockerfile

    def test_runs_as_non_root(self):
        """Should run as postgres user, not root."""
        assert "USER postgres" in self.dockerfile


class TestBackupInProductionCompose:
    """Validate backup service in docker-compose-prod.yaml."""

    @pytest.fixture(autouse=True)
    def setup(self):
        import yaml
        with open(COMPOSE_PROD) as f:
            self.compose = yaml.safe_load(f)

    def test_backup_service_exists(self):
        """Production compose should include a backup service."""
        services = self.compose.get("services", {})
        assert "backup" in services, "Missing 'backup' service in production compose"

    def test_backup_depends_on_postgres(self):
        """Backup service should depend on PostgreSQL being healthy."""
        backup = self.compose["services"]["backup"]
        depends = backup.get("depends_on", {})
        assert "postgres" in depends

    def test_backup_has_volume(self):
        """Backup service should have a persistent volume."""
        backup = self.compose["services"]["backup"]
        volumes = backup.get("volumes", [])
        assert len(volumes) > 0, "Backup service should have at least one volume"

    def test_backup_has_resource_limits(self):
        """Backup service should have resource limits."""
        backup = self.compose["services"]["backup"]
        deploy = backup.get("deploy", {})
        resources = deploy.get("resources", {})
        assert "limits" in resources

    def test_backupdata_volume_declared(self):
        """The backupdata volume should be declared at top level."""
        volumes = self.compose.get("volumes", {})
        assert "backupdata" in volumes


class TestWALConfig:
    """Validate WAL archiving configuration."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.config = (BACKUP_DIR / "postgresql-backup.conf").read_text()

    def test_wal_level_replica(self):
        """WAL level should be set to replica for archiving."""
        assert "wal_level = replica" in self.config

    def test_archive_mode_on(self):
        """Archive mode should be enabled."""
        assert "archive_mode = on" in self.config

    def test_has_archive_command(self):
        """Should define an archive_command."""
        assert "archive_command" in self.config
