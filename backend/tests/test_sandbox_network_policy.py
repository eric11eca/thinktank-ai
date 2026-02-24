"""Tests for the sandbox NetworkPolicy configuration.

Verifies that the provisioner creates a NetworkPolicy that:
- Targets sandbox pods (app: deer-flow-sandbox)
- Allows ingress only on port 8080
- Allows DNS egress (port 53)
- Allows external HTTP/HTTPS egress
- Blocks access to internal cluster CIDRs
"""

import importlib.util
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Load provisioner app.py directly by file path to avoid conflict with the
# 'docker' pip package (the provisioner lives in <repo>/docker/provisioner/).
_provisioner_app_path = os.path.join(
    os.path.dirname(__file__), "..", "..", "docker", "provisioner", "app.py"
)
_spec = importlib.util.spec_from_file_location("provisioner_app_np", _provisioner_app_path)
provisioner_app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(provisioner_app)

# Register in sys.modules so patch() can find it
sys.modules["provisioner_app_np"] = provisioner_app

_ensure_network_policy = provisioner_app._ensure_network_policy


@pytest.fixture
def mock_networking_v1():
    """Mock the networking_v1 K8s API client."""
    mock = MagicMock()
    return mock


class TestNetworkPolicyStructure:
    """Tests for the NetworkPolicy object structure."""

    def test_policy_created_on_404(self, mock_networking_v1):
        """NetworkPolicy is created when it doesn't exist."""
        from kubernetes.client.rest import ApiException

        mock_networking_v1.read_namespaced_network_policy.side_effect = ApiException(status=404)

        with patch.object(provisioner_app, "networking_v1", mock_networking_v1):
            with patch.object(provisioner_app, "K8S_NAMESPACE", "test-ns"):
                _ensure_network_policy()

        mock_networking_v1.create_namespaced_network_policy.assert_called_once()
        args = mock_networking_v1.create_namespaced_network_policy.call_args
        assert args[0][0] == "test-ns"
        policy = args[0][1]

        # Verify basic structure
        assert policy.metadata.name == "sandbox-isolation"
        assert policy.metadata.namespace == "test-ns"

    def test_policy_updated_when_exists(self, mock_networking_v1):
        """NetworkPolicy is replaced when it already exists."""
        mock_networking_v1.read_namespaced_network_policy.return_value = MagicMock()

        with patch.object(provisioner_app, "networking_v1", mock_networking_v1):
            with patch.object(provisioner_app, "K8S_NAMESPACE", "test-ns"):
                _ensure_network_policy()

        mock_networking_v1.replace_namespaced_network_policy.assert_called_once()

    def test_policy_targets_sandbox_pods(self, mock_networking_v1):
        """Policy pod selector matches deer-flow-sandbox pods."""
        from kubernetes.client.rest import ApiException

        mock_networking_v1.read_namespaced_network_policy.side_effect = ApiException(status=404)

        with patch.object(provisioner_app, "networking_v1", mock_networking_v1):
            with patch.object(provisioner_app, "K8S_NAMESPACE", "test-ns"):
                _ensure_network_policy()

        policy = mock_networking_v1.create_namespaced_network_policy.call_args[0][1]
        selector = policy.spec.pod_selector
        assert selector.match_labels == {"app": "deer-flow-sandbox"}

    def test_policy_types_include_ingress_and_egress(self, mock_networking_v1):
        """Policy enforces both ingress and egress."""
        from kubernetes.client.rest import ApiException

        mock_networking_v1.read_namespaced_network_policy.side_effect = ApiException(status=404)

        with patch.object(provisioner_app, "networking_v1", mock_networking_v1):
            with patch.object(provisioner_app, "K8S_NAMESPACE", "test-ns"):
                _ensure_network_policy()

        policy = mock_networking_v1.create_namespaced_network_policy.call_args[0][1]
        assert "Ingress" in policy.spec.policy_types
        assert "Egress" in policy.spec.policy_types


class TestNetworkPolicyIngress:
    """Tests for ingress rules."""

    def test_ingress_allows_port_8080(self, mock_networking_v1):
        """Ingress allows connections on port 8080."""
        from kubernetes.client.rest import ApiException

        mock_networking_v1.read_namespaced_network_policy.side_effect = ApiException(status=404)

        with patch.object(provisioner_app, "networking_v1", mock_networking_v1):
            with patch.object(provisioner_app, "K8S_NAMESPACE", "test-ns"):
                _ensure_network_policy()

        policy = mock_networking_v1.create_namespaced_network_policy.call_args[0][1]
        ingress_rules = policy.spec.ingress
        assert len(ingress_rules) >= 1

        # Check that port 8080 is allowed
        ports = ingress_rules[0].ports
        port_numbers = [p.port for p in ports]
        assert 8080 in port_numbers


class TestNetworkPolicyEgress:
    """Tests for egress rules."""

    def test_egress_allows_dns(self, mock_networking_v1):
        """Egress allows DNS queries (port 53 UDP and TCP)."""
        from kubernetes.client.rest import ApiException

        mock_networking_v1.read_namespaced_network_policy.side_effect = ApiException(status=404)

        with patch.object(provisioner_app, "networking_v1", mock_networking_v1):
            with patch.object(provisioner_app, "K8S_NAMESPACE", "test-ns"):
                _ensure_network_policy()

        policy = mock_networking_v1.create_namespaced_network_policy.call_args[0][1]
        egress_rules = policy.spec.egress

        # Find the DNS rule (has port 53)
        dns_rule = None
        for rule in egress_rules:
            if rule.ports:
                for port in rule.ports:
                    if port.port == 53:
                        dns_rule = rule
                        break

        assert dns_rule is not None, "No DNS egress rule found"
        dns_protocols = {p.protocol for p in dns_rule.ports if p.port == 53}
        assert "UDP" in dns_protocols
        assert "TCP" in dns_protocols

    def test_egress_allows_external_http_https(self, mock_networking_v1):
        """Egress allows external HTTP (80) and HTTPS (443)."""
        from kubernetes.client.rest import ApiException

        mock_networking_v1.read_namespaced_network_policy.side_effect = ApiException(status=404)

        with patch.object(provisioner_app, "networking_v1", mock_networking_v1):
            with patch.object(provisioner_app, "K8S_NAMESPACE", "test-ns"):
                _ensure_network_policy()

        policy = mock_networking_v1.create_namespaced_network_policy.call_args[0][1]
        egress_rules = policy.spec.egress

        # Find the HTTP/HTTPS rule
        http_rule = None
        for rule in egress_rules:
            if rule.ports and rule.to:
                port_numbers = {p.port for p in rule.ports}
                if 80 in port_numbers or 443 in port_numbers:
                    http_rule = rule
                    break

        assert http_rule is not None, "No HTTP/HTTPS egress rule found"
        port_numbers = {p.port for p in http_rule.ports}
        assert 80 in port_numbers
        assert 443 in port_numbers

    def test_egress_blocks_internal_cidrs(self, mock_networking_v1):
        """Egress to external internet blocks internal CIDRs."""
        from kubernetes.client.rest import ApiException

        mock_networking_v1.read_namespaced_network_policy.side_effect = ApiException(status=404)

        with patch.object(provisioner_app, "networking_v1", mock_networking_v1):
            with patch.object(provisioner_app, "K8S_NAMESPACE", "test-ns"):
                with patch.object(provisioner_app, "INTERNAL_CIDRS", ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]):
                    _ensure_network_policy()

        policy = mock_networking_v1.create_namespaced_network_policy.call_args[0][1]
        egress_rules = policy.spec.egress

        # Find the rule with IP block exceptions
        ip_block_rule = None
        for rule in egress_rules:
            if rule.to:
                for peer in rule.to:
                    if peer.ip_block and peer.ip_block._except:
                        ip_block_rule = rule
                        break

        assert ip_block_rule is not None, "No egress rule with internal CIDR exceptions"
        excluded = ip_block_rule.to[0].ip_block._except
        assert "10.0.0.0/8" in excluded
        assert "172.16.0.0/12" in excluded
        assert "192.168.0.0/16" in excluded
