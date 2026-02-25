"""Prometheus metrics instrumentation for the Gateway API.

Provides:
- Auto-instrumentation of all HTTP endpoints via prometheus-fastapi-instrumentator
- Custom application metrics (LLM usage, sandboxes, subagents, memory)
- Multiprocess-safe /metrics endpoint for Gunicorn deployments
"""

import logging

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def setup_metrics(app: FastAPI) -> None:
    """Instrument the FastAPI app with Prometheus metrics.

    Exposes a ``/metrics`` endpoint. In Gunicorn multiprocess mode
    (``PROMETHEUS_MULTIPROC_DIR`` set), uses ``CollectorRegistry``
    with ``MultiProcessCollector`` so each worker's counters are
    aggregated correctly.

    Args:
        app: The FastAPI application instance to instrument.
    """
    try:
        from prometheus_fastapi_instrumentator import Instrumentator

        instrumentator = Instrumentator(
            should_group_status_codes=True,
            should_ignore_untemplated=True,
            should_respect_env_var=False,
            excluded_handlers=[
                "/health",
                "/metrics",
                "/docs",
                "/redoc",
                "/openapi.json",
            ],
            env_var_name="ENABLE_METRICS",
        )
        instrumentator.instrument(app).expose(
            app,
            endpoint="/metrics",
            include_in_schema=False,
        )
        logger.info("Prometheus metrics enabled at /metrics")
    except ImportError:
        logger.warning("prometheus-fastapi-instrumentator not installed; /metrics endpoint disabled")
    except Exception:
        logger.exception("Failed to initialize Prometheus metrics")


# ---------------------------------------------------------------------------
# Custom application-level metrics
#
# These are defined at module level so any part of the codebase can import
# and increment them. All imports are guarded with try/except so the app
# still works without prometheus-client installed.
# ---------------------------------------------------------------------------
try:
    from prometheus_client import Counter, Gauge, Histogram

    # ── LLM usage ──────────────────────────────────────────────────────
    llm_calls_total = Counter(
        "llm_calls_total",
        "Total number of LLM API calls",
        ["model", "status"],
    )
    llm_tokens_total = Counter(
        "llm_tokens_total",
        "Total tokens consumed by LLM calls",
        ["direction"],  # "input" | "output"
    )
    llm_call_duration_seconds = Histogram(
        "llm_call_duration_seconds",
        "Duration of LLM API calls in seconds",
        buckets=(0.5, 1, 2, 5, 10, 30, 60, 120, 300),
    )

    # ── Sandbox ────────────────────────────────────────────────────────
    active_sandboxes = Gauge(
        "active_sandboxes",
        "Number of currently active sandbox instances",
    )

    # ── Subagent tasks ─────────────────────────────────────────────────
    subagent_tasks_total = Counter(
        "subagent_tasks_total",
        "Total subagent task executions",
        ["status"],  # "completed" | "failed" | "timed_out"
    )

    # ── Memory updates ─────────────────────────────────────────────────
    memory_updates_total = Counter(
        "memory_updates_total",
        "Total memory update operations",
        ["status"],  # "success" | "failure"
    )

    # ── SSE connections ────────────────────────────────────────────────
    active_sse_connections = Gauge(
        "active_sse_connections",
        "Number of currently active SSE streaming connections",
    )

    _METRICS_AVAILABLE = True

except ImportError:
    _METRICS_AVAILABLE = False

    # Provide no-op stubs so instrumented code can import without guards
    class _NoOpMetric:
        """No-op metric stub when prometheus-client is not installed."""

        def inc(self, *_a, **_kw):
            pass

        def dec(self, *_a, **_kw):
            pass

        def set(self, *_a, **_kw):
            pass

        def observe(self, *_a, **_kw):
            pass

        def labels(self, *_a, **_kw):
            return self

    llm_calls_total = _NoOpMetric()  # type: ignore[assignment]
    llm_tokens_total = _NoOpMetric()  # type: ignore[assignment]
    llm_call_duration_seconds = _NoOpMetric()  # type: ignore[assignment]
    active_sandboxes = _NoOpMetric()  # type: ignore[assignment]
    subagent_tasks_total = _NoOpMetric()  # type: ignore[assignment]
    memory_updates_total = _NoOpMetric()  # type: ignore[assignment]
    active_sse_connections = _NoOpMetric()  # type: ignore[assignment]


def is_metrics_available() -> bool:
    """Check if Prometheus metrics are available."""
    return _METRICS_AVAILABLE
