# Auto Title Generation Implementation Summary

## Completed Work

### 1. Core implementation files

#### [`src/agents/thread_state.py`](../src/agents/thread_state.py)
- Added `title: str | None = None` to `ThreadState`

#### [`src/config/title_config.py`](../src/config/title_config.py) (new)
- Created `TitleConfig` config class
- Added config fields: enabled, max_words, max_chars, model_name, prompt_template
- Added `get_title_config()` and `set_title_config()` helpers
- Added `load_title_config_from_dict()` to load from config

#### [`src/agents/title_middleware.py`](../src/agents/title_middleware.py) (new)
- Created `TitleMiddleware`
- Implemented `_should_generate_title()` to check if a title should be generated
- Implemented `_generate_title()` to call the LLM
- Implemented `after_agent()` hook to trigger after the first exchange
- Added a fallback strategy (use first few words from user message if LLM fails)

#### [`src/config/app_config.py`](../src/config/app_config.py)
- Imported `load_title_config_from_dict`
- Loaded title config inside `from_file()`

#### [`src/agents/lead_agent/agent.py`](../src/agents/lead_agent/agent.py)
- Imported `TitleMiddleware`
- Registered it in the middleware list: `[SandboxMiddleware(), TitleMiddleware()]`

### 2. Config file

#### [`config.yaml`](../config.yaml)
- Added title config section:
```yaml
title:
  enabled: true
  max_words: 6
  max_chars: 60
  model_name: null
```

### 3. Documentation

#### [`docs/AUTO_TITLE_GENERATION.md`](../docs/AUTO_TITLE_GENERATION.md) (new)
- Full feature documentation
- Implementation details and architecture
- Configuration guide
- Client usage examples (TypeScript)
- Workflow diagram (Mermaid)
- Troubleshooting guide
- State vs Metadata comparison

#### [`BACKEND_TODO.md`](../BACKEND_TODO.md)
- Added feature completion record

### 4. Tests

#### [`tests/test_title_generation.py`](../tests/test_title_generation.py) (new)
- Config class tests
- Middleware initialization tests
- TODO: integration tests (needs mock Runtime)

---

## Core Design Decisions

### Why use State instead of Metadata?

| Aspect | State (chosen) | Metadata (not chosen) |
|--------|----------------|-----------------------|
| Persistence | Automatic (via checkpointer) | Implementation-dependent |
| Versioning | Supports time travel | Not supported |
| Type safety | TypedDict | Arbitrary dict |
| Standardization | LangGraph core mechanism | Extension feature |

### Workflow

```
User sends the first message
  ↓
Agent processes and returns a reply
  ↓
TitleMiddleware.after_agent() triggers
  ↓
Check: first exchange? title already set?
  ↓
Call LLM to generate title
  ↓
Return {"title": "..."} and update state
  ↓
Checkpointer persists automatically (if configured)
  ↓
Client reads from state.values.title
```

---

## Usage Guide

### Backend configuration

1. **Enable/disable the feature**
```yaml
# config.yaml
title:
  enabled: true  # set false to disable
```

2. **Custom configuration**
```yaml
title:
  enabled: true
  max_words: 8      # max words in title
  max_chars: 80     # max characters in title
  model_name: null  # use default model
```

3. **Persistence (optional)**

If you need title persistence in local development:

```python
# checkpointer.py
from langgraph.checkpoint.sqlite import SqliteSaver

checkpointer = SqliteSaver.from_conn_string("checkpoints.db")
```

```json
// langgraph.json
{
  "graphs": {
    "lead_agent": "src.agents:lead_agent"
  },
  "checkpointer": "checkpointer:checkpointer"
}
```

### Client usage

```typescript
// Get thread title
const state = await client.threads.getState(threadId);
const title = state.values.title || "New Conversation";

// Render in the conversation list
<li>{title}</li>
```

**Note**: The title is stored at `state.values.title`, not `thread.metadata.title`.

---

## Tests

```bash
# Run a single test file
pytest tests/test_title_generation.py -v

# Run all tests
pytest
```

---

## Troubleshooting

### Title is not generated

1. Check config: `title.enabled = true`
2. Check logs: search for "Generated thread title"
3. Confirm first exchange only (1 user message + 1 assistant reply)

### Title generated but not visible

1. Verify read location: `state.values.title` (not `thread.metadata.title`)
2. Ensure API response includes title
3. Re-fetch state

### Title missing after restart

1. Local development requires a checkpointer
2. LangGraph Platform persists automatically
3. Check database to confirm checkpointer is working

---

## Performance Impact

- **Added latency**: ~0.5-1 seconds (LLM call)
- **Concurrency safety**: runs in `after_agent`, does not block the main flow
- **Resource usage**: each thread generates only once

### Optimization suggestions

1. Use a faster model (e.g. `gpt-3.5-turbo`)
2. Reduce `max_words` and `max_chars`
3. Simplify the prompt

---

## Next Steps

- [ ] Add integration tests (requires mock LangGraph Runtime)
- [ ] Support custom prompt templates
- [ ] Support multi-language title generation
- [ ] Add title regeneration
- [ ] Monitor title success rate and latency

---

## Resources

- [Full documentation](../docs/AUTO_TITLE_GENERATION.md)
- [LangGraph Middleware](https://langchain-ai.github.io/langgraph/concepts/middleware/)
- [LangGraph State Management](https://langchain-ai.github.io/langgraph/concepts/low_level/#state)
- [LangGraph Checkpointer](https://langchain-ai.github.io/langgraph/concepts/persistence/)

---

*Implementation completed: 2026-01-14*
