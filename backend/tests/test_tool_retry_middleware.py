"""Tests for the tool retry middleware."""

from unittest.mock import MagicMock, patch

from langchain_core.messages import ToolMessage

from src.agents.middlewares.tool_retry_middleware import (
    NO_RETRY_TOOLS,
    ErrorCategory,
    ToolRetryMiddleware,
    classify_error,
)


class TestClassifyError:
    """Tests for error classification."""

    def test_timeout_is_transient(self):
        assert classify_error("Error: Connection timed out") == ErrorCategory.TRANSIENT

    def test_connection_refused_is_transient(self):
        assert classify_error("Error: Connection refused") == ErrorCategory.TRANSIENT

    def test_rate_limit_is_transient(self):
        assert classify_error("Error: Rate limit exceeded, too many requests") == ErrorCategory.TRANSIENT

    def test_503_is_transient(self):
        assert classify_error("Error: 503 Service Unavailable") == ErrorCategory.TRANSIENT

    def test_502_is_transient(self):
        assert classify_error("Error: 502 Bad Gateway") == ErrorCategory.TRANSIENT

    def test_temporarily_unavailable_is_transient(self):
        assert classify_error("Error: Service temporarily unavailable") == ErrorCategory.TRANSIENT

    def test_401_is_auth(self):
        assert classify_error("Error: 401 Unauthorized") == ErrorCategory.AUTH

    def test_403_is_auth(self):
        assert classify_error("Error: 403 Forbidden") == ErrorCategory.AUTH

    def test_api_key_is_auth(self):
        assert classify_error("Error: Invalid API key") == ErrorCategory.AUTH

    def test_not_found_is_persistent(self):
        assert classify_error("Error: File not found: /path/to/file") == ErrorCategory.PERSISTENT

    def test_is_a_directory_is_persistent(self):
        assert classify_error("Error: Path is a directory, not a file") == ErrorCategory.PERSISTENT

    def test_no_such_file_is_persistent(self):
        assert classify_error("Error: No such file or directory") == ErrorCategory.PERSISTENT

    def test_command_not_found_is_persistent(self):
        assert classify_error("Error: command not found: foobar") == ErrorCategory.PERSISTENT

    def test_generic_error_is_unknown(self):
        assert classify_error("Error: Something went wrong") == ErrorCategory.UNKNOWN

    def test_empty_string_is_unknown(self):
        assert classify_error("") == ErrorCategory.UNKNOWN


class TestShouldRetry:
    """Tests for retry decision logic."""

    def setup_method(self):
        self.middleware = ToolRetryMiddleware(max_retries=2, base_delay=0.01)

    def test_no_retry_for_no_retry_tools(self):
        for tool_name in NO_RETRY_TOOLS:
            assert not self.middleware._should_retry(tool_name, "Error: timeout", 0)

    def test_no_retry_after_max_attempts(self):
        assert not self.middleware._should_retry("bash", "Error: timeout", 2)

    def test_retry_for_transient_error(self):
        assert self.middleware._should_retry("bash", "Error: Connection timed out", 0)

    def test_no_retry_for_persistent_error(self):
        assert not self.middleware._should_retry("bash", "Error: File not found", 0)

    def test_no_retry_for_auth_error(self):
        assert not self.middleware._should_retry("web_search", "Error: 401 Unauthorized", 0)

    def test_no_retry_for_unknown_error(self):
        assert not self.middleware._should_retry("bash", "Error: Something weird", 0)


class TestWrapToolCall:
    """Tests for the sync wrap_tool_call method."""

    def setup_method(self):
        self.middleware = ToolRetryMiddleware(max_retries=2, base_delay=0.01)

    def _make_request(self, tool_name="bash"):
        request = MagicMock()
        request.tool_call = {"name": tool_name, "id": "test_id", "args": {}}
        return request

    def _make_success_result(self):
        return ToolMessage(content="Success output", tool_call_id="test_id")

    def _make_error_result(self, error_msg="Error: Connection timed out"):
        return ToolMessage(content=error_msg, tool_call_id="test_id")

    def test_success_passes_through(self):
        """Successful tool calls should pass through without retry."""
        request = self._make_request()
        handler = MagicMock(return_value=self._make_success_result())

        result = self.middleware.wrap_tool_call(request, handler)

        assert result.content == "Success output"
        handler.assert_called_once()

    def test_persistent_error_no_retry(self):
        """Persistent errors should not be retried."""
        request = self._make_request()
        handler = MagicMock(return_value=self._make_error_result("Error: File not found"))

        result = self.middleware.wrap_tool_call(request, handler)

        assert "File not found" in result.content
        handler.assert_called_once()

    @patch("src.agents.middlewares.tool_retry_middleware.time.sleep")
    def test_transient_error_retries_and_succeeds(self, mock_sleep):
        """Transient errors should trigger retries, and succeed if retry works."""
        request = self._make_request()
        handler = MagicMock(side_effect=[
            self._make_error_result("Error: Connection timed out"),
            self._make_success_result(),
        ])

        result = self.middleware.wrap_tool_call(request, handler)

        assert result.content == "Success output"
        assert handler.call_count == 2
        mock_sleep.assert_called_once()

    @patch("src.agents.middlewares.tool_retry_middleware.time.sleep")
    def test_transient_error_exhausts_retries(self, mock_sleep):
        """Should return enriched error after exhausting retries."""
        request = self._make_request()
        handler = MagicMock(return_value=self._make_error_result("Error: Connection timed out"))

        result = self.middleware.wrap_tool_call(request, handler)

        assert "Connection timed out" in result.content
        assert "Retried 2 time(s)" in result.content
        assert handler.call_count == 3  # 1 initial + 2 retries

    @patch("src.agents.middlewares.tool_retry_middleware.time.sleep")
    def test_three_fails_then_success(self, mock_sleep):
        """Mock handler failing twice then succeeding on third retry."""
        middleware = ToolRetryMiddleware(max_retries=3, base_delay=0.01)
        request = self._make_request()
        handler = MagicMock(side_effect=[
            self._make_error_result("Error: 503 Service Unavailable"),
            self._make_error_result("Error: 503 Service Unavailable"),
            self._make_error_result("Error: 503 Service Unavailable"),
            self._make_success_result(),
        ])

        result = middleware.wrap_tool_call(request, handler)

        assert result.content == "Success output"
        assert handler.call_count == 4

    def test_no_retry_tool_passes_error_through(self):
        """Tools in NO_RETRY_TOOLS should not be retried even for transient errors."""
        request = self._make_request("think")
        handler = MagicMock(return_value=self._make_error_result("Error: Connection timed out"))

        result = self.middleware.wrap_tool_call(request, handler)

        assert "Connection timed out" in result.content
        handler.assert_called_once()

    def test_command_result_passes_through(self):
        """Command results (non-ToolMessage) should pass through."""
        from langgraph.types import Command

        request = self._make_request()
        command = Command(update={"messages": []})
        handler = MagicMock(return_value=command)

        result = self.middleware.wrap_tool_call(request, handler)

        assert isinstance(result, Command)
        handler.assert_called_once()


class TestEnrichError:
    """Tests for error message enrichment."""

    def test_enrich_error_includes_retry_count(self):
        middleware = ToolRetryMiddleware()
        enriched = middleware._enrich_error("Error: Connection timed out", 2)
        assert "Retried 2 time(s)" in enriched
        assert "Connection timed out" in enriched

    def test_enrich_error_mentions_transient(self):
        middleware = ToolRetryMiddleware()
        enriched = middleware._enrich_error("Error: timeout", 3)
        assert "transient errors" in enriched
