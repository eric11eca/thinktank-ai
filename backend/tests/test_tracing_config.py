"""Tests for LangSmith tracing configuration."""

import os
from unittest.mock import patch

import pytest


# Reset the cached config before each test
@pytest.fixture(autouse=True)
def reset_tracing_config():
    """Reset the tracing config singleton between tests."""
    import src.config.tracing_config as mod

    mod._tracing_config = None
    yield
    mod._tracing_config = None


class TestTracingConfig:
    """Tests for get_tracing_config()."""

    def test_enabled_with_langsmith_vars(self):
        """Tracing is enabled when LANGSMITH_TRACING=true and API key set."""
        env = {
            "LANGSMITH_TRACING": "true",
            "LANGSMITH_API_KEY": "lsv2_test_key",
            "LANGSMITH_PROJECT": "my-project",
        }
        with patch.dict(os.environ, env, clear=False):
            from src.config.tracing_config import get_tracing_config

            config = get_tracing_config()
            assert config.enabled is True
            assert config.api_key == "lsv2_test_key"
            assert config.project == "my-project"
            assert config.is_configured is True

    def test_enabled_with_langchain_vars(self):
        """Tracing is enabled when LANGCHAIN_TRACING_V2=true and API key set."""
        env = {
            "LANGCHAIN_TRACING_V2": "true",
            "LANGCHAIN_API_KEY": "lsv2_chain_key",
            "LANGCHAIN_PROJECT": "chain-project",
        }
        # Clear LANGSMITH_ vars to test LANGCHAIN_ fallback
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("LANGSMITH_TRACING", None)
            os.environ.pop("LANGSMITH_API_KEY", None)
            os.environ.pop("LANGSMITH_PROJECT", None)
            os.environ.pop("LANGSMITH_ENDPOINT", None)

            from src.config.tracing_config import get_tracing_config

            config = get_tracing_config()
            assert config.enabled is True
            assert config.api_key == "lsv2_chain_key"
            assert config.project == "chain-project"
            assert config.is_configured is True

    def test_disabled_without_api_key(self):
        """Tracing is not configured without an API key."""
        env = {"LANGSMITH_TRACING": "true"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("LANGSMITH_API_KEY", None)
            os.environ.pop("LANGCHAIN_API_KEY", None)

            from src.config.tracing_config import get_tracing_config

            config = get_tracing_config()
            assert config.enabled is True
            assert config.api_key is None
            assert config.is_configured is False

    def test_disabled_by_default(self):
        """Tracing is disabled when env vars are not set."""
        with patch.dict(os.environ, {}, clear=False):
            for key in ["LANGSMITH_TRACING", "LANGSMITH_API_KEY", "LANGSMITH_PROJECT", "LANGSMITH_ENDPOINT", "LANGCHAIN_TRACING_V2", "LANGCHAIN_API_KEY", "LANGCHAIN_PROJECT", "LANGCHAIN_ENDPOINT"]:
                os.environ.pop(key, None)

            from src.config.tracing_config import get_tracing_config

            config = get_tracing_config()
            assert config.enabled is False
            assert config.is_configured is False

    def test_project_name_fallback(self):
        """Project defaults to 'deer-flow' when not set."""
        with patch.dict(os.environ, {"LANGSMITH_TRACING": "true"}, clear=False):
            os.environ.pop("LANGSMITH_PROJECT", None)
            os.environ.pop("LANGCHAIN_PROJECT", None)

            from src.config.tracing_config import get_tracing_config

            config = get_tracing_config()
            assert config.project == "deer-flow"

    def test_langsmith_takes_precedence(self):
        """LANGSMITH_* vars take precedence over LANGCHAIN_* vars."""
        env = {
            "LANGSMITH_TRACING": "true",
            "LANGSMITH_API_KEY": "langsmith_key",
            "LANGSMITH_PROJECT": "smith-project",
            "LANGCHAIN_TRACING_V2": "false",
            "LANGCHAIN_API_KEY": "chain_key",
            "LANGCHAIN_PROJECT": "chain-project",
        }
        with patch.dict(os.environ, env, clear=False):
            from src.config.tracing_config import get_tracing_config

            config = get_tracing_config()
            assert config.api_key == "langsmith_key"
            assert config.project == "smith-project"
