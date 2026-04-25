#!/bin/bash
#
# Frontend-Backend Integration Test Script
# Purpose: Validate that frontend can access all required backend endpoints
# Date: 2025-12-15
#

echo "========================================="
echo "Frontend-Backend Integration Test"
echo "========================================="
echo ""

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Helper function to test endpoint
test_endpoint() {
    local name="$1"
    local url="$2"
    local expected_status="${3:-200}"

    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    echo -n "Testing $name... "

    # Make request and capture response
    response=$(curl -s -w "\n%{http_code}" "$url")
    status_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    # Check status code
    if [ "$status_code" -eq "$expected_status" ]; then
        # Check if response is valid JSON (for API endpoints)
        if echo "$body" | python3 -m json.tool &>/dev/null || [ "$expected_status" -ne 200 ]; then
            echo -e "${GREEN}✓ PASS${NC} (HTTP $status_code)"
            PASSED_TESTS=$((PASSED_TESTS + 1))
            return 0
        else
            echo -e "${RED}✗ FAIL${NC} (Invalid JSON response)"
            FAILED_TESTS=$((FAILED_TESTS + 1))
            return 1
        fi
    else
        echo -e "${RED}✗ FAIL${NC} (HTTP $status_code, expected $expected_status)"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return 1
    fi
}

echo "=== 1. Frontend Service ==="
test_endpoint "Frontend (React App)" "http://localhost:3000" 200
echo ""

echo "=== 2. API Gateway ==="
test_endpoint "API Gateway Health" "http://localhost:8000/health"
test_endpoint "API Gateway Root" "http://localhost:8000/"
echo ""

echo "=== 3. Portfolio Manager Endpoints ==="
test_endpoint "Portfolio Balance" "http://localhost:8000/api/v1/portfolio/balance"
test_endpoint "Active Positions" "http://localhost:8000/api/v1/portfolio/positions"
test_endpoint "Portfolio Status" "http://localhost:8003/status"
test_endpoint "Transaction History" "http://localhost:8003/api/v1/transactions?limit=10"
echo ""

echo "=== 4. Market Data Endpoints ==="
test_endpoint "Market Data Health" "http://localhost:8002/health"
test_endpoint "BNB Klines" "http://localhost:8002/api/v1/klines/BNBUSDT?interval=60&limit=10"
test_endpoint "SOL Klines" "http://localhost:8002/api/v1/klines/SOLUSDT?interval=60&limit=10"
test_endpoint "ADA Klines" "http://localhost:8002/api/v1/klines/ADAUSDT?interval=60&limit=10"
test_endpoint "BNB Ticker" "http://localhost:8002/api/v1/ticker/BNBUSDT"
echo ""

echo "=== 5. Technical Analysis Endpoints ==="
test_endpoint "TA Health" "http://localhost:8004/health"
test_endpoint "BNB RSI" "http://localhost:8004/api/v1/indicators/rsi/BNBUSDT?period=14&timeframe=60"
test_endpoint "SOL MACD" "http://localhost:8004/api/v1/indicators/macd/SOLUSDT?timeframe=60"
echo ""

echo "=== 6. Trading Engine Endpoints ==="
test_endpoint "Trading Engine Health" "http://localhost:8005/health"
test_endpoint "Trading Engine Status" "http://localhost:8005/status"
test_endpoint "Auto Trader Status" "http://localhost:8005/api/v1/auto-trader/status"
echo ""

echo "=== 7. ML Prediction Service ==="
test_endpoint "ML Service Health" "http://localhost:8007/health"
test_endpoint "ML Service Status" "http://localhost:8007/"
test_endpoint "BNB Prediction" "http://localhost:8007/api/v1/predict/BNBUSDT"
test_endpoint "SOL Prediction" "http://localhost:8007/api/v1/predict/SOLUSDT"
test_endpoint "ADA Prediction" "http://localhost:8007/api/v1/predict/ADAUSDT"
echo ""

echo "=== 8. Sentiment Analysis ==="
test_endpoint "Sentiment Health" "http://localhost:8008/health"
test_endpoint "BNB Sentiment" "http://localhost:8008/api/v1/sentiment/BNBUSDT"
echo ""

echo "=== 9. Risk Metrics ==="
test_endpoint "Risk Metrics Health" "http://localhost:8009/health"
test_endpoint "Portfolio Risk" "http://localhost:8009/api/v1/risk/portfolio"
echo ""

echo "=== 10. Notification Service ==="
test_endpoint "Notification Health" "http://localhost:8006/health"
test_endpoint "Notification Status" "http://localhost:8006/status"
echo ""

echo "=== 11. Bybit Connector ==="
test_endpoint "Bybit Connector Health" "http://localhost:8001/health"
test_endpoint "Bybit Account Balance" "http://localhost:8001/api/v1/account/balance"
echo ""

echo "========================================="
echo "Test Summary"
echo "========================================="
echo -e "Total Tests:  $TOTAL_TESTS"
echo -e "${GREEN}Passed:       $PASSED_TESTS${NC}"
echo -e "${RED}Failed:       $FAILED_TESTS${NC}"

SUCCESS_RATE=$((PASSED_TESTS * 100 / TOTAL_TESTS))
echo -e "Success Rate: $SUCCESS_RATE%"
echo ""

# Additional data inspection
echo "========================================="
echo "Sample Data Inspection"
echo "========================================="
echo ""

echo "Current Portfolio:"
curl -s http://localhost:8000/api/v1/portfolio/balance | python3 -m json.tool | grep -E '"cash_balance"|"total_value"|"unrealized_pnl"|"total_return_pct"'
echo ""

echo "Active Positions Count:"
curl -s http://localhost:8000/api/v1/portfolio/positions | python3 -m json.tool | grep -E '"count"'
echo ""

echo "Auto Trader Status:"
curl -s http://localhost:8005/api/v1/auto-trader/status | python3 -m json.tool | grep -E '"is_active"|"symbols_count"|"last_signal_time"'
echo ""

# Exit with appropriate code
if [ $FAILED_TESTS -eq 0 ]; then
    echo -e "${GREEN}All tests passed! Frontend should work correctly.${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed. Check endpoints above.${NC}"
    exit 1
fi
