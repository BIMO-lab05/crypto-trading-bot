#!/bin/bash

################################################################################
# Continuous Health Check Script
#
# Purpose: Monitors service health continuously
# Usage: ./health-check.sh [environment] [--interval SECONDS] [--duration SECONDS]
# Environment: dev|staging|prod (default: dev)
#
# Exit Codes:
#   0 - All health checks passed
#   1 - One or more health checks failed
################################################################################

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
ENVIRONMENT="${1:-dev}"
CHECK_INTERVAL=30
DURATION=300  # 5 minutes default

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --interval)
            CHECK_INTERVAL="$2"
            shift 2
            ;;
        --duration)
            DURATION="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_FILE="$PROJECT_ROOT/logs/health-check-$(date +%Y%m%d-%H%M%S).log"
NAMESPACE="crypto-trading-bot-$ENVIRONMENT"

mkdir -p "$PROJECT_ROOT/logs"

################################################################################
# Utility Functions
################################################################################

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $@" | tee -a "$LOG_FILE"
}

print_status() {
    local service="$1"
    local status="$2"
    local details="$3"

    if [ "$status" == "healthy" ]; then
        echo -e "${GREEN}✓${NC} $service: $details"
    elif [ "$status" == "warning" ]; then
        echo -e "${YELLOW}⚠${NC} $service: $details"
    else
        echo -e "${RED}✗${NC} $service: $details"
    fi
}

################################################################################
# Health Check Functions
################################################################################

check_service_health() {
    local service="$1"
    local port="$2"

    POD=$(kubectl get pods -n "$NAMESPACE" -l app="$service" --field-selector=status.phase=Running --no-headers -o custom-columns=":metadata.name" 2>/dev/null | head -1)

    if [ -z "$POD" ]; then
        print_status "$service" "unhealthy" "No running pod found"
        return 1
    fi

    # Check health endpoint
    HTTP_CODE=$(kubectl exec -n "$NAMESPACE" "$POD" -- curl -s -o /dev/null -w "%{http_code}" http://localhost:${port}/health 2>/dev/null || echo "000")

    if [ "$HTTP_CODE" == "200" ]; then
        # Get response time
        RESPONSE_TIME=$(kubectl exec -n "$NAMESPACE" "$POD" -- curl -s -o /dev/null -w "%{time_total}" http://localhost:${port}/health 2>/dev/null || echo "N/A")
        print_status "$service" "healthy" "HTTP $HTTP_CODE (${RESPONSE_TIME}s response time)"
        return 0
    else
        print_status "$service" "unhealthy" "HTTP $HTTP_CODE"
        return 1
    fi
}

check_database_health() {
    POSTGRES_POD=$(kubectl get pods -n "$NAMESPACE" -l app=postgres --field-selector=status.phase=Running --no-headers -o custom-columns=":metadata.name" 2>/dev/null | head -1)

    if [ -z "$POSTGRES_POD" ]; then
        print_status "PostgreSQL" "unhealthy" "No running pod found"
        return 1
    fi

    if kubectl exec -n "$NAMESPACE" "$POSTGRES_POD" -- pg_isready -U postgres &> /dev/null; then
        # Get connection count
        CONN_COUNT=$(kubectl exec -n "$NAMESPACE" "$POSTGRES_POD" -- psql -U postgres -t -c "SELECT count(*) FROM pg_stat_activity;" 2>/dev/null | tr -d ' ')
        print_status "PostgreSQL" "healthy" "Ready ($CONN_COUNT active connections)"
        return 0
    else
        print_status "PostgreSQL" "unhealthy" "Not accepting connections"
        return 1
    fi
}

check_redis_health() {
    REDIS_POD=$(kubectl get pods -n "$NAMESPACE" -l app=redis --field-selector=status.phase=Running --no-headers -o custom-columns=":metadata.name" 2>/dev/null | head -1)

    if [ -z "$REDIS_POD" ]; then
        print_status "Redis" "unhealthy" "No running pod found"
        return 1
    fi

    PING_RESPONSE=$(kubectl exec -n "$NAMESPACE" "$REDIS_POD" -- redis-cli ping 2>/dev/null)

    if [ "$PING_RESPONSE" == "PONG" ]; then
        # Get memory usage
        USED_MEMORY=$(kubectl exec -n "$NAMESPACE" "$REDIS_POD" -- redis-cli info memory 2>/dev/null | grep "used_memory_human:" | cut -d: -f2 | tr -d '\r')
        print_status "Redis" "healthy" "PONG (Memory: $USED_MEMORY)"
        return 0
    else
        print_status "Redis" "unhealthy" "No PONG response"
        return 1
    fi
}

check_rabbitmq_health() {
    RABBITMQ_POD=$(kubectl get pods -n "$NAMESPACE" -l app=rabbitmq --field-selector=status.phase=Running --no-headers -o custom-columns=":metadata.name" 2>/dev/null | head -1)

    if [ -z "$RABBITMQ_POD" ]; then
        print_status "RabbitMQ" "unhealthy" "No running pod found"
        return 1
    fi

    if kubectl exec -n "$NAMESPACE" "$RABBITMQ_POD" -- rabbitmqctl node_health_check &> /dev/null; then
        # Get queue count
        QUEUE_COUNT=$(kubectl exec -n "$NAMESPACE" "$RABBITMQ_POD" -- rabbitmqctl list_queues 2>/dev/null | tail -n +2 | wc -l)
        print_status "RabbitMQ" "healthy" "Node healthy ($QUEUE_COUNT queues)"
        return 0
    else
        print_status "RabbitMQ" "unhealthy" "Node health check failed"
        return 1
    fi
}

check_pod_resources() {
    if ! kubectl top pods -n "$NAMESPACE" &> /dev/null; then
        print_status "Resource Metrics" "warning" "Metrics server not available"
        return 1
    fi

    # Check for high resource usage
    HIGH_CPU_PODS=$(kubectl top pods -n "$NAMESPACE" --no-headers 2>/dev/null | awk '$2 ~ /m$/ && substr($2,1,length($2)-1) > 800 {print $1}')
    HIGH_MEM_PODS=$(kubectl top pods -n "$NAMESPACE" --no-headers 2>/dev/null | awk '$3 ~ /Mi$/ && substr($3,1,length($3)-2) > 500 {print $1}')

    if [ -z "$HIGH_CPU_PODS" ] && [ -z "$HIGH_MEM_PODS" ]; then
        print_status "Resource Usage" "healthy" "All pods within normal limits"
        return 0
    else
        if [ -n "$HIGH_CPU_PODS" ]; then
            print_status "Resource Usage" "warning" "High CPU: $(echo $HIGH_CPU_PODS | tr '\n' ' ')"
        fi
        if [ -n "$HIGH_MEM_PODS" ]; then
            print_status "Resource Usage" "warning" "High Memory: $(echo $HIGH_MEM_PODS | tr '\n' ' ')"
        fi
        return 1
    fi
}

check_queue_depths() {
    RABBITMQ_POD=$(kubectl get pods -n "$NAMESPACE" -l app=rabbitmq --field-selector=status.phase=Running --no-headers -o custom-columns=":metadata.name" 2>/dev/null | head -1)

    if [ -z "$RABBITMQ_POD" ]; then
        return 1
    fi

    # Check for deep queues (potential backlog)
    DEEP_QUEUES=$(kubectl exec -n "$NAMESPACE" "$RABBITMQ_POD" -- rabbitmqctl list_queues name messages 2>/dev/null | awk '$2 > 1000 {print $1 "(" $2 ")"}')

    if [ -z "$DEEP_QUEUES" ]; then
        print_status "Queue Depths" "healthy" "All queues processing normally"
        return 0
    else
        print_status "Queue Depths" "warning" "Deep queues: $(echo $DEEP_QUEUES | tr '\n' ' ')"
        return 1
    fi
}

check_cache_hit_rate() {
    REDIS_POD=$(kubectl get pods -n "$NAMESPACE" -l app=redis --field-selector=status.phase=Running --no-headers -o custom-columns=":metadata.name" 2>/dev/null | head -1)

    if [ -z "$REDIS_POD" ]; then
        return 1
    fi

    # Get hit rate statistics
    STATS=$(kubectl exec -n "$NAMESPACE" "$REDIS_POD" -- redis-cli info stats 2>/dev/null)
    HITS=$(echo "$STATS" | grep "keyspace_hits:" | cut -d: -f2 | tr -d '\r')
    MISSES=$(echo "$STATS" | grep "keyspace_misses:" | cut -d: -f2 | tr -d '\r')

    if [ -n "$HITS" ] && [ -n "$MISSES" ]; then
        TOTAL=$((HITS + MISSES))
        if [ "$TOTAL" -gt 0 ]; then
            HIT_RATE=$((HITS * 100 / TOTAL))
            if [ "$HIT_RATE" -gt 80 ]; then
                print_status "Cache Hit Rate" "healthy" "${HIT_RATE}%"
                return 0
            else
                print_status "Cache Hit Rate" "warning" "${HIT_RATE}% (low)"
                return 1
            fi
        fi
    fi

    print_status "Cache Hit Rate" "warning" "Unable to calculate"
    return 1
}

################################################################################
# Main Health Check Loop
################################################################################

main() {
    log "Starting health monitoring for environment: $ENVIRONMENT"
    log "Check interval: ${CHECK_INTERVAL}s, Duration: ${DURATION}s"

    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║         Crypto Trading Bot - Health Monitoring              ║"
    echo "║                                                              ║"
    echo "║  Environment: $(printf "%-48s" "$ENVIRONMENT")║"
    echo "║  Interval: $(printf "%-51s" "${CHECK_INTERVAL}s")║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    # Check kubectl availability
    if ! command -v kubectl &> /dev/null; then
        log "ERROR: kubectl not found"
        exit 1
    fi

    # Check namespace exists
    if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
        log "ERROR: Namespace $NAMESPACE does not exist"
        exit 1
    fi

    START_TIME=$(date +%s)
    ITERATION=0
    TOTAL_FAILURES=0

    # Services to monitor
    SERVICES=(
        "api-gateway:8000"
        "trading-engine:8001"
        "market-data-service:8002"
        "technical-analysis:8003"
        "portfolio-manager:8004"
        "bybit-connector:8005"
        "ml-service:8006"
        "notification-service:8007"
        "risk-metrics:8008"
    )

    while true; do
        CURRENT_TIME=$(date +%s)
        ELAPSED=$((CURRENT_TIME - START_TIME))

        if [ "$DURATION" -gt 0 ] && [ "$ELAPSED" -ge "$DURATION" ]; then
            log "Health monitoring completed (duration reached)"
            break
        fi

        ITERATION=$((ITERATION + 1))
        FAILURES=0

        echo -e "\n${BLUE}=== Health Check #$ITERATION ($(date +'%H:%M:%S')) ===${NC}"

        # Check infrastructure services
        check_database_health || FAILURES=$((FAILURES + 1))
        check_redis_health || FAILURES=$((FAILURES + 1))
        check_rabbitmq_health || FAILURES=$((FAILURES + 1))

        # Check application services
        for service_port in "${SERVICES[@]}"; do
            SERVICE=$(echo $service_port | cut -d: -f1)
            PORT=$(echo $service_port | cut -d: -f2)
            check_service_health "$SERVICE" "$PORT" || FAILURES=$((FAILURES + 1))
        done

        # Check system metrics
        check_pod_resources || true  # Don't count as failure
        check_queue_depths || true   # Don't count as failure
        check_cache_hit_rate || true # Don't count as failure

        TOTAL_FAILURES=$((TOTAL_FAILURES + FAILURES))

        if [ "$FAILURES" -gt 0 ]; then
            log "WARNING: $FAILURES health checks failed in iteration $ITERATION"
        else
            log "INFO: All health checks passed in iteration $ITERATION"
        fi

        if [ "$DURATION" -gt 0 ]; then
            REMAINING=$((DURATION - ELAPSED))
            echo -e "\n${BLUE}Time remaining: ${REMAINING}s | Next check in ${CHECK_INTERVAL}s${NC}"
        fi

        sleep "$CHECK_INTERVAL"
    done

    # Final summary
    echo -e "\n${BLUE}=== Health Monitoring Summary ===${NC}"
    log "Total iterations: $ITERATION"
    log "Total failures: $TOTAL_FAILURES"
    log "Log file: $LOG_FILE"

    if [ "$TOTAL_FAILURES" -eq 0 ]; then
        echo -e "${GREEN}✅ All health checks passed${NC}"
        exit 0
    else
        echo -e "${YELLOW}⚠️  $TOTAL_FAILURES health check(s) failed${NC}"
        exit 1
    fi
}

main "$@"
