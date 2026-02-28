"""Cross-cutting tool usage policies and per-tool behavioral rules.

These constants are injected into the system prompt to guide tool selection
and usage patterns. Stored as Python constants for importability and testability.
"""

CROSS_CUTTING_POLICIES = """<tool_usage_policies>

**Tool Preference Cascade:**
1. Use `read_file` instead of `bash(command="cat ...")` to read files
2. Use `str_replace` instead of `write_file` for targeted edits to existing files
3. Use `ls` instead of `bash(command="ls ...")` or `bash(command="find ...")` for directory listing
4. Use `write_file` only for creating new files or complete rewrites
5. Use `reflection` after gathering information from search or file reads to analyze before acting
6. Use `execute_python` instead of `bash(command="python ...")` for data analysis and structured Python execution

**Anti-Patterns to Avoid:**
- Do NOT chain multiple bash commands when dedicated tools exist (e.g., `bash("cat file.py | grep pattern")` — use `read_file` then analyze)
- Do NOT use `write_file` to make small edits — use `str_replace` to preserve surrounding content
- Do NOT call tools redundantly — if you already have the information, use `reflection` to analyze it
- Do NOT execute destructive commands (rm -rf, DROP TABLE) without explicit user confirmation via `ask_clarification`

**Parallel Tool Calling:**
- Call independent tools in parallel when possible (e.g., reading multiple files, searching multiple queries)
- Do NOT parallelize tools with dependencies (e.g., write then read the same file)

**Reflection-After-Search Rule:**
- After receiving results from `web_search`, `read_file`, or multiple tool calls, use `reflection` to analyze and synthesize before taking the next action
- This ensures deliberate reasoning rather than reactive tool chaining

{phase_guidance}
</tool_usage_policies>"""


TOOL_BEHAVIORAL_RULES: dict[str, str] = {
    "bash": """**bash — Behavioral Rules:**
- Always provide a clear `description` explaining the command's purpose
- Use absolute paths for all file references
- For long-running commands, consider breaking them into smaller steps
- If a command fails, analyze the error before retrying — do not blindly retry
- Prefer dedicated tools (read_file, write_file, ls) over bash equivalents""",

    "web_search": """**web_search — Behavioral Rules:**
- Use specific, targeted queries with relevant keywords
- Include year/date qualifiers for time-sensitive information
- After receiving results, use `reflection` to evaluate relevance and credibility
- If initial results are insufficient, refine the query rather than repeating it
- Follow up with `web_fetch` only on URLs from search results""",

    "web_fetch": """**web_fetch — Behavioral Rules:**
- Only fetch URLs from search results or explicitly provided by the user
- Do NOT guess or construct URLs
- Content is truncated to 4KB — for longer pages, focus on extracting key sections
- Cannot access authenticated or private content""",

    "str_replace": """**str_replace — Behavioral Rules:**
- Always read the file first to understand context before replacing
- Provide enough surrounding context in `old_str` to ensure unique matching
- Use `replace_all=True` only for variable/function renames across a file
- Verify the replacement by reading the file after modification if the change is critical""",

    "write_file": """**write_file — Behavioral Rules:**
- Use only for creating new files or complete rewrites
- For small edits to existing files, use `str_replace` instead
- Final deliverables must be written to `/mnt/user-data/outputs`
- Temporary work files go in `/mnt/user-data/workspace`""",

    "read_file": """**read_file — Behavioral Rules:**
- Use `start_line` and `end_line` for large files to read only relevant sections
- Read configuration files before modifying them
- For binary files or images, use `view_image` instead""",

    "execute_python": """**execute_python — Behavioral Rules:**
- Prefer over `bash(command="python ...")` for data analysis and complex computation
- Use `save_output_to` when output might be large (e.g., dataframes, long lists)
- Include necessary imports in each code block (execution is stateless)
- Use `description` to explain the analysis goal clearly""",

    "reflection": """**reflection — Behavioral Rules:**
- Use after receiving search results or reading files to analyze before acting
- Use before making complex decisions to weigh options explicitly
- Keep reflections focused and actionable — avoid restating raw data
- Do NOT use as a substitute for the model's built-in reasoning""",

    "present_files": """**present_files — Behavioral Rules:**
- Only present files from `/mnt/user-data/outputs`
- Move final deliverables to outputs directory before presenting
- Present after all modifications are complete, not during intermediate steps""",
}

# Phase guidance section for context-aware tool filtering (Step 5)
PHASE_GUIDANCE = """
**Phase-Aware Tool Selection:**
Consider which phase of work you are in and select tools accordingly:

| Phase | Appropriate Tools | Avoid |
|-------|------------------|-------|
| **Planning** (understanding requirements, exploring codebase) | reflection, read_file, ls, web_search, web_fetch, ask_clarification | bash, write_file, str_replace |
| **Execution** (implementing changes, running code) | bash, write_file, str_replace, read_file, execute_python, task, reflection | — |
| **Synthesis** (assembling results, writing reports) | write_file, str_replace, read_file, reflection, execute_python | web_search, web_fetch |
| **Review** (verifying results, checking quality) | read_file, ls, reflection, ask_clarification, bash (for tests only) | write_file, str_replace |
"""


def get_tool_usage_policies(tool_names: list[str]) -> str:
    """Assemble tool usage policies based on available tools.

    Combines cross-cutting policies with relevant per-tool behavioral rules
    based on which tools are actually available in the current session.

    Args:
        tool_names: List of tool names available to the agent.

    Returns:
        Formatted policies string for injection into system prompt.
    """
    # Collect relevant behavioral rules
    relevant_rules = []
    for name in sorted(tool_names):
        if name in TOOL_BEHAVIORAL_RULES:
            relevant_rules.append(TOOL_BEHAVIORAL_RULES[name])

    rules_section = "\n\n".join(relevant_rules) if relevant_rules else ""

    # Build the full policies string
    policies = CROSS_CUTTING_POLICIES.format(phase_guidance=PHASE_GUIDANCE)

    if rules_section:
        policies += f"\n\n<tool_behavioral_rules>\n{rules_section}\n</tool_behavioral_rules>"

    return policies
