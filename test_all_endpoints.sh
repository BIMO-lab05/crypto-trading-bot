#!/bin/bash
# Testing Guardian - Comprehensive Endpoint Testing Suite
# Version: 1.0
# Date: 2025-11-19

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test configuration
API_BASE="http://localhost:8000"
TEST_SYMBOL="BTCUSDT"
TEST_SYMBOL_2="ETHUSDT"
TIMEOUT=10

# Test results tracking
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
declare -a FAILED_ENDPOINTS
declare -a RESPONSE_TIMES

# Helper function to print test section
print_section() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

# Helper function to test endpoint
test_endpoint() {
    local method=$1
    local endpoint=$2
    local description=$3
    local expected_status=${4:-200}

    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    # Make request and capture response time
    START_TIME=$(date +%s%N)
    HTTP_CODE=$(curl -s -o /tmp/response.json -w "%{http_code}" \
                     -X "$method" \
                     --max-time "$TIMEOUT" \
                     "$API_BASE$endpoint" 2>/dev/null || echo "000")
    END_TIME=$(date +%s%N)
    RESPONSE_TIME=$(( (END_TIME - START_TIME) / 1000000 ))

    RESPONSE_TIMES+=("$endpoint:$RESPONSE_TIME")

    # Check result
    if [ "$HTTP_CODE" = "$expected_status" ]; then
        echo -e "${GREEN}✅ PASS${NC} [$RESPONSE_TIME ms] $method $endpoint - $description"
        PASSED_TESTS=$((PASSED_TESTS + 1))

        # Show response preview for some endpoints
        if [ -f /tmp/response.json ]; then
            echo "    Response: $(cat /tmp/response.json | jq -c . 2>/dev/null | head -c 100)..."
        fi
    else
        echo -e "${RED}❌ FAIL${NC} [$RESPONSE_TIME ms] $method $endpoint - $description"
        echo "    Expected: $expected_status, Got: $HTTP_CODE"
        if [ -f /tmp/response.json ]; then
            echo "    Response: $(cat /tmp/response.json)"
        fi
        FAILED_TESTS=$((FAILED_TESTS + 1))
        FAILED_ENDPOINTS+=("$endpoint (expected $expected_status, got $HTTP_CODE)")
    fi
}

# Start test execution
clear
echo -e "${YELLOW}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════════════════╗
║                    Testing Guardian Agent v1.0                        ║
║                  Comprehensive API Endpoint Testing                   ║
╚═══════════════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

echo "Test Configuration:"
echo "  API Base URL: $API_BASE"
echo "  Test Symbols: $TEST_SYMBOL, $TEST_SYMBOL_2"
echo "  Timeout: ${TIMEOUT}s per request"
echo ""

# Check if API Gateway is accessible
echo -n "Checking API Gateway connectivity... "
if curl -s --max-time 5 "$API_BASE/health" > /dev/null 2>&1; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
    echo "Error: Cannot connect to API Gateway at $API_BASE"
    exit 1
fi

# ============================================================================
# CORE ENDPOINTS
# ============================================================================
print_section "1. Core Endpoints"

test_endpoint "GET" "/" "Root endpoint" 200
test_endpoint "GET" "/health" "Health check" 200

# ============================================================================
# MARKET DATA ENDPOINTS
# ============================================================================
print_section "2. Market Data Endpoints"

test_endpoint "GET" "/api/market/ticker/$TEST_SYMBOL" "Get ticker for BTC" 200
test_endpoint "GET" "/api/market/ticker/$TEST_SYMBOL_2" "Get ticker for ETH" 200
test_endpoint "GET" "/api/market/kline/$TEST_SYMBOL?interval=60&limit=100" "Get kline data" 200

# ============================================================================
# TECHNICAL ANALYSIS ENDPOINTS
# ============================================================================
print_section "3. Technical Analysis Endpoints"

test_endpoint "GET" "/api/analysis/rsi/$TEST_SYMBOL?interval=60&period=14" "Get RSI indicator" 200
test_endpoint "GET" "/api/analysis/macd/$TEST_SYMBOL?interval=60" "Get MACD indicator" 200
test_endpoint "GET" "/api/analysis/all/$TEST_SYMBOL?interval=60" "Get all indicators" 200

# ============================================================================
# MULTI-TIMEFRAME ANALYSIS ENDPOINTS (NEW)
# ============================================================================
print_section "4. Multi-Timeframe Analysis Endpoints (NEW)"

test_endpoint "GET" "/api/analysis/multi-timeframe/$TEST_SYMBOL" "Multi-timeframe analysis BTC" 200
test_endpoint "GET" "/api/analysis/multi-timeframe/$TEST_SYMBOL_2" "Multi-timeframe analysis ETH" 200
test_endpoint "GET" "/api/analysis/indicators/signal/$TEST_SYMBOL" "Indicator signal strength" 200

# ============================================================================
# TRADING ENGINE ENDPOINTS
# ============================================================================
print_section "5. Trading Engine Endpoints"

test_endpoint "GET" "/api/trading/signals/$TEST_SYMBOL?interval=60" "Get trading signal" 200
test_endpoint "GET" "/api/trading/positions?status=open" "Get open positions" 200

# ============================================================================
# ENHANCED TRADING SIGNALS (NEW)
# ============================================================================
print_section "6. Enhanced Trading Signals (NEW)"

test_endpoint "GET" "/api/trading/signals/enhanced/$TEST_SYMBOL" "Enhanced signal BTC" 200
test_endpoint "GET" "/api/trading/signals/enhanced/$TEST_SYMBOL_2" "Enhanced signal ETH" 200

# ============================================================================
# PORTFOLIO ENDPOINTS
# ============================================================================
print_section "7. Portfolio Endpoints"

test_endpoint "GET" "/api/portfolio?portfolio_id=default" "Get portfolio details" 200
test_endpoint "GET" "/api/portfolio/balance?portfolio_id=default" "Get portfolio balance" 200
test_endpoint "GET" "/api/portfolio/holdings?portfolio_id=default" "Get portfolio holdings" 200
test_endpoint "GET" "/api/portfolio/performance?portfolio_id=default" "Get performance metrics" 200

# ============================================================================
# PORTFOLIO TRADES ENDPOINT (NEW)
# ============================================================================
print_section "8. Portfolio Trades Endpoint (NEW)"

test_endpoint "GET" "/api/portfolio/trades?portfolio_id=default" "Get all trades" 200
test_endpoint "GET" "/api/portfolio/trades?portfolio_id=default&limit=10" "Get last 10 trades" 200
test_endpoint "GET" "/api/portfolio/trades?portfolio_id=default&symbol=$TEST_SYMBOL" "Get BTC trades only" 200

# ============================================================================
# ML PREDICTION ENDPOINTS (NEW)
# ============================================================================
print_section "9. ML Prediction Endpoints (NEW)"

test_endpoint "GET" "/api/ml/predict/price/$TEST_SYMBOL?interval=60&model_type=LSTM" "ML price prediction BTC" 200
test_endpoint "GET" "/api/ml/predict/price/$TEST_SYMBOL_2?interval=60&model_type=LSTM" "ML price prediction ETH" 200
test_endpoint "GET" "/api/ml/predict/trend/$TEST_SYMBOL?interval=60" "ML trend prediction" 200
test_endpoint "GET" "/api/ml/predict/volatility/$TEST_SYMBOL?interval=60" "ML volatility forecast" 200
test_endpoint "GET" "/api/ml/predict/signal/$TEST_SYMBOL?interval=60" "ML trading signal" 200
test_endpoint "GET" "/api/ml/models" "List all ML models" 200
test_endpoint "GET" "/api/ml/models/$TEST_SYMBOL?interval=60&model_type=LSTM" "Get specific model info" 200

# ============================================================================
# SENTIMENT ANALYSIS ENDPOINTS (NEW)
# ============================================================================
print_section "10. Sentiment Analysis Endpoints (NEW)"

test_endpoint "GET" "/api/sentiment/news/$TEST_SYMBOL" "News sentiment BTC" 200
test_endpoint "GET" "/api/sentiment/social/$TEST_SYMBOL" "Social sentiment BTC" 200
test_endpoint "GET" "/api/sentiment/combined/$TEST_SYMBOL" "Combined sentiment BTC" 200
test_endpoint "GET" "/api/sentiment/trend/$TEST_SYMBOL" "Sentiment trend BTC" 200
test_endpoint "GET" "/api/sentiment/$TEST_SYMBOL" "Overall sentiment (legacy)" 200
test_endpoint "GET" "/api/sentiment/aggregate" "Aggregate market sentiment" 200

# ============================================================================
# RISK & METRICS ENDPOINTS
# ============================================================================
print_section "11. Risk & Metrics Endpoints"

test_endpoint "GET" "/api/risk/scorecard" "Risk scorecard" 200
test_endpoint "GET" "/api/risk/capital" "Capital metrics" 200
test_endpoint "GET" "/api/risk/exposure" "Exposure metrics" 200
test_endpoint "GET" "/api/risk/drawdown" "Drawdown metrics" 200
test_endpoint "GET" "/api/risk/var?confidence_level=0.95&time_horizon_days=1" "Value at Risk" 200
test_endpoint "GET" "/api/performance/metrics" "Performance metrics" 200
test_endpoint "GET" "/api/performance/sharpe" "Sharpe ratio" 200
test_endpoint "GET" "/api/risk/alerts" "Active alerts" 200
test_endpoint "GET" "/api/risk/circuit-breaker" "Circuit breaker status" 200

# ============================================================================
# DASHBOARD AGGREGATION
# ============================================================================
print_section "12. Dashboard Aggregation"

test_endpoint "GET" "/api/dashboard/$TEST_SYMBOL?interval=60" "Aggregated dashboard data" 200

# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================
print_section "13. Error Handling Tests"

test_endpoint "GET" "/api/market/ticker/INVALID" "Invalid symbol ticker" 404
test_endpoint "GET" "/api/ml/predict/price/FAKESYMBOL" "Invalid symbol ML prediction" 404
test_endpoint "GET" "/api/sentiment/news/BADSYMBOL" "Invalid symbol sentiment" 404

# ============================================================================
# PERFORMANCE ANALYSIS
# ============================================================================
print_section "14. Performance Analysis"

echo "Response Time Statistics:"
echo ""

# Calculate average response time
TOTAL_TIME=0
COUNT=0
MAX_TIME=0
MAX_ENDPOINT=""

for entry in "${RESPONSE_TIMES[@]}"; do
    ENDPOINT=$(echo "$entry" | cut -d':' -f1)
    TIME=$(echo "$entry" | cut -d':' -f2)
    TOTAL_TIME=$((TOTAL_TIME + TIME))
    COUNT=$((COUNT + 1))

    if [ "$TIME" -gt "$MAX_TIME" ]; then
        MAX_TIME=$TIME
        MAX_ENDPOINT=$ENDPOINT
    fi

    # Highlight slow endpoints (>1000ms)
    if [ "$TIME" -gt 1000 ]; then
        echo -e "  ${YELLOW}⚠ SLOW${NC} $ENDPOINT: ${TIME}ms"
    fi
done

AVG_TIME=$((TOTAL_TIME / COUNT))
echo ""
echo "  Average Response Time: ${AVG_TIME}ms"
echo "  Slowest Endpoint: $MAX_ENDPOINT (${MAX_TIME}ms)"

# Performance rating
if [ "$AVG_TIME" -lt 200 ]; then
    echo -e "  Performance Rating: ${GREEN}EXCELLENT${NC}"
elif [ "$AVG_TIME" -lt 500 ]; then
    echo -e "  Performance Rating: ${GREEN}GOOD${NC}"
elif [ "$AVG_TIME" -lt 1000 ]; then
    echo -e "  Performance Rating: ${YELLOW}ACCEPTABLE${NC}"
else
    echo -e "  Performance Rating: ${RED}NEEDS IMPROVEMENT${NC}"
fi

# ============================================================================
# FINAL TEST REPORT
# ============================================================================
print_section "15. Final Test Report"

echo "Test Execution Summary:"
echo "  Total Tests: $TOTAL_TESTS"
echo -e "  Passed: ${GREEN}$PASSED_TESTS${NC}"
echo -e "  Failed: ${RED}$FAILED_TESTS${NC}"
echo ""

SUCCESS_RATE=$((PASSED_TESTS * 100 / TOTAL_TESTS))
echo "  Success Rate: ${SUCCESS_RATE}%"
echo ""

if [ $FAILED_TESTS -gt 0 ]; then
    echo -e "${RED}Failed Endpoints:${NC}"
    for endpoint in "${FAILED_ENDPOINTS[@]}"; do
        echo "  - $endpoint"
    done
    echo ""
fi

# Quality Gates
echo "Quality Gates:"
if [ "$SUCCESS_RATE" -ge 95 ]; then
    echo -e "  ${GREEN}✅ Success Rate >= 95%${NC}"
else
    echo -e "  ${RED}❌ Success Rate < 95%${NC}"
fi

if [ "$AVG_TIME" -le 1000 ]; then
    echo -e "  ${GREEN}✅ Average Response Time <= 1s${NC}"
else
    echo -e "  ${RED}❌ Average Response Time > 1s${NC}"
fi

echo ""

# Overall result
if [ $FAILED_TESTS -eq 0 ]; then
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                        ✅ ALL TESTS PASSED                            ║${NC}"
    echo -e "${GREEN}║                   System is Production Ready                          ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════════════╝${NC}"
    exit 0
else
    echo -e "${RED}╔═══════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║                        ❌ TESTS FAILED                                ║${NC}"
    echo -e "${RED}║                  Please Review Failed Endpoints                        ║${NC}"
    echo -e "${RED}╚═══════════════════════════════════════════════════════════════════════╝${NC}"
    exit 1
fi
