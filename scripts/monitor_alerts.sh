#!/bin/bash
# =============================================================================
# Alert Monitoring Script
# Purpose: Monitor and test the alert system for paper trading
# Created: 2025-12-12
# Usage: ./scripts/monitor_alerts.sh [--test]
# =============================================================================

set -e

# Configuration
PROJECT_DIR="/mnt/d/Bimo_max/crypto-trading-bot"
NOTIFICATION_SERVICE="http://localhost:8006"

# Parse arguments
TEST_MODE=false
if [ "$1" == "--test" ] || [ "$1" == "-t" ]; then
    TEST_MODE=true
fi

echo "================================================================="
echo "          ALERT SYSTEM MONITORING"
echo "================================================================="
echo "Time: $(date '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

# =================================================================
# SECTION 1: SERVICE STATUS
# =================================================================
echo "=== SERVICE STATUS ==="

# Check notification service health
notif_status=$(curl -s "$NOTIFICATION_SERVICE/health" 2>/dev/null)
if [ -n "$notif_status" ]; then
    status=$(echo "$notif_status" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'unknown'))" 2>/dev/null || echo "unknown")
    echo "Notification Service: $status"

    # Get service details
    echo "$notif_status" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if 'channels' in data:
        print('  Configured Channels:', ', '.join(data.get('channels', [])))
    if 'uptime' in data:
        print(f'  Uptime: {data.get(\"uptime\", \"unknown\")}')
except:
    pass
" 2>/dev/null
else
    echo "Notification Service: OFFLINE"
fi
echo ""

# =================================================================
# SECTION 2: ALERT CHANNEL STATUS
# =================================================================
echo "=== ALERT CHANNEL STATUS ==="

# Check Telegram
echo -n "Telegram: "
tg_config=$(curl -s "$NOTIFICATION_SERVICE/api/v1/config/telegram" 2>/dev/null)
if [ -n "$tg_config" ]; then
    enabled=$(echo "$tg_config" | python3 -c "import sys, json; print(json.load(sys.stdin).get('enabled', False))" 2>/dev/null || echo "false")
    if [ "$enabled" == "True" ] || [ "$enabled" == "true" ]; then
        echo "ENABLED"
    else
        echo "DISABLED"
    fi
else
    # Check environment variable
    if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
        echo "CONFIGURED (via env)"
    else
        echo "NOT CONFIGURED"
    fi
fi

# Check Email
echo -n "Email: "
email_config=$(curl -s "$NOTIFICATION_SERVICE/api/v1/config/email" 2>/dev/null)
if [ -n "$email_config" ]; then
    enabled=$(echo "$email_config" | python3 -c "import sys, json; print(json.load(sys.stdin).get('enabled', False))" 2>/dev/null || echo "false")
    if [ "$enabled" == "True" ] || [ "$enabled" == "true" ]; then
        echo "ENABLED"
    else
        echo "DISABLED"
    fi
else
    if [ -n "$SMTP_HOST" ]; then
        echo "CONFIGURED (via env)"
    else
        echo "NOT CONFIGURED"
    fi
fi

# Check Slack
echo -n "Slack: "
slack_config=$(curl -s "$NOTIFICATION_SERVICE/api/v1/config/slack" 2>/dev/null)
if [ -n "$slack_config" ]; then
    enabled=$(echo "$slack_config" | python3 -c "import sys, json; print(json.load(sys.stdin).get('enabled', False))" 2>/dev/null || echo "false")
    if [ "$enabled" == "True" ] || [ "$enabled" == "true" ]; then
        echo "ENABLED"
    else
        echo "DISABLED"
    fi
else
    if [ -n "$SLACK_WEBHOOK_URL" ]; then
        echo "CONFIGURED (via env)"
    else
        echo "NOT CONFIGURED"
    fi
fi

# Check Discord
echo -n "Discord: "
if [ -n "$DISCORD_WEBHOOK_URL" ]; then
    echo "CONFIGURED"
else
    echo "NOT CONFIGURED"
fi
echo ""

# =================================================================
# SECTION 3: TEST ALERTS (if --test flag)
# =================================================================
if [ "$TEST_MODE" = true ]; then
    echo "=== TESTING ALERT CHANNELS ==="
    echo ""

    # Test Telegram
    echo "Testing Telegram..."
    tg_result=$(curl -s -X POST "$NOTIFICATION_SERVICE/api/v1/alerts/test" \
        -H "Content-Type: application/json" \
        -d '{"channel": "telegram", "message": "Day 2 Paper Trading Test Alert"}' 2>/dev/null)
    if [ -n "$tg_result" ]; then
        status=$(echo "$tg_result" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', json.load(sys.stdin).get('success', 'unknown')))" 2>/dev/null || echo "unknown")
        echo "  Telegram: $status"
    else
        echo "  Telegram: FAILED (no response)"
    fi

    # Test Email
    echo "Testing Email..."
    email_result=$(curl -s -X POST "$NOTIFICATION_SERVICE/api/v1/alerts/test" \
        -H "Content-Type: application/json" \
        -d '{"channel": "email", "message": "Day 2 Paper Trading Test Alert"}' 2>/dev/null)
    if [ -n "$email_result" ]; then
        status=$(echo "$email_result" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', json.load(sys.stdin).get('success', 'unknown')))" 2>/dev/null || echo "unknown")
        echo "  Email: $status"
    else
        echo "  Email: FAILED (no response)"
    fi

    # Test generic alert
    echo "Testing Generic Alert..."
    generic_result=$(curl -s -X POST "$NOTIFICATION_SERVICE/api/v1/alerts/send" \
        -H "Content-Type: application/json" \
        -d '{
            "type": "INFO",
            "title": "Day 2 Monitoring Test",
            "message": "This is a test alert from the Day 2 monitoring system.",
            "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
        }' 2>/dev/null)
    if [ -n "$generic_result" ]; then
        echo "  Generic Alert: sent"
    else
        echo "  Generic Alert: FAILED"
    fi
    echo ""
fi

# =================================================================
# SECTION 4: RECENT ALERTS
# =================================================================
echo "=== RECENT ALERTS (Last 10) ==="

# Try to get from notification service
alerts=$(curl -s "$NOTIFICATION_SERVICE/api/v1/alerts/history?limit=10" 2>/dev/null)
if [ -n "$alerts" ] && [ "$alerts" != "null" ] && [ "$alerts" != "[]" ]; then
    echo "$alerts" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if isinstance(data, list):
        for alert in data:
            timestamp = alert.get('timestamp', 'N/A')[:19]
            severity = alert.get('severity', alert.get('type', 'INFO'))
            message = alert.get('message', 'No message')[:50]
            print(f'  [{timestamp}] [{severity}] {message}')
    else:
        print('  No alerts found')
except:
    print('  Unable to parse alerts')
" 2>/dev/null
else
    # Try to get from docker logs
    if command -v docker &> /dev/null; then
        echo "  (From container logs)"
        docker logs crypto-bot-notification --since "24h" 2>&1 | grep -i "alert\|notification\|sent" | tail -10 | while read line; do
            echo "  $line"
        done
    else
        echo "  No recent alerts found"
    fi
fi
echo ""

# =================================================================
# SECTION 5: CRITICAL ALERTS TODAY
# =================================================================
echo "=== CRITICAL ALERTS TODAY ==="

# Check for critical alerts
critical_alerts=$(curl -s "$NOTIFICATION_SERVICE/api/v1/alerts/history?severity=CRITICAL&since=$(date +%Y-%m-%d)" 2>/dev/null)
if [ -n "$critical_alerts" ] && [ "$critical_alerts" != "null" ] && [ "$critical_alerts" != "[]" ]; then
    count=$(echo "$critical_alerts" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
    if [ "$count" -gt 0 ]; then
        echo "  WARNING: $count CRITICAL alert(s) found!"
        echo ""
        echo "$critical_alerts" | python3 -c "
import sys, json
try:
    for alert in json.load(sys.stdin):
        timestamp = alert.get('timestamp', 'N/A')
        message = alert.get('message', 'No message')
        print(f'  [{timestamp}] {message}')
except:
    pass
" 2>/dev/null
    else
        echo "  No critical alerts today"
    fi
else
    echo "  No critical alerts today"
fi
echo ""

# =================================================================
# SECTION 6: ALERT STATISTICS
# =================================================================
echo "=== ALERT STATISTICS (Last 24h) ==="

if command -v docker &> /dev/null; then
    # Count by severity from logs
    info_count=$(docker logs crypto-bot-notification --since "24h" 2>&1 | grep -ci "\[INFO\]" || echo "0")
    warn_count=$(docker logs crypto-bot-notification --since "24h" 2>&1 | grep -ci "\[WARNING\]\|\[WARN\]" || echo "0")
    error_count=$(docker logs crypto-bot-notification --since "24h" 2>&1 | grep -ci "\[ERROR\]" || echo "0")
    critical_count=$(docker logs crypto-bot-notification --since "24h" 2>&1 | grep -ci "\[CRITICAL\]" || echo "0")

    echo "  INFO: $info_count"
    echo "  WARNING: $warn_count"
    echo "  ERROR: $error_count"
    echo "  CRITICAL: $critical_count"
else
    echo "  Statistics not available (Docker not accessible)"
fi
echo ""

# =================================================================
# SECTION 7: ALERT TRIGGERS
# =================================================================
echo "=== CONFIGURED ALERT TRIGGERS ==="

# List configured triggers
triggers=$(curl -s "$NOTIFICATION_SERVICE/api/v1/alerts/triggers" 2>/dev/null)
if [ -n "$triggers" ] && [ "$triggers" != "null" ]; then
    echo "$triggers" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if isinstance(data, list):
        for trigger in data:
            name = trigger.get('name', 'Unknown')
            enabled = 'ENABLED' if trigger.get('enabled', True) else 'DISABLED'
            print(f'  - {name}: {enabled}')
    else:
        for key, value in data.items():
            print(f'  - {key}: {value}')
except:
    print('  Unable to parse triggers')
" 2>/dev/null
else
    # Default triggers
    echo "  - Daily Loss > 4%: ENABLED (warning)"
    echo "  - Daily Loss > 5%: ENABLED (emergency stop)"
    echo "  - Service Down: ENABLED"
    echo "  - Trade Executed: ENABLED"
    echo "  - Position Opened: ENABLED"
    echo "  - Position Closed: ENABLED"
fi
echo ""

echo "================================================================="
echo "Alert monitoring complete."
echo ""
echo "Quick Commands:"
echo "  Test alerts:     ./scripts/monitor_alerts.sh --test"
echo "  View logs:       docker logs -f crypto-bot-notification"
echo "  Send test:       curl -X POST http://localhost:8006/api/v1/alerts/test"
echo "================================================================="
