#!/bin/bash
# Health Monitoring Cron Script
# Runs every 5 minutes to check system health and send alerts

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/tmp/health_monitor.log"
ALERT_COOLDOWN=3600  # 1 hour cooldown for same alert
LAST_ALERT_FILE="/tmp/last_health_alert"

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
    PORTFOLIO=$(curl -s "http://localhost:8003/api/v1/portfolio" 2>/dev/null || echo "{}")
    DAILY_PNL=$(echo "$PORTFOLIO" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('portfolio', {}).get('total_return_pct', '0'))" 2>/dev/null || echo "0")

    # Convert to number and check
    LOSS_PCT=$(echo "$DAILY_PNL" | awk '{if ($1 < 0) print -$1; else print 0}')

    # Check 4% warning threshold
    if (( $(echo "$LOSS_PCT > 4" | bc -l) )); then
        if should_send_alert "loss_warning"; then
            send_telegram_alert "⚠️  WARNING: Daily loss at ${LOSS_PCT}% (approaching 5% limit)"
            record_alert "loss_warning"
        fi
    fi

    # Check 5% critical threshold
    if (( $(echo "$LOSS_PCT >= 5" | bc -l) )); then
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
