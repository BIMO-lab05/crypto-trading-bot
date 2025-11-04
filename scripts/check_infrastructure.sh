#!/bin/bash
# Quick Infrastructure Health Check

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🔍 Crypto Trading Bot - Infrastructure Check${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

check_service() {
    local service=$1
    local port=$2
    
    echo -n "Checking $service (port $port)... "
    
    if docker ps | grep -q "$service" && docker ps | grep "$service" | grep -q "Up"; then
        if docker ps | grep "$service" | grep -q "healthy"; then
            echo -e "${GREEN}✓ healthy${NC}"
            return 0
        else
            echo -e "${YELLOW}⚠ running (health check pending)${NC}"
            return 0
        fi
    else
        echo -e "${RED}✗ not running${NC}"
        return 1
    fi
}

all_ok=true

echo "Docker Infrastructure:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if ! check_service "crypto-bot-postgres" "5432"; then all_ok=false; fi
if ! check_service "crypto-bot-timescaledb" "5433"; then all_ok=false; fi  
if ! check_service "crypto-bot-redis" "6379"; then all_ok=false; fi
if ! check_service "crypto-bot-rabbitmq" "5672"; then all_ok=false; fi

echo ""
echo "Application Services:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

check_port() {
    local name=$1
    local port=$2
    echo -n "Checking $name (port $port)... "
    
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1 ; then
        echo -e "${GREEN}✓ listening${NC}"
        
        # Try HTTP health check
        if curl -s "http://localhost:$port/health" > /dev/null 2>&1; then
            echo "  └─ HTTP health check: ${GREEN}✓${NC}"
        fi
        return 0
    else
        echo -e "${YELLOW}⚠ not running${NC}"
        return 1
    fi
}

check_port "Bybit Connector" "8002"
check_port "Market Data Service" "8003"
check_port "Technical Analysis" "8004"
check_port "Trading Engine" "8001"
check_port "Portfolio Manager" "8005"
check_port "API Gateway" "8000"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "$all_ok" = true ]; then
    echo -e "${GREEN}✓ All infrastructure services are healthy!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Start Bybit Connector: cd services/bybit-connector && uvicorn app.main:app --port 8002"
    echo "  2. Start Market Data: cd services/market-data-service && uvicorn app.main:app --port 8003"
    echo "  3. Run tests: python3 scripts/test_pipeline.py"
else
    echo -e "${RED}✗ Some infrastructure services are not healthy${NC}"
    echo ""
    echo "Fix issues:"
    echo "  cd infrastructure && docker-compose up -d"
    echo "  docker-compose logs [service-name]"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
