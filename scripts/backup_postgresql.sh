#!/bin/bash
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# PostgreSQL Automated Backup Script
# Backs up portfolio and trading data

set -e

BACKUP_DIR="${PROJECT_ROOT}/backups/postgresql"
CONTAINER_NAME="crypto-bot-postgres"
DB_NAME="crypto_trading"
DB_USER="cryptobot"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="postgresql_${DB_NAME}_${TIMESTAMP}.sql.gz"
RETENTION_DAYS=7

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}[$(date +%Y-%m-%d\ %H:%M:%S)]${NC} Starting PostgreSQL backup..."

if ! docker ps | grep -q $CONTAINER_NAME; then
    echo -e "${RED}[ERROR]${NC} Container $CONTAINER_NAME is not running!"
    exit 1
fi

mkdir -p "$BACKUP_DIR"

echo -e "${YELLOW}[INFO]${NC} Backing up database: $DB_NAME"
docker exec $CONTAINER_NAME pg_dump -U $DB_USER -d $DB_NAME | gzip > "$BACKUP_DIR/$BACKUP_FILE"

if [ $? -eq 0 ]; then
    BACKUP_SIZE=$(du -h "$BACKUP_DIR/$BACKUP_FILE" | cut -f1)
    echo -e "${GREEN}[SUCCESS]${NC} Backup created: $BACKUP_FILE (Size: $BACKUP_SIZE)"
else
    echo -e "${RED}[ERROR]${NC} Backup failed!"
    exit 1
fi

echo -e "${YELLOW}[INFO]${NC} Cleaning up backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "postgresql_*.sql.gz" -type f -mtime +$RETENTION_DAYS -delete

BACKUP_COUNT=$(ls -1 "$BACKUP_DIR"/postgresql_*.sql.gz 2>/dev/null | wc -l)
echo -e "${GREEN}[INFO]${NC} Total backups: $BACKUP_COUNT"

echo -e "${GREEN}[COMPLETE]${NC} PostgreSQL backup completed successfully!"
