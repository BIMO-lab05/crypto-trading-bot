#!/bin/bash
# =============================================================================
# SQZMOM Paper Trading Monitoring Script
# Purpose: Monitor paper trading performance and system health
# Created: 2025-12-12
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
PROJECT_DIR="/mnt/d/Bimo_max/crypto-trading-bot"
LOG_FILE="$PROJECT_DIR/logs/paper_trading_monitor.log"
ALERT_FILE="$PROJECT_DIR/logs/paper_trading_alerts.log"

# Service endpoints
TRADING_ENGINE="http://localhost:8005"
PORTFOLIO_MANAGER="http://localhost:8003"
MARKET_DATA="http://localhost:8002"
NOTIFICATION="http://localhost:8006"
RISK_METRICS="http://localhost:8009"

# Timestamp function
timestamp() {
    date "+%Y-%m-%d %H:%M:%S"
}

# Log function
log() {
    echo -e "[$(timestamp)] $1" | tee -a "$LOG_FILE"
}

# Alert function
alert() {
    echo -e "[$(timestamp)] ALERT: $1" | tee -a "$ALERT_FILE"
}

# Print header
print_header() {
    echo -e "${CYAN}=============================================================================="
    echo -e "  SQZMOM Paper Trading Monitor - $(timestamp)"
    echo -e "==============================================================================${NC}"
    echo ""
}

# Check service health
check_service_health() {
    local name=$1
    local url=$2
    local response=$(curl -s -o /dev/null -w "%{http_code}" "$url/health" 2>/dev/null)

    if [ "$response" == "200" ]; then
        echo -e "${GREEN}[OK]${NC} $name"
        return 0
    else
        echo -e "${RED}[FAIL]${NC} $name (HTTP $response)"
        alert "$name service unhealthy (HTTP $response)"
        return 1
    fi
}

# Check all services
check_all_services() {
    echo -e "${BLUE}=== Service Health Check ===${NC}"
    echo ""

    local healthy=0
    local total=0

    for service in "Trading Engine:$TRADING_ENGINE" "Portfolio Manager:$PORTFOLIO_MANAGER" "Market Data:$MARKET_DATA" "Notification:$NOTIFICATION" "Risk Metrics:$RISK_METRICS"; do
        name=$(echo $service | cut -d: -f1)
        url=$(echo $service | cut -d: -f2-)
        ((total++))
        if check_service_health "$name" "$url"; then
            ((healthy++))
        fi
    done

    echo ""
    echo -e "Services: ${healthy}/${total} healthy"
    echo ""

    if [ $healthy -lt $total ]; then
        return 1
    fi
    return 0
}

# Get trading status
get_trading_status() {
    echo -e "${BLUE}=== Trading Engine Status ===${NC}"
    echo ""

    local status=$(curl -s "$TRADING_ENGINE/api/v1/status" 2>/dev/null)

    if [ -n "$status" ]; then
        echo "$status" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(f'  Mode: {data.get(\"mode\", \"unknown\")}')
    print(f'  Strategy: {data.get(\"strategy\", \"unknown\")}')
    print(f'  Auto Trading: {data.get(\"auto_trading_enabled\", \"unknown\")}')
    print(f'  Active Symbols: {data.get(\"active_symbols\", [])}')
except:
    print('  Unable to parse status')
"
    else
        echo -e "${YELLOW}  Unable to fetch trading status${NC}"
    fi
    echo ""
}

# Get current positions
get_positions() {
    echo -e "${BLUE}=== Current Positions ===${NC}"
    echo ""

    local positions=$(curl -s "$PORTFOLIO_MANAGER/api/v1/positions" 2>/dev/null)

    if [ -n "$positions" ]; then
        local count=$(echo "$positions" | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data.get('positions', []) if isinstance(data, dict) else data))" 2>/dev/null || echo "0")

        if [ "$count" == "0" ]; then
            echo -e "  ${YELLOW}No open positions${NC}"
        else
            echo "$positions" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    positions = data.get('positions', []) if isinstance(data, dict) else data
    for p in positions:
        symbol = p.get('symbol', 'N/A')
        side = p.get('side', 'N/A')
        size = p.get('size', 0)
        pnl = p.get('unrealized_pnl', 0)
        pnl_pct = p.get('pnl_percent', 0)
        color = '\\033[92m' if pnl >= 0 else '\\033[91m'
        reset = '\\033[0m'
        print(f'  {symbol}: {side} {size} | PnL: {color}${pnl:.2f} ({pnl_pct:.2f}%){reset}')
except Exception as e:
    print(f'  Unable to parse positions: {e}')
"
        fi
    else
        echo -e "  ${YELLOW}Unable to fetch positions${NC}"
    fi
    echo ""
}

# Get portfolio summary
get_portfolio_summary() {
    echo -e "${BLUE}=== Portfolio Summary ===${NC}"
    echo ""

    local portfolio=$(curl -s "$PORTFOLIO_MANAGER/api/v1/portfolio/status" 2>/dev/null)

    if [ -n "$portfolio" ]; then
        echo "$portfolio" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    balance = data.get('balance', {})
    total = balance.get('total', 0)
    available = balance.get('available', 0)
    used = balance.get('used', 0)
    pnl = data.get('total_pnl', 0)
    pnl_pct = data.get('pnl_percent', 0)

    color = '\\033[92m' if pnl >= 0 else '\\033[91m'
    reset = '\\033[0m'

    print(f'  Total Balance: \${total:.2f}')
    print(f'  Available: \${available:.2f}')
    print(f'  In Use: \${used:.2f}')
    print(f'  Total P&L: {color}\${pnl:.2f} ({pnl_pct:.2f}%){reset}')
except:
    print('  Unable to parse portfolio')
"
    else
        echo -e "  ${YELLOW}Unable to fetch portfolio${NC}"
    fi
    echo ""
}

# Get daily stats
get_daily_stats() {
    echo -e "${BLUE}=== Daily Statistics ===${NC}"
    echo ""

    local stats=$(curl -s "$TRADING_ENGINE/api/v1/performance/daily" 2>/dev/null)

    if [ -n "$stats" ]; then
        echo "$stats" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    trades = data.get('total_trades', 0)
    wins = data.get('winning_trades', 0)
    losses = data.get('losing_trades', 0)
    win_rate = data.get('win_rate', 0)
    pnl = data.get('daily_pnl', 0)

    color = '\\033[92m' if pnl >= 0 else '\\033[91m'
    reset = '\\033[0m'

    print(f'  Total Trades: {trades}')
    print(f'  Wins: {wins} | Losses: {losses}')
    print(f'  Win Rate: {win_rate:.1f}%')
    print(f'  Daily P&L: {color}\${pnl:.2f}{reset}')
except:
    print('  Unable to parse daily stats')
"
    else
        echo -e "  ${YELLOW}Unable to fetch daily stats${NC}"
    fi
    echo ""
}

# Get recent trades
get_recent_trades() {
    echo -e "${BLUE}=== Recent Trades (Last 10) ===${NC}"
    echo ""

    local trades=$(curl -s "$PORTFOLIO_MANAGER/api/v1/trades?limit=10" 2>/dev/null)

    if [ -n "$trades" ]; then
        echo "$trades" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    trades = data.get('trades', []) if isinstance(data, dict) else data
    if not trades:
        print('  No recent trades')
    else:
        for t in trades[:10]:
            symbol = t.get('symbol', 'N/A')
            side = t.get('side', 'N/A')
            pnl = t.get('pnl', 0)
            timestamp = t.get('timestamp', 'N/A')[:19] if t.get('timestamp') else 'N/A'
            color = '\\033[92m' if pnl >= 0 else '\\033[91m'
            reset = '\\033[0m'
            print(f'  [{timestamp}] {symbol} {side}: {color}\${pnl:.2f}{reset}')
except:
    print('  Unable to parse trades')
"
    else
        echo -e "  ${YELLOW}Unable to fetch trades${NC}"
    fi
    echo ""
}

# Get risk utilization
get_risk_utilization() {
    echo -e "${BLUE}=== Risk Utilization ===${NC}"
    echo ""

    local risk=$(curl -s "$RISK_METRICS/api/v1/risk/current" 2>/dev/null)

    if [ -n "$risk" ]; then
        echo "$risk" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    daily_loss = data.get('daily_loss_percent', 0)
    total_exposure = data.get('total_exposure_percent', 0)
    max_daily = data.get('max_daily_loss_percent', 5)
    max_exposure = data.get('max_exposure_percent', 70)

    # Color coding based on utilization
    daily_color = '\\033[92m' if daily_loss < max_daily * 0.5 else '\\033[93m' if daily_loss < max_daily * 0.8 else '\\033[91m'
    exp_color = '\\033[92m' if total_exposure < max_exposure * 0.5 else '\\033[93m' if total_exposure < max_exposure * 0.8 else '\\033[91m'
    reset = '\\033[0m'

    print(f'  Daily Loss: {daily_color}{daily_loss:.2f}% / {max_daily}%{reset}')
    print(f'  Total Exposure: {exp_color}{total_exposure:.2f}% / {max_exposure}%{reset}')
except:
    print('  Unable to parse risk data')
"
    else
        echo -e "  ${YELLOW}Unable to fetch risk metrics${NC}"
    fi
    echo ""
}

# Check for alerts
check_alerts() {
    echo -e "${BLUE}=== Alert Check ===${NC}"
    echo ""

    local alerts=0

    # Check daily loss limit
    local risk=$(curl -s "$RISK_METRICS/api/v1/risk/current" 2>/dev/null)
    if [ -n "$risk" ]; then
        local daily_loss=$(echo "$risk" | python3 -c "import sys, json; print(json.load(sys.stdin).get('daily_loss_percent', 0))" 2>/dev/null || echo "0")
        if (( $(echo "$daily_loss >= 4" | bc -l 2>/dev/null || echo "0") )); then
            echo -e "  ${RED}WARNING: Daily loss at ${daily_loss}% - approaching 5% limit!${NC}"
            alert "Daily loss at ${daily_loss}% - approaching emergency stop"
            ((alerts++))
        fi
    fi

    # Check for unhealthy services
    for service in "$TRADING_ENGINE" "$PORTFOLIO_MANAGER" "$MARKET_DATA"; do
        if ! curl -s -o /dev/null -w "%{http_code}" "$service/health" 2>/dev/null | grep -q "200"; then
            ((alerts++))
        fi
    done

    if [ $alerts -eq 0 ]; then
        echo -e "  ${GREEN}All systems normal${NC}"
    else
        echo -e "  ${YELLOW}$alerts alert(s) detected${NC}"
    fi
    echo ""
}

# Main monitoring function
main() {
    clear
    print_header

    check_all_services
    get_trading_status
    get_positions
    get_portfolio_summary
    get_daily_stats
    get_recent_trades
    get_risk_utilization
    check_alerts

    echo -e "${CYAN}=============================================================================="
    echo -e "  Press Ctrl+C to exit | Refreshing every 30 seconds"
    echo -e "==============================================================================${NC}"
}

# Continuous monitoring mode
if [ "$1" == "--continuous" ] || [ "$1" == "-c" ]; then
    while true; do
        main
        sleep 30
    done
else
    main
fi
