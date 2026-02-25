# Thinktank.ai Multi-User Web Platform: Deployment Design Document

**Version:** 1.0
**Date:** 2026-02-23
**Status:** Draft

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Architecture Assessment](#2-current-architecture-assessment)
3. [Multi-User Gap Analysis](#3-multi-user-gap-analysis)
4. [Target Architecture](#4-target-architecture)
5. [Implementation Plan](#5-implementation-plan)
   - [Phase 1: Authentication & User Isolation](#phase-1-authentication--user-isolation)
   - [Phase 2: Database Migration](#phase-2-database-migration)
   - [Phase 3: Sandbox Isolation](#phase-3-sandbox-isolation)
   - [Phase 4: Horizontal Scaling](#phase-4-horizontal-scaling)
   - [Phase 5: Frontend Web Deployment](#phase-5-frontend-web-deployment)
   - [Phase 6: Security Hardening](#phase-6-security-hardening)
   - [Phase 7: Monitoring & Observability](#phase-7-monitoring--observability)
   - [Phase 8: S3 Object Storage Migration](#phase-8-s3-object-storage-migration)
6. [Production Infrastructure](#6-production-infrastructure)
7. [Resource Sizing & Capacity Planning](#7-resource-sizing--capacity-planning)
8. [Server Recommendations](#8-server-recommendations)
9. [Production Docker Compose](#9-production-docker-compose)
10. [Production Nginx Configuration](#10-production-nginx-configuration)
11. [TODO Checklist](#11-todo-checklist)
12. [Testing Plan](#12-testing-plan)

---

## 1. Executive Summary

This document details the design for transforming Thinktank.ai from a single-user
Electron desktop application into a multi-user web platform, analogous to OpenAI's
ChatGPT. The goal is for many users to simultaneously use the backend agent system
without information leakage, resource contention, or interference between sessions.

The current system is a LangGraph-based agent backend with a FastAPI gateway,
Nginx reverse proxy, and a Vite/React + Electron frontend. It uses file-based
persistence, has no authentication, shares a single global memory file, and
executes sandboxed commands directly on the host. Each of these is a critical
blocker for multi-user deployment.

The plan is structured in 7 phases with a prioritized TODO checklist and
comprehensive testing strategy.

---

## 2. Current Architecture Assessment

### 2.1 Service Topology

```
                    +------------------+
  User (Electron) --> Nginx :2026      |
                    | (reverse proxy)  |
                    +--+-----+-----+--+
                       |     |     |
              +--------+     |     +--------+
              v              v              v
        Frontend:3000  Gateway:8001  LangGraph:2024
        (Vite/React)   (FastAPI)     (Agent engine)
                                          |
                                     +----+
                                     v
                               LocalSandbox
                             (host execution)
```

### 2.2 Key Components

| Component | Technology | Port | Role |
|-----------|-----------|------|------|
| **Nginx** | nginx:alpine | 2026 | Reverse proxy, CORS, path-based routing |
| **Frontend** | Vite + React + Electron | 3000 | User interface (SPA) |
| **Gateway** | FastAPI + Uvicorn | 8001 | REST API for config, uploads, models, memory |
| **LangGraph** | LangGraph Server | 2024 | Agent orchestration, SSE streaming, checkpoints |
| **Sandbox** | `LocalSandboxProvider` | N/A | Shell execution directly on host |
| **Provisioner** | Custom Python service | 8002 | Kubernetes-based sandbox pod management (optional) |

### 2.3 Data Storage (All File-Based)

| Data | Location | Format |
|------|----------|--------|
| Memory | `backend/.think-tank/memory.json` | Single JSON file (global) |
| API Keys | `backend/.think-tank/api-keys.json` | Encrypted JSON (keyed by device ID) |
| Master Key | `backend/.think-tank/api-keys.key` | Fernet key (plaintext file) |
| Thread Data | `backend/.think-tank/threads/{thread_id}/user-data/` | Directories per thread |
| Uploads | `backend/.think-tank/threads/{thread_id}/user-data/uploads/` | Binary files |
| Artifacts | `backend/.think-tank/threads/{thread_id}/user-data/outputs/` | Generated files |
| Timeline | `.../{thread_id}/user-data/outputs/agent_timeline.json` | JSON log |
| LangGraph Checkpoints | `backend/.langgraph_api/.langgraph_checkpoint.*.pckl` | Pickle files |
| Config | `config.yaml`, `extensions_config.json` | YAML / JSON |
| Environment | `.env`, `frontend/.env` | Dotenv |

### 2.4 Concurrency Mechanisms

| Component | Mechanism | Scope |
|-----------|-----------|-------|
| Memory queue | `threading.Lock()` + debounced timer | Per-process singleton |
| API key store | `threading.Lock()` | Per-process singleton |
| Timeline logging | `threading.Lock()` (`_WRITE_LOCK`) | Per-process, atomic writes |
| Subagent tasks | `threading.Lock()` + `ThreadPoolExecutor(3)` | Global, 3 scheduler + 3 exec workers |
| File I/O | Atomic temp-file + `os.replace()` | Per-file |
| LangGraph checkpoints | Built-in pickle persistence | Per-process |

---

## 3. Multi-User Gap Analysis

### 3.1 Critical Gaps (Must Fix Before Any Multi-User Deployment)

| # | Area | Current State | Risk | Severity |
|---|------|--------------|------|----------|
| G1 | **Authentication** | None. `x-device-id` header is spoofable. No login/register. | Any client can impersonate any device | **CRITICAL** |
| G2 | **Memory isolation** | Single global `memory.json`. All conversations update the same file. | User A's personal context, facts, and work history are visible to User B | **CRITICAL** |
| G3 | **Thread ownership** | No mapping of `thread_id` to user. Any client can read/write any thread. | Complete data exposure across users | **CRITICAL** |
| G4 | **Sandbox security** | `LocalSandboxProvider` runs `subprocess.run(command, shell=True)` on host | Users can execute arbitrary commands on the server, read/write any file | **CRITICAL** |

### 3.2 High-Priority Gaps (Required for Production)

| # | Area | Current State | Risk | Severity |
|---|------|--------------|------|----------|
| G5 | **CORS policy** | `Access-Control-Allow-Origin: *` in nginx.conf | Any website can make requests to the API | HIGH |
| G6 | **LangGraph checkpoints** | Local pickle files, not user-scoped | Cannot scale to multiple instances; no user isolation at checkpoint level | HIGH |
| G7 | **API key store** | Keyed by `device_id` in a single encrypted file | No user association; no per-user encryption boundary | HIGH |
| G8 | **Subagent pools** | Global `ThreadPoolExecutor(max_workers=3)` in `executor.py` | 3 concurrent subagent slots shared across ALL users globally | HIGH |
| G9 | **File uploads** | No size quotas per user, no ownership validation | Users could exhaust disk; any user can access any thread's uploads | HIGH |
| G10 | **Memory queue** | In-process singleton `MemoryUpdateQueue` with debounced timer | Cannot work across multiple backend instances; not user-scoped | HIGH |

### 3.3 Medium-Priority Gaps (For Robust Production)

| # | Area | Current State | Risk | Severity |
|---|------|--------------|------|----------|
| G11 | **Rate limiting** | None | Users can spam LLM calls, exhausting API budgets | MEDIUM |
| G12 | **HTTPS** | No TLS configuration | Traffic is unencrypted | MEDIUM |
| G13 | **Logging** | Mix of `print()` and `logging.info()` | No structured logging, no log aggregation, PII leakage risk | MEDIUM |
| G14 | **Config isolation** | Single `extensions_config.json` for MCP/skills | All users share the same tool configuration | MEDIUM |
| G15 | **Monitoring** | Only `/health` endpoint | No metrics, no alerting, no tracing | MEDIUM |

---

## 4. Target Architecture

### 4.1 Production Architecture Diagram

```
                          +-------------------+
                          |   CDN / Edge      |
                          |   (Cloudflare     |
                          |    Pages/Vercel)  |
                          |   Static Frontend |
                          +--------+----------+
                                   |
                          +--------v----------+
                          |  Load Balancer    |
                          |  (Nginx / ALB /   |
                          |   Traefik)        |
                          |  TLS termination  |
                          +--+------+------+--+
                             |      |      |
               +-------------+      |      +-------------+
               v                    v                     v
      +----------------+   +----------------+   +------------------+
      | Gateway x N    |   | LangGraph x N  |   | Workers x N      |
      | (FastAPI +     |   | (Agent SSE,    |   | (Memory updates,  |
      |  Gunicorn)     |   |  checkpoints)  |   |  subagent tasks,  |
      | - Auth (JWT)   |   | - Streaming    |   |  async jobs)      |
      | - REST API     |   | - Agent exec   |   |                   |
      | - Uploads      |   | - PG checkpts  |   |                   |
      +-------+--------+   +-------+--------+   +--------+---------+
              |                     |                      |
              +----------+----------+----------------------+
                         |
              +----------v-----------+     +--------------+
              |   PostgreSQL         |     |    Redis      |
              |   - users            |     |  - Sessions   |
              |   - threads          |     |  - Task queue |
              |   - user_memory      |     |  - Rate limits|
              |   - user_api_keys    |     |  - Cache      |
              |   - langgraph chkpt  |     +--------------+
              +----------+-----------+
                         |
              +----------v-----------+
              |  Object Storage      |
              |  (S3 / MinIO)        |
              |  - File uploads      |
              |  - Thread artifacts  |
              |  - Sandbox outputs   |
              +----------+-----------+
                         |
              +----------v-----------+
              |  Kubernetes Cluster  |
              |  (Sandbox Pods)      |
              |  - 1 Pod per session |
              |  - CPU/RAM limits    |
              |  - Network isolation |
              +----------------------+
```

### 4.2 Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Auth strategy | JWT (access + refresh tokens) | Stateless, works with horizontally scaled backends |
| Database | PostgreSQL | LangGraph has native PostgreSQL checkpointing support; robust ACID for user data |
| Cache / queue | Redis | Session store, rate limiting, distributed task queue (Celery or RQ) |
| Object storage | S3-compatible (S3 / MinIO) | Decouples file storage from compute instances |
| Sandbox isolation | Container-based via `AioSandboxProvider` + provisioner | Per-user containers with resource limits; existing provisioner code available |
| Frontend deployment | Static build on CDN | Decouples frontend from backend scaling; instant global availability |
| Streaming | SSE (existing) with sticky sessions | Already implemented; sticky sessions ensure stream continuity |

---

## 5. Implementation Plan

### Phase 1: Authentication & User Isolation

**Addresses:** G1 (auth), G2 (memory isolation), G3 (thread ownership), G7 (API key store)

#### 1.1 Backend Authentication Module

Create `backend/src/gateway/auth/`:

```
backend/src/gateway/auth/
  __init__.py
  models.py          # User SQLAlchemy model, Pydantic schemas
  jwt.py             # JWT creation, validation, refresh logic
  middleware.py       # FastAPI dependency: extract & verify JWT
  routes.py          # POST /api/auth/register, /login, /refresh, /me
  password.py         # bcrypt hashing utilities
```

**JWT Design:**

| Token | Lifetime | Storage | Purpose |
|-------|----------|---------|---------|
| Access token | 15 minutes | `Authorization: Bearer <token>` header | API authentication |
| Refresh token | 7 days | `httpOnly` secure cookie | Silent token renewal |

**Auth middleware** (`get_current_user` FastAPI dependency):
- Extracts `Authorization: Bearer <token>` header
- Verifies JWT signature (RS256 asymmetric keys)
- Returns `user_id` or raises `401 Unauthorized`
- Applied to all protected routes

**Routes:**

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/api/auth/register` | POST | Public | Create new account (email + password) |
| `/api/auth/login` | POST | Public | Authenticate, return access + refresh tokens |
| `/api/auth/refresh` | POST | Cookie | Issue new access token |
| `/api/auth/me` | GET | JWT | Return current user profile |
| `/api/auth/logout` | POST | JWT | Invalidate refresh token |

#### 1.2 Per-User Memory Isolation

**Current:** Single global `backend/.think-tank/memory.json`
**Target:** Per-user memory, either as database rows or scoped files.

**Changes to `backend/src/agents/memory/updater.py`:**

- `_get_memory_file_path()` -> `_get_memory_file_path(user_id: str)` (short-term, file-based)
- Long-term: replace with `SELECT memory_json FROM user_memory WHERE user_id = ?`
- Memory path: `backend/.think-tank/memory/{user_id}.json` (file-based interim)

**Changes to `backend/src/agents/memory/queue.py`:**

- `ConversationContext` gains a `user_id: str` field
- Queue deduplication key becomes `(user_id, thread_id)` instead of just `thread_id`
- `MemoryUpdater.update_memory()` receives `user_id` and loads/saves to user-specific storage

**Changes to `backend/src/agents/middlewares/memory_middleware.py`:**

- Extract `user_id` from `runtime.context` (set by auth middleware in LangGraph config)
- Pass `user_id` to `queue.add(user_id=..., thread_id=..., messages=...)`

#### 1.3 Thread Ownership Enforcement

**New data model** (PostgreSQL table or JSON index):

```sql
CREATE TABLE threads (
    thread_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    title TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_threads_user_id ON threads(user_id);
```

**Enforcement points:**

| Endpoint | Validation |
|----------|-----------|
| LangGraph thread creation | Record ownership in `threads` table |
| `GET /api/threads/search` | Filter by `WHERE user_id = :current_user` |
| `POST /api/threads/{id}/uploads` | Verify `thread.user_id == current_user` |
| `GET /api/threads/{id}/artifacts/*` | Verify `thread.user_id == current_user` |
| LangGraph streaming (`/api/langgraph/threads/{id}/runs/stream`) | Verify ownership before proxying |

**Gateway-level proxy validation:**

Add a middleware in the Nginx config (or a FastAPI middleware for `/api/langgraph/*`)
that intercepts thread-scoped requests, extracts the `thread_id` from the URL path,
queries the `threads` table, and returns `403 Forbidden` if the thread does not belong
to the authenticated user.

#### 1.4 API Key Store Migration

**Current:** `backend/src/security/api_key_store.py` keys by `device_id`
**Target:** Key by `user_id`

**Changes:**
- Replace all `device_id` parameters with `user_id`
- Remove `x-device-id` header dependency
- Long-term: store in `user_api_keys` PostgreSQL table with per-row encryption

```sql
CREATE TABLE user_api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    provider VARCHAR(64) NOT NULL,
    encrypted_key TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, provider)
);
```

#### 1.5 Frontend Authentication UI

**New files:**

```
frontend/src/pages/Login.tsx
frontend/src/pages/Register.tsx
frontend/src/core/auth/
  AuthContext.tsx        # React context providing user state
  AuthProvider.tsx       # Wraps app, manages JWT lifecycle
  useAuth.ts            # Hook: login(), logout(), user, isAuthenticated
  ProtectedRoute.tsx    # Route wrapper redirecting to /login if unauthenticated
  api.ts                # Auth API calls (register, login, refresh)
```

**Integration:**
- Wrap `<RouterProvider>` in `<AuthProvider>`
- All routes except `/login`, `/register`, `/` (landing) wrapped in `<ProtectedRoute>`
- Add `Authorization: Bearer <token>` to all API calls via a fetch/axios interceptor
- Token refresh on 401 response (transparent retry)

---

### Phase 2: Database Migration

**Addresses:** G6 (checkpoints), G10 (memory queue), persistence durability

#### 2.1 PostgreSQL Schema

```sql
-- Users (from Phase 1)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(128),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Thread ownership (from Phase 1)
CREATE TABLE threads (
    thread_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_threads_user_id ON threads(user_id);

-- Per-user memory
CREATE TABLE user_memory (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    memory_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Per-user API keys (encrypted)
CREATE TABLE user_api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(64) NOT NULL,
    encrypted_key TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, provider)
);

-- Upload metadata
CREATE TABLE uploads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id UUID NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    filename VARCHAR(512) NOT NULL,
    content_type VARCHAR(128),
    size_bytes BIGINT,
    storage_path TEXT NOT NULL,  -- S3 key or filesystem path
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_uploads_thread_id ON uploads(thread_id);

-- Agent timeline events (append-only log per thread)
CREATE TABLE timeline_events (
    id BIGSERIAL PRIMARY KEY,
    thread_id UUID NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
    event_type VARCHAR(64) NOT NULL,   -- 'message', 'history_truncated'
    stage VARCHAR(32),                 -- 'before_model', 'after_model', 'after_agent'
    message_index INT,
    role VARCHAR(32),                  -- 'human', 'ai', 'tool'
    message_id TEXT,
    message_data JSONB,                -- serialized message content
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_timeline_thread_id ON timeline_events(thread_id);
CREATE INDEX idx_timeline_created_at ON timeline_events(created_at);

-- Rate limiting / usage tracking
CREATE TABLE usage_log (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    thread_id UUID,
    model_name VARCHAR(128),
    input_tokens INT DEFAULT 0,
    output_tokens INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_usage_log_user_id ON usage_log(user_id);
CREATE INDEX idx_usage_log_created_at ON usage_log(created_at);

-- LangGraph checkpoints are managed by langgraph-checkpoint-postgres
-- (auto-creates its own tables)
```

#### 2.2 Database Dependencies

Add to `backend/pyproject.toml`:

```toml
dependencies = [
    # ... existing ...
    "langgraph-checkpoint-postgres>=2.0.0",
    "asyncpg>=0.30.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "alembic>=1.14.0",
    "bcrypt>=4.2.0",
    "PyJWT>=2.10.0",
    "cryptography>=44.0.0",
]
```

#### 2.3 Database Connection Module

Create `backend/src/db/`:

```
backend/src/db/
  __init__.py
  engine.py           # SQLAlchemy async engine + session factory
  models.py           # ORM models (User, Thread, UserMemory, etc.)
  migrations/         # Alembic migration directory
    env.py
    versions/
      001_initial_schema.py
```

**Configuration** (`.env`):

```env
DATABASE_URL=postgresql+asyncpg://thinktank:password@localhost:5432/thinktank
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=...         # or path to RS256 private key
JWT_ALGORITHM=RS256
```

#### 2.4 LangGraph Checkpoint Migration

**Current:** `backend/.langgraph_api/.langgraph_checkpoint.*.pckl`
**Target:** PostgreSQL via `langgraph-checkpoint-postgres`

Update `backend/langgraph.json`:

```json
{
  "$schema": "https://langgra.ph/schema.json",
  "dependencies": ["."],
  "env": ".env",
  "graphs": {
    "lead_agent": "src.agents:make_lead_agent"
  },
  "store": {
    "type": "postgres",
    "uri": "$DATABASE_URL"
  }
}
```

This enables:
- Multiple LangGraph instances sharing checkpoints
- Thread state accessible from any backend replica
- Proper user-scoped checkpoint cleanup

---

### Phase 3: Sandbox Isolation

**Addresses:** G4 (sandbox security)

#### 3.1 Switch from LocalSandboxProvider to AioSandboxProvider

The `LocalSandboxProvider` (at `backend/src/sandbox/local/local_sandbox.py`) runs
`subprocess.run(command, shell=True)` directly on the host. This gives users
unrestricted access to the server's filesystem, processes, and network.

**Change in `config.yaml`:**

```yaml
# BEFORE (DANGEROUS for multi-user):
sandbox:
  use: src.sandbox.local:LocalSandboxProvider

# AFTER (container-isolated):
sandbox:
  use: src.community.aio_sandbox:AioSandboxProvider
  provisioner_url: http://provisioner:8002
```

#### 3.2 Container Resource Limits

Configure the provisioner to enforce per-sandbox limits:

| Resource | Limit | Rationale |
|----------|-------|-----------|
| CPU | 1 core | Prevent single user from monopolizing CPU |
| Memory | 512 MiB | Enough for Python/Node scripts, prevents OOM |
| Disk | 5 GiB ephemeral | Prevents disk exhaustion |
| Network | Egress-only, no host network | Prevents lateral movement |
| Timeout | 15 minutes idle | Auto-cleanup unused sandboxes |
| PID limit | 256 | Prevents fork bombs |

#### 3.3 Sandbox Lifecycle

```
User starts chat  -->  LangGraph assigns thread_id
                  -->  SandboxMiddleware calls provisioner
                  -->  Provisioner creates K8s Pod with limits
                  -->  Tools execute inside container
                  -->  On timeout/disconnect: Pod garbage-collected
```

---

### Phase 4: Horizontal Scaling

**Addresses:** G8 (subagent pools), G10 (memory queue), high availability

#### 4.1 Gateway Scaling

The Gateway is already stateless. Run multiple replicas with Gunicorn:

```bash
gunicorn src.gateway.app:app \
  -w 4 \                          # 4 worker processes
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8001 \
  --timeout 120 \
  --graceful-timeout 30
```

#### 4.2 LangGraph Scaling with Sticky Sessions

SSE streams must stay on the same backend instance for their duration.
Configure Nginx upstream with `ip_hash` or cookie-based affinity:

```nginx
upstream langgraph {
    ip_hash;  # or use sticky cookie
    server langgraph-1:2024;
    server langgraph-2:2024;
}
```

#### 4.3 Subagent Pool Scaling

**Current bottleneck** in `backend/src/subagents/executor.py`:

```python
# Global, shared by ALL users:
_scheduler_pool = ThreadPoolExecutor(max_workers=3)
_execution_pool = ThreadPoolExecutor(max_workers=3)
```

**Changes:**
1. Increase `max_workers` to `os.cpu_count() * 2` (e.g., 16 on an 8-core machine)
2. Add a per-user concurrency semaphore (max 3 concurrent subagents per user, not global)
3. Long-term: offload to Celery + Redis for cross-instance distribution

```python
import os
from collections import defaultdict
from threading import Semaphore

_PER_USER_SEMAPHORES: dict[str, Semaphore] = defaultdict(lambda: Semaphore(3))
_scheduler_pool = ThreadPoolExecutor(
    max_workers=max(8, os.cpu_count() * 2),
    thread_name_prefix="subagent-scheduler-",
)
_execution_pool = ThreadPoolExecutor(
    max_workers=max(8, os.cpu_count() * 2),
    thread_name_prefix="subagent-exec-",
)
```

#### 4.4 Memory Queue Distribution

**Current:** In-process singleton `MemoryUpdateQueue` (works only within one process).

**Target:** Redis-based task queue:

```python
# Instead of in-process timer:
import redis
from rq import Queue

redis_conn = redis.from_url(os.environ["REDIS_URL"])
memory_queue = Queue("memory_updates", connection=redis_conn)

def queue_memory_update(user_id: str, thread_id: str, messages: list):
    memory_queue.enqueue(
        "src.agents.memory.updater.update_memory_from_conversation",
        user_id=user_id,
        messages=messages,
        thread_id=thread_id,
        job_timeout=120,
    )
```

Run a dedicated worker process: `rq worker memory_updates`

---

### Phase 5: Frontend Web Deployment

#### 5.1 Build as Static SPA

The frontend already supports web mode via `vite --mode web`:

```bash
cd frontend
VITE_BACKEND_BASE_URL=https://api.yourdomain.com \
VITE_LANGGRAPH_BASE_URL=https://api.yourdomain.com/api/langgraph \
pnpm build
# Output: dist/ (static HTML/JS/CSS)
```

The `env.ts` file detects Electron vs. web via `window.electronAPI`:

```typescript
// frontend/src/env.ts
const isElectron = typeof window !== "undefined" && window.electronAPI !== undefined;
```

This means Electron-specific code paths are already gated. The web build works out
of the box.

#### 5.2 Deploy Static Files

**Option A: Cloudflare Pages** (recommended for simplicity)
- Connect GitHub repo, set build command: `cd frontend && pnpm build`
- Set output directory: `frontend/dist`
- Configure SPA fallback: all routes -> `index.html`
- Free tier covers most use cases

**Option B: Self-hosted Nginx**
- Serve `dist/` from Nginx with `try_files $uri $uri/ /index.html`
- Cache static assets with `Cache-Control: max-age=31536000, immutable`

#### 5.3 Keep Electron as Desktop Distribution

The Electron app continues to work as a desktop client pointing to the same
backend API. Users choose between:
- **Web app** at `https://app.yourdomain.com`
- **Desktop app** (Electron) downloadable from the website

---

### Phase 6: Security Hardening

#### 6.1 HTTPS / TLS

- TLS termination at load balancer (Let's Encrypt via certbot or managed cert)
- HTTP -> HTTPS redirect
- HSTS header: `Strict-Transport-Security: max-age=63072000; includeSubDomains`

#### 6.2 CORS Lockdown

**Current** (in `docker/nginx/nginx.conf`):

```nginx
add_header 'Access-Control-Allow-Origin' '*' always;
```

**Target:**

```nginx
add_header 'Access-Control-Allow-Origin' 'https://app.yourdomain.com' always;
add_header 'Access-Control-Allow-Credentials' 'true' always;
```

#### 6.3 Rate Limiting

Implement at two levels:

**Nginx level** (connection-based):

```nginx
limit_req_zone $binary_remote_addr zone=api:10m rate=60r/m;
limit_req_zone $binary_remote_addr zone=auth:10m rate=10r/m;

location /api/ {
    limit_req zone=api burst=20 nodelay;
}

location /api/auth/ {
    limit_req zone=auth burst=5 nodelay;
}
```

**Application level** (user-based, via Redis):

```python
# Per-user: max 20 LLM calls per minute
async def check_rate_limit(user_id: str) -> bool:
    key = f"rate:{user_id}:{int(time.time()) // 60}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 120)
    return count <= 20
```

#### 6.4 Input Validation & Sanitization

- All user inputs validated via Pydantic models (already in place for most routes)
- File upload validation: check MIME type, enforce extension allowlist
- Sandbox command injection: handled by container isolation (Phase 3)
- SQL injection: use SQLAlchemy ORM with parameterized queries exclusively

#### 6.5 Secrets Management

| Secret | Current Location | Target |
|--------|-----------------|--------|
| LLM API keys | `.env` file | Environment variables from secrets manager (AWS Secrets Manager, Vault) |
| Master encryption key | `.think-tank/api-keys.key` | Secrets manager or KMS |
| JWT signing keys | N/A (to be created) | RS256 keypair in secrets manager |
| Database password | `.env` file | Secrets manager |

---

### Phase 7: Monitoring & Observability

#### 7.1 Structured Logging

Replace all `print()` calls with proper `logging`:

```python
# BEFORE (found in memory/updater.py, memory/queue.py, api_key_store.py):
print(f"Memory saved to {file_path}")

# AFTER:
logger.info("Memory saved", extra={"file_path": str(file_path), "user_id": user_id})
```

**Log format:** JSON structured logging via `python-json-logger`:

```python
import logging
from pythonjsonlogger import jsonlogger

handler = logging.StreamHandler()
handler.setFormatter(jsonlogger.JsonFormatter(
    "%(asctime)s %(name)s %(levelname)s %(message)s"
))
logging.root.addHandler(handler)
```

#### 7.2 Metrics (Prometheus)

Add `prometheus-fastapi-instrumentator` to Gateway:

```python
from prometheus_fastapi_instrumentator import Instrumentator

Instrumentator().instrument(app).expose(app, endpoint="/metrics")
```

**Key metrics to track:**

| Metric | Type | Purpose |
|--------|------|---------|
| `http_requests_total` | Counter | Request volume per endpoint |
| `http_request_duration_seconds` | Histogram | Latency distribution |
| `active_sse_connections` | Gauge | Current streaming connections |
| `llm_calls_total` | Counter | LLM API calls by model and user |
| `llm_call_duration_seconds` | Histogram | LLM response latency |
| `llm_tokens_total` | Counter | Token consumption (input + output) |
| `active_sandboxes` | Gauge | Running sandbox containers |
| `subagent_tasks_total` | Counter | Subagent executions by status |
| `memory_updates_total` | Counter | Memory update operations |

#### 7.3 Distributed Tracing

Enable LangSmith tracing for production LLM calls:

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=...
LANGCHAIN_PROJECT=thinktank-production
```

#### 7.4 Health Checks

Enhance `/health` endpoint:

```python
@app.get("/health")
async def health_check():
    checks = {
        "gateway": "healthy",
        "database": await check_db_connection(),
        "redis": await check_redis_connection(),
        "langgraph": await check_langgraph_health(),
    }
    status = "healthy" if all(v == "healthy" for v in checks.values()) else "degraded"
    return {"status": status, "checks": checks}
```

#### 7.5 Alerting Rules

| Alert | Condition | Severity |
|-------|-----------|----------|
| High error rate | HTTP 5xx > 5% over 5 min | Critical |
| High latency | P99 > 30s over 5 min | Warning |
| Database connection failure | Health check fails | Critical |
| Disk usage | > 80% | Warning |
| LLM API errors | > 10 failures in 1 min | Warning |
| Memory exhaustion | RSS > 80% of limit | Warning |

---

### Phase 8: S3 Object Storage Migration

**Addresses:** G9 (file upload isolation at scale), horizontal scaling file storage dependency

**Prerequisite:** Phase 4 (Horizontal Scaling) — S3 becomes necessary when multiple Gateway/LangGraph
replicas cannot share a local filesystem. Single-VM deployments work fine with local disk.

#### 8.1 Motivation

The current architecture stores all user files on the local filesystem under
`.think-tank/threads/{thread_id}/user-data/`. This works for single-VM deployments but creates
two blockers for horizontal scaling:

1. **Multi-instance file access** — Gateway replica A cannot serve a file uploaded via replica B
2. **Disk capacity** — local NVMe fills up faster than object storage, and cannot be resized without downtime

Migrating to S3-compatible object storage (AWS S3, MinIO, Cloudflare R2) decouples file
persistence from compute instances and enables unlimited storage scaling.

#### 8.2 Storage Abstraction Layer

Create `backend/src/storage/` module with a pluggable backend interface:

```
backend/src/storage/
  __init__.py
  base.py             # StorageBackend abstract base class
  local.py            # LocalStorageBackend (current filesystem behavior)
  s3.py               # S3StorageBackend (boto3/aiobotocore)
  factory.py          # get_storage_backend() factory based on env config
```

**Interface (`base.py`):**

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator

class StorageBackend(ABC):
    """Abstract interface for file storage operations."""

    @abstractmethod
    async def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        """Store a file. Returns the storage key."""

    @abstractmethod
    async def get(self, key: str) -> bytes:
        """Retrieve a file by key."""

    @abstractmethod
    async def get_stream(self, key: str) -> AsyncIterator[bytes]:
        """Stream a file by key (for large files)."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a file by key."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a file exists."""

    @abstractmethod
    async def list_keys(self, prefix: str) -> list[str]:
        """List all keys under a prefix."""

    @abstractmethod
    async def get_size(self, key: str) -> int:
        """Get file size in bytes."""

    @abstractmethod
    async def get_total_size(self, prefix: str) -> int:
        """Sum of all file sizes under a prefix (for quota tracking)."""

    @abstractmethod
    async def get_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate a presigned URL for direct client download (S3 only)."""
```

**Factory (`factory.py`):**

```python
import os
from src.storage.base import StorageBackend

_backend: StorageBackend | None = None

def get_storage_backend() -> StorageBackend:
    """Return the configured storage backend (singleton)."""
    global _backend
    if _backend is None:
        if os.environ.get("S3_BUCKET"):
            from src.storage.s3 import S3StorageBackend
            _backend = S3StorageBackend(
                bucket=os.environ["S3_BUCKET"],
                region=os.environ.get("S3_REGION", "us-east-1"),
                endpoint_url=os.environ.get("S3_ENDPOINT_URL"),  # MinIO
                prefix=os.environ.get("S3_PREFIX", ""),
            )
        else:
            from src.storage.local import LocalStorageBackend
            _backend = LocalStorageBackend()
    return _backend
```

#### 8.3 S3 Key Structure

Map the current filesystem layout to S3 object keys:

| Current Path | S3 Key | Purpose |
|-------------|--------|---------|
| `.think-tank/threads/{tid}/user-data/uploads/{file}` | `threads/{tid}/uploads/{file}` | User-uploaded files |
| `.think-tank/threads/{tid}/user-data/outputs/{file}` | `threads/{tid}/outputs/{file}` | Agent-generated artifacts |
| `.think-tank/threads/{tid}/user-data/outputs/agent_timeline.json` | `threads/{tid}/timeline.json` | Timeline events (if not using DB) |
| `.think-tank/threads/{tid}/user-data/workspace/{file}` | `threads/{tid}/workspace/{file}` | Sandbox workspace files |
| `.think-tank/memory/{user_id}.json` | `memory/{user_id}.json` | Per-user memory (if not using DB) |

#### 8.4 Files Requiring Refactoring

**High priority (core file I/O):**

| File | Functions to Refactor | Change Description |
|------|----------------------|-------------------|
| `gateway/routers/uploads.py` | `upload_files()`, `list_uploaded_files()`, `delete_uploaded_file()`, `convert_file_to_markdown()`, `_get_user_total_upload_bytes()` | Replace filesystem writes with `storage.put()`, reads with `storage.get()`, directory scans with `storage.list_keys()`, quota scan with `storage.get_total_size()` |
| `gateway/routers/artifacts.py` | `get_artifact()`, `_extract_file_from_skill_archive()` | Replace `Path.read_bytes()` with `storage.get()`, serve via `StreamingResponse` using `storage.get_stream()` |
| `gateway/path_utils.py` | `resolve_thread_virtual_path()` | Return S3 keys instead of filesystem paths; add `resolve_to_storage_key()` |
| `sandbox/local/local_sandbox.py` | `read_file()`, `write_file()`, `update_file()`, `list_dir()` | Implement `StorageBackend`-aware variants that sync between local sandbox workspace and S3 |
| `sandbox/tools.py` | `ensure_thread_directories_exist()`, `bash_tool()`, `read_file_tool()`, `write_file_tool()` | Use storage backend for sandbox output persistence after execution completes |

**Medium priority (can use DB alternative):**

| File | Functions to Refactor | Change Description |
|------|----------------------|-------------------|
| `agents/middlewares/timeline_logging_middleware.py` | `_load_timeline()`, `_write_timeline()`, `_file_record_messages()` | Replace file I/O with `storage.get()`/`storage.put()`, or prefer the existing DB path via `_db_record_messages()` |
| `agents/memory/updater.py` | `_load_memory_from_file()`, `_save_memory_to_file()` | Replace file I/O with storage backend, or prefer DB-backed memory (Phase 2) |
| `agents/middlewares/thread_data_middleware.py` | `_create_thread_directories()` | No-op for S3 (no directory creation needed); only create local sandbox workspace |

**Low priority (deferred or keep local):**

| File | Functions to Refactor | Change Description |
|------|----------------------|-------------------|
| `gateway/routers/skills.py` | `install_skill()` | Read `.skill` archive from S3 instead of filesystem; installed skills remain local (baked into Docker image or volume mount) |
| `skills/loader.py` | `load_skills()` | Keep local — skills are code, not user data |

#### 8.5 Sandbox Integration Strategy

Sandboxes (both `LocalSandboxProvider` and `AioSandboxProvider`) execute commands that
read/write files in a local workspace. S3 cannot replace local disk for active sandboxes.

**Sync pattern: local workspace <-> S3**

```
1. Agent run starts
   -> Download existing workspace files from S3 to local sandbox dir
2. Tools execute (read/write local files normally)
3. Agent run completes (or tool finishes)
   -> Sync modified/new files from local sandbox dir back to S3
4. Artifact/upload requests
   -> Serve from S3 directly (not from sandbox workspace)
```

This requires a **post-execution sync hook** in the sandbox middleware that uploads
modified files after each tool invocation or agent turn.

#### 8.6 Large File Streaming & Presigned URLs

For files > 10 MB, avoid loading the entire file into Gateway memory:

- **Downloads:** Use S3 presigned URLs — redirect the client directly to S3
- **Uploads:** Support S3 presigned upload URLs for direct browser-to-S3 uploads (optional, advanced)
- **Artifacts:** Stream via `StreamingResponse` from `storage.get_stream()` for moderate-size files

```python
# Example: Artifact serving with streaming
@router.get("/api/threads/{thread_id}/artifacts/{path:path}")
async def get_artifact(thread_id: str, path: str):
    storage = get_storage_backend()
    key = f"threads/{thread_id}/outputs/{path}"

    if not await storage.exists(key):
        raise HTTPException(status_code=404)

    # For large files, redirect to presigned URL
    size = await storage.get_size(key)
    if size > 10 * 1024 * 1024:  # 10 MB
        url = await storage.get_presigned_url(key)
        return RedirectResponse(url)

    # For small files, stream directly
    content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return StreamingResponse(
        storage.get_stream(key),
        media_type=content_type,
    )
```

#### 8.7 Configuration

**Environment variables:**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `S3_BUCKET` | No (enables S3 mode) | — | S3 bucket name. If unset, uses local filesystem |
| `S3_REGION` | No | `us-east-1` | AWS region |
| `S3_ENDPOINT_URL` | No | — | Custom endpoint for MinIO / R2 / LocalStack |
| `S3_PREFIX` | No | — | Key prefix (e.g., `prod/` for namespacing) |
| `AWS_ACCESS_KEY_ID` | Yes (if S3) | — | AWS credentials |
| `AWS_SECRET_ACCESS_KEY` | Yes (if S3) | — | AWS credentials |

**Docker Compose additions:**

```yaml
# docker/docker-compose-prod.yaml (optional self-hosted S3)

  # ── MinIO (self-hosted S3, optional) ──────────────────────────
  minio:
    image: minio/minio:latest
    container_name: thinktank-minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER:-minioadmin}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD required}
    ports:
      - "9000:9000"    # API
      - "9001:9001"    # Console UI
    volumes:
      - miniodata:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: always
    networks:
      - thinktank

  gateway:
    environment:
      S3_BUCKET: ${S3_BUCKET:-thinktank-files}
      S3_ENDPOINT_URL: ${S3_ENDPOINT_URL:-http://minio:9000}
      S3_REGION: ${S3_REGION:-us-east-1}
      AWS_ACCESS_KEY_ID: ${MINIO_ROOT_USER:-minioadmin}
      AWS_SECRET_ACCESS_KEY: ${MINIO_ROOT_PASSWORD}

volumes:
  miniodata:
```

#### 8.8 Migration Strategy

**Phase A: Introduce abstraction layer (no behavior change)**
1. Create `StorageBackend` interface and `LocalStorageBackend`
2. Refactor all file I/O callers to use the storage backend
3. All existing tests continue to pass (local backend is default)

**Phase B: Implement S3 backend**
1. Create `S3StorageBackend` with `aiobotocore`
2. Add integration tests using LocalStack or MinIO in Docker
3. Feature-flag via `S3_BUCKET` env var

**Phase C: Data migration**
1. Write a one-time migration script: scan `.think-tank/threads/` and upload all existing files to S3
2. Deploy with `S3_BUCKET` set — new uploads go to S3
3. Verify serving works, then decommission local storage

#### 8.9 Dependencies

Add to `backend/pyproject.toml`:

```toml
dependencies = [
    # ... existing ...
    "aiobotocore>=2.15.0",    # Async S3 client
    "boto3>=1.35.0",          # Sync fallback and presigned URLs
]
```

---

## 6. Production Infrastructure

### 6.1 Container Images

**Backend production Dockerfile** (`backend/Dockerfile.prod`):

```dockerfile
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y \
    curl build-essential && \
    rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app
COPY backend ./backend
RUN cd backend && uv sync --no-dev

FROM python:3.12-slim

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local/bin/uv /usr/local/bin/uv
COPY --from=builder /app /app
WORKDIR /app

# Non-root user
RUN useradd -m appuser
USER appuser

EXPOSE 8001 2024

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["uv", "run", "gunicorn", "src.gateway.app:app", \
     "-w", "4", "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8001", "--timeout", "120"]
```

### 6.2 Networking

| Service | Internal Port | External Exposure |
|---------|--------------|-------------------|
| Nginx/LB | 80, 443 | Public (HTTPS only) |
| Gateway | 8001 | Internal only |
| LangGraph | 2024 | Internal only |
| PostgreSQL | 5432 | Internal only |
| Redis | 6379 | Internal only |
| Provisioner | 8002 | Internal only |
| Metrics | 9090 (Prometheus) | Internal only |

---

## 7. Resource Sizing & Capacity Planning

### 7.1 Per-User Resource Consumption

| Resource | Per Active User | Notes |
|----------|----------------|-------|
| **Gateway RAM** | ~50 MB | FastAPI worker memory |
| **LangGraph RAM** | 200-500 MB per active stream | Agent state, tool context, message history |
| **CPU** | 0.5-1 core per active stream | JSON processing, tool orchestration |
| **SSE Connections** | 1 long-lived per active chat | Nginx `worker_connections` must accommodate |
| **Sandbox** | 1 container (512 MiB RAM, 1 CPU) | Only while tools are executing |
| **Storage** | ~10 MB/user/month | Uploads, artifacts, memory |
| **LLM API Calls** | 5-50 per conversation turn | Depends on agent complexity, subagents |

### 7.2 Capacity by Server Size

| Server Spec | Concurrent Active Users | Total Registered Users | Monthly LLM Cost (est.) |
|-------------|------------------------|----------------------|------------------------|
| 4 vCPU / 16 GB | 8-12 | 100+ | $200-500 |
| 8 vCPU / 32 GB | 15-25 | 500+ | $500-2,000 |
| 16 vCPU / 64 GB | 30-50 | 1,000+ | $2,000-10,000 |
| K8s cluster (3x8 vCPU) | 100+ | 5,000+ | $10,000+ |

**Note:** LLM API cost dominates. The compute cost is relatively small compared to
the per-token cost of Claude/GPT calls.

---

## 8. Server Recommendations

### Option A: Single VM (10-50 Users) - Simplest

**Best for:** Initial launch, small team, EPFL research group

| Component | Spec | Provider | Cost/Month |
|-----------|------|----------|-----------|
| App Server | 8 vCPU, 32 GB RAM, 200 GB NVMe SSD | Hetzner CPX41 | ~$35 |
| Managed PostgreSQL | 2 vCPU, 4 GB RAM, 50 GB | Hetzner Cloud DB | ~$15 |
| Redis | 1 GB (or run in Docker on app server) | Upstash free tier | $0 |
| Object Storage | 100 GB | Hetzner Storage Box | ~$4 |
| CDN + DNS | Cloudflare Pages | Cloudflare free tier | $0 |
| SSL Certificate | Let's Encrypt | Free | $0 |
| **Total** | | | **~$54/month** |

**AWS equivalent:** ~$250-420/month (t3.2xlarge + RDS + ElastiCache)

### Option B: Kubernetes Cluster (50-500+ Users) - Scalable

**Best for:** Growing user base, auto-scaling needs

| Component | Spec | Provider | Cost/Month |
|-----------|------|----------|-----------|
| K8s Cluster | 3 nodes, 4 vCPU / 16 GB each | GKE/EKS/Hetzner | $150-300 |
| Managed PostgreSQL | 4 vCPU, 16 GB, read replicas | AWS RDS / GCP Cloud SQL | $100-200 |
| Redis Cluster | 3 GB | AWS ElastiCache / Memorystore | $50-100 |
| Load Balancer | Application LB with SSL | Cloud provider | $20-30 |
| Object Storage | 500 GB S3 | S3 / GCS | $10-15 |
| Monitoring | Grafana Cloud free tier | Grafana | $0 |
| **Total** | | | **$330-645/month** |

### Option C: EPFL Infrastructure

**Best for:** Academic deployment within EPFL network

- Use EPFL SCITAS or IC cluster VMs
- EPFL Tequila/Shibboleth SSO for authentication (replaces custom JWT auth)
- Internal PostgreSQL service
- EPFL network — no CDN needed for campus users

---

## 9. Production Docker Compose

```yaml
# docker/docker-compose-prod.yaml

services:
  # ── Database ───────────────────────────────────────────────────
  postgres:
    image: postgres:16-alpine
    container_name: thinktank-postgres
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./init-db.sql:/docker-entrypoint-initdb.d/init.sql:ro
    environment:
      POSTGRES_DB: thinktank
      POSTGRES_USER: thinktank
      POSTGRES_PASSWORD: ${DB_PASSWORD:?DB_PASSWORD required}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U thinktank"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: always
    networks:
      - thinktank

  # ── Cache / Queue ──────────────────────────────────────────────
  redis:
    image: redis:7-alpine
    container_name: thinktank-redis
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: always
    networks:
      - thinktank

  # ── Gateway API (scalable) ─────────────────────────────────────
  gateway:
    build:
      context: ../
      dockerfile: backend/Dockerfile.prod
    command: >
      uv run gunicorn src.gateway.app:app
      -w ${GATEWAY_WORKERS:-4}
      -k uvicorn.workers.UvicornWorker
      --bind 0.0.0.0:8001
      --timeout 120
      --graceful-timeout 30
      --access-logfile -
    environment:
      DATABASE_URL: postgresql+asyncpg://thinktank:${DB_PASSWORD}@postgres:5432/thinktank
      REDIS_URL: redis://redis:6379/0
    env_file:
      - ../.env
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
    deploy:
      replicas: ${GATEWAY_REPLICAS:-2}
      resources:
        limits:
          cpus: "2"
          memory: 2G
    restart: always
    networks:
      - thinktank

  # ── LangGraph Server (scalable with sticky sessions) ───────────
  langgraph:
    build:
      context: ../
      dockerfile: backend/Dockerfile.prod
    command: >
      uv run langgraph up
      --host 0.0.0.0 --port 2024
      --postgres-uri postgresql://thinktank:${DB_PASSWORD}@postgres:5432/thinktank
    environment:
      DATABASE_URL: postgresql+asyncpg://thinktank:${DB_PASSWORD}@postgres:5432/thinktank
      REDIS_URL: redis://redis:6379/0
    env_file:
      - ../.env
    depends_on:
      postgres: { condition: service_healthy }
    deploy:
      replicas: ${LANGGRAPH_REPLICAS:-2}
      resources:
        limits:
          cpus: "4"
          memory: 8G
    restart: always
    networks:
      - thinktank

  # ── Background Workers (memory updates, async tasks) ───────────
  worker:
    build:
      context: ../
      dockerfile: backend/Dockerfile.prod
    command: >
      uv run rq worker memory_updates subagent_tasks
      --url redis://redis:6379/0
    environment:
      DATABASE_URL: postgresql+asyncpg://thinktank:${DB_PASSWORD}@postgres:5432/thinktank
      REDIS_URL: redis://redis:6379/0
    env_file:
      - ../.env
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
    deploy:
      replicas: ${WORKER_REPLICAS:-2}
      resources:
        limits:
          cpus: "2"
          memory: 4G
    restart: always
    networks:
      - thinktank

  # ── Sandbox Provisioner ────────────────────────────────────────
  provisioner:
    build:
      context: ../provisioner
      dockerfile: Dockerfile
    container_name: thinktank-provisioner
    volumes:
      - ~/.kube/config:/root/.kube/config:ro
    environment:
      K8S_NAMESPACE: thinktank-sandboxes
      SANDBOX_IMAGE: enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:latest
    env_file:
      - ../.env
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8002/health"]
      interval: 10s
      timeout: 5s
      retries: 6
    restart: always
    networks:
      - thinktank

  # ── Reverse Proxy / Load Balancer ──────────────────────────────
  nginx:
    image: nginx:alpine
    container_name: thinktank-nginx
    ports:
      - "443:443"
      - "80:80"
    volumes:
      - ./nginx/nginx-prod.conf:/etc/nginx/nginx.conf:ro
      - ./certs:/etc/nginx/certs:ro
    depends_on:
      - gateway
      - langgraph
    restart: always
    networks:
      - thinktank

volumes:
  pgdata:
  redisdata:

networks:
  thinktank:
    driver: bridge
```

---

## 10. Production Nginx Configuration

```nginx
# docker/nginx/nginx-prod.conf

worker_processes auto;
worker_rlimit_nofile 65535;

events {
    worker_connections 4096;
    multi_accept on;
    use epoll;
}

http {
    # ── Basic Settings ────────────────────────────────────────────
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    client_max_body_size 100M;

    # ── Logging ───────────────────────────────────────────────────
    log_format json escape=json '{'
        '"time":"$time_iso8601",'
        '"remote_addr":"$remote_addr",'
        '"method":"$request_method",'
        '"uri":"$request_uri",'
        '"status":$status,'
        '"body_bytes_sent":$body_bytes_sent,'
        '"request_time":$request_time,'
        '"upstream_response_time":"$upstream_response_time"'
    '}';
    access_log /dev/stdout json;
    error_log /dev/stderr warn;

    # ── Rate Limiting ─────────────────────────────────────────────
    limit_req_zone $binary_remote_addr zone=api:10m rate=60r/m;
    limit_req_zone $binary_remote_addr zone=auth:10m rate=10r/m;
    limit_req_zone $binary_remote_addr zone=llm:10m rate=30r/m;

    # ── Upstreams ─────────────────────────────────────────────────
    upstream gateway {
        least_conn;
        server gateway:8001;
        # Additional replicas discovered by Docker DNS
    }

    upstream langgraph {
        ip_hash;  # Sticky sessions for SSE streams
        server langgraph:2024;
    }

    # ── HTTPS Server ──────────────────────────────────────────────
    server {
        listen 443 ssl http2;
        listen [::]:443 ssl http2;
        server_name app.yourdomain.com;

        ssl_certificate /etc/nginx/certs/fullchain.pem;
        ssl_certificate_key /etc/nginx/certs/privkey.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_prefer_server_ciphers on;

        # Security headers
        add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
        add_header X-Content-Type-Options nosniff always;
        add_header X-Frame-Options DENY always;
        add_header X-XSS-Protection "1; mode=block" always;

        # CORS (locked to domain)
        add_header 'Access-Control-Allow-Origin' 'https://app.yourdomain.com' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, PATCH, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'Authorization, Content-Type, X-Requested-With' always;
        add_header 'Access-Control-Allow-Credentials' 'true' always;

        if ($request_method = 'OPTIONS') {
            return 204;
        }

        # ── Auth endpoints (strict rate limit) ────────────────────
        location /api/auth/ {
            limit_req zone=auth burst=5 nodelay;
            proxy_pass http://gateway;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # ── LangGraph API (SSE streaming) ─────────────────────────
        location /api/langgraph/ {
            limit_req zone=llm burst=10 nodelay;
            rewrite ^/api/langgraph/(.*) /$1 break;
            proxy_pass http://langgraph;
            proxy_http_version 1.1;

            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header Connection '';

            # SSE/Streaming
            proxy_buffering off;
            proxy_cache off;
            proxy_set_header X-Accel-Buffering no;

            # Long timeouts for agent execution
            proxy_connect_timeout 600s;
            proxy_send_timeout 600s;
            proxy_read_timeout 600s;
            chunked_transfer_encoding on;
        }

        # ── Gateway API (general) ─────────────────────────────────
        location /api/ {
            limit_req zone=api burst=20 nodelay;
            proxy_pass http://gateway;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # ── Upload endpoint (large body) ──────────────────────────
        location ~ ^/api/threads/[^/]+/uploads {
            limit_req zone=api burst=10 nodelay;
            proxy_pass http://gateway;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            client_max_body_size 100M;
            proxy_request_buffering off;
        }

        # ── Health check ──────────────────────────────────────────
        location /health {
            proxy_pass http://gateway;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
        }

        # ── Frontend (SPA fallback) ───────────────────────────────
        # If NOT using CDN: serve static files from a volume
        # location / {
        #     root /var/www/frontend;
        #     try_files $uri $uri/ /index.html;
        #     expires 1y;
        #     add_header Cache-Control "public, immutable";
        # }
    }

    # ── HTTP -> HTTPS redirect ────────────────────────────────────
    server {
        listen 80;
        listen [::]:80;
        server_name app.yourdomain.com;
        return 301 https://$server_name$request_uri;
    }
}
```

---

## 11. TODO Checklist

### Phase 1: Authentication & User Isolation [P0 - Critical]

- [x] **1.1** Create `backend/src/db/` module with SQLAlchemy async engine and session factory
- [x] **1.2** Create `backend/src/db/models.py` with User ORM model
- [x] **1.3** Set up Alembic migrations in `backend/src/db/migrations/`
- [x] **1.4** Write initial migration: `users` table
- [x] **1.5** Create `backend/src/gateway/auth/password.py` (bcrypt hashing)
- [x] **1.6** Create `backend/src/gateway/auth/jwt.py` (RS256 token create/verify/refresh)
- [x] **1.7** Create `backend/src/gateway/auth/middleware.py` (`get_current_user` FastAPI dependency)
- [x] **1.8** Create `backend/src/gateway/auth/routes.py` (register, login, refresh, me, logout)
- [x] **1.9** Add auth dependency to all protected Gateway routers
- [x] **1.10** Add auth validation to LangGraph proxy path (thread ownership check)
- [x] **1.11** Create `threads` table migration and ownership enforcement middleware
- [x] **1.12** Modify `backend/src/agents/memory/updater.py` to accept `user_id` and scope file paths
- [x] **1.13** Modify `backend/src/agents/memory/queue.py` to include `user_id` in `ConversationContext`
- [x] **1.14** Modify `backend/src/agents/middlewares/memory_middleware.py` to extract `user_id` from runtime context
- [x] **1.15** Modify `backend/src/security/api_key_store.py` to key by `user_id` instead of `device_id`
- [x] **1.16** Remove `x-device-id` header dependency from `backend/src/gateway/routers/keys.py`
- [x] **1.17** Create `frontend/src/pages/Login.tsx` and `Register.tsx`
- [x] **1.18** Create `frontend/src/core/auth/` module (AuthContext, AuthProvider, useAuth, ProtectedRoute)
- [x] **1.19** Add JWT `Authorization: Bearer` header to all frontend API calls
- [x] **1.20** Add token refresh logic (intercept 401, retry with refreshed token)
- [x] **1.21** Wrap frontend routes with `<ProtectedRoute>` except landing/login/register

### Phase 2: Database Migration [P0 - Critical]

- [x] **2.1** Add PostgreSQL dependencies to `backend/pyproject.toml` (asyncpg, sqlalchemy, alembic, langgraph-checkpoint-postgres)
- [x] **2.2** Write migration: `user_memory` table
- [x] **2.3** Write migration: `user_api_keys` table
- [x] **2.4** Write migration: `uploads` metadata table
- [x] **2.5** Write migration: `timeline_events` table
- [x] **2.6** Write migration: `usage_log` table
- [x] **2.7** Update `backend/langgraph.json` to use PostgreSQL checkpoint store
- [x] **2.8** Migrate `memory/updater.py` from file I/O to database queries
- [x] **2.9** Migrate `middlewares/timeline_logging_middleware.py` from file I/O to database inserts (removes `_WRITE_LOCK`, enables append-only INSERTs)
- [x] **2.10** Migrate `security/api_key_store.py` from file I/O to database queries
- [x] **2.11** Add database health check to `/health` endpoint
- [x] **2.12** Write data migration script for existing `.think-tank/` data to PostgreSQL

### Phase 3: Sandbox Isolation [P1 - High]

- [x] **3.1** Update `config.yaml` to use `AioSandboxProvider` with provisioner
- [x] **3.2** Configure container resource limits (CPU, memory, PID, disk) in provisioner
- [x] **3.3** Add network policy: sandbox containers cannot access internal services
- [x] **3.4** Implement sandbox idle timeout and auto-cleanup
- [x] **3.5** Add per-user sandbox quota (max N concurrent sandboxes)
- [x] **3.6** Test sandbox isolation: verify containers cannot escape to host

### Phase 4: Horizontal Scaling [P2 - Medium]

- [x] **4.1** Create `backend/Dockerfile.prod` with multi-stage build and non-root user
- [x] **4.2** Configure Gunicorn with multiple workers for Gateway
- [x] **4.3** Configure Nginx `ip_hash` or sticky sessions for LangGraph upstream
- [x] **4.4** Increase subagent `ThreadPoolExecutor` workers and add per-user semaphore
- [x] **4.5** Replace in-process `MemoryUpdateQueue` with Redis-based task queue (RQ or Celery)
- [x] **4.6** Create background worker service configuration
- [x] **4.7** Test multi-instance deployment with 2+ Gateway and 2+ LangGraph replicas

### Phase 5: Frontend Web Deployment [P1 - High]

- [x] **5.1** Verify `pnpm build` (web mode) produces correct static output
- [x] **5.2** Configure build-time environment variables for production backend URL
- [x] **5.3** Deploy static build to Cloudflare Pages (or Vercel, or self-hosted Nginx)
- [x] **5.4** Configure SPA fallback routing (all paths -> `index.html`)
- [x] **5.5** Set `Cache-Control` headers for static assets (immutable, 1 year)
- [x] **5.6** Verify Electron app still works against the same backend

### Phase 6: Security Hardening [P1 - High]

- [x] **6.1** Configure TLS termination (Let's Encrypt or managed cert) — `nginx-prod.conf` with SSL 443, certs volume
- [x] **6.2** Add HTTP -> HTTPS redirect — port 80 redirect server block in `nginx-prod.conf`
- [x] **6.3** Lock down CORS to specific domain(s) — `$CORS_ALLOWED_ORIGIN` envsubst variable in prod nginx
- [x] **6.4** Add Nginx rate limiting zones (auth, api, llm) — already done
- [x] **6.5** Add application-level per-user rate limiting via Redis — `backend/src/gateway/rate_limiter.py`
- [x] **6.6** Add file upload validation (MIME type check, extension allowlist) — `_validate_upload()` in `uploads.py`
- [x] **6.7** Add per-user upload storage quota (e.g., 500 MB) — `_check_upload_quota()` in `uploads.py`, configurable via `UPLOAD_QUOTA_MB`
- [x] **6.8** Move secrets to environment variables or secrets manager (not files) — `REQUIRE_ENV_SECRETS` mode in `jwt.py` and `api_key_store.py`
- [x] **6.9** Set security headers (HSTS, X-Content-Type-Options, X-Frame-Options) — all 4 nginx configs
- [x] **6.10** Audit all Pydantic models for input validation completeness — already done
- [ ] **6.11** ~~Integrate S3-compatible object storage client~~ — **moved to [Phase 8: S3 Object Storage Migration](#phase-8-s3-object-storage-migration)**

### Phase 7: Monitoring & Observability [P2 - Medium]

- [x] **7.1** Replace all `print()` calls with structured `logging` in backend
- [x] **7.2** Add `prometheus-fastapi-instrumentator` to Gateway
- [x] **7.3** Create custom Prometheus metrics for LLM calls, tokens, sandboxes, subagents
- [x] **7.4** Set up Grafana dashboards for key metrics
- [x] **7.5** Enable LangSmith tracing for production
- [x] **7.6** Enhance `/health` endpoint with database, Redis, and LangGraph checks
- [x] **7.7** Configure alerting rules (error rate, latency, disk, memory)
- [x] **7.8** Set up centralized log aggregation (ELK, Loki, or CloudWatch)

### Phase 8: S3 Object Storage Migration [P2 - Medium]

- [ ] **8.1** Add `aiobotocore` and `boto3` dependencies to `backend/pyproject.toml`
- [ ] **8.2** Create `backend/src/storage/base.py` with `StorageBackend` abstract base class (put, get, get_stream, delete, exists, list_keys, get_size, get_total_size, get_presigned_url)
- [ ] **8.3** Create `backend/src/storage/local.py` with `LocalStorageBackend` wrapping current filesystem operations
- [ ] **8.4** Create `backend/src/storage/s3.py` with `S3StorageBackend` using aiobotocore
- [ ] **8.5** Create `backend/src/storage/factory.py` with `get_storage_backend()` factory (feature-flagged via `S3_BUCKET` env var)
- [ ] **8.6** Refactor `gateway/routers/uploads.py` to use `StorageBackend` for upload, list, delete, quota tracking
- [ ] **8.7** Refactor `gateway/routers/artifacts.py` to use `StorageBackend` for file serving (with `StreamingResponse` and presigned URL fallback for large files)
- [ ] **8.8** Refactor `gateway/path_utils.py` to resolve virtual paths to storage keys instead of filesystem paths
- [ ] **8.9** Refactor `sandbox/local/local_sandbox.py` read/write/update/list operations to sync with storage backend
- [ ] **8.10** Refactor `sandbox/tools.py` to use storage backend for output persistence after tool execution
- [ ] **8.11** Add post-execution sync hook in sandbox middleware (local workspace -> S3 on agent turn completion)
- [ ] **8.12** Refactor `agents/middlewares/timeline_logging_middleware.py` file I/O to use storage backend (or prefer DB path)
- [ ] **8.13** Refactor `agents/memory/updater.py` file I/O to use storage backend (or prefer DB path)
- [ ] **8.14** Update `agents/middlewares/thread_data_middleware.py` directory creation to no-op for S3 mode
- [ ] **8.15** Add MinIO service to `docker/docker-compose-prod.yaml` with S3 env vars for gateway
- [ ] **8.16** Write unit tests for `LocalStorageBackend` and `S3StorageBackend` (using mocked aiobotocore)
- [ ] **8.17** Write integration tests for S3 backend using LocalStack or MinIO in Docker (testcontainers)
- [ ] **8.18** Write one-time data migration script: scan `.think-tank/threads/` and upload existing files to S3
- [ ] **8.19** Update `gateway/routers/skills.py` `install_skill()` to read `.skill` archives from storage backend

### Infrastructure & DevOps [P2 - Medium]

- [x] **9.1** Create `docker/docker-compose-prod.yaml`
- [x] **9.2** Create `docker/nginx/nginx-prod.conf`
- [x] **9.3** Create `backend/Dockerfile.prod` (multi-stage, non-root)
- [x] **9.4** Set up CI/CD pipeline (GitHub Actions: lint, test, build, deploy) — `.github/workflows/ci.yml`, `docker-publish.yml`, `deploy.yml`
- [x] **9.5** Create staging environment (mirrors production) — `docker/docker-compose-staging.yaml`, `scripts/staging.sh`
- [x] **9.6** Write deployment runbook documenting rollback procedures — `docs/DEPLOYMENT_RUNBOOK.md`
- [x] **9.7** Configure automated database backups (pg_dump daily, WAL archiving) with S3 bucket as backup destination — `docker/backup/`
- [x] **9.8** Set up DNS records and CDN configuration — `docs/DNS_CDN_SETUP.md`

---

## 12. Testing Plan

### 12.1 Unit Tests

| Test Area | File(s) to Test | Test Cases | Priority |
|-----------|----------------|------------|----------|
| **JWT auth** | `auth/jwt.py` | Token creation, verification, expiry, refresh, invalid signature, tampered payload | P0 |
| **Password hashing** | `auth/password.py` | Hash creation, verification, bcrypt rounds, empty/long passwords | P0 |
| **Auth middleware** | `auth/middleware.py` | Valid token extracts user_id, expired token returns 401, missing header returns 401, malformed token returns 401 | P0 |
| **Auth routes** | `auth/routes.py` | Register (success, duplicate email, weak password), login (success, wrong password, nonexistent user), refresh (valid cookie, expired cookie), logout | P0 |
| **Thread ownership** | Gateway middleware | Authorized user accesses own thread, user denied access to other's thread, thread creation records ownership | P0 |
| **Per-user memory** | `memory/updater.py` | Memory load/save scoped to user_id, user A cannot read user B's memory, empty memory initialization per user | P0 |
| **Memory queue** | `memory/queue.py` | Queue scoped by (user_id, thread_id), deduplication per user, debounce timer | P1 |
| **API key store** | `api_key_store.py` | Set/get/delete keyed by user_id, encryption/decryption, user isolation | P1 |
| **Database models** | `db/models.py` | User CRUD, thread CRUD, user_memory CRUD, foreign key constraints, cascading deletes | P0 |
| **Rate limiting** | Redis rate limiter | Under limit passes, over limit blocked, counter reset after window, per-user isolation | P1 |
| **Input validation** | All Pydantic models | Valid inputs accepted, invalid inputs rejected with proper error messages, injection attempts caught | P1 |
| **StorageBackend (local)** | `storage/local.py` | put/get/delete/exists/list_keys/get_size/get_total_size with local files, directory auto-creation, missing key errors | P1 |
| **StorageBackend (S3)** | `storage/s3.py` | put/get/delete/exists/list_keys/get_size/get_total_size/get_presigned_url with mocked aiobotocore, error handling for missing keys, connection failures | P1 |
| **Storage factory** | `storage/factory.py` | Returns `LocalStorageBackend` when `S3_BUCKET` unset, returns `S3StorageBackend` when set, singleton behavior, MinIO endpoint passthrough | P1 |
| **Upload validation** | `uploads.py` | Extension allowlist, MIME type check, per-file size limit, rejected extensions (exe/bat/dll), case-insensitive matching | P1 |
| **Upload quota** | `uploads.py` | Under-quota passes, over-quota returns 413, filesystem fallback counting, env var configuration | P1 |
| **Secrets hardening** | `jwt.py`, `api_key_store.py` | Env var used when set, RuntimeError when `REQUIRE_ENV_SECRETS` without key, file fallback in dev mode | P1 |

### 12.2 Integration Tests

| Test Scenario | Components Involved | Verification | Priority |
|---------------|-------------------|-------------|----------|
| **Full auth flow** | Frontend -> Gateway -> PostgreSQL | Register, login, access protected endpoint, refresh token, logout | P0 |
| **Thread isolation E2E** | Frontend -> Gateway -> LangGraph -> PostgreSQL | User A creates thread, User B cannot access it via API | P0 |
| **Memory isolation E2E** | Gateway -> LangGraph -> Memory middleware -> PostgreSQL | Two users chat, verify memory files/rows are separate | P0 |
| **Sandbox isolation** | LangGraph -> Provisioner -> K8s Pod | Run `whoami`, `hostname`, verify different per user; verify cannot access host filesystem | P0 |
| **SSE streaming** | Frontend -> Nginx -> LangGraph | Start agent stream, receive events, verify no cross-user event leakage | P1 |
| **File upload isolation** | Frontend -> Gateway -> Storage | User A uploads file, User B cannot download it via thread artifacts endpoint | P1 |
| **API key isolation** | Frontend -> Gateway -> PostgreSQL | User A saves OpenAI key, User B cannot retrieve it | P1 |
| **Concurrent users** | Multiple sessions -> All services | 10 concurrent chat sessions, no cross-contamination of state | P1 |
| **Database failover** | Gateway -> PostgreSQL (stopped) | Gateway returns 503, recovers when DB comes back | P2 |
| **LangGraph multi-instance** | Nginx -> 2x LangGraph -> PostgreSQL | Start stream on instance 1, verify checkpoint accessible from instance 2 | P2 |
| **S3 upload round-trip** | Gateway -> S3StorageBackend -> MinIO | Upload file via API, verify stored in S3, retrieve via artifacts endpoint, content matches | P1 |
| **S3 quota enforcement** | Gateway -> S3StorageBackend -> MinIO | Upload files until quota hit, verify 413 returned, verify `get_total_size()` counts S3 objects correctly | P1 |
| **S3 presigned URL redirect** | Gateway -> S3StorageBackend -> MinIO | Upload >10 MB file, request artifact, verify response is a redirect to presigned URL | P2 |
| **S3 sandbox sync** | LangGraph -> Sandbox -> S3StorageBackend | Agent writes file in sandbox, verify post-execution sync uploads to S3, artifact accessible from Gateway | P2 |
| **Local-to-S3 migration** | Migration script -> MinIO | Run migration script on `.think-tank/` test data, verify all files present in S3 with correct keys | P2 |
| **Storage backend fallback** | Gateway (no `S3_BUCKET`) -> LocalStorageBackend | Verify all upload/artifact operations work with local backend when S3 not configured | P1 |

### 12.3 Load Tests

Use `locust` or `k6` to simulate concurrent users.

| Test | Tool | Target | Pass Criteria |
|------|------|--------|--------------|
| **API throughput** | k6 | Gateway endpoints | 100 req/s with P99 < 500ms |
| **SSE concurrency** | k6 | LangGraph streaming | 50 concurrent streams stable for 10 min |
| **Auth endpoint** | k6 | `/api/auth/login` | 200 req/s with P99 < 200ms |
| **Upload stress** | k6 | `/api/threads/{id}/uploads` | 10 concurrent 50MB uploads complete |
| **Memory contention** | locust | 20 users updating memory simultaneously | No data corruption, all updates persisted |
| **Sandbox scaling** | k6 | 20 concurrent tool executions | All sandboxes provisioned within 30s |
| **Rate limit verification** | k6 | All rate-limited endpoints | Requests beyond limit return 429 |
| **S3 upload throughput** | k6 | `/api/threads/{id}/uploads` with S3 backend | 10 concurrent 50MB uploads to S3 complete within 60s |
| **S3 artifact serving** | k6 | `/api/threads/{id}/artifacts/*` with S3 backend | 100 concurrent small file requests with P99 < 500ms |
| **S3 presigned URL latency** | k6 | Large file artifact requests | Presigned URL redirect returns within 100ms |

**Load test script structure:**

```javascript
// k6-load-test.js
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '2m', target: 10 },   // Ramp up to 10 users
    { duration: '5m', target: 50 },   // Ramp up to 50 users
    { duration: '5m', target: 50 },   // Stay at 50 users
    { duration: '2m', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(99)<2000'],  // 99% under 2s
    http_req_failed: ['rate<0.05'],     // <5% error rate
  },
};

export default function () {
  // 1. Login
  const loginRes = http.post(`${BASE_URL}/api/auth/login`, JSON.stringify({
    email: `user${__VU}@test.com`,
    password: 'testpass123',
  }), { headers: { 'Content-Type': 'application/json' } });

  check(loginRes, { 'login succeeded': (r) => r.status === 200 });

  const token = loginRes.json('access_token');

  // 2. Create thread and send message
  // 3. Verify response
  // 4. Verify no cross-user data

  sleep(1);
}
```

### 12.4 Security Tests

| Test | Method | Verification | Priority |
|------|--------|-------------|----------|
| **JWT tampering** | Modify token payload, send to API | Returns 401 Unauthorized | P0 |
| **Cross-user thread access** | Authenticate as User A, access User B's thread_id | Returns 403 Forbidden | P0 |
| **Cross-user memory access** | Authenticate as User A, try to read User B's memory | Returns 403 or empty memory | P0 |
| **Sandbox escape** | From within sandbox container, attempt to access host | Network blocked, filesystem isolated | P0 |
| **SQL injection** | Send `'; DROP TABLE users; --` in registration fields | Parameterized query prevents execution | P0 |
| **XSS in thread title** | Send `<script>alert(1)</script>` as message | Properly escaped in UI rendering | P1 |
| **CORS enforcement** | Send API request from unauthorized origin | Blocked by browser CORS policy | P1 |
| **Rate limit bypass** | Send requests above limit from single IP | Returns 429 Too Many Requests | P1 |
| **Expired token access** | Use expired JWT to access protected endpoint | Returns 401, not 200 | P0 |
| **Refresh token theft** | Use refresh token from different IP/user-agent | Ideally rejected (optional: bind to fingerprint) | P2 |
| **File upload malware** | Upload executable disguised as image | Extension/MIME validation rejects | P1 |
| **Path traversal** | Request `/api/threads/../../../etc/passwd` via artifacts | Nginx and backend reject traversal | P1 |
| **Brute force login** | 100 rapid login attempts | Rate limited after 10 attempts | P1 |
| **API key enumeration** | Try to list other users' API keys | Only own keys returned | P0 |
| **S3 key traversal** | Request artifact with `../` in path | Storage backend rejects path traversal, returns 400 | P1 |
| **S3 bucket isolation** | Craft S3 key to access different user's prefix | Storage backend enforces thread-scoped keys, no cross-tenant access | P1 |
| **S3 presigned URL expiry** | Request presigned URL, wait for expiry, then access | Expired URL returns 403 from S3 | P2 |
| **Upload blocked extensions via S3** | Upload `.exe`, `.bat`, `.dll` files with S3 backend enabled | Validation rejects before reaching storage backend | P1 |
| **Upload oversized file via S3** | Upload file exceeding 50 MB per-file limit | Returns 413 before S3 write | P1 |

### 12.5 End-to-End Smoke Tests (Post-Deployment)

Run after every deployment:

```
1. [ ] Open https://app.yourdomain.com - landing page loads
2. [ ] Register a new account - succeeds
3. [ ] Login with the new account - succeeds, redirected to chat
4. [ ] Create a new conversation - thread created
5. [ ] Send a message - agent responds via SSE stream
6. [ ] Agent uses a tool (e.g., web search) - tool result displayed
7. [ ] Upload a file - file appears in conversation
8. [ ] Open Settings - API keys, MCP config, models visible
9. [ ] Save an API key - persists after page reload
10. [ ] Open conversation list - only own threads visible
11. [ ] Logout and login as different user - first user's threads NOT visible
12. [ ] Check /health endpoint - returns {"status": "healthy"}
13. [ ] Check Grafana/metrics dashboard - metrics flowing
14. [ ] Verify HTTPS - certificate valid, HTTP redirects to HTTPS
15. [ ] Test from mobile browser - responsive UI works
16. [ ] Upload a file, verify it persists across page reload (S3 or local)
17. [ ] Download an agent-generated artifact - file downloads correctly
18. [ ] If S3 enabled: verify MinIO console shows uploaded objects at expected keys
```

### 12.6 Test Infrastructure

| Tool | Purpose | Configuration |
|------|---------|--------------|
| **pytest** | Unit + integration tests (backend) | `backend/tests/`, use `pytest-asyncio` for async |
| **pytest-cov** | Code coverage reporting | Target: >80% for auth, memory, ownership modules |
| **httpx** | Async HTTP client for integration tests | Used with `TestClient` for FastAPI |
| **testcontainers** | Spin up PostgreSQL + Redis in tests | Docker-based, disposable test databases |
| **Vitest** | Frontend unit tests | `frontend/src/**/*.test.ts` |
| **Playwright** | Frontend E2E tests | `frontend/e2e/` |
| **k6** | Load/performance tests | `tests/load/` |
| **OWASP ZAP** | Automated security scanning | Run against staging environment |
| **LocalStack** | Local S3-compatible mock for S3 integration tests | Docker-based, used with testcontainers for isolated S3 testing |
| **MinIO** | Self-hosted S3 for staging/integration testing | `minio/minio:latest`, configured via `S3_ENDPOINT_URL` |

**CI Pipeline Test Stages:**

```
1. Lint (ruff, eslint)           ~30s
2. Type check (mypy, tsc)       ~60s
3. Unit tests (pytest, vitest)   ~2m
4. Integration tests (testcontainers) ~5m
5. Build (Docker images)         ~3m
6. E2E smoke tests (Playwright)  ~3m
7. Security scan (OWASP ZAP)     ~10m  [staging only]
8. Load tests (k6)               ~15m  [staging only]
```

---

## Appendix A: Migration Path from Current to Production

### Step 1: Local Development with PostgreSQL (Week 1)

```bash
# Start PostgreSQL locally
docker run -d --name thinktank-pg \
  -e POSTGRES_DB=thinktank \
  -e POSTGRES_USER=thinktank \
  -e POSTGRES_PASSWORD=localdev \
  -p 5432:5432 postgres:16-alpine

# Run migrations
cd backend && alembic upgrade head

# Start development with DATABASE_URL
DATABASE_URL=postgresql+asyncpg://thinktank:localdev@localhost:5432/thinktank \
  make dev
```

### Step 2: Deploy to Single VM (Week 2-3)

1. Provision server (Hetzner CPX41 or similar)
2. Install Docker + Docker Compose
3. Clone repository
4. Create `.env` with production secrets
5. Run `docker compose -f docker/docker-compose-prod.yaml up -d`
6. Set up SSL with Let's Encrypt
7. Point DNS to server IP
8. Run smoke tests

### Step 3: Scale Out (Week 4+, if needed)

1. Migrate to managed PostgreSQL
2. Add Redis cluster
3. Scale Gateway and LangGraph replicas
4. Set up monitoring stack
5. Run load tests, tune based on results

---

## Appendix B: Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Memory data leakage between users | HIGH (current) | CRITICAL | Phase 1: per-user memory isolation |
| Sandbox escape to host | HIGH (current) | CRITICAL | Phase 3: container isolation |
| LLM API cost overrun | MEDIUM | HIGH | Phase 6: per-user rate limiting + usage tracking |
| Database corruption | LOW | CRITICAL | Automated backups, WAL archiving, read replicas |
| SSE connection exhaustion | MEDIUM | HIGH | Nginx connection limits, LangGraph replica scaling |
| Single point of failure (DB) | MEDIUM | CRITICAL | Managed PostgreSQL with failover |
| Key/secret exposure | LOW | CRITICAL | Secrets manager, encrypted storage, non-root containers |
| DDoS attack | LOW | HIGH | Cloudflare CDN, rate limiting, IP banning |
