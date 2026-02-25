"""Tests for Gunicorn production configuration."""

import importlib.util
import os
from pathlib import Path
from unittest.mock import patch

GUNICORN_CONF_PATH = Path(__file__).parent.parent / "gunicorn.conf.py"


class TestGunicornConfig:
    """Tests for gunicorn.conf.py."""

    def _load_config(self, env_overrides: dict | None = None):
        """Load gunicorn.conf.py as a module with optional env overrides."""
        env = env_overrides or {}
        with patch.dict(os.environ, env, clear=False):
            spec = importlib.util.spec_from_file_location("gunicorn_conf", GUNICORN_CONF_PATH)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

    def test_config_is_valid_python(self):
        """gunicorn.conf.py should be importable without errors."""
        config = self._load_config()
        assert hasattr(config, "bind")
        assert hasattr(config, "workers")
        assert hasattr(config, "worker_class")

    def test_default_worker_class(self):
        """Default worker class should be UvicornWorker."""
        config = self._load_config()
        assert config.worker_class == "uvicorn.workers.UvicornWorker"

    def test_default_bind(self):
        """Default bind should be 0.0.0.0:8001."""
        config = self._load_config()
        assert config.bind == "0.0.0.0:8001"

    def test_default_workers_bounded(self):
        """Default worker count should be bounded (1-9)."""
        config = self._load_config()
        assert 1 <= config.workers <= 9

    def test_gateway_workers_env_override(self):
        """GATEWAY_WORKERS env var should override default worker count."""
        config = self._load_config({"GATEWAY_WORKERS": "3"})
        assert config.workers == 3

    def test_custom_bind_via_env(self):
        """GUNICORN_BIND env var should override default bind."""
        config = self._load_config({"GUNICORN_BIND": "127.0.0.1:9000"})
        assert config.bind == "127.0.0.1:9000"

    def test_custom_timeout_via_env(self):
        """GUNICORN_TIMEOUT env var should override default timeout."""
        config = self._load_config({"GUNICORN_TIMEOUT": "300"})
        assert config.timeout == 300

    def test_default_timeout(self):
        """Default timeout should be 120 seconds."""
        config = self._load_config()
        assert config.timeout == 120

    def test_preload_app_enabled(self):
        """preload_app should be True for copy-on-write benefits."""
        config = self._load_config()
        assert config.preload_app is True
