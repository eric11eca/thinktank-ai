"""Gunicorn production configuration for the Gateway API.

Environment variables:
    GATEWAY_WORKERS: Number of worker processes (default: min(cpu_count * 2 + 1, 9))
    GUNICORN_BIND: Bind address (default: 0.0.0.0:8001)
    GUNICORN_TIMEOUT: Worker timeout in seconds (default: 120)
    GUNICORN_LOG_LEVEL: Log level (default: info)
"""

import multiprocessing
import os

# Server socket
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8001")

# Worker processes
# Default: 2 * CPU cores + 1, capped at 9 to avoid excessive memory usage
workers = int(os.environ.get(
    "GATEWAY_WORKERS",
    min(multiprocessing.cpu_count() * 2 + 1, 9),
))

# Use UvicornWorker for ASGI compatibility with FastAPI
worker_class = "uvicorn.workers.UvicornWorker"

# Timeouts
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 120))
graceful_timeout = 30
keepalive = 5

# Logging
accesslog = "-"  # stdout
errorlog = "-"   # stderr
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")

# Process naming
proc_name = "deer-flow-gateway"

# Preload app for shared memory between workers (copy-on-write after fork).
# Safe because database connections are lazily initialized.
preload_app = True

# Worker tmp dir on tmpfs for better heartbeat performance
worker_tmp_dir = "/dev/shm"


# ── Prometheus multiprocess cleanup ────────────────────────────────────
# When PROMETHEUS_MULTIPROC_DIR is set, each worker writes to its own
# metrics DB file. This hook removes the file when a worker exits so
# stale gauges don't persist.
def child_exit(server, worker):  # noqa: ARG001
    try:
        from prometheus_client import multiprocess

        multiprocess.mark_process_dead(worker.pid)
    except ImportError:
        pass
