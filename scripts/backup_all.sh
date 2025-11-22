#!/bin/bash
# Master Backup Script with Retention Policy
# Runs daily and weekly backups with automatic cleanup

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_BASE="/mnt/d/Bimo_max/crypto-trading-bot/backups"
LOG_FILE="$BACKUP_BASE/backup.log"

# Retention settings
DAILY_RETENTION_DAYS=7
WEEKLY_RETENTION_WEEKS=4

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date +%Y-%m-%d\ %H:%M:%S)]${NC} $1" | tee -a "$LOG_FILE"
}

# Determine if this is a weekly backup (run on Sundays)
DAY_OF_WEEK=$(date +%u)
if [ "$DAY_OF_WEEK" -eq 7 ]; then
    BACKUP_TYPE="weekly"
    RETENTION_DAYS=$((WEEKLY_RETENTION_WEEKS * 7))
else
    BACKUP_TYPE="daily"
    RETENTION_DAYS=$DAILY_RETENTION_DAYS
fi

log "=========================================="
log "Starting $BACKUP_TYPE backup run"
log "Retention: $RETENTION_DAYS days"
log "=========================================="

# TimescaleDB Backup
log "Backing up TimescaleDB..."
bash "$SCRIPT_DIR/backup_timescaledb.sh" 2>&1 | tee -a "$LOG_FILE"

# PostgreSQL Backup
log "Backing up PostgreSQL..."
bash "$SCRIPT_DIR/backup_postgresql.sh" 2>&1 | tee -a "$LOG_FILE"

# Redis Backup
log "Backing up Redis..."
bash "$SCRIPT_DIR/backup_redis.sh" 2>&1 | tee -a "$LOG_FILE"

# Summary
log "=========================================="
log "Backup Summary:"
TIMESCALE_COUNT=$(ls -1 "$BACKUP_BASE/timescaledb"/*.sql.gz 2>/dev/null | wc -l)
POSTGRES_COUNT=$(ls -1 "$BACKUP_BASE/postgresql"/*.sql.gz 2>/dev/null | wc -l)
REDIS_COUNT=$(ls -1 "$BACKUP_BASE/redis"/*.rdb 2>/dev/null | wc -l)

log "TimescaleDB backups: $TIMESCALE_COUNT"
log "PostgreSQL backups: $POSTGRES_COUNT"
log "Redis backups: $REDIS_COUNT"

TOTAL_SIZE=$(du -sh "$BACKUP_BASE" | cut -f1)
log "Total backup size: $TOTAL_SIZE"
log "=========================================="
log "$BACKUP_TYPE backup completed successfully!"
