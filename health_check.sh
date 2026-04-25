#!/bin/bash
# ============================================================================
# Health Check Script for Crypto Trading Bot
# Purpose: Monitor health status of all microservices
# Usage: ./health_check.sh [--json] [--watch]
# Author: DevOps Automation Agent
# Date: 2025-12-11
# ============================================================================

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

# Service port mapping
declare -A SERVICES=(
    ["api-gateway"]=8000
    ["bybit-connector"]=8001
    ["market-data"]=8002
    ["portfolio"]=8003
    ["technical-analysis"]=8004
    ["trading-engine"]=8005
    ["notification"]=8006
    ["ml-prediction"]=8007
    ["sentiment"]=8008
    ["risk-metrics"]=8009
)

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to check service health
check_service_health() {
    local service=$1
    local port=$2
    local timeout=5

    # Try to get health endpoint
    local response=$(curl -s --max-time $timeout "http://localhost:$port/health" 2>/dev/null)
    local curl_exit=$?

    if [ $curl_exit -ne 0 ]; then
        echo "UNAVAILABLE"
        return 1
    fi

    # Parse status from JSON response
    local status=$(echo "$response" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data.get('status', 'unknown'))" 2>/dev/null || echo "error")

    if [ "$status" = "healthy" ] || [ "$status" = "ok" ]; then
        echo "HEALTHY"
        return 0
    else
        echo "$status"
        return 1
    fi
}

# Function to check Docker container status
check_container_status() {
    local service=$1
    local container_name="crypto-bot-${service}"

    # Check if docker is available
    if ! command -v docker &> /dev/null; then
        echo "N/A"
        return 2
    fi

    local status=$(docker ps --filter "name=$container_name" --format "{{.Status}}" 2>/dev/null | head -1)

    if [ -z "$status" ]; then
        echo "NOT_RUNNING"
        return 1
    fi

    echo "$status"
    return 0
}

# Function to check Statistical Arbitrage Manager status
check_stat_arb_status() {
    local response=$(curl -s --max-time 5 "http://localhost:8005/api/v1/statistical-arbitrage/status" 2>/dev/null)
    local curl_exit=$?

    if [ $curl_exit -ne 0 ]; then
        echo "UNAVAILABLE"
        return 1
    fi

    local status=$(echo "$response" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data.get('status', 'unknown'))" 2>/dev/null || echo "error")
    echo "$status"
    return 0
}

# Function to get stat arb performance metrics
get_stat_arb_metrics() {
    local response=$(curl -s --max-time 5 "http://localhost:8005/api/v1/statistical-arbitrage/status" 2>/dev/null)

    if [ -z "$response" ]; then
        return 1
    fi

    python3 << EOF
import json
import sys

try:
    data = json.loads('''$response''')
    manager = data.get('manager_status', {}).get('manager', {})
    strategies = data.get('manager_status', {}).get('strategies', {})

    print(f"Capital: \${manager.get('total_capital', 0):,.2f}")
    print(f"Allocated: \${manager.get('allocated_capital', 0):,.2f}")
    print(f"Total Profit: \${manager.get('total_profit', 0):,.2f}")
    print(f"Total Trades: {manager.get('total_trades', 0)}")
    print(f"Win Rate: {manager.get('win_rate', 0):.1%}")

    pairs_count = strategies.get('pairs', {}).get('count', 0)
    funding_count = strategies.get('funding', {}).get('count', 0)
    triangular = strategies.get('triangular', {}).get('num_paths', 0)

    print(f"Active Strategies: pairs={pairs_count}, funding={funding_count}, triangular_paths={triangular}")

except Exception as e:
    print(f"Error parsing metrics: {e}")
    sys.exit(1)
EOF
}

# Function to display results
display_results() {
    local format=$1

    echo ""
    echo "============================================================================"
    echo "  CRYPTO TRADING BOT - HEALTH CHECK"
    echo "  Time: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "============================================================================"
    echo ""

    # Services health
    echo -e "${BLUE}=== SERVICE HEALTH ===${NC}"
    echo ""
    printf "%-20s %-12s %-30s\n" "SERVICE" "STATUS" "CONTAINER"
    echo "------------------------------------------------------------------------"

    local all_healthy=true
    for service in "${!SERVICES[@]}"; do
        port=${SERVICES[$service]}

        health_status=$(check_service_health "$service" "$port")
        container_status=$(check_container_status "$service")

        if [ "$health_status" = "HEALTHY" ]; then
            color=$GREEN
        elif [ "$health_status" = "UNAVAILABLE" ]; then
            color=$RED
            all_healthy=false
        else
            color=$YELLOW
            all_healthy=false
        fi

        printf "%-20s ${color}%-12s${NC} %-30s\n" "$service" "$health_status" "$container_status"
    done | sort

    echo ""

    # Statistical Arbitrage Status
    echo -e "${BLUE}=== STATISTICAL ARBITRAGE STATUS ===${NC}"
    echo ""
    stat_arb_status=$(check_stat_arb_status)
    if [ "$stat_arb_status" = "active" ]; then
        echo -e "Manager Status: ${GREEN}$stat_arb_status${NC}"
        echo ""
        get_stat_arb_metrics
    else
        echo -e "Manager Status: ${YELLOW}$stat_arb_status${NC}"
        echo "Hint: Initialize with POST /api/v1/statistical-arbitrage/initialize"
    fi

    echo ""

    # Infrastructure Services
    echo -e "${BLUE}=== INFRASTRUCTURE ===${NC}"
    echo ""

    # Check PostgreSQL
    pg_status=$(docker exec crypto-bot-postgres pg_isready -U postgres 2>/dev/null && echo "READY" || echo "NOT_READY")
    echo -e "PostgreSQL:   ${GREEN}$pg_status${NC}"

    # Check TimescaleDB
    ts_status=$(docker exec crypto-bot-timescaledb pg_isready -U postgres 2>/dev/null && echo "READY" || echo "NOT_READY")
    echo -e "TimescaleDB:  ${GREEN}$ts_status${NC}"

    # Check Redis
    redis_status=$(docker exec crypto-bot-redis redis-cli ping 2>/dev/null | grep -q "PONG" && echo "READY" || echo "NOT_READY")
    echo -e "Redis:        ${GREEN}$redis_status${NC}"

    # Check RabbitMQ
    rabbit_status=$(curl -s "http://localhost:15672/api/health/checks/alarms" -u guest:guest 2>/dev/null | grep -q "ok" && echo "READY" || echo "NOT_READY")
    echo -e "RabbitMQ:     ${GREEN}$rabbit_status${NC}"

    echo ""
    echo "============================================================================"

    if [ "$all_healthy" = true ]; then
        echo -e "Overall Status: ${GREEN}ALL SYSTEMS OPERATIONAL${NC}"
    else
        echo -e "Overall Status: ${YELLOW}SOME ISSUES DETECTED${NC}"
    fi

    echo "============================================================================"
    echo ""
}

# Function for JSON output
output_json() {
    local timestamp=$(date -Iseconds)
    local results=()

    for service in "${!SERVICES[@]}"; do
        port=${SERVICES[$service]}
        health_status=$(check_service_health "$service" "$port")
        container_status=$(check_container_status "$service")
        results+=("\"$service\": {\"port\": $port, \"health\": \"$health_status\", \"container\": \"$container_status\"}")
    done

    stat_arb_status=$(check_stat_arb_status)

    echo "{"
    echo "  \"timestamp\": \"$timestamp\","
    echo "  \"services\": {"
    printf "    %s\n" "${results[@]}" | sed 's/$/,/' | sed '$ s/,$//'
    echo "  },"
    echo "  \"statistical_arbitrage\": \"$stat_arb_status\""
    echo "}"
}

# Function for watch mode
watch_mode() {
    while true; do
        clear
        display_results
        echo "Press Ctrl+C to stop. Refreshing every 10 seconds..."
        sleep 10
    done
}

# Main execution
main() {
    local json_output=false
    local watch=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --json)
                json_output=true
                shift
                ;;
            --watch)
                watch=true
                shift
                ;;
            -h|--help)
                echo "Usage: $0 [--json] [--watch]"
                echo ""
                echo "Options:"
                echo "  --json   Output in JSON format"
                echo "  --watch  Continuous monitoring mode"
                echo "  -h       Show this help"
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    if [ "$watch" = true ]; then
        watch_mode
    elif [ "$json_output" = true ]; then
        output_json
    else
        display_results
    fi
}

main "$@"
