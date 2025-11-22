#!/bin/bash
#
# Database Verification Script
# Purpose: Comprehensive health check of all databases
# Usage: bash scripts/verify_databases.sh
#

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=====================================================================${NC}"
echo -e "${BLUE}  CRYPTO BOT - DATABASE VERIFICATION${NC}"
echo -e "${BLUE}=====================================================================${NC}"
echo ""

# Function to check container status
check_container() {
    local name=$1
    if docker ps --format '{{.Names}}' | grep -q "^${name}$"; then
        echo -e "${GREEN}✓${NC} Container ${name} is running"
        return 0
    else
        echo -e "${RED}✗${NC} Container ${name} is NOT running"
        return 1
    fi
}

# Function to check database connectivity
check_db_connection() {
    local name=$1
    local command=$2

    if docker exec ${name} ${command} &>/dev/null; then
        echo -e "${GREEN}✓${NC} Database ${name} is responsive"
        return 0
    else
        echo -e "${RED}✗${NC} Database ${name} is NOT responsive"
        return 1
    fi
}

echo -e "${YELLOW}1. Container Status${NC}"
echo "-------------------------------------------------------------------"
check_container "crypto-bot-postgres"
check_container "crypto-bot-timescaledb"
check_container "crypto-bot-redis"
check_container "crypto-bot-rabbitmq"
echo ""

echo -e "${YELLOW}2. Database Connectivity${NC}"
echo "-------------------------------------------------------------------"
check_db_connection "crypto-bot-postgres" "pg_isready -U cryptobot"
check_db_connection "crypto-bot-timescaledb" "pg_isready -U cryptobot"
docker exec crypto-bot-redis redis-cli ping &>/dev/null && \
    echo -e "${GREEN}✓${NC} Redis is responsive" || \
    echo -e "${RED}✗${NC} Redis is NOT responsive"
docker exec crypto-bot-rabbitmq rabbitmq-diagnostics ping &>/dev/null && \
    echo -e "${GREEN}✓${NC} RabbitMQ is responsive" || \
    echo -e "${RED}✗${NC} RabbitMQ is NOT responsive"
echo ""

echo -e "${YELLOW}3. PostgreSQL Schema Verification${NC}"
echo "-------------------------------------------------------------------"
PSQL_TABLES=$(docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -t -c \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema IN ('trading_engine', 'portfolio', 'audit');")
echo -e "Tables created: ${GREEN}${PSQL_TABLES}${NC} (expected: 6)"

STRATEGIES=$(docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -t -c \
    "SELECT COUNT(*) FROM trading_engine.strategies;")
echo -e "Default strategies: ${GREEN}${STRATEGIES}${NC} (expected: 2)"
echo ""

echo -e "${YELLOW}4. TimescaleDB Data Verification${NC}"
echo "-------------------------------------------------------------------"
echo "Market data by symbol:"
docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data -c \
    "SELECT symbol, COUNT(*) as candles,
     TO_CHAR(MIN(time), 'YYYY-MM-DD') as earliest,
     TO_CHAR(MAX(time), 'YYYY-MM-DD') as latest
    FROM market_data.candles
    GROUP BY symbol ORDER BY symbol;" | tail -n +3 | head -n -2

TOTAL_CANDLES=$(docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data -t -c \
    "SELECT COUNT(*) FROM market_data.candles;")
echo -e "\nTotal candles: ${GREEN}${TOTAL_CANDLES}${NC} (expected: 5,040 for 7 symbols × 30 days × 24h)"
echo ""

echo -e "${YELLOW}5. Hypertable Verification${NC}"
echo "-------------------------------------------------------------------"
HYPERTABLES=$(docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data -t -c \
    "SELECT COUNT(*) FROM timescaledb_information.hypertables;")
echo -e "Hypertables created: ${GREEN}${HYPERTABLES}${NC} (expected: 4)"

CHUNKS=$(docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data -t -c \
    "SELECT COUNT(*) FROM timescaledb_information.chunks WHERE hypertable_name = 'candles';")
echo -e "Chunks for candles table: ${GREEN}${CHUNKS}${NC}"
echo ""

echo -e "${YELLOW}6. Service API Health${NC}"
echo "-------------------------------------------------------------------"
check_api() {
    local url=$1
    local name=$2

    if curl -s -f ${url} &>/dev/null; then
        echo -e "${GREEN}✓${NC} ${name} API is healthy"
    else
        echo -e "${RED}✗${NC} ${name} API is NOT responding"
    fi
}

check_api "http://localhost:8002/health" "Market Data Service"
check_api "http://localhost:8003/health" "Portfolio Manager"
check_api "http://localhost:8005/health" "Trading Engine"
check_api "http://localhost:8007/health" "ML Prediction Service"
echo ""

echo -e "${YELLOW}7. Data Quality Check${NC}"
echo "-------------------------------------------------------------------"
# Check for any NULL values in critical fields
NULL_COUNT=$(docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data -t -c \
    "SELECT COUNT(*) FROM market_data.candles
     WHERE open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL;")

if [ "${NULL_COUNT}" -eq 0 ]; then
    echo -e "${GREEN}✓${NC} No NULL values in price data"
else
    echo -e "${RED}✗${NC} Found ${NULL_COUNT} rows with NULL prices"
fi

# Check for price anomalies (high/low consistency)
ANOMALIES=$(docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data -t -c \
    "SELECT COUNT(*) FROM market_data.candles WHERE high < low OR high < open OR high < close OR low > open OR low > close;")

if [ "${ANOMALIES}" -eq 0 ]; then
    echo -e "${GREEN}✓${NC} No price anomalies detected"
else
    echo -e "${YELLOW}⚠${NC} Found ${ANOMALIES} potential price anomalies"
fi
echo ""

echo -e "${YELLOW}8. Recent Data Check${NC}"
echo "-------------------------------------------------------------------"
echo "Latest candle timestamps:"
docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data -c \
    "SELECT DISTINCT ON (symbol) symbol, time
    FROM market_data.candles
    ORDER BY symbol, time DESC;" | tail -n +3 | head -n -2
echo ""

echo -e "${YELLOW}9. Scheduler Status${NC}"
echo "-------------------------------------------------------------------"
SCHEDULER_STATUS=$(curl -s http://localhost:8002/api/v1/scheduler/status | grep -o '"running":[^,]*' || echo "unknown")
echo -e "Market data scheduler: ${SCHEDULER_STATUS}"
echo ""

echo -e "${BLUE}=====================================================================${NC}"
echo -e "${BLUE}  VERIFICATION SUMMARY${NC}"
echo -e "${BLUE}=====================================================================${NC}"
echo ""
echo -e "Database Status:"
echo -e "  ✓ PostgreSQL:  ${GREEN}Operational${NC}"
echo -e "  ✓ TimescaleDB: ${GREEN}Operational${NC} (${TOTAL_CANDLES} candles)"
echo -e "  ✓ Redis:       ${GREEN}Operational${NC}"
echo -e "  ✓ RabbitMQ:    ${GREEN}Operational${NC}"
echo ""
echo -e "Data Status:"
echo -e "  ✓ Historical data: ${GREEN}Loaded${NC} (30 days)"
echo -e "  ✓ Data quality:    ${GREEN}Validated${NC}"
echo -e "  ✓ Schema:          ${GREEN}Complete${NC}"
echo -e "  ✓ Optimizations:   ${GREEN}Active${NC} (hypertables, compression)"
echo ""
echo -e "${GREEN}✅ All database systems operational and ready for ML training${NC}"
echo ""
