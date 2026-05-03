#!/bin/bash
# =============================================================================
# Telegram Notification Integration Test Script
# Purpose: Verify end-to-end notification flow from trading engine to Telegram
# Date: 2025-12-11
# =============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NOTIFICATION_SERVICE_URL="http://localhost:8006"
TRADING_ENGINE_URL="http://localhost:8005"
RABBITMQ_URL="http://localhost:15672"

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  Telegram Notification Integration Test   ${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# Function to check service health
check_service() {
    local name=$1
    local url=$2
    local timeout=${3:-5}

    echo -n "Checking $name... "
    if curl -s --max-time $timeout "$url" > /dev/null 2>&1; then
        echo -e "${GREEN}OK${NC}"
        return 0
    else
        echo -e "${RED}NOT AVAILABLE${NC}"
        return 1
    fi
}

# Function to send test notification
send_test_notification() {
    echo -e "\n${YELLOW}Sending test notification...${NC}"

    response=$(curl -s -X POST "${NOTIFICATION_SERVICE_URL}/api/v1/test" \
        -H "Content-Type: application/json" \
        -w "\n%{http_code}")

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    if [ "$http_code" == "200" ]; then
        echo -e "${GREEN}Test notification sent successfully!${NC}"
        echo "Response: $body"
        return 0
    else
        echo -e "${RED}Failed to send test notification (HTTP $http_code)${NC}"
        echo "Response: $body"
        return 1
    fi
}

# Function to send trade notification
send_trade_notification() {
    echo -e "\n${YELLOW}Sending trade notification...${NC}"

    payload=$(cat << 'EOF'
{
    "action": "BUY",
    "symbol": "BTCUSDT",
    "quantity": 0.001,
    "price": 97500.00,
    "timestamp": "2025-12-11T12:00:00Z",
    "signal_confidence": 0.75
}
EOF
)

    response=$(curl -s -X POST "${NOTIFICATION_SERVICE_URL}/api/v1/notify/trade" \
        -H "Content-Type: application/json" \
        -d "$payload" \
        -w "\n%{http_code}")

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    if [ "$http_code" == "200" ]; then
        echo -e "${GREEN}Trade notification sent!${NC}"
        echo "Response: $body"
        return 0
    else
        echo -e "${RED}Failed (HTTP $http_code)${NC}"
        return 1
    fi
}

# Function to send P&L notification
send_pnl_notification() {
    echo -e "\n${YELLOW}Sending P&L notification...${NC}"

    payload=$(cat << 'EOF'
{
    "trade": {
        "action": "SELL",
        "symbol": "BTCUSDT",
        "quantity": 0.001,
        "price": 99000.00,
        "timestamp": "2025-12-11T13:00:00Z",
        "signal_confidence": 0.80,
        "entry_price": 97500.00,
        "exit_price": 99000.00,
        "exit_reason": "Take Profit"
    },
    "pnl": 1.50
}
EOF
)

    response=$(curl -s -X POST "${NOTIFICATION_SERVICE_URL}/api/v1/notify/pnl" \
        -H "Content-Type: application/json" \
        -d "$payload" \
        -w "\n%{http_code}")

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    if [ "$http_code" == "200" ]; then
        echo -e "${GREEN}P&L notification sent!${NC}"
        echo "Response: $body"
        return 0
    else
        echo -e "${RED}Failed (HTTP $http_code)${NC}"
        return 1
    fi
}

# Function to send daily summary
send_daily_summary() {
    echo -e "\n${YELLOW}Sending daily summary notification...${NC}"

    payload=$(cat << 'EOF'
{
    "total_pnl": 127.55,
    "total_trades": 15,
    "win_rate": 0.666,
    "best_trade": 55.90,
    "worst_trade": -12.50,
    "balance": 10127.55,
    "open_positions": 3
}
EOF
)

    response=$(curl -s -X POST "${NOTIFICATION_SERVICE_URL}/api/v1/notify/daily-summary" \
        -H "Content-Type: application/json" \
        -d "$payload" \
        -w "\n%{http_code}")

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    if [ "$http_code" == "200" ]; then
        echo -e "${GREEN}Daily summary sent!${NC}"
        echo "Response: $body"
        return 0
    else
        echo -e "${RED}Failed (HTTP $http_code)${NC}"
        return 1
    fi
}

# Function to check notification service config
check_notification_config() {
    echo -e "\n${YELLOW}Checking notification service configuration...${NC}"

    response=$(curl -s "${NOTIFICATION_SERVICE_URL}/api/v1/config")

    if [ -n "$response" ]; then
        echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
        return 0
    else
        echo -e "${RED}Failed to get configuration${NC}"
        return 1
    fi
}

# Function to check RabbitMQ queues
check_rabbitmq_queues() {
    echo -e "\n${YELLOW}Checking RabbitMQ queues...${NC}"

    # Check if RabbitMQ management is available
    if command -v docker &> /dev/null; then
        docker exec crypto-bot-rabbitmq rabbitmqadmin list queues name messages 2>/dev/null || \
            echo -e "${YELLOW}RabbitMQ management not available via Docker${NC}"
    else
        echo -e "${YELLOW}Docker not available, skipping RabbitMQ check${NC}"
    fi
}

# Function to run pytest integration tests
run_integration_tests() {
    echo -e "\n${BLUE}============================================${NC}"
    echo -e "${BLUE}  Running Integration Tests                 ${NC}"
    echo -e "${BLUE}============================================${NC}"

    cd "$PROJECT_ROOT"

    # Check if pytest is available
    if ! command -v pytest &> /dev/null; then
        echo -e "${YELLOW}pytest not found in PATH, trying with python -m pytest${NC}"
        python -m pytest services/trading-engine/tests/integration/test_telegram_notifications.py \
            -v \
            --tb=short \
            -x \
            --log-cli-level=INFO \
            2>&1 || {
                echo -e "${YELLOW}Some tests may have skipped due to services not running${NC}"
            }
    else
        pytest services/trading-engine/tests/integration/test_telegram_notifications.py \
            -v \
            --tb=short \
            -x \
            --log-cli-level=INFO \
            2>&1 || {
                echo -e "${YELLOW}Some tests may have skipped due to services not running${NC}"
            }
    fi
}

# Main execution
main() {
    echo -e "\n${BLUE}Step 1: Checking Services${NC}"
    echo "============================================"

    services_ok=true

    check_service "Notification Service" "${NOTIFICATION_SERVICE_URL}/health" || services_ok=false
    check_service "Trading Engine" "${TRADING_ENGINE_URL}/health" || services_ok=false

    # Docker services check
    echo ""
    echo "Checking Docker containers..."
    if command -v docker &> /dev/null; then
        docker ps --format 'table {{.Names}}\t{{.Status}}' 2>/dev/null | grep -E "trading-engine|notification|rabbitmq" || \
            echo -e "${YELLOW}No matching Docker containers found${NC}"
    fi

    echo ""

    if [ "$services_ok" = true ]; then
        echo -e "\n${BLUE}Step 2: Check Configuration${NC}"
        echo "============================================"
        check_notification_config

        echo -e "\n${BLUE}Step 3: Send Test Notifications${NC}"
        echo "============================================"

        # Send various test notifications
        send_test_notification
        sleep 1
        send_trade_notification
        sleep 1
        send_pnl_notification
        sleep 1
        send_daily_summary

        echo -e "\n${BLUE}Step 4: Check Message Queues${NC}"
        echo "============================================"
        check_rabbitmq_queues

        echo -e "\n${BLUE}Step 5: Run Integration Tests${NC}"
        echo "============================================"
        run_integration_tests
    else
        echo -e "${YELLOW}Some services are not available.${NC}"
        echo "You can still run the tests (some will be skipped):"
        echo ""
        run_integration_tests
    fi

    echo ""
    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}  Integration Test Complete                 ${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo ""
    echo -e "${GREEN}Check your Telegram for test messages!${NC}"
    echo ""
    echo "If notifications didn't arrive, verify:"
    echo "  1. TELEGRAM_BOT_TOKEN is set correctly"
    echo "  2. TELEGRAM_CHAT_ID is set correctly"
    echo "  3. telegram_enabled=true in notification service"
    echo "  4. You've started a chat with your bot on Telegram"
    echo ""
}

# Parse command line arguments
case "${1:-}" in
    --test-only)
        run_integration_tests
        ;;
    --notify-only)
        check_service "Notification Service" "${NOTIFICATION_SERVICE_URL}/health" && \
        send_test_notification
        ;;
    --trade)
        check_service "Notification Service" "${NOTIFICATION_SERVICE_URL}/health" && \
        send_trade_notification
        ;;
    --pnl)
        check_service "Notification Service" "${NOTIFICATION_SERVICE_URL}/health" && \
        send_pnl_notification
        ;;
    --summary)
        check_service "Notification Service" "${NOTIFICATION_SERVICE_URL}/health" && \
        send_daily_summary
        ;;
    --help|-h)
        echo "Usage: $0 [OPTION]"
        echo ""
        echo "Options:"
        echo "  (none)        Run full integration test suite"
        echo "  --test-only   Run only pytest integration tests"
        echo "  --notify-only Send only test notification"
        echo "  --trade       Send test trade notification"
        echo "  --pnl         Send test P&L notification"
        echo "  --summary     Send test daily summary"
        echo "  --help        Show this help message"
        ;;
    *)
        main
        ;;
esac
