#!/bin/bash
# Comprehensive startup script for all Crypto Trading Bot services
# This script starts all 6 microservices in the correct order

set -e  # Exit on error

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Project root directory
PROJECT_ROOT="/mnt/d/Bimo_max/crypto-trading-bot"

echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}🚀 Crypto Trading Bot - Starting All Services${NC}"
echo -e "${BLUE}======================================${NC}"
echo ""

# Function to start a service
start_service() {
    local service_name=$1
    local service_dir=$2
    local port=$3

    echo -e "${YELLOW}Starting ${service_name} on port ${port}...${NC}"

    # Kill any existing process on this port
    lsof -ti:${port} | xargs kill -9 2>/dev/null || true

    # Navigate to service directory and start
    cd "${PROJECT_ROOT}/${service_dir}"

    # Start service in background
    nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port ${port} \
        > "/tmp/${service_name}.log" 2>&1 &

    local pid=$!
    echo $pid > "/tmp/${service_name}.pid"

    # Wait a moment for service to start
    sleep 2

    # Check if service is responding
    if curl -s -f "http://localhost:${port}/health" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ ${service_name} started successfully (PID: ${pid})${NC}"
        return 0
    else
        echo -e "${RED}⚠️  ${service_name} may have issues (check /tmp/${service_name}.log)${NC}"
        return 1
    fi
}

# Function to check if PostgreSQL is running
check_database() {
    echo -e "${YELLOW}Checking database connection...${NC}"
    if pg_isready -h localhost >/dev/null 2>&1; then
        echo -e "${GREEN}✅ PostgreSQL is running${NC}"
        return 0
    else
        echo -e "${RED}❌ PostgreSQL is not running${NC}"
        echo -e "${YELLOW}Please start PostgreSQL first${NC}"
        return 1
    fi
}

# Main execution
echo "Step 1: Checking database..."
check_database || exit 1
echo ""

echo "Step 2: Starting microservices..."
echo ""

# Start services in order
# 1. Bybit Connector (provides exchange API)
start_service "bybit-connector" "services/bybit-connector" 8002
echo ""

# 2. Market Data Service (depends on Bybit Connector)
start_service "market-data-service" "services/market-data-service" 8003
echo ""

# 3. Technical Analysis (depends on Market Data)
start_service "technical-analysis" "services/technical-analysis" 8004
echo ""

# 4. Trading Engine (depends on Technical Analysis)
start_service "trading-engine" "services/trading-engine" 8005
echo ""

# 5. Portfolio Manager (independent)
start_service "portfolio-manager" "services/portfolio-manager" 8006
echo ""

# 6. API Gateway (provides unified interface)
start_service "api-gateway" "services/api-gateway" 8000
echo ""

echo -e "${BLUE}======================================${NC}"
echo -e "${GREEN}✅ All services started!${NC}"
echo -e "${BLUE}======================================${NC}"
echo ""

echo "Service Status:"
echo "  • Bybit Connector:     http://localhost:8002/docs"
echo "  • Market Data:         http://localhost:8003/docs"
echo "  • Technical Analysis:  http://localhost:8004/docs"
echo "  • Trading Engine:      http://localhost:8005/docs"
echo "  • Portfolio Manager:   http://localhost:8006/docs"
echo "  • API Gateway:         http://localhost:8000/docs"
echo ""

echo "Logs located in: /tmp/*.log"
echo ""

echo "To check service health:"
echo "  bash scripts/check_infrastructure.sh"
echo ""

echo "To stop all services:"
echo "  pkill -f 'uvicorn app.main:app'"
echo ""

echo -e "${GREEN}🎉 System ready for automated trading!${NC}"
