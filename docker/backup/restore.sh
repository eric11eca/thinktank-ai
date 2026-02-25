#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Thinktank.ai — PostgreSQL Restore Script
# ─────────────────────────────────────────────────────────────────────────────
# Restores a PostgreSQL database from a backup file (local or S3).
#
# Usage:
#   ./restore.sh <backup_file>           Restore from local .sql.gz file
#   ./restore.sh --latest                Restore the latest daily backup
#   ./restore.sh --from-s3 <s3_key>      Download from S3 and restore
#   ./restore.sh --list                  List available local backups
#   ./restore.sh --list-s3               List available S3 backups
#
# Environment variables:
#   PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE — PostgreSQL connection
#   BACKUP_DIR      - Local backup directory (default: /backups)
#   S3_BUCKET       - S3 bucket (required for --from-s3, --list-s3)
#   S3_PREFIX       - S3 key prefix (default: backups/)
#   S3_ENDPOINT_URL - S3 endpoint for MinIO (optional)
# ─────────────────────────────────────────────────────────────────────────────

PGHOST="${PGHOST:-postgres}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-thinktank}"
PGDATABASE="${PGDATABASE:-thinktank}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="${S3_PREFIX:-backups/}"
S3_ENDPOINT_URL="${S3_ENDPOINT_URL:-}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
log_error() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2; }

# ── Commands ─────────────────────────────────────────────────────────────────

list_local_backups() {
    log "Available local backups:"
    echo ""
    for type in daily weekly monthly; do
        local dir="${BACKUP_DIR}/${type}"
        if [[ -d "$dir" ]]; then
            local count
            count=$(find "$dir" -name "*.sql.gz" -type f 2>/dev/null | wc -l | tr -d ' ')
            echo "  ${type} (${count} backups):"
            find "$dir" -name "*.sql.gz" -type f -exec ls -lh {} \; 2>/dev/null \
                | awk '{print "    " $NF " (" $5 ")"}'
        fi
    done
    echo ""
}

list_s3_backups() {
    if [[ -z "$S3_BUCKET" ]]; then
        log_error "S3_BUCKET not set"
        exit 1
    fi

    local aws_args=()
    if [[ -n "$S3_ENDPOINT_URL" ]]; then
        aws_args+=(--endpoint-url "$S3_ENDPOINT_URL")
    fi

    log "Available S3 backups (s3://${S3_BUCKET}/${S3_PREFIX}):"
    echo ""
    aws s3 ls "${aws_args[@]}" "s3://${S3_BUCKET}/${S3_PREFIX}" --recursive \
        | grep "\.sql\.gz$" \
        | sort -r \
        | head -20
    echo ""
}

download_from_s3() {
    local s3_key="$1"
    local filename
    filename=$(basename "$s3_key")
    local local_path="${BACKUP_DIR}/restored/${filename}"

    mkdir -p "${BACKUP_DIR}/restored"

    local aws_args=()
    if [[ -n "$S3_ENDPOINT_URL" ]]; then
        aws_args+=(--endpoint-url "$S3_ENDPOINT_URL")
    fi

    log "Downloading s3://${S3_BUCKET}/${s3_key} to ${local_path}"
    aws s3 cp "${aws_args[@]}" "s3://${S3_BUCKET}/${s3_key}" "$local_path"
    echo "$local_path"
}

find_latest_backup() {
    local latest
    latest=$(find "${BACKUP_DIR}" -name "*.sql.gz" -type f 2>/dev/null \
        | sort -r \
        | head -1)

    if [[ -z "$latest" ]]; then
        log_error "No local backups found in ${BACKUP_DIR}"
        exit 1
    fi

    echo "$latest"
}

create_safety_backup() {
    log "Creating safety backup of current database state..."
    local safety_file="${BACKUP_DIR}/safety/pre_restore_$(date +%Y%m%d_%H%M%S).sql.gz"
    mkdir -p "${BACKUP_DIR}/safety"

    if pg_dump -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" \
        --no-owner --no-acl | gzip -9 > "$safety_file"; then
        log "Safety backup created: ${safety_file}"
    else
        log_error "Failed to create safety backup — proceeding anyway"
    fi
}

restore_database() {
    local filepath="$1"

    log "========================================="
    log "  Thinktank.ai Database Restore"
    log "========================================="
    log "Source: ${filepath}"
    log "Target: ${PGHOST}:${PGPORT}/${PGDATABASE}"

    # Verify file exists
    if [[ ! -f "$filepath" ]]; then
        log_error "Backup file not found: ${filepath}"
        exit 1
    fi

    # Verify gzip integrity
    if ! gzip -t "$filepath" 2>/dev/null; then
        log_error "Backup file is corrupted: ${filepath}"
        exit 1
    fi

    # Verify PostgreSQL is reachable
    if ! pg_isready -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -q 2>/dev/null; then
        log_error "PostgreSQL is not reachable at ${PGHOST}:${PGPORT}"
        exit 1
    fi

    # Safety confirmation (only in interactive mode)
    if [[ -t 0 ]]; then
        echo ""
        echo "WARNING: This will DROP and RECREATE the ${PGDATABASE} database."
        echo "         All current data will be replaced by the backup."
        echo ""
        read -rp "Are you sure? Type 'yes' to confirm: " confirm
        if [[ "$confirm" != "yes" ]]; then
            log "Restore cancelled"
            exit 0
        fi
    fi

    # Create safety backup first
    create_safety_backup

    # Restore the backup
    log "Restoring database from ${filepath}..."
    if zcat "$filepath" | psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" \
        --single-transaction --set ON_ERROR_STOP=on 2>&1; then
        log "Database restored successfully from ${filepath}"
    else
        log_error "Restore failed — check logs. Safety backup available in ${BACKUP_DIR}/safety/"
        exit 1
    fi

    log "Restore completed"
}

# ── Main ─────────────────────────────────────────────────────────────────────

main() {
    local command="${1:-}"

    case "$command" in
        --list)
            list_local_backups
            ;;
        --list-s3)
            list_s3_backups
            ;;
        --latest)
            local latest
            latest=$(find_latest_backup)
            restore_database "$latest"
            ;;
        --from-s3)
            local s3_key="${2:?Usage: restore.sh --from-s3 <s3_key>}"
            local local_path
            local_path=$(download_from_s3 "$s3_key")
            restore_database "$local_path"
            ;;
        --help|-h|"")
            echo "Usage:"
            echo "  $0 <backup_file>           Restore from local .sql.gz file"
            echo "  $0 --latest                Restore the latest daily backup"
            echo "  $0 --from-s3 <s3_key>      Download from S3 and restore"
            echo "  $0 --list                  List available local backups"
            echo "  $0 --list-s3               List available S3 backups"
            echo "  $0 --help                  Show this message"
            ;;
        *)
            # Assume it's a file path
            restore_database "$command"
            ;;
    esac
}

main "$@"
