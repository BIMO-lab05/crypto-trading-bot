#!/bin/bash
# Crypto Trading Bot - Daily Shutdown Routine
# Version: 1.0.0
# Last Updated: 2025-11-14
#
# Purpose: Safe evening shutdown with position checks
# Usage: ./scripts/daily_shutdown.sh [--force]

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
FORCE_SHUTDOWN=false
if [[ "$1" == "--force" ]]; then
    FORCE_SHUTDOWN=true
fi

LOG_DIR="/tmp"
TODAY=$(date +%Y%m%d)
SHUTDOWN_LOG="${LOG_DIR}/shutdown_${TODAY}.log"

# Function to log messages
log() {
    local level=$1
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    case $level in
        INFO)
            echo -e "${BLUE}[$timestamp] INFO:${NC} $message" | tee -a "$SHUTDOWN_LOG"
            ;;
        SUCCESS)
            echo -e "${GREEN}[$timestamp] SUCCESS:${NC} $message" | tee -a "$SHUTDOWN_LOG"
            ;;
        WARNING)
            echo -e "${YELLOW}[$timestamp] WARNING:${NC} $message" | tee -a "$SHUTDOWN_LOG"
            ;;
        ERROR)
            echo -e "${RED}[$timestamp] ERROR:${NC} $message" | tee -a "$SHUTDOWN_LOG"
            ;;
    esac
}

# Print header
print_header() {
    clear
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║  Crypto Trading Bot - Daily Shutdown Routine              ║${NC}"
    echo -e "${CYAN}║  $(date '+%A, %B %d, %Y - %H:%M:%S')                           ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    log INFO "Daily shutdown routine initiated"
}

# Stop auto trading
stop_trading() {
    log INFO "Stopping auto-trading..."

    local response=$(curl -s -X POST http://localhost:8005/api/v1/stop 2>/dev/null)

    if echo "$response" | grep -q "success"; then
        log SUCCESS "Auto-trading stopped"
        return 0
    else
        log WARNING "Could not stop auto-trading (may already be stopped)"
        return 1
    fi
}

# Check for open positions
check_positions() {
    log INFO "Checking for open positions..."

    local positions_response=$(curl -s http://localhost:8005/api/v1/positions?status=open 2>/dev/null)

    if [ ! -z "$positions_response" ]; then
        local position_count=$(echo "$positions_response" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('positions', [])))" 2>/dev/null)

        if [ ! -z "$position_count" ] && [ "$position_count" -gt 0 ]; then
            log WARNING "Found $position_count open position(s)"

            # Show position details
            echo ""
            echo -e "${YELLOW}Open Positions:${NC}"
            echo "$positions_response" | python3 -c "
import sys, json
positions = json.load(sys.stdin).get('positions', [])
for p in positions:
    symbol = p.get('symbol', 'UNKNOWN')
    side = p.get('side', 'UNKNOWN')
    pnl = p.get('pnl', 0)
    pnl_str = f'+\${pnl:.2f}' if pnl >= 0 else f'\${pnl:.2f}'
    print(f'  - {symbol} {side}: P&L {pnl_str}')
" 2>/dev/null

            echo ""

            if $FORCE_SHUTDOWN; then
                log WARNING "Force shutdown flag set - ignoring open positions"
                return 0
            fi

            echo -e "${YELLOW}Options:${NC}"
            echo "  1. Close all positions now (recommended)"
            echo "  2. Continue shutdown with positions open"
            echo "  3. Cancel shutdown"
            echo ""
            read -p "Select option (1-3): " -n 1 -r
            echo ""

            case $REPLY in
                1)
                    log INFO "User selected to close all positions"
                    close_all_positions
                    return $?
                    ;;
                2)
                    log WARNING "User selected to continue with open positions"
                    return 0
                    ;;
                3)
                    log INFO "User cancelled shutdown"
                    exit 0
                    ;;
                *)
                    log ERROR "Invalid option selected"
                    exit 1
                    ;;
            esac
        else
            log SUCCESS "No open positions"
            return 0
        fi
    else
        log WARNING "Could not check positions (trading engine may be down)"
        return 1
    fi
}

# Close all positions
close_all_positions() {
    log INFO "Closing all positions..."

    local response=$(curl -s -X POST http://localhost:8005/api/v1/emergency/close-all 2>/dev/null)

    if echo "$response" | grep -q "success"; then
        log SUCCESS "All positions closed"

        # Wait a moment for positions to close
        sleep 3

        # Verify positions closed
        local check_response=$(curl -s http://localhost:8005/api/v1/positions?status=open 2>/dev/null)
        local remaining=$(echo "$check_response" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('positions', [])))" 2>/dev/null)

        if [ "$remaining" -eq 0 ]; then
            log SUCCESS "Verified all positions closed"
            return 0
        else
            log WARNING "$remaining position(s) still open"
            return 1
        fi
    else
        log ERROR "Failed to close positions"
        return 1
    fi
}

# Generate daily report
generate_daily_report() {
    log INFO "Generating daily performance report..."

    # Get portfolio summary
    local balance_response=$(curl -s http://localhost:8003/api/v1/balance 2>/dev/null)

    if [ ! -z "$balance_response" ]; then
        local balance=$(echo "$balance_response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('total_balance', 0))" 2>/dev/null)
        local initial=$(echo "$balance_response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('initial_balance', 10000))" 2>/dev/null)

        local pnl=$(python3 -c "print(round($balance - $initial, 2))" 2>/dev/null)
        local pnl_pct=$(python3 -c "print(round(($balance - $initial) / $initial * 100, 2))" 2>/dev/null)

        echo "" | tee -a "$SHUTDOWN_LOG"
        echo -e "${CYAN}═══════════════════════════════════════════${NC}" | tee -a "$SHUTDOWN_LOG"
        echo -e "${CYAN}Daily Performance Summary${NC}" | tee -a "$SHUTDOWN_LOG"
        echo -e "${CYAN}$(date '+%Y-%m-%d')${NC}" | tee -a "$SHUTDOWN_LOG"
        echo -e "${CYAN}═══════════════════════════════════════════${NC}" | tee -a "$SHUTDOWN_LOG"
        echo "" | tee -a "$SHUTDOWN_LOG"
        echo "Starting Balance: \$$initial" | tee -a "$SHUTDOWN_LOG"
        echo "Ending Balance:   \$$balance" | tee -a "$SHUTDOWN_LOG"

        if (( $(echo "$pnl >= 0" | bc -l) )); then
            echo -e "Daily P&L:        ${GREEN}+\$$pnl (+$pnl_pct%)${NC}" | tee -a "$SHUTDOWN_LOG"
        else
            echo -e "Daily P&L:        ${RED}\$$pnl ($pnl_pct%)${NC}" | tee -a "$SHUTDOWN_LOG"
        fi

        echo "" | tee -a "$SHUTDOWN_LOG"

        log SUCCESS "Daily report generated"
        return 0
    else
        log WARNING "Could not generate daily report (portfolio service down)"
        return 1
    fi
}

# Stop monitoring
stop_monitoring() {
    log INFO "Stopping monitoring processes..."

    # Stop monitor.py
    if pgrep -f "scripts/monitor.py" >/dev/null; then
        pkill -f "scripts/monitor.py"
        log SUCCESS "Monitor stopped"
    else
        log INFO "Monitor not running"
    fi

}

# Save logs
archive_logs() {
    log INFO "Archiving today's logs..."

    local archive_dir="/tmp/crypto-bot-logs"
    mkdir -p "$archive_dir"

    # Copy logs
    if [ -f "${LOG_DIR}/monitor_${TODAY}.log" ]; then
        cp "${LOG_DIR}/monitor_${TODAY}.log" "$archive_dir/"
        log SUCCESS "Monitor log archived"
    fi


    if [ -f "${LOG_DIR}/startup_${TODAY}.log" ]; then
        cp "${LOG_DIR}/startup_${TODAY}.log" "$archive_dir/"
        log SUCCESS "Startup log archived"
    fi

    log INFO "Logs archived to: $archive_dir"
}

# Stop services
stop_services() {
    log INFO "Stopping Docker services..."

    docker-compose stop 2>&1 | tee -a "$SHUTDOWN_LOG"

    if [ ${PIPESTATUS[0]} -eq 0 ]; then
        log SUCCESS "All services stopped"
        return 0
    else
        log ERROR "Failed to stop some services"
        return 1
    fi
}

# Print summary
print_summary() {
    local exit_code=$1

    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}Shutdown Summary${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo ""

    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}✓ Shutdown completed successfully${NC}"
        echo ""
        echo "All services stopped cleanly."
        echo "Logs archived for review."
        echo ""
        echo -e "${CYAN}Tomorrow's Startup:${NC}"
        echo "  ./scripts/daily_startup.sh"
    else
        echo -e "${YELLOW}⚠ Shutdown completed with warnings${NC}"
        echo ""
        echo "Some issues encountered during shutdown."
        echo "Review logs for details: $SHUTDOWN_LOG"
    fi

    echo ""
    echo -e "${CYAN}Log Files:${NC}"
    echo "  Shutdown log: $SHUTDOWN_LOG"
    echo "  Archive dir:  /tmp/crypto-bot-logs"

    echo ""
    echo -e "${BLUE}Shutdown completed at $(date '+%Y-%m-%d %H:%M:%S')${NC}"
    echo ""
}

# Main execution
main() {
    local start_time=$(date +%s)

    print_header

    echo ""
    log INFO "Step 1/7: Stopping auto-trading..."
    stop_trading

    echo ""
    log INFO "Step 2/7: Checking for open positions..."
    check_positions
    local positions_result=$?

    echo ""
    log INFO "Step 3/7: Generating daily report..."
    generate_daily_report

    echo ""
    log INFO "Step 4/7: Stopping monitoring processes..."
    stop_monitoring

    echo ""
    log INFO "Step 5/7: Archiving logs..."
    archive_logs

    echo ""
    log INFO "Step 6/7: Stopping Docker services..."
    stop_services
    local services_result=$?

    echo ""
    log INFO "Step 7/7: Cleanup complete"

    # Calculate duration
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    log INFO "Total shutdown time: ${duration}s"

    # Print summary
    if [ $services_result -eq 0 ] && [ $positions_result -eq 0 ]; then
        print_summary 0
        exit 0
    else
        print_summary 1
        exit 1
    fi
}

# Run main function
main
