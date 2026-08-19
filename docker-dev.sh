#!/bin/bash
#
# Docker Development Environment Script
# Purpose: Quick start/stop/restart development environment
# Usage: ./docker-dev.sh [start|stop|restart|status|logs|clean]
#

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
# Canonical compose file per ADR-009. Plain docker-compose.yml was renamed to
# docker-compose.legacy.yml.DISABLED, so pointing at it made every command in
# this script fail with "no configuration file provided".
COMPOSE_FILE="docker-compose.unified.yml"
COMPOSE_MONITORING="docker-compose.monitoring.yml"
PROJECT_NAME="crypto-trading-bot"

# Compose binary, resolved by check_compose(). Compose v2 is the `docker
# compose` subcommand; v1 is the standalone `docker-compose`. Both are
# supported so the script runs on either.
DC=()

# Function to display help
show_help() {
    cat << EOF
Crypto Trading Bot - Development Environment Manager

Usage: $0 [COMMAND] [OPTIONS]

Commands:
    start       Start all services
    stop        Stop all services
    restart     Restart all services
    status      Show service status
    logs        Show service logs
    clean       Stop and remove all containers, volumes, and images
    build       Build all service images
    health      Check health of all services

Options:
    -m, --monitoring    Include monitoring stack (Prometheus, Grafana)
    -d, --detach       Run in detached mode
    -f, --follow       Follow logs (with logs command)

Examples:
    $0 start -d              # Start services in background
    $0 start -m              # Start services with monitoring
    $0 logs api-gateway -f   # Follow logs for api-gateway
    $0 health                # Check all services health

EOF
}

# Function to check if Docker is running
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        echo -e "${RED}Error: Docker is not running${NC}"
        exit 1
    fi
}

# Function to resolve the Compose binary (v2 preferred, v1 fallback)
check_compose() {
    if docker compose version &> /dev/null; then
        DC=(docker compose)
    elif command -v docker-compose &> /dev/null; then
        DC=(docker-compose)
    else
        echo -e "${RED}Error: Docker Compose is not installed${NC}"
        echo "Install Compose v2 (docker compose) or v1 (docker-compose)"
        exit 1
    fi
}

# Function to start services
start_services() {
    local compose_files="-f $COMPOSE_FILE"
    local detach=""

    # Parse options
    while [[ $# -gt 0 ]]; do
        case $1 in
            -m|--monitoring)
                compose_files="$compose_files -f $COMPOSE_MONITORING"
                shift
                ;;
            -d|--detach)
                detach="-d"
                shift
                ;;
            *)
                shift
                ;;
        esac
    done

    echo -e "${BLUE}Starting Crypto Trading Bot services...${NC}"
    "${DC[@]}" $compose_files up $detach

    if [ -n "$detach" ]; then
        echo -e "${GREEN}Services started successfully!${NC}"
        echo ""
        echo "Run '$0 status' to check service status"
        echo "Run '$0 logs' to view logs"
    fi
}

# Function to stop services
stop_services() {
    echo -e "${YELLOW}Stopping Crypto Trading Bot services...${NC}"
    "${DC[@]}" -f $COMPOSE_FILE down
    echo -e "${GREEN}Services stopped successfully!${NC}"
}

# Function to restart services
restart_services() {
    stop_services
    echo ""
    start_services "$@"
}

# Function to show service status
show_status() {
    echo -e "${BLUE}Service Status:${NC}"
    echo ""
    "${DC[@]}" -f $COMPOSE_FILE ps
    echo ""

    # Count running services
    running=$("${DC[@]}" -f $COMPOSE_FILE ps | grep -c "Up" || true)
    total=$("${DC[@]}" -f $COMPOSE_FILE config --services | wc -l)

    echo "Running: $running / $total services"
}

# Function to show logs
show_logs() {
    local service=""
    local follow=""

    # Parse options
    while [[ $# -gt 0 ]]; do
        case $1 in
            -f|--follow)
                follow="-f"
                shift
                ;;
            *)
                service="$1"
                shift
                ;;
        esac
    done

    if [ -n "$service" ]; then
        echo -e "${BLUE}Showing logs for $service...${NC}"
        "${DC[@]}" -f $COMPOSE_FILE logs $follow "$service"
    else
        echo -e "${BLUE}Showing logs for all services...${NC}"
        "${DC[@]}" -f $COMPOSE_FILE logs $follow
    fi
}

# Function to clean everything
clean_all() {
    echo -e "${RED}WARNING: This will remove all containers, volumes, and images!${NC}"
    read -p "Are you sure? (yes/no): " -r
    echo

    if [[ $REPLY == "yes" ]]; then
        echo -e "${YELLOW}Stopping and removing all services...${NC}"
        "${DC[@]}" -f $COMPOSE_FILE down -v --rmi all
        echo -e "${GREEN}Cleanup completed!${NC}"
    else
        echo "Cleanup cancelled"
    fi
}

# Function to build all images
build_all() {
    echo -e "${BLUE}Building all service images...${NC}"

    if [ -f "./build-all.sh" ]; then
        bash ./build-all.sh "$@"
    else
        "${DC[@]}" -f $COMPOSE_FILE build
    fi
}

# Function to check health of all services
check_health() {
    echo -e "${BLUE}Checking service health...${NC}"
    echo ""

    # Service ports, per the canonical table in CLAUDE.md. Six of these were
    # wrong (trading-engine was listed on 8001, bybit-connector on 8004, and
    # so on), so `docker-dev.sh health` probed the wrong service for most of
    # the mesh and reported whatever happened to answer on that port.
    declare -A PORTS=(
        ["api-gateway"]="8000"
        ["bybit-connector"]="8001"
        ["market-data-service"]="8002"
        ["portfolio-manager"]="8003"
        ["technical-analysis"]="8004"
        ["trading-engine"]="8005"
        ["notification-service"]="8006"
        ["ml-prediction-service"]="8007"
        ["sentiment-analysis-service"]="8008"
        ["risk-metrics-service"]="8009"
    )

    local healthy=0
    local unhealthy=0

    for service in "${!PORTS[@]}"; do
        port=${PORTS[$service]}

        if curl -sf "http://localhost:${port}/health" > /dev/null 2>&1; then
            echo -e "${GREEN}✓${NC} $service (port $port) - Healthy"
            ((healthy++))
        else
            echo -e "${RED}✗${NC} $service (port $port) - Unhealthy"
            ((unhealthy++))
        fi
    done

    echo ""
    echo "Healthy: $healthy / $((healthy + unhealthy))"
}

# Main script
check_docker
check_compose

# Parse command
case "${1:-}" in
    start)
        shift
        start_services "$@"
        ;;
    stop)
        stop_services
        ;;
    restart)
        shift
        restart_services "$@"
        ;;
    status)
        show_status
        ;;
    logs)
        shift
        show_logs "$@"
        ;;
    clean)
        clean_all
        ;;
    build)
        shift
        build_all "$@"
        ;;
    health)
        check_health
        ;;
    help|--help|-h)
        show_help
        ;;
    "")
        show_help
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        echo ""
        show_help
        exit 1
        ;;
esac
