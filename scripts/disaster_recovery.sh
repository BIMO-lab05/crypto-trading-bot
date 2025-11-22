#!/bin/bash
# Crypto Trading Bot - Disaster Recovery Script
# Version: 1.0.0
# Last Updated: 2025-11-14
#
# Purpose: Emergency system recovery and restoration
# Usage: ./scripts/disaster_recovery.sh [--restore-db FILE] [--restore-configs FILE] [--full-recovery]

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
RESTORE_DB=""
RESTORE_CONFIGS=""
FULL_RECOVERY=false
CONTAINER_NAME="crypto-trading-bot-timescaledb-1"
DB_NAME="crypto_trading"
DB_USER="crypto_user"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --restore-db)
            RESTORE_DB=$2
            shift 2
            ;;
        --restore-configs)
            RESTORE_CONFIGS=$2
            shift 2
            ;;
        --full-recovery)
            FULL_RECOVERY=true
            shift
            ;;
        --list-backups)
            ls -lh "$BACKUP_DIR" | grep -E "db_|configs_|ml_models_" | tail -20
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--restore-db FILE] [--restore-configs FILE] [--full-recovery] [--list-backups]"
            exit 1
            ;;
    esac
done

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
        CRITICAL)
            echo -e "${RED}[$timestamp] CRITICAL:${NC} $message"
            ;;
    esac
}

# Print header
print_header() {
    echo -e "${RED}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  DISASTER RECOVERY MODE                                    ║${NC}"
    echo -e "${RED}║  $(date '+%Y-%m-%d %H:%M:%S')                                       ║${NC}"
    echo -e "${RED}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    log WARNING "This script will perform system recovery operations"
    log WARNING "Ensure you have recent backups before proceeding"
}

# Emergency stop all services
emergency_stop() {
    log INFO "Emergency stop: Halting all services..."

    # Stop auto-trading immediately
    curl -s -X POST http://localhost:8005/api/v1/emergency/stop 2>/dev/null || true

    # Close all positions
    log INFO "Closing all open positions..."
    curl -s -X POST http://localhost:8005/api/v1/emergency/close-all 2>/dev/null || true

    # Wait for positions to close
    sleep 5

    # Stop monitoring
    pkill -f "scripts/monitor.py" 2>/dev/null || true
    pkill -f "http.server 8080" 2>/dev/null || true

    # Stop all Docker services
    log INFO "Stopping Docker services..."
    docker-compose stop 2>&1 | tee -a /tmp/emergency_stop.log

    log SUCCESS "All services stopped"
}

# Verify backup file
verify_backup_file() {
    local file=$1

    if [ ! -f "$file" ]; then
        log ERROR "Backup file not found: $file"
        return 1
    fi

    # Check file extension and verify integrity
    if [[ "$file" == *.gz ]]; then
        if ! gzip -t "$file" 2>/dev/null; then
            log ERROR "Backup file is corrupted (gzip test failed): $file"
            return 1
        fi
    fi

    local size=$(du -h "$file" | cut -f1)
    log INFO "Backup file verified: $file ($size)"
    return 0
}

# List available backups
list_available_backups() {
    log INFO "Available backups in $BACKUP_DIR:"
    echo ""

    if [ ! -d "$BACKUP_DIR" ]; then
        log WARNING "Backup directory not found: $BACKUP_DIR"
        return 1
    fi

    echo -e "${CYAN}Database Backups:${NC}"
    ls -lh "$BACKUP_DIR"/db_*.sql.gz 2>/dev/null | tail -10 | awk '{print "  " $9 " (" $5 ")"}' || echo "  None found"

    echo ""
    echo -e "${CYAN}Configuration Backups:${NC}"
    ls -lh "$BACKUP_DIR"/configs_*.tar.gz 2>/dev/null | tail -10 | awk '{print "  " $9 " (" $5 ")"}' || echo "  None found"

    echo ""
    echo -e "${CYAN}ML Model Backups:${NC}"
    ls -lh "$BACKUP_DIR"/ml_models_*.tar.gz 2>/dev/null | tail -10 | awk '{print "  " $9 " (" $5 ")"}' || echo "  None found"

    echo ""
}

# Restore database from backup
restore_database() {
    local backup_file=$1

    log INFO "Restoring database from: $backup_file"

    # Verify backup
    if ! verify_backup_file "$backup_file"; then
        return 1
    fi

    # Ensure database container is running
    if ! docker ps | grep -q "$CONTAINER_NAME"; then
        log INFO "Starting database container..."
        docker-compose up -d timescaledb
        sleep 5
    fi

    # Check database connectivity
    if ! docker exec "$CONTAINER_NAME" pg_isready -U "$DB_USER" >/dev/null 2>&1; then
        log ERROR "Database is not ready"
        return 1
    fi

    # Create backup of current database before restore
    local pre_restore_backup="/tmp/pre_restore_backup_$(date +%Y%m%d_%H%M%S).sql"
    log INFO "Creating pre-restore backup..."
    docker exec "$CONTAINER_NAME" pg_dump -U "$DB_USER" -d "$DB_NAME" > "$pre_restore_backup" 2>/dev/null || true

    # Drop existing connections
    log WARNING "Dropping existing database connections..."
    docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d postgres -c \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();" \
        2>/dev/null || true

    # Drop and recreate database
    log WARNING "Dropping and recreating database..."
    docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d postgres -c "DROP DATABASE IF EXISTS $DB_NAME;" 2>/dev/null
    docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d postgres -c "CREATE DATABASE $DB_NAME;" 2>/dev/null

    # Restore from backup
    log INFO "Restoring data..."
    if [[ "$backup_file" == *.gz ]]; then
        gunzip -c "$backup_file" | docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" 2>&1 | tee /tmp/restore_db.log
    else
        cat "$backup_file" | docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" 2>&1 | tee /tmp/restore_db.log
    fi

    if [ ${PIPESTATUS[0]} -eq 0 ]; then
        log SUCCESS "Database restored successfully"
        log INFO "Pre-restore backup saved: $pre_restore_backup"
        return 0
    else
        log ERROR "Database restore failed - check /tmp/restore_db.log"
        log INFO "Pre-restore backup available for rollback: $pre_restore_backup"
        return 1
    fi
}

# Restore configuration files
restore_configurations() {
    local backup_file=$1

    log INFO "Restoring configurations from: $backup_file"

    # Verify backup
    if ! verify_backup_file "$backup_file"; then
        return 1
    fi

    # Backup current configs
    local config_backup="/tmp/configs_before_restore_$(date +%Y%m%d_%H%M%S).tar.gz"
    log INFO "Backing up current configurations..."
    tar -czf "$config_backup" services/*/.env docker-compose.yml 2>/dev/null || true

    # Extract backup
    log INFO "Extracting configurations..."
    if tar -xzf "$backup_file" -C / 2>&1 | tee /tmp/restore_configs.log; then
        log SUCCESS "Configurations restored successfully"
        log INFO "Previous configs saved: $config_backup"
        return 0
    else
        log ERROR "Configuration restore failed"
        return 1
    fi
}

# Restore ML models
restore_ml_models() {
    local backup_file=$1

    log INFO "Restoring ML models from: $backup_file"

    # Verify backup
    if ! verify_backup_file "$backup_file"; then
        return 1
    fi

    # Extract models
    log INFO "Extracting ML models..."
    if tar -xzf "$backup_file" -C / 2>&1 | tee /tmp/restore_models.log; then
        log SUCCESS "ML models restored successfully"
        return 0
    else
        log ERROR "ML model restore failed"
        return 1
    fi
}

# Full system recovery
full_system_recovery() {
    log CRITICAL "Starting FULL SYSTEM RECOVERY"
    echo ""

    # Ask for confirmation
    echo -e "${RED}WARNING: This will stop all services and restore from backups${NC}"
    echo ""
    read -p "Are you sure you want to proceed? (type 'YES' to confirm): " confirm

    if [ "$confirm" != "YES" ]; then
        log INFO "Recovery cancelled by user"
        exit 0
    fi

    echo ""
    log INFO "=== STEP 1/7: Emergency Stop ==="
    emergency_stop

    echo ""
    log INFO "=== STEP 2/7: List Available Backups ==="
    list_available_backups

    echo ""
    log INFO "=== STEP 3/7: Select Backups ==="

    # Find latest backups if not specified
    if [ -z "$RESTORE_DB" ]; then
        RESTORE_DB=$(ls -t "$BACKUP_DIR"/db_*.sql.gz 2>/dev/null | head -1)
        if [ ! -z "$RESTORE_DB" ]; then
            log INFO "Auto-selected latest database backup: $(basename $RESTORE_DB)"
        fi
    fi

    if [ -z "$RESTORE_CONFIGS" ]; then
        RESTORE_CONFIGS=$(ls -t "$BACKUP_DIR"/configs_*.tar.gz 2>/dev/null | head -1)
        if [ ! -z "$RESTORE_CONFIGS" ]; then
            log INFO "Auto-selected latest config backup: $(basename $RESTORE_CONFIGS)"
        fi
    fi

    # Restore database
    if [ ! -z "$RESTORE_DB" ]; then
        echo ""
        log INFO "=== STEP 4/7: Restore Database ==="
        if ! restore_database "$RESTORE_DB"; then
            log ERROR "Database restore failed - aborting recovery"
            exit 1
        fi
    else
        log WARNING "No database backup specified - skipping"
    fi

    # Restore configurations
    if [ ! -z "$RESTORE_CONFIGS" ]; then
        echo ""
        log INFO "=== STEP 5/7: Restore Configurations ==="
        if ! restore_configurations "$RESTORE_CONFIGS"; then
            log WARNING "Configuration restore failed - continuing anyway"
        fi
    else
        log WARNING "No config backup specified - skipping"
    fi

    # Restart services
    echo ""
    log INFO "=== STEP 6/7: Restart Services ==="
    docker-compose up -d 2>&1 | tee /tmp/recovery_restart.log

    # Wait for services to start
    log INFO "Waiting for services to initialize (60 seconds)..."
    sleep 60

    # Validate recovery
    echo ""
    log INFO "=== STEP 7/7: Validate Recovery ==="

    local healthy=0
    local total=10

    for port in {8000..8009}; do
        if curl -s -f "http://localhost:$port/health" >/dev/null 2>&1; then
            ((healthy++))
            log SUCCESS "Service on port $port is healthy"
        else
            log WARNING "Service on port $port is not responding"
        fi
    done

    echo ""
    log INFO "Recovery validation: $healthy/$total services healthy"

    if [ $healthy -ge 7 ]; then
        log SUCCESS "System recovery completed successfully"
        return 0
    else
        log WARNING "System recovery completed with warnings"
        log WARNING "Only $healthy/$total services are healthy"
        return 1
    fi
}

# Health check after recovery
post_recovery_health_check() {
    log INFO "Running post-recovery health check..."
    echo ""

    # Run health check script if available
    if [ -f "./scripts/health_check.sh" ]; then
        ./scripts/health_check.sh --verbose
    else
        # Manual health check
        log INFO "Checking services..."
        for port in {8000..8009}; do
            if curl -s -f "http://localhost:$port/health" >/dev/null 2>&1; then
                echo "  ✓ Port $port: Healthy"
            else
                echo "  ✗ Port $port: Not responding"
            fi
        done
    fi
}

# Create disaster recovery report
create_recovery_report() {
    local report_file="/tmp/disaster_recovery_report_$(date +%Y%m%d_%H%M%S).txt"

    {
        echo "═══════════════════════════════════════════════════════════"
        echo "  DISASTER RECOVERY REPORT"
        echo "  $(date '+%Y-%m-%d %H:%M:%S')"
        echo "═══════════════════════════════════════════════════════════"
        echo ""

        echo "Recovery Type: $([ $FULL_RECOVERY == true ] && echo 'Full System Recovery' || echo 'Partial Recovery')"
        echo ""

        if [ ! -z "$RESTORE_DB" ]; then
            echo "Database Restored From:"
            echo "  File: $RESTORE_DB"
            echo "  Size: $(du -h "$RESTORE_DB" | cut -f1)"
        fi

        if [ ! -z "$RESTORE_CONFIGS" ]; then
            echo ""
            echo "Configurations Restored From:"
            echo "  File: $RESTORE_CONFIGS"
            echo "  Size: $(du -h "$RESTORE_CONFIGS" | cut -f1)"
        fi

        echo ""
        echo "Logs:"
        echo "  Emergency stop:    /tmp/emergency_stop.log"
        echo "  DB restore:        /tmp/restore_db.log"
        echo "  Config restore:    /tmp/restore_configs.log"
        echo "  Service restart:   /tmp/recovery_restart.log"

        echo ""
        echo "Next Steps:"
        echo "  1. Verify all services are healthy"
        echo "  2. Check trading positions"
        echo "  3. Validate risk limits"
        echo "  4. Review recent trades"
        echo "  5. Monitor system for 1 hour before resuming trading"

        echo ""
        echo "═══════════════════════════════════════════════════════════"

    } > "$report_file"

    log INFO "Recovery report created: $report_file"
    cat "$report_file"
}

# Print usage examples
print_usage() {
    echo ""
    echo "Usage Examples:"
    echo ""
    echo "List available backups:"
    echo "  $0 --list-backups"
    echo ""
    echo "Restore specific database:"
    echo "  $0 --restore-db $BACKUP_DIR/db_20251114_120000.sql.gz"
    echo ""
    echo "Restore specific configurations:"
    echo "  $0 --restore-configs $BACKUP_DIR/configs_20251114_120000.tar.gz"
    echo ""
    echo "Full system recovery (auto-selects latest backups):"
    echo "  $0 --full-recovery"
    echo ""
    echo "Full recovery with specific backups:"
    echo "  $0 --full-recovery --restore-db backup.sql.gz --restore-configs configs.tar.gz"
    echo ""
}

# Main execution
main() {
    print_header

    # Check if any action specified
    if [ -z "$RESTORE_DB" ] && [ -z "$RESTORE_CONFIGS" ] && [ "$FULL_RECOVERY" == false ]; then
        echo ""
        list_available_backups
        print_usage
        exit 0
    fi

    # Execute recovery
    if [ "$FULL_RECOVERY" == true ]; then
        full_system_recovery
        exit_code=$?
    else
        # Partial recovery
        if [ ! -z "$RESTORE_DB" ]; then
            echo ""
            restore_database "$RESTORE_DB"
        fi

        if [ ! -z "$RESTORE_CONFIGS" ]; then
            echo ""
            restore_configurations "$RESTORE_CONFIGS"
        fi

        exit_code=$?
    fi

    # Post-recovery steps
    echo ""
    post_recovery_health_check

    echo ""
    create_recovery_report

    exit $exit_code
}

# Run main function
main
