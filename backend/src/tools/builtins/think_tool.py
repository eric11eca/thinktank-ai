"""Think tool for structured reasoning between tool calls."""

from langchain.tools import tool


@tool("think", parse_docstring=True)
def think_tool(thought: str) -> str:
    """Use this tool to think step-by-step, reflect on gathered information, and plan your next actions.

    This is a scratchpad for explicit reasoning. The thought content is returned as-is
    and becomes part of the conversation context.

    When to use:
    - After receiving search results, to analyze and identify what's relevant
    - Before making a complex decision, to weigh options
    - When synthesizing information from multiple tool calls
    - To plan a multi-step approach before executing it
    - To verify your understanding before acting on it

    When NOT to use:
    - For simple, single-step operations where the action is obvious
    - As a substitute for the model's built-in thinking/reasoning capability
    - To repeat information without adding analysis

    Examples:
        think(thought="Search results show 3 conflicting claims. Sources A and C agree on 100/min. Source B is outdated (2023). Proceeding with 100/min.")
        think(thought="Plan: 1) Read auth middleware, 2) Find token validation, 3) Add refresh token support, 4) Update tests.")

    Args:
        thought: Your reasoning, analysis, or plan. Be specific and actionable.
    """
    return thought
