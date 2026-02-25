"""Tests for Prometheus alerting rules configuration."""

from pathlib import Path

import pytest
import yaml


ALERTS_FILE = Path(__file__).parent.parent.parent / "docker" / "monitoring" / "alerts.yml"

EXPECTED_ALERTS = [
    "HighErrorRate",
    "HighLatencyP99",
    "DatabaseConnectionFailure",
    "LLMAPIErrors",
    "HighMemoryUsage",
    "TooManySSEConnections",
]

VALID_SEVERITIES = {"critical", "warning", "info"}


@pytest.fixture()
def alerts_config():
    """Load and parse the alerts YAML file."""
    assert ALERTS_FILE.exists(), f"Alerts file not found: {ALERTS_FILE}"
    content = ALERTS_FILE.read_text(encoding="utf-8")
    return yaml.safe_load(content)


class TestAlertingRules:
    """Tests for alerts.yml validity."""

    def test_yaml_is_valid(self, alerts_config):
        """alerts.yml is valid YAML."""
        assert alerts_config is not None
        assert "groups" in alerts_config

    def test_all_expected_alerts_defined(self, alerts_config):
        """All expected alerts are defined."""
        all_alert_names = set()
        for group in alerts_config["groups"]:
            for rule in group.get("rules", []):
                all_alert_names.add(rule["alert"])

        for expected in EXPECTED_ALERTS:
            assert expected in all_alert_names, f"Missing alert: {expected}"

    def test_severities_are_valid(self, alerts_config):
        """All alert severities are valid values."""
        for group in alerts_config["groups"]:
            for rule in group.get("rules", []):
                severity = rule.get("labels", {}).get("severity")
                assert severity in VALID_SEVERITIES, (
                    f"Alert {rule['alert']} has invalid severity: {severity}"
                )

    def test_alerts_have_annotations(self, alerts_config):
        """All alerts have summary and description annotations."""
        for group in alerts_config["groups"]:
            for rule in group.get("rules", []):
                annotations = rule.get("annotations", {})
                assert "summary" in annotations, (
                    f"Alert {rule['alert']} missing 'summary' annotation"
                )
                assert "description" in annotations, (
                    f"Alert {rule['alert']} missing 'description' annotation"
                )

    def test_alerts_have_expr(self, alerts_config):
        """All alerts have a PromQL expression."""
        for group in alerts_config["groups"]:
            for rule in group.get("rules", []):
                assert "expr" in rule and rule["expr"].strip(), (
                    f"Alert {rule['alert']} missing 'expr'"
                )
