#!/bin/bash
# =============================================================================
# Database Backup Script
# Phase 7: High Availability & Monitoring Infrastructure
# Version: 2.0
# Created: 2025-12-11
#
# Purpose:
# - Automated PostgreSQL database backup
# - Compression and encryption of backup files
# - Upload to remote storage (S3/GCS compatible)
# - Retention policy management
# - Slack/Telegram notification on success/failure
#
# Usage:
#   ./backup-database.sh [full|incremental]
#
# Scheduling (cron):
#   # Full backup daily at 2 AM
#   0 2 * * * /path/to/backup-database.sh full
#   # Incremental backup every 6 hours
#   0 */6 * * * /path/to/backup-database.sh incremental
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
BACKUP_TYPE="${1:-full}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
COMPRESSION_LEVEL="${COMPRESSION_LEVEL:-9}"

# Remote storage configuration (S3 compatible)
REMOTE_BACKUP_ENABLED="${REMOTE_BACKUP_ENABLED:-false}"
S3_BUCKET="${S3_BUCKET:-crypto-bot-backups}"
S3_PREFIX="${S3_PREFIX:-database}"
AWS_REGION="${AWS_REGION:-us-east-1}"

# Encryption configuration
ENCRYPTION_ENABLED="${ENCRYPTION_ENABLED:-true}"
ENCRYPTION_KEY="${ENCRYPTION_KEY:-}"
GPG_RECIPIENT="${GPG_RECIPIENT:-}"

# Notification configuration
NOTIFICATION_ENABLED="${NOTIFICATION_ENABLED:-false}"
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-}"

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" >&2
}

send_notification() {
    local status="$1"
    local message="$2"
    local details="${3:-}"

    if [[ "${NOTIFICATION_ENABLED}" != "true" ]]; then
        return 0
    fi

    # Send Slack notification
    if [[ -n "${SLACK_WEBHOOK_URL}" ]]; then
        local color="good"
        [[ "${status}" == "error" ]] && color="danger"
        [[ "${status}" == "warning" ]] && color="warning"

        curl -s -X POST "${SLACK_WEBHOOK_URL}" \
            -H "Content-Type: application/json" \
            -d "{
                \"attachments\": [{
                    \"color\": \"${color}\",
                    \"title\": \"Database Backup - ${status^^}\",
                    \"text\": \"${message}\",
                    \"fields\": [{
                        \"title\": \"Details\",
                        \"value\": \"${details}\",
                        \"short\": false
                    }],
                    \"footer\": \"Crypto Trading Bot Backup System\",
                    \"ts\": $(date +%s)
                }]
            }" || true
    fi

    # Send Telegram notification
    if [[ -n "${TELEGRAM_BOT_TOKEN}" && -n "${TELEGRAM_CHAT_ID}" ]]; then
        local emoji="✅"
        [[ "${status}" == "error" ]] && emoji="❌"
        [[ "${status}" == "warning" ]] && emoji="⚠️"

        curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${TELEGRAM_CHAT_ID}" \
            -d "text=${emoji} *Database Backup - ${status^^}*%0A%0A${message}%0A%0A${details}" \
            -d "parse_mode=Markdown" || true
    fi
}

calculate_checksum() {
    local file="$1"
    sha256sum "${file}" | awk '{print $1}'
}

get_backup_size() {
    local file="$1"
    du -h "${file}" | awk '{print $1}'
}

# =============================================================================
# BACKUP FUNCTIONS
# =============================================================================

create_backup_dir() {
    log "Creating backup directory: ${BACKUP_DIR}"
    mkdir -p "${BACKUP_DIR}"
    chmod 700 "${BACKUP_DIR}"
}

perform_full_backup() {
    local timestamp
    timestamp=$(date '+%Y%m%d_%H%M%S')
    local backup_file="${BACKUP_DIR}/${PGDATABASE}_full_${timestamp}.sql"
    local compressed_file="${backup_file}.gz"
    local final_file="${compressed_file}"

    log "Starting full backup of database: ${PGDATABASE}"
    log "Target file: ${backup_file}"

    # Create backup using pg_dump
    PGPASSWORD="${PGPASSWORD}" pg_dump \
        -h "${PGHOST}" \
        -p "${PGPORT}" \
        -U "${PGUSER}" \
        -d "${PGDATABASE}" \
        -F plain \
        --verbose \
        --no-owner \
        --no-privileges \
        --clean \
        --if-exists \
        -f "${backup_file}" 2>&1 | while read -r line; do log "pg_dump: ${line}"; done

    # Verify backup file exists and has content
    if [[ ! -s "${backup_file}" ]]; then
        log_error "Backup file is empty or does not exist"
        return 1
    fi

    log "Backup file created: $(get_backup_size "${backup_file}")"

    # Compress backup
    log "Compressing backup with gzip (level ${COMPRESSION_LEVEL})..."
    gzip -${COMPRESSION_LEVEL} "${backup_file}"
    log "Compressed file size: $(get_backup_size "${compressed_file}")"

    # Encrypt backup if enabled
    if [[ "${ENCRYPTION_ENABLED}" == "true" && -n "${GPG_RECIPIENT}" ]]; then
        log "Encrypting backup..."
        final_file="${compressed_file}.gpg"
        gpg --encrypt --recipient "${GPG_RECIPIENT}" --output "${final_file}" "${compressed_file}"
        rm -f "${compressed_file}"
        log "Encrypted file size: $(get_backup_size "${final_file}")"
    fi

    # Calculate checksum
    local checksum
    checksum=$(calculate_checksum "${final_file}")
    echo "${checksum}" > "${final_file}.sha256"
    log "Checksum: ${checksum}"

    # Create latest symlink
    ln -sf "${final_file}" "${BACKUP_DIR}/${PGDATABASE}_latest.backup"

    echo "${final_file}"
}

perform_incremental_backup() {
    local timestamp
    timestamp=$(date '+%Y%m%d_%H%M%S')
    local wal_archive_dir="${BACKUP_DIR}/wal_archive"

    log "Starting incremental backup (WAL archive)..."

    # This assumes PostgreSQL is configured with WAL archiving
    # archive_mode = on
    # archive_command = 'cp %p /backups/postgres/wal_archive/%f'

    if [[ ! -d "${wal_archive_dir}" ]]; then
        log "Creating WAL archive directory: ${wal_archive_dir}"
        mkdir -p "${wal_archive_dir}"
    fi

    # Force a WAL switch to archive current segment
    PGPASSWORD="${PGPASSWORD}" psql \
        -h "${PGHOST}" \
        -p "${PGPORT}" \
        -U "${PGUSER}" \
        -d "${PGDATABASE}" \
        -c "SELECT pg_switch_wal();" || true

    # Create incremental backup marker
    local marker_file="${BACKUP_DIR}/incremental_${timestamp}.marker"
    cat > "${marker_file}" << EOF
{
    "type": "incremental",
    "timestamp": "${timestamp}",
    "database": "${PGDATABASE}",
    "wal_archive_dir": "${wal_archive_dir}"
}
EOF

    log "Incremental backup marker created: ${marker_file}"
    echo "${marker_file}"
}

upload_to_remote() {
    local file="$1"

    if [[ "${REMOTE_BACKUP_ENABLED}" != "true" ]]; then
        log "Remote backup disabled, skipping upload"
        return 0
    fi

    log "Uploading backup to S3: s3://${S3_BUCKET}/${S3_PREFIX}/$(basename "${file}")"

    # Upload using AWS CLI
    aws s3 cp "${file}" "s3://${S3_BUCKET}/${S3_PREFIX}/" \
        --region "${AWS_REGION}" \
        --storage-class STANDARD_IA

    # Upload checksum file if exists
    if [[ -f "${file}.sha256" ]]; then
        aws s3 cp "${file}.sha256" "s3://${S3_BUCKET}/${S3_PREFIX}/" \
            --region "${AWS_REGION}"
    fi

    log "Upload completed"
}

cleanup_old_backups() {
    log "Cleaning up backups older than ${RETENTION_DAYS} days..."

    # Clean local backups
    find "${BACKUP_DIR}" -type f -name "*.sql.gz*" -mtime +${RETENTION_DAYS} -delete
    find "${BACKUP_DIR}" -type f -name "*.sha256" -mtime +${RETENTION_DAYS} -delete
    find "${BACKUP_DIR}" -type f -name "*.marker" -mtime +${RETENTION_DAYS} -delete

    local deleted_count
    deleted_count=$(find "${BACKUP_DIR}" -type f -mtime +${RETENTION_DAYS} 2>/dev/null | wc -l || echo "0")
    log "Deleted ${deleted_count} old backup files"

    # Clean remote backups if enabled
    if [[ "${REMOTE_BACKUP_ENABLED}" == "true" ]]; then
        log "Cleaning old remote backups..."
        # S3 lifecycle policies should handle this, but we can force cleanup
        local cutoff_date
        cutoff_date=$(date -d "-${RETENTION_DAYS} days" '+%Y-%m-%d')
        aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/" | while read -r line; do
            local file_date
            file_date=$(echo "${line}" | awk '{print $1}')
            local file_name
            file_name=$(echo "${line}" | awk '{print $4}')

            if [[ "${file_date}" < "${cutoff_date}" ]]; then
                aws s3 rm "s3://${S3_BUCKET}/${S3_PREFIX}/${file_name}" || true
            fi
        done
    fi
}

verify_backup() {
    local backup_file="$1"

    log "Verifying backup integrity..."

    # Check if file exists and has size
    if [[ ! -s "${backup_file}" ]]; then
        log_error "Backup file does not exist or is empty"
        return 1
    fi

    # Verify checksum if available
    if [[ -f "${backup_file}.sha256" ]]; then
        local stored_checksum
        stored_checksum=$(cat "${backup_file}.sha256")
        local current_checksum
        current_checksum=$(calculate_checksum "${backup_file}")

        if [[ "${stored_checksum}" != "${current_checksum}" ]]; then
            log_error "Checksum verification failed!"
            return 1
        fi
        log "Checksum verified successfully"
    fi

    # Test decompression if gzip file
    if [[ "${backup_file}" == *.gz ]]; then
        gzip -t "${backup_file}" || {
            log_error "Gzip integrity check failed"
            return 1
        }
        log "Gzip integrity verified"
    fi

    log "Backup verification completed successfully"
    return 0
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

main() {
    local start_time
    start_time=$(date +%s)
    local backup_file=""
    local status="success"
    local error_message=""

    log "==================================================================="
    log "Starting database backup"
    log "Type: ${BACKUP_TYPE}"
    log "Database: ${PGDATABASE}"
    log "Host: ${PGHOST}:${PGPORT}"
    log "==================================================================="

    # Create backup directory
    create_backup_dir

    # Perform backup based on type
    case "${BACKUP_TYPE}" in
        full)
            backup_file=$(perform_full_backup) || {
                status="error"
                error_message="Full backup failed"
            }
            ;;
        incremental)
            backup_file=$(perform_incremental_backup) || {
                status="error"
                error_message="Incremental backup failed"
            }
            ;;
        *)
            log_error "Invalid backup type: ${BACKUP_TYPE}"
            log "Usage: $0 [full|incremental]"
            exit 1
            ;;
    esac

    # Verify backup
    if [[ "${status}" == "success" && -n "${backup_file}" ]]; then
        verify_backup "${backup_file}" || {
            status="error"
            error_message="Backup verification failed"
        }
    fi

    # Upload to remote storage
    if [[ "${status}" == "success" && -n "${backup_file}" ]]; then
        upload_to_remote "${backup_file}" || {
            status="warning"
            error_message="Remote upload failed (local backup exists)"
        }
    fi

    # Cleanup old backups
    cleanup_old_backups

    # Calculate duration
    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))

    # Final status
    local backup_size="N/A"
    [[ -n "${backup_file}" && -f "${backup_file}" ]] && backup_size=$(get_backup_size "${backup_file}")

    log "==================================================================="
    log "Backup completed"
    log "Status: ${status}"
    log "Duration: ${duration} seconds"
    log "File: ${backup_file}"
    log "Size: ${backup_size}"
    log "==================================================================="

    # Send notification
    send_notification "${status}" \
        "Database backup ${BACKUP_TYPE} completed" \
        "Database: ${PGDATABASE}\\nSize: ${backup_size}\\nDuration: ${duration}s\\n${error_message}"

    # Exit with appropriate code
    if [[ "${status}" == "error" ]]; then
        exit 1
    fi

    exit 0
}

# Run main function
main "$@"
