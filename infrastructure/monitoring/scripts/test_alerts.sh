#!/bin/bash
# Test Alert System
# Sends test alerts to verify email and Telegram notifications are working
# Usage: ./test_alerts.sh [critical|warning|info|all]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# AlertManager URL
ALERTMANAGER_URL="${ALERTMANAGER_URL:-http://localhost:9093}"
TELEGRAM_BOT_URL="${TELEGRAM_BOT_URL:-http://localhost:8007}"

# Function to print colored output
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to send test alert to AlertManager
send_test_alert() {
    local severity=$1
    local alertname=$2
    local summary=$3
    local description=$4
    local component=${5:-test}

    log_info "Sending $severity alert: $alertname"

    local payload=$(cat <<EOF
[
  {
    "labels": {
      "alertname": "$alertname",
      "severity": "$severity",
      "component": "$component",
      "category": "test",
      "instance": "test-instance",
      "job": "test-job"
    },
    "annotations": {
      "summary": "$summary",
      "description": "$description",
      "action": "This is a test alert. No action required.",
      "dashboard": "http://localhost:3000/d/test",
      "runbook": "https://github.com/crypto-bot/runbooks/test.md"
    },
    "startsAt": "$(date -u +%Y-%m-%dT%H:%M:%S.000Z)",
    "endsAt": "$(date -u -d '+5 minutes' +%Y-%m-%dT%H:%M:%S.000Z)"
  }
]
EOF
)

    response=$(curl -s -X POST "$ALERTMANAGER_URL/api/v1/alerts" \
        -H "Content-Type: application/json" \
        -d "$payload")

    if [ $? -eq 0 ]; then
        log_info "Alert sent successfully"
        return 0
    else
        log_error "Failed to send alert"
        log_error "Response: $response"
        return 1
    fi
}

# Function to test Telegram bot directly
test_telegram_bot() {
    log_info "Testing Telegram bot directly..."

    response=$(curl -s -X POST "$TELEGRAM_BOT_URL/test")

    if echo "$response" | grep -q "success"; then
        log_info "Telegram bot test successful"
        echo "$response" | jq '.'
        return 0
    else
        log_error "Telegram bot test failed"
        echo "$response"
        return 1
    fi
}

# Function to check AlertManager status
check_alertmanager() {
    log_info "Checking AlertManager status..."

    response=$(curl -s "$ALERTMANAGER_URL/api/v1/status")

    if echo "$response" | grep -q "success"; then
        log_info "AlertManager is running"
        echo "$response" | jq '.data.versionInfo'
        return 0
    else
        log_error "AlertManager is not responding"
        return 1
    fi
}

# Function to view active alerts
view_active_alerts() {
    log_info "Fetching active alerts..."

    response=$(curl -s "$ALERTMANAGER_URL/api/v1/alerts")

    if echo "$response" | grep -q "success"; then
        local alert_count=$(echo "$response" | jq '.data | length')
        log_info "Active alerts: $alert_count"
        echo "$response" | jq '.data[] | {alertname: .labels.alertname, status: .status.state, severity: .labels.severity}'
    else
        log_error "Failed to fetch alerts"
    fi
}

# Test critical alert
test_critical_alert() {
    log_warn "=== Testing CRITICAL Alert ==="
    send_test_alert \
        "critical" \
        "TestCriticalAlert" \
        "Test Critical Alert - Trading Engine Down Simulation" \
        "This is a test of critical alerts. If you receive this via email and Telegram, the alerting system is working correctly. This simulates a Trading Engine Down scenario." \
        "trading-engine"

    sleep 2
}

# Test warning alert
test_warning_alert() {
    log_warn "=== Testing WARNING Alert ==="
    send_test_alert \
        "warning" \
        "TestWarningAlert" \
        "Test Warning Alert - High API Latency Simulation" \
        "This is a test of warning alerts. If you receive this via email, the warning notification system is working correctly. This simulates a High API Latency scenario." \
        "api"

    sleep 2
}

# Test info alert
test_info_alert() {
    log_warn "=== Testing INFO Alert ==="
    send_test_alert \
        "info" \
        "TestInfoAlert" \
        "Test Info Alert - Deployment Completed Simulation" \
        "This is a test of info alerts. This simulates a successful deployment notification. Info alerts are grouped into daily summaries." \
        "deployment"

    sleep 2
}

# Test trading-specific alert
test_trading_alert() {
    log_warn "=== Testing TRADING Alert ==="
    send_test_alert \
        "critical" \
        "TestDailyLossExceeded" \
        "Test Daily Loss Alert - Simulated 6% Loss" \
        "This is a test of trading-specific alerts. If you receive this via Telegram and email, the trading alert system is working correctly. This simulates a Daily Loss Exceeded scenario (6% simulated loss)." \
        "risk-management"

    sleep 2
}

# Test database alert
test_database_alert() {
    log_warn "=== Testing DATABASE Alert ==="
    send_test_alert \
        "critical" \
        "TestDatabaseDown" \
        "Test Database Alert - Database Connection Lost" \
        "This is a test of database-specific alerts. If you receive this via email with database-specific formatting, the database alert routing is working correctly." \
        "database"

    sleep 2
}

# Test alert resolution
test_alert_resolution() {
    log_warn "=== Testing Alert RESOLUTION ==="

    # Send firing alert
    send_test_alert \
        "warning" \
        "TestResolutionAlert" \
        "Test Alert Resolution - Initial Alert" \
        "This alert will be resolved in 5 seconds to test resolution notifications." \
        "test"

    log_info "Waiting 5 seconds before resolving..."
    sleep 5

    # Send resolved alert
    local payload=$(cat <<EOF
[
  {
    "labels": {
      "alertname": "TestResolutionAlert",
      "severity": "warning",
      "component": "test"
    },
    "annotations": {
      "summary": "Test Alert Resolution - Resolved",
      "description": "This alert has been resolved. If you receive a resolution notification, the system is working correctly."
    },
    "startsAt": "$(date -u -d '-5 minutes' +%Y-%m-%dT%H:%M:%S.000Z)",
    "endsAt": "$(date -u +%Y-%m-%dT%H:%M:%S.000Z)"
  }
]
EOF
)

    log_info "Sending resolved alert..."
    curl -s -X POST "$ALERTMANAGER_URL/api/v1/alerts" \
        -H "Content-Type: application/json" \
        -d "$payload" > /dev/null

    log_info "Resolution notification sent"
    sleep 2
}

# Main script
main() {
    local test_type=${1:-all}

    echo ""
    echo "========================================"
    echo "  Crypto Trading Bot Alert Test Suite  "
    echo "========================================"
    echo ""

    # Check prerequisites
    log_info "Checking prerequisites..."

    if ! command -v curl &> /dev/null; then
        log_error "curl is required but not installed"
        exit 1
    fi

    if ! command -v jq &> /dev/null; then
        log_warn "jq is not installed. Output will be less formatted."
    fi

    # Check AlertManager
    if ! check_alertmanager; then
        log_error "AlertManager is not running. Start it with: docker-compose up -d alertmanager"
        exit 1
    fi

    echo ""

    # Run tests based on argument
    case $test_type in
        critical)
            test_critical_alert
            ;;
        warning)
            test_warning_alert
            ;;
        info)
            test_info_alert
            ;;
        trading)
            test_trading_alert
            ;;
        database)
            test_database_alert
            ;;
        resolution)
            test_alert_resolution
            ;;
        telegram)
            test_telegram_bot
            ;;
        all)
            test_telegram_bot
            echo ""
            test_critical_alert
            echo ""
            test_warning_alert
            echo ""
            test_info_alert
            echo ""
            test_trading_alert
            echo ""
            test_database_alert
            echo ""
            test_alert_resolution
            ;;
        *)
            log_error "Unknown test type: $test_type"
            echo ""
            echo "Usage: $0 [critical|warning|info|trading|database|resolution|telegram|all]"
            echo ""
            echo "Test types:"
            echo "  critical   - Test critical alert (immediate notification)"
            echo "  warning    - Test warning alert (email notification)"
            echo "  info       - Test info alert (daily summary)"
            echo "  trading    - Test trading-specific alert (Telegram + email)"
            echo "  database   - Test database alert (database-specific routing)"
            echo "  resolution - Test alert resolution notification"
            echo "  telegram   - Test Telegram bot directly"
            echo "  all        - Run all tests (default)"
            exit 1
            ;;
    esac

    echo ""
    log_info "=== Test Summary ==="
    echo ""
    log_info "Alerts have been sent to AlertManager"
    log_info "Check your email and Telegram for notifications"
    echo ""
    log_info "View active alerts: curl $ALERTMANAGER_URL/api/v1/alerts | jq"
    log_info "View AlertManager UI: $ALERTMANAGER_URL"
    echo ""

    # Show active alerts
    view_active_alerts

    echo ""
    log_info "Test completed!"
    echo ""
}

# Run main function
main "$@"
