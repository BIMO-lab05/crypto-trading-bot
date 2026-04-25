#!/bin/bash
# Master Monitoring Dashboard
# Combined view of all monitoring aspects

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Function to draw separator
draw_separator() {
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# Main dashboard
while true; do
    clear

    # Header
    echo -e "${BOLD}${CYAN}"
    cat << "EOF"
╔══════════════════════════════════════════════════════════════════════════╗
║                                                                          ║
║            🚀 CRYPTO TRADING BOT - MASTER DASHBOARD 🚀                  ║
║                                                                          ║
║                      Real-Time System Monitor                            ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
EOF
    echo -e "${NC}"

    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${CYAN}📅 Last Update: ${timestamp}${NC}"
    draw_separator
    echo ""

    # System Status Summary
    echo -e "${BOLD}${YELLOW}📊 SYSTEM STATUS${NC}"
    draw_separator

    # Count healthy services
    healthy=0
    total=11
    for port in 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009 3000; do
        status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 1 http://localhost:$port/health 2>/dev/null)
        [ "$status" = "200" ] && ((healthy++))
    done

    percentage=$((healthy * 100 / total))

    if [ $percentage -eq 100 ]; then
        status_color=$GREEN
        status_icon="✅"
        status_text="FULLY OPERATIONAL"
    elif [ $percentage -ge 80 ]; then
        status_color=$YELLOW
        status_icon="⚠️ "
        status_text="DEGRADED"
    else
        status_color=$RED
        status_icon="❌"
        status_text="CRITICAL"
    fi

    echo -e "${status_color}${status_icon} Status: ${status_text}  |  Services: ${healthy}/${total} (${percentage}%)${NC}"

    # Resource usage summary
    total_cpu=$(docker stats --no-stream --format "{{.CPUPerc}}" | grep -v CPU | sed 's/%//' | awk '{sum+=$1} END {printf "%.1f", sum}')
    echo -e "${BLUE}💻 Total CPU: ${total_cpu}%${NC}"

    echo ""

    # Services Grid
    echo -e "${BOLD}${YELLOW}🔧 SERVICES STATUS${NC}"
    draw_separator

    services=(
        "8000:API Gateway"
        "8001:Bybit"
        "8002:Market Data"
        "8003:Portfolio"
        "8004:Tech Analysis"
        "8005:Trading Engine"
        "8006:Notification"
        "8007:ML Prediction"
        "8008:Sentiment"
        "8009:Risk Metrics"
        "3000:Frontend"
    )

    col=0
    for service in "${services[@]}"; do
        port="${service%%:*}"
        name="${service##*:}"

        response=$(curl -s -o /dev/null -w "%{http_code}" --max-time 1 http://localhost:$port/health 2>/dev/null)

        if [ "$response" = "200" ]; then
            status="${GREEN}●${NC}"
        else
            status="${RED}●${NC}"
        fi

        printf "%-30s " "$status $name"

        ((col++))
        if [ $col -eq 3 ]; then
            echo ""
            col=0
        fi
    done
    [ $col -ne 0 ] && echo ""

    echo ""

    # Infrastructure
    echo -e "${BOLD}${YELLOW}🗄️  INFRASTRUCTURE${NC}"
    draw_separator

    infra_services=("postgres" "timescaledb" "redis" "rabbitmq")
    for svc in "${infra_services[@]}"; do
        container="crypto-bot-$svc"
        if docker ps --format "{{.Names}}" | grep -q "^${container}$"; then
            health=$(docker inspect --format='{{.State.Health.Status}}' $container 2>/dev/null || echo "running")
            if [ "$health" = "healthy" ] || [ "$health" = "running" ]; then
                echo -e "${GREEN}●${NC} $svc"
            else
                echo -e "${YELLOW}●${NC} $svc (starting)"
            fi
        else
            echo -e "${RED}●${NC} $svc (stopped)"
        fi
    done

    echo ""

    # Trading Activity
    echo -e "${BOLD}${YELLOW}💰 TRADING ACTIVITY${NC}"
    draw_separator

    portfolio=$(curl -s http://localhost:8003/api/v1/portfolio/summary 2>/dev/null)
    if [ ! -z "$portfolio" ] && [[ ! "$portfolio" =~ "detail" ]]; then
        echo "$portfolio" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(f\"Balance: \${data.get('balance', 'N/A')}\")
    print(f\"Equity: \${data.get('equity', 'N/A')}\")
    print(f\"P&L: {data.get('pnl', 'N/A')}%\")
except:
    print('Portfolio data not available')
" 2>/dev/null || echo "Portfolio initializing..."
    else
        echo -e "${YELLOW}No active trading yet${NC}"
    fi

    echo ""

    # Market Prices
    echo -e "${BOLD}${YELLOW}📈 MARKET PRICES${NC}"
    draw_separator

    symbols=("BTCUSDT" "ETHUSDT" "SOLUSDT" "BNBUSDT")
    col=0
    for symbol in "${symbols[@]}"; do
        price=$(curl -s "http://localhost:8002/api/v1/price/${symbol}" 2>/dev/null)
        if [ ! -z "$price" ] && [[ ! "$price" =~ "detail" ]]; then
            printf "%-25s " "$symbol: \$$price"
        else
            printf "%-25s " "$symbol: N/A"
        fi

        ((col++))
        if [ $col -eq 2 ]; then
            echo ""
            col=0
        fi
    done
    [ $col -ne 0 ] && echo ""

    echo ""

    # Performance Metrics
    echo -e "${BOLD}${YELLOW}⚡ PERFORMANCE${NC}"
    draw_separator

    # Average response time
    total_time=0
    count=0
    for port in 8000 8001 8002 8003 8004 8005; do
        time=$(curl -o /dev/null -s -w '%{time_total}' --max-time 1 http://localhost:$port/health 2>/dev/null)
        if [ ! -z "$time" ]; then
            total_time=$(echo "$total_time + $time" | bc)
            ((count++))
        fi
    done

    if [ $count -gt 0 ]; then
        avg_time=$(echo "scale=3; $total_time / $count * 1000" | bc)
        avg_time_int=${avg_time%.*}

        if [ "$avg_time_int" -lt 50 ]; then
            perf_color=$GREEN
        elif [ "$avg_time_int" -lt 100 ]; then
            perf_color=$YELLOW
        else
            perf_color=$RED
        fi

        echo -e "Average API Response: ${perf_color}${avg_time} ms${NC}"
    fi

    # Memory usage
    total_mem=$(docker stats --no-stream --format "{{.MemUsage}}" | grep -v MEM | awk '{sum+=substr($1,1,length($1)-3)} END {printf "%.0f", sum}')
    echo -e "Total Memory Usage: ${BLUE}${total_mem} MB${NC}"

    echo ""

    # Recent Errors
    echo -e "${BOLD}${YELLOW}⚠️  RECENT ERRORS${NC}"
    draw_separator

    error_count=0
    for container in crypto-bot-trading crypto-bot-portfolio crypto-bot-bybit; do
        errors=$(docker logs --tail 10 --since 5m $container 2>&1 | grep -i "error\|critical" | wc -l)
        error_count=$((error_count + errors))
    done

    if [ $error_count -eq 0 ]; then
        echo -e "${GREEN}✓ No recent errors${NC}"
    else
        echo -e "${RED}⚠ $error_count errors in last 5 minutes${NC}"
        echo -e "${YELLOW}Run './monitor_logs.sh' for details${NC}"
    fi

    echo ""
    draw_separator

    # Footer
    echo -e "${CYAN}[R] Refresh Now  [Q] Quit  [S] System Monitor  [T] Trading Monitor  [P] Performance${NC}"
    echo -e "${CYAN}Auto-refresh in 10 seconds...${NC}"

    # Wait for input or auto-refresh
    read -t 10 -n 1 key

    case $key in
        r|R) continue ;;
        q|Q) exit 0 ;;
        s|S) exec ./monitor_system.sh ;;
        t|T) exec ./monitor_trading.sh ;;
        p|P) exec ./monitor_performance.sh ;;
    esac
done
