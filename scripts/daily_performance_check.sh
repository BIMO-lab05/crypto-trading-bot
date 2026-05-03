#!/bin/bash
# Daily Performance Check Script
# Analyzes trading bot performance and generates a summary report

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

DATE=$(date +%Y-%m-%d)
REPORT_FILE="logs/daily_reports/performance_$DATE.txt"

mkdir -p logs/daily_reports

echo "╔══════════════════════════════════════════════════════════════╗" > "$REPORT_FILE"
echo "║     CRYPTO TRADING BOT - DAILY PERFORMANCE REPORT           ║" >> "$REPORT_FILE"
echo "╚══════════════════════════════════════════════════════════════╝" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "Report Date: $DATE" >> "$REPORT_FILE"
echo "Generated: $(date '+%Y-%m-%d %H:%M:%S')" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# Check if bot is running
if pgrep -f "automated_trading_loop.py" > /dev/null; then
    BOT_STATUS="✅ RUNNING"
    BOT_PID=$(pgrep -f "automated_trading_loop.py")
else
    BOT_STATUS="❌ STOPPED"
    BOT_PID="N/A"
fi

echo "════════════════════════════════════════════════════════════════" >> "$REPORT_FILE"
echo "SYSTEM STATUS" >> "$REPORT_FILE"
echo "════════════════════════════════════════════════════════════════" >> "$REPORT_FILE"
echo "Trading Bot: $BOT_STATUS (PID: $BOT_PID)" >> "$REPORT_FILE"

# Count running services
SERVICE_COUNT=$(ps aux | grep "uvicorn app.main:app" | grep -v grep | wc -l)
echo "Services Running: $SERVICE_COUNT/6" >> "$REPORT_FILE"

# Check frontend
if pgrep -f "npm run dev" > /dev/null; then
    echo "Frontend: ✅ RUNNING" >> "$REPORT_FILE"
else
    echo "Frontend: ❌ STOPPED" >> "$REPORT_FILE"
fi

echo "" >> "$REPORT_FILE"

# Get portfolio status
echo "════════════════════════════════════════════════════════════════" >> "$REPORT_FILE"
echo "PORTFOLIO STATUS" >> "$REPORT_FILE"
echo "════════════════════════════════════════════════════════════════" >> "$REPORT_FILE"

PORTFOLIO=$(curl -s "http://localhost:8000/api/portfolio" 2>/dev/null)
if [ $? -eq 0 ]; then
    CASH=$(echo "$PORTFOLIO" | python3 -c "import sys, json; print(json.load(sys.stdin)['portfolio']['cash_balance'])" 2>/dev/null || echo "N/A")
    TOTAL_VALUE=$(echo "$PORTFOLIO" | python3 -c "import sys, json; print(json.load(sys.stdin)['portfolio']['total_value'])" 2>/dev/null || echo "N/A")
    TOTAL_PNL=$(echo "$PORTFOLIO" | python3 -c "import sys, json; print(json.load(sys.stdin)['portfolio']['total_pnl'])" 2>/dev/null || echo "N/A")
    HOLDINGS_COUNT=$(echo "$PORTFOLIO" | python3 -c "import sys, json; print(len(json.load(sys.stdin)['portfolio']['holdings']))" 2>/dev/null || echo "0")

    echo "Cash Balance: \$$CASH" >> "$REPORT_FILE"
    echo "Total Portfolio Value: \$$TOTAL_VALUE" >> "$REPORT_FILE"
    echo "Total P&L: \$$TOTAL_PNL" >> "$REPORT_FILE"
    echo "Open Positions: $HOLDINGS_COUNT" >> "$REPORT_FILE"
else
    echo "❌ Unable to fetch portfolio data" >> "$REPORT_FILE"
fi

echo "" >> "$REPORT_FILE"

# Count trades
echo "════════════════════════════════════════════════════════════════" >> "$REPORT_FILE"
echo "TRADING ACTIVITY" >> "$REPORT_FILE"
echo "════════════════════════════════════════════════════════════════" >> "$REPORT_FILE"

if [ -f "logs/trades.jsonl" ]; then
    TOTAL_TRADES=$(wc -l < logs/trades.jsonl)
    TODAY_TRADES=$(grep "$(date +%Y-%m-%d)" logs/trades.jsonl 2>/dev/null | wc -l)

    echo "Total Trades (All Time): $TOTAL_TRADES" >> "$REPORT_FILE"
    echo "Trades Today: $TODAY_TRADES" >> "$REPORT_FILE"

    # Count buy vs sell
    if [ "$TOTAL_TRADES" -gt 0 ]; then
        BUY_COUNT=$(grep -o '"action":"BUY"' logs/trades.jsonl | wc -l)
        SELL_COUNT=$(grep -o '"action":"SELL"' logs/trades.jsonl | wc -l)
        echo "Total Buys: $BUY_COUNT" >> "$REPORT_FILE"
        echo "Total Sells: $SELL_COUNT" >> "$REPORT_FILE"
    fi

    # Show recent trades
    if [ "$TOTAL_TRADES" -gt 0 ]; then
        echo "" >> "$REPORT_FILE"
        echo "Recent Trades (Last 5):" >> "$REPORT_FILE"
        echo "----------------------------------------" >> "$REPORT_FILE"
        tail -5 logs/trades.jsonl | while read -r line; do
            TIMESTAMP=$(echo "$line" | python3 -c "import sys, json; print(json.load(sys.stdin)['timestamp'][:19])" 2>/dev/null || echo "N/A")
            ACTION=$(echo "$line" | python3 -c "import sys, json; print(json.load(sys.stdin)['action'])" 2>/dev/null || echo "N/A")
            SYMBOL=$(echo "$line" | python3 -c "import sys, json; print(json.load(sys.stdin)['symbol'])" 2>/dev/null || echo "N/A")
            QUANTITY=$(echo "$line" | python3 -c "import sys, json; print(json.load(sys.stdin)['quantity'])" 2>/dev/null || echo "N/A")
            PRICE=$(echo "$line" | python3 -c "import sys, json; print(json.load(sys.stdin)['price'])" 2>/dev/null || echo "N/A")

            echo "[$TIMESTAMP] $ACTION $QUANTITY $SYMBOL @ \$$PRICE" >> "$REPORT_FILE"
        done
    fi
else
    echo "No trades executed yet" >> "$REPORT_FILE"
fi

echo "" >> "$REPORT_FILE"

# Check logs for errors
echo "════════════════════════════════════════════════════════════════" >> "$REPORT_FILE"
echo "ERROR SUMMARY" >> "$REPORT_FILE"
echo "════════════════════════════════════════════════════════════════" >> "$REPORT_FILE"

LATEST_LOG=$(find logs -name "trading_session_*.log" -type f -printf '%T@ %p\n' | sort -n | tail -1 | cut -d' ' -f2-)
if [ -n "$LATEST_LOG" ]; then
    ERROR_COUNT=$(grep -i "error" "$LATEST_LOG" 2>/dev/null | wc -l)
    WARNING_COUNT=$(grep -i "warning" "$LATEST_LOG" 2>/dev/null | wc -l)

    echo "Errors Today: $ERROR_COUNT" >> "$REPORT_FILE"
    echo "Warnings Today: $WARNING_COUNT" >> "$REPORT_FILE"

    if [ "$ERROR_COUNT" -gt 0 ]; then
        echo "" >> "$REPORT_FILE"
        echo "Recent Errors:" >> "$REPORT_FILE"
        grep -i "error" "$LATEST_LOG" 2>/dev/null | tail -3 >> "$REPORT_FILE"
    fi
else
    echo "No log file found" >> "$REPORT_FILE"
fi

echo "" >> "$REPORT_FILE"

# Current signals
echo "════════════════════════════════════════════════════════════════" >> "$REPORT_FILE"
echo "CURRENT TRADING SIGNALS" >> "$REPORT_FILE"
echo "════════════════════════════════════════════════════════════════" >> "$REPORT_FILE"

for SYMBOL in "BTCUSDT" "ETHUSDT" "BNBUSDT"; do
    SIGNAL=$(curl -s "http://localhost:8000/api/trading/signals/$SYMBOL?interval=60" 2>/dev/null)
    if [ $? -eq 0 ]; then
        ACTION=$(echo "$SIGNAL" | python3 -c "import sys, json; print(json.load(sys.stdin)['signal']['action'])" 2>/dev/null || echo "N/A")
        CONFIDENCE=$(echo "$SIGNAL" | python3 -c "import sys, json; c=json.load(sys.stdin)['signal']['confidence']; print(f'{c*100:.1f}%')" 2>/dev/null || echo "N/A")
        echo "$SYMBOL: $ACTION (Confidence: $CONFIDENCE)" >> "$REPORT_FILE"
    fi
done

echo "" >> "$REPORT_FILE"

# Performance metrics
echo "════════════════════════════════════════════════════════════════" >> "$REPORT_FILE"
echo "PERFORMANCE METRICS" >> "$REPORT_FILE"
echo "════════════════════════════════════════════════════════════════" >> "$REPORT_FILE"

PERFORMANCE=$(curl -s "http://localhost:8000/api/portfolio/performance" 2>/dev/null)
if [ $? -eq 0 ]; then
    SHARPE=$(echo "$PERFORMANCE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('sharpe_ratio', 'N/A'))" 2>/dev/null || echo "N/A")
    MAX_DD=$(echo "$PERFORMANCE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('max_drawdown', 'N/A'))" 2>/dev/null || echo "N/A")
    WIN_RATE=$(echo "$PERFORMANCE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('win_rate', 'N/A'))" 2>/dev/null || echo "N/A")

    echo "Sharpe Ratio: $SHARPE" >> "$REPORT_FILE"
    echo "Max Drawdown: $MAX_DD" >> "$REPORT_FILE"
    echo "Win Rate: $WIN_RATE" >> "$REPORT_FILE"
else
    echo "Performance metrics not available" >> "$REPORT_FILE"
fi

echo "" >> "$REPORT_FILE"

# Recommendations
echo "════════════════════════════════════════════════════════════════" >> "$REPORT_FILE"
echo "RECOMMENDATIONS" >> "$REPORT_FILE"
echo "════════════════════════════════════════════════════════════════" >> "$REPORT_FILE"

if [ "$BOT_STATUS" = "❌ STOPPED" ]; then
    echo "⚠️  Trading bot is not running. Start it to resume automated trading." >> "$REPORT_FILE"
fi

if [ "$SERVICE_COUNT" -lt 6 ]; then
    echo "⚠️  Some services are not running. Check system status." >> "$REPORT_FILE"
fi

if [ -f "logs/trades.jsonl" ] && [ "$TOTAL_TRADES" -eq 0 ]; then
    echo "ℹ️  No trades executed yet. This may be normal if signals are weak." >> "$REPORT_FILE"
fi

if [ "$ERROR_COUNT" -gt 10 ]; then
    echo "⚠️  High error count detected. Review logs for issues." >> "$REPORT_FILE"
fi

echo "" >> "$REPORT_FILE"
echo "════════════════════════════════════════════════════════════════" >> "$REPORT_FILE"
echo "END OF REPORT" >> "$REPORT_FILE"
echo "════════════════════════════════════════════════════════════════" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "Next Report: $(date -d '+1 day' +%Y-%m-%d)" >> "$REPORT_FILE"

# Display report to console
cat "$REPORT_FILE"

echo ""
echo -e "${GREEN}✅ Report saved to: $REPORT_FILE${NC}"
echo ""
echo "To view this report later:"
echo "  cat $REPORT_FILE"
echo ""
echo "To generate weekly summary:"
echo "  python3 scripts/weekly_summary.py"
