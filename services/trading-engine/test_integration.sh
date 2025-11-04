#!/bin/bash
# Integration Test Script for Trading Engine
# Tests complete end-to-end flow across all services

set -e

echo "=========================================="
echo "  Trading Engine Integration Test"
echo "=========================================="
echo ""

BASE_URL="http://localhost:8005"
SYMBOL="BTCUSDT"
INTERVAL="60"

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
    local expected_status=${3:-200}

    echo -n "Testing: $name... "

    response=$(curl -s -w "\n%{http_code}" "$url")
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
test_endpoint "Trading Engine Health" "$BASE_URL/health"
test_endpoint "Trading Engine Status" "$BASE_URL/status"
echo ""

echo "=== Signal Analysis Tests ==="
test_endpoint "Get Trading Signal" "$BASE_URL/api/v1/signals/$SYMBOL?interval=$INTERVAL"
echo ""

echo "=== Position Management Tests ==="
test_endpoint "List All Positions" "$BASE_URL/api/v1/positions?status=all"
test_endpoint "List Open Positions" "$BASE_URL/api/v1/positions?status=open"
test_endpoint "List Closed Positions" "$BASE_URL/api/v1/positions?status=closed"
echo ""

echo "=== Performance Metrics Tests ==="
test_endpoint "Get Performance Metrics" "$BASE_URL/api/v1/performance"
echo ""

echo "=== Detailed Signal Analysis ==="
echo "Fetching complete signal data..."
signal_response=$(curl -s "$BASE_URL/api/v1/signals/$SYMBOL?interval=$INTERVAL")

if command -v python3 &> /dev/null; then
    echo "$signal_response" | python3 -m json.tool | head -50

    # Extract key metrics
    action=$(echo "$signal_response" | python3 -c "import sys, json; print(json.load(sys.stdin)['signal']['action'])" 2>/dev/null || echo "N/A")
    confidence=$(echo "$signal_response" | python3 -c "import sys, json; print(json.load(sys.stdin)['signal']['confidence'])" 2>/dev/null || echo "N/A")
    score=$(echo "$signal_response" | python3 -c "import sys, json; print(json.load(sys.stdin)['signal']['aggregated_score'])" 2>/dev/null || echo "N/A")
    consensus=$(echo "$signal_response" | python3 -c "import sys, json; print(json.load(sys.stdin)['signal']['consensus_count'])" 2>/dev/null || echo "N/A")

    echo ""
    echo -e "${YELLOW}=== Signal Summary ===${NC}"
    echo "  Action: $action"
    echo "  Confidence: $confidence"
    echo "  Aggregated Score: $score"
    echo "  Consensus: $consensus/5 indicators"
else
    echo "$signal_response"
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
