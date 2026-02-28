"""End-to-end integration tests: lead agent + LLM (claude-sonnet-4-6) + postgres-mcp.

These tests exercise the FULL agent loop:
  User query -> LLM (with thinking) -> tool calls -> tool execution -> final response

Requirements:
  1. Docker with thinktank-postgres running (make db-start)
  2. ERP sample database populated (make erp-setup)
  3. uvx available (ships with uv)
  4. ANTHROPIC_API_KEY environment variable set

Run with: cd backend && uv run pytest tests/test_agent_erp_e2e.py -v -m integration -s
Skip with: pytest -m "not integration"
"""

import os
import shutil
import subprocess

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Skip conditions
# ---------------------------------------------------------------------------

def _docker_available() -> bool:
    try:
        result = subprocess.run(["docker", "info"], capture_output=True, timeout=10)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _uvx_available() -> bool:
    return shutil.which("uvx") is not None


def _erp_database_ready() -> bool:
    try:
        result = subprocess.run(
            ["docker", "exec", "thinktank-postgres", "psql", "-U", "thinktank", "-d", "erp_sample", "-tc",
             "SELECT COUNT(*) FROM employees"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0 and result.stdout.strip() != "0"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _anthropic_key_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


skip_no_docker = pytest.mark.skipif(not _docker_available(), reason="Docker not available")
skip_no_uvx = pytest.mark.skipif(not _uvx_available(), reason="uvx not available")
skip_no_erp = pytest.mark.skipif(not _erp_database_ready(), reason="ERP database not ready (run: make erp-setup)")
skip_no_api_key = pytest.mark.skipif(not _anthropic_key_available(), reason="ANTHROPIC_API_KEY not set")

ERP_DATABASE_URI = "postgresql://thinktank:matterhorn@localhost:5432/erp_sample"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def setup_mcp_config():
    """Inject postgres-mcp config and reset cache before running agent tests."""
    from src.config.extensions_config import (
        ExtensionsConfig,
        McpServerConfig,
        reset_extensions_config,
        set_extensions_config,
    )
    from src.mcp.cache import reset_mcp_tools_cache

    # Inject postgres MCP config programmatically
    set_extensions_config(ExtensionsConfig(
        mcp_servers={
            "postgres": McpServerConfig(
                enabled=True,
                type="stdio",
                command="uvx",
                args=["postgres-mcp", "--access-mode=unrestricted"],
                env={"DATABASE_URI": ERP_DATABASE_URI},
                description="PostgreSQL ERP database",
            )
        },
    ))
    reset_mcp_tools_cache()

    yield

    # Cleanup
    reset_extensions_config()
    reset_mcp_tools_cache()


async def _run_agent(user_query: str) -> dict:
    """Run the lead agent with a user query and return the results.

    Uses async streaming because MCP tools are async-only (loaded via
    langchain_mcp_adapters with coroutine, no sync func).

    Returns dict with keys: messages, tool_calls, tool_results, final_response
    """
    from src.agents.lead_agent.agent import make_lead_agent

    thread_id = f"test-erp-e2e-{hash(user_query) % 10000}"

    config = {
        "configurable": {
            "model_name": "claude-sonnet-4-6",
            "thinking_enabled": True,
            "thread_id": thread_id,
            "is_plan_mode": False,
            "subagent_enabled": False,
        }
    }

    # The `context` parameter populates `runtime.context` accessed by middlewares.
    # It is separate from `config["configurable"]` which is used by make_lead_agent().
    context = {
        "thread_id": thread_id,
    }

    graph = make_lead_agent(config)
    input_state = {"messages": [HumanMessage(content=user_query)]}

    all_messages = []
    tool_calls_seen = []
    tool_results_seen = []

    # Use async streaming because MCP tools require async invocation
    async for chunk in graph.astream(input_state, config=config, context=context, stream_mode="updates"):
        for node_name, updates in chunk.items():
            if updates is None or not isinstance(updates, dict):
                continue
            if "messages" in updates:
                for msg in updates["messages"]:
                    all_messages.append(msg)

                    if isinstance(msg, AIMessage) and msg.tool_calls:
                        tool_calls_seen.extend(msg.tool_calls)
                        tool_names = [tc["name"] for tc in msg.tool_calls]
                        print(f"  [TOOL CALL] {tool_names}")

                    elif isinstance(msg, ToolMessage):
                        tool_results_seen.append(msg)
                        content_preview = str(msg.content)[:200]
                        print(f"  [TOOL RESULT] {msg.name}: {content_preview}")

                    elif isinstance(msg, AIMessage) and not msg.tool_calls:
                        content = msg.content if isinstance(msg.content, str) else str(msg.content)
                        print(f"  [AI RESPONSE] {content[:300]}")

    # Extract final AI response (last AIMessage without tool_calls)
    final_response = ""
    for msg in reversed(all_messages):
        if isinstance(msg, AIMessage) and not msg.tool_calls:
            final_response = msg.content if isinstance(msg.content, str) else str(msg.content)
            break

    return {
        "messages": all_messages,
        "tool_calls": tool_calls_seen,
        "tool_results": tool_results_seen,
        "final_response": final_response,
    }


# ---------------------------------------------------------------------------
# E2E Agent Tests
# ---------------------------------------------------------------------------

@skip_no_docker
@skip_no_uvx
@skip_no_erp
@skip_no_api_key
class TestAgentERPE2E:
    """End-to-end tests: full agent loop with LLM + postgres-mcp tools."""

    @pytest.mark.asyncio
    async def test_agent_discovers_schema(self):
        """Agent should use MCP tools to discover database tables."""
        print("\n--- test_agent_discovers_schema ---")
        result = await _run_agent("What tables exist in the database? Just list them briefly.")

        # Should have made at least one tool call
        assert len(result["tool_calls"]) > 0, "Expected at least one tool call"

        # Tool calls should include schema/object listing tools
        tool_names = [tc["name"] for tc in result["tool_calls"]]
        print(f"  Tools used: {tool_names}")

        # Final response should mention some tables
        response = result["final_response"].lower()
        assert any(
            table in response
            for table in ["employees", "orders", "products", "departments", "customers"]
        ), f"Expected table names in response: {result['final_response'][:500]}"

    @pytest.mark.asyncio
    async def test_agent_top_selling_category(self):
        """Agent should query and analyze top-selling product categories."""
        print("\n--- test_agent_top_selling_category ---")
        result = await _run_agent(
            "What's our top-selling product category by revenue? "
            "Give me the top 3 categories with their revenue figures."
        )

        # Should have used execute_sql or similar tool
        assert len(result["tool_calls"]) > 0, "Expected tool calls for SQL execution"

        tool_names = [tc["name"] for tc in result["tool_calls"]]
        print(f"  Tools used: {tool_names}")

        # Verify SQL-related tools were used
        sql_tools_used = any(
            "sql" in name.lower() or "query" in name.lower() or "execute" in name.lower()
            for name in tool_names
        )
        assert sql_tools_used, f"Expected SQL execution tools, got: {tool_names}"

        # Final response should contain category and revenue info
        response = result["final_response"].lower()
        assert any(
            kw in response
            for kw in ["category", "revenue", "electronics", "software", "networking"]
        ), f"Expected category/revenue info in response: {result['final_response'][:500]}"

    @pytest.mark.asyncio
    async def test_agent_department_performance(self):
        """Agent should analyze department performance by revenue."""
        print("\n--- test_agent_department_performance ---")
        result = await _run_agent("Show me department performance ranked by total order revenue.")

        assert len(result["tool_calls"]) > 0, "Expected tool calls"

        tool_names = [tc["name"] for tc in result["tool_calls"]]
        print(f"  Tools used: {tool_names}")

        # Response should mention departments
        response = result["final_response"].lower()
        assert any(
            dept in response
            for dept in ["sales", "engineering", "operations", "department"]
        ), f"Expected department info in response: {result['final_response'][:500]}"

    @pytest.mark.asyncio
    async def test_agent_mom_growth(self):
        """Agent should analyze month-over-month order growth."""
        print("\n--- test_agent_mom_growth ---")
        result = await _run_agent(
            "What's the month-over-month growth in total order revenue? "
            "Show the last 6 months with growth percentages."
        )

        assert len(result["tool_calls"]) > 0, "Expected tool calls"

        tool_names = [tc["name"] for tc in result["tool_calls"]]
        print(f"  Tools used: {tool_names}")

        # Response should contain temporal and growth data
        response = result["final_response"].lower()
        assert any(
            kw in response
            for kw in ["month", "growth", "revenue", "%", "percent"]
        ), f"Expected growth/temporal data in response: {result['final_response'][:500]}"
