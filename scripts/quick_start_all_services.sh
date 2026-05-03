#!/bin/bash
###############################################################################
# Quick Start All Services - Development Mode
# Starts all services directly with Python (faster than Docker)
###############################################################################

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${BLUE}=====================================================================================================${NC}"
echo -e "${BLUE}        CRYPTO TRADING BOT - QUICK START (Development Mode)${NC}"
echo -e "${BLUE}=====================================================================================================${NC}"
echo ""

# Kill any existing services
echo -e "${YELLOW}Stopping existing services...${NC}"
pkill -f "uvicorn app.main:app" 2>/dev/null || true
sleep 2

# Function to start a service
start_service() {
    local service_name=$1
    local service_dir=$2
    local port=$3

    echo -e "${GREEN}Starting $service_name on port $port...${NC}"

    cd "$PROJECT_ROOT/$service_dir"

    # Start in background
    nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port $port \
        > "/tmp/${service_name}.log" 2>&1 &

    local pid=$!
    echo "  PID: $pid"

    # Brief wait
    sleep 1
}

# Start all services
echo -e "\n${BLUE}Starting microservices...${NC}\n"

start_service "api-gateway" "services/api-gateway" 8000
start_service "bybit-connector" "services/bybit-connector" 8001
start_service "market-data" "services/market-data-service" 8002
start_service "portfolio-manager" "services/portfolio-manager" 8003
start_service "technical-analysis" "services/technical-analysis" 8004
start_service "trading-engine" "services/trading-engine" 8005
start_service "notification" "services/notification-service" 8006
start_service "ml-prediction" "services/ml-prediction-service" 8007
start_service "sentiment-analysis" "services/sentiment-analysis-service" 8008
start_service "risk-metrics" "services/risk-metrics-service" 8009

echo ""
echo -e "${YELLOW}Waiting 10 seconds for services to initialize...${NC}"
sleep 10

# Health check
echo ""
echo -e "${BLUE}=====================================================================================================${NC}"
echo -e "${BLUE}        SERVICE HEALTH CHECK${NC}"
echo -e "${BLUE}=====================================================================================================${NC}"
echo ""

for port in 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009; do
    status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$port/health 2>/dev/null || echo "000")

    if [ "$status" = "200" ]; then
        echo -e "Port $port: ${GREEN}✓ HEALTHY${NC}"
    else
        echo -e "Port $port: ${RED}✗ NOT RESPONDING${NC} (check /tmp/*-$port.log)"
    fi
done

echo ""
echo -e "${BLUE}=====================================================================================================${NC}"
echo -e "${GREEN}        SERVICES STARTED!${NC}"
echo -e "${BLUE}=====================================================================================================${NC}"
echo ""

echo "Service URLs:"
echo "  • API Gateway:          http://localhost:8000"
echo "  • Bybit Connector:      http://localhost:8001"
echo "  • Market Data:          http://localhost:8002"
echo "  • Portfolio Manager:    http://localhost:8003"
echo "  • Technical Analysis:   http://localhost:8004"
echo "  • Trading Engine:       http://localhost:8005"
echo "  • Notification:         http://localhost:8006"
echo "  • ML Prediction:        http://localhost:8007 ⭐"
echo "  • Sentiment Analysis:   http://localhost:8008 ⭐"
echo "  • Risk Metrics:         http://localhost:8009"
echo ""

echo "API Documentation:"
echo "  • http://localhost:8000/docs (API Gateway)"
echo "  • http://localhost:8007/docs (ML Prediction)"
echo "  • http://localhost:8008/docs (Sentiment Analysis)"
echo ""

echo "Logs:"
echo "  • tail -f /tmp/ml-prediction.log"
echo "  • tail -f /tmp/sentiment-analysis.log"
echo "  • tail -f /tmp/trading-engine.log"
echo ""

echo -e "${GREEN}Ready to train ML models and start trading!${NC}"
echo ""
