#!/bin/bash
# Crypto Trading Bot - Comprehensive Health Check Script
# Version: 1.0.0
# Last Updated: 2025-11-14
#
# Purpose: Validate all system components are healthy and operational
# Usage: ./scripts/health_check.sh [--verbose]

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
VERBOSE=false
if [[ "$1" == "--verbose" ]]; then
    VERBOSE=true
fi

# Services to check
declare -A SERVICES=(
    ["API Gateway"]="8000"
    ["Bybit Connector"]="8001"
    ["Market Data"]="8002"
    ["Portfolio Manager"]="8003"
    ["Technical Analysis"]="8004"
    ["Trading Engine"]="8005"
    ["Notification Service"]="8006"
    ["ML Prediction"]="8007"
    ["Sentiment Analysis"]="8008"
    ["Risk Metrics"]="8009"
)

# Counters
TOTAL=0
PASSED=0
FAILED=0

# Print header
echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Crypto Trading Bot - System Health Check             ║${NC}"
echo -e "${BLUE}║  $(date '+%Y-%m-%d %H:%M:%S')                                    ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# Function to check service health
check_service() {
    local name=$1
    local port=$2
    local url="http://localhost:${port}/health"

    ((TOTAL++))

    if $VERBOSE; then
        echo -n "Checking ${name} (port ${port})... "
    fi

    # Try to get health status
    response=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 --max-time 5 "$url" 2>/dev/null || echo "000")

    if [ "$response" == "200" ]; then
        # Get detailed status if verbose
        if $VERBOSE; then
            status=$(curl -s "$url" 2>/dev/null | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'unknown'))" 2>/dev/null || echo "unknown")
            echo -e "${GREEN}✓${NC} HEALTHY (status: $status)"
        fi
        ((PASSED++))
        return 0
    else
        if $VERBOSE; then
            echo -e "${RED}✗${NC} FAILED (HTTP $response)"
        fi
        ((FAILED++))
        return 1
    fi
}

# Function to check Docker containers
check_docker() {
    echo -e "\n${BLUE}[1/5] Docker Containers${NC}"
    echo "────────────────────────────────────────"

    if ! command -v docker &> /dev/null; then
        echo -e "${RED}✗${NC} Docker is not installed or not in PATH"
        return 1
    fi

    # Check if docker-compose is available
    if ! command -v docker-compose &> /dev/null; then
        echo -e "${YELLOW}⚠${NC} docker-compose not found in PATH"
        return 1
    fi

    # Get container status
    running=$(docker-compose ps --services --filter "status=running" 2>/dev/null | wc -l)
    total=$(docker-compose ps --services 2>/dev/null | wc -l)

    if [ "$running" -eq "$total" ] && [ "$total" -gt 0 ]; then
        echo -e "${GREEN}✓${NC} All containers running ($running/$total)"

        if $VERBOSE; then
            docker-compose ps
        fi
        return 0
    else
        echo -e "${RED}✗${NC} Some containers are down ($running/$total running)"
        docker-compose ps
        return 1
    fi
}

# Function to check microservices
check_microservices() {
    echo -e "\n${BLUE}[2/5] Microservices Health${NC}"
    echo "────────────────────────────────────────"

    for service in "${!SERVICES[@]}"; do
        check_service "$service" "${SERVICES[$service]}"
    done

    # Summary
    echo ""
    if [ $FAILED -eq 0 ]; then
        echo -e "${GREEN}✓${NC} All microservices healthy (${PASSED}/${TOTAL})"
    else
        echo -e "${RED}✗${NC} Some services unhealthy (${PASSED}/${TOTAL} passed, ${FAILED} failed)"
    fi
}

# Function to check database
check_database() {
    echo -e "\n${BLUE}[3/5] Database Connectivity${NC}"
    echo "────────────────────────────────────────"

    # Check TimescaleDB
    if docker exec crypto-trading-bot-timescaledb-1 pg_isready -U crypto_user -d crypto_trading >/dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} TimescaleDB is ready"

        if $VERBOSE; then
            # Get database size
            db_size=$(docker exec crypto-trading-bot-timescaledb-1 psql -U crypto_user -d crypto_trading -t -c "SELECT pg_size_pretty(pg_database_size('crypto_trading'));" 2>/dev/null | xargs)
            echo "  Database size: $db_size"
        fi
    else
        echo -e "${RED}✗${NC} TimescaleDB is not ready"
    fi

    # Check Redis
    if docker exec crypto-trading-bot-redis-1 redis-cli ping >/dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Redis is ready"

        if $VERBOSE; then
            # Get Redis info
            keys=$(docker exec crypto-trading-bot-redis-1 redis-cli dbsize 2>/dev/null | grep -oP '\d+' || echo "0")
            echo "  Keys in Redis: $keys"
        fi
    else
        echo -e "${RED}✗${NC} Redis is not ready"
    fi

    # Check RabbitMQ
    if docker exec crypto-trading-bot-rabbitmq-1 rabbitmqctl status >/dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} RabbitMQ is ready"
    else
        echo -e "${RED}✗${NC} RabbitMQ is not ready"
    fi
}

# Function to check data collection
check_data_collection() {
    echo -e "\n${BLUE}[4/5] Data Collection Status${NC}"
    echo "────────────────────────────────────────"

    # Check if market data service is collecting
    response=$(curl -s "http://localhost:8002/api/v1/klines/BTCUSDT?interval=60&limit=10" 2>/dev/null)

    if echo "$response" | grep -q "success"; then
        count=$(echo "$response" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('data', [])))" 2>/dev/null || echo "0")

        if [ "$count" -gt 0 ]; then
            echo -e "${GREEN}✓${NC} Market data available ($count candles for BTCUSDT)"

            if $VERBOSE; then
                # Get date range
                first_date=$(echo "$response" | python3 -c "import sys, json; data = json.load(sys.stdin).get('data', []); print(data[0]['timestamp'] if data else 'N/A')" 2>/dev/null || echo "N/A")
                last_date=$(echo "$response" | python3 -c "import sys, json; data = json.load(sys.stdin).get('data', []); print(data[-1]['timestamp'] if data else 'N/A')" 2>/dev/null || echo "N/A")
                echo "  Date range: $first_date to $last_date"
            fi
        else
            echo -e "${YELLOW}⚠${NC} No market data found (database may be empty)"
        fi
    else
        echo -e "${RED}✗${NC} Cannot retrieve market data"
    fi
}

# Function to check ML models
check_ml_models() {
    echo -e "\n${BLUE}[5/5] ML Models Status${NC}"
    echo "────────────────────────────────────────"

    # Check if ML service has models
    symbols=("BTCUSDT" "ETHUSDT" "BNBUSDT" "SOLUSDT" "XRPUSDT")
    models_found=0

    for symbol in "${symbols[@]}"; do
        response=$(curl -s "http://localhost:8007/api/v1/predictions/${symbol}?interval=60" 2>/dev/null)

        if echo "$response" | grep -q "prediction"; then
            ((models_found++))
            if $VERBOSE; then
                direction=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('prediction', {}).get('direction', 'N/A'))" 2>/dev/null || echo "N/A")
                confidence=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('prediction', {}).get('confidence', 0))" 2>/dev/null || echo "0")
                echo -e "  ${symbol}: ${direction} (confidence: ${confidence})"
            fi
        fi
    done

    if [ $models_found -gt 0 ]; then
        echo -e "${GREEN}✓${NC} ML models loaded ($models_found/${#symbols[@]} symbols)"
    else
        echo -e "${YELLOW}⚠${NC} No ML models found (may need training)"
    fi
}

# Function to print summary
print_summary() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}Summary${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"

    # Calculate overall health
    if [ $FAILED -eq 0 ]; then
        echo -e "${GREEN}✓ System Status: HEALTHY${NC}"
        echo -e "  All ${PASSED} services are operational"
        echo ""
        echo -e "Next steps:"
        echo -e "  1. Open dashboard: cd dashboard && python3 -m http.server 8080"
        echo -e "  2. View API docs: http://localhost:8005/docs"
        echo -e "  3. Run E2E test: cd tests/integration && python3 test_e2e_trading_flow.py"
        return 0
    elif [ $FAILED -le 2 ]; then
        echo -e "${YELLOW}⚠ System Status: DEGRADED${NC}"
        echo -e "  ${PASSED}/${TOTAL} services operational, ${FAILED} failed"
        echo ""
        echo -e "Action required:"
        echo -e "  1. Check failed services: docker-compose ps"
        echo -e "  2. View logs: docker-compose logs [service-name]"
        echo -e "  3. Restart: docker-compose restart [service-name]"
        return 1
    else
        echo -e "${RED}✗ System Status: CRITICAL${NC}"
        echo -e "  ${PASSED}/${TOTAL} services operational, ${FAILED} failed"
        echo ""
        echo -e "Action required:"
        echo -e "  1. Restart all services: docker-compose restart"
        echo -e "  2. Check logs: docker-compose logs"
        echo -e "  3. Rebuild if needed: docker-compose build && docker-compose up -d"
        return 2
    fi
}

# Main execution
main() {
    check_docker
    check_microservices
    check_database
    check_data_collection
    check_ml_models
    print_summary
}

# Run main function
main
exit_code=$?

echo ""
echo -e "${BLUE}Health check completed at $(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo ""

exit $exit_code
