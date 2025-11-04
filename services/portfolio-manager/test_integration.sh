#!/bin/bash
# Integration Test Script for Portfolio Manager
# Tests complete end-to-end flow

set -e

echo "=========================================="
echo "  Portfolio Manager Integration Test"
echo "=========================================="
echo ""

BASE_URL="http://localhost:8006"
PORTFOLIO_ID="default"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass_count=0
fail_count=0

# Test function
test_endpoint() {
    local name=$1
    local url=$2
    local method=${3:-GET}
    local expected_status=${4:-200}

    echo -n "Testing: $name... "

    if [ "$method" = "POST" ]; then
        response=$(curl -s -w "\n%{http_code}" -X POST "$url")
    else
        response=$(curl -s -w "\n%{http_code}" "$url")
    fi

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    if [ "$http_code" -eq "$expected_status" ]; then
        echo -e "${GREEN}PASS${NC} (HTTP $http_code)"
        ((pass_count++))
        return 0
    else
        echo -e "${RED}FAIL${NC} (HTTP $http_code, expected $expected_status)"
        echo "Response: $body"
        ((fail_count++))
        return 1
    fi
}

echo "=== Service Health Checks ==="
test_endpoint "Portfolio Manager Health" "$BASE_URL/health"
test_endpoint "Portfolio Manager Status" "$BASE_URL/status"
echo ""

echo "=== Portfolio Endpoints ==="
test_endpoint "Get Default Portfolio" "$BASE_URL/api/v1/portfolio?portfolio_id=$PORTFOLIO_ID"
test_endpoint "List All Portfolios" "$BASE_URL/api/v1/portfolios"
test_endpoint "Get Portfolio Balance" "$BASE_URL/api/v1/portfolio/balance?portfolio_id=$PORTFOLIO_ID"
test_endpoint "Get Portfolio Holdings" "$BASE_URL/api/v1/portfolio/holdings?portfolio_id=$PORTFOLIO_ID"
echo ""

echo "=== Performance Endpoints ==="
test_endpoint "Get Performance Metrics" "$BASE_URL/api/v1/performance?portfolio_id=$PORTFOLIO_ID"
test_endpoint "Get Asset Performance" "$BASE_URL/api/v1/performance/assets?portfolio_id=$PORTFOLIO_ID"
echo ""

echo "=== Allocation Endpoints ==="
test_endpoint "Get Portfolio Allocation" "$BASE_URL/api/v1/allocation?portfolio_id=$PORTFOLIO_ID"
test_endpoint "Get Rebalance Recommendations" "$BASE_URL/api/v1/rebalance?portfolio_id=$PORTFOLIO_ID"
echo ""

echo "=== Integration Tests ==="
test_endpoint "Sync with Trading Engine" "$BASE_URL/api/v1/sync?portfolio_id=$PORTFOLIO_ID" "POST"
echo ""

echo "=== Detailed Portfolio Analysis ===="
echo "Fetching complete portfolio data..."
portfolio_response=$(curl -s "$BASE_URL/api/v1/portfolio?portfolio_id=$PORTFOLIO_ID")

if command -v python3 &> /dev/null; then
    echo "$portfolio_response" | python3 -m json.tool | head -50

    # Extract key metrics
    cash=$(echo "$portfolio_response" | python3 -c "import sys, json; print(json.load(sys.stdin)['portfolio']['cash_balance'])" 2>/dev/null || echo "N/A")
    total_value=$(echo "$portfolio_response" | python3 -c "import sys, json; print(json.load(sys.stdin)['portfolio']['total_value'])" 2>/dev/null || echo "N/A")
    total_pnl=$(echo "$portfolio_response" | python3 -c "import sys, json; print(json.load(sys.stdin)['portfolio']['total_pnl'])" 2>/dev/null || echo "N/A")
    return_pct=$(echo "$portfolio_response" | python3 -c "import sys, json; print(json.load(sys.stdin)['portfolio']['total_return_pct'])" 2>/dev/null || echo "N/A")

    echo ""
    echo -e "${YELLOW}=== Portfolio Summary ===${NC}"
    echo "  Cash Balance: \$$cash"
    echo "  Total Value: \$$total_value"
    echo "  Total P&L: \$$total_pnl"
    echo "  Return: $return_pct%"
else
    echo "$portfolio_response"
fi

echo ""
echo "=========================================="
echo "  Test Results Summary"
echo "=========================================="
echo -e "${GREEN}Passed: $pass_count${NC}"
echo -e "${RED}Failed: $fail_count${NC}"
echo "Total: $((pass_count + fail_count))"
echo ""

if [ $fail_count -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests failed${NC}"
    exit 1
fi
