#!/bin/bash
# Health Monitoring Cron Script
# Runs every 5 minutes to check system health and send alerts

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_FILE="/tmp/health_monitor.log"
ALERT_COOLDOWN=3600  # 1 hour cooldown for same alert
LAST_ALERT_FILE="/tmp/last_health_alert"

# Daily-loss breaker, read from shared/account.py (the declaration of record;
# host-run scripts may import it per CLAUDE.md money rules). This script used
# to hardcode a 5% breaker and send a CRITICAL "limit REACHED" Telegram alert
# at 5% — seven points before the real ADR-028 breaker at 12%.
#
# This must NOT be a bare `VAR=$(...)`: under `set -e` a failed import would
# exit here and this cron would stop monitoring entirely. A monitor that goes
# silent is a worse failure than one using a stale threshold, so on failure we
# fall back, keep running, and say so loudly. (startup.sh takes the opposite
# stance deliberately — there, refusing to guess is correct, because it WRITES
# an account size rather than reading one.)
DAILY_LOSS_BREAKER_FALLBACK=12.0  # ADR-028; only used if the import fails
if ! DAILY_LOSS_BREAKER_PCT="$(cd "$REPO_ROOT" && python3 -c \
    'from shared.account import MAX_DAILY_LOSS_PCT; print(MAX_DAILY_LOSS_PCT)' \
    2>/dev/null)"; then
    DAILY_LOSS_BREAKER_PCT="$DAILY_LOSS_BREAKER_FALLBACK"
    RISK_CONFIG_UNREADABLE=1
fi
# Pre-alert with headroom before the breaker, matching scripts/monitor.py's
# THRESHOLDS["daily_loss_pct"] convention (warn at 10 ahead of the 12 breaker).
DAILY_LOSS_WARN_PCT="$(echo "$DAILY_LOSS_BREAKER_PCT - 2" | bc -l)"

# Check if last alert was sent recently
should_send_alert() {
    local alert_type=$1
    if [ -f "$LAST_ALERT_FILE" ]; then
        local last_alert_time=$(cat "$LAST_ALERT_FILE" | grep "$alert_type" | cut -d: -f2)
        if [ -n "$last_alert_time" ]; then
            local current_time=$(date +%s)
            local diff=$((current_time - last_alert_time))
            if [ $diff -lt $ALERT_COOLDOWN ]; then
                return 1  # Don't send alert
            fi
        fi
    fi
    return 0  # Send alert
}

record_alert() {
    local alert_type=$1
    echo "$alert_type:$(date +%s)" >> "$LAST_ALERT_FILE"
}

send_telegram_alert() {
    local message=$1
    curl -s -X POST "http://localhost:8006/api/v1/notify" \
        -H "Content-Type: application/json" \
        -d "{\"type\":\"error\",\"message\":\"$message\"}" > /dev/null 2>&1
}

# Check critical services
check_services() {
    CRITICAL_SERVICES=("trading" "bybit" "market-data" "portfolio")

    for service in "${CRITICAL_SERVICES[@]}"; do
        if ! docker ps | grep -q "crypto-bot-$service"; then
            if should_send_alert "service_$service"; then
                send_telegram_alert "🚨 CRITICAL: $service container is DOWN!"
                record_alert "service_$service"
            fi
            echo "[CRITICAL] $service is DOWN" | tee -a "$LOG_FILE"
        fi
    done
}

# Check daily loss limit
check_daily_loss() {
    # Surface a stale-threshold run rather than letting it pass as normal.
    if [ "${RISK_CONFIG_UNREADABLE:-0}" = "1" ] && should_send_alert "risk_config"; then
        send_telegram_alert "⚠️  WARNING: cannot read shared/account.py — daily-loss thresholds fell back to ${DAILY_LOSS_BREAKER_PCT}%. Verify the risk config."
        record_alert "risk_config"
    fi

    PORTFOLIO=$(curl -s "http://localhost:8003/api/v1/portfolio" 2>/dev/null || echo "{}")
    DAILY_PNL=$(echo "$PORTFOLIO" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('portfolio', {}).get('total_return_pct', '0'))" 2>/dev/null || echo "0")

    # Convert to number and check
    LOSS_PCT=$(echo "$DAILY_PNL" | awk '{if ($1 < 0) print -$1; else print 0}')

    # Pre-alert, with headroom before the breaker
    if (( $(echo "$LOSS_PCT > $DAILY_LOSS_WARN_PCT" | bc -l) )); then
        if should_send_alert "loss_warning"; then
            send_telegram_alert "⚠️  WARNING: Daily loss at ${LOSS_PCT}% (approaching ${DAILY_LOSS_BREAKER_PCT}% limit)"
            record_alert "loss_warning"
        fi
    fi

    # Breaker threshold (ADR-028)
    if (( $(echo "$LOSS_PCT >= $DAILY_LOSS_BREAKER_PCT" | bc -l) )); then
        if should_send_alert "loss_critical"; then
            send_telegram_alert "🚨 CRITICAL: Daily loss limit REACHED at ${LOSS_PCT}%! Trading should be stopped!"
            record_alert "loss_critical"
        fi
    fi
}

# Check disk space
check_disk_space() {
    DISK_USAGE=$(df -h /mnt/d | tail -1 | awk '{print $5}' | sed 's/%//')

    if [ "$DISK_USAGE" -gt 90 ]; then
        if should_send_alert "disk_space"; then
            send_telegram_alert "🚨 CRITICAL: Disk space at ${DISK_USAGE}%!"
            record_alert "disk_space"
        fi
    elif [ "$DISK_USAGE" -gt 80 ]; then
        if should_send_alert "disk_warning"; then
            send_telegram_alert "⚠️  WARNING: Disk space at ${DISK_USAGE}%"
            record_alert "disk_warning"
        fi
    fi
}

# Main monitoring
echo "[$(date +%Y-%m-%d\ %H:%M:%S)] Running health checks..." | tee -a "$LOG_FILE"

check_services
check_daily_loss
check_disk_space

echo "[$(date +%Y-%m-%d\ %H:%M:%S)] Health check complete" | tee -a "$LOG_FILE"
