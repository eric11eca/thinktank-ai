import logging
import os
import threading

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
_config_lock = threading.Lock()


class TracingConfig(BaseModel):
    """Configuration for LangSmith tracing."""

    enabled: bool = Field(...)
    api_key: str | None = Field(...)
    project: str = Field(...)
    endpoint: str = Field(...)

    @property
    def is_configured(self) -> bool:
        """Check if tracing is fully configured (enabled and has API key)."""
        return self.enabled and bool(self.api_key)


_tracing_config: TracingConfig | None = None


def get_tracing_config() -> TracingConfig:
    """Get the current tracing configuration from environment variables.

    Supports both ``LANGSMITH_*`` and ``LANGCHAIN_*`` env var prefixes.
    ``LANGSMITH_*`` takes precedence when both are set.

    Returns:
        TracingConfig with current settings.
    """
    global _tracing_config
    if _tracing_config is not None:
        return _tracing_config
    with _config_lock:
        if _tracing_config is not None:  # Double-check after acquiring lock
            return _tracing_config

        # Support both LANGSMITH_* and LANGCHAIN_* env var names
        enabled_str = os.environ.get("LANGSMITH_TRACING") or os.environ.get("LANGCHAIN_TRACING_V2") or ""
        api_key = os.environ.get("LANGSMITH_API_KEY") or os.environ.get("LANGCHAIN_API_KEY")
        project = os.environ.get("LANGSMITH_PROJECT") or os.environ.get("LANGCHAIN_PROJECT") or "deer-flow"
        endpoint = os.environ.get("LANGSMITH_ENDPOINT") or os.environ.get("LANGCHAIN_ENDPOINT") or "https://api.smith.langchain.com"

        _tracing_config = TracingConfig(
            enabled=enabled_str.lower() == "true",
            api_key=api_key,
            project=project,
            endpoint=endpoint,
        )
        return _tracing_config


def is_tracing_enabled() -> bool:
    """Check if LangSmith tracing is enabled and configured.
    Returns:
        True if tracing is enabled and has an API key.
    """
    return get_tracing_config().is_configured
