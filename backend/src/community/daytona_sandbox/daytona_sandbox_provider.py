"""Daytona Sandbox Provider — manages sandbox lifecycle via the Daytona SDK.

Provisions cloud sandboxes through the Daytona API for isolated code
execution.  Each ``thread_id`` gets its own sandbox; anonymous requests
receive a one-off sandbox.

Configuration in ``config.yaml`` under ``sandbox``:

    sandbox:
      use: src.community.daytona_sandbox:DaytonaSandboxProvider
      # Daytona API key (resolved from env if prefixed with $)
      api_key: $DAYTONA_API_KEY
      # Daytona API URL (default: https://app.daytona.io/api)
      api_url: https://app.daytona.io/api
      # Target region (default: us)
      target: us
      # Docker image for the sandbox (default: python:3.12-slim)
      image: python:3.12-slim
      # Language runtime (default: python)
      language: python
      # Auto-stop interval in minutes (default: 15, 0 to disable)
      auto_stop_interval: 15
      # Environment variables to inject into the sandbox
      environment:
        NODE_ENV: production
        API_KEY: $MY_API_KEY
"""

import atexit
import logging
import os
import signal
import threading
import time

from daytona import CreateSandboxFromImageParams, Daytona, DaytonaConfig

from src.config import get_app_config
from src.sandbox.sandbox import Sandbox
from src.sandbox.sandbox_provider import SandboxProvider

from .daytona_sandbox import DaytonaSandbox

logger = logging.getLogger(__name__)

DEFAULT_API_URL = "https://app.daytona.io/api"
DEFAULT_TARGET = "us"
DEFAULT_IMAGE = "python:3.12-slim"
DEFAULT_LANGUAGE = "python"
DEFAULT_AUTO_STOP = 15  # minutes
DEFAULT_TIMEOUT = 120  # seconds to wait for sandbox creation
IDLE_CHECK_INTERVAL = 60  # seconds


class DaytonaSandboxProvider(SandboxProvider):
    """Sandbox provider that manages Daytona cloud sandboxes.

    Configuration options in config.yaml under sandbox:
        use: src.community.daytona_sandbox:DaytonaSandboxProvider
        api_key: $DAYTONA_API_KEY
        api_url: https://app.daytona.io/api
        target: us
        image: python:3.12-slim
        language: python
        auto_stop_interval: 15
        environment: {}
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._sandboxes: dict[str, DaytonaSandbox] = {}  # sandbox_id -> DaytonaSandbox
        self._thread_sandboxes: dict[str, str] = {}  # thread_id -> sandbox_id
        self._last_activity: dict[str, float] = {}  # sandbox_id -> timestamp
        self._user_sandboxes: dict[str, set[str]] = {}  # user_id -> set of sandbox_ids
        self._shutdown_called = False
        self._idle_checker_stop = threading.Event()
        self._idle_checker_thread: threading.Thread | None = None

        self._config = self._load_config()
        self._daytona = self._create_client()
        self._max_per_user: int = self._config.get("max_sandboxes_per_user", 3)

        atexit.register(self.shutdown)
        self._register_signal_handlers()

        idle_timeout = self._config.get("idle_timeout", DEFAULT_AUTO_STOP * 60)
        if idle_timeout > 0:
            self._start_idle_checker()

    # ── Client creation ──────────────────────────────────────────────────

    def _create_client(self) -> Daytona:
        cfg = DaytonaConfig(
            api_key=self._config.get("api_key") or None,
            api_url=self._config.get("api_url") or DEFAULT_API_URL,
            target=self._config.get("target") or DEFAULT_TARGET,
        )
        return Daytona(cfg)

    # ── Configuration ────────────────────────────────────────────────────

    def _load_config(self) -> dict:
        config = get_app_config()
        sandbox_cfg = config.sandbox

        raw_api_key = getattr(sandbox_cfg, "api_key", None) or ""
        api_key = self._resolve_env(raw_api_key)

        return {
            "api_key": api_key,
            "api_url": getattr(sandbox_cfg, "api_url", None) or DEFAULT_API_URL,
            "target": getattr(sandbox_cfg, "target", None) or DEFAULT_TARGET,
            "image": sandbox_cfg.image or DEFAULT_IMAGE,
            "language": getattr(sandbox_cfg, "language", None) or DEFAULT_LANGUAGE,
            "auto_stop_interval": getattr(sandbox_cfg, "auto_stop_interval", None) or DEFAULT_AUTO_STOP,
            "idle_timeout": (getattr(sandbox_cfg, "idle_timeout", None) or DEFAULT_AUTO_STOP * 60),
            "max_sandboxes_per_user": getattr(sandbox_cfg, "max_sandboxes_per_user", 3),
            "environment": self._resolve_env_vars(sandbox_cfg.environment or {}),
        }

    @staticmethod
    def _resolve_env(value: str) -> str:
        if isinstance(value, str) and value.startswith("$"):
            return os.environ.get(value[1:], "")
        return value

    @staticmethod
    def _resolve_env_vars(env_config: dict[str, str]) -> dict[str, str]:
        resolved = {}
        for key, value in env_config.items():
            if isinstance(value, str) and value.startswith("$"):
                resolved[key] = os.environ.get(value[1:], "")
            else:
                resolved[key] = str(value)
        return resolved

    # ── Core: acquire / get / release / shutdown ─────────────────────────

    def acquire(self, thread_id: str | None = None, user_id: str | None = None) -> str:
        # Fast path: reuse existing sandbox for the same thread
        if thread_id:
            with self._lock:
                if thread_id in self._thread_sandboxes:
                    existing_id = self._thread_sandboxes[thread_id]
                    if existing_id in self._sandboxes:
                        logger.info("Reusing Daytona sandbox %s for thread %s", existing_id, thread_id)
                        self._last_activity[existing_id] = time.time()
                        return existing_id

        # Per-user quota check
        if user_id and self._max_per_user > 0:
            with self._lock:
                current_count = len(self._user_sandboxes.get(user_id, set()))
            if current_count >= self._max_per_user:
                raise RuntimeError(
                    f"User {user_id} has reached the maximum of {self._max_per_user} concurrent sandboxes."
                )

        # Create a new Daytona sandbox
        env_vars = dict(self._config.get("environment", {}))
        params = CreateSandboxFromImageParams(
            image=self._config["image"],
            language=self._config["language"],
            env_vars=env_vars if env_vars else None,
            auto_stop_interval=self._config["auto_stop_interval"],
            labels={"thread_id": thread_id} if thread_id else None,
        )

        try:
            daytona_sb = self._daytona.create(params, timeout=DEFAULT_TIMEOUT)
        except Exception as e:
            logger.error("Failed to create Daytona sandbox: %s", e)
            raise RuntimeError(f"Failed to create Daytona sandbox: {e}") from e

        sandbox_id = daytona_sb.id
        sandbox = DaytonaSandbox(id=sandbox_id, daytona_sandbox=daytona_sb)

        with self._lock:
            self._sandboxes[sandbox_id] = sandbox
            self._last_activity[sandbox_id] = time.time()
            if thread_id:
                self._thread_sandboxes[thread_id] = sandbox_id
            if user_id:
                self._user_sandboxes.setdefault(user_id, set()).add(sandbox_id)

        logger.info("Created Daytona sandbox %s for thread %s", sandbox_id, thread_id)
        return sandbox_id

    def get(self, sandbox_id: str) -> Sandbox | None:
        with self._lock:
            sandbox = self._sandboxes.get(sandbox_id)
            if sandbox is not None:
                self._last_activity[sandbox_id] = time.time()
            return sandbox

    def release(self, sandbox_id: str) -> None:
        sandbox: DaytonaSandbox | None = None
        with self._lock:
            sandbox = self._sandboxes.pop(sandbox_id, None)
            thread_ids = [tid for tid, sid in self._thread_sandboxes.items() if sid == sandbox_id]
            for tid in thread_ids:
                del self._thread_sandboxes[tid]
            self._last_activity.pop(sandbox_id, None)
            for uid, sids in list(self._user_sandboxes.items()):
                sids.discard(sandbox_id)
                if not sids:
                    del self._user_sandboxes[uid]

        if sandbox is not None:
            try:
                self._daytona.delete(sandbox.daytona_sandbox, timeout=60)
                logger.info("Deleted Daytona sandbox %s", sandbox_id)
            except Exception as e:
                logger.error("Failed to delete Daytona sandbox %s: %s", sandbox_id, e)

    def shutdown(self) -> None:
        with self._lock:
            if self._shutdown_called:
                return
            self._shutdown_called = True
            sandbox_ids = list(self._sandboxes.keys())

        self._idle_checker_stop.set()
        if self._idle_checker_thread is not None and self._idle_checker_thread.is_alive():
            self._idle_checker_thread.join(timeout=5)

        logger.info("Shutting down %d Daytona sandbox(es)", len(sandbox_ids))
        for sandbox_id in sandbox_ids:
            try:
                self.release(sandbox_id)
            except Exception as e:
                logger.error("Failed to release Daytona sandbox %s during shutdown: %s", sandbox_id, e)

    # ── Idle timeout management ──────────────────────────────────────────

    def _start_idle_checker(self) -> None:
        self._idle_checker_thread = threading.Thread(
            target=self._idle_checker_loop,
            name="daytona-sandbox-idle-checker",
            daemon=True,
        )
        self._idle_checker_thread.start()

    def _idle_checker_loop(self) -> None:
        idle_timeout = self._config.get("idle_timeout", DEFAULT_AUTO_STOP * 60)
        while not self._idle_checker_stop.wait(timeout=IDLE_CHECK_INTERVAL):
            try:
                self._cleanup_idle(idle_timeout)
            except Exception as e:
                logger.error("Error in Daytona idle checker: %s", e)

    def _cleanup_idle(self, idle_timeout: float) -> None:
        now = time.time()
        to_release = []
        with self._lock:
            for sandbox_id, last in self._last_activity.items():
                if now - last > idle_timeout:
                    to_release.append(sandbox_id)

        for sandbox_id in to_release:
            logger.info("Releasing idle Daytona sandbox %s", sandbox_id)
            try:
                self.release(sandbox_id)
            except Exception as e:
                logger.error("Failed to release idle Daytona sandbox %s: %s", sandbox_id, e)

    # ── Signal handling ──────────────────────────────────────────────────

    def _register_signal_handlers(self) -> None:
        self._original_sigterm = signal.getsignal(signal.SIGTERM)
        self._original_sigint = signal.getsignal(signal.SIGINT)

        def handler(signum, frame):
            self.shutdown()
            original = self._original_sigterm if signum == signal.SIGTERM else self._original_sigint
            if callable(original):
                original(signum, frame)
            elif original == signal.SIG_DFL:
                signal.signal(signum, signal.SIG_DFL)
                signal.raise_signal(signum)

        try:
            signal.signal(signal.SIGTERM, handler)
            signal.signal(signal.SIGINT, handler)
        except ValueError:
            logger.debug("Could not register signal handlers (not main thread)")
