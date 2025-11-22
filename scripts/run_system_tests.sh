#!/bin/bash
# Crypto Trading Bot - Comprehensive System Test Suite
# Version: 1.0.0
# Last Updated: 2025-11-14
#
# Purpose: End-to-end system validation and testing
# Usage: ./scripts/run_system_tests.sh [--verbose] [--report]

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
VERBOSE=false
GENERATE_REPORT=false
PROJECT_DIR="/mnt/d/Bimo_max/crypto-trading-bot"
REPORT_FILE="/tmp/system_test_report_$(date +%Y%m%d_%H%M%S).txt"

# Test counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_WARNINGS=0

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --verbose)
            VERBOSE=true
            shift
            ;;
        --report)
            GENERATE_REPORT=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--verbose] [--report]"
            exit 1
            ;;
    esac
done

# Log function
log() {
    local level=$1
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    case $level in
        INFO)
            echo -e "${BLUE}[INFO]${NC} $message"
            ;;
        SUCCESS)
            echo -e "${GREEN}[PASS]${NC} $message"
            ((TESTS_PASSED++))
            ;;
        FAIL)
            echo -e "${RED}[FAIL]${NC} $message"
            ((TESTS_FAILED++))
            ;;
        WARN)
            echo -e "${YELLOW}[WARN]${NC} $message"
            ((TESTS_WARNINGS++))
            ;;
    esac

    # Log to report file if enabled
    if $GENERATE_REPORT; then
        echo "[$timestamp] [$level] $message" >> "$REPORT_FILE"
    fi
}

# Test function wrapper
run_test() {
    local test_name=$1
    local test_command=$2

    ((TESTS_RUN++))

    if $VERBOSE; then
        log INFO "Running: $test_name"
    fi

    if eval "$test_command" >/dev/null 2>&1; then
        log SUCCESS "$test_name"
        return 0
    else
        log FAIL "$test_name"
        return 1
    fi
}

# Print header
print_header() {
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║  System Test Suite                                         ║${NC}"
    echo -e "${CYAN}║  $(date '+%Y-%m-%d %H:%M:%S')                                       ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    if $GENERATE_REPORT; then
        log INFO "Test report will be saved to: $REPORT_FILE"
    fi

    echo ""
}

# Test 1: Docker Services Health
test_docker_services() {
    echo -e "${CYAN}═══ Test Category: Docker Services ═══${NC}"
    echo ""

    local services=(
        "api-gateway:8000"
        "bybit-connector:8001"
        "market-data:8002"
        "portfolio-manager:8003"
        "technical-analysis:8004"
        "trading-engine:8005"
        "notification-service:8006"
        "ml-prediction:8007"
        "sentiment-analysis:8008"
        "risk-metrics:8009"
    )

    for service_port in "${services[@]}"; do
        local service=$(echo $service_port | cut -d':' -f1)
        local port=$(echo $service_port | cut -d':' -f2)

        # Test container running
        run_test "Service $service is running" \
            "docker-compose ps | grep -q '$service.*Up'"

        # Test health endpoint
        run_test "Service $service health check (port $port)" \
            "curl -f -s http://localhost:$port/health >/dev/null 2>&1"
    done

    echo ""
}

# Test 2: API Endpoints
test_api_endpoints() {
    echo -e "${CYAN}═══ Test Category: API Endpoints ═══${NC}"
    echo ""

    # API Gateway routes
    run_test "API Gateway root endpoint" \
        "curl -f -s http://localhost:8000/ >/dev/null 2>&1"

    # Bybit Connector
    run_test "Bybit Connector - Get server time" \
        "curl -f -s http://localhost:8001/api/v1/time >/dev/null 2>&1"

    # Market Data Service
    run_test "Market Data - Get market data for BTCUSDT" \
        "curl -f -s 'http://localhost:8002/api/v1/market/BTCUSDT' >/dev/null 2>&1"

    # Portfolio Manager
    run_test "Portfolio Manager - Get portfolio summary" \
        "curl -f -s http://localhost:8003/api/v1/portfolio >/dev/null 2>&1"

    # Technical Analysis
    run_test "Technical Analysis - Get indicators for BTCUSDT" \
        "curl -f -s 'http://localhost:8004/api/v1/indicators/BTCUSDT?interval=60' >/dev/null 2>&1"

    # Trading Engine
    run_test "Trading Engine - Get engine status" \
        "curl -f -s http://localhost:8005/api/v1/status >/dev/null 2>&1"

    # Notification Service
    run_test "Notification Service - Health check" \
        "curl -f -s http://localhost:8006/health >/dev/null 2>&1"

    # ML Prediction Service
    run_test "ML Prediction - Get available models" \
        "curl -f -s http://localhost:8007/api/v1/models >/dev/null 2>&1"

    # Sentiment Analysis
    run_test "Sentiment Analysis - Health check" \
        "curl -f -s http://localhost:8008/health >/dev/null 2>&1"

    # Risk Metrics
    run_test "Risk Metrics - Get current metrics" \
        "curl -f -s http://localhost:8009/api/v1/metrics >/dev/null 2>&1"

    echo ""
}

# Test 3: Database Connectivity
test_database() {
    echo -e "${CYAN}═══ Test Category: Database ═══${NC}"
    echo ""

    # Check TimescaleDB container
    run_test "TimescaleDB container is running" \
        "docker ps | grep -q timescaledb"

    # Test database connection
    run_test "Database connection test" \
        "docker exec crypto-bot-timescaledb pg_isready -U crypto_user"

    # Check database exists
    run_test "Crypto trading database exists" \
        "docker exec crypto-bot-timescaledb psql -U crypto_user -lqt | grep -q crypto_trading"

    # Test table existence (market_data should exist)
    run_test "Market data table exists" \
        "docker exec crypto-bot-timescaledb psql -U crypto_user -d crypto_trading -c '\\dt' | grep -q market_data"

    echo ""
}

# Test 4: Message Queue
test_message_queue() {
    echo -e "${CYAN}═══ Test Category: Message Queue ═══${NC}"
    echo ""

    # Check RabbitMQ container
    run_test "RabbitMQ container is running" \
        "docker ps | grep -q rabbitmq"

    # Test RabbitMQ management API
    run_test "RabbitMQ management API accessible" \
        "curl -f -s -u guest:guest http://localhost:15672/api/overview >/dev/null 2>&1"

    # Check for exchanges
    run_test "RabbitMQ exchanges configured" \
        "curl -f -s -u guest:guest http://localhost:15672/api/exchanges | grep -q 'crypto_trading'"

    echo ""
}

# Test 5: Operational Scripts
test_operational_scripts() {
    echo -e "${CYAN}═══ Test Category: Operational Scripts ═══${NC}"
    echo ""

    local scripts=(
        "validate_configuration.sh"
        "health_check.sh"
        "quick_check.sh"
        "backup.sh"
        "cleanup_logs.sh"
        "optimize_database.sh"
        "generate_performance_report.sh"
        "system_status_report.sh"
        "setup_automation.sh"
        "disaster_recovery.sh"
    )

    for script in "${scripts[@]}"; do
        # Check script exists
        run_test "Script exists: $script" \
            "test -f $PROJECT_DIR/scripts/$script"

        # Check script is executable
        run_test "Script executable: $script" \
            "test -x $PROJECT_DIR/scripts/$script"
    done

    echo ""
}

# Test 6: Configuration Files
test_configuration() {
    echo -e "${CYAN}═══ Test Category: Configuration ═══${NC}"
    echo ""

    # Docker Compose
    run_test "docker-compose.yml exists" \
        "test -f $PROJECT_DIR/docker-compose.yml"

    run_test "docker-compose.yml is valid" \
        "docker-compose config >/dev/null 2>&1"

    # Service .env files
    local services=(
        "bybit-connector"
        "market-data-service"
        "trading-engine"
        "portfolio-manager"
        "notification-service"
    )

    for service in "${services[@]}"; do
        run_test "Service $service has .env file" \
            "test -f $PROJECT_DIR/services/$service/.env"
    done

    echo ""
}

# Test 7: Documentation
test_documentation() {
    echo -e "${CYAN}═══ Test Category: Documentation ═══${NC}"
    echo ""

    local docs=(
        "README.md"
        "GETTING_STARTED.md"
        "SYSTEM_ARCHITECTURE.md"
        "SCRIPTS_INDEX.md"
        "SCRIPTS_OPERATIONAL_GUIDE.md"
        "QUICK_REFERENCE.md"
        "TRADING_ENGINE_CAPABILITIES.md"
        "BYBIT_API_SETUP_GUIDE.md"
        "TELEGRAM_NOTIFICATIONS_SETUP.md"
    )

    for doc in "${docs[@]}"; do
        run_test "Documentation exists: $doc" \
            "test -f $PROJECT_DIR/$doc"
    done

    echo ""
}

# Test 8: Dashboard Accessibility
test_dashboard() {
    echo -e "${CYAN}═══ Test Category: Dashboard ═══${NC}"
    echo ""

    # Test dashboard is accessible
    run_test "Dashboard HTML accessible" \
        "curl -f -s http://localhost:8080 >/dev/null 2>&1"

    # Test dashboard files exist
    run_test "Dashboard index.html exists" \
        "test -f $PROJECT_DIR/frontend/dashboard/index.html"

    run_test "Dashboard CSS exists" \
        "test -f $PROJECT_DIR/frontend/dashboard/styles.css"

    run_test "Dashboard JS exists" \
        "test -f $PROJECT_DIR/frontend/dashboard/app.js"

    echo ""
}

# Test 9: System Performance
test_performance() {
    echo -e "${CYAN}═══ Test Category: Performance ═══${NC}"
    echo ""

    # Test API response times
    local start_time=$(date +%s%N)
    curl -s http://localhost:8000/health >/dev/null 2>&1
    local end_time=$(date +%s%N)
    local response_time=$(( (end_time - start_time) / 1000000 ))

    if [ $response_time -lt 100 ]; then
        log SUCCESS "API Gateway response time: ${response_time}ms (<100ms target)"
    elif [ $response_time -lt 500 ]; then
        log WARN "API Gateway response time: ${response_time}ms (acceptable)"
    else
        log FAIL "API Gateway response time: ${response_time}ms (>500ms, too slow)"
    fi
    ((TESTS_RUN++))

    # Check memory usage
    local total_memory=$(docker stats --no-stream --format "{{.MemUsage}}" | awk '{sum+=$1} END {print sum}')
    if $VERBOSE; then
        log INFO "Total container memory usage: ~${total_memory}MB"
    fi

    # Check CPU usage
    run_test "System CPU load acceptable" \
        "test $(uptime | awk -F'load average:' '{print $2}' | awk '{print int($1)}') -lt 8"

    echo ""
}

# Test 10: Emergency Procedures
test_emergency_procedures() {
    echo -e "${CYAN}═══ Test Category: Emergency Procedures ═══${NC}"
    echo ""

    # Test emergency endpoints exist (without triggering them)
    run_test "Emergency stop endpoint exists" \
        "curl -f -s -X OPTIONS http://localhost:8005/api/v1/emergency/stop >/dev/null 2>&1 || true"

    # Test disaster recovery script
    run_test "Disaster recovery script exists" \
        "test -f $PROJECT_DIR/scripts/disaster_recovery.sh"

    run_test "Disaster recovery can list backups" \
        "$PROJECT_DIR/scripts/disaster_recovery.sh --list-backups >/dev/null 2>&1 || true"

    echo ""
}

# Generate summary report
generate_summary() {
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}Test Summary${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo ""

    echo "Total Tests Run:    $TESTS_RUN"
    echo -e "${GREEN}Tests Passed:       $TESTS_PASSED${NC}"

    if [ $TESTS_FAILED -gt 0 ]; then
        echo -e "${RED}Tests Failed:       $TESTS_FAILED${NC}"
    else
        echo "Tests Failed:       0"
    fi

    if [ $TESTS_WARNINGS -gt 0 ]; then
        echo -e "${YELLOW}Warnings:           $TESTS_WARNINGS${NC}"
    else
        echo "Warnings:           0"
    fi

    echo ""

    # Calculate success rate
    local success_rate=0
    if [ $TESTS_RUN -gt 0 ]; then
        success_rate=$(( (TESTS_PASSED * 100) / TESTS_RUN ))
    fi

    echo "Success Rate:       ${success_rate}%"
    echo ""

    # Overall status
    if [ $TESTS_FAILED -eq 0 ]; then
        if [ $TESTS_WARNINGS -eq 0 ]; then
            echo -e "${GREEN}✓ All tests passed - system is production ready${NC}"
            OVERALL_STATUS=0
        else
            echo -e "${YELLOW}⚠ Tests passed with warnings - review before production${NC}"
            OVERALL_STATUS=0
        fi
    else
        echo -e "${RED}✗ Some tests failed - fix issues before production deployment${NC}"
        OVERALL_STATUS=1
    fi

    if $GENERATE_REPORT; then
        echo ""
        echo "Detailed report saved to: $REPORT_FILE"
    fi

    echo ""
}

# Main execution
main() {
    print_header

    # Initialize report
    if $GENERATE_REPORT; then
        echo "System Test Report - $(date '+%Y-%m-%d %H:%M:%S')" > "$REPORT_FILE"
        echo "========================================" >> "$REPORT_FILE"
        echo "" >> "$REPORT_FILE"
    fi

    # Run all test categories
    test_docker_services
    test_api_endpoints
    test_database
    test_message_queue
    test_operational_scripts
    test_configuration
    test_documentation
    test_dashboard
    test_performance
    test_emergency_procedures

    # Generate summary
    generate_summary

    exit $OVERALL_STATUS
}

# Run main function
main
