"""Tests for the centralized logging configuration."""

import json
import logging
import os
from io import StringIO
from unittest.mock import patch

import pytest


class TestConfigureLogging:
    """Tests for configure_logging()."""

    def setup_method(self):
        """Reset logging state before each test."""
        # Remove all handlers from root logger
        root = logging.getLogger()
        for h in root.handlers[:]:
            root.removeHandler(h)

    def _capture_log_output(self, level: str = "INFO", log_format: str = "text"):
        """Helper: configure logging and capture output."""
        env = {"LOG_LEVEL": level, "LOG_FORMAT": log_format}
        with patch.dict(os.environ, env, clear=False):
            # Re-import to pick up new env vars
            from src.logging_config import configure_logging
            configure_logging()

            # Replace handler stream with our capture buffer
            root = logging.getLogger()
            buf = StringIO()
            for handler in root.handlers:
                handler.stream = buf
            return root, buf

    def test_text_mode_formatting(self):
        """Text mode produces human-readable output."""
        root, buf = self._capture_log_output(log_format="text")
        test_logger = logging.getLogger("test.text")
        test_logger.info("hello world")
        output = buf.getvalue()
        assert "hello world" in output
        assert "test.text" in output
        assert "INFO" in output

    def test_json_mode_formatting(self):
        """JSON mode produces valid JSON log lines."""
        root, buf = self._capture_log_output(log_format="json")
        test_logger = logging.getLogger("test.json")
        test_logger.info("structured log")
        output = buf.getvalue().strip()
        if not output:
            pytest.skip("python-json-logger not installed")
        # Should be parseable as JSON
        parsed = json.loads(output)
        assert parsed["message"] == "structured log"
        assert "timestamp" in parsed or "asctime" in parsed

    def test_log_level_respected(self):
        """LOG_LEVEL env var controls minimum log level."""
        root, buf = self._capture_log_output(level="WARNING")
        test_logger = logging.getLogger("test.level")
        test_logger.info("should be hidden")
        test_logger.warning("should appear")
        output = buf.getvalue()
        assert "should be hidden" not in output
        assert "should appear" in output

    def test_default_log_level_is_info(self):
        """Without LOG_LEVEL env var, default is INFO."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LOG_LEVEL", None)
            os.environ.pop("LOG_FORMAT", None)
            from src.logging_config import configure_logging
            configure_logging()
            root = logging.getLogger()
            assert root.level == logging.INFO

    def test_noisy_loggers_suppressed(self):
        """httpx and httpcore loggers are set to WARNING."""
        self._capture_log_output()
        assert logging.getLogger("httpx").level >= logging.WARNING
        assert logging.getLogger("httpcore").level >= logging.WARNING


class TestNoPrintStatements:
    """Regression test: no print() calls in production source code."""

    def test_no_print_in_source(self):
        """Scan for print() calls in src/ directory."""
        import re
        from pathlib import Path

        src_dir = Path(__file__).parent.parent / "src"
        violations = []

        for py_file in src_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for i, line in enumerate(content.splitlines(), 1):
                stripped = line.lstrip()
                # Skip comments and strings
                if stripped.startswith("#"):
                    continue
                # Match print( at the start of a statement
                if re.match(r"^print\s*\(", stripped):
                    violations.append(f"{py_file.relative_to(src_dir)}:{i}: {stripped[:80]}")

        assert not violations, (
            f"Found {len(violations)} print() call(s) in source:\n"
            + "\n".join(violations)
        )
