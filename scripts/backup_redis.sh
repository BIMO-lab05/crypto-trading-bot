#!/bin/bash
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Redis Automated Backup Script
# Backs up Redis cache and session data

set -e

BACKUP_DIR="${PROJECT_ROOT}/backups/redis"
CONTAINER_NAME="crypto-bot-redis"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="redis_dump_${TIMESTAMP}.rdb"
RETENTION_DAYS=7

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}[$(date +%Y-%m-%d\ %H:%M:%S)]${NC} Starting Redis backup..."

if ! docker ps | grep -q $CONTAINER_NAME; then
    echo -e "${RED}[ERROR]${NC} Container $CONTAINER_NAME is not running!"
    exit 1
fi

mkdir -p "$BACKUP_DIR"

# Trigger Redis SAVE command
echo -e "${YELLOW}[INFO]${NC} Triggering Redis SAVE..."
docker exec $CONTAINER_NAME redis-cli SAVE > /dev/null

# Copy dump.rdb from container
echo -e "${YELLOW}[INFO]${NC} Copying Redis dump file..."
docker cp $CONTAINER_NAME:/data/dump.rdb "$BACKUP_DIR/$BACKUP_FILE"

if [ $? -eq 0 ]; then
    BACKUP_SIZE=$(du -h "$BACKUP_DIR/$BACKUP_FILE" | cut -f1)
    echo -e "${GREEN}[SUCCESS]${NC} Backup created: $BACKUP_FILE (Size: $BACKUP_SIZE)"
else
    echo -e "${RED}[ERROR]${NC} Backup failed!"
    exit 1
fi

echo -e "${YELLOW}[INFO]${NC} Cleaning up backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "redis_dump_*.rdb" -type f -mtime +$RETENTION_DAYS -delete

BACKUP_COUNT=$(ls -1 "$BACKUP_DIR"/redis_dump_*.rdb 2>/dev/null | wc -l)
echo -e "${GREEN}[INFO]${NC} Total backups: $BACKUP_COUNT"

echo -e "${GREEN}[COMPLETE]${NC} Redis backup completed successfully!"
