"""Tests for the health check endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    """Create a test client for the gateway app."""
    # Patch external dependencies before importing app
    with (
        patch("src.db.engine.is_db_enabled", return_value=False),
        patch("src.queue.redis_connection.is_redis_available", return_value=False),
    ):
        from src.gateway.app import create_app

        app = create_app()
        yield TestClient(app)


class TestHealthCheck:
    """Tests for the /health endpoint."""

    def test_basic_health_check(self, client):
        """Health check returns 200 with expected structure."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            response = client.get("/health")
            assert response.status_code == 200
            body = response.json()
            assert body["service"] == "deer-flow-gateway"
            assert "status" in body
            assert "checks" in body
            assert "gateway" in body["checks"]

    def test_health_includes_langgraph_check(self, client):
        """Health response includes langgraph check."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            response = client.get("/health")
            body = response.json()
            assert "langgraph" in body["checks"]

    def test_langgraph_healthy(self, client):
        """When LangGraph responds 200, check is healthy."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            response = client.get("/health")
            body = response.json()
            assert body["checks"]["langgraph"] == "healthy"

    def test_langgraph_unreachable_degraded(self, client):
        """When LangGraph is unreachable, status is degraded."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = ConnectionError("refused")

            response = client.get("/health")
            body = response.json()
            assert body["status"] == "degraded"
            assert "unhealthy" in body["checks"]["langgraph"]

    def test_overall_healthy_when_all_checks_pass(self, client):
        """Overall status is healthy when all checks pass."""
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            response = client.get("/health")
            body = response.json()
            assert body["status"] == "healthy"
