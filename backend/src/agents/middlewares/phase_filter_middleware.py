"""Skeleton middleware for context-aware tool filtering based on execution phase.

Currently only logs the detected phase. Can later be extended to strip disallowed
tool calls in after_model (like SubagentLimitMiddleware truncates excess task calls).

Phase detection is heuristic-based — it examines conversation history to infer
which phase the agent is in. The actual enforcement is prompt-guided (soft)
via PHASE_GUIDANCE in tool_policies.py.
"""

import logging
from enum import StrEnum
from typing import override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


class ExecutionPhase(StrEnum):
    """Execution phases for tool filtering."""

    PLANNING = "planning"
    EXECUTION = "execution"
    SYNTHESIS = "synthesis"
    REVIEW = "review"


# Tool allowlist per phase — defines which tools are appropriate in each phase.
# Currently used for logging/monitoring only. Future: enforce by stripping disallowed
# tool calls in after_model.
PHASE_TOOL_ALLOWLIST: dict[ExecutionPhase, set[str]] = {
    ExecutionPhase.PLANNING: {
        "web_search", "web_fetch",
        "reflection", "read_file", "ls",
        "ask_clarification",
    },
    ExecutionPhase.EXECUTION: {
        "web_search", "web_fetch",
        "reflection", "read_file", "ls",
        "ask_clarification",
        "bash", "write_file", "str_replace",
        "execute_python",
        "present_files", "task",
    },
    ExecutionPhase.SYNTHESIS: {
        "reflection", "read_file", "ls",
        "ask_clarification",
        "bash", "write_file", "str_replace",
        "execute_python",
    },
    ExecutionPhase.REVIEW: {
        "reflection", "read_file", "ls",
        "ask_clarification",
        "bash",  # for running tests
    },
}


def _detect_phase(state: AgentState) -> ExecutionPhase:
    """Heuristic phase detection from conversation state.

    Examines the message history to infer the current execution phase.
    This is a best-effort heuristic — the model may not follow phases linearly.

    Args:
        state: Current agent state with message history.

    Returns:
        Detected execution phase.
    """
    messages = state.get("messages", [])
    if not messages:
        return ExecutionPhase.PLANNING

    # Count tool calls and types to infer phase
    ai_messages = [m for m in messages if getattr(m, "type", None) == "ai"]
    if not ai_messages:
        return ExecutionPhase.PLANNING

    # Look at recent tool calls to detect phase transitions
    recent_tool_calls = []
    for msg in reversed(ai_messages[-5:]):
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            recent_tool_calls.extend([tc.get("name", "") for tc in tool_calls])

    write_tools = {"write_file", "str_replace", "bash"}
    read_tools = {"read_file", "web_search", "web_fetch", "ls"}
    present_tools = {"present_files"}

    recent_set = set(recent_tool_calls)

    # If presenting files, likely in review/synthesis phase
    if recent_set & present_tools:
        return ExecutionPhase.REVIEW

    # If mostly writing/executing, in execution phase
    if recent_set & write_tools:
        return ExecutionPhase.EXECUTION

    # If mostly reading/searching, in planning phase
    if recent_set & read_tools:
        return ExecutionPhase.PLANNING

    # Default to execution for ongoing conversations
    if len(ai_messages) > 2:
        return ExecutionPhase.EXECUTION

    return ExecutionPhase.PLANNING


class PhaseFilterMiddleware(AgentMiddleware[AgentState]):
    """Logs the detected execution phase before model invocation.

    Currently observation-only. Future extension: strip disallowed tool calls
    from model output based on detected phase (like SubagentLimitMiddleware).
    """

    @override
    def before_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        phase = _detect_phase(state)
        logger.debug("Detected execution phase: %s", phase.value)
        return None

    @override
    async def abefore_model(self, state: AgentState, runtime: Runtime) -> dict | None:
        phase = _detect_phase(state)
        logger.debug("Detected execution phase: %s", phase.value)
        return None
