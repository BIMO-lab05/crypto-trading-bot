#!/bin/bash
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# =============================================================================
# Check Daily Loss and Alert if Threshold Exceeded
# Purpose: Automated monitoring of daily loss limits
# Created: 2025-12-12
# Usage: ./scripts/check_daily_loss.sh
# Can be added to cron: 0 */4 * * * /path/to/check_daily_loss.sh
# =============================================================================

set -e

# Configuration
PROJECT_DIR="${PROJECT_ROOT}"
LOG_FILE="$PROJECT_DIR/logs/daily_loss_check.log"
NOTIFICATION_SERVICE="http://localhost:8006"
RISK_METRICS="http://localhost:8009"
TRADING_ENGINE="http://localhost:8005"

# Thresholds
WARNING_THRESHOLD=3.0    # Warning at 3% daily loss
CRITICAL_THRESHOLD=4.0   # Critical at 4% daily loss
EMERGENCY_THRESHOLD=5.0  # Emergency stop at 5% daily loss

# Initial capital
INITIAL_CAPITAL=10000

# Timestamp function
timestamp() {
    date "+%Y-%m-%d %H:%M:%S UTC"
}

# Log function
log() {
    echo "[$(timestamp)] $1" | tee -a "$LOG_FILE"
}

# Send alert function
send_alert() {
    local severity=$1
    local message=$2

    log "$severity: $message"

    # Send via notification service
    curl -s -X POST "$NOTIFICATION_SERVICE/api/v1/alerts/send" \
        -H "Content-Type: application/json" \
        -d "{
            \"type\": \"$severity\",
            \"title\": \"Daily Loss Alert\",
            \"message\": \"$message\",
            \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
        }" > /dev/null 2>&1 || true

    # Also try telegram directly if available
    if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
        curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
            -d "chat_id=$TELEGRAM_CHAT_ID" \
            -d "text=[$severity] $message" \
            -d "parse_mode=HTML" > /dev/null 2>&1 || true
    fi
}

# Main check
main() {
    log "Starting daily loss check..."

    # Get daily P&L from database
    if command -v docker &> /dev/null; then
        daily_pnl=$(docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -t -A -c "
            SELECT COALESCE(ROUND(SUM(pnl)::numeric, 2), 0)
            FROM trades
            WHERE DATE(created_at) = CURRENT_DATE;
        " 2>/dev/null || echo "0")
    else
        daily_pnl="0"
    fi

    # Calculate loss percentage
    if [ -n "$daily_pnl" ] && [ "$daily_pnl" != "" ]; then
        loss_pct=$(echo "scale=2; ($daily_pnl / $INITIAL_CAPITAL) * -100" | bc 2>/dev/null || echo "0")

        # Handle negative (which means profit)
        if (( $(echo "$loss_pct < 0" | bc -l) )); then
            loss_pct=0
            log "Daily P&L: +\$$daily_pnl (Profit) - No concerns"
            exit 0
        fi

        log "Daily P&L: \$$daily_pnl | Loss: ${loss_pct}%"

        # Check thresholds
        if (( $(echo "$loss_pct >= $EMERGENCY_THRESHOLD" | bc -l) )); then
            send_alert "CRITICAL" "EMERGENCY: Daily loss at ${loss_pct}% exceeds ${EMERGENCY_THRESHOLD}% limit! Trading should be stopped!"

            # Trigger emergency stop
            log "Triggering emergency stop..."
            curl -s -X POST "$TRADING_ENGINE/api/v1/emergency-stop" > /dev/null 2>&1 || true

        elif (( $(echo "$loss_pct >= $CRITICAL_THRESHOLD" | bc -l) )); then
            send_alert "WARNING" "CRITICAL: Daily loss at ${loss_pct}% approaching emergency threshold of ${EMERGENCY_THRESHOLD}%!"

        elif (( $(echo "$loss_pct >= $WARNING_THRESHOLD" | bc -l) )); then
            send_alert "INFO" "Warning: Daily loss at ${loss_pct}% exceeds warning threshold of ${WARNING_THRESHOLD}%"

        else
            log "Daily loss ${loss_pct}% within acceptable limits"
        fi
    else
        log "Unable to fetch daily P&L data"
    fi

    # Also check unrealized P&L
    unrealized=$(curl -s "$TRADING_ENGINE/api/v1/positions" 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    positions = data.get('positions', data) if isinstance(data, dict) else data
    total = sum(p.get('unrealized_pnl', 0) for p in positions)
    print(f'{total:.2f}')
except:
    print('0')
" 2>/dev/null || echo "0")

    if [ -n "$unrealized" ] && [ "$unrealized" != "0" ]; then
        unrealized_pct=$(echo "scale=2; ($unrealized / $INITIAL_CAPITAL) * -100" | bc 2>/dev/null || echo "0")

        if (( $(echo "$unrealized_pct > 0 && $unrealized_pct >= $WARNING_THRESHOLD" | bc -l) )); then
            log "WARNING: Unrealized loss at \$$unrealized (${unrealized_pct}%)"
            send_alert "INFO" "Unrealized loss at \$$unrealized (${unrealized_pct}%)"
        fi
    fi

    log "Daily loss check complete"
}

# Run main function
main
