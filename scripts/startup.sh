#!/bin/bash
# Crypto Trading Bot - Automated Startup Script
# Version: 1.0.0
# Last Updated: 2025-11-14
#
# Purpose: Orchestrate complete system startup with proper ordering and validation
# Usage: ./scripts/startup.sh [--skip-build] [--verbose]

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
SKIP_BUILD=false
VERBOSE=false
START_TIME=$(date +%s)

# Repo root, derived from this script's own location rather than assuming the
# caller's cwd — initialize_paper_trading() imports shared/account.py from here.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --help)
            echo "Usage: $0 [--skip-build] [--verbose] [--help]"
            echo ""
            echo "Options:"
            echo "  --skip-build    Skip Docker image rebuild (faster restart)"
            echo "  --verbose       Show detailed output from all commands"
            echo "  --help          Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Logging function
log() {
    local level=$1
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    case $level in
        INFO)
            echo -e "${BLUE}[$timestamp] INFO:${NC} $message"
            ;;
        SUCCESS)
            echo -e "${GREEN}[$timestamp] SUCCESS:${NC} $message"
            ;;
        WARNING)
            echo -e "${YELLOW}[$timestamp] WARNING:${NC} $message"
            ;;
        ERROR)
            echo -e "${RED}[$timestamp] ERROR:${NC} $message"
            ;;
        STEP)
            echo -e "${CYAN}[$timestamp] STEP:${NC} $message"
            ;;
    esac
}

# Verbose logging
vlog() {
    if $VERBOSE; then
        echo -e "${NC}  → $@${NC}"
    fi
}

# Progress indicator
show_progress() {
    local message=$1
    local max_wait=${2:-30}  # Default 30 seconds
    local wait_time=0

    echo -n "$message"
    while [ $wait_time -lt $max_wait ]; do
        echo -n "."
        sleep 1
        ((wait_time++))
    done
    echo ""
}

# Wait for service to be healthy
wait_for_service() {
    local name=$1
    local url=$2
    local max_attempts=${3:-30}
    local attempt=0

    vlog "Waiting for $name to be ready..."

    while [ $attempt -lt $max_attempts ]; do
        if curl -s -f "$url" >/dev/null 2>&1; then
            log SUCCESS "$name is ready"
            return 0
        fi

        if $VERBOSE; then
            echo -n "."
        fi

        sleep 2
        ((attempt++))
    done

    log ERROR "$name failed to start after $max_attempts attempts"
    return 1
}

# Print header
print_header() {
    echo ""
    echo -e "${BLUE}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║  Crypto Trading Bot - System Startup                     ║${NC}"
    echo -e "${BLUE}║  $(date '+%Y-%m-%d %H:%M:%S')                                       ║${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""

    if $SKIP_BUILD; then
        log INFO "Fast restart mode: Skipping Docker rebuild"
    fi

    if $VERBOSE; then
        log INFO "Verbose mode enabled"
    fi
    echo ""
}

# Step 1: Pre-flight checks
preflight_checks() {
    log STEP "[1/10] Running pre-flight checks..."

    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        log ERROR "Docker is not installed. Please install Docker first."
        exit 1
    fi
    vlog "Docker found: $(docker --version)"

    # Check if Docker Compose is installed
    if ! command -v docker-compose &> /dev/null; then
        log ERROR "docker-compose is not installed. Please install docker-compose first."
        exit 1
    fi
    vlog "Docker Compose found: $(docker-compose --version)"

    # Check if Docker daemon is running
    if ! docker info &> /dev/null; then
        log ERROR "Docker daemon is not running. Please start Docker first."
        exit 1
    fi
    vlog "Docker daemon is running"

    # Check if required directories exist
    if [ ! -d "services" ]; then
        log ERROR "services/ directory not found. Are you in the project root?"
        exit 1
    fi
    vlog "Project structure validated"

    # Check if docker-compose.yml exists
    if [ ! -f "docker-compose.yml" ]; then
        log ERROR "docker-compose.yml not found in current directory"
        exit 1
    fi
    vlog "Docker Compose configuration found"

    log SUCCESS "Pre-flight checks passed"
}

# Step 2: Stop existing containers
stop_existing() {
    log STEP "[2/10] Stopping existing containers..."

    if docker-compose ps -q 2>/dev/null | grep -q .; then
        vlog "Found running containers, stopping gracefully..."
        docker-compose down 2>&1 | grep -v "WARNING" || true
        log SUCCESS "Stopped existing containers"
    else
        log INFO "No existing containers to stop"
    fi
}

# Step 3: Build Docker images (optional)
build_images() {
    if $SKIP_BUILD; then
        log STEP "[3/10] Skipping Docker image build (--skip-build)"
        return 0
    fi

    log STEP "[3/10] Building Docker images..."
    log INFO "This may take 5-10 minutes on first run..."

    if $VERBOSE; then
        docker-compose build
    else
        docker-compose build 2>&1 | grep -E "(Building|Successfully built|ERROR)" | while read line; do
            echo "  $line"
        done
    fi

    log SUCCESS "Docker images built successfully"
}

# Step 4: Start infrastructure services
start_infrastructure() {
    log STEP "[4/10] Starting infrastructure services..."

    local infrastructure=(
        "timescaledb:5432"
        "redis:6379"
        "rabbitmq:15672"
    )

    # Start infrastructure containers
    vlog "Starting TimescaleDB, Redis, and RabbitMQ..."
    docker-compose up -d timescaledb redis rabbitmq 2>&1 | grep -v "WARNING" || true

    # Wait for each infrastructure service
    for service_port in "${infrastructure[@]}"; do
        IFS=':' read -r service port <<< "$service_port"

        vlog "Waiting for $service on port $port..."

        case $service in
            timescaledb)
                # Wait for PostgreSQL to accept connections
                local attempts=0
                while [ $attempts -lt 30 ]; do
                    if docker exec crypto-trading-bot-timescaledb-1 pg_isready -U crypto_user >/dev/null 2>&1; then
                        log SUCCESS "TimescaleDB is ready"
                        break
                    fi
                    sleep 2
                    ((attempts++))
                done
                ;;
            redis)
                # Wait for Redis to respond to PING
                local attempts=0
                while [ $attempts -lt 30 ]; do
                    if docker exec crypto-trading-bot-redis-1 redis-cli ping >/dev/null 2>&1; then
                        log SUCCESS "Redis is ready"
                        break
                    fi
                    sleep 2
                    ((attempts++))
                done
                ;;
            rabbitmq)
                # Wait for RabbitMQ management interface
                local attempts=0
                while [ $attempts -lt 30 ]; do
                    if docker exec crypto-trading-bot-rabbitmq-1 rabbitmqctl status >/dev/null 2>&1; then
                        log SUCCESS "RabbitMQ is ready"
                        break
                    fi
                    sleep 2
                    ((attempts++))
                done
                ;;
        esac
    done

    log SUCCESS "Infrastructure services started"
}

# Step 5: Start core microservices
start_core_services() {
    log STEP "[5/10] Starting core microservices..."

    # Start all microservices
    vlog "Starting bybit-connector, market-data, and technical-analysis..."
    docker-compose up -d bybit-connector market-data technical-analysis 2>&1 | grep -v "WARNING" || true

    # Wait for services to be healthy
    wait_for_service "Bybit Connector" "http://localhost:8001/health" 30
    wait_for_service "Market Data" "http://localhost:8002/health" 30
    wait_for_service "Technical Analysis" "http://localhost:8004/health" 30

    log SUCCESS "Core services started"
}

# Step 6: Start AI/ML services
start_ai_services() {
    log STEP "[6/10] Starting AI/ML services..."

    vlog "Starting ml-prediction, sentiment-analysis, and risk-metrics..."
    docker-compose up -d ml-prediction sentiment-analysis risk-metrics 2>&1 | grep -v "WARNING" || true

    # Wait for services to be healthy
    wait_for_service "ML Prediction" "http://localhost:8007/health" 30
    wait_for_service "Sentiment Analysis" "http://localhost:8008/health" 30
    wait_for_service "Risk Metrics" "http://localhost:8009/health" 30

    log SUCCESS "AI/ML services started"
}

# Step 7: Start business logic services
start_business_services() {
    log STEP "[7/10] Starting business logic services..."

    vlog "Starting portfolio-manager and trading-engine..."
    docker-compose up -d portfolio-manager trading-engine 2>&1 | grep -v "WARNING" || true

    # Wait for services to be healthy
    wait_for_service "Portfolio Manager" "http://localhost:8003/health" 30
    wait_for_service "Trading Engine" "http://localhost:8005/health" 30

    log SUCCESS "Business logic services started"
}

# Step 8: Start support services
start_support_services() {
    log STEP "[8/10] Starting support services..."

    vlog "Starting notification-service and api-gateway..."
    docker-compose up -d notification-service api-gateway 2>&1 | grep -v "WARNING" || true

    # Wait for services to be healthy
    wait_for_service "Notification Service" "http://localhost:8006/health" 30
    wait_for_service "API Gateway" "http://localhost:8000/health" 30

    log SUCCESS "Support services started"
}

# Step 9: Initialize paper trading
initialize_paper_trading() {
    log STEP "[9/10] Initializing paper trading..."

    # Check if paper trading already initialized
    local balance_response=$(curl -s http://localhost:8005/api/v1/paper/balance 2>/dev/null || echo '{"error":"not initialized"}')

    if echo "$balance_response" | grep -q '"balance"'; then
        local balance=$(echo "$balance_response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('balance', 0))" 2>/dev/null || echo "0")
        log INFO "Paper trading already initialized with balance: \$$balance"
    else
        # This comment deliberately asserts NO account size. shared/account.py
        # is the declaration of record (ADR-029), and this script is host-run
        # so importing it is allowed (CLAUDE.md money rules). A figure restated
        # here would be a second declaration agreeing with the first only by
        # coincidence: the previous wording named one, and stayed in the file
        # long after a re-scale made it wrong. Deliberately NO literal fallback
        # either -- this POST is the only place the startup path *writes* an
        # account size, and a silent default here is how the recorded
        # portfolios.initial_balance once diverged from total_value (AUDIT 2.2).
        # Refusing to guess is the safe failure. The code below READS the
        # declared value rather than restating it; keep it that way.
        local initial_balance
        if ! initial_balance=$(cd "$REPO_ROOT" && python3 -c \
            'from shared.account import PAPER_INITIAL_BALANCE; print(PAPER_INITIAL_BALANCE)'); then
            log ERROR "Could not read PAPER_INITIAL_BALANCE from shared/account.py"
            log ERROR "Refusing to seed the paper account with a guessed balance."
            exit 1
        fi

        vlog "Initializing paper trading with \$${initial_balance} balance..."

        # Initialize paper trading
        local init_response=$(curl -s -X POST http://localhost:8005/api/v1/paper/reset \
            -H "Content-Type: application/json" \
            -d "{\"initial_balance\": ${initial_balance}}" 2>/dev/null)

        if echo "$init_response" | grep -q '"success":true'; then
            log SUCCESS "Paper trading initialized with \$${initial_balance}"
        else
            log WARNING "Could not initialize paper trading (may already be set up)"
        fi
    fi
}

# Step 10: Run health checks
run_health_checks() {
    log STEP "[10/10] Running comprehensive health checks..."

    if [ -f "scripts/health_check.sh" ]; then
        vlog "Executing health_check.sh..."

        if $VERBOSE; then
            bash scripts/health_check.sh --verbose
        else
            bash scripts/health_check.sh 2>&1 | grep -E "(✓|✗|⚠|System Status|All microservices)" || true
        fi

        local health_exit=$?

        if [ $health_exit -eq 0 ]; then
            log SUCCESS "All health checks passed"
        elif [ $health_exit -eq 1 ]; then
            log WARNING "Some services degraded - check output above"
        else
            log ERROR "Critical health check failures - review output"
        fi

        return $health_exit
    else
        log WARNING "health_check.sh not found, skipping health validation"

        # Manual service count check
        local healthy_count=0
        for port in {8000..8009}; do
            if curl -s -f "http://localhost:$port/health" >/dev/null 2>&1; then
                ((healthy_count++))
            fi
        done

        log INFO "$healthy_count/10 services responding"

        if [ $healthy_count -eq 10 ]; then
            log SUCCESS "All 10 services are healthy"
            return 0
        elif [ $healthy_count -ge 7 ]; then
            log WARNING "Only $healthy_count/10 services healthy"
            return 1
        else
            log ERROR "Only $healthy_count/10 services healthy - system degraded"
            return 2
        fi
    fi
}

# Print startup summary
print_summary() {
    local exit_code=$1
    local end_time=$(date +%s)
    local duration=$((end_time - START_TIME))
    local minutes=$((duration / 60))
    local seconds=$((duration % 60))

    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}Startup Summary${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo ""

    # Show timing
    echo -e "Total startup time: ${CYAN}${minutes}m ${seconds}s${NC}"
    echo ""

    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}✓ System Status: ALL SYSTEMS OPERATIONAL${NC}"
        echo ""
        echo "All 10 microservices are running and healthy."
        echo ""
        echo -e "${CYAN}Next Steps:${NC}"
        echo "  1. Open dashboard:"
        echo "     cd dashboard && python3 -m http.server 8080"
        echo "     Access: http://localhost:8080"
        echo ""
        echo "  2. View API documentation:"
        echo "     Trading Engine: http://localhost:8005/docs"
        echo "     API Gateway: http://localhost:8000/docs"
        echo ""
        echo "  3. Configure real data (optional):"
        echo "     Follow: docs/BYBIT_API_SETUP_GUIDE.md"
        echo ""
        echo "  4. Enable notifications (optional):"
        echo "     Follow: docs/TELEGRAM_NOTIFICATIONS_SETUP.md"
        echo ""
        echo "  5. Run E2E tests:"
        echo "     cd tests/integration"
        echo "     python3 test_e2e_trading_flow.py"
        echo ""
        echo -e "${GREEN}System is ready for paper trading!${NC}"

    elif [ $exit_code -eq 1 ]; then
        echo -e "${YELLOW}⚠ System Status: DEGRADED${NC}"
        echo ""
        echo "Some services are not fully operational."
        echo ""
        echo -e "${CYAN}Action Required:${NC}"
        echo "  1. Check service status:"
        echo "     docker-compose ps"
        echo ""
        echo "  2. View logs for unhealthy services:"
        echo "     docker-compose logs -f [service-name]"
        echo ""
        echo "  3. Restart failed services:"
        echo "     docker-compose restart [service-name]"
        echo ""
        echo "  4. Re-run startup script:"
        echo "     ./scripts/startup.sh"

    else
        echo -e "${RED}✗ System Status: CRITICAL${NC}"
        echo ""
        echo "Multiple services failed to start."
        echo ""
        echo -e "${CYAN}Action Required:${NC}"
        echo "  1. Check Docker resources:"
        echo "     docker system df"
        echo "     docker stats --no-stream"
        echo ""
        echo "  2. View all logs:"
        echo "     docker-compose logs"
        echo ""
        echo "  3. Complete rebuild:"
        echo "     docker-compose down -v"
        echo "     docker-compose build --no-cache"
        echo "     ./scripts/startup.sh"
        echo ""
        echo "  4. Check system requirements:"
        echo "     - 8GB RAM minimum"
        echo "     - 20GB disk space"
        echo "     - Docker 20.10+"
        echo ""
        echo -e "${RED}System is NOT ready for trading${NC}"
    fi

    echo ""
    echo -e "${BLUE}Startup completed at $(date '+%Y-%m-%d %H:%M:%S')${NC}"
    echo ""
}

# Cleanup on exit
cleanup() {
    local exit_code=$?

    if [ $exit_code -ne 0 ]; then
        log ERROR "Startup failed with exit code $exit_code"
        echo ""
        echo "To view logs: docker-compose logs"
        echo "To retry: ./scripts/startup.sh"
    fi
}

trap cleanup EXIT

# Main execution
main() {
    print_header

    preflight_checks
    stop_existing
    build_images
    start_infrastructure
    start_core_services
    start_ai_services
    start_business_services
    start_support_services
    initialize_paper_trading

    # Run health checks and capture exit code
    run_health_checks
    local health_exit=$?

    print_summary $health_exit

    exit $health_exit
}

# Run main function
main
