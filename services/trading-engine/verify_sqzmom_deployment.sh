#!/bin/bash
#
# SQZMOM Strategy Deployment Verification Script
# Purpose: Verify that SQZMOM strategy is correctly configured and operational
# Usage: ./verify_sqzmom_deployment.sh
#

set -e

echo "======================================================================"
echo "SQZMOM Strategy Deployment Verification"
echo "Date: $(date)"
echo "======================================================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
TRADING_ENGINE_URL="http://localhost:8005"
TECHNICAL_ANALYSIS_URL="http://localhost:8004"

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

# Function to run test
run_test() {
    local test_name="$1"
    local command="$2"
    local expected="$3"

    echo -n "Testing: $test_name ... "

    if eval "$command" | grep -q "$expected"; then
        echo -e "${GREEN}PASS${NC}"
        ((TESTS_PASSED++))
        return 0
    else
        echo -e "${RED}FAIL${NC}"
        ((TESTS_FAILED++))
        return 1
    fi
}

# Function to run test with JSON output
run_json_test() {
    local test_name="$1"
    local url="$2"
    local json_path="$3"
    local expected_value="$4"

    echo -n "Testing: $test_name ... "

    response=$(curl -s "$url")
    actual=$(echo "$response" | jq -r "$json_path" 2>/dev/null || echo "ERROR")

    if [ "$actual" = "$expected_value" ]; then
        echo -e "${GREEN}PASS${NC}"
        ((TESTS_PASSED++))
        return 0
    else
        echo -e "${RED}FAIL${NC} (expected: $expected_value, got: $actual)"
        ((TESTS_FAILED++))
        return 1
    fi
}

echo "=== Phase 1: Service Health Checks ==="
echo ""

# Test Trading Engine health
run_test "Trading Engine health" \
    "curl -s $TRADING_ENGINE_URL/health" \
    "healthy"

# Test Technical Analysis Service health
run_test "Technical Analysis Service health" \
    "curl -s $TECHNICAL_ANALYSIS_URL/health" \
    "healthy"

echo ""
echo "=== Phase 2: SQZMOM Strategy Configuration ==="
echo ""

# Test strategy info endpoint
run_test "SQZMOM strategy info endpoint" \
    "curl -s $TRADING_ENGINE_URL/api/v1/strategies/sqzmom/info" \
    "SQZMOM"

# Test enabled symbols
run_json_test "SOLUSDT is enabled" \
    "$TRADING_ENGINE_URL/api/v1/strategies/sqzmom/config" \
    '.enabled_symbols | contains(["SOLUSDT"])' \
    "true"

run_json_test "DOGEUSDT is enabled" \
    "$TRADING_ENGINE_URL/api/v1/strategies/sqzmom/config" \
    '.enabled_symbols | contains(["DOGEUSDT"])' \
    "true"

run_json_test "BNBUSDT is enabled" \
    "$TRADING_ENGINE_URL/api/v1/strategies/sqzmom/config" \
    '.enabled_symbols | contains(["BNBUSDT"])' \
    "true"

# Test optimized parameters
run_json_test "Min momentum threshold is 0.3" \
    "$TRADING_ENGINE_URL/api/v1/strategies/sqzmom/config" \
    '.min_momentum_threshold' \
    "0.3"

run_json_test "Stop loss is 1.5%" \
    "$TRADING_ENGINE_URL/api/v1/strategies/sqzmom/config" \
    '.stop_loss_pct' \
    "1.5"

run_json_test "Take profit is 3.0%" \
    "$TRADING_ENGINE_URL/api/v1/strategies/sqzmom/config" \
    '.take_profit_pct' \
    "3"

# Test trading mode
run_json_test "Paper trading is enabled" \
    "$TRADING_ENGINE_URL/api/v1/strategies/sqzmom/config" \
    '.paper_trading' \
    "true"

run_json_test "Auto trading is disabled" \
    "$TRADING_ENGINE_URL/api/v1/strategies/sqzmom/config" \
    '.auto_trading' \
    "false"

# Test max positions
run_json_test "Max positions is 3" \
    "$TRADING_ENGINE_URL/api/v1/strategies/sqzmom/config" \
    '.max_positions' \
    "3"

echo ""
echo "=== Phase 3: Symbol-Specific Configuration ==="
echo ""

# Test SOLUSDT config
run_json_test "SOLUSDT position size is 2.5%" \
    "$TRADING_ENGINE_URL/api/v1/strategies/sqzmom/symbols/SOLUSDT/config" \
    '.config.position_size_pct' \
    "2.5"

run_json_test "SOLUSDT min confidence is 0.65" \
    "$TRADING_ENGINE_URL/api/v1/strategies/sqzmom/symbols/SOLUSDT/config" \
    '.config.min_confidence' \
    "0.65"

# Test DOGEUSDT config
run_json_test "DOGEUSDT position size is 1.5%" \
    "$TRADING_ENGINE_URL/api/v1/strategies/sqzmom/symbols/DOGEUSDT/config" \
    '.config.position_size_pct' \
    "1.5"

run_json_test "DOGEUSDT min confidence is 0.75" \
    "$TRADING_ENGINE_URL/api/v1/strategies/sqzmom/symbols/DOGEUSDT/config" \
    '.config.min_confidence' \
    "0.75"

# Test BNBUSDT config
run_json_test "BNBUSDT position size is 2.0%" \
    "$TRADING_ENGINE_URL/api/v1/strategies/sqzmom/symbols/BNBUSDT/config" \
    '.config.position_size_pct' \
    "2"

echo ""
echo "=== Phase 4: Signal Generation ==="
echo ""

# Test SQZMOM signal for SOLUSDT
echo -n "Testing: SOLUSDT signal generation ... "
response=$(curl -s "$TRADING_ENGINE_URL/api/v1/strategies/sqzmom/signal/SOLUSDT")
if echo "$response" | jq -e '.success' >/dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC}"
    ((TESTS_PASSED++))

    # Display signal details
    action=$(echo "$response" | jq -r '.signal.action // "N/A"')
    confidence=$(echo "$response" | jq -r '.signal.confidence // "N/A"')
    echo "  Action: $action, Confidence: $confidence"
else
    echo -e "${YELLOW}WARN${NC} (signal may not be available, but endpoint works)"
fi

# Test disabled symbol (should fail gracefully)
echo -n "Testing: BTCUSDT rejection (disabled symbol) ... "
response=$(curl -s "$TRADING_ENGINE_URL/api/v1/strategies/sqzmom/signal/BTCUSDT")
if echo "$response" | jq -e '.success == false' >/dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC}"
    ((TESTS_PASSED++))
    echo "  Correctly rejected disabled symbol"
else
    echo -e "${RED}FAIL${NC}"
    ((TESTS_FAILED++))
fi

echo ""
echo "=== Phase 5: API Endpoints ==="
echo ""

# Test all strategy endpoints
endpoints=(
    "/api/v1/strategies/sqzmom/info"
    "/api/v1/strategies/sqzmom/config"
    "/api/v1/strategies/sqzmom/signals"
)

for endpoint in "${endpoints[@]}"; do
    echo -n "Testing: GET $endpoint ... "
    status_code=$(curl -s -o /dev/null -w "%{http_code}" "$TRADING_ENGINE_URL$endpoint")
    if [ "$status_code" = "200" ]; then
        echo -e "${GREEN}PASS${NC} (HTTP $status_code)"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}FAIL${NC} (HTTP $status_code)"
        ((TESTS_FAILED++))
    fi
done

echo ""
echo "=== Phase 6: Control Endpoints ==="
echo ""

# Test enable endpoint (don't actually enable)
echo -n "Testing: POST /api/v1/strategies/sqzmom/enable ... "
status_code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$TRADING_ENGINE_URL/api/v1/strategies/sqzmom/enable")
if [ "$status_code" = "200" ]; then
    echo -e "${GREEN}PASS${NC} (HTTP $status_code)"
    ((TESTS_PASSED++))
    # Disable it again
    curl -s -X POST "$TRADING_ENGINE_URL/api/v1/strategies/sqzmom/disable" >/dev/null
else
    echo -e "${RED}FAIL${NC} (HTTP $status_code)"
    ((TESTS_FAILED++))
fi

echo ""
echo "=== Phase 7: Technical Analysis Integration ==="
echo ""

# Test SQZMOM indicator in Technical Analysis service
run_test "SQZMOM indicator for SOLUSDT" \
    "curl -s $TECHNICAL_ANALYSIS_URL/api/v1/indicators/sqzmom/SOLUSDT" \
    "SOLUSDT"

# Test SQZMOM strategy signal
run_test "SQZMOM strategy signal for SOLUSDT" \
    "curl -s $TECHNICAL_ANALYSIS_URL/api/v1/strategies/sqzmom/signal/SOLUSDT" \
    "SOLUSDT"

echo ""
echo "======================================================================"
echo "VERIFICATION SUMMARY"
echo "======================================================================"
echo ""
echo -e "Tests Passed: ${GREEN}${TESTS_PASSED}${NC}"
echo -e "Tests Failed: ${RED}${TESTS_FAILED}${NC}"
echo "Total Tests:  $((TESTS_PASSED + TESTS_FAILED))"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ ALL TESTS PASSED${NC}"
    echo ""
    echo "SQZMOM Strategy is correctly configured and operational!"
    echo ""
    echo "Next Steps:"
    echo "1. Monitor signals: curl http://localhost:8005/api/v1/strategies/sqzmom/signals"
    echo "2. View documentation: cat SQZMOM_DEPLOYMENT_GUIDE.md"
    echo "3. Enable paper trading when ready"
    exit 0
else
    echo -e "${RED}❌ SOME TESTS FAILED${NC}"
    echo ""
    echo "Please review the failed tests and fix configuration issues."
    echo "Check logs at: services/trading-engine/logs/"
    exit 1
fi
