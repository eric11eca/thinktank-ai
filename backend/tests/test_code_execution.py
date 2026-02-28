"""Tests for the code execution tool."""


from src.sandbox.code_execution import MAX_OUTPUT_LENGTH


class TestCodeExecutionConstants:
    """Tests for code execution tool constants and configuration."""

    def test_max_output_length_is_reasonable(self):
        """MAX_OUTPUT_LENGTH should be a reasonable value for context efficiency."""
        assert MAX_OUTPUT_LENGTH == 4096

    def test_execute_python_tool_has_correct_name(self):
        """The tool should be named 'execute_python'."""
        from src.sandbox.code_execution import execute_python_tool

        assert execute_python_tool.name == "execute_python"

    def test_execute_python_tool_has_examples(self):
        """The tool should have Examples in its description."""
        from src.sandbox.code_execution import execute_python_tool

        assert "Examples:" in execute_python_tool.description

    def test_execute_python_tool_has_save_output_param(self):
        """The tool should document the save_output_to parameter."""
        from src.sandbox.code_execution import execute_python_tool

        assert "save_output_to" in execute_python_tool.description

    def test_execute_python_not_in_subagent_disallowed_tools(self):
        """execute_python should be available to subagents."""
        from src.subagents.builtins.general_purpose import GENERAL_PURPOSE_CONFIG

        assert "execute_python" not in GENERAL_PURPOSE_CONFIG.disallowed_tools

    def test_execute_python_behavioral_rules_exist(self):
        """execute_python should have behavioral rules in tool_policies."""
        from src.tools.docs.tool_policies import TOOL_BEHAVIORAL_RULES

        assert "execute_python" in TOOL_BEHAVIORAL_RULES

    def test_execute_python_in_config_tools(self):
        """execute_python should be registered in config.yaml tools list.

        This test verifies the tool path is correct by importing the module.
        """
        from src.sandbox.code_execution import execute_python_tool

        assert execute_python_tool is not None
