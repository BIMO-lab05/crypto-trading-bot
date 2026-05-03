#!/bin/bash
# Performance Monitoring & Alert Script
# Purpose: Monitor trading performance and alert on degradation
# Recommended: Run via cron every 6 hours
# Cron: 0 */6 * * * /path/to/performance_monitor.sh >> /var/log/performance_monitor.log 2>&1

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
# Project root resolves from script location (was hardcoded WSL path).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
DB_HOST="localhost"
DB_PORT="5432"
DB_USER="cryptobot"
DB_NAME="cryptobot"
LOG_FILE="${PROJECT_ROOT}/logs/performance_monitor.log"

# Thresholds
MIN_WIN_RATE=40.0          # Minimum acceptable win rate (%)
MIN_SYMBOL_WIN_RATE=30.0   # Minimum win rate per symbol (%)
MIN_TRADES_FOR_ANALYSIS=5  # Minimum trades needed to analyze a symbol
MAX_DAILY_LOSS=-50.0       # Maximum acceptable daily loss ($)
MIN_CONFIDENCE_TRACKED=50  # Minimum % of trades with confidence tracked

# Create log directory
mkdir -p "$(dirname "$LOG_FILE")"

# Function to log messages
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Function to send alert
send_alert() {
    local title="$1"
    local message="$2"
    local level="${3:-warning}"

    log_message "🚨 ALERT: $title - $message"

    # Send via notification service
    curl -s -X POST "http://localhost:8006/api/v1/notify/alert" \
        -H "Content-Type: application/json" \
        -d "{\"title\": \"$title\", \"message\": \"$message\", \"level\": \"$level\"}" \
        --max-time 5 > /dev/null 2>&1
}

# Function to query database
query_db() {
    docker exec crypto-bot-postgres psql -U "$DB_USER" -d "$DB_NAME" -t -c "$1" 2>/dev/null
}

# Function to check overall performance
check_overall_performance() {
    log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_message "Checking Overall Performance"
    log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Get overall statistics
    stats=$(query_db "
        SELECT
            COUNT(*) FILTER (WHERE status = 'CLOSED') as total_trades,
            COUNT(*) FILTER (WHERE status = 'CLOSED' AND realized_pnl > 0) as wins,
            ROUND((COUNT(*) FILTER (WHERE status = 'CLOSED' AND realized_pnl > 0)::numeric /
                   NULLIF(COUNT(*) FILTER (WHERE status = 'CLOSED'), 0)::numeric) * 100, 2) as win_rate,
            ROUND(COALESCE(SUM(realized_pnl) FILTER (WHERE status = 'CLOSED'), 0)::numeric, 2) as total_pnl
        FROM positions;
    ")

    read total_trades wins win_rate total_pnl <<< "$stats"

    log_message "Total Trades: $total_trades"
    log_message "Wins: $wins"
    log_message "Win Rate: ${win_rate}%"
    log_message "Total P&L: \$$total_pnl"

    # Check if win rate is below threshold
    if (( $(echo "$win_rate < $MIN_WIN_RATE" | bc -l) )); then
        send_alert "Low Win Rate Alert" \
            "Overall win rate (${win_rate}%) is below threshold (${MIN_WIN_RATE}%). Review strategy." \
            "warning"
    fi

    # Check if total P&L is negative and significant
    if (( $(echo "$total_pnl < -100" | bc -l) )); then
        send_alert "Significant Loss Alert" \
            "Total P&L is \$$total_pnl. Consider pausing trading and reviewing strategy." \
            "error"
    fi
}

# Function to check symbol performance
check_symbol_performance() {
    log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_message "Checking Symbol Performance"
    log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Get per-symbol statistics
    symbol_stats=$(query_db "
        SELECT
            symbol,
            COUNT(*) as trades,
            COUNT(*) FILTER (WHERE realized_pnl > 0) as wins,
            ROUND((COUNT(*) FILTER (WHERE realized_pnl > 0)::numeric / COUNT(*)::numeric) * 100, 1) as win_rate,
            ROUND(SUM(realized_pnl)::numeric, 2) as pnl
        FROM positions
        WHERE status = 'CLOSED'
        GROUP BY symbol
        HAVING COUNT(*) >= $MIN_TRADES_FOR_ANALYSIS
        ORDER BY win_rate ASC;
    ")

    echo "$symbol_stats" | while read line; do
        read symbol trades wins win_rate pnl <<< "$line"

        log_message "$symbol: $trades trades, ${win_rate}% win rate, \$$pnl P&L"

        # Alert on underperforming symbols
        if (( $(echo "$win_rate < $MIN_SYMBOL_WIN_RATE" | bc -l) )); then
            send_alert "Underperforming Symbol: $symbol" \
                "$symbol has ${win_rate}% win rate (${wins}/${trades} trades). Consider removing." \
                "warning"
        fi

        # Alert on symbols with significant losses
        if (( $(echo "$pnl < -50" | bc -l) )); then
            send_alert "Symbol Loss Alert: $symbol" \
                "$symbol has accumulated \$$pnl in losses. Review or disable." \
                "warning"
        fi
    done
}

# Function to check daily performance
check_daily_performance() {
    log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_message "Checking Daily Performance (Last 24h)"
    log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    daily_stats=$(query_db "
        SELECT
            COUNT(*) as trades,
            ROUND(COALESCE(SUM(realized_pnl), 0)::numeric, 2) as daily_pnl
        FROM positions
        WHERE status = 'CLOSED'
          AND updated_at > NOW() - INTERVAL '24 hours';
    ")

    read daily_trades daily_pnl <<< "$daily_stats"

    log_message "Trades (24h): $daily_trades"
    log_message "P&L (24h): \$$daily_pnl"

    # Alert on significant daily losses
    if (( $(echo "$daily_pnl < $MAX_DAILY_LOSS" | bc -l) )); then
        send_alert "High Daily Loss Alert" \
            "Daily P&L is \$$daily_pnl (threshold: \$$MAX_DAILY_LOSS). Consider reducing risk." \
            "error"
    fi
}

# Function to check entry confidence tracking
check_confidence_tracking() {
    log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_message "Checking Entry Confidence Tracking"
    log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    confidence_stats=$(query_db "
        SELECT
            COUNT(*) as total,
            COUNT(entry_signal_confidence) as with_confidence,
            ROUND((COUNT(entry_signal_confidence)::numeric / NULLIF(COUNT(*), 0)::numeric) * 100, 1) as pct_tracked
        FROM positions
        WHERE updated_at > NOW() - INTERVAL '7 days';
    ")

    read total with_confidence pct_tracked <<< "$confidence_stats"

    log_message "Recent positions (7d): $total"
    log_message "With confidence: $with_confidence (${pct_tracked}%)"

    # Alert if confidence tracking is low
    if (( $(echo "$pct_tracked < $MIN_CONFIDENCE_TRACKED" | bc -l) )) && [ "$total" -gt 5 ]; then
        send_alert "Low Confidence Tracking" \
            "Only ${pct_tracked}% of recent trades have confidence tracked. Expected >50%." \
            "warning"
    fi
}

# Function to check ML model freshness
check_model_freshness() {
    log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_message "Checking ML Model Freshness"
    log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Get model info for core symbols
    for symbol in "BTCUSDT" "BNBUSDT" "SOLUSDT" "ADAUSDT"; do
        model_data=$(curl -s --max-time 5 "http://localhost:8007/api/v1/predict/trend/${symbol}?interval=60" 2>/dev/null)

        if [ ! -z "$model_data" ]; then
            confidence=$(echo "$model_data" | python3 -c "import sys, json; print(f\"{json.load(sys.stdin).get('trend_confidence', 0)*100:.1f}\")" 2>/dev/null)

            log_message "$symbol: ${confidence}% confidence"

            # Alert on low model confidence
            if (( $(echo "$confidence < 40" | bc -l) )); then
                send_alert "Low ML Model Confidence: $symbol" \
                    "$symbol model confidence is only ${confidence}%. Consider retraining." \
                    "info"
            fi
        fi
    done
}

# Function to check for stuck positions
check_stuck_positions() {
    log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_message "Checking for Stuck Positions"
    log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    stuck_positions=$(query_db "
        SELECT
            symbol,
            side,
            ROUND(unrealized_pnl::numeric, 2) as pnl,
            EXTRACT(EPOCH FROM (NOW() - updated_at))/3600 as hours_open
        FROM positions
        WHERE status = 'OPEN'
          AND updated_at < NOW() - INTERVAL '48 hours'
        ORDER BY updated_at ASC;
    ")

    if [ ! -z "$stuck_positions" ]; then
        echo "$stuck_positions" | while read line; do
            read symbol side pnl hours_open <<< "$line"
            hours_int=$(printf "%.0f" "$hours_open")

            log_message "⚠️  $symbol $side open for ${hours_int}h, P&L: \$$pnl"

            send_alert "Long-Running Position: $symbol" \
                "$symbol $side position open for ${hours_int}h with \$$pnl unrealized P&L." \
                "info"
        done
    else
        log_message "✅ No stuck positions (>48h)"
    fi
}

# Main execution
main() {
    log_message "╔═══════════════════════════════════════════════════════════════╗"
    log_message "║        PERFORMANCE MONITORING & ALERT SYSTEM                  ║"
    log_message "╚═══════════════════════════════════════════════════════════════╝"
    log_message ""

    # Run all checks
    check_overall_performance
    echo ""

    check_symbol_performance
    echo ""

    check_daily_performance
    echo ""

    check_confidence_tracking
    echo ""

    check_model_freshness
    echo ""

    check_stuck_positions
    echo ""

    log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_message "✅ Performance monitoring complete"
    log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# Run main function
main
