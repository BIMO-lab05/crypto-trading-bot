#!/bin/bash
# System Monitoring Script for Crypto Trading Bot
# Comprehensive monitoring of all services, health, metrics, and trading activity

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Service endpoints
declare -A SERVICES=(
    ["API Gateway"]="http://localhost:8000"
    ["Bybit Connector"]="http://localhost:8001"
    ["Market Data"]="http://localhost:8002"
    ["Portfolio Manager"]="http://localhost:8003"
    ["Technical Analysis"]="http://localhost:8004"
    ["Trading Engine"]="http://localhost:8005"
    ["Notification"]="http://localhost:8006"
    ["ML Prediction"]="http://localhost:8007"
    ["Sentiment Analysis"]="http://localhost:8008"
    ["Risk Metrics"]="http://localhost:8009"
    ["Frontend"]="http://localhost:3000"
)

# Function to print section header
print_header() {
    echo -e "\n${CYAN}========================================${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}========================================${NC}\n"
}

# Function to check service health
check_health() {
    local service_name=$1
    local url=$2

    # Try health endpoint first
    response=$(curl -s -o /dev/null -w "%{http_code}" --max-time 2 "${url}/health" 2>/dev/null)

    if [ "$response" = "200" ]; then
        echo -e "${GREEN}✓${NC} ${service_name}: ${GREEN}HEALTHY${NC} (${response})"

        # Try to get detailed health info
        health_data=$(curl -s --max-time 2 "${url}/health" 2>/dev/null)
        if [ ! -z "$health_data" ]; then
            echo "  └─ $health_data" | head -c 100
        fi
    elif [ "$response" = "000" ]; then
        echo -e "${RED}✗${NC} ${service_name}: ${RED}UNREACHABLE${NC}"
    else
        echo -e "${YELLOW}⚠${NC} ${service_name}: ${YELLOW}UNHEALTHY${NC} (${response})"
    fi
}

# Function to get docker stats
get_docker_stats() {
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" | grep crypto-bot
}

# Function to check trading activity
check_trading_activity() {
    # Check portfolio status
    portfolio=$(curl -s --max-time 2 "http://localhost:8003/api/v1/portfolio/summary" 2>/dev/null)

    if [ ! -z "$portfolio" ]; then
        echo -e "${GREEN}Portfolio Summary:${NC}"
        echo "$portfolio" | python3 -m json.tool 2>/dev/null || echo "$portfolio"
    fi

    echo ""

    # Check active positions
    positions=$(curl -s --max-time 2 "http://localhost:8003/api/v1/positions" 2>/dev/null)

    if [ ! -z "$positions" ]; then
        echo -e "${GREEN}Active Positions:${NC}"
        echo "$positions" | python3 -m json.tool 2>/dev/null || echo "$positions"
    fi
}

# Function to check market data availability
check_market_data() {
    symbols=("BTCUSDT" "ETHUSDT")

    for symbol in "${symbols[@]}"; do
        price=$(curl -s --max-time 2 "http://localhost:8002/api/v1/price/${symbol}" 2>/dev/null)
        if [ ! -z "$price" ]; then
            echo -e "${GREEN}${symbol}:${NC} $price"
        else
            echo -e "${RED}${symbol}:${NC} No data"
        fi
    done
}

# Function to tail recent logs
tail_recent_logs() {
    local service=$1
    local lines=${2:-10}

    echo -e "${YELLOW}Recent logs from ${service}:${NC}"
    docker logs --tail ${lines} ${service} 2>&1 | tail -${lines}
}

# Main monitoring loop
main() {
    clear

    print_header "🚀 CRYPTO TRADING BOT - SYSTEM MONITOR"
    echo -e "Timestamp: ${CYAN}$(date '+%Y-%m-%d %H:%M:%S')${NC}\n"

    # 1. Docker Container Status
    print_header "📦 DOCKER CONTAINERS"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "NAMES|crypto-bot"

    # 2. Service Health Checks
    print_header "🏥 SERVICE HEALTH STATUS"
    for service in "${!SERVICES[@]}"; do
        check_health "$service" "${SERVICES[$service]}"
    done

    # 3. System Resources
    print_header "💻 SYSTEM RESOURCES"
    get_docker_stats

    # 4. Market Data
    print_header "📊 MARKET DATA"
    check_market_data

    # 5. Trading Activity
    print_header "💰 TRADING ACTIVITY"
    check_trading_activity

    # 6. Recent Critical Logs
    print_header "📝 RECENT LOGS (Critical Services)"

    # Check for errors in critical services
    critical_services=("crypto-bot-trading" "crypto-bot-portfolio" "crypto-bot-bybit")

    for service in "${critical_services[@]}"; do
        echo -e "\n${MAGENTA}━━━ ${service} ━━━${NC}"
        docker logs --tail 5 --since 5m ${service} 2>&1 | grep -i "error\|warning\|critical" || echo "  No critical logs"
    done

    # 7. System Status Summary
    print_header "📈 SYSTEM STATUS SUMMARY"

    # Count healthy services
    healthy_count=0
    total_count=${#SERVICES[@]}

    for service in "${!SERVICES[@]}"; do
        response=$(curl -s -o /dev/null -w "%{http_code}" --max-time 2 "${SERVICES[$service]}/health" 2>/dev/null)
        if [ "$response" = "200" ]; then
            ((healthy_count++))
        fi
    done

    health_percentage=$((healthy_count * 100 / total_count))

    echo -e "Services Online: ${GREEN}${healthy_count}/${total_count}${NC} (${health_percentage}%)"

    if [ $health_percentage -eq 100 ]; then
        echo -e "System Status: ${GREEN}FULLY OPERATIONAL ✓${NC}"
    elif [ $health_percentage -ge 80 ]; then
        echo -e "System Status: ${YELLOW}DEGRADED ⚠${NC}"
    else
        echo -e "System Status: ${RED}CRITICAL ✗${NC}"
    fi

    echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "Press ${YELLOW}Ctrl+C${NC} to exit continuous monitoring"
    echo -e "Refresh interval: ${CYAN}5 seconds${NC}"
}

# Check if running in continuous mode
if [ "$1" = "--continuous" ] || [ "$1" = "-c" ]; then
    echo "Starting continuous monitoring mode..."
    while true; do
        main
        sleep 5
        clear
    done
else
    # Single run
    main
    echo -e "\n${CYAN}Tip: Run with --continuous for live monitoring${NC}\n"
fi
