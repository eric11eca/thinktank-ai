#!/usr/bin/env bash
# =============================================================================
# ERP Sample Database Setup Script
# =============================================================================
# Idempotent: safe to run multiple times.
#
# Usage:
#   ./setup-erp.sh                          # Uses Docker container thinktank-postgres
#   ./setup-erp.sh --direct                 # Uses psql directly (CI/already-running PG)
#
# Environment variables (for --direct mode):
#   PGHOST     (default: localhost)
#   PGPORT     (default: 5432)
#   PGUSER     (default: thinktank)
#   PGPASSWORD (default: matterhorn)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SQL_FILE="${SCRIPT_DIR}/init-erp.sql"
DB_NAME="erp_sample"
CONTAINER_NAME="thinktank-postgres"

PG_USER="${PGUSER:-thinktank}"
PG_PASS="${PGPASSWORD:-matterhorn}"
PG_HOST="${PGHOST:-localhost}"
PG_PORT="${PGPORT:-5432}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() { echo "[erp-setup] $*"; }

run_psql_docker() {
    docker exec -e PGPASSWORD="${PG_PASS}" "${CONTAINER_NAME}" psql -U "${PG_USER}" "$@"
}

run_psql_direct() {
    PGPASSWORD="${PG_PASS}" psql -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" "$@"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
MODE="docker"
if [[ "${1:-}" == "--direct" ]]; then
    MODE="direct"
fi

if [[ "${MODE}" == "docker" ]]; then
    # Verify container is running
    if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        log "ERROR: Container '${CONTAINER_NAME}' is not running."
        log "Start it with: make db-start"
        exit 1
    fi
    PSQL="run_psql_docker"
else
    if ! command -v psql &>/dev/null; then
        log "ERROR: psql not found. Install postgresql-client."
        exit 1
    fi
    PSQL="run_psql_direct"
fi

# Create database if it doesn't exist
DB_EXISTS=$($PSQL -tc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" 2>/dev/null | tr -d ' ')
if [[ "${DB_EXISTS}" != "1" ]]; then
    log "Creating database '${DB_NAME}'..."
    $PSQL -c "CREATE DATABASE ${DB_NAME}"
else
    log "Database '${DB_NAME}' already exists"
fi

# Run init script
log "Running init-erp.sql..."
if [[ "${MODE}" == "docker" ]]; then
    docker cp "${SQL_FILE}" "${CONTAINER_NAME}:/tmp/init-erp.sql"
    run_psql_docker -d "${DB_NAME}" -f /tmp/init-erp.sql -q
else
    run_psql_direct -d "${DB_NAME}" -f "${SQL_FILE}" -q
fi

# Verify
COUNTS=$($PSQL -d "${DB_NAME}" -t -c "
    SELECT string_agg(tbl || '=' || cnt, ', ')
    FROM (
        SELECT 'departments' AS tbl, COUNT(*)::text AS cnt FROM departments
        UNION ALL SELECT 'employees', COUNT(*)::text FROM employees
        UNION ALL SELECT 'products', COUNT(*)::text FROM products
        UNION ALL SELECT 'customers', COUNT(*)::text FROM customers
        UNION ALL SELECT 'orders', COUNT(*)::text FROM orders
        UNION ALL SELECT 'order_items', COUNT(*)::text FROM order_items
    ) sub
" 2>/dev/null | tr -d ' ')

log "ERP database ready: ${COUNTS}"
log "Connection: postgresql://${PG_USER}:****@${PG_HOST}:${PG_PORT}/${DB_NAME}"
