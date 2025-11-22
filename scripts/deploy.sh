#!/bin/bash

################################################################################
# Deployment Automation Script
# Purpose: Streamline deployment operations for crypto trading bot
# Author: DevOps Automation Agent
# Version: 1.0
################################################################################

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.yml"
INFRA_COMPOSE_FILE="$PROJECT_ROOT/infrastructure/docker-compose.yml"
LOG_DIR="$PROJECT_ROOT/logs"
BACKUP_DIR="$PROJECT_ROOT/backups"

################################################################################
# Function: Print Banner
################################################################################
print_banner() {
    echo -e "${CYAN}"
    cat << "EOF"
╔═══════════════════════════════════════════════════════════════╗
║         Crypto Trading Bot - Deployment Manager              ║
║                   DevOps Automation v1.0                      ║
╚═══════════════════════════════════════════════════════════════╝
EOF
    echo -e "${NC}"
}

################################################################################
# Function: Initialize
################################################################################
initialize() {
    mkdir -p "$LOG_DIR" "$BACKUP_DIR"
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')] Deployment operation started${NC}"
}

################################################################################
# Function: Check Prerequisites
################################################################################
check_prerequisites() {
    echo -e "${BLUE}Checking prerequisites...${NC}"

    # Check Docker
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Error: Docker is not installed${NC}"
        exit 1
    fi

    # Check Docker Compose
    if ! docker compose version &> /dev/null; then
        echo -e "${RED}Error: Docker Compose is not installed${NC}"
        exit 1
    fi

    # Check if docker-compose.yml exists
    if [ ! -f "$COMPOSE_FILE" ]; then
        echo -e "${RED}Error: docker-compose.yml not found at $COMPOSE_FILE${NC}"
        exit 1
    fi

    echo -e "${GREEN}✓ Prerequisites check passed${NC}"
}

################################################################################
# Function: Quick Restart All Services
################################################################################
quick_restart() {
    echo -e "${YELLOW}=== Quick Restart All Services ===${NC}"

    # Restart infrastructure services
    echo -e "${BLUE}Restarting infrastructure services...${NC}"
    cd "$PROJECT_ROOT/infrastructure"
    docker compose restart

    # Restart application services
    echo -e "${BLUE}Restarting application services...${NC}"
    cd "$PROJECT_ROOT"
    docker compose restart

    echo -e "${GREEN}✓ All services restarted${NC}"

    # Wait for services to be healthy
    echo -e "${BLUE}Waiting for services to be healthy...${NC}"
    sleep 10

    # Check health
    bash "$SCRIPT_DIR/health-check-monitor.sh" -c
}

################################################################################
# Function: Rebuild Specific Service
################################################################################
rebuild_service() {
    local service_name=$1

    if [ -z "$service_name" ]; then
        echo -e "${RED}Error: Service name not provided${NC}"
        echo "Usage: $0 rebuild <service-name>"
        echo "Example: $0 rebuild trading-engine"
        exit 1
    fi

    echo -e "${YELLOW}=== Rebuilding Service: $service_name ===${NC}"

    cd "$PROJECT_ROOT"

    # Stop the service
    echo -e "${BLUE}Stopping $service_name...${NC}"
    docker compose stop "$service_name"

    # Remove the container
    echo -e "${BLUE}Removing old container...${NC}"
    docker compose rm -f "$service_name"

    # Rebuild the service
    echo -e "${BLUE}Building $service_name...${NC}"
    docker compose build --no-cache "$service_name"

    # Start the service
    echo -e "${BLUE}Starting $service_name...${NC}"
    docker compose up -d "$service_name"

    # Wait for health
    echo -e "${BLUE}Waiting for $service_name to be healthy...${NC}"
    sleep 10

    # Check service health
    local container_name="crypto-bot-$service_name"
    local health=$(docker inspect -f '{{.State.Health.Status}}' "$container_name" 2>/dev/null || echo "unknown")

    if [ "$health" = "healthy" ]; then
        echo -e "${GREEN}✓ $service_name is healthy${NC}"
    else
        echo -e "${YELLOW}⚠ $service_name status: $health${NC}"
        echo -e "${BLUE}Checking logs...${NC}"
        docker logs --tail 50 "$container_name"
    fi
}

################################################################################
# Function: Full System Reset
################################################################################
full_reset() {
    echo -e "${RED}=== FULL SYSTEM RESET ===${NC}"
    echo -e "${YELLOW}WARNING: This will destroy all containers and volumes!${NC}"
    read -p "Are you sure? Type 'yes' to continue: " confirmation

    if [ "$confirmation" != "yes" ]; then
        echo -e "${BLUE}Reset cancelled${NC}"
        exit 0
    fi

    echo -e "${BLUE}Creating backup before reset...${NC}"
    create_backup

    # Stop all services
    echo -e "${BLUE}Stopping all services...${NC}"
    cd "$PROJECT_ROOT"
    docker compose down
    cd "$PROJECT_ROOT/infrastructure"
    docker compose down

    # Remove volumes (optional)
    read -p "Remove volumes (data will be lost)? Type 'yes' to remove: " remove_volumes
    if [ "$remove_volumes" = "yes" ]; then
        echo -e "${YELLOW}Removing volumes...${NC}"
        cd "$PROJECT_ROOT"
        docker compose down -v
        cd "$PROJECT_ROOT/infrastructure"
        docker compose down -v
    fi

    # Clean up dangling images
    echo -e "${BLUE}Cleaning up Docker resources...${NC}"
    docker system prune -f

    echo -e "${GREEN}✓ System reset complete${NC}"
    echo -e "${BLUE}To restart the system, run: $0 start${NC}"
}

################################################################################
# Function: Start All Services
################################################################################
start_all() {
    echo -e "${YELLOW}=== Starting All Services ===${NC}"

    # Start infrastructure services first
    echo -e "${BLUE}Starting infrastructure services...${NC}"
    cd "$PROJECT_ROOT/infrastructure"
    docker compose up -d

    echo -e "${BLUE}Waiting for infrastructure to be ready...${NC}"
    sleep 15

    # Start application services
    echo -e "${BLUE}Starting application services...${NC}"
    cd "$PROJECT_ROOT"
    docker compose up -d

    echo -e "${BLUE}Waiting for services to be healthy...${NC}"
    sleep 15

    # Check health
    bash "$SCRIPT_DIR/health-check-monitor.sh" -c

    echo -e "${GREEN}✓ All services started${NC}"
}

################################################################################
# Function: Stop All Services
################################################################################
stop_all() {
    echo -e "${YELLOW}=== Stopping All Services ===${NC}"

    # Stop application services
    echo -e "${BLUE}Stopping application services...${NC}"
    cd "$PROJECT_ROOT"
    docker compose stop

    # Stop infrastructure services
    echo -e "${BLUE}Stopping infrastructure services...${NC}"
    cd "$PROJECT_ROOT/infrastructure"
    docker compose stop

    echo -e "${GREEN}✓ All services stopped${NC}"
}

################################################################################
# Function: Rebuild All Services
################################################################################
rebuild_all() {
    echo -e "${YELLOW}=== Rebuilding All Services ===${NC}"

    # Stop services
    echo -e "${BLUE}Stopping services...${NC}"
    cd "$PROJECT_ROOT"
    docker compose stop

    # Rebuild all
    echo -e "${BLUE}Rebuilding all services...${NC}"
    docker compose build --no-cache

    # Start services
    echo -e "${BLUE}Starting services...${NC}"
    docker compose up -d

    # Wait for health
    echo -e "${BLUE}Waiting for services to be healthy...${NC}"
    sleep 15

    # Check health
    bash "$SCRIPT_DIR/health-check-monitor.sh" -c

    echo -e "${GREEN}✓ All services rebuilt${NC}"
}

################################################################################
# Function: Create Backup
################################################################################
create_backup() {
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="$BACKUP_DIR/backup_$timestamp.tar.gz"

    echo -e "${BLUE}Creating backup...${NC}"

    # Export database data
    docker exec crypto-bot-postgres pg_dump -U cryptobot cryptobot > "$BACKUP_DIR/postgres_$timestamp.sql"
    docker exec crypto-bot-timescaledb pg_dump -U cryptobot market_data > "$BACKUP_DIR/timescale_$timestamp.sql"

    # Backup logs and configurations
    tar -czf "$backup_file" \
        --exclude='*.pyc' \
        --exclude='__pycache__' \
        "$PROJECT_ROOT/logs" \
        "$PROJECT_ROOT/services/*/logs" \
        "$PROJECT_ROOT/services/ml-prediction-service/models" \
        "$BACKUP_DIR/postgres_$timestamp.sql" \
        "$BACKUP_DIR/timescale_$timestamp.sql" \
        2>/dev/null

    echo -e "${GREEN}✓ Backup created: $backup_file${NC}"

    # Clean old SQL dumps
    rm -f "$BACKUP_DIR/postgres_$timestamp.sql" "$BACKUP_DIR/timescale_$timestamp.sql"
}

################################################################################
# Function: View Logs
################################################################################
view_logs() {
    local service_name=$1

    if [ -z "$service_name" ]; then
        echo -e "${BLUE}Showing logs for all services...${NC}"
        cd "$PROJECT_ROOT"
        docker compose logs --tail=50 -f
    else
        echo -e "${BLUE}Showing logs for $service_name...${NC}"
        local container_name="crypto-bot-$service_name"
        docker logs -f --tail=100 "$container_name"
    fi
}

################################################################################
# Function: Show Status
################################################################################
show_status() {
    echo -e "${YELLOW}=== System Status ===${NC}\n"

    echo -e "${BLUE}Docker Containers:${NC}"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep crypto-bot

    echo -e "\n${BLUE}Resource Usage:${NC}"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" | grep crypto-bot

    echo -e "\n${BLUE}Recent Logs:${NC}"
    echo "Check $LOG_DIR for detailed logs"
}

################################################################################
# Function: Clean Orphaned Containers
################################################################################
clean_orphans() {
    echo -e "${YELLOW}=== Cleaning Orphaned Containers ===${NC}"

    # Find and remove stopped containers
    local stopped=$(docker ps -a --filter "status=exited" --format "{{.Names}}" | grep -v crypto-bot || true)

    if [ -n "$stopped" ]; then
        echo -e "${BLUE}Removing stopped containers:${NC}"
        echo "$stopped"
        docker rm $stopped
    else
        echo -e "${GREEN}No orphaned containers found${NC}"
    fi

    # Clean up unused images
    echo -e "${BLUE}Removing unused images...${NC}"
    docker image prune -f

    # Clean up unused volumes
    echo -e "${BLUE}Removing unused volumes...${NC}"
    docker volume prune -f

    echo -e "${GREEN}✓ Cleanup complete${NC}"
}

################################################################################
# Function: Update Services
################################################################################
update_services() {
    echo -e "${YELLOW}=== Updating Services ===${NC}"

    # Pull latest base images
    echo -e "${BLUE}Pulling latest base images...${NC}"
    cd "$PROJECT_ROOT"
    docker compose pull

    # Rebuild services with updated images
    echo -e "${BLUE}Rebuilding services...${NC}"
    docker compose build

    # Restart services
    echo -e "${BLUE}Restarting services...${NC}"
    docker compose up -d

    echo -e "${GREEN}✓ Services updated${NC}"
}

################################################################################
# Function: Show Help
################################################################################
show_help() {
    cat << EOF
${CYAN}Crypto Trading Bot - Deployment Manager${NC}

${YELLOW}USAGE:${NC}
    $0 <command> [options]

${YELLOW}COMMANDS:${NC}
    ${GREEN}start${NC}              Start all services
    ${GREEN}stop${NC}               Stop all services
    ${GREEN}restart${NC}            Quick restart all services
    ${GREEN}rebuild [service]${NC}  Rebuild specific service or all services
    ${GREEN}reset${NC}              Full system reset (WARNING: destructive)
    ${GREEN}status${NC}             Show system status
    ${GREEN}logs [service]${NC}     View logs (all or specific service)
    ${GREEN}health${NC}             Run health check
    ${GREEN}backup${NC}             Create system backup
    ${GREEN}clean${NC}              Clean orphaned containers and images
    ${GREEN}update${NC}             Update all services to latest images
    ${GREEN}help${NC}               Show this help message

${YELLOW}EXAMPLES:${NC}
    $0 start                    # Start all services
    $0 restart                  # Quick restart
    $0 rebuild trading-engine   # Rebuild specific service
    $0 rebuild                  # Rebuild all services
    $0 logs trading-engine      # View specific service logs
    $0 health                   # Run health check
    $0 backup                   # Create backup
    $0 clean                    # Clean up orphaned resources

${YELLOW}NOTES:${NC}
    - Infrastructure services (PostgreSQL, Redis, etc.) start first
    - Health checks run automatically after start/restart operations
    - Backups are stored in: $BACKUP_DIR
    - Logs are stored in: $LOG_DIR

EOF
}

################################################################################
# Main Script Execution
################################################################################
main() {
    print_banner
    check_prerequisites
    initialize

    case "${1:-}" in
        start)
            start_all
            ;;
        stop)
            stop_all
            ;;
        restart)
            quick_restart
            ;;
        rebuild)
            if [ -n "${2:-}" ]; then
                rebuild_service "$2"
            else
                rebuild_all
            fi
            ;;
        reset)
            full_reset
            ;;
        status)
            show_status
            ;;
        logs)
            view_logs "${2:-}"
            ;;
        health)
            bash "$SCRIPT_DIR/health-check-monitor.sh" -a
            ;;
        backup)
            create_backup
            ;;
        clean)
            clean_orphans
            ;;
        update)
            update_services
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            echo -e "${RED}Error: Unknown command '${1:-}'${NC}\n"
            show_help
            exit 1
            ;;
    esac

    echo -e "\n${GREEN}Operation completed successfully!${NC}"
}

# Run main function with all arguments
main "$@"
