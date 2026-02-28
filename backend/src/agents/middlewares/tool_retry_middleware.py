"""Middleware for retrying transient tool failures with exponential backoff."""

import asyncio
import logging
import re
import time
from collections.abc import Callable
from enum import StrEnum
from typing import override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

logger = logging.getLogger(__name__)


class ErrorCategory(StrEnum):
    """Classification of tool error types."""

    TRANSIENT = "transient"
    AUTH = "auth"
    PERSISTENT = "persistent"
    UNKNOWN = "unknown"


# Tools that should never be retried
NO_RETRY_TOOLS: set[str] = {"ask_clarification", "think", "present_files"}

# Patterns for error classification (compiled for performance)
_TRANSIENT_PATTERNS = re.compile(
    r"timeout|timed?\s*out|connection\s*(refused|reset|error)|"
    r"rate\s*limit|too\s*many\s*requests|"
    r"502|503|504|"
    r"temporarily\s*unavailable|service\s*unavailable|"
    r"network\s*(error|unreachable)|"
    r"ECONNREFUSED|ECONNRESET|ETIMEDOUT",
    re.IGNORECASE,
)

_AUTH_PATTERNS = re.compile(
    r"401|403|forbidden|unauthorized|"
    r"api\s*key|credential|authentication\s*failed|"
    r"access\s*denied|invalid\s*token",
    re.IGNORECASE,
)

_PERSISTENT_PATTERNS = re.compile(
    r"not\s*found|404|does\s*not\s*exist|"
    r"invalid\s*(argument|parameter|input)|"
    r"permission\s*denied|"
    r"is\s*a\s*directory|not\s*a\s*directory|"
    r"no\s*such\s*file|"
    r"syntax\s*error|"
    r"command\s*not\s*found",
    re.IGNORECASE,
)


def classify_error(error_message: str) -> ErrorCategory:
    """Classify an error message into a category.

    Args:
        error_message: The error string from a tool result.

    Returns:
        The error category.
    """
    if _TRANSIENT_PATTERNS.search(error_message):
        return ErrorCategory.TRANSIENT
    if _AUTH_PATTERNS.search(error_message):
        return ErrorCategory.AUTH
    if _PERSISTENT_PATTERNS.search(error_message):
        return ErrorCategory.PERSISTENT
    return ErrorCategory.UNKNOWN


def _is_error_result(result: ToolMessage | Command) -> bool:
    """Check if a tool result indicates an error."""
    if isinstance(result, Command):
        return False
    content = getattr(result, "content", "")
    return isinstance(content, str) and content.startswith("Error:")


def _get_error_content(result: ToolMessage) -> str:
    """Extract error content from a ToolMessage."""
    return getattr(result, "content", "")


class ToolRetryMiddleware(AgentMiddleware[AgentState]):
    """Retries transient tool failures with exponential backoff.

    Follows the same wrap_tool_call/awrap_tool_call pattern as ClarificationMiddleware.
    Only retries errors classified as TRANSIENT. AUTH, PERSISTENT, and UNKNOWN
    errors are returned immediately.

    Args:
        max_retries: Maximum number of retry attempts (default: 2).
        base_delay: Base delay in seconds for exponential backoff (default: 1.0).
    """

    def __init__(self, max_retries: int = 2, base_delay: float = 1.0):
        super().__init__()
        self.max_retries = max_retries
        self.base_delay = base_delay

    def _should_retry(self, tool_name: str, error_message: str, attempt: int) -> bool:
        """Determine if a tool call should be retried.

        Args:
            tool_name: Name of the tool that failed.
            error_message: The error message from the tool result.
            attempt: Current retry attempt number (0-indexed).

        Returns:
            True if the tool call should be retried.
        """
        if tool_name in NO_RETRY_TOOLS:
            return False
        if attempt >= self.max_retries:
            return False
        return classify_error(error_message) == ErrorCategory.TRANSIENT

    def _enrich_error(self, error_message: str, attempts: int) -> str:
        """Add retry context to a final error message.

        Args:
            error_message: The original error message.
            attempts: Total number of attempts made.

        Returns:
            Enriched error message with retry information.
        """
        return f"{error_message}\n[Retried {attempts} time(s) — all attempts failed with transient errors]"

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        """Retry transient tool failures with exponential backoff (sync).

        Args:
            request: Tool call request.
            handler: Original tool execution handler.

        Returns:
            Tool result, potentially after retries.
        """
        tool_name = request.tool_call.get("name", "")

        # First attempt
        result = handler(request)

        if not _is_error_result(result):
            return result

        error_message = _get_error_content(result)

        # Retry loop
        for attempt in range(self.max_retries):
            if not self._should_retry(tool_name, error_message, attempt):
                return result

            delay = self.base_delay * (2 ** attempt)
            logger.warning(
                "Tool '%s' failed with transient error (attempt %d/%d), retrying in %.1fs: %s",
                tool_name, attempt + 1, self.max_retries, delay, error_message[:200],
            )
            time.sleep(delay)

            result = handler(request)
            if not _is_error_result(result):
                logger.info("Tool '%s' succeeded on retry attempt %d", tool_name, attempt + 1)
                return result
            error_message = _get_error_content(result)

        # All retries exhausted
        logger.error("Tool '%s' failed after %d retries: %s", tool_name, self.max_retries, error_message[:200])
        enriched = self._enrich_error(error_message, self.max_retries)
        return ToolMessage(content=enriched, tool_call_id=result.tool_call_id, name=tool_name)

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        """Retry transient tool failures with exponential backoff (async).

        Args:
            request: Tool call request.
            handler: Original tool execution handler (async).

        Returns:
            Tool result, potentially after retries.
        """
        tool_name = request.tool_call.get("name", "")

        # First attempt
        result = await handler(request)

        if not _is_error_result(result):
            return result

        error_message = _get_error_content(result)

        # Retry loop
        for attempt in range(self.max_retries):
            if not self._should_retry(tool_name, error_message, attempt):
                return result

            delay = self.base_delay * (2 ** attempt)
            logger.warning(
                "Tool '%s' failed with transient error (attempt %d/%d), retrying in %.1fs: %s",
                tool_name, attempt + 1, self.max_retries, delay, error_message[:200],
            )
            await asyncio.sleep(delay)

            result = await handler(request)
            if not _is_error_result(result):
                logger.info("Tool '%s' succeeded on retry attempt %d", tool_name, attempt + 1)
                return result
            error_message = _get_error_content(result)

        # All retries exhausted
        logger.error("Tool '%s' failed after %d retries: %s", tool_name, self.max_retries, error_message[:200])
        enriched = self._enrich_error(error_message, self.max_retries)
        return ToolMessage(content=enriched, tool_call_id=result.tool_call_id, name=tool_name)
