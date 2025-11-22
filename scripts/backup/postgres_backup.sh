#!/bin/bash
# PostgreSQL Backup Script
# Automated database backup with compression and cloud upload

set -e  # Exit on error

# Configuration
BACKUP_DIR="/backups/postgres"
RETENTION_DAYS=30
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-cryptobot}"
DB_USER="${DB_USER:-cryptobot}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="cryptobot_${TIMESTAMP}.dump"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== PostgreSQL Backup Script ===${NC}"
echo "Timestamp: $(date)"
echo "Database: ${DB_NAME}@${DB_HOST}:${DB_PORT}"

# Create backup directory
mkdir -p ${BACKUP_DIR}

# Perform backup
echo -e "${YELLOW}Creating backup...${NC}"
PGPASSWORD=${DB_PASSWORD} pg_dump \
    -h ${DB_HOST} \
    -p ${DB_PORT} \
    -U ${DB_USER} \
    -d ${DB_NAME} \
    -F c \
    -b \
    -v \
    -f "${BACKUP_DIR}/${BACKUP_FILE}"

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Backup failed!${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Backup created: ${BACKUP_FILE}${NC}"

# Compress backup
echo -e "${YELLOW}Compressing backup...${NC}"
gzip "${BACKUP_DIR}/${BACKUP_FILE}"

# Verify backup integrity
echo -e "${YELLOW}Verifying backup integrity...${NC}"
pg_restore --list "${BACKUP_DIR}/${BACKUP_FILE}.gz" > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Backup verified: ${BACKUP_FILE}.gz${NC}"

    # Get backup size
    BACKUP_SIZE=$(du -h "${BACKUP_DIR}/${BACKUP_FILE}.gz" | cut -f1)
    echo "Backup size: ${BACKUP_SIZE}"
else
    echo -e "${RED}❌ Backup verification failed!${NC}"
    exit 1
fi

# Upload to S3/Cloud Storage (if configured)
if [ -n "${AWS_S3_BUCKET}" ]; then
    echo -e "${YELLOW}Uploading to S3...${NC}"
    aws s3 cp "${BACKUP_DIR}/${BACKUP_FILE}.gz" \
        "s3://${AWS_S3_BUCKET}/postgres/" \
        --storage-class STANDARD_IA

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Uploaded to S3${NC}"
    else
        echo -e "${YELLOW}⚠️ S3 upload failed (local backup retained)${NC}"
    fi
fi

# Cleanup old backups
echo -e "${YELLOW}Cleaning up old backups (keeping last ${RETENTION_DAYS} days)...${NC}"
find ${BACKUP_DIR} -name "cryptobot_*.dump.gz" -mtime +${RETENTION_DAYS} -delete

# Log backup
echo "$(date): Backup completed - ${BACKUP_FILE}.gz (${BACKUP_SIZE})" >> /var/log/backups.log

echo -e "${GREEN}=== Backup Complete ===${NC}"
