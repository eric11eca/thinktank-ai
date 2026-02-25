#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Thinktank.ai — Staging Stack Management
# ─────────────────────────────────────────────────────────────────────────────
# Manages the staging Docker Compose stack (mirrors production with debugging).
#
# Usage:
#   ./scripts/staging.sh start          Start the staging stack
#   ./scripts/staging.sh stop           Stop all staging services
#   ./scripts/staging.sh restart        Rebuild and restart
#   ./scripts/staging.sh status         Show service status
#   ./scripts/staging.sh logs [service] Tail logs
#   ./scripts/staging.sh build          Build images without starting
#   ./scripts/staging.sh health         Check health of all services
#   ./scripts/staging.sh test           Run Playwright E2E tests
#   ./scripts/staging.sh seed           Seed test data into the database
#   ./scripts/staging.sh reset          Stop, remove volumes, and restart fresh
#   ./scripts/staging.sh clean          Stop and remove volumes (destructive)
#   ./scripts/staging.sh help           Show this help message
# ─────────────────────────────────────────────────────────────────────────────

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DOCKER_DIR="$PROJECT_ROOT/docker"
COMPOSE_FILE="$DOCKER_DIR/docker-compose-staging.yaml"
ENV_FILE="$DOCKER_DIR/.env.staging"

# Defaults
export DB_PASSWORD="${DB_PASSWORD:-staging-password}"
export NGINX_HTTP_PORT="${NGINX_HTTP_PORT:-8080}"

# Load staging .env if it exists
if [[ -f "$ENV_FILE" ]]; then
    set -a
    source "$ENV_FILE"
    set +a
elif [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# ── Helpers ──────────────────────────────────────────────────────────────────

compose() {
    docker compose -f "$COMPOSE_FILE" "$@"
}

log_info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
log_ok()      { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $*"; }
log_header()  { echo -e "\n${BOLD}$*${NC}\n"; }

wait_for_healthy() {
    local service="$1"
    local max_wait="${2:-60}"
    local elapsed=0

    while [[ $elapsed -lt $max_wait ]]; do
        local status
        status=$(compose ps --format json "$service" 2>/dev/null \
            | grep -o '"Health":"[^"]*"' \
            | head -1 \
            | cut -d'"' -f4) || true

        if [[ "$status" == "healthy" ]]; then
            return 0
        fi

        sleep 2
        elapsed=$((elapsed + 2))
    done
    return 1
}

wait_for_url() {
    local url="$1"
    local max_wait="${2:-60}"
    local elapsed=0

    while [[ $elapsed -lt $max_wait ]]; do
        if curl -sf -o /dev/null "$url" 2>/dev/null; then
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    return 1
}

# ── Commands ─────────────────────────────────────────────────────────────────

cmd_build() {
    log_header "Building Staging Images"
    compose build "$@"
    log_ok "All staging images built"
}

cmd_start() {
    log_header "Starting Thinktank.ai Staging Stack"

    local port="${NGINX_HTTP_PORT:-8080}"

    log_info "Configuration:"
    echo "       NGINX_HTTP_PORT = $port"
    echo "       LOG_LEVEL       = ${LOG_LEVEL:-DEBUG}"
    echo ""

    log_info "Building and starting services..."
    compose up --build -d

    log_info "Waiting for PostgreSQL..."
    if wait_for_healthy postgres 30; then
        log_ok "PostgreSQL is healthy"
    else
        log_error "PostgreSQL did not become healthy"
        compose logs postgres --tail=10
        return 1
    fi

    log_info "Waiting for Redis..."
    if wait_for_healthy redis 15; then
        log_ok "Redis is healthy"
    else
        log_error "Redis did not become healthy"
        return 1
    fi

    log_info "Waiting for Gateway API..."
    if wait_for_url "http://localhost:${port}/health" 90; then
        log_ok "Gateway API is healthy"
    else
        log_warn "Gateway health check did not pass within 90s"
    fi

    log_header "Staging Environment is Running!"
    echo "  Application:     http://localhost:${port}"
    echo "  API Gateway:     http://localhost:${port}/api/*"
    echo "  Health:          http://localhost:${port}/health"
    echo "  MinIO Console:   http://localhost:${STAGING_MINIO_CONSOLE_PORT:-9001}"
    echo "  PostgreSQL:      localhost:${STAGING_PG_PORT:-15432}"
    echo "  Redis:           localhost:${STAGING_REDIS_PORT:-16379}"
    echo ""
    echo "  Commands:"
    echo "    $0 status    Service status"
    echo "    $0 logs      Follow logs"
    echo "    $0 health    Health checks"
    echo "    $0 test      Run E2E tests"
    echo "    $0 seed      Seed test data"
    echo ""
}

cmd_stop() {
    log_header "Stopping Staging Stack"
    compose down
    log_ok "All staging services stopped (volumes preserved)"
}

cmd_restart() {
    log_header "Restarting Staging Stack"
    compose down
    cmd_start
}

cmd_status() {
    log_header "Staging Service Status"
    compose ps
}

cmd_logs() {
    local service="${1:-}"
    if [[ -n "$service" ]]; then
        log_info "Following staging logs for: $service"
        compose logs -f "$service"
    else
        log_info "Following all staging logs (Ctrl+C to stop)"
        compose logs -f
    fi
}

cmd_health() {
    log_header "Staging Health Check"

    local port="${NGINX_HTTP_PORT:-8080}"
    local base="http://localhost:${port}"

    echo -n "  nginx (frontend)  ... "
    if curl -sf -o /dev/null "$base/"; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${RED}FAIL${NC}"
    fi

    echo -n "  SPA fallback      ... "
    if curl -sf -o /dev/null "$base/login"; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${RED}FAIL${NC}"
    fi

    echo -n "  gateway /health   ... "
    local health_body
    health_body=$(curl -sf "$base/health" 2>/dev/null) || true
    if echo "$health_body" | grep -q '"healthy"' 2>/dev/null; then
        echo -e "${GREEN}OK${NC}  $health_body"
    else
        local http_code
        http_code=$(curl -sf -o /dev/null -w "%{http_code}" "$base/health" 2>/dev/null) || http_code="000"
        echo -e "${RED}FAIL${NC}  (HTTP $http_code)"
    fi

    echo -n "  MinIO             ... "
    if curl -sf -o /dev/null "http://localhost:${STAGING_MINIO_API_PORT:-9000}/minio/health/live" 2>/dev/null; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${YELLOW}WARN${NC}"
    fi

    echo ""
}

cmd_seed() {
    log_header "Seeding Staging Database"

    log_info "Creating test users and data..."

    # Use the gateway container to run seed commands
    compose exec -T gateway sh -c '
        cd backend && uv run python -c "
import asyncio
from src.auth.user_store import DatabaseUserStore
from src.db.connection import get_engine

async def seed():
    engine = get_engine()
    store = DatabaseUserStore(engine)

    # Create test users
    test_users = [
        (\"test@staging.local\", \"TestPassword123!\"),
        (\"admin@staging.local\", \"AdminPassword123!\"),
    ]

    for email, password in test_users:
        try:
            user = await store.create_user(email, password)
            print(f\"  Created user: {email} (id={user.id})\")
        except Exception as e:
            print(f\"  User {email} already exists or error: {e}\")

asyncio.run(seed())
"' 2>/dev/null && log_ok "Test data seeded" || log_warn "Seed may have partially failed — check logs"
}

cmd_reset() {
    log_header "Resetting Staging Environment"
    log_warn "This will DELETE all staging data and restart fresh."
    read -rp "Are you sure? [y/N] " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        compose down -v
        log_ok "Staging data removed"
        cmd_start
    else
        log_info "Cancelled"
    fi
}

cmd_clean() {
    log_header "Cleaning Up Staging (removing volumes)"
    log_warn "This will DELETE all staging data."
    read -rp "Are you sure? [y/N] " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        compose down -v
        log_ok "Staging stack stopped and volumes removed"
    else
        log_info "Cancelled"
    fi
}

cmd_test() {
    log_header "Running Playwright E2E Tests (Staging)"

    local port="${NGINX_HTTP_PORT:-8080}"

    log_info "Testing against http://localhost:${port}"

    if ! curl -sf -o /dev/null "http://localhost:${port}/" 2>/dev/null; then
        log_error "Staging stack is not running on port $port. Start it first: $0 start"
        return 1
    fi

    cd "$PROJECT_ROOT/frontend" && \
        E2E_BASE_URL="http://localhost:${port}" \
        pnpm test:e2e
}

cmd_help() {
    echo ""
    echo -e "${BOLD}Thinktank.ai Staging Stack${NC}"
    echo ""
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  start              Build and start all staging services"
    echo "  stop               Stop all services (preserves data)"
    echo "  restart            Rebuild and restart"
    echo "  status             Show service status"
    echo "  logs [service]     Follow logs (all or specific service)"
    echo "  build              Build images without starting"
    echo "  health             Run health checks"
    echo "  test               Run Playwright E2E tests"
    echo "  seed               Seed test data into the database"
    echo "  reset              Stop, delete data, and restart fresh"
    echo "  clean              Stop and delete all staging data"
    echo "  help               Show this message"
    echo ""
    echo "Services: nginx, gateway, langgraph, worker, postgres, redis, minio, backup"
    echo ""
}

# ── Main ─────────────────────────────────────────────────────────────────────

main() {
    case "${1:-help}" in
        start)   cmd_start ;;
        stop)    cmd_stop ;;
        restart) cmd_restart ;;
        status)  cmd_status ;;
        logs)    shift; cmd_logs "$@" ;;
        build)   shift; cmd_build "$@" ;;
        health)  cmd_health ;;
        test)    cmd_test ;;
        seed)    cmd_seed ;;
        reset)   cmd_reset ;;
        clean)   cmd_clean ;;
        help|--help|-h) cmd_help ;;
        *)
            log_error "Unknown command: $1"
            cmd_help
            exit 1
            ;;
    esac
}

main "$@"
