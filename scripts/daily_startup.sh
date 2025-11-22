#!/bin/bash
# Crypto Trading Bot - Daily Startup Routine
# Version: 1.0.0
# Last Updated: 2025-11-14
#
# Purpose: Automated morning startup routine with validation
# Usage: ./scripts/daily_startup.sh

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="/tmp"
TODAY=$(date +%Y%m%d)

# Log file for this session
STARTUP_LOG="${LOG_DIR}/startup_${TODAY}.log"
MONITOR_LOG="${LOG_DIR}/monitor_${TODAY}.log"

# Function to log messages
log() {
    local level=$1
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    case $level in
        INFO)
            echo -e "${BLUE}[$timestamp] INFO:${NC} $message" | tee -a "$STARTUP_LOG"
            ;;
        SUCCESS)
            echo -e "${GREEN}[$timestamp] SUCCESS:${NC} $message" | tee -a "$STARTUP_LOG"
            ;;
        WARNING)
            echo -e "${YELLOW}[$timestamp] WARNING:${NC} $message" | tee -a "$STARTUP_LOG"
            ;;
        ERROR)
            echo -e "${RED}[$timestamp] ERROR:${NC} $message" | tee -a "$STARTUP_LOG"
            ;;
    esac
}

# Print header
print_header() {
    clear
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║  Crypto Trading Bot - Daily Startup Routine               ║${NC}"
    echo -e "${CYAN}║  $(date '+%A, %B %d, %Y - %H:%M:%S')                           ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    log INFO "Daily startup routine initiated"
}

# Check if services are already running
check_existing_services() {
    log INFO "Checking for existing services..."

    local running_services=$(docker-compose ps --services --filter "status=running" 2>/dev/null | wc -l)

    if [ "$running_services" -gt 0 ]; then
        log WARNING "Found $running_services services already running"
        echo ""
        echo -e "${YELLOW}Options:${NC}"
        echo "  1. Restart all services (recommended for clean start)"
        echo "  2. Continue with existing services"
        echo "  3. Exit and check manually"
        echo ""
        read -p "Select option (1-3): " -n 1 -r
        echo ""

        case $REPLY in
            1)
                log INFO "User selected restart"
                docker-compose down
                log SUCCESS "Stopped existing services"
                ;;
            2)
                log INFO "User selected to continue with existing services"
                return 0
                ;;
            3)
                log INFO "User selected to exit"
                exit 0
                ;;
            *)
                log ERROR "Invalid option selected"
                exit 1
                ;;
        esac
    else
        log INFO "No existing services found"
    fi
}

# Start system
start_system() {
    log INFO "Starting system with orchestrated startup..."
    echo ""

    cd "$PROJECT_ROOT"

    # Run startup script with skip-build for faster start
    if [ -f "scripts/startup.sh" ]; then
        bash scripts/startup.sh --skip-build 2>&1 | tee -a "$STARTUP_LOG"
        local exit_code=${PIPESTATUS[0]}

        if [ $exit_code -eq 0 ]; then
            log SUCCESS "System startup completed successfully"
            return 0
        else
            log ERROR "System startup failed with exit code $exit_code"
            return 1
        fi
    else
        log ERROR "startup.sh not found in scripts directory"
        return 1
    fi
}

# Run health validation
validate_health() {
    log INFO "Running comprehensive health checks..."
    echo ""

    cd "$PROJECT_ROOT"

    if [ -f "scripts/health_check.sh" ]; then
        bash scripts/health_check.sh 2>&1 | tee -a "$STARTUP_LOG"
        local exit_code=${PIPESTATUS[0]}

        if [ $exit_code -eq 0 ]; then
            log SUCCESS "All health checks passed"
            return 0
        elif [ $exit_code -eq 1 ]; then
            log WARNING "Some services degraded - review output above"
            return 1
        else
            log ERROR "Critical health check failures"
            return 2
        fi
    else
        log WARNING "health_check.sh not found, skipping health validation"
        return 0
    fi
}

# Validate risk controls
validate_risk() {
    log INFO "Validating risk management controls..."
    echo ""

    cd "$PROJECT_ROOT"

    if [ -f "scripts/validate_risk_limits.py" ]; then
        python3 scripts/validate_risk_limits.py 2>&1 | tee -a "$STARTUP_LOG"
        local exit_code=${PIPESTATUS[0]}

        if [ $exit_code -eq 0 ]; then
            log SUCCESS "All risk controls validated"
            return 0
        elif [ $exit_code -eq 1 ]; then
            log WARNING "Some risk rules need attention - review before trading"
            return 1
        else
            log ERROR "Critical risk validation failures - DO NOT TRADE"
            return 2
        fi
    else
        log WARNING "validate_risk_limits.py not found, skipping risk validation"
        return 0
    fi
}

# Start monitoring
start_monitoring() {
    log INFO "Starting continuous monitoring..."

    cd "$PROJECT_ROOT"

    # Check if monitor already running
    if pgrep -f "scripts/monitor.py" >/dev/null; then
        log WARNING "Monitor already running (PID: $(pgrep -f 'scripts/monitor.py'))"
        return 0
    fi

    if [ -f "scripts/monitor.py" ]; then
        nohup python3 scripts/monitor.py --interval 60 > "$MONITOR_LOG" 2>&1 &
        local monitor_pid=$!

        # Wait a moment and check if it's still running
        sleep 2
        if ps -p $monitor_pid > /dev/null; then
            log SUCCESS "Monitor started (PID: $monitor_pid)"
            log INFO "Monitor logs: $MONITOR_LOG"
            return 0
        else
            log ERROR "Monitor failed to start"
            return 1
        fi
    else
        log WARNING "monitor.py not found, skipping monitoring"
        return 0
    fi
}

# Start dashboard
start_dashboard() {
    log INFO "Starting dashboard..."

    cd "$PROJECT_ROOT/dashboard"

    # Check if dashboard already running
    if pgrep -f "http.server 8080" >/dev/null; then
        log WARNING "Dashboard already running (PID: $(pgrep -f 'http.server 8080'))"
        return 0
    fi

    if [ -f "index.html" ]; then
        nohup python3 -m http.server 8080 > "${LOG_DIR}/dashboard_${TODAY}.log" 2>&1 &
        local dashboard_pid=$!

        # Wait a moment and check if it's still running
        sleep 2
        if ps -p $dashboard_pid > /dev/null; then
            log SUCCESS "Dashboard started (PID: $dashboard_pid)"
            log INFO "Access at: http://localhost:8080"
            return 0
        else
            log ERROR "Dashboard failed to start"
            return 1
        fi
    else
        log WARNING "Dashboard index.html not found"
        return 0
    fi
}

# Check for important updates
check_updates() {
    log INFO "Checking for important notifications..."

    # Check if API keys configured
    if grep -q "your_api_key_here" "$PROJECT_ROOT/services/bybit-connector/.env" 2>/dev/null; then
        log WARNING "Bybit API keys not configured - using mock data"
        echo -e "${YELLOW}  → Configure real keys: docs/BYBIT_API_SETUP_GUIDE.md${NC}"
    fi

    # Check if Telegram configured
    if grep -q "TELEGRAM_ENABLED=false" "$PROJECT_ROOT/services/notification-service/.env" 2>/dev/null; then
        log WARNING "Telegram notifications disabled"
        echo -e "${YELLOW}  → Enable alerts: docs/TELEGRAM_NOTIFICATIONS_SETUP.md${NC}"
    fi

    # Check disk space
    local disk_usage=$(df -h "$PROJECT_ROOT" | awk 'NR==2 {print $5}' | sed 's/%//')
    if [ "$disk_usage" -gt 80 ]; then
        log WARNING "Disk space is ${disk_usage}% full - consider cleanup"
    fi
}

# Print summary
print_summary() {
    local health_status=$1
    local risk_status=$2

    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}Daily Startup Summary${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo ""

    # Overall status
    if [ $health_status -eq 0 ] && [ $risk_status -eq 0 ]; then
        echo -e "${GREEN}✓ System Status: READY FOR TRADING${NC}"
        echo ""
        echo "All systems operational and validated."
    elif [ $health_status -le 1 ] && [ $risk_status -le 1 ]; then
        echo -e "${YELLOW}⚠ System Status: REVIEW REQUIRED${NC}"
        echo ""
        echo "Some issues detected - review warnings above."
    else
        echo -e "${RED}✗ System Status: NOT READY${NC}"
        echo ""
        echo "Critical issues detected - DO NOT start trading."
    fi

    echo ""
    echo -e "${CYAN}Active Services:${NC}"

    # Quick service check
    local healthy_count=0
    for port in {8000..8009}; do
        if curl -s -f "http://localhost:$port/health" >/dev/null 2>&1; then
            ((healthy_count++))
        fi
    done

    if [ $healthy_count -eq 10 ]; then
        echo -e "  ${GREEN}✓${NC} All 10 microservices running"
    else
        echo -e "  ${YELLOW}⚠${NC} $healthy_count/10 microservices running"
    fi

    # Check monitor
    if pgrep -f "scripts/monitor.py" >/dev/null; then
        echo -e "  ${GREEN}✓${NC} Continuous monitoring active"
    else
        echo -e "  ${RED}✗${NC} Monitoring not running"
    fi

    # Check dashboard
    if pgrep -f "http.server 8080" >/dev/null; then
        echo -e "  ${GREEN}✓${NC} Dashboard available at http://localhost:8080"
    else
        echo -e "  ${RED}✗${NC} Dashboard not running"
    fi

    echo ""
    echo -e "${CYAN}Quick Links:${NC}"
    echo "  Dashboard:          http://localhost:8080"
    echo "  Trading Engine API: http://localhost:8005/docs"
    echo "  Portfolio Manager:  http://localhost:8003/docs"
    echo "  API Gateway:        http://localhost:8000/docs"

    echo ""
    echo -e "${CYAN}Logs:${NC}"
    echo "  Startup log:  $STARTUP_LOG"
    echo "  Monitor log:  $MONITOR_LOG"
    echo "  Dashboard log: ${LOG_DIR}/dashboard_${TODAY}.log"

    echo ""
    echo -e "${CYAN}Useful Commands:${NC}"
    echo "  Quick check:    ./scripts/quick_check.sh"
    echo "  Stop trading:   curl -X POST http://localhost:8005/api/v1/stop"
    echo "  Emergency stop: curl -X POST http://localhost:8005/api/v1/emergency/stop"
    echo "  View logs:      docker-compose logs -f [service-name]"

    echo ""
    echo -e "${CYAN}Next Steps:${NC}"

    if [ $health_status -eq 0 ] && [ $risk_status -eq 0 ]; then
        echo "  1. Monitor dashboard for any alerts"
        echo "  2. Review positions and balance"
        echo "  3. Check monitor log occasionally: tail -f $MONITOR_LOG"
        echo "  4. Enable auto-trading if desired (after review)"
    else
        echo "  1. Review warnings/errors above"
        echo "  2. Fix any critical issues"
        echo "  3. Re-run health check: ./scripts/health_check.sh --verbose"
        echo "  4. Re-run risk validation: python3 scripts/validate_risk_limits.py"
    fi

    echo ""
    echo -e "${BLUE}Startup completed at $(date '+%Y-%m-%d %H:%M:%S')${NC}"
    echo ""
}

# Main execution
main() {
    local start_time=$(date +%s)

    print_header

    # Check existing services
    check_existing_services

    echo ""
    log INFO "Step 1/6: Starting system..."
    start_system
    local startup_result=$?

    if [ $startup_result -ne 0 ]; then
        log ERROR "System startup failed - aborting"
        exit 1
    fi

    echo ""
    log INFO "Step 2/6: Validating health..."
    validate_health
    local health_result=$?

    echo ""
    log INFO "Step 3/6: Validating risk controls..."
    validate_risk
    local risk_result=$?

    echo ""
    log INFO "Step 4/6: Starting monitoring..."
    start_monitoring

    echo ""
    log INFO "Step 5/6: Starting dashboard..."
    start_dashboard

    echo ""
    log INFO "Step 6/6: Checking for updates..."
    check_updates

    # Calculate duration
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local minutes=$((duration / 60))
    local seconds=$((duration % 60))

    log INFO "Total startup time: ${minutes}m ${seconds}s"

    # Print summary
    print_summary $health_result $risk_result

    # Return appropriate exit code
    if [ $health_result -eq 0 ] && [ $risk_result -eq 0 ]; then
        exit 0
    elif [ $health_result -le 1 ] && [ $risk_result -le 1 ]; then
        exit 1
    else
        exit 2
    fi
}

# Run main function
main
