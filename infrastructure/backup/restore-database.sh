#!/bin/bash
# =============================================================================
# Database Restore Script
# Phase 7: High Availability & Monitoring Infrastructure
# Version: 2.0
# Created: 2025-12-11
#
# Purpose:
# - Restore PostgreSQL database from backup
# - Support for encrypted and compressed backups
# - Download from remote storage
# - Point-in-time recovery (PITR) support
# - Pre-restore verification
#
# Usage:
#   ./restore-database.sh <backup_file>
#   ./restore-database.sh --latest
#   ./restore-database.sh --from-s3 <s3_path>
#   ./restore-database.sh --pitr <timestamp>
#
# WARNING: This script will DROP and recreate the target database!
# =============================================================================

set -euo pipefail

# =============================================================================
# CONFIGURATION
# =============================================================================

# Database configuration
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGDATABASE="${PGDATABASE:-trading_db}"
PGPASSWORD="${PGPASSWORD:-}"

# Backup configuration
BACKUP_DIR="${BACKUP_DIR:-/backups/postgres}"
TEMP_DIR="${TEMP_DIR:-/tmp/restore}"

# Remote storage configuration
S3_BUCKET="${S3_BUCKET:-crypto-bot-backups}"
S3_PREFIX="${S3_PREFIX:-database}"
AWS_REGION="${AWS_REGION:-us-east-1}"

# Encryption configuration
GPG_PASSPHRASE="${GPG_PASSPHRASE:-}"

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" >&2
}

log_warning() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARNING: $1" >&2
}

confirm_action() {
    local message="$1"
    read -p "${message} (yes/no): " -r response
    if [[ "${response}" != "yes" ]]; then
        log "Operation cancelled by user"
        exit 0
    fi
}

create_temp_dir() {
    log "Creating temporary directory: ${TEMP_DIR}"
    mkdir -p "${TEMP_DIR}"
    chmod 700 "${TEMP_DIR}"
}

cleanup_temp_dir() {
    log "Cleaning up temporary files..."
    rm -rf "${TEMP_DIR}"
}

verify_checksum() {
    local file="$1"
    local checksum_file="${file}.sha256"

    if [[ ! -f "${checksum_file}" ]]; then
        log_warning "Checksum file not found, skipping verification"
        return 0
    fi

    log "Verifying checksum..."
    local stored_checksum
    stored_checksum=$(cat "${checksum_file}")
    local current_checksum
    current_checksum=$(sha256sum "${file}" | awk '{print $1}')

    if [[ "${stored_checksum}" != "${current_checksum}" ]]; then
        log_error "Checksum verification FAILED!"
        log_error "Expected: ${stored_checksum}"
        log_error "Got: ${current_checksum}"
        return 1
    fi

    log "Checksum verified successfully"
    return 0
}

# =============================================================================
# DOWNLOAD FUNCTIONS
# =============================================================================

download_from_s3() {
    local s3_path="$1"
    local local_file="${TEMP_DIR}/$(basename "${s3_path}")"

    log "Downloading backup from S3: ${s3_path}"
    aws s3 cp "${s3_path}" "${local_file}" --region "${AWS_REGION}"

    # Download checksum if available
    aws s3 cp "${s3_path}.sha256" "${local_file}.sha256" --region "${AWS_REGION}" || true

    echo "${local_file}"
}

find_latest_backup() {
    local latest_link="${BACKUP_DIR}/${PGDATABASE}_latest.backup"

    if [[ -L "${latest_link}" ]]; then
        readlink -f "${latest_link}"
    else
        # Find the most recent backup file
        find "${BACKUP_DIR}" -name "${PGDATABASE}_full_*.sql.gz*" -type f | sort -r | head -1
    fi
}

list_available_backups() {
    log "Available local backups:"
    find "${BACKUP_DIR}" -name "${PGDATABASE}_*.sql.gz*" -type f | sort -r | while read -r file; do
        local size
        size=$(du -h "${file}" | awk '{print $1}')
        local date
        date=$(stat -c '%y' "${file}" 2>/dev/null || stat -f '%Sm' "${file}" 2>/dev/null)
        echo "  ${file} (${size}, ${date})"
    done

    if [[ "${REMOTE_BACKUP_ENABLED:-false}" == "true" ]]; then
        log "Available remote backups:"
        aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/" --region "${AWS_REGION}" | grep -E '\.sql\.gz' || true
    fi
}

# =============================================================================
# DECRYPT/DECOMPRESS FUNCTIONS
# =============================================================================

decrypt_file() {
    local encrypted_file="$1"
    local decrypted_file="${encrypted_file%.gpg}"

    log "Decrypting backup..."

    if [[ -n "${GPG_PASSPHRASE}" ]]; then
        echo "${GPG_PASSPHRASE}" | gpg --batch --passphrase-fd 0 --decrypt \
            --output "${decrypted_file}" "${encrypted_file}"
    else
        gpg --decrypt --output "${decrypted_file}" "${encrypted_file}"
    fi

    echo "${decrypted_file}"
}

decompress_file() {
    local compressed_file="$1"
    local decompressed_file="${compressed_file%.gz}"

    log "Decompressing backup..."
    gunzip -k "${compressed_file}"

    echo "${decompressed_file}"
}

prepare_backup_file() {
    local input_file="$1"
    local working_file="${input_file}"

    # Copy to temp directory
    local temp_file="${TEMP_DIR}/$(basename "${input_file}")"
    if [[ "${input_file}" != "${temp_file}" ]]; then
        cp "${input_file}" "${temp_file}"
        working_file="${temp_file}"

        # Copy checksum if exists
        [[ -f "${input_file}.sha256" ]] && cp "${input_file}.sha256" "${temp_file}.sha256"
    fi

    # Verify checksum
    verify_checksum "${working_file}"

    # Decrypt if GPG encrypted
    if [[ "${working_file}" == *.gpg ]]; then
        working_file=$(decrypt_file "${working_file}")
    fi

    # Decompress if gzipped
    if [[ "${working_file}" == *.gz ]]; then
        working_file=$(decompress_file "${working_file}")
    fi

    echo "${working_file}"
}

# =============================================================================
# RESTORE FUNCTIONS
# =============================================================================

check_database_connection() {
    log "Checking database connection..."

    PGPASSWORD="${PGPASSWORD}" psql \
        -h "${PGHOST}" \
        -p "${PGPORT}" \
        -U "${PGUSER}" \
        -d "postgres" \
        -c "SELECT 1;" > /dev/null 2>&1 || {
            log_error "Cannot connect to database server"
            return 1
        }

    log "Database connection successful"
    return 0
}

stop_services() {
    log "Stopping dependent services before restore..."

    # If running in Docker/Kubernetes, stop trading services
    if command -v docker &> /dev/null; then
        docker stop crypto-bot-trading-engine 2>/dev/null || true
        docker stop crypto-bot-api-gateway 2>/dev/null || true
    fi

    if command -v kubectl &> /dev/null; then
        kubectl scale deployment trading-engine --replicas=0 -n crypto-bot 2>/dev/null || true
        kubectl scale deployment api-gateway --replicas=0 -n crypto-bot 2>/dev/null || true
    fi

    log "Services stopped"
}

start_services() {
    log "Starting services after restore..."

    if command -v docker &> /dev/null; then
        docker start crypto-bot-trading-engine 2>/dev/null || true
        docker start crypto-bot-api-gateway 2>/dev/null || true
    fi

    if command -v kubectl &> /dev/null; then
        kubectl scale deployment trading-engine --replicas=3 -n crypto-bot 2>/dev/null || true
        kubectl scale deployment api-gateway --replicas=2 -n crypto-bot 2>/dev/null || true
    fi

    log "Services started"
}

terminate_connections() {
    log "Terminating existing connections to ${PGDATABASE}..."

    PGPASSWORD="${PGPASSWORD}" psql \
        -h "${PGHOST}" \
        -p "${PGPORT}" \
        -U "${PGUSER}" \
        -d "postgres" \
        -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${PGDATABASE}' AND pid <> pg_backend_pid();" || true

    sleep 2
}

drop_database() {
    log "Dropping database ${PGDATABASE}..."

    PGPASSWORD="${PGPASSWORD}" psql \
        -h "${PGHOST}" \
        -p "${PGPORT}" \
        -U "${PGUSER}" \
        -d "postgres" \
        -c "DROP DATABASE IF EXISTS ${PGDATABASE};"

    log "Database dropped"
}

create_database() {
    log "Creating database ${PGDATABASE}..."

    PGPASSWORD="${PGPASSWORD}" psql \
        -h "${PGHOST}" \
        -p "${PGPORT}" \
        -U "${PGUSER}" \
        -d "postgres" \
        -c "CREATE DATABASE ${PGDATABASE};"

    log "Database created"
}

restore_from_sql() {
    local sql_file="$1"

    log "Restoring database from: ${sql_file}"
    log "This may take several minutes..."

    PGPASSWORD="${PGPASSWORD}" psql \
        -h "${PGHOST}" \
        -p "${PGPORT}" \
        -U "${PGUSER}" \
        -d "${PGDATABASE}" \
        -f "${sql_file}" 2>&1 | while read -r line; do
            # Only log errors and important messages
            if [[ "${line}" == *"ERROR"* ]] || [[ "${line}" == *"NOTICE"* ]]; then
                log "psql: ${line}"
            fi
        done

    log "Restore completed"
}

verify_restore() {
    log "Verifying restore..."

    # Check if tables exist
    local table_count
    table_count=$(PGPASSWORD="${PGPASSWORD}" psql \
        -h "${PGHOST}" \
        -p "${PGPORT}" \
        -U "${PGUSER}" \
        -d "${PGDATABASE}" \
        -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';")

    table_count=$(echo "${table_count}" | tr -d ' ')

    if [[ "${table_count}" -gt 0 ]]; then
        log "Restore verified: ${table_count} tables found"
        return 0
    else
        log_error "Restore verification failed: no tables found"
        return 1
    fi
}

perform_restore() {
    local backup_file="$1"

    # Create temp directory
    create_temp_dir
    trap cleanup_temp_dir EXIT

    # Prepare backup file (decrypt/decompress)
    local sql_file
    sql_file=$(prepare_backup_file "${backup_file}")

    # Check database connection
    check_database_connection

    # Confirmation
    log_warning "This will DROP and recreate database: ${PGDATABASE}"
    confirm_action "Are you sure you want to proceed?"

    # Stop dependent services
    stop_services

    # Terminate existing connections
    terminate_connections

    # Drop and recreate database
    drop_database
    create_database

    # Restore from SQL
    restore_from_sql "${sql_file}"

    # Verify restore
    verify_restore

    # Start services
    start_services
}

# =============================================================================
# PITR (Point-in-Time Recovery) FUNCTIONS
# =============================================================================

perform_pitr() {
    local target_timestamp="$1"
    local wal_archive_dir="${BACKUP_DIR}/wal_archive"

    log "Performing Point-in-Time Recovery to: ${target_timestamp}"
    log_warning "PITR requires PostgreSQL to be configured with WAL archiving"

    # This is a simplified PITR procedure
    # Full PITR requires:
    # 1. Base backup
    # 2. WAL archive files
    # 3. recovery.conf or recovery.signal with recovery_target_time

    # Find the appropriate base backup
    local base_backup
    base_backup=$(find "${BACKUP_DIR}" -name "${PGDATABASE}_full_*.sql.gz*" -type f | \
        while read -r file; do
            local backup_time
            backup_time=$(basename "${file}" | grep -oP '\d{8}_\d{6}')
            if [[ "${backup_time}" < "${target_timestamp//[:-]/}" ]]; then
                echo "${file}"
            fi
        done | sort -r | head -1)

    if [[ -z "${base_backup}" ]]; then
        log_error "No suitable base backup found for PITR target: ${target_timestamp}"
        exit 1
    fi

    log "Using base backup: ${base_backup}"
    log "WAL archive directory: ${wal_archive_dir}"

    # Create recovery configuration
    cat > "${TEMP_DIR}/recovery.conf" << EOF
restore_command = 'cp ${wal_archive_dir}/%f %p'
recovery_target_time = '${target_timestamp}'
recovery_target_action = 'promote'
EOF

    log_warning "PITR requires manual PostgreSQL restart with recovery.conf"
    log "Recovery configuration written to: ${TEMP_DIR}/recovery.conf"
    log "Please follow the PostgreSQL PITR documentation to complete the recovery"
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

show_usage() {
    cat << EOF
Database Restore Script

Usage:
    $0 <backup_file>        Restore from local backup file
    $0 --latest             Restore from latest backup
    $0 --from-s3 <s3_path>  Restore from S3 backup
    $0 --pitr <timestamp>   Point-in-Time Recovery
    $0 --list               List available backups
    $0 --help               Show this help message

Examples:
    $0 /backups/trading_db_full_20251211_020000.sql.gz
    $0 --latest
    $0 --from-s3 s3://crypto-bot-backups/database/trading_db_full_20251211_020000.sql.gz
    $0 --pitr "2025-12-11 14:30:00"

WARNING: Restore operations will DROP and recreate the target database!
EOF
}

main() {
    local start_time
    start_time=$(date +%s)

    log "==================================================================="
    log "Database Restore Script"
    log "Target database: ${PGDATABASE}"
    log "Target host: ${PGHOST}:${PGPORT}"
    log "==================================================================="

    case "${1:-}" in
        --help|-h)
            show_usage
            exit 0
            ;;
        --list)
            list_available_backups
            exit 0
            ;;
        --latest)
            local latest_backup
            latest_backup=$(find_latest_backup)
            if [[ -z "${latest_backup}" ]]; then
                log_error "No backup files found"
                exit 1
            fi
            log "Using latest backup: ${latest_backup}"
            perform_restore "${latest_backup}"
            ;;
        --from-s3)
            if [[ -z "${2:-}" ]]; then
                log_error "S3 path required"
                show_usage
                exit 1
            fi
            create_temp_dir
            trap cleanup_temp_dir EXIT
            local downloaded_file
            downloaded_file=$(download_from_s3 "$2")
            perform_restore "${downloaded_file}"
            ;;
        --pitr)
            if [[ -z "${2:-}" ]]; then
                log_error "Target timestamp required"
                show_usage
                exit 1
            fi
            perform_pitr "$2"
            ;;
        "")
            log_error "Backup file or option required"
            show_usage
            exit 1
            ;;
        *)
            if [[ ! -f "$1" ]]; then
                log_error "Backup file not found: $1"
                exit 1
            fi
            perform_restore "$1"
            ;;
    esac

    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))

    log "==================================================================="
    log "Restore completed successfully"
    log "Duration: ${duration} seconds"
    log "==================================================================="
}

# Run main function
main "$@"
