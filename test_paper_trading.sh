#!/bin/bash
# Extended Paper Trading Test Script
# Tests complete trading flow across all services

set -e

echo "=================================================================="
echo "     CRYPTO TRADING BOT - EXTENDED PAPER TRADING TEST"
echo "=================================================================="
echo ""
echo "This test will:"
echo "  1. Fetch real-time market data"
echo "  2. Generate trading signals"
echo "  3. Execute paper trades via Trading Engine"
echo "  4. Track positions in Portfolio Manager"
echo "  5. Calculate performance metrics"
echo "  6. Test rebalancing recommendations"
echo ""
echo "Starting test at $(date)"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Service URLs
MARKET_DATA_URL="http://localhost:8003"
TECHNICAL_ANALYSIS_URL="http://localhost:8004"
TRADING_ENGINE_URL="http://localhost:8005"
PORTFOLIO_MANAGER_URL="http://localhost:8006"

# Test symbols
SYMBOLS=("BTCUSDT" "ETHUSDT")
INTERVAL="60"

test_count=0
pass_count=0
fail_count=0

# Helper functions
log_step() {
    echo -e "${BLUE}===> $1${NC}"
}

log_success() {
    echo -e "${GREEN}✓ $1${NC}"
    ((pass_count++))
}

log_error() {
    echo -e "${RED}✗ $1${NC}"
    ((fail_count++))
}

log_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

# Check service health
check_services() {
    log_step "Step 1: Checking Service Health"

    services=(
        "Market Data:$MARKET_DATA_URL"
        "Technical Analysis:$TECHNICAL_ANALYSIS_URL"
        "Trading Engine:$TRADING_ENGINE_URL"
        "Portfolio Manager:$PORTFOLIO_MANAGER_URL"
    )

    all_healthy=true
    for service in "${services[@]}"; do
        name="${service%%:*}"
        url="${service#*:}"

        status=$(curl -s -o /dev/null -w "%{http_code}" "$url/health" 2>/dev/null)
        if [ "$status" = "200" ]; then
            log_success "$name is healthy"
        else
            log_error "$name is not responding"
            all_healthy=false
        fi
    done

    if [ "$all_healthy" = false ]; then
        echo ""
        echo "ERROR: Not all services are healthy. Exiting."
        exit 1
    fi

    echo ""
}

# Get initial portfolio state
get_initial_state() {
    log_step "Step 2: Recording Initial Portfolio State"

    initial_portfolio=$(curl -s "$PORTFOLIO_MANAGER_URL/api/v1/portfolio")
    initial_balance=$(echo "$initial_portfolio" | python3 -c "import sys, json; print(json.load(sys.stdin)['portfolio']['cash_balance'])")
    initial_value=$(echo "$initial_portfolio" | python3 -c "import sys, json; print(json.load(sys.stdin)['portfolio']['total_value'])")

    log_info "Initial Cash Balance: \$$initial_balance"
    log_info "Initial Total Value: \$$initial_value"

    echo ""
}

# Fetch market data
fetch_market_data() {
    log_step "Step 3: Fetching Real-Time Market Data"

    for symbol in "${SYMBOLS[@]}"; do
        echo -n "  Fetching $symbol... "

        ticker=$(curl -s "$MARKET_DATA_URL/api/v1/ticker/$symbol")
        price=$(echo "$ticker" | python3 -c "import sys, json; print(json.load(sys.stdin).get('last_price', 'N/A'))" 2>/dev/null || echo "N/A")

        if [ "$price" != "N/A" ]; then
            echo -e "${GREEN}$price${NC}"
            eval "${symbol}_PRICE=$price"
        else
            echo -e "${RED}Failed${NC}"
        fi
    done

    echo ""
}

# Generate trading signals
generate_signals() {
    log_step "Step 4: Generating Trading Signals"

    for symbol in "${SYMBOLS[@]}"; do
        echo "  Analyzing $symbol..."

        signal_response=$(curl -s "$TRADING_ENGINE_URL/api/v1/signals/$symbol?interval=$INTERVAL")

        if command -v python3 &> /dev/null; then
            action=$(echo "$signal_response" | python3 -c "import sys, json; print(json.load(sys.stdin)['signal']['action'])" 2>/dev/null || echo "ERROR")
            confidence=$(echo "$signal_response" | python3 -c "import sys, json; print(json.load(sys.stdin)['signal']['confidence'])" 2>/dev/null || echo "0")
            score=$(echo "$signal_response" | python3 -c "import sys, json; print(json.load(sys.stdin)['signal']['aggregated_score'])" 2>/dev/null || echo "0")
            consensus=$(echo "$signal_response" | python3 -c "import sys, json; print(json.load(sys.stdin)['signal']['consensus_count'])" 2>/dev/null || echo "0")

            log_info "  Action: $action | Confidence: $confidence | Score: $score | Consensus: $consensus/5"

            # Store signal for later
            eval "${symbol}_ACTION=$action"
            eval "${symbol}_CONFIDENCE=$confidence"
        fi
    done

    echo ""
}

# Execute paper trades
execute_trades() {
    log_step "Step 5: Executing Paper Trades"

    # Test BUY for BTC if we have a strong enough signal
    if [ "$BTCUSDT_ACTION" = "BUY" ] || [ "$BTCUSDT_ACTION" = "HOLD" ]; then
        log_info "Executing TEST BUY for BTCUSDT (0.05 BTC)"

        buy_response=$(curl -s -X POST "$PORTFOLIO_MANAGER_URL/api/v1/transaction/buy?portfolio_id=default&symbol=BTCUSDT&quantity=0.05")

        success=$(echo "$buy_response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('success', False))" 2>/dev/null || echo "false")

        if [ "$success" = "True" ]; then
            log_success "BUY BTCUSDT executed successfully"
        else
            message=$(echo "$buy_response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('error', 'Unknown error'))" 2>/dev/null)
            log_error "BUY BTCUSDT failed: $message"
        fi
    else
        log_info "Skipping BTCUSDT buy (signal: $BTCUSDT_ACTION)"
    fi

    # Small delay
    sleep 1

    # Test BUY for ETH
    if [ "$ETHUSDT_ACTION" = "BUY" ] || [ "$ETHUSDT_ACTION" = "HOLD" ]; then
        log_info "Executing TEST BUY for ETHUSDT (0.5 ETH)"

        buy_response=$(curl -s -X POST "$PORTFOLIO_MANAGER_URL/api/v1/transaction/buy?portfolio_id=default&symbol=ETHUSDT&quantity=0.5")

        success=$(echo "$buy_response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('success', False))" 2>/dev/null || echo "false")

        if [ "$success" = "True" ]; then
            log_success "BUY ETHUSDT executed successfully"
        else
            message=$(echo "$buy_response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('error', 'Unknown error'))" 2>/dev/null)
            log_error "BUY ETHUSDT failed: $message"
        fi
    else
        log_info "Skipping ETHUSDT buy (signal: $ETHUSDT_ACTION)"
    fi

    echo ""
}

# Sync with Trading Engine
sync_portfolio() {
    log_step "Step 6: Syncing Portfolio with Trading Engine"

    sync_response=$(curl -s -X POST "$PORTFOLIO_MANAGER_URL/api/v1/sync?portfolio_id=default")
    success=$(echo "$sync_response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('success', False))" 2>/dev/null || echo "false")

    if [ "$success" = "True" ]; then
        log_success "Portfolio synced successfully"
    else
        log_error "Portfolio sync failed"
    fi

    echo ""
}

# Check portfolio state
check_portfolio() {
    log_step "Step 7: Checking Portfolio State"

    portfolio=$(curl -s "$PORTFOLIO_MANAGER_URL/api/v1/portfolio")

    if command -v python3 &> /dev/null; then
        echo "$portfolio" | python3 << 'PYTHON'
import sys
import json

data = json.load(sys.stdin)
portfolio = data['portfolio']

print(f"  Portfolio ID: {portfolio['portfolio_id']}")
print(f"  Cash Balance: ${portfolio['cash_balance']}")
print(f"  Total Value: ${portfolio['total_value']}")
print(f"  Total P&L: ${portfolio['total_pnl']}")
print(f"  Return: {portfolio['total_return_pct']}%")
print(f"  Holdings: {len(portfolio['holdings'])}")

if portfolio['holdings']:
    print("\n  Holdings Detail:")
    for holding in portfolio['holdings']:
        print(f"    {holding['symbol']}: {holding['quantity']} @ ${holding['current_price']}")
        print(f"      Value: ${holding['current_value']} | P&L: ${holding['unrealized_pnl']} ({holding['unrealized_pnl_pct']}%)")
PYTHON
    fi

    echo ""
}

# Get performance metrics
check_performance() {
    log_step "Step 8: Calculating Performance Metrics"

    performance=$(curl -s "$PORTFOLIO_MANAGER_URL/api/v1/performance?portfolio_id=default")

    if command -v python3 &> /dev/null; then
        echo "$performance" | python3 << 'PYTHON'
import sys
import json

data = json.load(sys.stdin)
metrics = data['metrics']

print(f"  Total Return: ${metrics['total_return']} ({metrics['total_return_pct']}%)")
print(f"  Daily Return: ${metrics['daily_return']} ({metrics['daily_return_pct']}%)")
print(f"  Total Trades: {metrics['total_trades']}")
print(f"  Winning Trades: {metrics['winning_trades']}")
print(f"  Win Rate: {metrics['win_rate']}%")
print(f"  Realized P&L: ${metrics['realized_pnl']}")
print(f"  Unrealized P&L: ${metrics['unrealized_pnl']}")

if metrics.get('sharpe_ratio'):
    print(f"  Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
if metrics.get('max_drawdown'):
    print(f"  Max Drawdown: {metrics['max_drawdown']:.2f}%")
PYTHON
    fi

    echo ""
}

# Check allocation
check_allocation() {
    log_step "Step 9: Checking Asset Allocation"

    allocation=$(curl -s "$PORTFOLIO_MANAGER_URL/api/v1/allocation?portfolio_id=default")

    if command -v python3 &> /dev/null; then
        needs_rebalancing=$(echo "$allocation" | python3 -c "import sys, json; print(json.load(sys.stdin).get('needs_rebalancing', False))")

        echo "$allocation" | python3 << 'PYTHON'
import sys
import json

data = json.load(sys.stdin)
allocations = data.get('allocations', {})

if allocations:
    print("  Current Allocation:")
    for symbol, pct in allocations.items():
        print(f"    {symbol}: {pct}%")
else:
    print("  No allocations yet (cash only)")
PYTHON

        if [ "$needs_rebalancing" = "True" ]; then
            log_info "Portfolio needs rebalancing"
        else
            log_info "Portfolio allocation is balanced"
        fi
    fi

    echo ""
}

# Test sell transaction
test_sell() {
    log_step "Step 10: Testing SELL Transaction"

    # Get current holdings
    holdings=$(curl -s "$PORTFOLIO_MANAGER_URL/api/v1/portfolio/holdings")
    has_btc=$(echo "$holdings" | python3 -c "import sys, json; holdings = json.load(sys.stdin)['holdings']; print(any(h['symbol'] == 'BTCUSDT' for h in holdings))" 2>/dev/null || echo "False")

    if [ "$has_btc" = "True" ]; then
        log_info "Executing TEST SELL for BTCUSDT (0.02 BTC)"

        sell_response=$(curl -s -X POST "$PORTFOLIO_MANAGER_URL/api/v1/transaction/sell?portfolio_id=default&symbol=BTCUSDT&quantity=0.02")

        success=$(echo "$sell_response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('success', False))" 2>/dev/null || echo "false")

        if [ "$success" = "True" ]; then
            realized_pnl=$(echo "$sell_response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('realized_pnl', 'N/A'))" 2>/dev/null)
            log_success "SELL BTCUSDT executed successfully (Realized P&L: \$$realized_pnl)"
        else
            message=$(echo "$sell_response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('error', 'Unknown error'))" 2>/dev/null)
            log_error "SELL BTCUSDT failed: $message"
        fi
    else
        log_info "Skipping SELL test (no BTCUSDT holdings)"
    fi

    echo ""
}

# Final portfolio state
final_state() {
    log_step "Step 11: Final Portfolio State"

    portfolio=$(curl -s "$PORTFOLIO_MANAGER_URL/api/v1/portfolio")

    if command -v python3 &> /dev/null; then
        echo "$portfolio" | python3 << 'PYTHON'
import sys
import json

data = json.load(sys.stdin)
portfolio = data['portfolio']

print("\n" + "="*60)
print("             FINAL PORTFOLIO SUMMARY")
print("="*60)
print(f"Cash Balance:    ${portfolio['cash_balance']}")
print(f"Total Value:     ${portfolio['total_value']}")
print(f"Total P&L:       ${portfolio['total_pnl']}")
print(f"Total Return:    {portfolio['total_return_pct']}%")
print(f"Active Holdings: {len(portfolio['holdings'])}")
print("="*60)

if portfolio['holdings']:
    print("\nActive Positions:")
    for holding in portfolio['holdings']:
        print(f"  • {holding['symbol']}: {holding['quantity']} (${holding['current_value']})")
        pnl_color = '\033[0;32m' if float(holding['unrealized_pnl']) >= 0 else '\033[0;31m'
        print(f"    P&L: {pnl_color}${holding['unrealized_pnl']} ({holding['unrealized_pnl_pct']}%)\033[0m")
print()
PYTHON
    fi
}

# Main execution
main() {
    check_services
    get_initial_state
    fetch_market_data
    generate_signals
    execute_trades
    sync_portfolio
    check_portfolio
    check_performance
    check_allocation
    test_sell
    final_state

    # Summary
    echo "=================================================================="
    echo "                    TEST SUMMARY"
    echo "=================================================================="
    echo -e "Test completed at: $(date)"
    echo -e "Total operations: $((pass_count + fail_count))"
    echo -e "${GREEN}Successful: $pass_count${NC}"
    echo -e "${RED}Failed: $fail_count${NC}"
    echo "=================================================================="
    echo ""

    if [ $fail_count -eq 0 ]; then
        echo -e "${GREEN}✓ ALL TESTS PASSED!${NC}"
        echo ""
        echo "Paper trading system is fully operational!"
        echo "Ready for extended testing and strategy development."
        return 0
    else
        echo -e "${RED}✗ SOME TESTS FAILED${NC}"
        echo ""
        echo "Please review the errors above and check service logs."
        return 1
    fi
}

# Run main function
main
exit $?
