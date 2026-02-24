# Local Deployment Testing Guide

Test the full production deployment on your MacBook before renting a server.
Covers two modes: **Vite dev server** (daily development) and **nginx + static
build** (production simulation).

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Prerequisites](#2-prerequisites)
3. [Mode A: Vite Dev Server (Daily Development)](#3-mode-a-vite-dev-server-daily-development)
4. [Mode B: Nginx + Static Build (Production Simulation)](#4-mode-b-nginx--static-build-production-simulation)
5. [Testing the Auth Flow](#5-testing-the-auth-flow)
6. [Testing Multi-User Isolation](#6-testing-multi-user-isolation)
7. [Testing the Full Agent Flow](#7-testing-the-full-agent-flow)
8. [Testing the Static Build for Electron](#8-testing-the-static-build-for-electron)
9. [Troubleshooting](#9-troubleshooting)
10. [Comparison: Local vs. Production](#10-comparison-local-vs-production)

---

## 1. Architecture Overview

### What Runs Where

```
Your MacBook (Apple Silicon)
+==================================================================+
|                                                                    |
|  MODE A (dev):  Vite :3000 proxies /api/* to backend               |
|  MODE B (prod): Nginx :2026 serves static + proxies /api/*         |
|                                                                    |
|  Backend processes (native, not Docker):                           |
|    Gateway     :8001   FastAPI (uvicorn)                           |
|    LangGraph   :2024   Agent engine                                |
|                                                                    |
|  Docker containers:                                                |
|    deer-flow-postgres  :5432   PostgreSQL 16                       |
|    thinktank-redis     :6379   Redis 7 (optional for now)          |
|                                                                    |
+==================================================================+
```

### Why This Split

| Component | Runs As | Reason |
|-----------|---------|--------|
| **PostgreSQL** | Docker container | Isolated, version-pinned, persistent volume, matches production |
| **Redis** | Docker container | Lightweight, no host install needed |
| **Gateway** | Native process | Instant `--reload` on code changes, no image rebuild |
| **LangGraph** | Native process | Same — fast iteration during development |
| **Frontend (Mode A)** | Vite dev server | Hot module replacement, proxy rules replicate nginx |
| **Frontend (Mode B)** | Static files via nginx | Tests the real production serving path |
| **Nginx** | Homebrew (Mode B only) | Not needed for Mode A — Vite handles proxying |

### How the Proxy Works

In both modes, the browser makes requests to a single origin. API calls are
proxied to the backend services:

```
Browser request                    Mode A (Vite)              Mode B (Nginx)
─────────────────────────────────────────────────────────────────────────────
GET /                              Vite HMR server            Static file from disk
GET /api/auth/login                proxy → localhost:8001     proxy → 127.0.0.1:8001
GET /api/langgraph/threads/...     proxy → localhost:2024     proxy → 127.0.0.1:2024
GET /api/models/                   proxy → localhost:8001     proxy → 127.0.0.1:8001
```

Vite's proxy config (in `frontend/vite.config.ts`) replicates what nginx does:

```typescript
proxy: {
  "/api/langgraph": {
    target: "http://localhost:2024",
    rewrite: (path) => path.replace(/^\/api\/langgraph/, ""),
  },
  "/api": {
    target: "http://localhost:8001",
  },
},
```

---

## 2. Prerequisites

### Already installed (verify)

```bash
# Check all at once
make check
```

Expected output:

```
✓ Node.js 22.x
✓ pnpm 10.x
✓ uv 0.x
✓ nginx (only needed for Mode B — OK if missing for Mode A)
```

### Docker

Docker Desktop must be running (for PostgreSQL and Redis containers).

```bash
docker ps  # Should not error
```

### Install nginx (Mode B only)

```bash
brew install nginx
```

---

## 3. Mode A: Vite Dev Server (Daily Development)

Use this mode for day-to-day coding. No nginx required.

### 3.1 One-Command Start

From the project root:

```bash
make dev
```

This single command:
1. Starts PostgreSQL (Docker) if not running
2. Runs Alembic migrations (`alembic upgrade head`)
3. Starts LangGraph server on `:2024`
4. Starts Gateway API on `:8001`
5. Starts Vite frontend on `:3000`
6. Starts nginx on `:2026` (optional reverse proxy)

Press `Ctrl+C` to stop all services (PostgreSQL keeps running).

Access the app at: **http://localhost:2026**

Alternatively, access directly via Vite at **http://localhost:3000** (Vite proxies
API calls automatically).

### 3.2 Manual Start (Individual Terminals)

If you prefer explicit control over each process:

**Terminal 1 — Database:**

```bash
make db-start
make db-migrate
```

**Terminal 2 — LangGraph:**

```bash
cd backend
DATABASE_URL=postgresql://deerflow:deerflow@localhost:5432/deerflow \
  uv run langgraph dev --no-browser --allow-blocking
```

**Terminal 3 — Gateway:**

```bash
cd backend
DATABASE_URL=postgresql://deerflow:deerflow@localhost:5432/deerflow \
  uv run uvicorn src.gateway.app:app --host 0.0.0.0 --port 8001 --reload
```

**Terminal 4 — Frontend:**

```bash
cd frontend
pnpm dev:web
```

Access at: **http://localhost:3000**

### 3.3 Optional: Start Redis

Redis is needed for rate limiting and session management in production. For local
dev it's optional — the backend falls back gracefully without it.

```bash
docker run -d --name thinktank-redis \
  -p 6379:6379 \
  redis:7-alpine \
  redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
```

### 3.4 Verify Services

```bash
# Gateway health
curl -s http://localhost:8001/health
# → {"status":"healthy","service":"deer-flow-gateway"}

# Auth endpoint reachable
curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/auth/me
# → 403 (no token — expected)

# LangGraph reachable
curl -s -o /dev/null -w "%{http_code}" http://localhost:2024/info
# → 200

# Frontend (via Vite proxy)
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/
# → 200

# Frontend API proxy working
curl -s http://localhost:3000/api/models/ | head -c 100
# → Should return model JSON (proxied to :8001)

# Database
docker exec deer-flow-postgres pg_isready -U deerflow
# → accepting connections
```

### 3.5 Stop Everything

```bash
make stop       # Stops Gateway, LangGraph, Frontend, Nginx
make db-stop    # Stops PostgreSQL (separate command — data persists)
```

Or for a full clean:

```bash
make clean      # stop + remove log files
```

---

## 4. Mode B: Nginx + Static Build (Production Simulation)

Use this mode to test the exact deployment that runs on a real server: nginx
serving pre-built static files and proxying API calls to the backend.

### 4.1 Build the Frontend

```bash
cd frontend
pnpm build
```

Output:

```
dist/renderer/
  index.html
  assets/
    index-[hash].js
    index-[hash].css
    ...
```

The `VITE_BACKEND_BASE_URL` and `VITE_LANGGRAPH_BASE_URL` default to `""` (empty
string), meaning all API calls use relative paths (`/api/...`). This is correct —
nginx on the same origin handles the routing.

### 4.2 Create the Nginx Config

Create the file at `/tmp/thinktank-local-prod.conf`:

```nginx
# Local production simulation
# Replicates the production nginx config on localhost

events {
    worker_connections 1024;
}

pid /tmp/thinktank-nginx.pid;

http {
    # IMPORTANT: include mime.types so .js files are served as
    # application/javascript (not application/octet-stream)
    include /opt/homebrew/etc/nginx/mime.types;
    default_type application/octet-stream;

    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;

    access_log /dev/stdout;
    error_log /dev/stderr;

    # Rate limiting (same zones as production)
    limit_req_zone $binary_remote_addr zone=api:10m rate=60r/m;
    limit_req_zone $binary_remote_addr zone=auth:10m rate=10r/m;

    server {
        listen 2026;
        server_name localhost;

        # ── Auth endpoints (stricter rate limit) ──────────────
        location /api/auth/ {
            limit_req zone=auth burst=5 nodelay;
            proxy_pass http://127.0.0.1:8001;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # ── LangGraph API (SSE streaming) ─────────────────────
        location /api/langgraph/ {
            limit_req zone=api burst=20 nodelay;
            rewrite ^/api/langgraph/(.*) /$1 break;
            proxy_pass http://127.0.0.1:2024;
            proxy_http_version 1.1;

            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header Connection '';

            # SSE/Streaming — must disable buffering
            proxy_buffering off;
            proxy_cache off;
            proxy_set_header X-Accel-Buffering no;

            # Long timeouts for agent execution
            proxy_connect_timeout 600s;
            proxy_send_timeout 600s;
            proxy_read_timeout 600s;
            chunked_transfer_encoding on;
        }

        # ── Upload endpoint (large body) ──────────────────────
        location ~ ^/api/threads/[^/]+/uploads {
            limit_req zone=api burst=10 nodelay;
            proxy_pass http://127.0.0.1:8001;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            client_max_body_size 100M;
            proxy_request_buffering off;
        }

        # ── Gateway API (all other /api/*) ────────────────────
        location /api/ {
            limit_req zone=api burst=20 nodelay;
            proxy_pass http://127.0.0.1:8001;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # ── Health check ──────────────────────────────────────
        location /health {
            proxy_pass http://127.0.0.1:8001;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
        }

        # ── API docs (gateway) ────────────────────────────────
        location /docs {
            proxy_pass http://127.0.0.1:8001;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
        }

        location /redoc {
            proxy_pass http://127.0.0.1:8001;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
        }

        location /openapi.json {
            proxy_pass http://127.0.0.1:8001;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
        }

        # ── Frontend (static files + SPA fallback) ────────────
        location / {
            root /Users/zechen/EPFL/thinktank-ai/frontend/dist/renderer;
            try_files $uri $uri/ /index.html;

            # Cache hashed assets aggressively
            location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff2?)$ {
                expires 1y;
                add_header Cache-Control "public, immutable";
            }
        }
    }
}
```

### 4.3 Start the Full Stack

**Step 1 — Database (if not already running):**

```bash
make db-start
make db-migrate
```

**Step 2 — Backend (two terminals):**

```bash
# Terminal 1: LangGraph
cd backend
DATABASE_URL=postgresql://deerflow:deerflow@localhost:5432/deerflow \
  uv run langgraph dev --no-browser --allow-blocking

# Terminal 2: Gateway
cd backend
DATABASE_URL=postgresql://deerflow:deerflow@localhost:5432/deerflow \
  uv run uvicorn src.gateway.app:app --host 0.0.0.0 --port 8001
```

**Step 3 — Nginx (serving the static build):**

```bash
nginx -c /tmp/thinktank-local-prod.conf
```

**Step 4 — Open the app:**

Open **http://localhost:2026** in your browser.

This is serving the pre-built static `index.html` from disk (not Vite), with
nginx proxying all `/api/*` requests to the backend. This is identical to what
happens on a production server.

### 4.4 Verify the Static Build

```bash
# Static file served with correct content type
curl -s -I http://localhost:2026/ | grep -i content-type
# → Content-Type: text/html

# JS assets served with correct type and caching
curl -s -I http://localhost:2026/assets/ 2>/dev/null | head -5
# Should include: Content-Type: application/javascript
#                 Cache-Control: max-age=31536000

# API proxy works through nginx
curl -s http://localhost:2026/health
# → {"status":"healthy","service":"deer-flow-gateway"}

# SPA fallback: unknown routes return index.html (not 404)
curl -s -o /dev/null -w "%{http_code}" http://localhost:2026/some/random/route
# → 200 (index.html served, React Router handles the route)

# SSE streaming works through nginx
curl -s -N "http://localhost:2026/api/langgraph/info" | head -5
# → Should return LangGraph server info
```

### 4.5 Stop Nginx

```bash
nginx -c /tmp/thinktank-local-prod.conf -s quit
```

### 4.6 Rebuild After Code Changes

When you change frontend code:

```bash
cd frontend && pnpm build
# Nginx automatically serves the new files (no restart needed)
# Hard-refresh in browser: Cmd+Shift+R
```

When you change backend code: restart the relevant terminal (Gateway or LangGraph).

---

## 5. Testing the Auth Flow

### 5.1 Via curl (Backend Direct)

```bash
BASE=http://localhost:8001  # Direct to gateway
# Or use BASE=http://localhost:2026 for nginx / BASE=http://localhost:3000 for Vite

# ── Register ──────────────────────────────────────────────────
curl -s $BASE/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "alice@test.com",
    "password": "SecurePass123!"
  }' | python3 -m json.tool

# Response:
# {
#     "access_token": "eyJhbGciOiJIUzI1NiIs...",
#     "user": {
#         "id": "abc123...",
#         "email": "alice@test.com",
#         "display_name": null,
#         "created_at": "2026-02-24T..."
#     }
# }

# ── Login ─────────────────────────────────────────────────────
RESPONSE=$(curl -s $BASE/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@test.com", "password": "SecurePass123!"}')

TOKEN=$(echo $RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "Token: $TOKEN"

# ── Authenticated Request ─────────────────────────────────────
curl -s $BASE/api/auth/me \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# ── Without Token (should fail) ───────────────────────────────
curl -s -o /dev/null -w "Status: %{http_code}\n" $BASE/api/auth/me
# → Status: 403

# ── With Expired/Fake Token (should fail) ─────────────────────
curl -s -o /dev/null -w "Status: %{http_code}\n" \
  $BASE/api/auth/me \
  -H "Authorization: Bearer fake.token.here"
# → Status: 401

# ── Register Duplicate Email (should fail) ────────────────────
curl -s -o /dev/null -w "Status: %{http_code}\n" \
  $BASE/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@test.com", "password": "AnotherPass123!"}'
# → Status: 409
```

### 5.2 Via Browser

1. Open the app (`:3000` or `:2026`)
2. You should see the login/register page
3. Register a new account
4. Verify you're redirected to the chat interface
5. Refresh the page — you should stay logged in (token refresh via cookie)
6. Open DevTools → Application → Cookies: verify `refresh_token` cookie exists
   with `httpOnly=true`, `path=/api/auth`

---

## 6. Testing Multi-User Isolation

This is the most important test. It validates that two users cannot see each
other's data.

### 6.1 Setup: Create Two Users

```bash
BASE=http://localhost:8001

# Register Alice
ALICE=$(curl -s $BASE/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@isolation.test","password":"Pass123!","display_name":"Alice"}')
ALICE_TOKEN=$(echo $ALICE | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Register Bob
BOB=$(curl -s $BASE/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"bob@isolation.test","password":"Pass123!","display_name":"Bob"}')
BOB_TOKEN=$(echo $BOB | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "Alice token: ${ALICE_TOKEN:0:20}..."
echo "Bob token:   ${BOB_TOKEN:0:20}..."
```

### 6.2 Test: Thread Isolation

```bash
# Alice's threads should not include Bob's, and vice versa.
# (Adjust endpoints based on your thread listing implementation)

# Alice lists her threads
curl -s $BASE/api/langgraph/threads/search \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool | head -20

# Bob lists his threads
curl -s $BASE/api/langgraph/threads/search \
  -H "Authorization: Bearer $BOB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -m json.tool | head -20
```

### 6.3 Test: Memory Isolation

```bash
# Alice's memory should be separate from Bob's
curl -s $BASE/api/memory/ \
  -H "Authorization: Bearer $ALICE_TOKEN" | python3 -m json.tool

curl -s $BASE/api/memory/ \
  -H "Authorization: Bearer $BOB_TOKEN" | python3 -m json.tool

# These should return different (or empty) memory objects
```

### 6.4 Test: Cross-User Access Denied

```bash
# If Alice has a thread, Bob should not be able to access it.
# Get one of Alice's thread IDs (if she has any), then try as Bob:

# ALICE_THREAD_ID=...  (get from Alice's thread list)
# curl -s $BASE/api/threads/$ALICE_THREAD_ID/artifacts/ \
#   -H "Authorization: Bearer $BOB_TOKEN"
# → Should return 403 Forbidden
```

### 6.5 Test: Browser-Based Multi-User

1. Open **Chrome** — log in as Alice
2. Open **Chrome Incognito** (or Safari/Firefox) — log in as Bob
3. Both chat simultaneously
4. Verify:
   - Alice's sidebar shows only her conversations
   - Bob's sidebar shows only his conversations
   - Alice's messages and agent responses do not appear in Bob's view
   - Memory settings are independent

---

## 7. Testing the Full Agent Flow

### 7.1 Via Browser

1. Log in at `http://localhost:3000` (Mode A) or `http://localhost:2026` (Mode B)
2. Start a new conversation
3. Send a message like: "Search the web for the current weather in Lausanne"
4. Verify:
   - SSE stream shows real-time agent thinking
   - Tool calls appear (web search, etc.)
   - Final response renders correctly
   - Thread title is auto-generated
5. Upload a file (PDF, image, or text)
6. Ask the agent about the uploaded file
7. Check that artifacts are accessible

### 7.2 Via curl (SSE Stream Test)

```bash
TOKEN="..."  # Use a valid token from login

# Create a thread
THREAD=$(curl -s http://localhost:2024/threads \
  -H "Content-Type: application/json" \
  -d '{}')
THREAD_ID=$(echo $THREAD | python3 -c "import sys,json; print(json.load(sys.stdin)['thread_id'])")
echo "Thread: $THREAD_ID"

# Send a message and stream the response
curl -N http://localhost:2024/threads/$THREAD_ID/runs/stream \
  -H "Content-Type: application/json" \
  -d '{
    "assistant_id": "lead_agent",
    "input": {
      "messages": [{"role": "human", "content": "What is 2+2?"}]
    },
    "stream_mode": ["events"]
  }'
# → SSE events stream in real-time
# Ctrl+C to stop
```

### 7.3 Verify PostgreSQL Checkpoints

After chatting, verify the conversation state is persisted in PostgreSQL (not
pickle files):

```bash
docker exec deer-flow-postgres psql -U deerflow -d deerflow -c "
  SELECT thread_id, created_at
  FROM checkpoints
  ORDER BY created_at DESC
  LIMIT 5;
" 2>/dev/null || echo "Checkpoints table may have a different name — check with: \\dt"
```

---

## 8. Testing the Static Build for Electron

The Electron desktop app uses the same frontend code but with a different build
mode and an explicit backend URL.

### 8.1 Build for Electron (Pointing to Local Backend)

```bash
cd frontend

# Build Electron app pointing to local backend
VITE_BACKEND_BASE_URL=http://localhost:8001 \
VITE_LANGGRAPH_BASE_URL=http://localhost:2024 \
  pnpm build:electron
```

### 8.2 Build for Electron (Pointing to Production)

```bash
VITE_BACKEND_BASE_URL=https://app.yourdomain.com \
VITE_LANGGRAPH_BASE_URL=https://app.yourdomain.com/api/langgraph \
  pnpm build:mac    # or build:win, build:linux
```

### 8.3 Verify Both Builds Co-Exist

| Build | Command | Output | Backend URL |
|-------|---------|--------|-------------|
| Web (static) | `pnpm build` | `dist/renderer/` | `""` (same origin, relative) |
| Electron (mac) | `pnpm build:mac` | `.dmg` installer | Explicit `https://...` |
| Electron (win) | `pnpm build:win` | `.exe` installer | Explicit `https://...` |

The web build and Electron build use different Vite modes (`web` vs `electron`),
so they don't interfere with each other.

---

## 9. Troubleshooting

### Port Already in Use

```bash
# Find what's using a port
lsof -i :8001  # gateway
lsof -i :2024  # langgraph
lsof -i :3000  # frontend
lsof -i :2026  # nginx

# Kill it
kill -9 $(lsof -ti :8001)
```

### Nginx Won't Start

```bash
# Test config syntax
nginx -t -c /tmp/thinktank-local-prod.conf

# Common issue: another nginx is running
pkill nginx
nginx -c /tmp/thinktank-local-prod.conf

# Check error log
# Errors go to stderr (visible in terminal)
```

### Nginx Serves JS as Wrong Content Type

If the browser console shows "MIME type not executable" errors, the `include
mime.types` line is missing or pointing to the wrong path. Verify:

```bash
# Find mime.types on your system
find /opt/homebrew /etc/nginx /usr/local -name mime.types 2>/dev/null
# Update the 'include' line in the nginx config to match
```

### Database Connection Refused

```bash
# Is PostgreSQL running?
docker ps | grep postgres

# Restart if needed
make db-start

# Check connection
docker exec deer-flow-postgres pg_isready -U deerflow
```

### LangGraph Fails to Start

```bash
# Check if DATABASE_URL is set
cd backend
DATABASE_URL=postgresql://deerflow:deerflow@localhost:5432/deerflow \
  uv run python -c "
from src.db.engine import check_db_connection
print(check_db_connection())
"
# → "healthy"
```

### Frontend Build Fails

```bash
cd frontend

# Check for type errors
pnpm typecheck

# Check for lint errors
pnpm lint

# Clean and rebuild
rm -rf dist node_modules/.vite
pnpm build
```

### SPA Routing Returns 404 in Nginx Mode

The `try_files $uri $uri/ /index.html` directive handles this. If you see 404s
for routes like `/chat/abc123`, verify:

1. The `root` path in the nginx config points to the correct `dist/renderer/` directory
2. `index.html` exists at that path
3. Nginx was reloaded after config changes: `nginx -c /tmp/thinktank-local-prod.conf -s reload`

---

## 10. Comparison: Local vs. Production

| Aspect | Local (Mode A) | Local (Mode B) | Production Server |
|--------|---------------|---------------|-------------------|
| Frontend serving | Vite dev server (HMR) | Nginx static files | Nginx static files |
| API proxy | Vite proxy (vite.config.ts) | Nginx proxy | Nginx proxy |
| TLS/HTTPS | No | No | Yes (Let's Encrypt) |
| CORS | Not enforced | Not configured | Locked to domain |
| Rate limiting | No | Yes (nginx zones) | Yes (nginx + Redis) |
| Database | Docker PostgreSQL | Docker PostgreSQL | Docker/Managed PostgreSQL |
| LangGraph checkpoints | PostgreSQL | PostgreSQL | PostgreSQL |
| Sandbox | LocalSandboxProvider | LocalSandboxProvider | AioSandboxProvider (containers) |
| Auth | JWT (HS256, auto-generated key) | JWT (HS256, auto-generated key) | JWT (env var or secrets manager) |
| Backend processes | Native (uv run) | Native (uv run) | Docker (Gunicorn) |
| Frontend rebuild | Instant (HMR) | `pnpm build` then refresh | `pnpm build` + copy to server |

### What Mode B Validates That Mode A Cannot

| Test | Mode A | Mode B |
|------|--------|--------|
| Static file serving (no Node.js runtime) | No | **Yes** |
| SPA fallback routing (`try_files`) | No | **Yes** |
| Asset caching headers (`Cache-Control: immutable`) | No | **Yes** |
| Nginx proxy behavior (rewrite rules, buffering) | No | **Yes** |
| Rate limiting (429 responses) | No | **Yes** |
| `mime.types` correctness (JS/CSS served correctly) | No | **Yes** |
| Production-identical request flow | No | **Yes** |

### When to Use Each

- **Mode A** — Writing code, debugging, testing features. Daily workflow.
- **Mode B** — Before deploying to a real server. Validates the build pipeline
  and nginx configuration. Run this at least once before your first deployment
  and after any nginx config changes.

---

## Quick Reference

```bash
# ── Daily Development (Mode A) ────────────────────────────────
make dev                         # Start everything
# → http://localhost:2026 (via nginx)
# → http://localhost:3000 (via Vite, also works)
make stop                        # Stop everything except PostgreSQL

# ── Production Simulation (Mode B) ────────────────────────────
make db-start && make db-migrate # Database
cd frontend && pnpm build        # Build static files

# Terminal 1:
cd backend && DATABASE_URL=postgresql://deerflow:deerflow@localhost:5432/deerflow \
  uv run langgraph dev --no-browser --allow-blocking

# Terminal 2:
cd backend && make gateway-db

# Start nginx:
nginx -c /tmp/thinktank-local-prod.conf
# → http://localhost:2026

# Stop nginx:
nginx -c /tmp/thinktank-local-prod.conf -s quit

# ── Database Management ───────────────────────────────────────
make db-start                    # Start PostgreSQL
make db-stop                     # Stop PostgreSQL
make db-migrate                  # Run migrations
make db-reset                    # Wipe and recreate (destructive!)

# ── Electron Builds ───────────────────────────────────────────
cd frontend
pnpm build:mac                   # macOS .dmg
pnpm build:win                   # Windows .exe
```
