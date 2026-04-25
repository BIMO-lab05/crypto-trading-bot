#!/bin/bash
# =============================================================================
# Alert Channel Testing Script
# Purpose: Test all configured notification channels
# Created: 2025-12-12
# Usage: ./scripts/test_alert_channels.sh
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
NOTIFICATION_SERVICE_URL="${NOTIFICATION_SERVICE_URL:-http://localhost:8006}"
TRADING_ENGINE_URL="${TRADING_ENGINE_URL:-http://localhost:8005}"
REPORT_FILE="/mnt/d/Bimo_max/crypto-trading-bot/reports/alert_test_report_$(date +%Y%m%d_%H%M%S).md"

# Create reports directory
mkdir -p /mnt/d/Bimo_max/crypto-trading-bot/reports

# Start report
cat << 'EOF' > "$REPORT_FILE"
# Alert Channel Testing Report

**Date:** $(date '+%Y-%m-%d %H:%M:%S')
**Notification Service:** $NOTIFICATION_SERVICE_URL
**Trading Engine:** $TRADING_ENGINE_URL

---

## Test Results

EOF

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Alert Channel Testing Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to test endpoint
test_endpoint() {
    local name="$1"
    local url="$2"
    local method="$3"
    local data="$4"

    echo -e "${YELLOW}Testing: ${name}${NC}"

    if [ "$method" == "POST" ]; then
        if [ -n "$data" ]; then
            response=$(curl -s -w "\n%{http_code}" -X POST "$url" \
                -H "Content-Type: application/json" \
                -d "$data" 2>&1) || true
        else
            response=$(curl -s -w "\n%{http_code}" -X POST "$url" 2>&1) || true
        fi
    else
        response=$(curl -s -w "\n%{http_code}" -X GET "$url" 2>&1) || true
    fi

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    if [[ "$http_code" =~ ^2 ]]; then
        echo -e "  ${GREEN}SUCCESS${NC} (HTTP $http_code)"
        echo "### $name" >> "$REPORT_FILE"
        echo "- **Status:** SUCCESS" >> "$REPORT_FILE"
        echo "- **HTTP Code:** $http_code" >> "$REPORT_FILE"
        echo "- **Response:** \`$body\`" >> "$REPORT_FILE"
        echo "" >> "$REPORT_FILE"
        return 0
    else
        echo -e "  ${RED}FAILED${NC} (HTTP $http_code)"
        echo "### $name" >> "$REPORT_FILE"
        echo "- **Status:** FAILED" >> "$REPORT_FILE"
        echo "- **HTTP Code:** $http_code" >> "$REPORT_FILE"
        echo "- **Error:** \`$body\`" >> "$REPORT_FILE"
        echo "" >> "$REPORT_FILE"
        return 1
    fi
}

# Test 1: Service Health Checks
echo -e "\n${BLUE}--- Service Health Checks ---${NC}\n"
echo "## Service Health Checks" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

test_endpoint "Notification Service Health" "$NOTIFICATION_SERVICE_URL/health" "GET" || true
test_endpoint "Notification Service Ready" "$NOTIFICATION_SERVICE_URL/ready" "GET" || true
test_endpoint "Trading Engine Health" "$TRADING_ENGINE_URL/health" "GET" || true

# Test 2: Channel Status
echo -e "\n${BLUE}--- Channel Status ---${NC}\n"
echo "## Channel Status" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

test_endpoint "Get Channel Status" "$NOTIFICATION_SERVICE_URL/api/v1/alerts/channels/status" "GET" || true

# Test 3: Configuration
echo -e "\n${BLUE}--- Alert Configuration ---${NC}\n"
echo "## Alert Configuration" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

test_endpoint "Get Alert Config" "$NOTIFICATION_SERVICE_URL/api/v1/alerts/config" "GET" || true

# Test 4: Channel Tests
echo -e "\n${BLUE}--- Channel Tests ---${NC}\n"
echo "## Channel Tests" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo -e "${YELLOW}Testing Telegram channel...${NC}"
test_endpoint "Test Telegram" "$NOTIFICATION_SERVICE_URL/api/v1/alerts/test/telegram" "POST" || true

echo -e "${YELLOW}Testing Email channel...${NC}"
test_endpoint "Test Email" "$NOTIFICATION_SERVICE_URL/api/v1/alerts/test/email" "POST" || true

echo -e "${YELLOW}Testing Slack channel...${NC}"
test_endpoint "Test Slack" "$NOTIFICATION_SERVICE_URL/api/v1/alerts/test/slack" "POST" || true

# Test 5: Send Test Alerts
echo -e "\n${BLUE}--- Send Test Alerts ---${NC}\n"
echo "## Test Alerts" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# Trade alert
trade_alert_data='{
    "action": "BUY",
    "symbol": "BNBUSDT",
    "quantity": 0.1,
    "price": 650.0,
    "confidence": 0.75
}'
test_endpoint "Send Trade Alert" "$NOTIFICATION_SERVICE_URL/api/v1/alerts/trade" "POST" "$trade_alert_data" || true

# Risk alert
risk_alert_data='{
    "alert_type": "TEST_ALERT",
    "message": "Test risk alert - validating alert system",
    "severity": "MEDIUM"
}'
test_endpoint "Send Risk Alert" "$NOTIFICATION_SERVICE_URL/api/v1/alerts/risk" "POST" "$risk_alert_data" || true

# System alert
system_alert_data='{
    "service_name": "test-service",
    "status": "HEALTHY",
    "error_message": null
}'
test_endpoint "Send System Alert" "$NOTIFICATION_SERVICE_URL/api/v1/alerts/system?service_name=test-service&status=HEALTHY" "POST" || true

# Test 6: Alert History
echo -e "\n${BLUE}--- Alert History ---${NC}\n"
echo "## Alert History" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

test_endpoint "Get Alert History" "$NOTIFICATION_SERVICE_URL/api/v1/alerts/history?limit=10" "GET" || true
test_endpoint "Get Active Alerts" "$NOTIFICATION_SERVICE_URL/api/v1/alerts/active" "GET" || true

# Test 7: Alert Statistics
echo -e "\n${BLUE}--- Alert Statistics ---${NC}\n"
echo "## Alert Statistics" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

test_endpoint "Get Alert Stats (24h)" "$NOTIFICATION_SERVICE_URL/api/v1/alerts/stats?hours=24" "GET" || true

# Summary
echo -e "\n${BLUE}========================================${NC}"
echo -e "${GREEN}  Testing Complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Report saved to: ${YELLOW}$REPORT_FILE${NC}"

# Add summary to report
cat << EOF >> "$REPORT_FILE"
---

## Summary

Testing completed at $(date '+%Y-%m-%d %H:%M:%S')

### Recommendations

1. **Telegram:** Should be enabled and configured with bot token and chat ID
2. **Email:** Enable if you want email notifications for LOW priority alerts
3. **Slack:** Enable if you want team collaboration for CRITICAL alerts
4. **SMS:** Enable only for emergency escalation (requires Twilio)

### Alert Routing Configured

| Severity | Channels |
|----------|----------|
| CRITICAL | Telegram + Email + Slack |
| HIGH | Telegram + Email |
| MEDIUM | Telegram |
| LOW | Email (batched) |
| INFO | Dashboard only |

### Next Steps

1. Verify all enabled channels received test messages
2. Configure any disabled channels as needed
3. Test with actual trading signals
4. Monitor alert delivery in production

---

*Generated by alert_test_channels.sh*
EOF

echo ""
echo "View the full report:"
echo "  cat $REPORT_FILE"
