#!/bin/bash
# ============================================================================
# Paper Trading Monitor for Statistical Arbitrage
# Purpose: Real-time monitoring of paper trading activities and performance
# Usage: ./monitor_paper_trading.sh [--continuous] [--interval 30] [--json]
# Author: DevOps Automation Agent
# Date: 2025-12-11
# ============================================================================

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs/paper_trading"
mkdir -p "$LOG_DIR"

# Service endpoints
TRADING_ENGINE_URL="http://localhost:8005"
BYBIT_CONNECTOR_URL="http://localhost:8001"
MARKET_DATA_URL="http://localhost:8002"
STAT_ARB_ENDPOINT="$TRADING_ENGINE_URL/api/v1/statistical-arbitrage"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'
BOLD='\033[1m'

# Default settings
CONTINUOUS=false
INTERVAL=30
JSON_OUTPUT=false
SHOW_LOGS=true
LOG_LINES=15

# Function to print section header
print_header() {
    local title=$1
    echo ""
    echo -e "${BLUE}${BOLD}=== $title ===${NC}"
    echo ""
}

# Function to fetch stat arb status
fetch_stat_arb_status() {
    curl -s --max-time 5 "$STAT_ARB_ENDPOINT/status" 2>/dev/null
}

# Function to fetch performance metrics
fetch_performance() {
    curl -s --max-time 5 "$STAT_ARB_ENDPOINT/performance" 2>/dev/null
}

# Function to display manager status
display_manager_status() {
    local response=$(fetch_stat_arb_status)

    if [ -z "$response" ]; then
        echo -e "${RED}Error: Unable to fetch Statistical Arbitrage status${NC}"
        return 1
    fi

    python3 << EOF
import json
import sys
from datetime import datetime

try:
    data = json.loads('''$response''')
    status = data.get('status', 'unknown')
    manager = data.get('manager_status', {}).get('manager', {})
    allocation = data.get('manager_status', {}).get('allocation', {})
    strategies = data.get('manager_status', {}).get('strategies', {})
    timestamp = data.get('timestamp', '')

    # Status color
    if status == 'active':
        status_display = '\033[0;32mACTIVE\033[0m'
    elif status == 'not_initialized':
        status_display = '\033[1;33mNOT INITIALIZED\033[0m'
    else:
        status_display = f'\033[0;31m{status.upper()}\033[0m'

    print(f"Status:           {status_display}")
    print(f"Timestamp:        {timestamp[:19] if timestamp else 'N/A'}")
    print("")

    # Capital Info
    total_capital = manager.get('total_capital', 0)
    allocated_capital = manager.get('allocated_capital', 0)
    total_profit = manager.get('total_profit', 0)
    total_trades = manager.get('total_trades', 0)
    win_rate = manager.get('win_rate', 0)

    print(f"Total Capital:    \${total_capital:,.2f}")
    print(f"Allocated:        \${allocated_capital:,.2f} ({allocated_capital/total_capital*100 if total_capital > 0 else 0:.1f}%)")
    print(f"Total P&L:        {'+'if total_profit >= 0 else ''}\${total_profit:,.2f}")

    # ROI calculation
    roi = (total_profit / total_capital * 100) if total_capital > 0 else 0
    roi_color = '\033[0;32m' if roi >= 0 else '\033[0;31m'
    print(f"ROI:              {roi_color}{roi:+.2f}%\033[0m")

    print(f"Total Trades:     {total_trades}")
    print(f"Win Rate:         {win_rate:.1%}")
    print("")

    # Allocation
    print("Capital Allocation:")
    pairs_alloc = allocation.get('pairs_trading', 0) * 100
    funding_alloc = allocation.get('funding_rate', 0) * 100
    triangular_alloc = allocation.get('triangular', 0) * 100
    print(f"  Pairs Trading:      {pairs_alloc:.0f}%")
    print(f"  Funding Rate:       {funding_alloc:.0f}%")
    print(f"  Triangular:         {triangular_alloc:.0f}%")

except json.JSONDecodeError:
    print("\033[0;31mError: Invalid JSON response\033[0m")
    sys.exit(1)
except Exception as e:
    print(f"\033[0;31mError: {e}\033[0m")
    sys.exit(1)
EOF
}

# Function to display active strategies
display_active_strategies() {
    local response=$(fetch_stat_arb_status)

    if [ -z "$response" ]; then
        echo -e "${RED}Error: Unable to fetch strategies${NC}"
        return 1
    fi

    python3 << EOF
import json
import sys

try:
    data = json.loads('''$response''')
    strategies = data.get('manager_status', {}).get('strategies', {})

    # Pairs Trading
    pairs = strategies.get('pairs', {})
    pairs_enabled = pairs.get('enabled', False)
    pairs_count = pairs.get('count', 0)
    pairs_ids = pairs.get('strategy_ids', [])

    status_icon = '\033[0;32m[ON]\033[0m' if pairs_enabled else '\033[0;31m[OFF]\033[0m'
    print(f"Pairs Trading:     {status_icon} {pairs_count} strategies")
    if pairs_ids:
        for pid in pairs_ids[:5]:  # Show first 5
            print(f"                   - {pid}")
        if len(pairs_ids) > 5:
            print(f"                   ... and {len(pairs_ids) - 5} more")

    # Funding Rate
    funding = strategies.get('funding', {})
    funding_enabled = funding.get('enabled', False)
    funding_count = funding.get('count', 0)
    funding_ids = funding.get('strategy_ids', [])

    status_icon = '\033[0;32m[ON]\033[0m' if funding_enabled else '\033[0;31m[OFF]\033[0m'
    print(f"Funding Rate:      {status_icon} {funding_count} strategies")
    if funding_ids:
        for fid in funding_ids[:5]:
            print(f"                   - {fid}")

    # Triangular
    triangular = strategies.get('triangular', {})
    triangular_enabled = triangular.get('enabled', False)
    triangular_configured = triangular.get('configured', False)
    num_paths = triangular.get('num_paths', 0)

    status_icon = '\033[0;32m[ON]\033[0m' if triangular_enabled else '\033[0;31m[OFF]\033[0m'
    config_status = 'configured' if triangular_configured else 'not configured'
    print(f"Triangular Arb:    {status_icon} {config_status}, {num_paths} paths")

except Exception as e:
    print(f"\033[0;31mError: {e}\033[0m")
    sys.exit(1)
EOF
}

# Function to display recent signals
display_recent_signals() {
    local response=$(fetch_stat_arb_status)

    if [ -z "$response" ]; then
        echo -e "${YELLOW}No signal data available${NC}"
        return 0
    fi

    python3 << EOF
import json
import sys

try:
    data = json.loads('''$response''')
    manager_status = data.get('manager_status', {})
    signals_count = manager_status.get('signals_history_count', 0)
    last_signal = manager_status.get('last_signal_time', None)

    print(f"Signals Generated: {signals_count}")
    if last_signal:
        print(f"Last Signal Time:  {last_signal[:19]}")
    else:
        print(f"Last Signal Time:  No signals generated yet")

    # Performance by strategy type
    performance = manager_status.get('performance', {})

    if performance.get('pairs') or performance.get('funding') or performance.get('triangular'):
        print("")
        print("Performance by Strategy:")

        pairs_perf = performance.get('pairs', {})
        if pairs_perf:
            for strategy_id, perf in pairs_perf.items():
                profit = perf.get('total_profit', 0)
                trades = perf.get('trades', 0)
                win_rate = perf.get('win_rate', 0)
                color = '\033[0;32m' if profit >= 0 else '\033[0;31m'
                print(f"  {strategy_id}: {color}\${profit:+,.2f}\033[0m ({trades} trades, {win_rate:.0%} win)")

        funding_perf = performance.get('funding', {})
        if funding_perf:
            for strategy_id, perf in funding_perf.items():
                profit = perf.get('total_profit', 0)
                trades = perf.get('trades', 0)
                color = '\033[0;32m' if profit >= 0 else '\033[0;31m'
                print(f"  {strategy_id}: {color}\${profit:+,.2f}\033[0m ({trades} trades)")
    else:
        print("")
        print("No performance data yet - waiting for trades")

except Exception as e:
    print(f"\033[0;31mError: {e}\033[0m")
    sys.exit(1)
EOF
}

# Function to display recent errors from logs
display_recent_errors() {
    # Check Docker logs for errors
    local container="crypto-bot-trading"

    if docker ps --filter "name=$container" --format "{{.Names}}" | grep -q "$container"; then
        local errors=$(docker logs "$container" 2>&1 | grep -iE "error|fail|exception" | tail -5)

        if [ -n "$errors" ]; then
            echo -e "${RED}Recent Errors:${NC}"
            echo "$errors" | while read -r line; do
                echo "  $(echo "$line" | cut -c1-100)..."
            done
        else
            echo -e "${GREEN}No recent errors${NC}"
        fi
    else
        echo -e "${YELLOW}Container not running${NC}"
    fi
}

# Function to display recent activity from logs
display_recent_activity() {
    local container="crypto-bot-trading"

    if docker ps --filter "name=$container" --format "{{.Names}}" | grep -q "$container"; then
        echo "Recent Activity (last $LOG_LINES lines):"
        echo ""
        docker logs "$container" 2>&1 | grep -iE "signal|arbitrage|pairs|funding|triangular|profit|loss" | tail -$LOG_LINES | while read -r line; do
            # Color code based on content
            if echo "$line" | grep -qi "error\|fail"; then
                echo -e "${RED}$line${NC}"
            elif echo "$line" | grep -qi "signal\|generating"; then
                echo -e "${CYAN}$line${NC}"
            elif echo "$line" | grep -qi "profit"; then
                echo -e "${GREEN}$line${NC}"
            else
                echo "$line"
            fi
        done
    fi
}

# Function to check service connectivity
check_connectivity() {
    echo "Service Connectivity:"
    echo ""

    # Trading Engine
    local te_status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$TRADING_ENGINE_URL/health" 2>/dev/null)
    if [ "$te_status" = "200" ]; then
        echo -e "  Trading Engine:    ${GREEN}CONNECTED${NC}"
    else
        echo -e "  Trading Engine:    ${RED}DISCONNECTED${NC} (HTTP $te_status)"
    fi

    # Bybit Connector
    local bc_status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$BYBIT_CONNECTOR_URL/health" 2>/dev/null)
    if [ "$bc_status" = "200" ]; then
        echo -e "  Bybit Connector:   ${GREEN}CONNECTED${NC}"
    else
        echo -e "  Bybit Connector:   ${RED}DISCONNECTED${NC} (HTTP $bc_status)"
    fi

    # Market Data
    local md_status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$MARKET_DATA_URL/health" 2>/dev/null)
    if [ "$md_status" = "200" ]; then
        echo -e "  Market Data:       ${GREEN}CONNECTED${NC}"
    else
        echo -e "  Market Data:       ${RED}DISCONNECTED${NC} (HTTP $md_status)"
    fi
}

# Function for main monitoring display
display_monitor() {
    echo ""
    echo "============================================================================"
    echo -e "${BOLD}  STATISTICAL ARBITRAGE - PAPER TRADING MONITOR${NC}"
    echo "  Time: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "============================================================================"

    print_header "MANAGER STATUS"
    display_manager_status

    print_header "ACTIVE STRATEGIES"
    display_active_strategies

    print_header "SIGNALS & PERFORMANCE"
    display_recent_signals

    print_header "SERVICE CONNECTIVITY"
    check_connectivity

    print_header "ERROR CHECK"
    display_recent_errors

    if [ "$SHOW_LOGS" = true ]; then
        print_header "RECENT ACTIVITY LOG"
        display_recent_activity
    fi

    echo ""
    echo "============================================================================"
}

# Function for JSON output
output_json() {
    local status_response=$(fetch_stat_arb_status)
    local performance_response=$(fetch_performance)

    python3 << EOF
import json
import sys
from datetime import datetime

try:
    status = json.loads('''$status_response''') if '''$status_response''' else {}
    performance = json.loads('''$performance_response''') if '''$performance_response''' else {}

    output = {
        "timestamp": datetime.now().isoformat(),
        "status": status,
        "performance": performance
    }

    print(json.dumps(output, indent=2))

except Exception as e:
    print(json.dumps({"error": str(e)}))
    sys.exit(1)
EOF
}

# Function for continuous monitoring
continuous_monitor() {
    local iteration=0

    while true; do
        iteration=$((iteration + 1))
        clear

        echo -e "${MAGENTA}[Iteration #$iteration | Press Ctrl+C to stop]${NC}"
        display_monitor

        echo ""
        echo -e "${YELLOW}Next refresh in $INTERVAL seconds...${NC}"

        # Log to file
        local log_file="$LOG_DIR/monitor_$(date '+%Y%m%d').log"
        echo "--- $(date '+%Y-%m-%d %H:%M:%S') ---" >> "$log_file"
        fetch_stat_arb_status >> "$log_file"
        echo "" >> "$log_file"

        sleep $INTERVAL
    done
}

# Parse arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --continuous|-c)
                CONTINUOUS=true
                shift
                ;;
            --interval|-i)
                INTERVAL=$2
                shift 2
                ;;
            --json|-j)
                JSON_OUTPUT=true
                shift
                ;;
            --no-logs)
                SHOW_LOGS=false
                shift
                ;;
            --log-lines)
                LOG_LINES=$2
                shift 2
                ;;
            -h|--help)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Monitor Statistical Arbitrage paper trading activities"
                echo ""
                echo "Options:"
                echo "  -c, --continuous      Continuous monitoring mode"
                echo "  -i, --interval N      Refresh interval in seconds (default: 30)"
                echo "  -j, --json            Output in JSON format"
                echo "  --no-logs             Don't show activity logs"
                echo "  --log-lines N         Number of log lines to show (default: 15)"
                echo "  -h, --help            Show this help"
                echo ""
                echo "Examples:"
                echo "  $0                    # Single snapshot"
                echo "  $0 --continuous       # Continuous monitoring"
                echo "  $0 -c -i 60           # Monitor every 60 seconds"
                echo "  $0 --json             # JSON output for scripting"
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                echo "Use -h for help"
                exit 1
                ;;
        esac
    done
}

# Main execution
main() {
    parse_args "$@"

    if [ "$JSON_OUTPUT" = true ]; then
        output_json
    elif [ "$CONTINUOUS" = true ]; then
        trap 'echo -e "\n${YELLOW}Monitoring stopped${NC}"; exit 0' INT
        continuous_monitor
    else
        display_monitor
    fi
}

main "$@"
