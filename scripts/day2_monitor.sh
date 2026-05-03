#!/bin/bash
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# =============================================================================
# Day 2 Paper Trading Monitoring Dashboard
# Purpose: Comprehensive monitoring for Day 2 of paper trading validation
# Created: 2025-12-12
# Usage: ./scripts/day2_monitor.sh [--continuous]
# =============================================================================

set -e

# Configuration
PROJECT_DIR="${PROJECT_ROOT}"
LOG_FILE="$PROJECT_DIR/logs/day2_monitor.log"

# Service endpoints
TRADING_ENGINE="http://localhost:8005"
PORTFOLIO_MANAGER="http://localhost:8003"
MARKET_DATA="http://localhost:8002"
NOTIFICATION="http://localhost:8006"
RISK_METRICS="http://localhost:8009"
TECHNICAL_ANALYSIS="http://localhost:8004"
ML_PREDICTION="http://localhost:8007"

# Parse arguments
CONTINUOUS=false
if [ "$1" == "--continuous" ] || [ "$1" == "-c" ]; then
    CONTINUOUS=true
fi

# Timestamp function
timestamp() {
    date "+%Y-%m-%d %H:%M:%S UTC"
}

# Log function
log() {
    echo "[$(timestamp)] $1" >> "$LOG_FILE"
}

# Main dashboard display
display_dashboard() {
    clear
    echo "================================================================="
    echo "       DAY 2 PAPER TRADING MONITORING DASHBOARD"
    echo "================================================================="
    echo "Date: $(timestamp)"
    echo "Mode: Paper Trading | Strategy: SQZMOM"
    echo ""

    # =================================================================
    # SECTION 1: SYSTEM HEALTH
    # =================================================================
    echo "=== SYSTEM HEALTH ==="

    # Check container health via docker
    if command -v docker &> /dev/null; then
        healthy=$(docker ps --filter "health=healthy" --format "{{.Names}}" 2>/dev/null | wc -l)
        unhealthy=$(docker ps --filter "health=unhealthy" --format "{{.Names}}" 2>/dev/null | wc -l)
        total=$(docker ps --format "{{.Names}}" 2>/dev/null | wc -l)

        if [ "$unhealthy" -gt 0 ]; then
            echo "WARNING: $unhealthy container(s) unhealthy!"
            docker ps --filter "health=unhealthy" --format "  - {{.Names}}: {{.Status}}" 2>/dev/null
        else
            echo "Containers: $healthy/$total healthy"
        fi
    fi

    # Service health checks
    services_ok=0
    services_total=0

    for svc in "Trading Engine:$TRADING_ENGINE" "Portfolio:$PORTFOLIO_MANAGER" "Market Data:$MARKET_DATA" "TA Service:$TECHNICAL_ANALYSIS" "ML Prediction:$ML_PREDICTION" "Risk Metrics:$RISK_METRICS" "Notifications:$NOTIFICATION"; do
        name=$(echo "$svc" | cut -d: -f1)
        url=$(echo "$svc" | cut -d: -f2-)
        ((services_total++))

        response=$(curl -s -o /dev/null -w "%{http_code}" "$url/health" 2>/dev/null || echo "000")
        if [ "$response" == "200" ]; then
            ((services_ok++))
        else
            echo "  [FAIL] $name (HTTP $response)"
        fi
    done

    echo "Services: $services_ok/$services_total healthy"
    echo ""

    # =================================================================
    # SECTION 2: TRADING STATUS
    # =================================================================
    echo "=== TRADING STATUS ==="

    # Get trading engine status
    status=$(curl -s "$TRADING_ENGINE/api/v1/status" 2>/dev/null)
    if [ -n "$status" ]; then
        echo "$status" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(f'  Mode: {data.get(\"mode\", \"N/A\")}')
    print(f'  Strategy: {data.get(\"strategy\", \"N/A\")}')
    print(f'  Auto Trading: {data.get(\"auto_trading_enabled\", \"N/A\")}')
    symbols = data.get('active_symbols', [])
    print(f'  Active Symbols: {len(symbols)}')
except Exception as e:
    print(f'  Unable to parse status: {e}')
" 2>/dev/null
    else
        echo "  Unable to fetch trading status"
    fi
    echo ""

    # =================================================================
    # SECTION 3: PORTFOLIO SUMMARY
    # =================================================================
    echo "=== PORTFOLIO SUMMARY ==="

    portfolio=$(curl -s "$PORTFOLIO_MANAGER/api/v1/portfolio/status" 2>/dev/null)
    if [ -n "$portfolio" ]; then
        echo "$portfolio" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)

    # Handle different response structures
    if 'balance' in data:
        balance = data.get('balance', {})
        total = balance.get('total', 0)
        available = balance.get('available', 0)
    else:
        total = data.get('equity', data.get('total_equity', 10000))
        available = data.get('available_balance', total)

    pnl = data.get('total_pnl', data.get('realized_pnl', 0))
    unrealized = data.get('unrealized_pnl', 0)

    # Color codes
    pnl_color = '\033[92m' if pnl >= 0 else '\033[91m'
    ur_color = '\033[92m' if unrealized >= 0 else '\033[91m'
    reset = '\033[0m'

    pnl_pct = (pnl / 10000) * 100 if total != 0 else 0

    print(f'  Equity: \${total:.2f}')
    print(f'  Available: \${available:.2f}')
    print(f'  Total P&L: {pnl_color}\${pnl:.2f} ({pnl_pct:.2f}%){reset}')
    print(f'  Unrealized: {ur_color}\${unrealized:.2f}{reset}')
except Exception as e:
    print(f'  Unable to parse portfolio: {e}')
" 2>/dev/null
    else
        echo "  Unable to fetch portfolio"
    fi
    echo ""

    # =================================================================
    # SECTION 4: TODAY'S PERFORMANCE
    # =================================================================
    echo "=== TODAY'S PERFORMANCE ==="

    # Try to get from trading engine
    daily=$(curl -s "$TRADING_ENGINE/api/v1/performance/daily" 2>/dev/null)
    if [ -n "$daily" ] && [ "$daily" != "null" ]; then
        echo "$daily" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    trades = data.get('total_trades', data.get('trades_count', 0))
    wins = data.get('winning_trades', data.get('wins', 0))
    losses = data.get('losing_trades', data.get('losses', 0))
    win_rate = data.get('win_rate', 0)
    pnl = data.get('daily_pnl', data.get('pnl', 0))

    if trades > 0 and win_rate == 0:
        win_rate = (wins / trades) * 100

    pnl_color = '\033[92m' if pnl >= 0 else '\033[91m'
    reset = '\033[0m'

    print(f'  Trades Today: {trades}')
    print(f'  Wins/Losses: {wins}/{losses}')
    print(f'  Win Rate: {win_rate:.1f}%')
    print(f'  Daily P&L: {pnl_color}\${pnl:.2f}{reset}')
except Exception as e:
    print(f'  Trades Today: 0')
    print(f'  Daily P&L: \$0.00')
" 2>/dev/null
    else
        # Try database query if available
        if command -v docker &> /dev/null; then
            result=$(docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -t -A -c "
                SELECT
                    COUNT(*) as trades,
                    COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0) as wins,
                    COALESCE(ROUND(SUM(pnl)::numeric, 2), 0) as pnl
                FROM trades
                WHERE DATE(created_at) = CURRENT_DATE;
            " 2>/dev/null || echo "0|0|0")

            trades=$(echo "$result" | cut -d'|' -f1)
            wins=$(echo "$result" | cut -d'|' -f2)
            pnl=$(echo "$result" | cut -d'|' -f3)

            if [ -n "$trades" ] && [ "$trades" != "0" ]; then
                win_rate=$(echo "scale=1; ($wins / $trades) * 100" | bc 2>/dev/null || echo "0")
            else
                win_rate="0.0"
                trades="0"
                pnl="0.00"
            fi

            echo "  Trades Today: $trades"
            echo "  Wins: $wins"
            echo "  Win Rate: $win_rate%"
            echo "  Daily P&L: \$$pnl"
        else
            echo "  Trades Today: N/A (database not accessible)"
        fi
    fi
    echo ""

    # =================================================================
    # SECTION 5: OPEN POSITIONS
    # =================================================================
    echo "=== OPEN POSITIONS ==="

    positions=$(curl -s "$PORTFOLIO_MANAGER/api/v1/positions" 2>/dev/null)
    if [ -n "$positions" ]; then
        echo "$positions" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    positions = data.get('positions', data) if isinstance(data, dict) else data

    if not positions or len(positions) == 0:
        print('  No open positions')
    else:
        for p in positions:
            symbol = p.get('symbol', 'N/A')
            side = p.get('side', 'N/A')
            size = p.get('size', p.get('quantity', 0))
            entry = p.get('entry_price', p.get('avg_entry_price', 0))
            current = p.get('current_price', p.get('mark_price', entry))
            pnl = p.get('unrealized_pnl', p.get('pnl', 0))

            color = '\033[92m' if pnl >= 0 else '\033[91m'
            reset = '\033[0m'

            print(f'  {symbol}: {side} | Entry: \${entry:.4f} | P&L: {color}\${pnl:.2f}{reset}')
except Exception as e:
    print(f'  Unable to parse positions: {e}')
" 2>/dev/null
    else
        echo "  Unable to fetch positions"
    fi
    echo ""

    # =================================================================
    # SECTION 6: RISK STATUS
    # =================================================================
    echo "=== RISK STATUS ==="

    risk=$(curl -s "$RISK_METRICS/api/v1/risk/current" 2>/dev/null)
    if [ -n "$risk" ]; then
        echo "$risk" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    daily_loss = data.get('daily_loss_percent', data.get('daily_drawdown', 0))
    exposure = data.get('total_exposure_percent', data.get('exposure_pct', 0))
    max_daily = data.get('max_daily_loss_percent', 5)
    max_exposure = data.get('max_exposure_percent', 70)

    # Color coding
    daily_color = '\033[92m' if daily_loss < max_daily * 0.5 else '\033[93m' if daily_loss < max_daily * 0.8 else '\033[91m'
    exp_color = '\033[92m' if exposure < max_exposure * 0.5 else '\033[93m' if exposure < max_exposure * 0.8 else '\033[91m'
    reset = '\033[0m'

    print(f'  Daily Loss: {daily_color}{daily_loss:.2f}% / {max_daily}%{reset}')
    print(f'  Exposure: {exp_color}{exposure:.2f}% / {max_exposure}%{reset}')

    if daily_loss >= max_daily * 0.8:
        print(f'  \033[91mWARNING: Approaching daily loss limit!\033[0m')
except Exception as e:
    print(f'  Unable to parse risk data: {e}')
" 2>/dev/null
    else
        echo "  Unable to fetch risk metrics"
    fi

    # Also check risk budget
    budget=$(curl -s "$TRADING_ENGINE/api/v1/risk/budget/current" 2>/dev/null)
    if [ -n "$budget" ] && [ "$budget" != "null" ]; then
        echo "$budget" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    current = data.get('current_budget', data.get('budget', 0))
    used = data.get('used_budget', data.get('used', 0))
    util = data.get('utilization_pct', 0)

    if current > 0 and util == 0:
        util = (used / current) * 100

    print(f'  Risk Budget: \${current:.2f}')
    print(f'  Budget Used: \${used:.2f} ({util:.1f}%)')
except:
    pass
" 2>/dev/null
    fi
    echo ""

    # =================================================================
    # SECTION 7: SIGNAL ACTIVITY
    # =================================================================
    echo "=== SIGNAL ACTIVITY (Last Hour) ==="

    if command -v docker &> /dev/null; then
        signals=$(docker logs crypto-bot-trading --since "1h" 2>&1 | grep -ci "signal" || echo "0")
        executed=$(docker logs crypto-bot-trading --since "1h" 2>&1 | grep -ci "executed\|opened\|entry" || echo "0")
        rejected=$(docker logs crypto-bot-trading --since "1h" 2>&1 | grep -ci "rejected\|skipped\|blocked" || echo "0")

        echo "  Signals Generated: $signals"
        echo "  Trades Executed: $executed"
        echo "  Signals Rejected: $rejected"
    else
        echo "  Docker not available for log analysis"
    fi
    echo ""

    # =================================================================
    # SECTION 8: RECENT TRADES
    # =================================================================
    echo "=== RECENT TRADES (Last 5) ==="

    trades=$(curl -s "$PORTFOLIO_MANAGER/api/v1/trades?limit=5" 2>/dev/null)
    if [ -n "$trades" ]; then
        echo "$trades" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    trades = data.get('trades', data) if isinstance(data, dict) else data

    if not trades or len(trades) == 0:
        print('  No recent trades')
    else:
        for t in trades[:5]:
            symbol = t.get('symbol', 'N/A')
            side = t.get('side', 'N/A')
            pnl = t.get('pnl', t.get('realized_pnl', 0))
            time = t.get('timestamp', t.get('exit_time', 'N/A'))
            if time and len(time) > 16:
                time = time[11:16]  # Extract HH:MM

            color = '\033[92m' if pnl >= 0 else '\033[91m'
            reset = '\033[0m'

            print(f'  [{time}] {symbol} {side}: {color}\${pnl:.2f}{reset}')
except Exception as e:
    print(f'  Unable to parse trades: {e}')
" 2>/dev/null
    else
        # Try database
        if command -v docker &> /dev/null; then
            docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -t -c "
                SELECT
                    symbol,
                    side,
                    ROUND(pnl::numeric, 2) as pnl,
                    TO_CHAR(exit_time, 'HH24:MI') as time
                FROM trades
                WHERE exit_time IS NOT NULL
                ORDER BY exit_time DESC
                LIMIT 5;
            " 2>/dev/null | while read line; do
                if [ -n "$line" ]; then
                    echo "  $line"
                fi
            done
        fi
    fi
    echo ""

    # =================================================================
    # SECTION 9: ALERT STATUS
    # =================================================================
    echo "=== ALERT STATUS ==="

    # Check notification service
    notif_health=$(curl -s -o /dev/null -w "%{http_code}" "$NOTIFICATION/health" 2>/dev/null || echo "000")
    if [ "$notif_health" == "200" ]; then
        echo "  Notification Service: ONLINE"
    else
        echo "  Notification Service: OFFLINE (HTTP $notif_health)"
    fi

    # Count alerts in last hour
    if command -v docker &> /dev/null; then
        alerts=$(docker logs crypto-bot-notification --since "1h" 2>&1 | grep -ci "alert\|sent\|notification" || echo "0")
        echo "  Alerts (Last Hour): $alerts"
    fi
    echo ""

    # =================================================================
    # SECTION 10: COMPARISON VS DAY 1
    # =================================================================
    echo "=== DAY 2 VS DAY 1 COMPARISON ==="

    if command -v docker &> /dev/null; then
        comparison=$(docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -t -A -c "
            WITH daily AS (
                SELECT
                    DATE(created_at) as date,
                    COUNT(*) as trades,
                    COALESCE(ROUND(SUM(pnl)::numeric, 2), 0) as pnl,
                    ROUND(AVG(CASE WHEN pnl > 0 THEN 1.0 ELSE 0.0 END) * 100, 1) as win_rate
                FROM trades
                WHERE DATE(created_at) >= CURRENT_DATE - 1
                GROUP BY DATE(created_at)
                ORDER BY date
            )
            SELECT * FROM daily;
        " 2>/dev/null)

        if [ -n "$comparison" ]; then
            echo "  Date       | Trades | P&L     | Win Rate"
            echo "  -----------|--------|---------|----------"
            echo "$comparison" | while IFS='|' read date trades pnl win_rate; do
                if [ -n "$date" ]; then
                    printf "  %-10s | %-6s | \$%-6s | %s%%\n" "$date" "$trades" "$pnl" "$win_rate"
                fi
            done
        else
            echo "  No comparison data available yet"
        fi
    fi
    echo ""

    echo "================================================================="
    if [ "$CONTINUOUS" = true ]; then
        echo "  Refreshing every 30 seconds... (Ctrl+C to stop)"
    fi
    echo "================================================================="
}

# Main execution
if [ "$CONTINUOUS" = true ]; then
    while true; do
        display_dashboard
        log "Dashboard refreshed"
        sleep 30
    done
else
    display_dashboard
fi
