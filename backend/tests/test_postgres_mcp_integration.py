"""Integration tests for postgres-mcp tools against the ERP sample database.

These tests require:
  1. Docker with thinktank-postgres running (make db-start)
  2. ERP sample database populated (make erp-setup)
  3. uvx available (ships with uv)

Run with: cd backend && uv run pytest tests/test_postgres_mcp_integration.py -v -m integration
Skip with: pytest -m "not integration" (default behavior)
"""

import asyncio
import shutil
import subprocess

import pytest

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
    """Check if the erp_sample database exists and has data."""
    try:
        result = subprocess.run(
            ["docker", "exec", "thinktank-postgres", "psql", "-U", "thinktank", "-d", "erp_sample", "-tc",
             "SELECT COUNT(*) FROM employees"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0 and result.stdout.strip() != "0"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


skip_no_docker = pytest.mark.skipif(not _docker_available(), reason="Docker not available")
skip_no_uvx = pytest.mark.skipif(not _uvx_available(), reason="uvx not available")
skip_no_erp = pytest.mark.skipif(not _erp_database_ready(), reason="ERP database not ready (run: make erp-setup)")

ERP_DATABASE_URI = "postgresql://thinktank:matterhorn@localhost:5432/erp_sample"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mcp_tools():
    """Load postgres-mcp tools via MultiServerMCPClient.

    Session-scoped: creates the MCP client once for all tests in this module.
    """
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient({
        "postgres": {
            "transport": "stdio",
            "command": "uvx",
            "args": ["postgres-mcp", "--access-mode=unrestricted"],
            "env": {"DATABASE_URI": ERP_DATABASE_URI},
        }
    })

    tools = asyncio.get_event_loop().run_until_complete(client.get_tools())
    assert len(tools) > 0, "No tools loaded from postgres-mcp"
    return tools


def _find_tool(tools, name_substring: str):
    """Find a tool by partial name match."""
    for tool in tools:
        if name_substring.lower() in tool.name.lower():
            return tool
    tool_names = [t.name for t in tools]
    raise ValueError(f"Tool matching '{name_substring}' not found. Available: {tool_names}")


# ---------------------------------------------------------------------------
# MCP Tool Tests
# ---------------------------------------------------------------------------

@skip_no_docker
@skip_no_uvx
@skip_no_erp
class TestPostgresMCPTools:
    """Integration tests for individual postgres-mcp tools."""

    def test_tools_loaded(self, mcp_tools):
        """postgres-mcp should expose multiple tools."""
        assert len(mcp_tools) >= 4, f"Expected at least 4 tools, got {len(mcp_tools)}"
        tool_names = [t.name for t in mcp_tools]
        print(f"Available tools: {tool_names}")

    def test_list_schemas(self, mcp_tools):
        """list_schemas should return the public schema."""
        tool = _find_tool(mcp_tools, "list_schemas")
        result = asyncio.get_event_loop().run_until_complete(tool.ainvoke({}))
        assert "public" in str(result).lower(), f"Expected 'public' schema in result: {result}"

    def test_list_objects(self, mcp_tools):
        """list_objects should return ERP tables."""
        tool = _find_tool(mcp_tools, "list_objects")
        result = asyncio.get_event_loop().run_until_complete(
            tool.ainvoke({"schema_name": "public"})
        )
        result_str = str(result).lower()
        assert "employees" in result_str, f"Expected 'employees' table in result: {result}"
        assert "orders" in result_str, f"Expected 'orders' table in result: {result}"

    def test_get_object_details(self, mcp_tools):
        """get_object_details should return column info for employees."""
        tool = _find_tool(mcp_tools, "get_object_details")
        result = asyncio.get_event_loop().run_until_complete(
            tool.ainvoke({"schema_name": "public", "object_name": "employees"})
        )
        result_str = str(result).lower()
        assert "first_name" in result_str, f"Expected 'first_name' column in result: {result}"
        assert "department_id" in result_str, f"Expected 'department_id' column in result: {result}"

    def test_execute_sql_count(self, mcp_tools):
        """execute_sql should return correct count of employees."""
        tool = _find_tool(mcp_tools, "execute_sql")
        result = asyncio.get_event_loop().run_until_complete(
            tool.ainvoke({"sql": "SELECT COUNT(*) AS cnt FROM employees"})
        )
        assert "50" in str(result), f"Expected 50 employees, got: {result}"

    def test_execute_sql_join(self, mcp_tools):
        """execute_sql should handle JOIN queries correctly."""
        tool = _find_tool(mcp_tools, "execute_sql")
        result = asyncio.get_event_loop().run_until_complete(
            tool.ainvoke({
                "sql": """
                    SELECT d.name, COUNT(e.id) AS emp_count
                    FROM departments d
                    LEFT JOIN employees e ON e.department_id = d.id
                    GROUP BY d.name
                    ORDER BY emp_count DESC
                    LIMIT 3
                """
            })
        )
        result_str = str(result)
        # Engineering and Sales should be in top departments
        assert "Engineering" in result_str or "Sales" in result_str, f"Expected dept names in result: {result}"

    def test_explain_query(self, mcp_tools):
        """explain_query should return an execution plan."""
        tool = _find_tool(mcp_tools, "explain_query")
        result = asyncio.get_event_loop().run_until_complete(
            tool.ainvoke({"sql": "SELECT * FROM orders WHERE status = 'shipped'"})
        )
        result_str = str(result).lower()
        # Should contain plan nodes
        assert "scan" in result_str or "seq" in result_str or "index" in result_str, \
            f"Expected execution plan in result: {result}"

    def test_analyze_db_health(self, mcp_tools):
        """analyze_db_health should return health metrics."""
        tool = _find_tool(mcp_tools, "analyze_db_health")
        result = asyncio.get_event_loop().run_until_complete(tool.ainvoke({}))
        assert result is not None and len(str(result)) > 0, "Expected non-empty health result"


# ---------------------------------------------------------------------------
# Analytical Query Tests (simulating agent research scenarios)
# ---------------------------------------------------------------------------

@skip_no_docker
@skip_no_uvx
@skip_no_erp
class TestERPAnalyticalQueries:
    """Verify the ERP data supports the analytical queries agents will need."""

    def test_top_selling_category(self, mcp_tools):
        """Agent scenario: 'What is our top-selling product category?'"""
        tool = _find_tool(mcp_tools, "execute_sql")
        result = asyncio.get_event_loop().run_until_complete(
            tool.ainvoke({
                "sql": """
                    SELECT pc.name AS category, SUM(oi.quantity * oi.unit_price) AS revenue
                    FROM order_items oi
                    JOIN products p ON oi.product_id = p.id
                    JOIN product_categories pc ON p.category_id = pc.id
                    GROUP BY pc.name
                    ORDER BY revenue DESC
                    LIMIT 1
                """
            })
        )
        result_str = str(result)
        assert result_str, "Expected a top-selling category result"
        # Should return one of our categories
        categories = ["Electronics", "Office Supplies", "Furniture", "Software Licenses",
                       "Networking", "Storage", "Peripherals", "Security", "Cloud Services", "Training Materials"]
        assert any(cat in result_str for cat in categories), f"Expected a category name in result: {result}"

    def test_department_revenue(self, mcp_tools):
        """Agent scenario: 'Show me department performance by revenue'"""
        tool = _find_tool(mcp_tools, "execute_sql")
        result = asyncio.get_event_loop().run_until_complete(
            tool.ainvoke({
                "sql": """
                    SELECT d.name AS department, SUM(o.total_amount) AS total_revenue
                    FROM departments d
                    JOIN employees e ON e.department_id = d.id
                    JOIN orders o ON o.employee_id = e.id
                    GROUP BY d.name
                    ORDER BY total_revenue DESC
                """
            })
        )
        result_str = str(result)
        # Sales department should have significant revenue
        assert "Sales" in result_str, f"Expected 'Sales' department in result: {result}"

    def test_month_over_month_growth(self, mcp_tools):
        """Agent scenario: 'What is the month-over-month growth in orders?'"""
        tool = _find_tool(mcp_tools, "execute_sql")
        result = asyncio.get_event_loop().run_until_complete(
            tool.ainvoke({
                "sql": """
                    WITH monthly AS (
                        SELECT DATE_TRUNC('month', order_date) AS month,
                               SUM(total_amount) AS revenue
                        FROM orders
                        GROUP BY DATE_TRUNC('month', order_date)
                    )
                    SELECT month::date, revenue,
                           LAG(revenue) OVER (ORDER BY month) AS prev_revenue,
                           ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY month))
                                 / NULLIF(LAG(revenue) OVER (ORDER BY month), 0), 2) AS growth_pct
                    FROM monthly
                    ORDER BY month
                """
            })
        )
        result_str = str(result)
        # Should have multiple months of data
        assert "2024" in result_str or "2025" in result_str, \
            f"Expected date data in result: {result}"

    def test_top_employees_by_sales(self, mcp_tools):
        """Agent scenario: 'Top 5 employees by total sales with departments'"""
        tool = _find_tool(mcp_tools, "execute_sql")
        result = asyncio.get_event_loop().run_until_complete(
            tool.ainvoke({
                "sql": """
                    SELECT e.first_name || ' ' || e.last_name AS employee_name,
                           d.name AS department,
                           SUM(o.total_amount) AS total_sales
                    FROM employees e
                    JOIN departments d ON e.department_id = d.id
                    JOIN orders o ON o.employee_id = e.id
                    GROUP BY e.id, e.first_name, e.last_name, d.name
                    ORDER BY total_sales DESC
                    LIMIT 5
                """
            })
        )
        result_str = str(result)
        # Should have employee names
        assert result_str and len(result_str) > 10, f"Expected employee data in result: {result}"
