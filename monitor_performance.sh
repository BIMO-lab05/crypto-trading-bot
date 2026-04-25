#!/bin/bash
# Performance Metrics Monitor
# Tracks API response times, throughput, and resource usage

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

clear

echo -e "${CYAN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     CRYPTO TRADING BOT - PERFORMANCE MONITOR          ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# Test API response times
echo -e "${CYAN}API Response Times (ms):${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

declare -A SERVICES=(
    ["API Gateway"]="http://localhost:8000/health"
    ["Bybit"]="http://localhost:8001/health"
    ["Market Data"]="http://localhost:8002/health"
    ["Portfolio"]="http://localhost:8003/health"
    ["Tech Analysis"]="http://localhost:8004/health"
    ["Trading Engine"]="http://localhost:8005/health"
    ["Notification"]="http://localhost:8006/health"
    ["ML Prediction"]="http://localhost:8007/health"
)

for service in "${!SERVICES[@]}"; do
    url="${SERVICES[$service]}"

    # Measure response time
    response_time=$(curl -o /dev/null -s -w '%{time_total}' "$url" 2>/dev/null)
    response_ms=$(echo "$response_time * 1000" | bc 2>/dev/null | cut -d. -f1)

    # Color code based on performance
    if [ "$response_ms" -lt 50 ]; then
        color=$GREEN
    elif [ "$response_ms" -lt 100 ]; then
        color=$YELLOW
    else
        color=$RED
    fi

    printf "%-20s ${color}%5s ms${NC}\n" "$service:" "$response_ms"
done

echo ""
echo -e "${CYAN}Resource Usage:${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | \
    grep crypto-bot | \
    awk '{printf "%-25s CPU: %8s  MEM: %s\n", $1, $2, $3}'

echo ""
echo -e "${CYAN}Network I/O:${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
docker stats --no-stream --format "{{.Name}}\t{{.NetIO}}" | \
    grep crypto-bot | \
    awk '{printf "%-25s %s\n", $1, $2}'

echo ""
echo -e "${CYAN}Database Connections:${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check PostgreSQL connections
pg_connections=$(docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -t -c \
    "SELECT count(*) FROM pg_stat_activity WHERE datname='cryptobot';" 2>/dev/null | tr -d ' ')
echo "PostgreSQL active connections: ${pg_connections:-N/A}"

# Check Redis memory
redis_mem=$(docker exec crypto-bot-redis redis-cli INFO memory 2>/dev/null | \
    grep "used_memory_human" | cut -d: -f2 | tr -d '\r')
echo "Redis memory usage: ${redis_mem:-N/A}"

# Check RabbitMQ queues
rabbitmq_queues=$(docker exec crypto-bot-rabbitmq rabbitmqctl list_queues 2>/dev/null | wc -l)
echo "RabbitMQ queues: ${rabbitmq_queues:-N/A}"

echo ""
echo -e "${CYAN}System Load:${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
uptime

echo ""
if [ "$1" = "--continuous" ] || [ "$1" = "-c" ]; then
    echo -e "${YELLOW}Refreshing in 5 seconds...${NC}"
    sleep 5
    clear
    exec bash "$0" "$@"
else
    echo -e "${CYAN}Tip: Run with --continuous for live updates${NC}"
fi
