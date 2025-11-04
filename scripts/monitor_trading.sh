#!/bin/bash
# Real-time Trading Bot Monitor
# Shows live updates of trading activity and portfolio status

PROJECT_ROOT="/mnt/d/Bimo_max/crypto-trading-bot"
cd "$PROJECT_ROOT"

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║        CRYPTO TRADING BOT - REAL-TIME MONITOR               ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Function to check service health
check_services() {
    echo -e "${YELLOW}━━━ SERVICE HEALTH ━━━${NC}"
    for port in 8000 8002 8003 8004 8005 8006; do
        status=$(curl -s http://localhost:$port/health 2>/dev/null | jq -r '.status // "DOWN"')
        if [ "$status" = "healthy" ]; then
            echo -e "  Port $port: ${GREEN}✓ HEALTHY${NC}"
        else
            echo -e "  Port $port: ${RED}✗ DOWN${NC}"
        fi
    done
    echo ""
}

# Function to show portfolio
show_portfolio() {
    echo -e "${YELLOW}━━━ PORTFOLIO STATUS ━━━${NC}"
    portfolio=$(curl -s "http://localhost:8000/api/portfolio" 2>/dev/null)

    if [ $? -eq 0 ]; then
        cash=$(echo "$portfolio" | jq -r '.portfolio.cash_balance // "0"')
        total=$(echo "$portfolio" | jq -r '.portfolio.total_value // "0"')
        pnl=$(echo "$portfolio" | jq -r '.portfolio.total_pnl // "0"')
        holdings=$(echo "$portfolio" | jq -r '.portfolio.holdings | length')

        echo -e "  Cash Balance:    ${GREEN}\$$cash${NC}"
        echo -e "  Total Value:     ${CYAN}\$$total${NC}"
        echo -e "  Total P&L:       ${GREEN}\$$pnl${NC}"
        echo -e "  Holdings:        ${CYAN}$holdings positions${NC}"
    else
        echo -e "  ${RED}Unable to fetch portfolio${NC}"
    fi
    echo ""
}

# Function to show recent trades
show_recent_trades() {
    echo -e "${YELLOW}━━━ RECENT TRADES (Last 5) ━━━${NC}"
    if [ -f "logs/trades.jsonl" ]; then
        tail -5 logs/trades.jsonl | while read -r line; do
            symbol=$(echo "$line" | jq -r '.symbol')
            action=$(echo "$line" | jq -r '.action')
            quantity=$(echo "$line" | jq -r '.quantity')
            price=$(echo "$line" | jq -r '.price')
            timestamp=$(echo "$line" | jq -r '.timestamp' | cut -d'T' -f2 | cut -d'.' -f1)

            if [ "$action" = "BUY" ]; then
                color=$GREEN
            else
                color=$RED
            fi

            echo -e "  [$timestamp] ${color}$action${NC} $quantity $symbol @ \$$price"
        done
    else
        echo -e "  ${CYAN}No trades yet${NC}"
    fi
    echo ""
}

# Function to show trading bot stats
show_bot_stats() {
    echo -e "${YELLOW}━━━ TRADING BOT STATUS ━━━${NC}"

    # Check if trading bot is running
    if pgrep -f "automated_trading_loop.py" > /dev/null; then
        pid=$(pgrep -f "automated_trading_loop.py")
        echo -e "  Status:          ${GREEN}✓ RUNNING${NC} (PID: $pid)"

        # Get last few log lines
        latest_log=$(find logs -name "trading_session_*.log" -type f -printf '%T@ %p\n' | sort -n | tail -1 | cut -d' ' -f2-)
        if [ -n "$latest_log" ]; then
            last_cycle=$(grep "Starting trading cycle" "$latest_log" | tail -1 | awk '{print $1, $2}')
            echo -e "  Last Cycle:      ${CYAN}$last_cycle${NC}"

            trades_today=$(grep "Trades today:" "$latest_log" | tail -1 | awk -F':' '{print $NF}' | xargs)
            if [ -n "$trades_today" ]; then
                echo -e "  Trades Today:    ${CYAN}$trades_today${NC}"
            fi
        fi
    else
        echo -e "  Status:          ${RED}✗ NOT RUNNING${NC}"
        echo -e "  ${YELLOW}Run: python3 scripts/automated_trading_loop.py${NC}"
    fi
    echo ""
}

# Function to show current signals
show_signals() {
    echo -e "${YELLOW}━━━ CURRENT TRADING SIGNALS ━━━${NC}"
    for symbol in "BTCUSDT" "ETHUSDT" "BNBUSDT"; do
        signal=$(curl -s "http://localhost:8000/api/trading/signals/$symbol?interval=60" 2>/dev/null)
        if [ $? -eq 0 ]; then
            action=$(echo "$signal" | jq -r '.signal.action // "N/A"')
            confidence=$(echo "$signal" | jq -r '.signal.confidence // 0')
            confidence_pct=$(echo "$confidence * 100" | bc)

            case $action in
                "BUY")
                    color=$GREEN
                    ;;
                "SELL")
                    color=$RED
                    ;;
                *)
                    color=$CYAN
                    ;;
            esac

            echo -e "  $symbol: ${color}$action${NC} (confidence: ${confidence_pct}%)"
        fi
    done
    echo ""
}

# Main monitoring loop
if [ "$1" = "--watch" ]; then
    # Continuous monitoring mode
    while true; do
        clear
        echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${BLUE}║        CRYPTO TRADING BOT - REAL-TIME MONITOR               ║${NC}"
        echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
        echo -e "${CYAN}Updated: $(date '+%Y-%m-%d %H:%M:%S')${NC}"
        echo ""

        check_services
        show_bot_stats
        show_portfolio
        show_signals
        show_recent_trades

        echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${CYAN}Press Ctrl+C to exit monitoring${NC}"

        sleep 5
    done
else
    # One-time snapshot
    check_services
    show_bot_stats
    show_portfolio
    show_signals
    show_recent_trades

    echo -e "${CYAN}For continuous monitoring, run: $0 --watch${NC}"
    echo ""
fi
