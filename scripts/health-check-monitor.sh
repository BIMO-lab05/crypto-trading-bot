#!/bin/bash

################################################################################
# Health Check Monitoring Script
# Purpose: Automated monitoring of all crypto trading bot services
# Author: DevOps Automation Agent
# Version: 1.0
################################################################################

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PROJECT_ROOT/logs/health-check.log"
ALERT_FILE="$PROJECT_ROOT/logs/health-alerts.log"

# Service configuration with health endpoints
declare -A SERVICES=(
    ["api-gateway"]="http://localhost:8000/health"
    ["bybit-connector"]="http://localhost:8001/health"
    ["market-data"]="http://localhost:8002/health"
    ["portfolio-manager"]="http://localhost:8003/health"
    ["technical-analysis"]="http://localhost:8004/health"
    ["trading-engine"]="http://localhost:8005/health"
    ["notification-service"]="http://localhost:8006/health"
    ["ml-prediction"]="http://localhost:8007/health"
    ["sentiment-analysis"]="http://localhost:8008/health"
    ["risk-metrics"]="http://localhost:8009/health"
)

# Database and infrastructure services
declare -A INFRA_SERVICES=(
    ["postgres"]="crypto-bot-postgres"
    ["timescaledb"]="crypto-bot-timescaledb"
    ["redis"]="crypto-bot-redis"
    ["rabbitmq"]="crypto-bot-rabbitmq"
    ["prometheus"]="crypto-bot-prometheus"
    ["grafana"]="crypto-bot-grafana"
)

################################################################################
# Function: Initialize
# Description: Create necessary directories and files
################################################################################
initialize() {
    mkdir -p "$PROJECT_ROOT/logs"

    if [ ! -f "$LOG_FILE" ]; then
        touch "$LOG_FILE"
    fi

    if [ ! -f "$ALERT_FILE" ]; then
        touch "$ALERT_FILE"
    fi

    echo -e "${BLUE}=== Health Check Monitor Started at $(date) ===${NC}"
    echo "=== Health Check Started at $(date) ===" >> "$LOG_FILE"
}

################################################################################
# Function: Check Service Health
# Description: Check HTTP health endpoint for a service
# Arguments:
#   $1 - Service name
#   $2 - Health endpoint URL
################################################################################
check_service_health() {
    local service_name=$1
    local health_url=$2
    local response
    local http_code

    # Attempt to curl health endpoint with timeout
    response=$(curl -s -w "\n%{http_code}" --max-time 5 "$health_url" 2>&1)
    http_code=$(echo "$response" | tail -n1)

    if [ "$http_code" = "200" ]; then
        echo -e "${GREEN}✓${NC} $service_name: HEALTHY"
        echo "$(date) - $service_name: HEALTHY" >> "$LOG_FILE"
        return 0
    else
        echo -e "${RED}✗${NC} $service_name: UNHEALTHY (HTTP: $http_code)"
        echo "$(date) - $service_name: UNHEALTHY (HTTP: $http_code)" >> "$LOG_FILE"
        echo "$(date) - ALERT: $service_name is UNHEALTHY" >> "$ALERT_FILE"
        return 1
    fi
}

################################################################################
# Function: Check Container Status
# Description: Check if Docker container is running
# Arguments:
#   $1 - Container name
################################################################################
check_container_status() {
    local container_name=$1
    local status

    status=$(docker inspect -f '{{.State.Status}}' "$container_name" 2>/dev/null)

    if [ "$status" = "running" ]; then
        # Additional health check from Docker
        health=$(docker inspect -f '{{.State.Health.Status}}' "$container_name" 2>/dev/null)

        if [ "$health" = "healthy" ] || [ "$health" = "" ]; then
            echo -e "${GREEN}✓${NC} $container_name: RUNNING"
            echo "$(date) - $container_name: RUNNING" >> "$LOG_FILE"
            return 0
        else
            echo -e "${YELLOW}⚠${NC} $container_name: RUNNING but $health"
            echo "$(date) - $container_name: RUNNING but $health" >> "$LOG_FILE"
            return 1
        fi
    else
        echo -e "${RED}✗${NC} $container_name: NOT RUNNING (Status: $status)"
        echo "$(date) - $container_name: NOT RUNNING (Status: $status)" >> "$LOG_FILE"
        echo "$(date) - ALERT: $container_name is NOT RUNNING" >> "$ALERT_FILE"
        return 1
    fi
}

################################################################################
# Function: Check All Services
# Description: Iterate through all services and check health
################################################################################
check_all_services() {
    local total_services=0
    local healthy_services=0

    echo -e "\n${BLUE}=== Microservices Health Check ===${NC}"

    for service in "${!SERVICES[@]}"; do
        ((total_services++))
        if check_service_health "$service" "${SERVICES[$service]}"; then
            ((healthy_services++))
        fi
    done

    echo -e "\n${BLUE}=== Infrastructure Services Check ===${NC}"

    for service in "${!INFRA_SERVICES[@]}"; do
        ((total_services++))
        if check_container_status "${INFRA_SERVICES[$service]}"; then
            ((healthy_services++))
        fi
    done

    # Summary
    echo -e "\n${BLUE}=== Health Check Summary ===${NC}"
    echo "Total Services: $total_services"
    echo "Healthy: $healthy_services"
    echo "Unhealthy: $((total_services - healthy_services))"

    local health_percentage=$((healthy_services * 100 / total_services))

    if [ $health_percentage -eq 100 ]; then
        echo -e "${GREEN}System Status: ALL SYSTEMS OPERATIONAL${NC}"
    elif [ $health_percentage -ge 80 ]; then
        echo -e "${YELLOW}System Status: DEGRADED${NC}"
    else
        echo -e "${RED}System Status: CRITICAL${NC}"
    fi

    echo "Health Percentage: $health_percentage%"
    echo "$(date) - Health Summary: $healthy_services/$total_services healthy ($health_percentage%)" >> "$LOG_FILE"

    return $((total_services - healthy_services))
}

################################################################################
# Function: Check Resource Usage
# Description: Monitor Docker resource consumption
################################################################################
check_resource_usage() {
    echo -e "\n${BLUE}=== Resource Usage ===${NC}"

    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}" | head -20

    echo "$(date) - Resource usage checked" >> "$LOG_FILE"
}

################################################################################
# Function: Generate Report
# Description: Generate detailed health report
################################################################################
generate_report() {
    local report_file="$PROJECT_ROOT/logs/health-report-$(date +%Y%m%d-%H%M%S).txt"

    {
        echo "=== Crypto Trading Bot Health Report ==="
        echo "Generated: $(date)"
        echo ""
        echo "=== Docker Containers ==="
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
        echo ""
        echo "=== Recent Alerts ==="
        tail -20 "$ALERT_FILE" 2>/dev/null || echo "No alerts"
        echo ""
        echo "=== Resource Usage ==="
        docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"
    } > "$report_file"

    echo -e "\n${GREEN}Report generated: $report_file${NC}"
}

################################################################################
# Function: Continuous Monitor
# Description: Run health checks continuously at specified interval
# Arguments:
#   $1 - Check interval in seconds (default: 60)
################################################################################
continuous_monitor() {
    local interval=${1:-60}

    echo -e "${BLUE}Starting continuous monitoring (interval: ${interval}s)${NC}"
    echo "Press Ctrl+C to stop"

    while true; do
        clear
        check_all_services
        echo -e "\n${YELLOW}Next check in ${interval} seconds...${NC}"
        sleep "$interval"
    done
}

################################################################################
# Function: Auto Restart Unhealthy
# Description: Automatically restart unhealthy containers
################################################################################
auto_restart_unhealthy() {
    echo -e "\n${YELLOW}=== Auto-Restart Mode ===${NC}"

    for service in "${!SERVICES[@]}"; do
        if ! check_service_health "$service" "${SERVICES[$service]}" >/dev/null 2>&1; then
            local container_name="crypto-bot-${service}"
            echo -e "${YELLOW}Restarting $container_name...${NC}"
            docker restart "$container_name"
            echo "$(date) - Auto-restarted $container_name" >> "$LOG_FILE"
            sleep 5
        fi
    done

    for service in "${!INFRA_SERVICES[@]}"; do
        if ! check_container_status "${INFRA_SERVICES[$service]}" >/dev/null 2>&1; then
            echo -e "${YELLOW}Restarting ${INFRA_SERVICES[$service]}...${NC}"
            docker restart "${INFRA_SERVICES[$service]}"
            echo "$(date) - Auto-restarted ${INFRA_SERVICES[$service]}" >> "$LOG_FILE"
            sleep 5
        fi
    done
}

################################################################################
# Function: Show Help
# Description: Display usage information
################################################################################
show_help() {
    cat << EOF
Health Check Monitor for Crypto Trading Bot

Usage: $0 [OPTIONS]

OPTIONS:
    -h, --help              Show this help message
    -c, --check             Run single health check
    -m, --monitor [INTERVAL] Run continuous monitoring (default interval: 60s)
    -r, --restart           Auto-restart unhealthy containers
    -R, --report            Generate detailed health report
    -u, --usage             Show resource usage
    -a, --all               Run comprehensive check (health + resources + report)

EXAMPLES:
    $0 -c                   # Single health check
    $0 -m 30                # Monitor every 30 seconds
    $0 -r                   # Restart unhealthy services
    $0 -a                   # Full system check with report

EOF
}

################################################################################
# Main Script Execution
################################################################################
main() {
    initialize

    case "${1:-}" in
        -h|--help)
            show_help
            ;;
        -c|--check)
            check_all_services
            ;;
        -m|--monitor)
            continuous_monitor "${2:-60}"
            ;;
        -r|--restart)
            check_all_services
            auto_restart_unhealthy
            echo -e "\n${GREEN}Waiting 10 seconds for services to start...${NC}"
            sleep 10
            check_all_services
            ;;
        -R|--report)
            check_all_services
            generate_report
            ;;
        -u|--usage)
            check_resource_usage
            ;;
        -a|--all)
            check_all_services
            check_resource_usage
            generate_report
            ;;
        *)
            echo -e "${YELLOW}No option specified. Running default health check.${NC}"
            echo "Use -h or --help for usage information."
            echo ""
            check_all_services
            ;;
    esac
}

# Run main function with all arguments
main "$@"
