# Deep Research: Agent Architecture Improvement Report

> Comprehensive analysis of state-of-the-art agentic systems with actionable recommendations for DeerFlow 2.0

**Date**: 2026-02-27
**Systems Analyzed**: 15+ agentic frameworks and deep-research systems
**Sources**: open-ptc-agent, OpenClaw, Claude Code, Anthropic Engineering Blog, OpenAI Deep Research, Perplexity, LangGraph, CrewAI, AutoGen, Gemini Deep Research, Grok/xAI, Manus AI, DSPy, OpenAI Agents SDK

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Architecture Assessment](#2-current-architecture-assessment)
3. [System Prompt Engineering](#3-system-prompt-engineering)
4. [Context Engineering](#4-context-engineering)
5. [Agent State & Memory Management](#5-agent-state--memory-management)
6. [Tool Usage & Orchestration](#6-tool-usage--orchestration)
7. [File & Document Processing](#7-file--document-processing)
8. [Multi-Agent Architecture](#8-multi-agent-architecture)
9. [Deep Research Capabilities](#9-deep-research-capabilities)
10. [Implementation Priority Matrix](#10-implementation-priority-matrix)
11. [Sources & References](#11-sources--references)

---

## 1. Executive Summary

After analyzing 15+ production agentic systems, seven major improvement areas emerge for DeerFlow 2.0. The most impactful changes cluster around three themes:

1. **Context engineering as a first-class discipline** -- treating the context window as an engineered system with its own lifecycle, budget management, and optimization metrics (KV-cache hit rate, attention anchoring, selective compaction)
2. **Externalized state persistence** -- moving from in-memory conversation state to file-based progress tracking that survives context resets and enables multi-session operation
3. **Structured research orchestration** -- replacing ad-hoc subagent delegation with explicit planning-execution-synthesis pipelines with progressive context accumulation

The gap analysis reveals that DeerFlow has strong foundations (middleware chain, MCP integration, memory system, subagent orchestration) but lacks several patterns that top systems have converged on independently: progressive tool discovery, KV-cache-aware context construction, attention anchoring via todo rewriting, multi-pass synthesis, and structured research planning.

---

## 2. Current Architecture Assessment

### Strengths

| Capability | Implementation | Quality |
|---|---|---|
| Middleware chain | 13-stage ordered pipeline | Excellent -- clear separation of concerns |
| Persistent memory | Per-user facts + contextual summaries | Good -- confidence-scored, token-budgeted |
| MCP tool integration | Multi-server with lazy init + caching | Good -- fault-tolerant per-server |
| Subagent orchestration | Parallel execution with concurrency control | Good -- per-user semaphores, batching |
| Context compression | SummarizationMiddleware with configurable triggers | Adequate -- basic summarization |
| File processing | Auto-conversion pipeline (PDF/PPT/Excel/Word -> MD) | Good -- markitdown integration |
| Virtual path system | Seamless sandbox abstraction | Good -- transparent translation |

### Gaps Identified

| Gap | Impact | Systems That Solve It |
|---|---|---|
| No progressive tool discovery | Bloated system prompt with all tool schemas upfront | open-ptc-agent, Claude Code |
| No KV-cache-aware context construction | 10x higher API costs from cache misses | Manus AI |
| No structured research planning | Subagents lack coordinated research strategy | Perplexity, Gemini, open-ptc-agent |
| No attention anchoring mechanism | Critical objectives lost in long contexts | Manus AI, Claude Code |
| No multi-pass synthesis | Single-pass output quality ceiling | Gemini Deep Research |
| No tool result compaction (selective) | Full tool outputs waste context space | Claude Code, OpenClaw, Manus AI |
| No file-based state externalization | Context resets lose all progress | Claude Agent SDK, Manus AI |
| No think-after-search loop | Research quality depends on implicit reasoning | open-ptc-agent |
| Single subagent depth (no nesting) | Cannot decompose deeply recursive tasks | OpenClaw |
| No agent error recovery/retry logic | Tool failures terminate without alternatives | LangGraph, OpenClaw |
| No skill-adaptive loading | Skills listed statically regardless of task type | Claude Code |
| No citation grounding | Research outputs lack verifiable sources | Perplexity, OpenAI Deep Research |

---

## 3. System Prompt Engineering

### 3.1 Current State

DeerFlow uses a template-based system prompt in `backend/src/agents/lead_agent/prompt.py` with dynamic injection of memory context, skills, subagent instructions, and working directory paths. The prompt is monolithic -- one large template with conditional sections.

### 3.2 Best Practices from Industry

#### A. Modular Prompt Composition (Claude Code Pattern)

**What Claude Code does**: 223 independently versioned prompt fragments organized into 6 categories (agent prompts, data references, skill prompts, system prompts, system reminders, tool descriptions). Fragments use namespace conventions like `doing-tasks-*` and `tool-usage-*`.

**What open-ptc-agent does**: Jinja2 template composition with `{% include %}` directives. The main `system.md.j2` includes 7 modular components (workspace_paths, tool_discovery, output_guidelines, citation_rules, subagent_coordination, data_processing, image_upload).

**Recommendation**: Decompose the monolithic prompt template into independently maintainable fragments:

```
prompts/
  system/
    identity.md.j2           # Role definition
    thinking_style.md.j2     # Reasoning guidance
    clarification_rules.md.j2 # When to ask for clarification
  context/
    memory_injection.md.j2   # Persistent memory section
    skills_listing.md.j2     # Available skills
    uploads_context.md.j2    # Uploaded files
  tools/
    tool_discovery.md.j2     # Progressive discovery workflow
    tool_usage_policies.md.j2 # Cross-cutting usage rules
  research/
    planning.md.j2           # Research planning workflow
    citation_rules.md.j2     # Citation formatting
    synthesis_guidelines.md.j2 # Multi-pass synthesis
  delegation/
    subagent_coordination.md.j2 # Task decomposition strategy
    batching_rules.md.j2     # Concurrency management
```

#### B. Instruction Intensity Hierarchy (Claude Code Pattern)

Claude Code uses a deliberate escalation of language strength:
1. **Suggestion**: "Prefer editing existing files"
2. **Directive**: "Only make changes that are directly requested"
3. **Strong Directive**: "Do not propose changes to code you haven't read"
4. **Prohibition**: "NEVER create files unless absolutely necessary"
5. **Critical**: "STRICTLY PROHIBITED" (reserved for safety)

**Recommendation**: Audit current prompt instructions and apply consistent intensity levels. Reserve ALL CAPS for safety-critical rules only.

#### C. Few-Shot Examples Over Rule Lists (Anthropic Guidance)

Anthropic's context engineering guide emphasizes: for LLMs, examples are far more effective than comprehensive rule lists. The anti-pattern is enumerating every possible edge case.

**Recommendation**: Replace the clarification scenario list with 3-5 diverse canonical examples showing expected agent behavior, including the agent's reasoning process.

#### D. Variable Interpolation (Claude Code Pattern)

Claude Code uses `${TOOL_NAME}` variables rather than hardcoded tool references, enabling tool renaming without prompt rewrites.

**Recommendation**: Introduce template variables for tool names, directory paths, and configurable thresholds. This also enables A/B testing of prompt variations.

### 3.3 Specific Improvements

| Priority | Change | Effort | Impact |
|---|---|---|---|
| High | Decompose into modular Jinja2 fragments | Medium | Maintainability, testability |
| High | Add research planning section with structured workflow | Medium | Research quality |
| Medium | Add citation rules section | Low | Output quality |
| Medium | Replace rule lists with few-shot examples | Medium | Compliance rate |
| Low | Implement variable interpolation for tool names | Low | Decoupling |

---

## 4. Context Engineering

### 4.1 Current State

DeerFlow has `SummarizationMiddleware` that compresses older messages when approaching token limits (trigger at configurable threshold, keeps recent messages). Memory injection is capped at 2000 tokens. Tool results are returned in full.

### 4.2 Critical Concept: Context Rot

From Anthropic's engineering blog: as context tokens increase, the model's ability to accurately recall information decreases. This is not a cliff but a gradient. Models have finite "attention budgets" that get depleted by low-signal tokens. The guiding principle: **find the smallest possible set of high-signal tokens that maximize desired outcomes**.

### 4.3 Best Practices from Industry

#### A. KV-Cache-Aware Context Construction (Manus AI Pattern)

Manus reports this as their #1 production metric. With Claude Sonnet, cached tokens cost $0.30/MTok vs $3.00/MTok uncached -- a 10x cost difference. Their input-to-output ratio is approximately 100:1.

**Three principles**:
1. **Stable prefixes**: Even a single-token difference invalidates the cache from that point. System prompt + tool definitions must be deterministic.
2. **Append-only context**: Never modify previous messages or tool results. Ensure deterministic serialization order.
3. **Explicit cache breakpoints**: Mark breakpoints when the provider doesn't support automatic incremental prefix caching.

**Recommendation**: Audit the message construction pipeline to ensure:
- System prompt is rendered deterministically (no timestamp-dependent content in the prefix)
- Tool definitions maintain stable ordering across invocations
- Previous messages are never mutated (only appended to)
- SummarizationMiddleware preserves cache-friendly prefixes

#### B. Selective Tool Result Compaction (Claude Code + Manus Pattern)

Rather than keeping full tool results or summarizing everything, selectively compact stale tool results:
- Replace old tool outputs with `[compacted: {tool_name} output removed -- re-run if needed]`
- Keep the agent's conclusions about tool results (in its response messages)
- This is "the safest, lightest-touch form of compaction" per Anthropic

**Recommendation**: Add a `ToolResultCompactionMiddleware` that:
1. Tracks tool result age (turns since last reference)
2. After N turns without reference, replaces content with compact summary
3. Preserves the tool call structure (so the model knows the tool was called)
4. Allows re-execution if the agent needs the data again

#### C. Attention Anchoring via Todo Rewriting (Manus Pattern)

Manus constantly rewrites `todo.md`, pushing current objectives to the end of context (the model's strongest attention zone). This prevents the "lost-in-the-middle" problem where critical objectives get buried.

**Recommendation**: Modify `TodoListMiddleware` to:
1. Append the current todo state at the END of each agent turn (not just when updated)
2. Include a "Current Focus" field that restates the active objective
3. On compaction, ensure the todo list is preserved in full at the end of the summary

#### D. Three-Layer Context Management (OpenClaw Pattern)

OpenClaw implements three complementary layers:
1. **Proactive history limiting**: Counts backward through messages, keeping only N most recent user turns
2. **Tool result truncation**: Allocates 30% of context to tool results, uses head-tail truncation (70% from start, 20% from end)
3. **Runtime context guard**: Interceptor that caps individual tool results at 50% of context window

**Recommendation**: Implement all three layers as distinct middlewares:
- `HistoryLimitMiddleware` -- configurable turn limit
- `ToolResultTruncationMiddleware` -- budget-based with head-tail strategy
- `ContextGuardMiddleware` -- runtime safety net

#### E. Progressive Tool Discovery (open-ptc-agent Pattern)

Instead of injecting all tool schemas upfront:
1. At startup, show only tool **summaries** (server name, tool count, import path)
2. Agent discovers exact signatures on-demand via documentation files
3. Discovery workflow: `glob("tools/docs/{server}/*.md")` -> `read_file("{tool}.md")`

This dramatically reduces system prompt token count for large tool sets.

**Recommendation**: For MCP servers with 5+ tools, switch to summary-only injection with on-demand discovery via `read_file`.

### 4.4 Context Budget Allocation

Based on patterns across all analyzed systems, here is a recommended context budget allocation:

| Component | Budget | Rationale |
|---|---|---|
| System prompt (base) | 5-8% | Stable prefix for KV-cache |
| Memory injection | 3-5% | Top facts + contextual summaries |
| Skills context | 2-4% | Only active skill content |
| Tool definitions | 3-5% | Summaries only; full schemas on-demand |
| Conversation history | 40-50% | Recent turns in full, older compressed |
| Tool results | 20-30% | Budget-capped with selective compaction |
| Working memory (todos) | 2-3% | Attention anchor at context end |
| Reserved headroom | 10-15% | Safety margin for generation |

---

## 5. Agent State & Memory Management

### 5.1 Current State

DeerFlow has a robust per-user memory system with confidence-scored facts (max 100), contextual summaries (user context, history, long-term background), and a debounced update queue. Memory is injected into system prompts within a 2000-token budget.

### 5.2 Best Practices from Industry

#### A. Three-File External State (Manus AI Pattern)

Manus uses three persistent files as the agent's externalized working memory:
- **`task_plan.md`**: The roadmap outlining every step
- **`notes.md`**: External memory bank for research findings and interim results
- **`todo.md`**: Live checklist constantly rewritten for attention anchoring

**Recommendation**: Implement a `WorkingStateMiddleware` that maintains:
```
workspace/
  PLAN.md        # Current task plan (structured sections)
  NOTES.md       # Research findings, interim results
  PROGRESS.md    # Current state summary (for session recovery)
```

Benefits:
- Survives context compaction (files can be re-read)
- Enables multi-session operation (next session reads PROGRESS.md)
- Provides user visibility into agent reasoning

#### B. Hybrid Memory Search (OpenClaw Pattern)

OpenClaw's memory system combines:
- **Vector similarity** (embedding-based semantic search)
- **BM25 keyword ranking** (full-text search)
- **Temporal decay** (exponential: 30-day half-life)
- **MMR re-ranking** (Maximal Marginal Relevance for diversity)

The formula: `vectorWeight * vectorScore + textWeight * textScore`, with decay applied, then MMR diversification.

**Current gap**: DeerFlow's memory uses confidence-based ranking but lacks temporal decay and diversity re-ranking. Old facts can persist indefinitely even when irrelevant.

**Recommendation**:
1. Add temporal decay to fact retrieval (configurable half-life)
2. Implement MMR or similar diversity mechanism to avoid retrieving near-duplicate facts
3. Consider adding vector search alongside the current structured fact store for richer semantic retrieval

#### C. Structured Compaction (Claude Code Pattern)

When context fills, Claude Code distills to five sections:
1. **Task Overview** (what "done" looks like)
2. **Current State** (completed work with file paths)
3. **Important Discoveries** (decisions, resolved errors, failed approaches)
4. **Next Steps** (remaining actions, blockers, priorities)
5. **Context to Preserve** (user preferences, commitments)

Priority: "information that would prevent duplicate work or repeated mistakes."

**Recommendation**: Replace the generic SummarizationMiddleware prompt with this structured five-section template. Also preserve:
- All file paths that were read or modified
- All tool calls that failed (to prevent re-attempting)
- The current todo list state

#### D. Session Recovery via Progress Files (Claude Agent SDK Pattern)

Anthropic's agent harness uses a two-agent pattern:
1. **Initializer Agent**: Creates `init.sh`, `claude-progress.txt`, and an initial git commit
2. **Coding Agent**: Reads progress file on startup, makes incremental progress, updates file

This solves the problem of agents with fresh context windows either redoing work or prematurely declaring completion.

**Recommendation**: On each significant milestone (completed subagent task, file write, tool chain completion), update `PROGRESS.md` with:
```markdown
## Current State
- Last action: [what was just done]
- Files modified: [list]
- Pending tasks: [from todo list]
- Key decisions: [architectural choices made]

## Resume Instructions
[What the next agent invocation should do first]
```

#### E. Leave Failed Actions in Context (Manus Pattern)

Manus explicitly keeps failed tool calls and error messages in context rather than compacting them away. This implicitly updates the model's beliefs about what doesn't work, reducing repeated errors.

**Recommendation**: Modify the compaction strategy to always preserve:
- Failed tool calls with their error messages
- The agent's response analyzing the failure
- Any workaround decisions that followed

---

## 6. Tool Usage & Orchestration

### 6.1 Current State

DeerFlow assembles tools from 5 sources (config, MCP, built-in, subagent, community). MCP tools use lazy initialization with file mtime caching. Tool execution uses virtual path translation and sandbox isolation.

### 6.2 Best Practices from Industry

#### A. Three-Layer Tool Documentation (Claude Code Pattern)

Claude Code documents each tool at three levels:
1. **Schema-level description**: One-line purpose in the tool definition
2. **Tool-specific behavioral rules**: Dedicated prompt fragments (Bash alone has 47 fragments)
3. **Cross-cutting usage policies**: When to use which tool, preference cascades

**Recommendation**: Create tool usage guidance as separate prompt sections:
- Per-tool: When to use, when NOT to use, common patterns, error recovery
- Cross-cutting: Tool preference cascade (e.g., prefer `read_file` over `bash cat`)
- Anti-patterns: Common misuse patterns to avoid

#### B. Code-as-Tool-Call Pattern (open-ptc-agent / PTC)

The core innovation of open-ptc-agent: instead of individual JSON tool calls, the LLM writes Python code that orchestrates entire workflows in a sandbox. MCP tools are exposed as importable Python modules.

**Benefits**: 85-98% token reduction for data-heavy tasks because raw data stays in the sandbox.

**Recommendation**: For data-intensive workflows (ERP analysis, financial research), consider a `code_execution` tool that:
1. Runs Python in the sandbox
2. MCP tools are available as importable functions
3. Only summaries/results return to context
4. Full data persists in sandbox files for further processing

#### C. Think Tool for Strategic Reflection (open-ptc-agent Pattern)

A deliberate "scratchpad" tool that simply returns its input. Forces the model to pause and reason:

```python
@tool
def think(reflection: str) -> str:
    """Strategic reflection on progress and next steps."""
    return f"Reflection recorded: {reflection}"
```

The research subagent in open-ptc-agent is required to call `think` after every search, analyzing: what was found, what's missing, whether to continue or synthesize.

**Recommendation**: Add a `think` tool and mandate its use in the research planning workflow. This is lightweight to implement but significantly improves research depth.

#### D. Tool Error Recovery (LangGraph + OpenClaw Patterns)

LangGraph implements retry with backoff at the tool node level. OpenClaw has cascading recovery: retry -> fallback provider -> auth rotation -> thinking level fallback.

**Current gap**: DeerFlow's tool failures don't trigger retry logic. Dangling tool calls get generic placeholder messages.

**Recommendation**: Implement a `ToolRetryMiddleware` that:
1. Catches tool execution errors
2. For transient errors (network, timeout): retry with exponential backoff (max 3 attempts)
3. For auth errors: rotate credentials if available
4. For persistent errors: return a structured error message that helps the agent adapt
5. Track failure patterns to inform future tool selection

#### E. Context-Aware Tool Filtering (Manus Pattern)

Manus uses a context-aware state machine that manages tool availability using logit masking during decoding. Tools are enabled/disabled based on the current execution phase.

**Recommendation**: Implement phase-based tool filtering:
- **Planning phase**: Enable search/fetch tools, disable file write tools
- **Execution phase**: Enable all tools
- **Synthesis phase**: Enable file write tools, disable search tools
- **Review phase**: Enable read tools only

---

## 7. File & Document Processing

### 7.1 Current State

DeerFlow auto-converts uploaded files (PDF/PPT/Excel/Word -> Markdown) via markitdown. Files are stored in thread-isolated directories with virtual path mapping. The agent receives a file list with metadata.

### 7.2 Best Practices from Industry

#### A. Sandbox-Based Processing with Pre-Installed Libraries (open-ptc-agent Pattern)

open-ptc-agent pre-installs data science libraries in the sandbox:
```
openpyxl, xlrd, python-docx, pypdf, beautifulsoup4, lxml, pyyaml,
pandas, numpy, scipy, scikit-learn, matplotlib, seaborn, plotly,
pillow, opencv-python-headless, scikit-image
```

This enables the agent to process files programmatically rather than relying on pre-conversion.

**Recommendation**: Ensure the sandbox has common data processing libraries pre-installed. For complex documents (multi-sheet Excel, form-heavy PDFs), programmatic processing in the sandbox is more flexible than static conversion.

#### B. Multi-Format Media Understanding (OpenClaw Pattern)

OpenClaw has a comprehensive media processing pipeline with provider-based fallback chains:
- **Audio**: Sherpa-ONNX -> Whisper.cpp -> Whisper -> API providers
- **Image**: Active model -> Agent defaults -> Gemini CLI -> API providers
- **Video**: Similar cascade with specialized providers
- **Links**: URL content extraction with readability optimization

**Recommendation**: Extend file processing to handle:
1. **Audio transcription**: Integrate Whisper or similar for audio file support
2. **Image analysis**: Use vision-capable models for image understanding (already partially supported via ViewImageMiddleware)
3. **URL content extraction**: Add web fetch with readability extraction for research tasks
4. **Structured data extraction**: For CSVs/Excel, extract schema information (column names, types, sample rows) rather than full content

#### C. Data-First-Then-Process Pattern (open-ptc-agent)

The open-ptc-agent enforces a strict workflow for data processing:
1. Call tool / fetch data
2. **Dump raw result to file immediately** (never process in-memory only)
3. Inspect structure
4. Extract what you need
5. Return only summary to context

**Recommendation**: Add this pattern to the system prompt for data-heavy tasks. Raw data should always be persisted to the workspace before processing, enabling iterative inspection without re-fetching.

#### D. Head-Tail Truncation Strategy (OpenClaw Pattern)

When files exceed size limits, OpenClaw uses 70/20 truncation: 70% from the start, 20% from the end, with a marker between. This preserves both the document header/introduction and the conclusion/summary.

**Recommendation**: Apply head-tail truncation to:
- File content injection when documents exceed budget
- Tool result truncation (instead of simple head-cut)
- Memory context when approaching limits

---

## 8. Multi-Agent Architecture

### 8.1 Current State

DeerFlow has a supervisor pattern with the lead agent delegating to `general-purpose` and `bash` subagents. Concurrency is controlled via per-user semaphores (max 3), with batch processing for >3 tasks (clamped to [2,4] per response). Subagents cannot spawn further subagents.

### 8.2 Best Practices from Industry

#### A. Specialized Subagent Types (Claude Code + open-ptc-agent Pattern)

Claude Code defines specialized agents with tiered capabilities:

| Agent | Capability | Model | Use Case |
|---|---|---|---|
| Explore | Read-only, fast | Haiku | Quick codebase navigation |
| Plan | Read-only + plan file | Full model | Architecture design |
| Task | Full capabilities | Full model | Autonomous implementation |
| Research | Search + think only | Configurable | Web research |

open-ptc-agent separates:
- **Research subagent**: Tavily search + think tool only (stateless)
- **General-purpose subagent**: Full sandbox + MCP + filesystem (stateful)

**Recommendation**: Expand the subagent registry with specialized types:

```python
SUBAGENT_REGISTRY = {
    "research": {  # NEW
        "tools": ["web_search", "web_fetch", "think"],
        "max_turns": 30,
        "prompt": "researcher.md.j2",
        "model": "fast"  # Can use lighter model
    },
    "analyst": {  # NEW
        "tools": ["read_file", "execute_code", "think"],
        "max_turns": 40,
        "prompt": "analyst.md.j2",
    },
    "general-purpose": {
        "tools": ALL_EXCEPT_TASK,
        "max_turns": 50,
    },
    "bash": {
        "tools": ["bash"],
        "max_turns": 20,
    },
}
```

#### B. Background Execution with Notification Loop (open-ptc-agent Pattern)

open-ptc-agent's `BackgroundSubagentOrchestrator` wraps the agent in a notification loop:
1. Agent calls `task()` -> immediately gets "Background subagent deployed: Task-1"
2. Agent continues working on other things
3. When background tasks complete, orchestrator re-invokes the agent with completion notification
4. Agent calls `task_output()` to retrieve results

**Recommendation**: Implement background subagent execution with:
- `task()` returns immediately with task ID
- `wait(task_ids)` blocks until specified tasks complete
- `task_output(task_id)` retrieves results
- Orchestrator re-invokes on completion with notification

This is more flexible than the current synchronous batching model.

#### C. Sub-Agent Lifecycle Management (OpenClaw Pattern)

OpenClaw maintains a full lifecycle tracker for spawned agents:
- Registration, completion tracking, steering (redirecting running agents)
- Cascade kill for recursive termination
- Persistence to disk with orphan reconciliation
- 60-second garbage collection sweep

**Recommendation**: Add lifecycle management:
1. **Steering**: Ability to send directive messages to running subagents
2. **Cancellation**: Cascade kill when parent task is cancelled
3. **Persistence**: Save subagent state to disk for recovery after crashes

#### D. Context Summary Passing to Subagents

**Current gap**: Subagents inherit sandbox and thread data but lack awareness of what the parent has already explored. This leads to redundant work.

**Recommendation**: When spawning a subagent, include a context summary:
```python
task(
    description="Research X",
    prompt="Find details about X",
    context_summary="Parent has already found: [key findings]. "
                    "Avoid searching for: [already explored topics]. "
                    "Focus on: [specific gaps].",
    subagent_type="research"
)
```

#### E. Multi-Agent Coordination Models

Based on the cross-cutting analysis, four dominant patterns exist:

| Pattern | Best For | Framework Example |
|---|---|---|
| **Conversational (debate)** | Problems improved by critique | AutoGen/AG2 |
| **Role-based (coordinator + specialists)** | Team-structured workflows | CrewAI |
| **Graph-based (explicit state flow)** | Complex workflows needing control | LangGraph |
| **Handoff (delegation chain)** | Clear specialist routing | OpenAI Agents SDK |

**Recommendation**: DeerFlow currently uses the role-based pattern. For deep research specifically, consider adding a graph-based sub-workflow:

```
Plan -> [Parallel Research Tasks] -> Synthesize -> Self-Critique -> Final Output
```

---

## 9. Deep Research Capabilities

### 9.1 Current State

DeerFlow delegates research to `general-purpose` subagents with web search tools (Tavily, Jina, Firecrawl). There is no structured research planning, no citation grounding, no multi-pass synthesis, and no think-after-search loop.

### 9.2 Research Pipeline Architecture

Based on patterns from all analyzed systems, here is a recommended deep research pipeline:

#### Phase 1: Planning

**Perplexity pattern**: Separate planning from execution. Create an explicit step-by-step research plan.

**Gemini pattern**: Determine which sub-questions can be tackled in parallel vs. sequentially.

**Recommendation**: Before executing any search, the agent should:
1. Decompose the research question into 3-7 sub-questions
2. Identify dependencies between sub-questions
3. Write the plan to `PLAN.md`
4. Assign sub-questions to parallel or sequential execution

#### Phase 2: Research Execution

**open-ptc-agent pattern**: Mandatory think-after-search loop with explicit stop conditions:
- Can answer comprehensively
- Have 3+ relevant sources
- Last 2 searches yield similar content (saturation)

**Calibrated budgets**: Simple queries: 2-3 searches. Complex: up to 5. Beyond 5: synthesize with available information.

**Recommendation**: Create a `research` subagent type with:
1. `web_search` + `web_fetch` + `think` tools only
2. Mandatory `think()` call after every search
3. Explicit stop conditions in the prompt
4. Progress tracking via notes written to workspace files
5. Citation collection (source URL, title, key quote for each finding)

#### Phase 3: Synthesis

**Gemini pattern**: Multiple passes of self-critique. The system evaluates information, identifies themes and inconsistencies, and structures the report.

**Perplexity pattern**: Score citations as full support (1.0), partial (0.5), or none (0.0).

**Recommendation**: After all research subagents complete:
1. Lead agent reads all research notes from workspace
2. First pass: Draft synthesis with inline citations
3. Second pass: Self-critique (check for gaps, contradictions, unsupported claims)
4. Third pass: Final output with structured citations

#### Phase 4: Citation & Verification

**Recommendation**: Implement a citation system:

```markdown
## Findings

The market grew 15% year-over-year [1]. However, regional
variations were significant, with Asia-Pacific showing 23%
growth [2] while Europe contracted 2% [3].

## Sources

[1] "Market Analysis Report 2025" - https://example.com/report
    Relevance: High | Access date: 2026-02-27
[2] "APAC Growth Trends" - https://example.com/apac
    Relevance: High | Access date: 2026-02-27
[3] "European Market Overview" - https://example.com/europe
    Relevance: Medium | Access date: 2026-02-27
```

### 9.3 Research Quality Benchmarks

From Perplexity's DRACO benchmark (100 tasks, ~40 criteria per task), evaluation covers:
- **Factual accuracy** (~50% of criteria)
- **Breadth/depth of analysis** (~25%)
- **Presentation quality** (~15%)
- **Citation of primary sources** (~10%)

Even leading systems achieve under 68% on comprehensive benchmarks. The main failure modes are:
1. Missing citations for factual claims
2. Insufficient depth on complex sub-topics
3. Failing to identify contradictory evidence
4. Not citing primary sources (citing secondary summaries instead)

### 9.4 Research-Specific Prompt Section

Add to the system prompt when research mode is active:

```markdown
## Deep Research Workflow

When conducting deep research:

1. **Plan first**: Decompose into 3-7 sub-questions. Write plan to PLAN.md.
2. **Search with purpose**: For each sub-question, search with specific queries.
   After EVERY search, call think() to assess:
   - What did I find?
   - What gaps remain?
   - Should I search more or synthesize?
3. **Stop conditions**: Stop searching when:
   - You can answer the sub-question comprehensively
   - You have 3+ relevant, corroborating sources
   - Last 2 searches yielded similar content
4. **Write notes**: After each sub-question, write findings to NOTES.md.
5. **Synthesize**: After all sub-questions are answered:
   - Draft: Combine findings with inline citations
   - Critique: Check for gaps, contradictions, unsupported claims
   - Finalize: Produce structured output with citation list
6. **Cite everything**: Every factual claim needs a source reference.
```

---

## 10. Implementation Priority Matrix

### Tier 1: High Impact, Moderate Effort (Implement First)

| # | Improvement | Key Technique | Effort | Expected Impact |
|---|---|---|---|---|
| 1 | Selective tool result compaction | Replace stale results with compact markers | 2-3 days | 30-40% context savings |
| 2 | Think tool for reflection | Simple tool returning input | 1 day | Significant research quality improvement |
| 3 | Structured compaction template | 5-section summary format | 1-2 days | Better context recovery |
| 4 | Research subagent type | Specialized tools + think-after-search | 2-3 days | Deep research capability |
| 5 | Attention anchoring via todo rewrite | Append todos at context end | 1 day | Reduced objective drift |
| 6 | Context summary for subagents | Pass parent findings to children | 1 day | Reduced redundant work |

### Tier 2: High Impact, Higher Effort (Implement Second)

| # | Improvement | Key Technique | Effort | Expected Impact |
|---|---|---|---|---|
| 7 | File-based state externalization | PLAN.md + NOTES.md + PROGRESS.md | 3-4 days | Multi-session capability |
| 8 | Background subagent execution | Async tasks with notification loop | 4-5 days | Better parallelism |
| 9 | Progressive tool discovery | Summary-only injection + on-demand schemas | 3-4 days | Token savings on large tool sets |
| 10 | Three-layer context management | History limiting + result truncation + guard | 4-5 days | Robust context management |
| 11 | Citation grounding system | Source tracking + citation formatting | 3-4 days | Research output quality |
| 12 | Modular prompt composition | Jinja2 fragments + includes | 3-4 days | Maintainability |

### Tier 3: Moderate Impact, Variable Effort (Implement As Needed)

| # | Improvement | Key Technique | Effort | Expected Impact |
|---|---|---|---|---|
| 13 | KV-cache optimization | Stable prefixes, append-only, breakpoints | 2-3 days | Cost reduction (up to 10x) |
| 14 | Tool error recovery/retry | Middleware with backoff + fallback | 3-4 days | Reliability |
| 15 | Hybrid memory search | Vector + BM25 + temporal decay + MMR | 5-7 days | Memory retrieval quality |
| 16 | Multi-pass synthesis | Draft -> critique -> finalize | 2-3 days | Output quality |
| 17 | Phase-based tool filtering | Enable/disable tools by execution phase | 2-3 days | Reduced tool confusion |
| 18 | Code execution tool | Python in sandbox with MCP as imports | 5-7 days | Data processing capability |
| 19 | Head-tail truncation | 70/20 split for file/result truncation | 1-2 days | Better truncated content |
| 20 | Subagent steering | Send directives to running subagents | 2-3 days | Dynamic coordination |

### Quick Wins (< 1 day each)

1. Add `think` tool (trivial implementation, high research quality impact)
2. Update compaction prompt to use 5-section template
3. Add "Current Focus" to todo list middleware output
4. Preserve failed tool calls during compaction
5. Add citation rules section to system prompt

---

## 11. Sources & References

### Primary Sources (Mandated)

1. **open-ptc-agent** -- https://github.com/Chen-zexi/open-ptc-agent
   Programmatic Tool Calling pattern, Jinja2 prompt composition, progressive tool discovery, think-after-search, background subagent orchestration

2. **OpenClaw** -- https://github.com/openclaw/openclaw
   Three-layer context management, hybrid memory search with MMR, sub-agent lifecycle management, media understanding pipeline, budget-aware prompt composition

3. **Anthropic Context Engineering Guide** -- https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
   Context rot concept, attention budget, compaction patterns, note-taking memory, sub-agent architectures, tool design principles, just-in-time context

4. **Claude Code System Prompts** -- https://github.com/Piebald-AI/claude-code-system-prompts
   Modular prompt composition (223 fragments), instruction intensity hierarchy, three-layer tool documentation, four-tier memory architecture, plan mode workflow

### Secondary Sources (Researched)

5. **Manus AI** -- https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus
   KV-cache optimization, three-file state system, attention anchoring, context-aware state machine, PDCA cycle

6. **OpenAI Deep Research** -- RL-trained ReAct loops, clarification pipeline, background execution
7. **Perplexity / DRACO Benchmark** -- Sequential plan execution, citation scoring, research quality evaluation
8. **Google Gemini Deep Research** -- Async task manager, multi-pass self-critique, 1M token context + RAG
9. **Grok/xAI** -- Multi-agent internal architecture (4-16 agents), 2M token context
10. **LangGraph** -- Reducer-driven state, checkpointing, scatter-gather multi-agent
11. **CrewAI** -- Role-based crews, event-driven Flows, hierarchical process
12. **AutoGen / Microsoft Agent Framework** -- Conversable agents, YAML declarative definitions
13. **Claude Agent SDK** -- Two-agent harness, progress file pattern, hooks system
14. **OpenAI Codex** -- Native compaction, sandboxed execution, multi-agent command center
15. **DSPy** -- Declarative signatures, automatic prompt optimization
16. **OpenAI Agents SDK** -- Handoffs, guardrails, tracing primitives
