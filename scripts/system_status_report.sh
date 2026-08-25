#!/bin/bash
# Crypto Trading Bot - System Status Report Generator
# Version: 1.0.0
# Last Updated: 2025-11-14
#
# Purpose: Generate comprehensive system status reports
# Usage: ./scripts/system_status_report.sh [--email user@example.com] [--save /path/to/file]

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
EMAIL=""
SAVE_TO=""
TODAY=$(date +%Y%m%d)
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
TEMP_REPORT="/tmp/system_status_${TODAY}.txt"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --email)
            EMAIL=$2
            shift 2
            ;;
        --save)
            SAVE_TO=$2
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--email user@example.com] [--save /path/to/file]"
            exit 1
            ;;
    esac
done

# Log function
log() {
    local level=$1
    shift
    echo -e "${BLUE}[$(date '+%H:%M:%S')] $level:${NC} $@"
}

# Print header
print_header() {
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║  System Status Report Generator                           ║${NC}"
    echo -e "${CYAN}║  $(date '+%Y-%m-%d %H:%M:%S')                                       ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    log INFO "Collecting system status information..."
}

# Check service health
check_services() {
    log INFO "Checking service health..."

    local services_healthy=0
    local services_total=10

    for port in {8000..8009}; do
        if curl -s -f "http://localhost:$port/health" >/dev/null 2>&1; then
            ((services_healthy++))
        fi
    done

    echo "SERVICES_HEALTHY:$services_healthy"
    echo "SERVICES_TOTAL:$services_total"

    # Get individual service status
    declare -A service_names=(
        [8000]="API Gateway"
        [8001]="Bybit Connector"
        [8002]="Market Data"
        [8003]="Portfolio Manager"
        [8004]="Technical Analysis"
        [8005]="Trading Engine"
        [8006]="Notifications"
        [8007]="ML Prediction"
        [8008]="Sentiment Analysis"
        [8009]="Risk Metrics"
    )

    for port in {8000..8009}; do
        local status="DOWN"
        local response_time="N/A"

        if curl -s -f "http://localhost:$port/health" >/dev/null 2>&1; then
            status="UP"
            # Measure response time
            response_time=$(curl -s -w "%{time_total}" -o /dev/null "http://localhost:$port/health" 2>/dev/null)
            response_time="${response_time}s"
        fi

        echo "SERVICE:$port|${service_names[$port]}|$status|$response_time"
    done
}

# Check Docker containers
check_containers() {
    log INFO "Checking Docker containers..."

    local containers=$(docker-compose ps --format json 2>/dev/null | jq -r '.Name' 2>/dev/null)
    local running=0
    local total=0

    while IFS= read -r container; do
        if [ ! -z "$container" ]; then
            ((total++))
            local state=$(docker inspect -f '{{.State.Status}}' "$container" 2>/dev/null)
            if [ "$state" == "running" ]; then
                ((running++))
            fi
            echo "CONTAINER:$container|$state"
        fi
    done <<< "$containers"

    echo "CONTAINERS_RUNNING:$running"
    echo "CONTAINERS_TOTAL:$total"
}

# Check infrastructure services
check_infrastructure() {
    log INFO "Checking infrastructure services..."

    # Check TimescaleDB
    if docker exec crypto-trading-bot-timescaledb-1 pg_isready >/dev/null 2>&1; then
        echo "INFRASTRUCTURE:TimescaleDB|UP"
    else
        echo "INFRASTRUCTURE:TimescaleDB|DOWN"
    fi

    # Check Redis
    if docker exec crypto-trading-bot-redis-1 redis-cli ping >/dev/null 2>&1; then
        echo "INFRASTRUCTURE:Redis|UP"
    else
        echo "INFRASTRUCTURE:Redis|DOWN"
    fi

    # Check RabbitMQ
    if curl -s -f http://localhost:15672 >/dev/null 2>&1; then
        echo "INFRASTRUCTURE:RabbitMQ|UP"
    else
        echo "INFRASTRUCTURE:RabbitMQ|DOWN"
    fi
}

# Get trading status
get_trading_status() {
    log INFO "Getting trading status..."

    local status_response=$(curl -s http://localhost:8005/api/v1/status 2>/dev/null)

    if [ ! -z "$status_response" ]; then
        echo "$status_response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(f\"TRADING_STATUS:{data.get('status', 'UNKNOWN')}\")
    print(f\"AUTO_TRADING:{data.get('auto_trading_enabled', False)}\")
    print(f\"CIRCUIT_BREAKER:{data.get('circuit_breaker_active', False)}\")
except:
    print('TRADING_STATUS:UNKNOWN')
" 2>/dev/null || echo "TRADING_STATUS:UNKNOWN"
    else
        echo "TRADING_STATUS:UNKNOWN"
    fi
}

# Get portfolio summary
get_portfolio_summary() {
    log INFO "Getting portfolio summary..."

    local balance_response=$(curl -s http://localhost:8003/api/v1/balance 2>/dev/null)

    if [ ! -z "$balance_response" ]; then
        echo "$balance_response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(f\"BALANCE_TOTAL:{data.get('total_balance', 0)}\")
    print(f\"BALANCE_INITIAL:{data.get('initial_balance', __import__('shared.account', fromlist=['ACCOUNT_EQUITY_USD']).ACCOUNT_EQUITY_USD)}\")
    print(f\"BALANCE_AVAILABLE:{data.get('available_balance', 0)}\")

    total = data.get('total_balance', 0)
    initial = data.get('initial_balance', __import__('shared.account', fromlist=['ACCOUNT_EQUITY_USD']).ACCOUNT_EQUITY_USD)
    pnl = total - initial
    pnl_pct = (pnl / initial * 100) if initial > 0 else 0

    print(f\"PORTFOLIO_PNL:{pnl:.2f}\")
    print(f\"PORTFOLIO_PNL_PCT:{pnl_pct:.2f}\")
except:
    print('BALANCE_TOTAL:0')
" 2>/dev/null || echo "BALANCE_TOTAL:0"
    else
        echo "BALANCE_TOTAL:0"
    fi
}

# Get open positions count
get_positions() {
    log INFO "Getting open positions..."

    local positions_response=$(curl -s "http://localhost:8005/api/v1/positions?status=open" 2>/dev/null)

    if [ ! -z "$positions_response" ]; then
        local count=$(echo "$positions_response" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('positions', [])))" 2>/dev/null)
        echo "OPEN_POSITIONS:${count:-0}"
    else
        echo "OPEN_POSITIONS:0"
    fi
}

# Get system resource usage
get_system_resources() {
    log INFO "Getting system resource usage..."

    # Docker stats
    local stats=$(docker stats --no-stream --format "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}" 2>/dev/null | head -15)

    echo "$stats" | while IFS='|' read name cpu mem; do
        # Remove % from CPU
        cpu=${cpu%\%}
        echo "RESOURCE:$name|$cpu|$mem"
    done

    # Disk usage
    local disk_usage=$(df -h / | tail -1 | awk '{print $5}' | sed 's/%//')
    echo "DISK_USAGE:$disk_usage"

    # Database size
    local db_size=$(docker exec crypto-trading-bot-timescaledb-1 psql -U crypto_user -d crypto_trading -t -c "SELECT pg_size_pretty(pg_database_size('crypto_trading'));" 2>/dev/null | xargs)
    echo "DATABASE_SIZE:${db_size:-Unknown}"
}

# Check for recent errors
check_recent_errors() {
    log INFO "Checking for recent errors..."

    # Check Docker logs for errors in last hour
    local error_count=0

    for service in trading-engine portfolio-manager market-data-service; do
        local errors=$(docker-compose logs --since 1h "$service" 2>/dev/null | grep -i "error\|exception\|failed" | wc -l)
        if [ "$errors" -gt 0 ]; then
            echo "ERRORS:$service|$errors"
            ((error_count += errors))
        fi
    done

    echo "TOTAL_ERRORS:$error_count"
}

# Generate the report
generate_report() {
    log INFO "Generating status report..."

    # Collect all metrics
    local metrics_file="/tmp/metrics_${TODAY}.txt"

    {
        check_services
        check_containers
        check_infrastructure
        get_trading_status
        get_portfolio_summary
        get_positions
        get_system_resources
        check_recent_errors
    } > "$metrics_file"

    # Parse metrics
    source <(cat "$metrics_file" | grep -E "^[A-Z_]+:" | grep -v "^SERVICE:" | grep -v "^CONTAINER:" | grep -v "^INFRASTRUCTURE:" | grep -v "^RESOURCE:" | grep -v "^ERRORS:")

    # Generate report
    {
        echo "════════════════════════════════════════════════════════════"
        echo "  CRYPTO TRADING BOT - SYSTEM STATUS REPORT"
        echo "════════════════════════════════════════════════════════════"
        echo "  Generated: $TIMESTAMP"
        echo "════════════════════════════════════════════════════════════"
        echo ""

        # Overall status
        local overall_status="HEALTHY"
        local overall_color=$GREEN

        if [ "${SERVICES_HEALTHY:-0}" -lt "${SERVICES_TOTAL:-10}" ]; then
            overall_status="DEGRADED"
            overall_color=$YELLOW
        fi

        if [ "${SERVICES_HEALTHY:-0}" -lt $((SERVICES_TOTAL / 2)) ]; then
            overall_status="CRITICAL"
            overall_color=$RED
        fi

        echo "📊 OVERALL STATUS: $overall_status"
        echo ""

        # Services health
        echo "🔧 MICROSERVICES HEALTH"
        echo "────────────────────────────────────────────────────────────"
        echo "  Status: ${SERVICES_HEALTHY:-0}/${SERVICES_TOTAL:-10} services healthy"
        echo ""

        cat "$metrics_file" | grep "^SERVICE:" | cut -d: -f2 | while IFS='|' read port name status response_time; do
            local status_icon="✓"
            if [ "$status" == "DOWN" ]; then
                status_icon="✗"
            fi
            printf "  [%-18s] %s %-7s (Port %s, %s)\n" "$name" "$status_icon" "$status" "$port" "$response_time"
        done

        echo ""
        echo "🐳 DOCKER CONTAINERS"
        echo "────────────────────────────────────────────────────────────"
        echo "  Status: ${CONTAINERS_RUNNING:-0}/${CONTAINERS_TOTAL:-0} containers running"
        echo ""

        cat "$metrics_file" | grep "^CONTAINER:" | cut -d: -f2 | while IFS='|' read container state; do
            local state_icon="✓"
            if [ "$state" != "running" ]; then
                state_icon="✗"
            fi
            printf "  %s %-40s %s\n" "$state_icon" "$container" "$state"
        done

        echo ""
        echo "⚙️  INFRASTRUCTURE"
        echo "────────────────────────────────────────────────────────────"

        cat "$metrics_file" | grep "^INFRASTRUCTURE:" | cut -d: -f2 | while IFS='|' read service status; do
            local status_icon="✓"
            if [ "$status" == "DOWN" ]; then
                status_icon="✗"
            fi
            printf "  %s %-20s %s\n" "$status_icon" "$service" "$status"
        done

        echo ""
        echo "💼 TRADING STATUS"
        echo "────────────────────────────────────────────────────────────"
        echo "  Status:            ${TRADING_STATUS:-UNKNOWN}"
        echo "  Auto Trading:      ${AUTO_TRADING:-false}"
        echo "  Circuit Breaker:   ${CIRCUIT_BREAKER:-false}"
        echo "  Open Positions:    ${OPEN_POSITIONS:-0}"

        echo ""
        echo "💰 PORTFOLIO"
        echo "────────────────────────────────────────────────────────────"
        echo "  Total Balance:     \$${BALANCE_TOTAL:-0}"
        echo "  Initial Balance:   \$${BALANCE_INITIAL:-unknown}"
        echo "  Available:         \$${BALANCE_AVAILABLE:-0}"

        local pnl_indicator="📈"
        if (( $(echo "${PORTFOLIO_PNL:-0} < 0" | bc -l 2>/dev/null || echo "0") )); then
            pnl_indicator="📉"
        fi

        echo "  Total P&L:         $pnl_indicator \$${PORTFOLIO_PNL:-0} (${PORTFOLIO_PNL_PCT:-0}%)"

        echo ""
        echo "💻 SYSTEM RESOURCES"
        echo "────────────────────────────────────────────────────────────"
        echo "  Disk Usage:        ${DISK_USAGE:-Unknown}%"
        echo "  Database Size:     ${DATABASE_SIZE:-Unknown}"
        echo ""

        # Show top 5 resource consumers
        echo "  Top Resource Consumers:"
        cat "$metrics_file" | grep "^RESOURCE:" | cut -d: -f2 | sort -t'|' -k2 -nr | head -5 | while IFS='|' read name cpu mem; do
            printf "    %-30s CPU: %5s%%  MEM: %s\n" "$name" "$cpu" "$mem"
        done

        echo ""
        echo "⚠️  RECENT ISSUES"
        echo "────────────────────────────────────────────────────────────"
        echo "  Total Errors (1h): ${TOTAL_ERRORS:-0}"

        if [ "${TOTAL_ERRORS:-0}" -gt 0 ]; then
            echo ""
            cat "$metrics_file" | grep "^ERRORS:" | cut -d: -f2 | while IFS='|' read service count; do
                printf "    %-30s %d errors\n" "$service" "$count"
            done
        else
            echo "  No errors detected in the last hour"
        fi

        echo ""
        echo "════════════════════════════════════════════════════════════"
        echo "  STATUS: $overall_status"
        echo "  Generated at: $TIMESTAMP"
        echo "════════════════════════════════════════════════════════════"

    } > "$TEMP_REPORT"

    # Clean up
    rm -f "$metrics_file"

    log SUCCESS "Report generated"
}

# Display report
display_report() {
    echo ""
    cat "$TEMP_REPORT"
}

# Save report to file
save_report() {
    if [ ! -z "$SAVE_TO" ]; then
        cp "$TEMP_REPORT" "$SAVE_TO"
        log SUCCESS "Report saved to: $SAVE_TO"
    fi
}

# Send email (if configured)
send_email() {
    if [ ! -z "$EMAIL" ]; then
        log INFO "Sending report to: $EMAIL"

        # Check if mail command is available
        if command -v mail &> /dev/null; then
            cat "$TEMP_REPORT" | mail -s "Crypto Trading Bot - System Status Report" "$EMAIL"
            log SUCCESS "Email sent successfully"
        else
            log WARNING "Mail command not found - cannot send email"
            log INFO "Install mailutils: sudo apt-get install mailutils"
        fi
    fi
}

# Print summary
print_summary() {
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}Report Summary${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo ""

    echo -e "${GREEN}✓ Status report generated successfully${NC}"
    echo ""

    [ ! -z "$SAVE_TO" ] && echo "  Saved to: $SAVE_TO"
    [ ! -z "$EMAIL" ] && echo "  Emailed to: $EMAIL"

    echo ""
    echo "Next steps:"
    echo "  • Review report for any issues"
    echo "  • Check services marked as DOWN"
    echo "  • Investigate any recent errors"
    echo "  • Monitor resource usage trends"

    echo ""
}

# Main execution
main() {
    print_header

    echo ""
    generate_report

    display_report

    save_report

    send_email

    print_summary

    # Cleanup
    rm -f "$TEMP_REPORT"
}

# Run main function
main
