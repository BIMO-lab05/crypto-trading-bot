#!/bin/bash
# =============================================================================
# INFRASTRUCTURE MIGRATION SCRIPT
# =============================================================================
# This script migrates from the old dual docker-compose setup to the new
# unified docker-compose.unified.yml
#
# Usage:
#   ./scripts/migrate-infrastructure.sh
#
# What it does:
#   1. Stops old containers
#   2. Creates new network
#   3. Starts new unified setup
#   4. Verifies all services are healthy
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Crypto Trading Bot Infrastructure${NC}"
echo -e "${BLUE}  Migration Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Step 1: Stop existing containers
echo -e "${YELLOW}Step 1: Stopping existing containers...${NC}"
docker-compose -f docker-compose.yml down --remove-orphans 2>/dev/null || true
docker-compose -f infrastructure/docker-compose.yml down --remove-orphans 2>/dev/null || true
echo -e "${GREEN}Done.${NC}"
echo ""

# Step 2: Remove old network if exists
echo -e "${YELLOW}Step 2: Cleaning up old networks...${NC}"
docker network rm infrastructure_crypto-bot-network 2>/dev/null || true
docker network rm crypto-bot-network 2>/dev/null || true
echo -e "${GREEN}Done.${NC}"
echo ""

# Step 3: Create new network
echo -e "${YELLOW}Step 3: Creating new network...${NC}"
docker network create crypto-bot-network 2>/dev/null || echo "Network already exists"
echo -e "${GREEN}Done.${NC}"
echo ""

# Step 4: Start infrastructure services first
echo -e "${YELLOW}Step 4: Starting infrastructure services...${NC}"
docker-compose -f docker-compose.unified.yml up -d postgres timescaledb redis rabbitmq
echo -e "${GREEN}Done.${NC}"
echo ""

# Step 5: Wait for infrastructure to be healthy
echo -e "${YELLOW}Step 5: Waiting for infrastructure to be healthy...${NC}"
echo "Waiting for PostgreSQL..."
until docker exec crypto-bot-postgres pg_isready -U cryptobot > /dev/null 2>&1; do
    sleep 2
    echo -n "."
done
echo " Ready!"

echo "Waiting for TimescaleDB..."
until docker exec crypto-bot-timescaledb pg_isready -U cryptobot > /dev/null 2>&1; do
    sleep 2
    echo -n "."
done
echo " Ready!"

echo "Waiting for Redis..."
until docker exec crypto-bot-redis redis-cli ping > /dev/null 2>&1; do
    sleep 2
    echo -n "."
done
echo " Ready!"

echo "Waiting for RabbitMQ..."
until docker exec crypto-bot-rabbitmq rabbitmq-diagnostics ping > /dev/null 2>&1; do
    sleep 2
    echo -n "."
done
echo " Ready!"
echo -e "${GREEN}All infrastructure services are healthy.${NC}"
echo ""

# Step 6: Start application services
echo -e "${YELLOW}Step 6: Starting application services...${NC}"
docker-compose -f docker-compose.unified.yml up -d
echo -e "${GREEN}Done.${NC}"
echo ""

# Step 7: Wait for all services to be healthy
echo -e "${YELLOW}Step 7: Waiting for all services to be healthy...${NC}"
sleep 30

# Check service health
SERVICES=(
    "api-gateway:8000"
    "bybit-connector:8001"
    "market-data:8002"
    "portfolio-manager:8003"
    "technical-analysis:8004"
    "trading-engine:8005"
    "notification-service:8006"
    "ml-prediction:8007"
    "sentiment-analysis:8008"
    "risk-metrics:8009"
    "frontend:3000"
)

echo ""
echo -e "${BLUE}Service Health Check:${NC}"
echo "----------------------------------------"

ALL_HEALTHY=true
for SERVICE in "${SERVICES[@]}"; do
    NAME="${SERVICE%%:*}"
    PORT="${SERVICE##*:}"

    if curl -s "http://localhost:${PORT}/health" > /dev/null 2>&1; then
        echo -e "${GREEN}[OK]${NC} ${NAME} (port ${PORT})"
    else
        echo -e "${RED}[FAIL]${NC} ${NAME} (port ${PORT})"
        ALL_HEALTHY=false
    fi
done

echo "----------------------------------------"
echo ""

if [ "$ALL_HEALTHY" = true ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  Migration Complete!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "Dashboard: ${BLUE}http://localhost:3000${NC}"
    echo -e "API Gateway: ${BLUE}http://localhost:8000${NC}"
    echo -e "API Docs: ${BLUE}http://localhost:8000/docs${NC}"
    echo -e "RabbitMQ: ${BLUE}http://localhost:15672${NC}"
    echo ""
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}  Migration completed with warnings${NC}"
    echo -e "${RED}========================================${NC}"
    echo ""
    echo "Some services may still be starting."
    echo "Check logs with: docker-compose -f docker-compose.unified.yml logs -f"
    echo ""
fi

# Step 8: Show running containers
echo -e "${YELLOW}Running containers:${NC}"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | head -20
