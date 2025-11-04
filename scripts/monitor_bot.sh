#!/bin/bash
# Real-time monitoring dashboard for the trading bot

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

clear

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║        🤖 CRYPTO TRADING BOT - LIVE MONITOR                 ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if bot is running
if ps aux | grep -q "[a]utomated_trading_loop.py"; then
    BOT_PID=$(ps aux | grep "[a]utomated_trading_loop.py" | awk '{print $2}')
    echo -e "${GREEN}✅ Trading Bot Status: RUNNING (PID: $BOT_PID)${NC}"
else
    echo -e "${RED}❌ Trading Bot Status: NOT RUNNING${NC}"
    echo ""
    echo "To start the bot:"
    echo "  nohup python3 scripts/automated_trading_loop.py > logs/trading_bot.log 2>&1 &"
    exit 1
fi

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}📊 PORTFOLIO STATUS${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Get portfolio status
PORTFOLIO=$(curl -s http://localhost:8000/api/portfolio 2>/dev/null)

if [ $? -eq 0 ]; then
    CASH=$(echo $PORTFOLIO | python3 -c "import sys, json; print(json.load(sys.stdin)['portfolio']['cash_balance'])" 2>/dev/null)
    TOTAL_VALUE=$(echo $PORTFOLIO | python3 -c "import sys, json; print(json.load(sys.stdin)['portfolio']['total_value'])" 2>/dev/null)
    PNL=$(echo $PORTFOLIO | python3 -c "import sys, json; print(json.load(sys.stdin)['portfolio']['total_pnl'])" 2>/dev/null)
    HOLDINGS=$(echo $PORTFOLIO | python3 -c "import sys, json; print(len(json.load(sys.stdin)['portfolio']['holdings']))" 2>/dev/null)

    echo "  💰 Cash Balance:    \$$CASH"
    echo "  📈 Total Value:     \$$TOTAL_VALUE"
    echo "  📊 Total P&L:       \$$PNL"
    echo "  🔢 Open Positions:  $HOLDINGS"
else
    echo -e "${RED}  ⚠️  Unable to fetch portfolio (check if services are running)${NC}"
fi

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}📝 RECENT TRADING ACTIVITY (Last 10 lines)${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if [ -f logs/trading_bot.log ]; then
    tail -10 logs/trading_bot.log | grep -E "(INFO|WARNING|ERROR)" | sed 's/^/  /'
else
    echo -e "${RED}  No log file found${NC}"
fi

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}🔄 SERVICES STATUS${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Check services
check_service() {
    local name=$1
    local port=$2

    if nc -z localhost $port 2>/dev/null; then
        echo -e "  ${GREEN}✅${NC} $name (Port $port)"
    else
        echo -e "  ${RED}❌${NC} $name (Port $port)"
    fi
}

check_service "API Gateway      " 8000
check_service "Bybit Connector  " 8002
check_service "Market Data      " 8003
check_service "Technical Analysis" 8004
check_service "Trading Engine   " 8005
check_service "Portfolio Manager" 8006

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}📈 TRADE HISTORY${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if [ -f logs/trades.jsonl ] && [ -s logs/trades.jsonl ]; then
    TRADE_COUNT=$(wc -l < logs/trades.jsonl)
    echo "  Total Trades Executed: $TRADE_COUNT"
    echo ""
    echo "  Recent Trades:"
    tail -5 logs/trades.jsonl | python3 -c "
import sys, json
for line in sys.stdin:
    trade = json.loads(line)
    print(f\"    {trade['timestamp'][:19]} | {trade['action']:4s} {trade['quantity']:.4f} {trade['symbol']:8s} @ \${trade['price']:.2f}\")
" 2>/dev/null
else
    echo "  No trades executed yet. Bot is analyzing..."
fi

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${BLUE}💡 Commands:${NC}"
echo "  • Monitor live logs:     tail -f logs/trading_bot.log"
echo "  • Check portfolio:       curl http://localhost:8000/api/portfolio | python3 -m json.tool"
echo "  • Daily report:          python3 scripts/daily_report.py"
echo "  • Stop bot:              kill -SIGTERM $BOT_PID"
echo "  • Refresh this view:     bash scripts/monitor_bot.sh"
echo ""
echo -e "${GREEN}System is operational. Press Ctrl+C to exit.${NC}"
