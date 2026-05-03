#!/bin/bash
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# TimescaleDB Automated Backup Script
# Backs up market data database with compression and timestamp

set -e

# Configuration
BACKUP_DIR="${PROJECT_ROOT}/backups/timescaledb"
CONTAINER_NAME="crypto-bot-timescaledb"
DB_NAME="market_data"
DB_USER="cryptobot"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="timescaledb_${DB_NAME}_${TIMESTAMP}.sql.gz"
RETENTION_DAYS=7

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}[$(date +%Y-%m-%d\ %H:%M:%S)]${NC} Starting TimescaleDB backup..."

# Check if container is running
if ! docker ps | grep -q $CONTAINER_NAME; then
    echo -e "${RED}[ERROR]${NC} Container $CONTAINER_NAME is not running!"
    exit 1
fi

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Perform backup
echo -e "${YELLOW}[INFO]${NC} Backing up database: $DB_NAME"
docker exec $CONTAINER_NAME pg_dump -U $DB_USER -d $DB_NAME | gzip > "$BACKUP_DIR/$BACKUP_FILE"

# Check if backup was successful
if [ $? -eq 0 ]; then
    BACKUP_SIZE=$(du -h "$BACKUP_DIR/$BACKUP_FILE" | cut -f1)
    echo -e "${GREEN}[SUCCESS]${NC} Backup created: $BACKUP_FILE (Size: $BACKUP_SIZE)"
else
    echo -e "${RED}[ERROR]${NC} Backup failed!"
    exit 1
fi

# Cleanup old backups (keep last RETENTION_DAYS)
echo -e "${YELLOW}[INFO]${NC} Cleaning up backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "timescaledb_*.sql.gz" -type f -mtime +$RETENTION_DAYS -delete

# Count remaining backups
BACKUP_COUNT=$(ls -1 "$BACKUP_DIR"/timescaledb_*.sql.gz 2>/dev/null | wc -l)
echo -e "${GREEN}[INFO]${NC} Total backups: $BACKUP_COUNT"

# Calculate total backup size
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
echo -e "${GREEN}[INFO]${NC} Total backup directory size: $TOTAL_SIZE"

echo -e "${GREEN}[COMPLETE]${NC} TimescaleDB backup completed successfully!"
