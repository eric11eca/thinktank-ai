# OpenViking Memory Integration Plan

> **Status**: Proposed
> **Date**: 2026-02-21
> **Branch**: `claude/openviking-memory-integration-plan-Zhgck`
> **Scope**: Backend only — no frontend changes in this plan

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Architecture Analysis](#2-current-architecture-analysis)
3. [OpenViking Architecture Overview](#3-openviking-architecture-overview)
4. [Integration Strategy](#4-integration-strategy)
5. [Phase 1 — Foundation Layer](#5-phase-1--foundation-layer)
6. [Phase 2 — Session Lifecycle Integration](#6-phase-2--session-lifecycle-integration)
7. [Phase 3 — Context-Aware Retrieval](#7-phase-3--context-aware-retrieval)
8. [Phase 4 — Memory Extraction Pipeline](#8-phase-4--memory-extraction-pipeline)
9. [Phase 5 — Resource Management](#9-phase-5--resource-management)
10. [Phase 6 — Skills Registry](#10-phase-6--skills-registry)
11. [Phase 7 — Gateway API Extensions](#11-phase-7--gateway-api-extensions)
12. [Phase 8 — Migration & Backward Compatibility](#12-phase-8--migration--backward-compatibility)
13. [Configuration Reference](#13-configuration-reference)
14. [File Change Inventory](#14-file-change-inventory)
15. [Risk Assessment & Mitigations](#15-risk-assessment--mitigations)
16. [Testing Strategy](#16-testing-strategy)
17. [Rollout Plan](#17-rollout-plan)

---

## 1. Executive Summary

This plan details the integration of [OpenViking](https://github.com/volcengine/OpenViking) (v0.1.17+) — a context database for AI agents — into the thinktank-ai backend. OpenViking replaces the current flat-file memory system (`memory.json`) with a hierarchical, filesystem-based context engine that provides:

- **Three-tier progressive context loading** (L0/L1/L2) to minimize token usage
- **Intent-aware retrieval** via hierarchical directory-recursive search
- **Automatic memory extraction** from sessions with six typed categories
- **Unified `viking://` URI addressing** for memories, resources, and skills
- **Observable retrieval pipeline** for debugging and tuning

The integration touches four backend subsystems: the memory module (`src/agents/memory/`), the middleware chain (`src/agents/middlewares/`), the lead agent prompt injection (`src/agents/lead_agent/`), and the Gateway API (`src/gateway/routers/`). It is designed as an **8-phase incremental rollout** with a feature flag (`memory.backend: "openviking" | "legacy"`) enabling safe, reversible deployment.

---

## 2. Current Architecture Analysis

### 2.1 Memory Data Model

The current memory system stores a single JSON file at `backend/.think-tank/memory.json`:

```
memory.json
├── version: "1.0"
├── lastUpdated: ISO-8601
├── user
│   ├── workContext      { summary, updatedAt }
│   ├── personalContext  { summary, updatedAt }
│   └── topOfMind        { summary, updatedAt }
├── history
│   ├── recentMonths         { summary, updatedAt }
│   ├── earlierContext       { summary, updatedAt }
│   └── longTermBackground   { summary, updatedAt }
└── facts[]
    ├── id, content, category, confidence, createdAt, source
    └── categories: preference | knowledge | context | behavior | goal
```

### 2.2 Memory Update Flow

```
Agent completes turn
  → MemoryMiddleware.after_agent()
    → _filter_messages_for_memory() (keep human + final AI only)
      → MemoryUpdateQueue.add(thread_id, messages)
        → Debounce timer (30s default)
          → MemoryUpdater.update_memory(messages, thread_id)
            → LLM extracts context + facts
              → Atomic write to memory.json (temp + rename)
```

### 2.3 Memory Injection Flow

```
make_lead_agent()
  → apply_prompt_template()
    → _get_memory_context()
      → get_memory_data() (cached, mtime-invalidated)
        → format_memory_for_injection(memory_data, max_tokens=2000)
          → Injected as <memory>...</memory> in system prompt
```

### 2.4 Key Source Files

| File | Role |
|------|------|
| `src/agents/memory/updater.py` | `MemoryUpdater` class — LLM-based extraction |
| `src/agents/memory/queue.py` | `MemoryUpdateQueue` — debounced background processing |
| `src/agents/memory/prompt.py` | Prompt templates + `format_memory_for_injection()` |
| `src/agents/memory/__init__.py` | Public API exports |
| `src/agents/middlewares/memory_middleware.py` | `MemoryMiddleware` — after-agent hook |
| `src/agents/lead_agent/prompt.py` | `_get_memory_context()` — system prompt injection |
| `src/agents/lead_agent/agent.py` | Middleware chain assembly in `_build_middlewares()` |
| `src/agents/thread_state.py` | `ThreadState` schema |
| `src/config/memory_config.py` | `MemoryConfig` — configuration model |
| `src/gateway/routers/memory.py` | REST endpoints for memory access |
| `config.yaml` | Top-level memory configuration block |

### 2.5 Limitations of Current System

1. **Flat storage** — No hierarchy; all facts stored in a single list with linear scan
2. **No semantic retrieval** — Facts are ranked by confidence only, not by relevance to the current query
3. **No progressive loading** — All injected context counts against a single 2000-token budget
4. **No session awareness** — Memory extraction doesn't consider conversation context or intent
5. **No resource management** — No mechanism for ingesting and searching external knowledge
6. **Five coarse categories** — Preference, knowledge, context, behavior, goal; no distinction between user and agent memories
7. **No cross-session learning** — Agent doesn't accumulate operational experience (cases, patterns)

---

## 3. OpenViking Architecture Overview

### 3.1 Core Concepts

**Context Database**: OpenViking is a purpose-built database for AI agent context. It uses a virtual filesystem paradigm where all context is addressable via `viking://` URIs.

**Three Context Types**:

| Type | URI Root | Description |
|------|----------|-------------|
| Resources | `viking://resources/` | External knowledge (docs, APIs, manuals) — user-added, static after ingestion |
| Memory | `viking://user/memories/`, `viking://agent/` | Auto-extracted from sessions — continuously evolving |
| Skills | `viking://agent/skills/` | Callable agent capabilities — relatively static |

**Six Memory Categories** (vs current 5 fact categories):

| Category | Scope | Mutability | Maps To (Current) |
|----------|-------|------------|-------------------|
| Profile | User | Appendable | `personalContext` |
| Preferences | User | Appendable | `preference` facts |
| Entities | User | Append-only | `knowledge` facts |
| Events | User | Append-only | `context` facts |
| Cases | Agent | Append-only | *(new — no equivalent)* |
| Patterns | Agent | Append-only | `behavior` facts |

### 3.2 L0/L1/L2 Progressive Context Layers

| Layer | Size | Purpose | When Used |
|-------|------|---------|-----------|
| L0 — Abstract | ~100 tokens | Vector similarity search, quick filtering | Always (retrieval index) |
| L1 — Overview | ~2,000 tokens | Reranking, navigation, agent decision-making | On match |
| L2 — Detail | Full content | Deep reading, complete source material | On demand |

This replaces the current single-tier `format_memory_for_injection()` with a strategy that loads progressively — reducing token waste by 60-80% on average while improving relevance.

### 3.3 Retrieval Pipeline

```
Query
  → IntentAnalyzer (LLM) → 0-5 TypedQuery objects
    → HierarchicalRetriever
      → Global vector search on L0 abstracts
        → Recursive directory search with score propagation
          → Convergence detection (stable top-k for 3 rounds)
            → Optional reranking
              → FindResult { memories, resources, skills }
```

### 3.4 Session Lifecycle

```
client.create_session()
  → session.add_message(role, parts)    # Track conversation
    → session.used(contexts, skills)    # Track what was retrieved
      → session.commit()               # Archive + extract memories
```

### 3.5 Key Python APIs

```python
import openviking as ov

# Initialize
client = ov.OpenViking(path="./data")          # Embedded mode
client = ov.SyncHTTPClient(url="...", api_key="...")  # HTTP mode

# Sessions
session = client.create_session()
session.add_message("user", [{"type": "text", "text": "..."}])
session.add_message("assistant", [{"type": "text", "text": "..."}])
session.used(contexts=[matched_context])
session.commit()

# Retrieval
results = client.search(query, session=session, limit=10)
results = client.find(query, limit=10)

# Filesystem
entries = client.ls("viking://user/memories/")
content = client.read("viking://user/memories/preferences/coding-style")
summary = client.abstract("viking://resources/api-docs")
overview = client.overview("viking://resources/api-docs")

# Resources
client.add_resource("/path/to/doc.pdf", target="viking://resources/docs")
```

---

## 4. Integration Strategy

### 4.1 Design Principles

1. **Feature-flagged backend switch** — `memory.backend: "openviking" | "legacy"` in `config.yaml`; legacy remains the default until OpenViking is validated
2. **Interface preservation** — All existing public APIs (`get_memory_data()`, `format_memory_for_injection()`, Gateway endpoints) continue to work; OpenViking provides an alternative implementation behind the same interfaces
3. **Incremental rollout** — 8 phases, each independently deployable and testable
4. **No frontend changes** — The frontend continues to consume the same Gateway API; internal backend changes are transparent
5. **Session-thread alignment** — Each thinktank thread maps 1:1 to an OpenViking session

### 4.2 Architecture After Integration

```
                           ┌─────────────────────────────┐
                           │     config.yaml              │
                           │  memory:                     │
                           │    backend: "openviking"     │
                           │    openviking: { ... }       │
                           └──────────┬──────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    │                                     │
              ┌─────▼──────┐                     ┌───────▼────────┐
              │   Legacy    │                     │   OpenViking   │
              │  Backend    │                     │   Backend      │
              │             │                     │                │
              │ memory.json │                     │ ov.OpenViking  │
              │ MemoryUpd.  │                     │ AGFS + Vector  │
              │ MemoryQueue │                     │ Sessions       │
              └─────┬──────┘                     └───────┬────────┘
                    │                                     │
                    └─────────────────┬───────────────────┘
                                      │
                    ┌─────────────────▼─────────────────┐
                    │       MemoryBackend Interface       │
                    │                                     │
                    │  get_context(query, session) → str  │
                    │  update(messages, thread_id)        │
                    │  get_data() → dict                  │
                    │  inject_into_prompt(max_tokens)     │
                    └─────────────────┬─────────────────┘
                                      │
                    ┌─────────────────▼─────────────────┐
                    │       MemoryMiddleware              │
                    │       Lead Agent Prompt             │
                    │       Gateway API                   │
                    └───────────────────────────────────┘
```

### 4.3 Concept Mapping

| Thinktank Concept | OpenViking Equivalent |
|---|---|
| Thread (`thread_id`) | Session (`session_id`) |
| `memory.json` | AGFS + Vector Index |
| `facts[]` | `viking://user/memories/*` entries |
| `user.workContext` | `viking://user/memories/profile/` |
| `user.personalContext` | `viking://user/memories/preferences/` |
| `user.topOfMind` | Retrieved via `search()` with session context |
| `history.*` | Session archives under `viking://user/memories/events/` |
| `MemoryUpdater` LLM extraction | `session.commit()` → `MemoryExtractor` |
| `MemoryUpdateQueue` debounce | OpenViking's async `SemanticQueue` |
| `format_memory_for_injection()` | `client.search()` → L1 summaries |
| `confidence` score (0-1) | `MatchedContext.score` (0-1) |
| Fact `category` | Memory `context_type` (profile, preferences, entities, events, cases, patterns) |
| *(not available)* | `viking://resources/` — external knowledge |
| Skill injection in prompt | `viking://agent/skills/` — retrievable skills |

---

## 5. Phase 1 — Foundation Layer

**Goal**: Install OpenViking, create the backend abstraction, and wire up the feature flag.

### 5.1 Add Dependency

**File**: `backend/pyproject.toml`

Add to `[project.dependencies]`:
```toml
"openviking>=0.1.17",
```

### 5.2 Create `MemoryBackend` Protocol

**New file**: `src/agents/memory/backend.py`

```python
from typing import Protocol, Any

class MemoryBackend(Protocol):
    """Abstract interface for memory backends."""

    def initialize(self) -> None:
        """Initialize the backend (called once at startup)."""
        ...

    def close(self) -> None:
        """Clean up resources."""
        ...

    def get_data(self) -> dict[str, Any]:
        """Return memory data in the legacy format for API compatibility."""
        ...

    def inject_context(self, query: str | None, thread_id: str | None,
                       max_tokens: int) -> str:
        """Return formatted context string for system prompt injection."""
        ...

    def update_from_messages(self, messages: list[Any],
                             thread_id: str | None) -> bool:
        """Process messages and update memory. Returns success."""
        ...

    def reload(self) -> dict[str, Any]:
        """Force-reload from storage. Returns fresh data."""
        ...
```

### 5.3 Create Legacy Backend Adapter

**New file**: `src/agents/memory/legacy_backend.py`

Wraps the existing `MemoryUpdater`, `MemoryUpdateQueue`, and `format_memory_for_injection()` behind the `MemoryBackend` protocol. No behavior change — this is a pure refactor.

```python
class LegacyMemoryBackend:
    """Adapter wrapping the existing memory.json system."""

    def initialize(self) -> None:
        # No-op: legacy system initializes lazily

    def close(self) -> None:
        self._queue.flush()

    def get_data(self) -> dict[str, Any]:
        return get_memory_data()

    def inject_context(self, query, thread_id, max_tokens) -> str:
        # Delegates to existing format_memory_for_injection()
        return format_memory_for_injection(get_memory_data(), max_tokens)

    def update_from_messages(self, messages, thread_id) -> bool:
        self._queue.add(thread_id, messages)
        return True

    def reload(self) -> dict[str, Any]:
        return reload_memory_data()
```

### 5.4 Create OpenViking Backend

**New file**: `src/agents/memory/openviking_backend.py`

```python
import openviking as ov

class OpenVikingMemoryBackend:
    """OpenViking-powered memory backend."""

    def __init__(self, config: OpenVikingConfig):
        self._config = config
        self._client: ov.OpenViking | None = None
        self._sessions: dict[str, ov.Session] = {}  # thread_id → session

    def initialize(self) -> None:
        self._client = ov.OpenViking(path=self._config.data_path)

    def close(self) -> None:
        for session in self._sessions.values():
            session.commit()
        self._client.close()

    # ... (implementations detailed in Phases 2-4)
```

### 5.5 Create Backend Factory

**New file**: `src/agents/memory/factory.py`

```python
_backend: MemoryBackend | None = None

def get_memory_backend() -> MemoryBackend:
    global _backend
    if _backend is None:
        config = get_memory_config()
        if config.backend == "openviking":
            _backend = OpenVikingMemoryBackend(config.openviking)
        else:
            _backend = LegacyMemoryBackend()
        _backend.initialize()
    return _backend
```

### 5.6 Extend `MemoryConfig`

**File**: `src/config/memory_config.py`

Add new fields:
```python
class OpenVikingConfig(BaseModel):
    data_path: str = ".think-tank/openviking"
    deployment_mode: str = "standalone"  # standalone | hybrid | http
    http_url: str | None = None
    http_api_key: str | None = None
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"
    embedding_api_key: str | None = None
    vlm_provider: str | None = None
    vlm_model: str | None = None
    vlm_api_key: str | None = None
    rerank_provider: str | None = None
    rerank_model: str | None = None
    search_limit: int = 10
    l1_injection: bool = True   # Use L1 overviews in prompt (vs L0)

class MemoryConfig(BaseModel):
    # ... existing fields ...
    backend: str = "legacy"  # "legacy" | "openviking"
    openviking: OpenVikingConfig = OpenVikingConfig()
```

### 5.7 Extend `config.yaml`

```yaml
memory:
  enabled: true
  backend: "legacy"           # Switch to "openviking" to activate
  # ... existing fields ...
  openviking:
    data_path: ".think-tank/openviking"
    deployment_mode: "standalone"
    embedding_provider: "openai"
    embedding_model: "text-embedding-3-small"
    embedding_api_key: $OPENAI_API_KEY
    vlm_provider: "openai"
    vlm_model: "gpt-4o-mini"
    vlm_api_key: $OPENAI_API_KEY
    search_limit: 10
    l1_injection: true
```

---

## 6. Phase 2 — Session Lifecycle Integration

**Goal**: Map thinktank threads 1:1 to OpenViking sessions so that every conversation is tracked for memory extraction.

### 6.1 Session Management in OpenViking Backend

**File**: `src/agents/memory/openviking_backend.py`

```python
def get_or_create_session(self, thread_id: str) -> ov.Session:
    """Get existing session or create one for this thread."""
    if thread_id not in self._sessions:
        # Try to resume an existing OpenViking session with matching ID
        try:
            session = self._client.get_session(thread_id)
        except Exception:
            session = self._client.create_session(session_id=thread_id)
        self._sessions[thread_id] = session
    return self._sessions[thread_id]

def add_messages_to_session(self, thread_id: str, messages: list) -> None:
    """Forward messages to the OpenViking session."""
    session = self.get_or_create_session(thread_id)
    for msg in messages:
        role = "user" if msg.type == "human" else "assistant"
        session.add_message(role, [{"type": "text", "text": str(msg.content)}])
```

### 6.2 New `OpenVikingSessionMiddleware`

**New file**: `src/agents/middlewares/openviking_session_middleware.py`

This middleware runs **before** the agent (to set up the session and inject context) and **after** (to track messages and usage).

```python
class OpenVikingSessionMiddleware(AgentMiddleware[ThreadState]):
    """Manages OpenViking session lifecycle per thread."""

    def before_agent(self, state, runtime) -> dict | None:
        backend = get_memory_backend()
        if not isinstance(backend, OpenVikingMemoryBackend):
            return None
        thread_id = runtime.context.get("thread_id")
        if not thread_id:
            return None
        # Ensure session exists for this thread
        backend.get_or_create_session(thread_id)
        return None

    def after_agent(self, state, runtime) -> dict | None:
        backend = get_memory_backend()
        if not isinstance(backend, OpenVikingMemoryBackend):
            return None
        thread_id = runtime.context.get("thread_id")
        messages = _filter_messages_for_session(state.get("messages", []))
        backend.add_messages_to_session(thread_id, messages)
        return None
```

### 6.3 Middleware Chain Update

**File**: `src/agents/lead_agent/agent.py` — `_build_middlewares()`

Insert `OpenVikingSessionMiddleware` at position **8** (right before the existing `MemoryMiddleware` at position 9):

```
 8. OpenVikingSessionMiddleware  ← NEW (only active when backend="openviking")
 9. MemoryMiddleware             ← existing (becomes no-op when backend="openviking")
```

The existing `MemoryMiddleware` is conditionally skipped when OpenViking is active, since session management replaces the debounced queue.

---

## 7. Phase 3 — Context-Aware Retrieval

**Goal**: Replace the static `format_memory_for_injection()` with OpenViking's `search()` for intent-aware, query-relevant context retrieval with L0/L1/L2 progressive loading.

### 7.1 Implement `inject_context()` on OpenViking Backend

**File**: `src/agents/memory/openviking_backend.py`

```python
def inject_context(self, query: str | None, thread_id: str | None,
                   max_tokens: int) -> str:
    """
    Retrieve relevant context from OpenViking and format for injection.

    Uses search() with session context for intent-aware retrieval.
    Returns L1 overviews by default (configurable to L0 for lower token usage).
    """
    session = self._sessions.get(thread_id) if thread_id else None

    if query and session:
        results = self._client.search(
            query=query,
            session=session,
            limit=self._config.search_limit,
        )
    elif query:
        results = self._client.find(query=query, limit=self._config.search_limit)
    else:
        # No query available — fall back to recent memories
        results = self._client.find(
            query="recent user context and preferences",
            limit=5,
        )

    return self._format_results(results, max_tokens)

def _format_results(self, results, max_tokens: int) -> str:
    """Format FindResult into prompt-injectable text with token budgeting."""
    sections = []
    token_count = 0

    # Memories first (highest priority)
    for ctx in results.memories:
        content = self._get_layer_content(ctx)
        tokens = _estimate_tokens(content)
        if token_count + tokens > max_tokens:
            break
        sections.append(f"[Memory: {ctx.uri}]\n{content}")
        token_count += tokens

    # Resources second
    for ctx in results.resources:
        content = self._get_layer_content(ctx)
        tokens = _estimate_tokens(content)
        if token_count + tokens > max_tokens:
            break
        sections.append(f"[Resource: {ctx.uri}]\n{content}")
        token_count += tokens

    # Skills last
    for ctx in results.skills:
        content = self._get_layer_content(ctx)
        tokens = _estimate_tokens(content)
        if token_count + tokens > max_tokens:
            break
        sections.append(f"[Skill: {ctx.uri}]\n{content}")
        token_count += tokens

    return "\n\n".join(sections)

def _get_layer_content(self, ctx) -> str:
    """Get L1 overview (default) or L0 abstract based on config."""
    if self._config.l1_injection:
        return self._client.overview(ctx.uri) or ctx.abstract
    return ctx.abstract
```

### 7.2 Update System Prompt Injection

**File**: `src/agents/lead_agent/prompt.py` — `_get_memory_context()`

Change the function to use the backend abstraction and pass the current query:

```python
def _get_memory_context(query: str | None = None,
                        thread_id: str | None = None) -> str:
    config = get_memory_config()
    if not config.enabled or not config.injection_enabled:
        return ""

    backend = get_memory_backend()
    content = backend.inject_context(
        query=query,
        thread_id=thread_id,
        max_tokens=config.max_injection_tokens,
    )

    if not content:
        return ""
    return f"<memory>\n{content}\n</memory>"
```

### 7.3 Pass Query Context to Prompt Builder

**File**: `src/agents/lead_agent/agent.py`

The `apply_prompt_template()` call needs access to the latest user message for query-aware retrieval. This requires extracting the last human message from state and forwarding it:

```python
# In the agent's pre-model hook or system prompt generation:
last_user_message = _extract_last_user_message(state.get("messages", []))
system_prompt = apply_prompt_template(
    ...,
    query=last_user_message,
    thread_id=runtime.context.get("thread_id"),
)
```

### 7.4 Token Budget Allocation

With L0/L1/L2, the `max_injection_tokens` budget is spent more efficiently:

| Scenario | Current System | OpenViking (L1) | OpenViking (L0) |
|----------|---------------|-----------------|-----------------|
| 2000 token budget | ~15 facts (flat) | ~1 L1 overview | ~20 L0 abstracts |
| Relevance | Confidence-ranked | Intent-aware | Similarity-ranked |
| Coverage | Top 15 by score | Deep on 1 topic | Broad across 20 |

**Recommendation**: Use L1 injection (`l1_injection: true`) by default for richer context, with L0 fallback for breadth-oriented queries. The `max_injection_tokens` should be increased to 4000 when using OpenViking to leverage the improved relevance.

---

## 8. Phase 4 — Memory Extraction Pipeline

**Goal**: Replace the `MemoryUpdater` LLM extraction + `MemoryUpdateQueue` debounce with OpenViking's `session.commit()` which performs archival and memory extraction automatically.

### 8.1 Implement `update_from_messages()` on OpenViking Backend

**File**: `src/agents/memory/openviking_backend.py`

```python
def update_from_messages(self, messages: list, thread_id: str | None) -> bool:
    """
    Commit the session to trigger memory extraction.

    OpenViking's session.commit() performs:
    1. Archive messages to timestamped directories
    2. Generate structured summary (overview, user intent, key concepts)
    3. MemoryExtractor categorizes into 6 memory types
    4. Vector deduplication against existing memories
    5. Persist to AGFS + vector index
    """
    if not thread_id or thread_id not in self._sessions:
        return False

    session = self._sessions[thread_id]
    session.commit()

    # Clean up session reference (new session will be created on next interaction)
    del self._sessions[thread_id]
    return True
```

### 8.2 Commit Trigger Strategy

The existing system debounces memory updates (30s). OpenViking's `session.commit()` is a heavier operation (archival + extraction + indexing). The trigger strategy changes:

| Trigger | Current System | OpenViking |
|---------|---------------|------------|
| After each turn | Queue + debounce (30s) | `session.add_message()` only |
| Thread idle (30s+) | Process queue | `session.commit()` |
| Thread end / user leaves | `queue.flush()` | `session.commit()` |
| Explicit user action | N/A | `session.commit()` via API |

**Implementation**: The `OpenVikingSessionMiddleware.after_agent()` tracks messages. A separate background timer (reusing the existing debounce mechanism) calls `session.commit()` when a thread is idle for `debounce_seconds`. This preserves the "don't commit on every turn" behavior while using OpenViking's richer extraction.

### 8.3 Memory Category Mapping

When `get_data()` is called (for API compatibility), OpenViking memories are mapped back to the legacy format:

```python
def get_data(self) -> dict[str, Any]:
    """Return memory in legacy-compatible format."""
    memories = {
        "version": "2.0",
        "lastUpdated": datetime.utcnow().isoformat() + "Z",
        "user": {
            "workContext": self._read_section("viking://user/memories/profile/"),
            "personalContext": self._read_section("viking://user/memories/preferences/"),
            "topOfMind": self._read_section("viking://user/memories/events/"),
        },
        "history": {
            "recentMonths": self._read_section("viking://user/memories/events/"),
            "earlierContext": self._read_section("viking://user/memories/entities/"),
            "longTermBackground": self._read_section("viking://agent/cases/"),
        },
        "facts": self._convert_memories_to_facts(),
    }
    return memories

def _convert_memories_to_facts(self) -> list[dict]:
    """Read all memories and convert to legacy fact format."""
    facts = []
    for uri_base, category in [
        ("viking://user/memories/preferences/", "preference"),
        ("viking://user/memories/entities/", "knowledge"),
        ("viking://user/memories/events/", "context"),
        ("viking://user/memories/profile/", "context"),
        ("viking://agent/patterns/", "behavior"),
        ("viking://agent/cases/", "knowledge"),
    ]:
        entries = self._client.ls(uri_base)
        for entry in entries:
            abstract = self._client.abstract(entry.uri)
            facts.append({
                "id": entry.uri,
                "content": abstract,
                "category": category,
                "confidence": 0.9,  # OpenViking pre-filters low-quality
                "createdAt": entry.metadata.get("created_at", ""),
                "source": entry.metadata.get("source_session", ""),
            })
    return facts
```

---

## 9. Phase 5 — Resource Management

**Goal**: Enable the agent to ingest, search, and reference external documents through OpenViking's resource system.

### 9.1 New Agent Tool: `add_resource`

**New file**: `src/agents/tools/openviking_tools.py`

```python
@tool("add_resource", parse_docstring=True)
def add_resource_tool(path: str, description: str | None = None) -> str:
    """Add a document or URL as a searchable resource.

    Args:
        path: Local file path or URL to ingest.
        description: Optional description of the resource.
    """
    backend = get_memory_backend()
    if not isinstance(backend, OpenVikingMemoryBackend):
        return "Resource management requires OpenViking backend."

    client = backend.get_client()
    client.add_resource(path, reason=description, wait=True)
    return f"Resource added: {path}"
```

### 9.2 New Agent Tool: `search_resources`

```python
@tool("search_resources", parse_docstring=True)
def search_resources_tool(query: str) -> str:
    """Search through ingested resources and memories.

    Args:
        query: Natural language search query.
    """
    backend = get_memory_backend()
    if not isinstance(backend, OpenVikingMemoryBackend):
        return "Resource search requires OpenViking backend."

    client = backend.get_client()
    results = client.find(query, target_uri="viking://resources/", limit=5)

    output_parts = []
    for ctx in results.resources:
        overview = client.overview(ctx.uri) or ctx.abstract
        output_parts.append(f"**{ctx.uri}** (score: {ctx.score:.2f})\n{overview}")

    return "\n\n---\n\n".join(output_parts) if output_parts else "No matching resources found."
```

### 9.3 New Agent Tool: `read_resource`

```python
@tool("read_resource", parse_docstring=True)
def read_resource_tool(uri: str) -> str:
    """Read the full content of a resource by its viking:// URI.

    Args:
        uri: The viking:// URI of the resource to read.
    """
    backend = get_memory_backend()
    if not isinstance(backend, OpenVikingMemoryBackend):
        return "Resource reading requires OpenViking backend."

    client = backend.get_client()
    return client.read(uri)
```

### 9.4 Tool Registration

**File**: `src/agents/lead_agent/agent.py` — `get_available_tools()`

When OpenViking backend is active, add the resource tools to the available tools list:

```python
if get_memory_config().backend == "openviking":
    tools.extend([add_resource_tool, search_resources_tool, read_resource_tool])
```

### 9.5 Upload Pipeline Integration

**File**: `src/gateway/routers/uploads.py`

When a user uploads a document (PDF, DOCX, etc.) through the existing upload endpoint, optionally ingest it into OpenViking as a resource:

```python
# After saving the uploaded file:
if get_memory_config().backend == "openviking":
    backend = get_memory_backend()
    client = backend.get_client()
    client.add_resource(
        saved_path,
        target=f"viking://resources/uploads/{thread_id}/",
        reason=f"User uploaded: {filename}",
    )
```

---

## 10. Phase 6 — Skills Registry

**Goal**: Register thinktank skills in OpenViking's skill system so they become searchable and retrievable alongside memories and resources.

### 10.1 Skill Sync on Startup

**New file**: `src/agents/memory/skill_sync.py`

```python
def sync_skills_to_openviking(client: ov.OpenViking, skills_path: str) -> None:
    """Sync thinktank SKILL.md files to OpenViking's skill registry."""
    skills_dir = Path(skills_path)
    for skill_file in skills_dir.rglob("SKILL.md"):
        skill_name = skill_file.parent.name
        target_uri = f"viking://agent/skills/{skill_name}"

        # Check if skill already exists and is up to date
        try:
            stat = client.stat(target_uri)
            if stat and stat.mtime >= skill_file.stat().st_mtime:
                continue  # Already synced
        except Exception:
            pass  # Doesn't exist yet

        client.add_resource(
            str(skill_file),
            target=target_uri,
            reason=f"Thinktank skill: {skill_name}",
            wait=False,
        )
```

### 10.2 Integration Point

Call `sync_skills_to_openviking()` during `OpenVikingMemoryBackend.initialize()`:

```python
def initialize(self) -> None:
    self._client = ov.OpenViking(path=self._config.data_path)
    skills_config = get_app_config().skills
    sync_skills_to_openviking(self._client, skills_config.path)
```

### 10.3 Impact on Retrieval

Once skills are registered, `client.search()` can return matching skills alongside memories and resources. This means the agent can discover relevant skills dynamically based on the conversation context, instead of having all skills injected into every system prompt.

**Current behavior**: All enabled skills are injected into the system prompt regardless of relevance.

**After integration**: Skills are injected via OpenViking search — only contextually relevant skills appear. A fallback ensures critical/always-on skills are still injected unconditionally.

---

## 11. Phase 7 — Gateway API Extensions

**Goal**: Extend the Gateway API with new endpoints for OpenViking-specific features while preserving backward compatibility on existing endpoints.

### 11.1 Existing Endpoints — Compatibility Layer

**File**: `src/gateway/routers/memory.py`

The existing endpoints continue to work by calling `get_memory_backend()`:

```python
@router.get("/memory")
async def get_memory() -> MemoryResponse:
    backend = get_memory_backend()
    data = backend.get_data()  # Returns legacy-format dict
    return MemoryResponse(**data)

@router.post("/memory/reload")
async def reload_memory() -> MemoryResponse:
    backend = get_memory_backend()
    data = backend.reload()
    return MemoryResponse(**data)
```

### 11.2 New OpenViking-Specific Endpoints

**New file**: `src/gateway/routers/openviking.py`

```python
router = APIRouter(prefix="/api/openviking", tags=["openviking"])

@router.get("/browse")
async def browse(uri: str = "viking://") -> BrowseResponse:
    """Browse the OpenViking filesystem."""

@router.get("/read")
async def read_entry(uri: str) -> ReadResponse:
    """Read content at a viking:// URI."""

@router.get("/search")
async def search(query: str, limit: int = 10) -> SearchResponse:
    """Semantic search across all context types."""

@router.post("/resources/add")
async def add_resource(request: AddResourceRequest) -> AddResourceResponse:
    """Ingest a resource into OpenViking."""

@router.get("/sessions")
async def list_sessions() -> SessionListResponse:
    """List all OpenViking sessions."""

@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> SessionResponse:
    """Get session details."""

@router.post("/sessions/{session_id}/commit")
async def commit_session(session_id: str) -> CommitResponse:
    """Manually trigger memory extraction for a session."""

@router.get("/health")
async def health() -> HealthResponse:
    """OpenViking health check."""
```

### 11.3 Register Router

**File**: `src/gateway/app.py`

```python
if get_memory_config().backend == "openviking":
    from src.gateway.routers.openviking import router as openviking_router
    app.include_router(openviking_router)
```

---

## 12. Phase 8 — Migration & Backward Compatibility

**Goal**: Provide a migration path from `memory.json` to OpenViking, and ensure seamless rollback.

### 12.1 Migration Script

**New file**: `src/agents/memory/migrate.py`

```python
def migrate_legacy_to_openviking(
    memory_json_path: str,
    openviking_data_path: str,
) -> MigrationReport:
    """
    Migrate existing memory.json data into OpenViking.

    Steps:
    1. Read memory.json
    2. Initialize OpenViking client
    3. Convert user context sections → viking://user/memories/profile/
    4. Convert facts → appropriate memory categories
    5. Convert history sections → viking://user/memories/events/
    6. Verify migration completeness
    7. Return report
    """
    # Read existing data
    with open(memory_json_path) as f:
        legacy_data = json.load(f)

    client = ov.OpenViking(path=openviking_data_path)

    # Migrate user context
    for section_name, uri_target in [
        ("workContext", "viking://user/memories/profile/work-context"),
        ("personalContext", "viking://user/memories/profile/personal-context"),
        ("topOfMind", "viking://user/memories/preferences/top-of-mind"),
    ]:
        content = legacy_data.get("user", {}).get(section_name, {}).get("summary", "")
        if content:
            client.write(uri_target, content)

    # Migrate facts
    category_map = {
        "preference": "viking://user/memories/preferences/",
        "knowledge": "viking://user/memories/entities/",
        "context": "viking://user/memories/events/",
        "behavior": "viking://agent/patterns/",
        "goal": "viking://user/memories/preferences/goals/",
    }
    for fact in legacy_data.get("facts", []):
        target_base = category_map.get(fact["category"], "viking://user/memories/entities/")
        uri = f"{target_base}{fact['id']}"
        client.write(uri, fact["content"])

    # Migrate history
    for section_name, uri_target in [
        ("recentMonths", "viking://user/memories/events/recent"),
        ("earlierContext", "viking://user/memories/events/earlier"),
        ("longTermBackground", "viking://user/memories/events/background"),
    ]:
        content = legacy_data.get("history", {}).get(section_name, {}).get("summary", "")
        if content:
            client.write(uri_target, content)

    client.wait_processed()  # Wait for semantic indexing
    client.close()

    return MigrationReport(
        facts_migrated=len(legacy_data.get("facts", [])),
        sections_migrated=6,
        success=True,
    )
```

### 12.2 CLI Migration Command

Add a management command (callable via the existing provisioner or as a standalone script):

```bash
python -m src.agents.memory.migrate \
  --source backend/.think-tank/memory.json \
  --target backend/.think-tank/openviking
```

### 12.3 Rollback Strategy

Since the feature flag (`memory.backend: "legacy"`) keeps the old system intact:

1. **memory.json is never deleted** — it continues to exist alongside OpenViking
2. **Setting `backend: "legacy"`** immediately reverts to the old system
3. **The `LegacyMemoryBackend`** is always available as a fallback
4. **OpenViking data** persists independently at `.think-tank/openviking/`

### 12.4 Dual-Write Mode (Optional)

For a cautious rollout, a `"dual"` backend mode can write to both systems simultaneously:

```yaml
memory:
  backend: "dual"  # Write to both, read from OpenViking
```

This provides a safety net where legacy memory.json stays updated as a backup while OpenViking is the primary read source.

---

## 13. Configuration Reference

### 13.1 Full `config.yaml` Memory Block

```yaml
memory:
  # Master switches
  enabled: true
  injection_enabled: true

  # Backend selection: "legacy" | "openviking" | "dual"
  backend: "openviking"

  # Legacy backend settings (always available for fallback)
  storage_path: ".think-tank/memory.json"
  debounce_seconds: 30
  model_name: null
  max_facts: 100
  fact_confidence_threshold: 0.7
  max_injection_tokens: 4000  # Increased from 2000 for L1 content

  # OpenViking backend settings
  openviking:
    # Storage
    data_path: ".think-tank/openviking"
    deployment_mode: "standalone"    # standalone | hybrid | http

    # HTTP mode (when deployment_mode is "http")
    http_url: null
    http_api_key: null

    # Embedding model (required)
    embedding_provider: "openai"
    embedding_model: "text-embedding-3-small"
    embedding_api_key: $OPENAI_API_KEY

    # Vision-Language Model (recommended for rich L0/L1 generation)
    vlm_provider: "openai"
    vlm_model: "gpt-4o-mini"
    vlm_api_key: $OPENAI_API_KEY

    # Reranker (optional, improves retrieval quality)
    rerank_provider: null
    rerank_model: null

    # Retrieval settings
    search_limit: 10
    l1_injection: true          # Use L1 overviews (true) or L0 abstracts (false)
    score_threshold: 0.3        # Minimum relevance score for injection

    # Session settings
    auto_commit_on_idle: true   # Commit session after idle timeout
    idle_commit_seconds: 60     # Seconds of inactivity before commit

    # Resource settings
    auto_ingest_uploads: true   # Auto-ingest uploaded files as resources
    sync_skills: true           # Sync SKILL.md files to OpenViking
```

### 13.2 OpenViking Internal Config

The OpenViking instance will be initialized with a generated `ov.conf` derived from the thinktank config. This is managed internally by `OpenVikingMemoryBackend.initialize()`:

```python
def _generate_ov_config(self) -> dict:
    """Generate ov.conf from thinktank config."""
    return {
        "embedding": {
            "provider": self._config.embedding_provider,
            "model": self._config.embedding_model,
            "api_key": self._config.embedding_api_key,
        },
        "vlm": {
            "provider": self._config.vlm_provider,
            "model": self._config.vlm_model,
            "api_key": self._config.vlm_api_key,
        } if self._config.vlm_provider else None,
        "agfs": {
            "backend": "localfs",
            "path": str(Path(self._config.data_path) / "agfs"),
        },
        "vectordb": {
            "backend": "local",
            "path": str(Path(self._config.data_path) / "vectordb"),
        },
    }
```

---

## 14. File Change Inventory

### 14.1 New Files

| File | Phase | Description |
|------|-------|-------------|
| `src/agents/memory/backend.py` | 1 | `MemoryBackend` protocol definition |
| `src/agents/memory/legacy_backend.py` | 1 | Adapter wrapping existing memory system |
| `src/agents/memory/openviking_backend.py` | 1-4 | OpenViking `MemoryBackend` implementation |
| `src/agents/memory/factory.py` | 1 | Backend factory with feature flag |
| `src/agents/memory/migrate.py` | 8 | Legacy → OpenViking migration script |
| `src/agents/memory/skill_sync.py` | 6 | Skill file synchronization |
| `src/agents/middlewares/openviking_session_middleware.py` | 2 | Session lifecycle middleware |
| `src/agents/tools/openviking_tools.py` | 5 | Agent tools for resource management |
| `src/gateway/routers/openviking.py` | 7 | New Gateway API endpoints |

### 14.2 Modified Files

| File | Phase | Changes |
|------|-------|---------|
| `backend/pyproject.toml` | 1 | Add `openviking>=0.1.17` dependency |
| `config.yaml` | 1 | Add `memory.backend` and `memory.openviking` block |
| `src/config/memory_config.py` | 1 | Add `OpenVikingConfig` model, `backend` field |
| `src/agents/memory/__init__.py` | 1 | Re-export new modules |
| `src/agents/lead_agent/agent.py` | 2, 3, 5 | Middleware chain update, tool registration, query passing |
| `src/agents/lead_agent/prompt.py` | 3 | Update `_get_memory_context()` to use backend abstraction |
| `src/agents/middlewares/memory_middleware.py` | 2 | Skip when OpenViking is active |
| `src/gateway/routers/memory.py` | 7 | Use backend abstraction for existing endpoints |
| `src/gateway/app.py` | 7 | Register OpenViking router |
| `src/gateway/routers/uploads.py` | 5 | Optional auto-ingest into OpenViking |

### 14.3 Unchanged Files

The following are explicitly **not modified**:
- All frontend files
- `src/agents/thread_state.py` (no new state fields needed)
- `src/sandbox/` (no sandbox changes)
- `src/subagents/` (subagents inherit the same memory backend)
- `src/mcp/` (no MCP changes)
- `src/skills/` (skills are read-only; synced to OpenViking, not modified)
- `extensions_config.json` (OpenViking is not an MCP server)

---

## 15. Risk Assessment & Mitigations

### 15.1 Performance Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| OpenViking `search()` latency exceeds the current inject time (~50ms) | Slower first-token time | Medium | Cache search results per turn; use `find()` (no intent analysis) for sub-100ms path |
| `session.commit()` blocks the middleware chain | Thread hangs during extraction | High | Run commit in background thread (same pattern as existing debounced queue) |
| Embedding API calls add cost per message | Higher operational cost | High | Batch embeddings; use smaller embedding model; cache embeddings locally |
| AGFS disk usage grows unbounded | Disk fills up | Low | Configure max storage; add periodic cleanup of old sessions |

### 15.2 Reliability Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| OpenViking Python package has breaking changes (v0.x) | Backend crashes | Medium | Pin version range (`>=0.1.17,<0.2`); add integration tests |
| Embedding model API is down | No retrieval, degraded injection | Medium | Fall back to legacy backend on OpenViking errors |
| Corrupt AGFS data | Memory loss | Low | Regular backups of `.think-tank/openviking/`; atomic writes via OpenViking |
| Race condition between session commit and new messages | Lost messages | Low | Session commit creates a new session; messages arriving during commit are queued |

### 15.3 Functional Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Intent analysis misclassifies queries | Irrelevant context injected | Medium | Monitor retrieval quality; tune score threshold; fall back to `find()` |
| Memory extraction produces low-quality memories | Noisy memory accumulation | Medium | Review extraction prompts; set quality thresholds; enable deduplication |
| Legacy API consumers break | Frontend errors | Low | `get_data()` maintains exact legacy format; full backward compatibility |

---

## 16. Testing Strategy

### 16.1 Unit Tests

| Test Suite | Covers | Location |
|------------|--------|----------|
| `test_memory_backend.py` | `MemoryBackend` protocol compliance | `tests/agents/memory/` |
| `test_legacy_backend.py` | Legacy adapter correctness | `tests/agents/memory/` |
| `test_openviking_backend.py` | OpenViking adapter (mocked client) | `tests/agents/memory/` |
| `test_factory.py` | Feature flag routing | `tests/agents/memory/` |
| `test_session_middleware.py` | Session lifecycle hooks | `tests/agents/middlewares/` |
| `test_openviking_tools.py` | Agent tool functions | `tests/agents/tools/` |
| `test_migrate.py` | Migration correctness | `tests/agents/memory/` |
| `test_skill_sync.py` | Skill synchronization | `tests/agents/memory/` |

### 16.2 Integration Tests

| Test | What It Validates |
|------|-------------------|
| Full conversation cycle | Thread creation → messages → memory commit → retrieval in next thread |
| Migration round-trip | Migrate legacy → verify OpenViking content → verify `get_data()` matches |
| Backend switch | Start with legacy → switch to OpenViking → verify continuity |
| Dual-write mode | Write to both → verify both backends have same data |
| Resource ingestion | Upload file → auto-ingest → search → find resource |
| Gateway API compat | All existing `/api/memory/*` endpoints return same schema |

### 16.3 Performance Benchmarks

| Metric | Current Baseline | Target with OpenViking |
|--------|-----------------|----------------------|
| Memory injection latency | ~50ms (file read + format) | <500ms (search + L1 read) |
| Memory update latency | ~2s (LLM extraction) | <5s (session commit + extraction) |
| Context relevance (manual eval) | N/A (no scoring) | >0.7 avg score in top-5 |
| Token efficiency | 2000 tokens / 15 facts | 2000 tokens / 1-2 L1 overviews (higher quality) |

---

## 17. Rollout Plan

### 17.1 Phase Timeline

| Phase | Description | Est. Effort | Dependencies |
|-------|-------------|-------------|--------------|
| **Phase 1** | Foundation layer (protocol, adapters, config) | 3-4 days | None |
| **Phase 2** | Session lifecycle middleware | 2-3 days | Phase 1 |
| **Phase 3** | Context-aware retrieval + prompt injection | 3-4 days | Phase 2 |
| **Phase 4** | Memory extraction pipeline | 2-3 days | Phase 2 |
| **Phase 5** | Resource management tools | 2-3 days | Phase 1 |
| **Phase 6** | Skills registry sync | 1-2 days | Phase 1 |
| **Phase 7** | Gateway API extensions | 2-3 days | Phase 4 |
| **Phase 8** | Migration + backward compat | 2-3 days | All above |

### 17.2 Deployment Sequence

```
Week 1-2: Phase 1 (Foundation)
  → Deploy with backend: "legacy" (no behavior change)
  → Validate: all existing tests pass

Week 2-3: Phase 2 + 3 (Sessions + Retrieval)
  → Deploy with backend: "openviking" in staging
  → Validate: context injection quality, latency

Week 3-4: Phase 4 + 5 (Extraction + Resources)
  → Validate: memory accumulation, resource search
  → Performance benchmarking

Week 4-5: Phase 6 + 7 (Skills + API)
  → Feature-complete in staging
  → Gateway API testing

Week 5-6: Phase 8 (Migration)
  → Run migration script on existing memory.json
  → A/B test: legacy vs OpenViking
  → Production rollout with dual-write mode
  → After validation period: switch default to "openviking"
```

### 17.3 Success Criteria

- [ ] All existing Gateway API endpoints return valid responses with OpenViking backend
- [ ] Memory injection latency stays under 500ms at p95
- [ ] Context relevance improves (measured by manual evaluation of top-5 retrieval results)
- [ ] Token efficiency: same or fewer tokens for higher-quality context
- [ ] Zero regressions in existing test suite
- [ ] Successful migration of existing `memory.json` data
- [ ] Clean rollback to legacy backend with `backend: "legacy"`
