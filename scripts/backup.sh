#!/bin/bash
# Crypto Trading Bot - Automated Backup Script
# Version: 1.0.0
# Last Updated: 2025-11-14
#
# Purpose: Automated backup of database, logs, and configuration
# Usage: ./scripts/backup.sh [--full] [--compress]

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
BACKUP_DIR="/mnt/d/Bimo_max/crypto-trading-bot/backups"
TODAY=$(date +%Y%m%d_%H%M%S)
FULL_BACKUP=false
COMPRESS=true
KEEP_DAYS=30  # Keep backups for 30 days

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --full)
            FULL_BACKUP=true
            shift
            ;;
        --compress)
            COMPRESS=true
            shift
            ;;
        --no-compress)
            COMPRESS=false
            shift
            ;;
        --keep-days)
            KEEP_DAYS=$2
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--full] [--compress] [--no-compress] [--keep-days N]"
            exit 1
            ;;
    esac
done

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Log function
log() {
    local level=$1
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    case $level in
        INFO)
            echo -e "${BLUE}[$timestamp] INFO:${NC} $message"
            ;;
        SUCCESS)
            echo -e "${GREEN}[$timestamp] SUCCESS:${NC} $message"
            ;;
        WARNING)
            echo -e "${YELLOW}[$timestamp] WARNING:${NC} $message"
            ;;
        ERROR)
            echo -e "${RED}[$timestamp] ERROR:${NC} $message"
            ;;
    esac
}

# Print header
print_header() {
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║  Crypto Trading Bot - Automated Backup                    ║${NC}"
    echo -e "${CYAN}║  $(date '+%Y-%m-%d %H:%M:%S')                                       ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    log INFO "Starting backup process..."
}

# Backup TimescaleDB
backup_database() {
    log INFO "Backing up TimescaleDB..."

    local db_backup="${BACKUP_DIR}/db_${TODAY}.sql"

    # Dump database
    docker exec crypto-trading-bot-timescaledb-1 pg_dump \
        -U crypto_user \
        -d crypto_trading \
        > "$db_backup"

    if [ $? -eq 0 ]; then
        local size=$(du -h "$db_backup" | cut -f1)
        log SUCCESS "Database backed up (${size})"

        # Compress if requested
        if $COMPRESS; then
            gzip "$db_backup"
            local compressed_size=$(du -h "${db_backup}.gz" | cut -f1)
            log SUCCESS "Database compressed (${compressed_size})"
            echo "${db_backup}.gz"
        else
            echo "$db_backup"
        fi
    else
        log ERROR "Database backup failed"
        return 1
    fi
}

# Backup Redis data
backup_redis() {
    log INFO "Backing up Redis..."

    local redis_backup="${BACKUP_DIR}/redis_${TODAY}.rdb"

    # Trigger Redis save
    docker exec crypto-trading-bot-redis-1 redis-cli BGSAVE >/dev/null

    # Wait for save to complete
    sleep 2

    # Copy RDB file
    docker cp crypto-trading-bot-redis-1:/data/dump.rdb "$redis_backup"

    if [ $? -eq 0 ]; then
        local size=$(du -h "$redis_backup" | cut -f1)
        log SUCCESS "Redis backed up (${size})"
        echo "$redis_backup"
    else
        log WARNING "Redis backup failed (not critical)"
        return 0
    fi
}

# Backup configuration files
backup_configs() {
    log INFO "Backing up configuration files..."

    local config_backup="${BACKUP_DIR}/configs_${TODAY}.tar"

    # Create tar archive of all .env files and configs
    tar -cf "$config_backup" \
        services/*/.env \
        docker-compose.yml \
        2>/dev/null || true

    if [ -f "$config_backup" ]; then
        local size=$(du -h "$config_backup" | cut -f1)
        log SUCCESS "Configurations backed up (${size})"

        # Compress if requested
        if $COMPRESS; then
            gzip "$config_backup"
            local compressed_size=$(du -h "${config_backup}.gz" | cut -f1)
            log SUCCESS "Configurations compressed (${compressed_size})"
            echo "${config_backup}.gz"
        else
            echo "$config_backup"
        fi
    else
        log WARNING "No configuration files to backup"
        return 0
    fi
}

# Backup logs
backup_logs() {
    log INFO "Backing up logs..."

    local logs_backup="${BACKUP_DIR}/logs_${TODAY}.tar"

    # Find and archive recent logs
    find /tmp -name "*.log" -mtime -7 -type f -exec tar -rf "$logs_backup" {} + 2>/dev/null || true

    # Also backup Docker logs
    docker-compose logs --tail 1000 > "${BACKUP_DIR}/docker_logs_${TODAY}.txt" 2>/dev/null || true

    if [ -f "$logs_backup" ]; then
        local size=$(du -h "$logs_backup" | cut -f1)
        log SUCCESS "Logs backed up (${size})"

        if $COMPRESS; then
            gzip "$logs_backup"
            gzip "${BACKUP_DIR}/docker_logs_${TODAY}.txt"
            log SUCCESS "Logs compressed"
        fi
    else
        log WARNING "No logs to backup"
    fi
}

# Backup ML models
backup_ml_models() {
    log INFO "Backing up ML models..."

    local models_backup="${BACKUP_DIR}/ml_models_${TODAY}.tar"

    # Find and archive all trained models
    find services/ml-prediction-service/models -name "*.h5" -type f -exec tar -rf "$models_backup" {} + 2>/dev/null || true

    if [ -f "$models_backup" ]; then
        local size=$(du -h "$models_backup" | cut -f1)
        log SUCCESS "ML models backed up (${size})"

        if $COMPRESS; then
            gzip "$models_backup"
            local compressed_size=$(du -h "${models_backup}.gz" | cut -f1)
            log SUCCESS "ML models compressed (${compressed_size})"
        fi
    else
        log WARNING "No ML models to backup"
    fi
}

# Clean old backups
cleanup_old_backups() {
    log INFO "Cleaning up old backups (older than ${KEEP_DAYS} days)..."

    local deleted_count=0

    # Find and delete old backups
    while IFS= read -r old_file; do
        rm -f "$old_file"
        ((deleted_count++))
    done < <(find "$BACKUP_DIR" -name "*.sql" -o -name "*.gz" -o -name "*.tar" -mtime +${KEEP_DAYS} 2>/dev/null)

    if [ $deleted_count -gt 0 ]; then
        log SUCCESS "Deleted $deleted_count old backup(s)"
    else
        log INFO "No old backups to delete"
    fi
}

# Verify backup integrity
verify_backup() {
    local backup_file=$1

    if [ -f "$backup_file" ]; then
        if [[ "$backup_file" == *.gz ]]; then
            # Test gzip integrity
            gzip -t "$backup_file" 2>/dev/null
            if [ $? -eq 0 ]; then
                log SUCCESS "Backup verified: $(basename $backup_file)"
                return 0
            else
                log ERROR "Backup corrupted: $(basename $backup_file)"
                return 1
            fi
        else
            # Just check if file exists and has size
            local size=$(stat -f%z "$backup_file" 2>/dev/null || stat -c%s "$backup_file" 2>/dev/null)
            if [ "$size" -gt 0 ]; then
                log SUCCESS "Backup verified: $(basename $backup_file)"
                return 0
            else
                log ERROR "Backup empty: $(basename $backup_file)"
                return 1
            fi
        fi
    else
        log ERROR "Backup not found: $backup_file"
        return 1
    fi
}

# Create backup manifest
create_manifest() {
    local manifest_file="${BACKUP_DIR}/backup_manifest_${TODAY}.txt"

    {
        echo "Crypto Trading Bot - Backup Manifest"
        echo "Date: $(date '+%Y-%m-%d %H:%M:%S')"
        echo "Type: $([ $FULL_BACKUP == true ] && echo 'Full Backup' || echo 'Incremental Backup')"
        echo ""
        echo "Files:"
        ls -lh "${BACKUP_DIR}" | grep "${TODAY}"
        echo ""
        echo "Total Size:"
        du -sh "${BACKUP_DIR}" | awk '{print $1}'
    } > "$manifest_file"

    log SUCCESS "Backup manifest created"
}

# Print summary
print_summary() {
    local exit_code=$1

    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}Backup Summary${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo ""

    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}✓ Backup completed successfully${NC}"
        echo ""
        echo "Backup location: $BACKUP_DIR"
        echo "Backup timestamp: $TODAY"
        echo ""

        # Show backup sizes
        echo "Backup contents:"
        ls -lh "${BACKUP_DIR}" | grep "${TODAY}" | awk '{print "  " $9 " - " $5}'

        echo ""
        echo "Total backup size:"
        du -sh "${BACKUP_DIR}" | awk '{print "  " $1}'

        echo ""
        echo -e "${CYAN}Retention Policy:${NC}"
        echo "  Keeping backups for ${KEEP_DAYS} days"

        echo ""
        echo -e "${CYAN}Restore Commands:${NC}"
        echo "  Database: gunzip -c db_${TODAY}.sql.gz | docker exec -i crypto-trading-bot-timescaledb-1 psql -U crypto_user -d crypto_trading"
        echo "  Configs:  tar -xzf configs_${TODAY}.tar.gz"
        echo "  Models:   tar -xzf ml_models_${TODAY}.tar.gz"
    else
        echo -e "${RED}✗ Backup completed with errors${NC}"
        echo ""
        echo "Some components failed to backup."
        echo "Review errors above and retry if needed."
    fi

    echo ""
    echo -e "${BLUE}Backup completed at $(date '+%Y-%m-%d %H:%M:%S')${NC}"
    echo ""
}

# Main execution
main() {
    local start_time=$(date +%s)
    local errors=0

    print_header

    # Backup database
    echo ""
    db_file=$(backup_database)
    [ $? -ne 0 ] && ((errors++))
    verify_backup "$db_file" || ((errors++))

    # Backup Redis
    echo ""
    redis_file=$(backup_redis)
    # Redis backup failure is not critical, don't increment errors

    # Backup configurations
    echo ""
    config_file=$(backup_configs)
    verify_backup "$config_file" || true

    # Backup logs (if full backup)
    if $FULL_BACKUP; then
        echo ""
        backup_logs
    fi

    # Backup ML models
    echo ""
    backup_ml_models

    # Clean old backups
    echo ""
    cleanup_old_backups

    # Create manifest
    echo ""
    create_manifest

    # Calculate duration
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    log INFO "Backup duration: ${duration} seconds"

    # Print summary
    if [ $errors -eq 0 ]; then
        print_summary 0
        exit 0
    else
        print_summary 1
        exit 1
    fi
}

# Run main function
main
