#!/bin/bash
# PostgreSQL Restore Script
# Restore database from backup with verification

set -e

# Configuration
BACKUP_DIR="/backups/postgres"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-cryptobot}"
DB_USER="${DB_USER:-cryptobot}"
TEST_MODE="${1:-}"  # Pass --test for test environment

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== PostgreSQL Restore Script ===${NC}"

# Get latest backup
if [ -n "${2}" ]; then
    BACKUP_FILE="${2}"
    echo "Using specified backup: ${BACKUP_FILE}"
else
    BACKUP_FILE=$(ls -t ${BACKUP_DIR}/cryptobot_*.dump.gz 2>/dev/null | head -1)
    if [ -z "${BACKUP_FILE}" ]; then
        # Try S3 if local not found
        if [ -n "${AWS_S3_BUCKET}" ]; then
            echo -e "${YELLOW}No local backup found. Downloading from S3...${NC}"
            LATEST_S3=$(aws s3 ls "s3://${AWS_S3_BUCKET}/postgres/" | sort | tail -n 1 | awk '{print $4}')
            aws s3 cp "s3://${AWS_S3_BUCKET}/postgres/${LATEST_S3}" /tmp/
            BACKUP_FILE="/tmp/${LATEST_S3}"
        else
            echo -e "${RED}❌ No backup found!${NC}"
            exit 1
        fi
    fi
    echo "Using latest backup: ${BACKUP_FILE}"
fi

# Decompress if needed
if [[ ${BACKUP_FILE} == *.gz ]]; then
    echo -e "${YELLOW}Decompressing backup...${NC}"
    gunzip -k "${BACKUP_FILE}"
    BACKUP_FILE="${BACKUP_FILE%.gz}"
fi

# Safety check - require confirmation unless in test mode
if [ "${TEST_MODE}" != "--test" ]; then
    echo -e "${RED}⚠️  WARNING: This will drop the existing database!${NC}"
    read -p "Type 'yes' to continue: " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Restore cancelled"
        exit 0
    fi

    # Stop trading engine to prevent data corruption
    echo -e "${YELLOW}Stopping trading engine...${NC}"
    docker-compose stop trading-engine 2>/dev/null || true
fi

# Get pre-restore counts for verification
PRE_TRADE_COUNT=$(PGPASSWORD=${DB_PASSWORD} psql -h ${DB_HOST} -U ${DB_USER} -d ${DB_NAME} -t -c "SELECT COUNT(*) FROM trades;" 2>/dev/null || echo "0")

echo -e "${YELLOW}Current database has ${PRE_TRADE_COUNT} trades${NC}"

# Drop and recreate database
echo -e "${YELLOW}Dropping and recreating database...${NC}"
PGPASSWORD=${DB_PASSWORD} psql -h ${DB_HOST} -U postgres -c "DROP DATABASE IF EXISTS ${DB_NAME};"
PGPASSWORD=${DB_PASSWORD} psql -h ${DB_HOST} -U postgres -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"

# Restore from backup
echo -e "${YELLOW}Restoring from backup...${NC}"
PGPASSWORD=${DB_PASSWORD} pg_restore \
    -h ${DB_HOST} \
    -p ${DB_PORT} \
    -U ${DB_USER} \
    -d ${DB_NAME} \
    -v \
    --no-owner \
    --no-acl \
    "${BACKUP_FILE}"

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Restore failed!${NC}"
    exit 1
fi

# Verify restoration
echo -e "${YELLOW}Verifying restoration...${NC}"
POST_TRADE_COUNT=$(PGPASSWORD=${DB_PASSWORD} psql -h ${DB_HOST} -U ${DB_USER} -d ${DB_NAME} -t -c "SELECT COUNT(*) FROM trades;")
POST_POSITION_COUNT=$(PGPASSWORD=${DB_PASSWORD} psql -h ${DB_HOST} -U ${DB_USER} -d ${DB_NAME} -t -c "SELECT COUNT(*) FROM positions;" 2>/dev/null || echo "0")

echo -e "${GREEN}✅ Restored database:${NC}"
echo "  - Trades: ${POST_TRADE_COUNT}"
echo "  - Positions: ${POST_POSITION_COUNT}"

# Run integrity checks
echo -e "${YELLOW}Running integrity checks...${NC}"

# Check for orphaned records
ORPHANED=$(PGPASSWORD=${DB_PASSWORD} psql -h ${DB_HOST} -U ${DB_USER} -d ${DB_NAME} -t -c \
    "SELECT COUNT(*) FROM positions WHERE portfolio_id NOT IN (SELECT id FROM portfolios);" 2>/dev/null || echo "0")

if [ "${ORPHANED}" -gt 0 ]; then
    echo -e "${YELLOW}⚠️ Found ${ORPHANED} orphaned position records${NC}"
else
    echo -e "${GREEN}✅ No orphaned records${NC}"
fi

# Restart services if not in test mode
if [ "${TEST_MODE}" != "--test" ]; then
    echo -e "${YELLOW}Restarting services...${NC}"
    docker-compose start trading-engine

    # Wait for service to be healthy
    echo "Waiting for trading engine to be healthy..."
    for i in {1..30}; do
        HEALTH=$(curl -s http://localhost:8001/health | jq -r '.status' 2>/dev/null || echo "unknown")
        if [ "${HEALTH}" = "healthy" ]; then
            echo -e "${GREEN}✅ Trading engine is healthy${NC}"
            break
        fi
        sleep 2
    done
fi

echo -e "${GREEN}=== Database Restoration Complete ===${NC}"

# Cleanup decompressed file
rm -f "${BACKUP_FILE%.gz}"

echo -e "${YELLOW}⚠️  POST-RESTORE CHECKLIST:${NC}"
echo "  [ ] Verify critical data is present"
echo "  [ ] Check recent trades are correct"
echo "  [ ] Verify portfolio balances"
echo "  [ ] Test one manual trade"
echo "  [ ] Monitor logs for errors"
echo "  [ ] Re-enable automated trading (if disabled)"
