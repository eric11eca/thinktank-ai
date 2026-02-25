# Thinktank-AI TODO List System: Complete Walkthrough

A comprehensive code-level walkthrough of how Thinktank-AI generates, manages, and completes TODO lists during deep research workflows — plus a detailed frontend UI plan for displaying and tracking them.

---

## 1. High-Level TODO System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          TODO SYSTEM OVERVIEW                              │
│                                                                            │
│  Frontend (Next.js)                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  User toggles "Plan Mode" ON                                        │  │
│  │  ──► Sends is_plan_mode: true in config.configurable                │  │
│  │  ──► Listens to SSE stream for "values" events with todos[] field   │  │
│  │  ──► Renders real-time TODO list widget                             │  │
│  └──────────────────────────────┬───────────────────────────────────────┘  │
│                                 │                                          │
│                      POST /api/langgraph/threads/{id}/runs/stream          │
│                                 │                                          │
│  Backend                        ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  make_lead_agent(config)                                            │  │
│  │    │                                                                │  │
│  │    ├── is_plan_mode = config.configurable.is_plan_mode  (True)      │  │
│  │    │                                                                │  │
│  │    ├── _build_middlewares(config)                                    │  │
│  │    │     └── _create_todo_list_middleware(is_plan_mode=True)         │  │
│  │    │           └── TodoListMiddleware(system_prompt, tool_desc)      │  │
│  │    │                 └── Registers write_todos tool                  │  │
│  │    │                                                                │  │
│  │    └── create_agent(model, tools + [write_todos], middleware, ...)   │  │
│  │                                                                     │  │
│  │  Agent Loop:                                                        │  │
│  │    1. LLM sees system prompt with <todo_list_system> instructions   │  │
│  │    2. LLM calls write_todos([{content, status}, ...])               │  │
│  │    3. Tool returns Command(update={"todos": [...], "messages": []}  │  │
│  │    4. ThreadState.todos updated                                     │  │
│  │    5. SSE "values" event streamed with updated todos[]              │  │
│  │    6. LLM continues work, updating todos as tasks complete          │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Plan Mode Activation Flow

Plan mode is a **runtime toggle**, not a global config. The frontend decides per-request whether to enable it.

```
┌─────────────────────────────────────────────────────────────────────┐
│                  PLAN MODE ACTIVATION CHAIN                        │
│                                                                     │
│  Frontend sends POST request:                                       │
│  {                                                                  │
│    "input": { "messages": [{"role": "user", "content": "..."}] },  │
│    "config": {                                                      │
│      "configurable": {                                              │
│        "model_name": "gpt-4o",                                     │
│        "thinking_enabled": true,                                    │
│        "is_plan_mode": true,       ◄── TOGGLE                      │
│        "subagent_enabled": true,                                    │
│        "max_concurrent_subagents": 3                                │
│      }                                                              │
│    },                                                               │
│    "stream_mode": ["values", "messages"]                            │
│  }                                                                  │
│                                                                     │
│         │                                                           │
│         ▼                                                           │
│  make_lead_agent(config: RunnableConfig)                            │
│         │                                                           │
│         ├── Line 243: is_plan_mode = config.get("configurable",     │
│         │              {}).get("is_plan_mode", False)                │
│         │                                                           │
│         ├── Line 250: _build_middlewares(config)                     │
│         │     │                                                     │
│         │     ├── Line 204: is_plan_mode = config.get(...)          │
│         │     │                                                     │
│         │     └── Line 205: _create_todo_list_middleware(is_plan_mode│
│         │           │                                               │
│         │           ├── if not is_plan_mode: return None  ← SKIP   │
│         │           │                                               │
│         │           └── if is_plan_mode:                            │
│         │                 return TodoListMiddleware(                │
│         │                   system_prompt=<custom Thinktank-AI prompt>, │
│         │                   tool_description=<custom description>   │
│         │                 )                                         │
│         │                                                           │
│         └── create_agent(                                           │
│               model=...,                                            │
│               tools=get_available_tools() + [write_todos],  ← AUTO │
│               middleware=[..., TodoListMiddleware, ...],             │
│               system_prompt=...,                                    │
│               state_schema=ThreadState                              │
│             )                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Function: `_create_todo_list_middleware`

**File:** `src/agents/lead_agent/agent.py` (Lines 63-175)

**Input:** `is_plan_mode: bool` — the runtime toggle from the frontend.

**Output:** `TodoListMiddleware | None` — returns a configured middleware instance if enabled, or `None` if disabled.

**Behavior:** When enabled, constructs a `TodoListMiddleware` with two custom Thinktank-AI-specific prompts: a system prompt injected into the LLM's instructions, and a tool description that guides the agent on when/how to use the `write_todos` tool.

---

## 3. The LangChain `TodoListMiddleware` (Source Analysis)

**File:** `.venv/lib/python3.12/site-packages/langchain/agents/middleware/todo.py`

This is a LangChain-provided middleware, not a Thinktank-AI custom implementation. Thinktank-AI customizes it with its own prompts.

### 3.1 The `Todo` Data Structure

```python
class Todo(TypedDict):
    """A single todo item with content and status."""
    content: str                                          # Task description
    status: Literal["pending", "in_progress", "completed"] # Current state
```

Three states form a simple finite state machine:

```
                ┌──────────┐
                │ pending  │
                └────┬─────┘
                     │  Agent starts work
                     ▼
              ┌─────────────┐
              │ in_progress │ ◄── Can loop back if blocked
              └──────┬──────┘
                     │  Agent finishes task
                     ▼
              ┌───────────┐
              │ completed │
              └───────────┘
```

### 3.2 The `PlanningState` Schema

```python
class PlanningState(AgentState):
    """State schema for the todo middleware."""
    todos: Annotated[NotRequired[list[Todo]], OmitFromInput]
```

The `OmitFromInput` annotation means `todos` is not part of the user's input — it is managed entirely by the agent through the `write_todos` tool.

### 3.3 The `write_todos` Tool

```
┌───────────────────────────────────────────────────────────────────┐
│                    write_todos Tool                               │
│                                                                   │
│  @tool(description=WRITE_TODOS_TOOL_DESCRIPTION)                 │
│  def write_todos(                                                │
│      todos: list[Todo],                                          │
│      tool_call_id: Annotated[str, InjectedToolCallId]            │
│  ) -> Command:                                                   │
│                                                                   │
│  Input:                                                           │
│    todos = [                                                      │
│      {"content": "Research X", "status": "completed"},           │
│      {"content": "Analyze Y",  "status": "in_progress"},        │
│      {"content": "Write report","status": "pending"},            │
│    ]                                                              │
│                                                                   │
│  Output:                                                          │
│    Command(update={                                               │
│      "todos": todos,          ◄── Replaces entire ThreadState.   │
│                                    todos with this new list      │
│      "messages": [ToolMessage(                                    │
│        "Updated todo list to [...]",                             │
│        tool_call_id=tool_call_id                                 │
│      )]                                                           │
│    })                                                             │
│                                                                   │
│  Key behavior:                                                    │
│  • REPLACES the entire todo list (not a diff/patch)              │
│  • Each call sends the COMPLETE current list                     │
│  • Adds a ToolMessage to confirm the update                      │
│  • Returns a LangGraph Command for atomic state update           │
└───────────────────────────────────────────────────────────────────┘
```

### 3.4 Middleware Hooks

The `TodoListMiddleware` class uses three hooks:

```
┌───────────────────────────────────────────────────────────────────┐
│               TodoListMiddleware Hooks                            │
│                                                                   │
│  ┌─────────────────────────────────────────┐                     │
│  │  __init__(system_prompt, tool_desc)     │                     │
│  │  • Creates write_todos tool instance    │                     │
│  │  • Stores in self.tools = [write_todos] │                     │
│  │  • Registered automatically by          │                     │
│  │    create_agent() middleware system      │                     │
│  └─────────────────────────────────────────┘                     │
│                                                                   │
│  ┌─────────────────────────────────────────┐                     │
│  │  wrap_model_call(request, handler)      │                     │
│  │  • Intercepts BEFORE LLM invocation     │                     │
│  │  • Appends todo system prompt to the    │                     │
│  │    existing SystemMessage content        │                     │
│  │  • This is how the LLM "knows" about   │                     │
│  │    the write_todos tool and its rules   │                     │
│  └─────────────────────────────────────────┘                     │
│                                                                   │
│  ┌─────────────────────────────────────────┐                     │
│  │  after_model(state, runtime)            │                     │
│  │  • Intercepts AFTER LLM responds        │                     │
│  │  • Checks: did the LLM call write_todos │                     │
│  │    MORE THAN ONCE in this turn?         │                     │
│  │  • If yes: returns error ToolMessages   │                     │
│  │    for all write_todos calls            │                     │
│  │  • Enforces: at most 1 write_todos call │                     │
│  │    per LLM turn (list replacement       │                     │
│  │    semantics require sequential updates) │                     │
│  └─────────────────────────────────────────┘                     │
└───────────────────────────────────────────────────────────────────┘
```

---

## 4. How the TODO List Is Generated

When the agent receives a complex task with plan mode enabled, here is the step-by-step generation flow:

```
 USER: "Build a REST API with authentication, database, and tests"
  │    (is_plan_mode: true)
  │
  ▼
 BEFORE_AGENT MIDDLEWARES fire (standard chain)
  │
  ▼
 TodoListMiddleware.wrap_model_call
  │  Appends to system message:
  │  "You have access to the `write_todos` tool...
  │   CRITICAL RULES:
  │   - Mark todos as completed IMMEDIATELY
  │   - Keep EXACTLY ONE task as in_progress
  │   - DO NOT use for simple tasks (< 3 steps)"
  │
  ▼
 LLM INVOCATION #1
  │
  │  System prompt includes:
  │  ┌────────────────────────────────────────────────────┐
  │  │  <role>You are Thinktank-AI 2.0...</role>              │
  │  │  <todo_list_system>                                │
  │  │  You have access to `write_todos` tool...          │
  │  │  CRITICAL RULES:                                   │
  │  │  - Mark todos completed IMMEDIATELY                │
  │  │  - Keep ONE task in_progress at a time            │
  │  │  - DO NOT use for simple tasks                    │
  │  │  </todo_list_system>                               │
  │  │  ... (plus all other Thinktank-AI prompt sections)     │
  │  └────────────────────────────────────────────────────┘
  │
  │  LLM thinks: "This is a complex 5-step task. I should create a plan."
  │
  │  LLM returns AIMessage with tool_calls:
  │  [{
  │    "name": "write_todos",
  │    "args": {
  │      "todos": [
  │        {"content": "Set up project structure",   "status": "in_progress"},
  │        {"content": "Implement database models",  "status": "pending"},
  │        {"content": "Build REST API endpoints",   "status": "pending"},
  │        {"content": "Add JWT authentication",     "status": "pending"},
  │        {"content": "Write integration tests",    "status": "pending"}
  │      ]
  │    }
  │  }]
  │
  ▼
 TodoListMiddleware.after_model
  │  Checks: only 1 write_todos call → OK, pass through
  │
  ▼
 TOOL EXECUTION: write_todos
  │  Returns Command(update={
  │    "todos": [5 items...],
  │    "messages": [ToolMessage("Updated todo list to [...]")]
  │  })
  │
  ▼
 ThreadState.todos = [5 items]
  │
  ▼
 SSE event: values
  │  data: {"todos": [
  │    {"content": "Set up project structure",  "status": "in_progress"},
  │    {"content": "Implement database models", "status": "pending"},
  │    {"content": "Build REST API endpoints",  "status": "pending"},
  │    {"content": "Add JWT authentication",    "status": "pending"},
  │    {"content": "Write integration tests",   "status": "pending"}
  │  ], "messages": [...], ...}
  │
  ▼
 Frontend receives and renders the TODO list
```

---

## 5. How the TODO List Is Managed and Completed

After the initial TODO list is created, the agent works through items one by one, calling `write_todos` after each step to update the state:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                  TODO LIST LIFECYCLE (Multi-Turn)                       │
│                                                                         │
│  TURN 1: Generate plan                                                  │
│  ──────────────────────                                                 │
│  LLM → write_todos([                                                    │
│    {content: "Set up project structure",   status: "in_progress"},      │
│    {content: "Implement database models",  status: "pending"},          │
│    {content: "Build REST API endpoints",   status: "pending"},          │
│    {content: "Add JWT authentication",     status: "pending"},          │
│    {content: "Write integration tests",    status: "pending"},          │
│  ])                                                                     │
│  LLM → bash("mkdir -p src/{models,routes,middleware,tests}")            │
│  LLM → write_file("/mnt/user-data/workspace/src/app.py", ...)          │
│                                                                         │
│  TURN 2: Complete step 1, start step 2                                  │
│  ──────────────────────────────────────                                 │
│  LLM → write_todos([                                                    │
│    {content: "Set up project structure",   status: "completed"},  ◄ ✓  │
│    {content: "Implement database models",  status: "in_progress"},◄ ►  │
│    {content: "Build REST API endpoints",   status: "pending"},         │
│    {content: "Add JWT authentication",     status: "pending"},         │
│    {content: "Write integration tests",    status: "pending"},         │
│  ])                                                                     │
│  LLM → write_file("/mnt/user-data/workspace/src/models/user.py", ...)  │
│  LLM → write_file("/mnt/user-data/workspace/src/models/db.py", ...)    │
│                                                                         │
│  TURN 3: Complete step 2, start step 3                                  │
│  ──────────────────────────────────────                                 │
│  LLM → write_todos([                                                    │
│    {content: "Set up project structure",   status: "completed"},       │
│    {content: "Implement database models",  status: "completed"},  ◄ ✓  │
│    {content: "Build REST API endpoints",   status: "in_progress"},◄ ►  │
│    {content: "Add JWT authentication",     status: "pending"},         │
│    {content: "Write integration tests",    status: "pending"},         │
│  ])                                                                     │
│  ...continues until all completed...                                    │
│                                                                         │
│  TURN 6: All done                                                       │
│  ────────────────                                                       │
│  LLM → write_todos([                                                    │
│    {content: "Set up project structure",   status: "completed"},  ✓    │
│    {content: "Implement database models",  status: "completed"},  ✓    │
│    {content: "Build REST API endpoints",   status: "completed"},  ✓    │
│    {content: "Add JWT authentication",     status: "completed"},  ✓    │
│    {content: "Write integration tests",    status: "completed"},  ✓    │
│  ])                                                                     │
│  LLM → present_files(["/mnt/user-data/outputs/project.zip"])           │
│  LLM → "Here's your complete REST API project with..."                  │
│                                                                         │
│  Each write_todos call:                                                  │
│    1. REPLACES the entire ThreadState.todos list                        │
│    2. Sends ToolMessage confirmation to agent                           │
│    3. Triggers SSE "values" event to frontend                           │
│    4. Frontend re-renders the TODO widget in real-time                   │
└──────────────────────────────────────────────────────────────────────────┘
```

### Dynamic Plan Revision

The agent can also **revise** the plan mid-execution:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    DYNAMIC PLAN REVISION                                │
│                                                                         │
│  Original plan:                                                         │
│    [✓] Set up project        [►] Build API        [ ] Add auth          │
│                                                                         │
│  Agent discovers: "The existing codebase already has auth middleware"    │
│                                                                         │
│  Revised plan via write_todos:                                          │
│    [✓] Set up project                                                   │
│    [►] Build API endpoints                                              │
│    [►] Integrate existing auth middleware  ◄── REPLACED "Add auth"      │
│    [ ] Write integration tests                                          │
│    [ ] Update API documentation            ◄── NEW task discovered      │
│                                                                         │
│  The agent sends the COMPLETE new list (not a diff).                    │
│  Old tasks can be removed, new tasks can be added.                      │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Parallel Write Protection

The `TodoListMiddleware.after_model` hook prevents ambiguous parallel updates:

```
┌──────────────────────────────────────────────────────────────────────────┐
│               PARALLEL WRITE PROTECTION                                │
│                                                                         │
│  LLM returns AIMessage with MULTIPLE write_todos calls:                 │
│    tool_calls = [                                                       │
│      {name: "write_todos", args: {todos: [version A]}},                │
│      {name: "bash", args: {command: "npm install"}},                   │
│      {name: "write_todos", args: {todos: [version B]}},  ◄ CONFLICT   │
│    ]                                                                    │
│                                                                         │
│  TodoListMiddleware.after_model detects:                                │
│    write_todos_calls = [call_1, call_2]   ← len() > 1                  │
│                                                                         │
│  Returns error ToolMessages:                                            │
│    [                                                                    │
│      ToolMessage("Error: write_todos should never be called multiple    │
│        times in parallel...", tool_call_id=call_1.id, status="error"), │
│      ToolMessage("Error: write_todos should never be called multiple    │
│        times in parallel...", tool_call_id=call_2.id, status="error"), │
│    ]                                                                    │
│                                                                         │
│  Agent retries with a single write_todos call on next turn.            │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Prompt Engineering for TODO Behavior

Thinktank-AI customizes two prompts that shape how the LLM uses the TODO system:

### 7.1 System Prompt (Injected via `wrap_model_call`)

```xml
<todo_list_system>
You have access to the `write_todos` tool to help you manage
and track complex multi-step objectives.

**CRITICAL RULES:**
- Mark todos as completed IMMEDIATELY after finishing each step
  - do NOT batch completions
- Keep EXACTLY ONE task as `in_progress` at any time
  (unless tasks can run in parallel)
- Update the todo list in REAL-TIME as you work
  - this gives users visibility into your progress
- DO NOT use this tool for simple tasks (< 3 steps)
  - just complete them directly

**When to Use:**
- Complex multi-step tasks requiring 3+ distinct steps
- Non-trivial tasks needing careful planning and execution
- User explicitly requests a todo list
- User provides multiple tasks

**When NOT to Use:**
- Single, straightforward tasks
- Trivial tasks (< 3 steps)
- Purely conversational or informational requests

**Best Practices:**
- Break down complex tasks into smaller, actionable steps
- Use clear, descriptive task names
- Remove tasks that become irrelevant
- Add new tasks discovered during implementation
- Don't be afraid to revise the todo list as you learn more
</todo_list_system>
```

### 7.2 Tool Description (Controls Tool Schema Seen by LLM)

The `write_todos` tool description includes:

- **When to Use** (5 scenarios): complex multi-step, non-trivial, explicitly requested, multiple tasks, dynamic planning
- **When NOT to Use** (4 scenarios): straightforward, trivial, <3 steps, conversational
- **How to Use** (4 rules): mark in_progress before starting, complete immediately, update future tasks, batch updates allowed
- **Task States**: pending, in_progress, completed
- **Completion Requirements**: only mark completed when FULLY accomplished, never mark if errors/blockers exist
- **Task Breakdown**: specific, actionable, clear, descriptive names

---

## 8. ThreadState Integration

**File:** `src/agents/thread_state.py`

```
┌─────────────────────────────────────────────────────────────────┐
│                     ThreadState(AgentState)                     │
│                                                                 │
│  messages: list[BaseMessage]        ← Conversation history      │
│  sandbox: SandboxState              ← Sandbox ID                │
│  thread_data: ThreadDataState       ← Directory paths           │
│  title: str | None                  ← Thread title              │
│  artifacts: list[str]               ← Output file paths         │
│  todos: list | None                 ← ★ TODO LIST ★             │
│  uploaded_files: list[dict] | None  ← Uploaded files            │
│  viewed_images: dict                ← Vision image data         │
│                                                                 │
│  The `todos` field:                                             │
│  • Type: NotRequired[list | None]                               │
│  • No custom reducer (unlike artifacts/viewed_images)           │
│  • Set to None when plan_mode is disabled                       │
│  • Populated by write_todos tool via Command(update={"todos"})  │
│  • Each write_todos call REPLACES the entire list               │
│  • Streamed to frontend via SSE "values" events                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 9. SSE Streaming of TODO Updates

When the agent calls `write_todos`, the updated state is streamed to the frontend:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                SSE EVENT FLOW FOR TODO UPDATES                         │
│                                                                         │
│  Agent calls write_todos([...])                                         │
│    │                                                                    │
│    ▼                                                                    │
│  Command(update={"todos": [...], "messages": [ToolMessage(...)]})      │
│    │                                                                    │
│    ▼                                                                    │
│  LangGraph applies state update:                                        │
│    ThreadState.todos = [new list]                                       │
│    ThreadState.messages.append(ToolMessage)                             │
│    │                                                                    │
│    ▼                                                                    │
│  LangGraph streams via SSE (stream_mode="values"):                     │
│                                                                         │
│  event: values                                                          │
│  data: {                                                                │
│    "messages": [...all messages including ToolMessage...],              │
│    "todos": [                                                           │
│      {"content": "Research competitors",    "status": "completed"},    │
│      {"content": "Analyze market trends",   "status": "in_progress"}, │
│      {"content": "Draft recommendations",   "status": "pending"},     │
│      {"content": "Create presentation",     "status": "pending"}      │
│    ],                                                                   │
│    "title": "Market Analysis Report",                                  │
│    "artifacts": [],                                                     │
│    "thread_data": {...},                                                │
│    "sandbox": {...}                                                     │
│  }                                                                      │
│                                                                         │
│  Frontend extracts state.todos and re-renders the TODO widget.         │
│                                                                         │
│  TIMING: A new "values" event is emitted after EVERY state change,     │
│  so the frontend gets a TODO update each time the agent:               │
│    • Creates the initial plan (first write_todos call)                 │
│    • Completes a step and starts the next one                          │
│    • Revises the plan (adds/removes/reorders tasks)                    │
│    • Completes all tasks                                               │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 10. TODO with Subagent Deep Research

When plan mode and subagent mode are both enabled, the TODO system orchestrates multi-phase research:

```
┌──────────────────────────────────────────────────────────────────────────┐
│            TODO + SUBAGENT COMBINED WORKFLOW                            │
│                                                                         │
│  User: "Write a comprehensive market analysis report on EV industry"   │
│  Config: {is_plan_mode: true, subagent_enabled: true}                  │
│                                                                         │
│  TURN 1: Plan Generation                                                │
│  ──────────────────────                                                 │
│  LLM → write_todos([                                                    │
│    {content: "Research EV market size & growth",   status: "in_progress"}│
│    {content: "Analyze key players & market share", status: "in_progress"}│
│    {content: "Study regulatory landscape",         status: "in_progress"}│
│    {content: "Synthesize findings into report",    status: "pending"},  │
│    {content: "Create final presentation",          status: "pending"},  │
│  ])                                                                     │
│                                                                         │
│  LLM → task(desc="EV market size",   prompt="...", type="general-purpose│
│  LLM → task(desc="EV key players",   prompt="...", type="general-purpose│
│  LLM → task(desc="EV regulations",   prompt="...", type="general-purpose│
│  (3 subagents run in parallel, researching concurrently)                │
│                                                                         │
│  SSE events during research:                                            │
│    task_started  → Subagent 1 launched                                  │
│    task_started  → Subagent 2 launched                                  │
│    task_started  → Subagent 3 launched                                  │
│    task_running  → Subagent 1 found market data...                      │
│    task_running  → Subagent 2 analyzing Tesla...                        │
│    task_running  → Subagent 3 reviewing EU regulations...               │
│    task_completed → Subagent 1 done                                     │
│    task_completed → Subagent 2 done                                     │
│    task_completed → Subagent 3 done                                     │
│                                                                         │
│  TURN 2: Update plan, synthesize                                        │
│  ────────────────────────────────                                       │
│  LLM → write_todos([                                                    │
│    {content: "Research EV market size & growth",   status: "completed"},│
│    {content: "Analyze key players & market share", status: "completed"},│
│    {content: "Study regulatory landscape",         status: "completed"},│
│    {content: "Synthesize findings into report",    status: "in_progress"}│
│    {content: "Create final presentation",          status: "pending"},  │
│  ])                                                                     │
│  LLM → write_file("/mnt/user-data/outputs/ev_report.md", ...)         │
│                                                                         │
│  TURN 3: Final deliverable                                              │
│  ─────────────────────────                                              │
│  LLM → write_todos([...all completed...])                               │
│  LLM → present_files(["/mnt/user-data/outputs/ev_report.md"])          │
│  LLM → "Here's your comprehensive EV market analysis..."               │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 11. Frontend UI Plan for TODO List Display

### 11.1 Component Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    FRONTEND COMPONENT TREE                             │
│                                                                         │
│  <ChatPage>                                                             │
│  ├── <ChatHeader>                                                       │
│  │   ├── <ModelSelector />          ← Dropdown for model_name          │
│  │   ├── <ThinkingToggle />         ← Switch for thinking_enabled      │
│  │   ├── <PlanModeToggle />         ← Switch for is_plan_mode   ★ NEW │
│  │   └── <SubagentToggle />         ← Switch for subagent_enabled      │
│  │                                                                      │
│  ├── <ChatBody>                                                         │
│  │   ├── <MessageList>                                                  │
│  │   │   ├── <UserMessage />                                            │
│  │   │   ├── <AssistantMessage />                                       │
│  │   │   ├── <ToolCallMessage />                                        │
│  │   │   └── <SubagentMessage />                                        │
│  │   │                                                                  │
│  │   └── <TodoPanel />              ← Collapsible side/inline   ★ NEW │
│  │       ├── <TodoHeader>                                               │
│  │       │   ├── Title: "Plan Progress"                                │
│  │       │   ├── Progress: "3/5 completed"                             │
│  │       │   └── ProgressBar (60%)                                     │
│  │       │                                                              │
│  │       └── <TodoList>                                                 │
│  │           ├── <TodoItem status="completed" />  ✓ Research data      │
│  │           ├── <TodoItem status="completed" />  ✓ Analyze trends     │
│  │           ├── <TodoItem status="completed" />  ✓ Build models       │
│  │           ├── <TodoItem status="in_progress"/> ► Write report       │
│  │           └── <TodoItem status="pending" />    ○ Final review       │
│  │                                                                      │
│  └── <ChatInput>                                                        │
│      ├── <TextArea />                                                   │
│      └── <SendButton />                                                 │
└─────────────────────────────────────────────────────────────────────────┘
```

### 11.2 Plan Mode Toggle Component

```
┌────────────────────────────────────────────────────────┐
│  PlanModeToggle                                        │
│                                                        │
│  Props:                                                │
│    enabled: boolean                                    │
│    onChange: (enabled: boolean) => void                │
│                                                        │
│  Renders:                                              │
│    ┌──────────────────────────────────────────┐        │
│    │  📋 Plan Mode  [═══●]                    │        │
│    │                  ON                       │        │
│    │  "Agent will create a task checklist     │        │
│    │   for complex requests"                  │        │
│    └──────────────────────────────────────────┘        │
│                                                        │
│  Behavior:                                             │
│    • Toggle sets is_plan_mode in next API request     │
│    • Can be toggled mid-conversation (takes effect     │
│      on the next message only)                        │
│    • Visual indicator when plan mode is active        │
└────────────────────────────────────────────────────────┘
```

### 11.3 TODO Panel Component

```
┌────────────────────────────────────────────────────────┐
│  TodoPanel                                             │
│                                                        │
│  Props:                                                │
│    todos: Todo[] | null                                │
│    isVisible: boolean                                  │
│                                                        │
│  State:                                                │
│    collapsed: boolean (default false)                  │
│                                                        │
│  Renders (when todos is non-null and non-empty):       │
│                                                        │
│  ┌──────────────────────────────────────────────┐      │
│  │  📋 Plan Progress                    [▼]     │      │
│  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━  3/5 done       │      │
│  │  ████████████████░░░░░░░░░░  60%             │      │
│  │                                              │      │
│  │  ✅ Research EV market size & growth         │      │
│  │     └ completed                              │      │
│  │                                              │      │
│  │  ✅ Analyze key players & market share       │      │
│  │     └ completed                              │      │
│  │                                              │      │
│  │  ✅ Study regulatory landscape               │      │
│  │     └ completed                              │      │
│  │                                              │      │
│  │  🔄 Synthesize findings into report          │      │
│  │     └ in progress...                         │      │
│  │                                              │      │
│  │  ⏳ Create final presentation                │      │
│  │     └ pending                                │      │
│  └──────────────────────────────────────────────┘      │
│                                                        │
│  Behavior:                                             │
│    • Appears automatically when first todos arrive     │
│    • Updates in real-time as SSE events arrive         │
│    • Can be collapsed/expanded                        │
│    • Progress bar animates on state changes            │
│    • Completed items get strike-through + green check │
│    • In-progress items have spinning indicator        │
│    • Hidden entirely when todos is null/empty          │
└────────────────────────────────────────────────────────┘
```

### 11.4 TodoItem Component

```
┌────────────────────────────────────────────────────────┐
│  TodoItem                                              │
│                                                        │
│  Props:                                                │
│    content: string                                     │
│    status: "pending" | "in_progress" | "completed"     │
│    index: number                                       │
│                                                        │
│  Visual States:                                        │
│                                                        │
│  pending:                                              │
│    ○  Task description                                 │
│    └ text-gray-400, no decoration                      │
│                                                        │
│  in_progress:                                          │
│    🔄 Task description                                 │
│    └ text-blue-600, font-medium, pulse animation       │
│       optional: spinning loader icon                   │
│                                                        │
│  completed:                                            │
│    ✅ Task description                                 │
│    └ text-green-600, line-through decoration            │
│       optional: slide-in checkmark animation           │
│                                                        │
│  Transition Animation:                                 │
│    pending → in_progress: fade blue + pulse start      │
│    in_progress → completed: green flash + checkmark    │
└────────────────────────────────────────────────────────┘
```

### 11.5 State Management

```
┌──────────────────────────────────────────────────────────────────────┐
│                   FRONTEND STATE MANAGEMENT                         │
│                                                                      │
│  // React state (or Zustand/Redux store)                            │
│                                                                      │
│  interface ChatState {                                               │
│    // Existing state                                                 │
│    messages: Message[];                                              │
│    threadId: string;                                                 │
│    isStreaming: boolean;                                             │
│                                                                      │
│    // Configuration state                                            │
│    config: {                                                         │
│      modelName: string;                                              │
│      thinkingEnabled: boolean;                                       │
│      isPlanMode: boolean;       ★ NEW                                │
│      subagentEnabled: boolean;                                       │
│      maxConcurrentSubagents: number;                                │
│    };                                                                │
│                                                                      │
│    // TODO state  ★ NEW                                              │
│    todos: Todo[] | null;                                             │
│    todosHistory: Todo[][];      // For undo/animation                │
│  }                                                                   │
│                                                                      │
│  interface Todo {                                                     │
│    content: string;                                                  │
│    status: "pending" | "in_progress" | "completed";                 │
│  }                                                                   │
│                                                                      │
│  // SSE event handler                                                │
│  function handleValuesEvent(data: ThreadState) {                    │
│    if (data.todos !== undefined) {                                  │
│      // Track previous state for animations                        │
│      if (state.todos) {                                             │
│        state.todosHistory.push([...state.todos]);                   │
│      }                                                               │
│      state.todos = data.todos;  // Replace entire list             │
│    }                                                                 │
│    if (data.messages) {                                              │
│      state.messages = data.messages;                                │
│    }                                                                 │
│    if (data.title) {                                                 │
│      state.title = data.title;                                      │
│    }                                                                 │
│  }                                                                   │
└──────────────────────────────────────────────────────────────────────┘
```

### 11.6 SSE Connection and Event Parsing

```
┌──────────────────────────────────────────────────────────────────────┐
│                   SSE CONNECTION PATTERN                             │
│                                                                      │
│  async function streamChat(threadId, message, config) {             │
│    const response = await fetch(                                    │
│      `/api/langgraph/threads/${threadId}/runs/stream`,              │
│      {                                                               │
│        method: "POST",                                               │
│        headers: { "Content-Type": "application/json" },             │
│        body: JSON.stringify({                                        │
│          input: {                                                    │
│            messages: [{ role: "user", content: message }]           │
│          },                                                          │
│          config: {                                                   │
│            configurable: {                                           │
│              model_name: config.modelName,                          │
│              thinking_enabled: config.thinkingEnabled,               │
│              is_plan_mode: config.isPlanMode,      ★ SENDS TOGGLE  │
│              subagent_enabled: config.subagentEnabled,               │
│              max_concurrent_subagents: config.maxConcurrentSubagents│
│            }                                                         │
│          },                                                          │
│          stream_mode: ["values", "messages"]                        │
│        })                                                            │
│      }                                                               │
│    );                                                                │
│                                                                      │
│    const reader = response.body.getReader();                        │
│    const decoder = new TextDecoder();                               │
│                                                                      │
│    while (true) {                                                    │
│      const { done, value } = await reader.read();                  │
│      if (done) break;                                                │
│                                                                      │
│      const text = decoder.decode(value);                            │
│      const events = parseSSE(text);                                 │
│                                                                      │
│      for (const event of events) {                                  │
│        switch (event.type) {                                        │
│          case "values":                                              │
│            const state = JSON.parse(event.data);                   │
│            handleValuesEvent(state);  ← Updates todos              │
│            break;                                                    │
│                                                                      │
│          case "messages":                                            │
│            const msg = JSON.parse(event.data);                     │
│            handleMessageEvent(msg);                                 │
│            break;                                                    │
│                                                                      │
│          case "end":                                                 │
│            setIsStreaming(false);                                    │
│            break;                                                    │
│        }                                                             │
│      }                                                               │
│    }                                                                 │
│  }                                                                   │
└──────────────────────────────────────────────────────────────────────┘
```

### 11.7 Display Placement Options

```
┌──────────────────────────────────────────────────────────────────────┐
│              THREE LAYOUT OPTIONS FOR TODO PANEL                    │
│                                                                      │
│  OPTION A: Inline in Chat (Recommended)                              │
│  ┌──────────────────────────────────────────────────┐                │
│  │  [User] Build me a REST API with auth and tests  │                │
│  │                                                  │                │
│  │  ┌──────────────────────────────────────────┐    │                │
│  │  │  📋 Plan Progress  3/5  ████████░░░  60% │    │  ← Embedded   │
│  │  │  ✅ Project structure                    │    │    inside      │
│  │  │  ✅ Database models                      │    │    the chat    │
│  │  │  ✅ API endpoints                        │    │    flow        │
│  │  │  🔄 JWT authentication                   │    │                │
│  │  │  ⏳ Integration tests                    │    │                │
│  │  └──────────────────────────────────────────┘    │                │
│  │                                                  │                │
│  │  [Assistant] I've set up the project structure...│                │
│  └──────────────────────────────────────────────────┘                │
│                                                                      │
│  OPTION B: Sticky Side Panel                                         │
│  ┌──────────────────────┬───────────────────┐                        │
│  │  Chat Messages       │  📋 Plan         │                        │
│  │                      │                   │                        │
│  │  [User] Build API... │  ✅ Structure    │  ← Always visible     │
│  │                      │  ✅ Models       │    on the right        │
│  │  [Agent] Working...  │  🔄 Endpoints   │    side of the chat    │
│  │                      │  ⏳ Auth         │                        │
│  │  [Agent] Done with...│  ⏳ Tests        │                        │
│  │                      │                   │                        │
│  └──────────────────────┴───────────────────┘                        │
│                                                                      │
│  OPTION C: Floating Overlay                                          │
│  ┌──────────────────────────────────────────────────┐                │
│  │  Chat Messages                                   │                │
│  │                               ┌─────────────┐   │                │
│  │  [User] Build API...          │ 📋 3/5 done │   │  ← Floating   │
│  │                               │ ✅ ✅ ✅ 🔄 ⏳ │   │    badge that │
│  │  [Agent] Working on...        └─────────────┘   │    expands on  │
│  │                                                  │    hover/click │
│  └──────────────────────────────────────────────────┘                │
└──────────────────────────────────────────────────────────────────────┘
```

### 11.8 Animation and Transition Design

```
┌──────────────────────────────────────────────────────────────────────┐
│                    ANIMATION SPECIFICATIONS                          │
│                                                                      │
│  1. Panel Appearance (first todos arrive):                           │
│     • Slide down from 0 height with ease-out (300ms)               │
│     • Fade in from opacity 0 → 1 (200ms)                           │
│                                                                      │
│  2. Todo Item Status Change:                                         │
│     pending → in_progress:                                          │
│     • Background flash: transparent → blue-50 → transparent (400ms)│
│     • Icon transition: ○ → 🔄 with rotate animation               │
│     • Text color: gray-400 → blue-600 (200ms)                     │
│                                                                      │
│     in_progress → completed:                                        │
│     • Background flash: transparent → green-50 → transparent (400ms│
│     • Icon transition: 🔄 → ✅ with scale bounce (0.8 → 1.1 → 1.0│
│     • Text decoration: none → line-through (200ms)                 │
│     • Text color: blue-600 → green-600 (200ms)                    │
│                                                                      │
│  3. New Todo Added:                                                  │
│     • Slide in from right with ease-out (250ms)                    │
│     • Fade in (200ms)                                               │
│                                                                      │
│  4. Todo Removed:                                                    │
│     • Slide out to left with ease-in (200ms)                       │
│     • Fade out (150ms)                                              │
│     • Height collapse (200ms)                                       │
│                                                                      │
│  5. Progress Bar:                                                    │
│     • Width transition: ease-in-out (500ms)                        │
│     • Color gradient: red(0%) → yellow(50%) → green(100%)         │
│                                                                      │
│  6. Completion Celebration:                                          │
│     When all todos are completed:                                   │
│     • Progress bar flashes green (2 pulses)                        │
│     • "All tasks complete! 🎉" text appears (fade in 300ms)       │
│     • Optional: confetti animation                                  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 12. Summary Table of Key Classes and Functions

| Component | File | Signature | Role |
|---|---|---|---|
| `Todo` | `langchain/agents/middleware/todo.py` | `TypedDict{content: str, status: Literal[...]}` | Data structure for a single todo item |
| `PlanningState` | `langchain/agents/middleware/todo.py` | `AgentState + todos: list[Todo]` | State schema with todo tracking |
| `write_todos` | `langchain/agents/middleware/todo.py` | `(todos: list[Todo]) → Command` | Tool that replaces the entire todo list atomically |
| `TodoListMiddleware` | `langchain/agents/middleware/todo.py` | `AgentMiddleware` subclass | Injects system prompt, registers tool, enforces single-write rule |
| `.wrap_model_call` | `TodoListMiddleware` | `(request, handler) → ModelCallResult` | Appends todo system prompt to LLM's system message |
| `.after_model` | `TodoListMiddleware` | `(state, runtime) → dict\|None` | Detects and rejects parallel write_todos calls |
| `_create_todo_list_middleware` | `src/agents/lead_agent/agent.py` | `(is_plan_mode: bool) → TodoListMiddleware\|None` | Creates middleware with custom Thinktank-AI prompts |
| `_build_middlewares` | `src/agents/lead_agent/agent.py` | `(config: RunnableConfig) → list[Middleware]` | Assembles middleware chain, inserting TodoList at position 6 |
| `make_lead_agent` | `src/agents/lead_agent/agent.py` | `(config: RunnableConfig) → CompiledGraph` | Extracts is_plan_mode from config, passes to middleware builder |
| `ThreadState.todos` | `src/agents/thread_state.py` | `NotRequired[list\|None]` | State field that stores the current todo list |

---

## 13. Data Flow Summary Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     COMPLETE TODO DATA FLOW                            │
│                                                                         │
│  Frontend                    Backend                                    │
│  ────────                    ───────                                    │
│                                                                         │
│  User toggles Plan Mode ON                                              │
│         │                                                               │
│         ▼                                                               │
│  POST /api/langgraph/threads/{id}/runs/stream                          │
│  body: {config: {configurable: {is_plan_mode: true}}}                  │
│         │                                                               │
│         │                    make_lead_agent(config)                    │
│         │                         │                                     │
│         │                    is_plan_mode = True                        │
│         │                         │                                     │
│         │                    TodoListMiddleware created                 │
│         │                    write_todos tool registered                │
│         │                         │                                     │
│         │                    Agent loop starts                          │
│         │                         │                                     │
│         │                    LLM sees <todo_list_system> prompt         │
│         │                    LLM decides to create plan                 │
│         │                    LLM calls write_todos([...])               │
│         │                         │                                     │
│         │                    after_model: validate (≤1 call)           │
│         │                         │                                     │
│         │                    write_todos tool executes:                 │
│         │                    Command(update={"todos": [...]})          │
│         │                         │                                     │
│         │                    ThreadState.todos updated                  │
│         │                         │                                     │
│  ◄──────┼──── SSE event: values ──┘                                    │
│         │    data: {todos: [...], messages: [...]}                      │
│         │                                                               │
│  Extract todos from event                                               │
│  Update React state                                                     │
│  Re-render TodoPanel                                                    │
│         │                                                               │
│         │                    LLM works on task #1                       │
│         │                    LLM calls write_todos([...updated])        │
│         │                         │                                     │
│  ◄──────┼──── SSE event: values ──┘                                    │
│         │    data: {todos: [...updated], ...}                           │
│         │                                                               │
│  Diff previous vs new todos                                             │
│  Animate status transitions                                             │
│  Update progress bar                                                    │
│         │                                                               │
│         │                    ...repeats until all completed...          │
│         │                                                               │
│  ◄──────┼──── SSE event: values                                        │
│         │    data: {todos: [...all completed], ...}                     │
│         │                                                               │
│  Show completion celebration                                            │
│         │                                                               │
│  ◄──────┼──── SSE event: end                                           │
│                                                                         │
│  Mark streaming complete                                                │
└──────────────────────────────────────────────────────────────────────────┘
```
