#!/bin/bash
# =============================================================================
# SQZMOM Strategy Orchestration Setup Script
# Purpose: Register and activate SQZMOM strategy with orchestrator
# Created: 2025-12-12
# Usage: ./scripts/setup_sqzmom_strategy.sh
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
TRADING_ENGINE_URL="${TRADING_ENGINE_URL:-http://localhost:8005}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  SQZMOM Strategy Orchestration Setup${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to make API call
api_call() {
    local method="$1"
    local endpoint="$2"
    local data="$3"
    local description="$4"

    echo -e "${YELLOW}$description...${NC}"

    if [ "$method" == "POST" ]; then
        if [ -n "$data" ]; then
            response=$(curl -s -w "\n%{http_code}" -X POST "$TRADING_ENGINE_URL$endpoint" \
                -H "Content-Type: application/json" \
                -d "$data" 2>&1)
        else
            response=$(curl -s -w "\n%{http_code}" -X POST "$TRADING_ENGINE_URL$endpoint" 2>&1)
        fi
    else
        response=$(curl -s -w "\n%{http_code}" -X GET "$TRADING_ENGINE_URL$endpoint" 2>&1)
    fi

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    if [[ "$http_code" =~ ^2 ]]; then
        echo -e "  ${GREEN}SUCCESS${NC} (HTTP $http_code)"
        echo "  Response: $body"
        return 0
    else
        echo -e "  ${RED}FAILED${NC} (HTTP $http_code)"
        echo "  Error: $body"
        return 1
    fi
}

# Step 1: Check Trading Engine Health
echo -e "\n${BLUE}Step 1: Checking Trading Engine Health${NC}"
if ! api_call "GET" "/health" "" "Checking health"; then
    echo -e "${RED}Trading Engine is not healthy. Please start the service first.${NC}"
    exit 1
fi

# Step 2: Register SQZMOM Strategy
echo -e "\n${BLUE}Step 2: Registering SQZMOM Strategy${NC}"

register_data='{
    "strategy_id": "sqzmom_paper",
    "name": "SQZMOM Paper Trading",
    "strategy_type": "momentum",
    "description": "Squeeze Momentum strategy for paper trading validation",
    "symbols": ["BNBUSDT", "SOLUSDT", "ADAUSDT", "ARBUSDT", "OPUSDT", "POLUSDT", "SUIUSDT"],
    "allocation_pct": 100.0,
    "min_capital": 100.0,
    "max_positions": 7,
    "config": {
        "risk_per_trade": 0.02,
        "stop_loss_pct": 0.02,
        "take_profit_pct": 0.04,
        "max_daily_loss_pct": 0.05,
        "min_signal_confidence": 0.60,
        "enable_dynamic_risk": true
    }
}'

api_call "POST" "/api/v1/orchestration/strategies/register" "$register_data" "Registering SQZMOM strategy" || true

# Step 3: Configure Capital Allocation
echo -e "\n${BLUE}Step 3: Configuring Capital Allocation${NC}"

# Capital allocation - 33% each for top 3 performers
allocation_data='{
    "strategy_id": "sqzmom_paper",
    "allocation_method": "performance_weighted",
    "allocations": {
        "BNBUSDT": 0.16,
        "SOLUSDT": 0.16,
        "ADAUSDT": 0.14,
        "ARBUSDT": 0.14,
        "OPUSDT": 0.14,
        "POLUSDT": 0.13,
        "SUIUSDT": 0.13
    }
}'

api_call "POST" "/api/v1/orchestration/strategies/sqzmom_paper/allocations" "$allocation_data" "Setting capital allocation" || true

# Step 4: Activate Strategy
echo -e "\n${BLUE}Step 4: Activating SQZMOM Strategy${NC}"

api_call "POST" "/api/v1/orchestration/strategies/sqzmom_paper/activate" "" "Activating strategy" || true

# Step 5: Verify Strategy Status
echo -e "\n${BLUE}Step 5: Verifying Strategy Status${NC}"

api_call "GET" "/api/v1/orchestration/strategies/sqzmom_paper/status" "" "Getting strategy status" || true

# Step 6: Get Orchestrator Status
echo -e "\n${BLUE}Step 6: Getting Orchestrator Status${NC}"

api_call "GET" "/api/v1/orchestration/status" "" "Getting orchestrator status" || true

# Summary
echo -e "\n${BLUE}========================================${NC}"
echo -e "${GREEN}  Setup Complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "SQZMOM Strategy Configuration:"
echo "  - Strategy ID: sqzmom_paper"
echo "  - Symbols: BNBUSDT, SOLUSDT, ADAUSDT, ARBUSDT, OPUSDT, POLUSDT, SUIUSDT"
echo "  - Risk per trade: 2%"
echo "  - Stop loss: 2%"
echo "  - Take profit: 4%"
echo "  - Max daily loss: 5%"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "  1. Monitor paper trading via dashboard"
echo "  2. Check alerts via notification service"
echo "  3. Review daily P&L summaries"
echo "  4. Validate for 2 weeks before going live"
echo ""
echo "Useful Commands:"
echo "  # Check strategy status"
echo "  curl $TRADING_ENGINE_URL/api/v1/orchestration/strategies/sqzmom_paper/status"
echo ""
echo "  # Get paper trading balance"
echo "  curl $TRADING_ENGINE_URL/api/v1/trading/paper/balance"
echo ""
echo "  # Get today's trades"
echo "  curl $TRADING_ENGINE_URL/api/v1/trading/paper/trades?date=$(date +%Y-%m-%d)"
