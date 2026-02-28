"""Tests for the think tool."""



class TestThinkTool:
    """Tests for think_tool functionality."""

    def test_think_tool_returns_thought(self):
        """Think tool should return the input thought as-is."""
        from src.tools.builtins.think_tool import think_tool

        result = think_tool.invoke({"thought": "test reasoning"})
        assert result == "test reasoning"

    def test_think_tool_preserves_content(self):
        """Think tool should preserve the full thought content."""
        from src.tools.builtins.think_tool import think_tool

        complex_thought = (
            "The search results show three sources. "
            "Source A says X, Source B says Y. "
            "I should proceed with X because it's more recent."
        )
        result = think_tool.invoke({"thought": complex_thought})
        assert result == complex_thought

    def test_think_tool_has_correct_name(self):
        """Think tool should be named 'think'."""
        from src.tools.builtins.think_tool import think_tool

        assert think_tool.name == "think"

    def test_think_tool_has_examples_in_docstring(self):
        """Think tool should have Examples in its description."""
        from src.tools.builtins.think_tool import think_tool

        assert "Examples:" in think_tool.description

    def test_think_tool_in_builtin_tools(self):
        """Think tool should be included in BUILTIN_TOOLS."""
        from src.tools.tools import BUILTIN_TOOLS

        tool_names = [t.name for t in BUILTIN_TOOLS]
        assert "think" in tool_names

    def test_think_tool_in_builtins_all(self):
        """Think tool should be exported from builtins __all__."""
        from src.tools.builtins import __all__

        assert "think_tool" in __all__

    def test_think_tool_not_in_subagent_disallowed_tools(self):
        """Think tool should NOT be in general-purpose subagent's disallowed_tools.

        Subagents should be able to use the think tool for structured reasoning.
        """
        from src.subagents.builtins.general_purpose import GENERAL_PURPOSE_CONFIG

        assert "think" not in GENERAL_PURPOSE_CONFIG.disallowed_tools


class TestToolPolicies:
    """Tests for tool usage policies."""

    def test_get_tool_usage_policies_includes_relevant_rules(self):
        """Policies should include rules for tools in the provided list."""
        from src.tools.docs.tool_policies import get_tool_usage_policies

        policies = get_tool_usage_policies(["bash", "read_file", "think"])
        assert "bash — Behavioral Rules:" in policies
        assert "read_file — Behavioral Rules:" in policies
        assert "think — Behavioral Rules:" in policies

    def test_get_tool_usage_policies_excludes_irrelevant_rules(self):
        """Policies should NOT include rules for tools not in the list."""
        from src.tools.docs.tool_policies import get_tool_usage_policies

        policies = get_tool_usage_policies(["bash"])
        assert "bash — Behavioral Rules:" in policies
        assert "web_search — Behavioral Rules:" not in policies

    def test_get_tool_usage_policies_contains_preference_cascade(self):
        """Policies should always contain the tool preference cascade."""
        from src.tools.docs.tool_policies import get_tool_usage_policies

        policies = get_tool_usage_policies(["bash"])
        assert "Tool Preference Cascade:" in policies

    def test_get_tool_usage_policies_contains_phase_guidance(self):
        """Policies should contain phase-aware tool selection guidance."""
        from src.tools.docs.tool_policies import get_tool_usage_policies

        policies = get_tool_usage_policies(["bash"])
        assert "Phase-Aware Tool Selection:" in policies

    def test_get_tool_usage_policies_empty_tools(self):
        """Policies should work with empty tool list."""
        from src.tools.docs.tool_policies import get_tool_usage_policies

        policies = get_tool_usage_policies([])
        assert "Tool Preference Cascade:" in policies
        assert "tool_behavioral_rules" not in policies


class TestPhaseFilterMiddleware:
    """Tests for phase filter middleware constants."""

    def test_phase_tool_allowlist_has_all_phases(self):
        """PHASE_TOOL_ALLOWLIST should have entries for all phases."""
        from src.agents.middlewares.phase_filter_middleware import (
            PHASE_TOOL_ALLOWLIST,
            ExecutionPhase,
        )

        for phase in ExecutionPhase:
            assert phase in PHASE_TOOL_ALLOWLIST

    def test_planning_phase_includes_search_tools(self):
        """Planning phase should include search and read tools."""
        from src.agents.middlewares.phase_filter_middleware import (
            PHASE_TOOL_ALLOWLIST,
            ExecutionPhase,
        )

        planning = PHASE_TOOL_ALLOWLIST[ExecutionPhase.PLANNING]
        assert "web_search" in planning
        assert "read_file" in planning
        assert "think" in planning

    def test_planning_phase_excludes_write_tools(self):
        """Planning phase should exclude write/execution tools."""
        from src.agents.middlewares.phase_filter_middleware import (
            PHASE_TOOL_ALLOWLIST,
            ExecutionPhase,
        )

        planning = PHASE_TOOL_ALLOWLIST[ExecutionPhase.PLANNING]
        assert "write_file" not in planning
        assert "str_replace" not in planning

    def test_execution_phase_includes_all_tools(self):
        """Execution phase should include the broadest set of tools."""
        from src.agents.middlewares.phase_filter_middleware import (
            PHASE_TOOL_ALLOWLIST,
            ExecutionPhase,
        )

        execution = PHASE_TOOL_ALLOWLIST[ExecutionPhase.EXECUTION]
        assert "bash" in execution
        assert "write_file" in execution
        assert "web_search" in execution
        assert "task" in execution

    def test_synthesis_phase_excludes_search(self):
        """Synthesis phase should not include web search tools."""
        from src.agents.middlewares.phase_filter_middleware import (
            PHASE_TOOL_ALLOWLIST,
            ExecutionPhase,
        )

        synthesis = PHASE_TOOL_ALLOWLIST[ExecutionPhase.SYNTHESIS]
        assert "web_search" not in synthesis
        assert "web_fetch" not in synthesis
        assert "write_file" in synthesis

    def test_review_phase_is_read_heavy(self):
        """Review phase should be read-heavy with limited write access."""
        from src.agents.middlewares.phase_filter_middleware import (
            PHASE_TOOL_ALLOWLIST,
            ExecutionPhase,
        )

        review = PHASE_TOOL_ALLOWLIST[ExecutionPhase.REVIEW]
        assert "read_file" in review
        assert "think" in review
        assert "write_file" not in review
        assert "str_replace" not in review
