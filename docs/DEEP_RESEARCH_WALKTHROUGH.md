# Thinktank.ai Deep Research: Complete System Walkthrough

A comprehensive code-level walkthrough of how the Thinktank.ai backend agent conducts deep research — from user input through the entire system to final output.

---

## 1. High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              NGINX (port 2026)                             │
│   /api/langgraph/* ──► LangGraph    /api/* ──► Gateway    / ──► Frontend   │
└────────┬───────────────────────────────────────┬───────────────────┬────────┘
         │                                       │                   │
         ▼                                       ▼                   ▼
┌─────────────────┐                 ┌──────────────────┐   ┌─────────────────┐
│  LangGraph Srvr │                 │   Gateway API    │   │  Next.js Front  │
│   (port 2024)   │                 │   (port 8001)    │   │   (port 3000)   │
│                 │                 │                  │   │                 │
│ Registers graph:│                 │ Routers:         │   │ Chat UI         │
│ "lead_agent" =  │                 │  /api/models     │   │ File upload     │
│ make_lead_agent │                 │  /api/mcp        │   │ Artifact viewer │
│                 │                 │  /api/skills     │   │ SSE listener    │
└────────┬────────┘                 │  /api/memory     │   └─────────────────┘
         │                          │  /api/uploads    │
         │                          │  /api/artifacts  │
         │                          └──────────────────┘
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        make_lead_agent(config)                             │
│                                                                            │
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────┐  ┌───────────┐  │
│  │ create_chat_ │  │ get_available_   │  │  _build_     │  │ apply_    │  │
│  │ model()      │  │ tools()          │  │ middlewares() │  │ prompt_   │  │
│  │              │  │                  │  │              │  │ template()│  │
│  └──────┬───────┘  └────────┬─────────┘  └──────┬───────┘  └─────┬─────┘  │
│         │                   │                    │                │        │
│         ▼                   ▼                    ▼                ▼        │
│    LLM Instance       Tool List           Middleware Chain   System Prompt │
│                                                                            │
│  ════════════════════════════════════════════════════════════════════════   │
│                         create_agent(...)                                  │
│                    Returns a LangGraph CompiledGraph                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. The Entry Point: `langgraph.json` → `make_lead_agent`

**File:** `langgraph.json`

The LangGraph server loads one graph: `"lead_agent": "src.agents:make_lead_agent"`. When a user sends a message, LangGraph resolves this path, imports `make_lead_agent`, and calls it with a `RunnableConfig` containing runtime settings (`thinking_enabled`, `model_name`, `is_plan_mode`, `subagent_enabled`, `max_concurrent_subagents`).

**File:** `src/agents/lead_agent/agent.py`

```
┌──────────────────────────────────────────────────────┐
│             make_lead_agent(config)                  │
│                                                      │
│  1. Extract runtime flags from config.configurable:  │
│     • thinking_enabled  (bool, default True)         │
│     • model_name        (str or None)                │
│     • is_plan_mode      (bool, default False)        │
│     • subagent_enabled  (bool, default False)        │
│     • max_concurrent    (int, default 3)             │
│                                                      │
│  2. Call create_agent(                               │
│       model   = create_chat_model(name, thinking),   │
│       tools   = get_available_tools(model, subagent),│
│       middle  = _build_middlewares(config),           │
│       system  = apply_prompt_template(...),           │
│       schema  = ThreadState                          │
│     )                                                │
│                                                      │
│  Returns ──► LangGraph CompiledGraph                 │
└──────────────────────────────────────────────────────┘
```

### Key Class/Function

- **`make_lead_agent(config: RunnableConfig) → CompiledGraph`** — The factory function registered with LangGraph. It is called on every new thread/invocation. It assembles the four pillars of the agent (model, tools, middlewares, prompt) and returns a compiled graph. Input: `RunnableConfig` dict with `configurable` keys. Output: a runnable agent graph.

---

## 3. The Model Factory

**File:** `src/models/factory.py`

```
┌─────────────────────────────────────────────────────────────────┐
│           create_chat_model(name, thinking_enabled)             │
│                                                                 │
│  1. Load config.yaml via get_app_config()                       │
│  2. Find ModelConfig by name (or use first model as default)    │
│  3. Resolve the Python class via reflection:                    │
│       resolve_class(model_config.use, BaseChatModel)            │
│       e.g. "langchain_openai:ChatOpenAI" → ChatOpenAI class    │
│  4. Dump model settings, excluding metadata fields              │
│  5. Validate api_key (fail fast if unresolved $ENV_VAR)         │
│  6. If thinking_enabled AND model supports it:                  │
│       Merge when_thinking_enabled overrides into settings       │
│  7. Instantiate: model_class(**settings)                        │
│                                                                 │
│  Returns ──► BaseChatModel instance                             │
└─────────────────────────────────────────────────────────────────┘
```

### Key Function

- **`create_chat_model(name, thinking_enabled) → BaseChatModel`** — The model factory. It reads `config.yaml`, resolves the model's Python class via dynamic import (`resolve_class`), validates API keys, applies thinking-mode overrides, and returns an instantiated LLM. Input: model name string + thinking flag. Output: a LangChain `BaseChatModel`.

---

## 4. System Prompt Generation

**File:** `src/agents/lead_agent/prompt.py`

This is how the agent's "personality" and instructions are assembled:

```
┌─────────────────────────────────────────────────────────────────────┐
│           apply_prompt_template(subagent_enabled,                   │
│                                 max_concurrent, thinking_enabled)   │
│                                                                     │
│  ┌─────────────────────┐                                            │
│  │ _get_memory_context()│  ← Reads memory.json, formats top 15     │
│  │                     │    facts + user/history context            │
│  │                     │    Wraps in <memory>...</memory> tags      │
│  └──────────┬──────────┘                                            │
│             │                                                       │
│  ┌──────────▼──────────┐                                            │
│  │ get_skills_prompt_  │  ← Loads enabled skills from               │
│  │ section()           │    extensions_config.json, lists them      │
│  │                     │    in <skill_system> tags with locations    │
│  └──────────┬──────────┘                                            │
│             │                                                       │
│  ┌──────────▼──────────┐                                            │
│  │ _build_subagent_    │  ← If subagent_enabled: builds the        │
│  │ section(n)          │    <subagent_system> block with examples,  │
│  │                     │    concurrency limits, orchestration rules │
│  └──────────┬──────────┘                                            │
│             │                                                       │
│  ┌──────────▼──────────────────────────────────────────────┐        │
│  │  SYSTEM_PROMPT_TEMPLATE.format(                         │        │
│  │    memory_context     = <memory>facts+context</memory>, │        │
│  │    skills_section     = <skill_system>...</skill_system>,│        │
│  │    subagent_section   = <subagent_system>...</>,         │        │
│  │    subagent_reminder  = orchestrator reminder,           │        │
│  │    subagent_thinking  = decomposition check guidance,    │        │
│  │  )                                                       │        │
│  │  + <current_date>2025-06-15, Sunday</current_date>      │        │
│  └─────────────────────────────────────────────────────────┘        │
│                                                                     │
│  The final prompt includes these sections:                          │
│    <role>              ← Identity: "Thinktank.ai 2.0"                   │
│    <memory>            ← Persistent user facts & context            │
│    <thinking_style>    ← How to reason before acting                │
│    <clarification_system> ← When/how to ask for clarification      │
│    <skill_system>      ← Available skills with paths                │
│    <subagent_system>   ← Orchestration rules (if enabled)           │
│    <working_directory> ← File path conventions                      │
│    <response_style>    ← Formatting rules                           │
│    <citations>         ← Citation format                            │
│    <critical_reminders>← Top-priority rules                         │
│    <current_date>      ← Today's date                               │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Functions

- **`apply_prompt_template(subagent_enabled, max_concurrent, thinking_enabled) → str`** — The master prompt assembler. Gathers memory context, skills listing, and subagent instructions, then formats them into the final system prompt string. Output: the complete system prompt.

- **`_get_memory_context() → str`** — Reads `memory.json` via `get_memory_data()`, formats facts and user context via `format_memory_for_injection()`, and wraps in `<memory>` tags. Returns empty string if disabled.

- **`get_skills_prompt_section() → str`** — Calls `load_skills(enabled_only=True)` to discover enabled skills, formats them into a `<skill_system>` block listing name, description, and file path for each.

- **`_build_subagent_section(n) → str`** — Generates the `<subagent_system>` prompt section with orchestration rules, concurrency limits (max `n` per turn), batch examples, and counter-examples.

---

## 5. Tool Assembly

**File:** `src/tools/tools.py`

```
┌────────────────────────────────────────────────────────────────────────┐
│        get_available_tools(groups, include_mcp, model_name,           │
│                            subagent_enabled) → list[BaseTool]        │
│                                                                       │
│  Step 1: Config-defined tools                                         │
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │ For each tool in config.yaml tools[]:                        │     │
│  │   resolve_variable(tool.use, BaseTool)                       │     │
│  │   e.g. "src.community.tavily:web_search_tool" → web_search  │     │
│  │   Filter by tool.group if groups param provided              │     │
│  └──────────────────────────────────────────────────────────────┘     │
│                                                                       │
│  Step 2: MCP tools (if include_mcp=True)                              │
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │ ExtensionsConfig.from_file()  ← re-reads extensions_config  │     │
│  │ get_cached_mcp_tools()        ← lazy init + mtime staleness │     │
│  │   ├─ If cache stale: reset + re-initialize from servers     │     │
│  │   └─ Returns cached list of MCP-adapted LangChain tools     │     │
│  └──────────────────────────────────────────────────────────────┘     │
│                                                                       │
│  Step 3: Built-in tools                                               │
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │ Always included:                                             │     │
│  │   • present_files  ← Make output files visible to user      │     │
│  │   • ask_clarification ← Request user input (intercepted)    │     │
│  │                                                              │     │
│  │ Conditionally included:                                      │     │
│  │   • task           ← Subagent delegation (if subagent_enab) │     │
│  │   • view_image     ← Image viewing (if model supports_vision│     │
│  └──────────────────────────────────────────────────────────────┘     │
│                                                                       │
│  Final: loaded_tools + builtin_tools + mcp_tools                      │
└────────────────────────────────────────────────────────────────────────┘
```

### Key Function

- **`get_available_tools(groups, include_mcp, model_name, subagent_enabled) → list[BaseTool]`** — Assembles the complete tool list from three sources: (1) config-defined tools loaded via reflection, (2) MCP tools from enabled servers, (3) built-in tools. Conditionally adds `task` tool for subagent delegation and `view_image` for vision models.

---

## 6. The Middleware Chain

**File:** `src/agents/lead_agent/agent.py` → `_build_middlewares(config)`

The middleware chain wraps the agent's execution. Each middleware can intercept `before_agent`, `after_agent`, `after_model`, and `wrap_tool_call` hooks.

```
 User Message Arrives
         │
         ▼
 ┌───────────────────────────────────────────────────────────────────┐
 │                    BEFORE_AGENT PHASE                            │
 │  (Executed in order, each can modify state before LLM sees it)  │
 │                                                                  │
 │  ① ThreadDataMiddleware.before_agent                             │
 │     • Reads thread_id from runtime.context                      │
 │     • Computes paths: workspace, uploads, outputs                │
 │     • Returns: {thread_data: {workspace_path, uploads_path,      │
 │                                outputs_path}}                    │
 │                                                                  │
 │  ② UploadsMiddleware.before_agent                                │
 │     • Scans uploads dir for NEW files (not previously shown)    │
 │     • Prepends <uploaded_files> listing to last HumanMessage    │
 │     • Returns: {uploaded_files: [...], messages: [...]}          │
 │                                                                  │
 │  ③ SandboxMiddleware.before_agent                                │
 │     • If lazy_init=True (default): does nothing here            │
 │     • Sandbox acquired on first tool call instead               │
 │                                                                  │
 │  ④ DanglingToolCallMiddleware.before_agent                       │
 │     • Finds AIMessages with tool_calls lacking ToolMessages     │
 │     • Injects placeholder ToolMessages to prevent LLM confusion │
 │                                                                  │
 │  ⑤ SummarizationMiddleware.before_agent  (if enabled)            │
 │     • Checks token/message triggers                             │
 │     • Summarizes old messages, keeps recent ones                 │
 │                                                                  │
 │  ⑥ TodoListMiddleware.before_agent  (if plan_mode)               │
 │     • Injects write_todos tool and system instructions          │
 │                                                                  │
 │  ⑦ TitleMiddleware.before_agent                                  │
 │     • (Generates title after first exchange)                    │
 │                                                                  │
 │  ⑧ MemoryMiddleware  (no-op in before_agent)                     │
 │                                                                  │
 │  ⑨ ViewImageMiddleware.before_agent  (if vision model)           │
 │     • Finds viewed_images in state                              │
 │     • Injects base64 image data into messages before LLM call   │
 │                                                                  │
 │  ⑩ SubagentLimitMiddleware  (no-op in before_agent)              │
 │                                                                  │
 │  ⑪ ClarificationMiddleware  (no-op in before_agent)              │
 └──────────────────────────────────┬────────────────────────────────┘
                                    │
                                    ▼
                        ┌───────────────────┐
                        │   LLM INVOCATION  │
                        │   model.invoke()  │
                        │                   │
                        │ Input:            │
                        │  • System prompt  │
                        │  • Message history│
                        │  • Tool schemas   │
                        │                   │
                        │ Output:           │
                        │  • AIMessage with │
                        │    content and/or │
                        │    tool_calls[]   │
                        └────────┬──────────┘
                                 │
                                 ▼
 ┌───────────────────────────────────────────────────────────────────┐
 │                     AFTER_MODEL PHASE                            │
 │                                                                  │
 │  ⑩ SubagentLimitMiddleware.after_model                           │
 │     • Counts "task" tool_calls in the AIMessage                 │
 │     • If count > max_concurrent (default 3):                    │
 │       Truncates excess task calls, keeps first N                │
 │     • Returns updated AIMessage with trimmed tool_calls         │
 └──────────────────────────────────┬────────────────────────────────┘
                                    │
                                    ▼
 ┌───────────────────────────────────────────────────────────────────┐
 │                   TOOL EXECUTION PHASE                           │
 │                                                                  │
 │  For each tool_call in AIMessage.tool_calls[]:                  │
 │                                                                  │
 │  ⑪ ClarificationMiddleware.wrap_tool_call                        │
 │     • IF tool_call.name == "ask_clarification":                 │
 │       ├─ Formats question with icon and options                 │
 │       ├─ Creates ToolMessage with formatted question            │
 │       └─ Returns Command(goto=END) ← INTERRUPTS execution      │
 │     • ELSE: passes through to normal tool handler               │
 │                                                                  │
 │  Normal tool execution:                                          │
 │     • Sandbox tools: bash, ls, read_file, write_file, str_replace│
 │     • present_files: Returns Command with artifacts state update│
 │     • task: Launches subagent (see Section 8 below)             │
 │     • MCP tools: Forwarded to MCP server                        │
 │     • Community tools: web_search, web_fetch, image_search      │
 └──────────────────────────────────┬────────────────────────────────┘
                                    │
                                    ▼
 ┌───────────────────────────────────────────────────────────────────┐
 │                    AFTER_AGENT PHASE                             │
 │                                                                  │
 │  ⑧ MemoryMiddleware.after_agent                                  │
 │     • Filters messages: keeps only HumanMessages and            │
 │       AIMessages WITHOUT tool_calls (final responses)           │
 │     • Queues filtered conversation to MemoryUpdateQueue         │
 │     • Queue debounces (30s), then background thread runs        │
 │       MemoryUpdater.update_memory() using an LLM call to       │
 │       extract facts and update memory.json atomically           │
 └──────────────────────────────────┬────────────────────────────────┘
                                    │
                                    ▼
                          Response to User
```

### Key Classes

- **`ThreadDataMiddleware`** — Creates per-thread directory paths. Input: `thread_id` from runtime context. Output: state update with `thread_data` containing `workspace_path`, `uploads_path`, `outputs_path`.

- **`UploadsMiddleware`** — Detects newly uploaded files and prepends their listing to the user's message. Input: thread state + thread_id. Output: modified messages with `<uploaded_files>` prepended.

- **`SandboxMiddleware`** — Manages sandbox lifecycle. With `lazy_init=True` (default), defers acquisition until the first tool call. Input: thread_id. Output: `{sandbox: {sandbox_id}}` state.

- **`SubagentLimitMiddleware`** — Enforces max concurrent subagent calls. Runs in `after_model` hook, truncates excess `task` tool_calls. Input: AIMessage with tool_calls. Output: AIMessage with at most N task calls.

- **`ClarificationMiddleware`** — Intercepts `ask_clarification` tool calls, formats the question, and returns `Command(goto=END)` to interrupt the agent loop and present the question to the user.

- **`MemoryMiddleware`** — After each agent run, queues the conversation for background memory extraction via LLM.

---

## 7. ThreadState — The Agent's Shared Memory

**File:** `src/agents/thread_state.py`

```
┌─────────────────────────────────────────────────────────────────┐
│                     ThreadState(AgentState)                     │
│                                                                 │
│  Inherited from AgentState:                                     │
│    messages: list[BaseMessage]   ← Full conversation history    │
│                                                                 │
│  Added fields:                                                  │
│    sandbox:        SandboxState     {sandbox_id: str}           │
│    thread_data:    ThreadDataState  {workspace_path,            │
│                                      uploads_path,              │
│                                      outputs_path}              │
│    title:          str              Auto-generated thread title  │
│    artifacts:      list[str]        Reducer: merge_artifacts()  │
│                                     (deduplicates file paths)   │
│    todos:          list             TodoList items               │
│    uploaded_files: list[dict]       Files from UploadsMiddleware │
│    viewed_images:  dict             Reducer: merge_viewed_images │
│                                     (path → {base64, mime_type})│
└─────────────────────────────────────────────────────────────────┘
```

The `Annotated[..., reducer]` pattern means LangGraph uses custom merge logic when multiple state updates target the same field — critical for `artifacts` (deduplicate) and `viewed_images` (merge or clear).

---

## 8. The Subagent System (Deep Research Orchestration)

This is the core of "deep research." When the lead agent receives a complex question, the system prompt instructs it to decompose the task and launch parallel subagents.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    SUBAGENT EXECUTION FLOW                              │
│                                                                         │
│  Lead Agent (LLM response)                                              │
│    │                                                                    │
│    │  AIMessage.tool_calls = [                                          │
│    │    {name: "task", args: {description, prompt, subagent_type}},     │
│    │    {name: "task", args: {description, prompt, subagent_type}},     │
│    │    {name: "task", args: {description, prompt, subagent_type}},     │
│    │  ]                                                                 │
│    │                                                                    │
│    ▼  SubagentLimitMiddleware.after_model (truncate if > max)           │
│    │                                                                    │
│    ▼  For each task tool_call (executed in parallel):                   │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    task_tool() execution                         │   │
│  │                                                                  │   │
│  │  1. get_subagent_config(subagent_type)                          │   │
│  │     └─ Looks up BUILTIN_SUBAGENTS registry                     │   │
│  │        • "general-purpose" → GENERAL_PURPOSE_CONFIG             │   │
│  │        • "bash"            → BASH_AGENT_CONFIG                  │   │
│  │                                                                  │   │
│  │  2. Inject skills_section into subagent's system_prompt         │   │
│  │                                                                  │   │
│  │  3. Extract parent context from runtime:                        │   │
│  │     • sandbox_state  (reuse parent's sandbox)                   │   │
│  │     • thread_data    (share directory paths)                    │   │
│  │     • thread_id      (for sandbox access)                       │   │
│  │     • parent_model   (for model inheritance)                    │   │
│  │     • trace_id       (for distributed tracing)                  │   │
│  │                                                                  │   │
│  │  4. get_available_tools(subagent_enabled=False)                 │   │
│  │     └─ Same tools as parent MINUS the "task" tool               │   │
│  │                                                                  │   │
│  │  5. SubagentExecutor(config, tools, parent_model, ...)          │   │
│  │     └─ _filter_tools: applies allowed/disallowed lists          │   │
│  │                                                                  │   │
│  │  6. executor.execute_async(prompt, task_id=tool_call_id)        │   │
│  │     └─ Submits to _scheduler_pool → _execution_pool             │   │
│  │                                                                  │   │
│  │  7. POLLING LOOP (blocking the tool call):                      │   │
│  │     writer(task_started)                                        │   │
│  │     while True:                                                 │   │
│  │       result = get_background_task_result(task_id)              │   │
│  │       if new AI messages: writer(task_running, messages)        │   │
│  │       if COMPLETED: writer(task_completed) → return result      │   │
│  │       if FAILED:    writer(task_failed)    → return error       │   │
│  │       if TIMED_OUT: writer(task_timed_out) → return timeout     │   │
│  │       sleep(5)  ← poll every 5 seconds                         │   │
│  │       if polls > 192 (16 min): timeout safety net               │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  Inside execute_async → run_task → execute():                           │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │            SubagentExecutor.execute(task)                        │   │
│  │                                                                  │   │
│  │  1. _create_agent():                                            │   │
│  │     • create_chat_model(name=inherited, thinking=False)         │   │
│  │     • Minimal middlewares: [ThreadDataMiddleware, SandboxMW]    │   │
│  │     • create_agent(model, tools, middleware, system_prompt,     │   │
│  │                    state_schema=ThreadState)                    │   │
│  │                                                                  │   │
│  │  2. _build_initial_state(task):                                 │   │
│  │     • messages: [HumanMessage(content=task)]                    │   │
│  │     • sandbox: parent's sandbox_state  (shared)                 │   │
│  │     • thread_data: parent's thread_data (shared)                │   │
│  │                                                                  │   │
│  │  3. agent.stream(state, config, context, stream_mode="values")  │   │
│  │     • Runs the subagent's own LangGraph loop                   │   │
│  │     • Subagent calls tools autonomously (bash, web_search...)  │   │
│  │     • Each AIMessage is captured into result.ai_messages[]     │   │
│  │     • Runs for up to max_turns (default 50)                    │   │
│  │                                                                  │   │
│  │  4. Extract last AIMessage.content as final result              │   │
│  │     • result.status = COMPLETED                                 │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  After ALL task tool_calls return results:                               │
│    Lead Agent receives all results in ToolMessages                       │
│    Lead Agent calls LLM again to SYNTHESIZE final answer                │
│    ──► Response to user                                                 │
└──────────────────────────────────────────────────────────────────────────┘
```

### Key Classes and Functions

- **`SubagentConfig`** (`src/subagents/config.py`) — Dataclass defining a subagent's identity: `name`, `description`, `system_prompt`, `tools` (allowlist), `disallowed_tools` (denylist), `model` ("inherit" or specific), `max_turns` (50), `timeout_seconds` (900). This is the blueprint.

- **`GENERAL_PURPOSE_CONFIG`** (`src/subagents/builtins/general_purpose.py`) — Config for the "general-purpose" subagent. Inherits all tools except `task`, `ask_clarification`, `present_files`. Gets a system prompt instructing it to complete tasks autonomously and return structured results. Max 50 turns.

- **`BASH_AGENT_CONFIG`** (`src/subagents/builtins/bash_agent.py`) — Config for the "bash" subagent. Limited to sandbox tools only (`bash`, `ls`, `read_file`, `write_file`, `str_replace`). Max 30 turns.

- **`SubagentExecutor`** (`src/subagents/executor.py`) — The execution engine. Constructor filters tools per config, resolves model name. `execute()` creates a fresh LangGraph agent, builds initial state with the task as a HumanMessage, streams execution, captures AI messages, and extracts the final result. `execute_async()` wraps this in a dual thread pool (scheduler + executor) with timeout support.

- **`task_tool()`** (`src/tools/builtins/task_tool.py`) — The `@tool("task")` function that the lead agent calls. It looks up the subagent config, injects skills, extracts parent context (sandbox, thread_data, model), creates a `SubagentExecutor`, launches async execution, then polls every 5s while streaming SSE events (`task_started`, `task_running`, `task_completed`).

- **`get_subagent_config(name) → SubagentConfig`** (`src/subagents/registry.py`) — Registry lookup. Maps "general-purpose" and "bash" to their config dataclasses.

---

## 9. Sandbox Execution (Tool Calls)

**File:** `src/sandbox/tools.py`

When the agent (or subagent) calls tools like `bash`, `read_file`, etc., the sandbox system handles execution:

```
┌─────────────────────────────────────────────────────────────────────┐
│               SANDBOX TOOL EXECUTION FLOW                          │
│                                                                     │
│  Agent calls bash(command="/mnt/user-data/workspace/run.py")       │
│    │                                                                │
│    ▼                                                                │
│  bash_tool(runtime, description, command)                          │
│    │                                                                │
│    ├── ensure_sandbox_initialized(runtime)                          │
│    │     • Check runtime.state["sandbox"]["sandbox_id"]            │
│    │     • If exists: provider.get(sandbox_id) → return Sandbox    │
│    │     • If not: provider.acquire(thread_id) → new sandbox_id   │
│    │       Store in runtime.state["sandbox"]                       │
│    │                                                                │
│    ├── ensure_thread_directories_exist(runtime)                     │
│    │     • If local sandbox: create workspace/uploads/outputs dirs │
│    │                                                                │
│    ├── is_local_sandbox(runtime)?                                   │
│    │     YES → replace_virtual_paths_in_command(command, thread_data)│
│    │            /mnt/user-data/workspace/run.py                    │
│    │            ──► .deer-flow/threads/{id}/user-data/workspace/... │
│    │                                                                │
│    └── sandbox.execute_command(translated_command)                   │
│          │                                                          │
│          ▼                                                          │
│    ┌─────────────────────────────┐                                  │
│    │   Sandbox (Abstract)        │                                  │
│    │                             │                                  │
│    │   Implementations:          │                                  │
│    │   • LocalSandbox            │                                  │
│    │     └─ subprocess.run()     │                                  │
│    │   • AioSandbox              │                                  │
│    │     └─ Docker container     │                                  │
│    └─────────────────────────────┘                                  │
│                                                                     │
│  Virtual Path System:                                               │
│    Agent sees:     /mnt/user-data/{workspace,uploads,outputs}      │
│    Physical path:  .deer-flow/threads/{thread_id}/user-data/...    │
│    Translation:    replace_virtual_path() + replace_virtual_paths_ │
│                    in_command()                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Functions

- **`ensure_sandbox_initialized(runtime) → Sandbox`** — Lazy sandbox acquisition. Checks if a sandbox already exists in state; if not, acquires one from the provider. Thread-safe.

- **`replace_virtual_paths_in_command(command, thread_data) → str`** — Regex-based path translator. Finds all `/mnt/user-data/...` patterns in a command string and replaces them with physical thread-specific paths. Only applies to local sandbox.

- **`bash_tool(runtime, description, command) → str`** — The `@tool("bash")` function. Acquires sandbox, translates paths, executes command, returns output.

- **`Sandbox`** (`src/sandbox/sandbox.py`) — Abstract base class with four methods: `execute_command`, `read_file`, `write_file`, `list_dir`. Implementations: `LocalSandbox` (subprocess on host) and `AioSandbox` (Docker).

---

## 10. The Memory System (Persistent Learning)

```
┌─────────────────────────────────────────────────────────────────────┐
│                     MEMORY LIFECYCLE                               │
│                                                                     │
│  During conversation:                                               │
│    MemoryMiddleware.after_agent()                                   │
│      │                                                              │
│      ├── Filter messages (keep only human + final AI responses)    │
│      └── queue.add(thread_id, filtered_messages)                   │
│            │                                                        │
│            ▼                                                        │
│    MemoryUpdateQueue (debounced, 30s wait)                          │
│      │  • Per-thread deduplication                                  │
│      │  • Background thread                                        │
│      │                                                              │
│      ▼                                                              │
│    MemoryUpdater.update_memory(messages, thread_id)                 │
│      │                                                              │
│      ├── get_memory_data()  ← cached read of memory.json          │
│      ├── format_conversation_for_update(messages)                  │
│      ├── Build prompt with MEMORY_UPDATE_PROMPT template           │
│      ├── model.invoke(prompt)  ← LLM extracts facts/context       │
│      ├── Parse JSON response                                       │
│      ├── _apply_updates():                                         │
│      │     • Update user sections (workContext, personalContext)   │
│      │     • Update history sections                               │
│      │     • Remove outdated facts                                 │
│      │     • Add new facts (filtered by confidence threshold)     │
│      │     • Enforce max_facts limit (keep highest confidence)    │
│      └── _save_memory_to_file()  ← atomic write (temp + rename)  │
│                                                                     │
│  At next conversation start:                                        │
│    apply_prompt_template() → _get_memory_context()                 │
│      │                                                              │
│      ├── get_memory_data()  ← cached read                         │
│      ├── format_memory_for_injection(data, max_tokens=2000)       │
│      └── Wraps in <memory>...</memory> tags in system prompt       │
│                                                                     │
│  memory.json structure:                                             │
│    {                                                                │
│      user: { workContext, personalContext, topOfMind },             │
│      history: { recentMonths, earlierContext, longTermBackground },│
│      facts: [{ id, content, category, confidence, createdAt }]    │
│    }                                                                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 11. End-to-End Walkthrough: A Deep Research Query

Let's trace what happens when a user asks: **"Why is Tencent's stock price declining?"** with subagent mode enabled.

```
 USER: "Why is Tencent's stock price declining?"
  │
  ▼
 LANGGRAPH SERVER receives message, calls make_lead_agent(config)
  │
  ├── config.configurable = {thinking_enabled: True, subagent_enabled: True,
  │                           max_concurrent_subagents: 3}
  │
  ├── create_chat_model("claude-sonnet-4-5", thinking=True)
  │     └── Resolves class, applies thinking overrides, returns LLM
  │
  ├── get_available_tools(subagent_enabled=True)
  │     └── [web_search, web_fetch, bash, ls, read_file, write_file,
  │          str_replace, present_files, ask_clarification, task, view_image]
  │
  ├── _build_middlewares(config)
  │     └── [ThreadData, Uploads, Sandbox, DanglingToolCall,
  │          Summarization?, TodoList?, Title, Memory, ViewImage?,
  │          SubagentLimit(3), Clarification]
  │
  └── apply_prompt_template(subagent_enabled=True, max_concurrent=3)
        └── System prompt includes <subagent_system> with orchestration rules
  │
  ▼
 AGENT GRAPH EXECUTES
  │
  ├── BEFORE_AGENT middlewares fire:
  │     ThreadData → computes paths
  │     Uploads → no new files
  │     Sandbox → lazy (skip)
  │     Others → pass through
  │
  ├── LLM INVOCATION #1
  │     System: "You are Thinktank.ai 2.0... <subagent_system>DECOMPOSE..."
  │     User: "Why is Tencent's stock price declining?"
  │
  │     LLM thinks: "3 sub-tasks → fits in 1 batch"
  │
  │     LLM returns AIMessage with tool_calls:
  │       [task(desc="Tencent financials",    prompt="...", type="general-purpose"),
  │        task(desc="Tencent news/regulation", prompt="...", type="general-purpose"),
  │        task(desc="Market/industry trends",  prompt="...", type="general-purpose")]
  │
  ├── AFTER_MODEL: SubagentLimitMiddleware
  │     3 task calls ≤ max 3 → no truncation
  │
  ├── TOOL EXECUTION (3 task calls in parallel):
  │
  │   ┌─────────────── SUBAGENT 1 ──────────────────┐
  │   │ task_tool("Tencent financials", prompt, GP)  │
  │   │  → SubagentExecutor(GP config, all tools)    │
  │   │  → execute_async(prompt)                     │
  │   │    → _scheduler_pool → _execution_pool       │
  │   │    → Creates fresh agent with GP system prompt│
  │   │    → Agent calls web_search("Tencent Q3...")  │
  │   │    → Agent calls web_fetch(earnings_url)      │
  │   │    → Agent synthesizes findings               │
  │   │    → Returns: "Revenue declined 8%..."        │
  │   │  → task_tool polls every 5s, sends SSE events│
  │   │  → Returns: "Task Succeeded. Result: ..."    │
  │   └──────────────────────────────────────────────┘
  │
  │   ┌─────────────── SUBAGENT 2 ──────────────────┐
  │   │ (Same pattern, researches news/regulation)   │
  │   │  → Returns: "Regulatory crackdown on..."     │
  │   └──────────────────────────────────────────────┘
  │
  │   ┌─────────────── SUBAGENT 3 ──────────────────┐
  │   │ (Same pattern, researches market trends)     │
  │   │  → Returns: "Tech sector selloff..."         │
  │   └──────────────────────────────────────────────┘
  │
  ├── 3 ToolMessages returned to lead agent
  │
  ├── LLM INVOCATION #2 (Synthesis)
  │     System: same system prompt
  │     History: user question + task calls + 3 results
  │
  │     LLM synthesizes all three research threads into
  │     a comprehensive analysis with citations
  │
  │     Returns: AIMessage with final answer (no tool_calls)
  │
  ├── AFTER_AGENT middlewares fire:
  │     MemoryMiddleware:
  │       Filters to [HumanMessage, final AIMessage]
  │       Queues for async memory update
  │       → 30s later: LLM extracts facts about Tencent discussion
  │       → Saves to memory.json
  │
  └── Response streamed to user via SSE
```

---

## 12. Summary Table of Key Classes and Functions

| Component | File | Signature | Role |
|---|---|---|---|
| `make_lead_agent` | `agents/lead_agent/agent.py` | `(config: RunnableConfig) → CompiledGraph` | Factory: assembles model + tools + middlewares + prompt into a LangGraph agent |
| `create_chat_model` | `models/factory.py` | `(name, thinking_enabled) → BaseChatModel` | Creates LLM instance from config via reflection |
| `apply_prompt_template` | `agents/lead_agent/prompt.py` | `(subagent_enabled, max_concurrent, thinking_enabled) → str` | Builds the complete system prompt with memory, skills, subagent rules |
| `get_available_tools` | `tools/tools.py` | `(groups, include_mcp, model_name, subagent_enabled) → list[BaseTool]` | Assembles all tools: config + MCP + built-in + conditional |
| `ThreadState` | `agents/thread_state.py` | `AgentState` subclass | Shared state schema with custom reducers for artifacts and images |
| `SubagentExecutor` | `subagents/executor.py` | `.execute(task) → SubagentResult` | Creates and runs a fresh agent for a delegated task |
| `task_tool` | `tools/builtins/task_tool.py` | `(runtime, description, prompt, subagent_type) → str` | Bridges lead agent → SubagentExecutor, handles async polling + SSE |
| `SubagentConfig` | `subagents/config.py` | Dataclass | Blueprint for a subagent (prompt, tools, model, limits) |
| `Sandbox` | `sandbox/sandbox.py` | Abstract class | Interface for command execution, file I/O |
| `bash_tool` | `sandbox/tools.py` | `(runtime, description, command) → str` | Executes bash via sandbox with path translation |
| `ensure_sandbox_initialized` | `sandbox/tools.py` | `(runtime) → Sandbox` | Lazy sandbox acquisition |
| `replace_virtual_paths_in_command` | `sandbox/tools.py` | `(command, thread_data) → str` | Translates `/mnt/user-data/...` to physical paths |
| `ClarificationMiddleware` | `middlewares/clarification_middleware.py` | `wrap_tool_call` | Intercepts ask_clarification, interrupts with `Command(goto=END)` |
| `SubagentLimitMiddleware` | `middlewares/subagent_limit_middleware.py` | `after_model` | Truncates excess task calls beyond max concurrent |
| `MemoryMiddleware` | `middlewares/memory_middleware.py` | `after_agent` | Queues conversation for async memory extraction |
| `MemoryUpdater` | `agents/memory/updater.py` | `.update_memory(messages, thread_id) → bool` | LLM-based memory extraction + atomic JSON persistence |
| `get_cached_mcp_tools` | `mcp/cache.py` | `() → list[BaseTool]` | Lazy-init MCP tools with mtime-based cache invalidation |

---

## 13. Architectural Insights

The three architectural pillars that make "deep research" work are:

1. **Subagent Orchestration** — The decompose-delegate-synthesize pattern, enforced by prompt engineering (the `<subagent_system>` block) and the `SubagentLimitMiddleware`. The lead agent acts as an orchestrator, breaking complex queries into parallel research threads, each handled by an autonomous subagent with its own tool-calling loop.

2. **Shared Sandbox** — Parent and child agents share the same filesystem via `thread_data` and `sandbox_state` passthrough. This means a subagent can write a file that the lead agent (or another subagent) can read, enabling collaborative workflows without message-passing overhead.

3. **Persistent Memory** — The memory system accumulates knowledge across conversations via async LLM-driven fact extraction. The `MemoryMiddleware` queues conversations, the `MemoryUpdater` extracts facts with confidence scores, and the next conversation's system prompt includes relevant facts in `<memory>` tags — enabling the agent to learn and personalize over time.
