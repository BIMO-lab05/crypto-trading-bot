#!/bin/bash
# =============================================================================
# Staging Verification Script for Crypto Trading Bot
# =============================================================================
# Version: 1.0
# Created: 2025-12-12
#
# This script verifies the staging deployment health and status
# Namespace: trading-bot-staging
#
# Usage:
#   ./verify-staging.sh [options]
#
# Options:
#   --detailed      Show detailed health information
#   --watch         Continuously watch pod status
#   --test-health   Test health check endpoints
#   --json          Output results in JSON format
#   --help          Show this help message
# =============================================================================

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
NAMESPACE="trading-bot-staging"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Options
DETAILED=false
WATCH_MODE=false
TEST_HEALTH=false
JSON_OUTPUT=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --detailed|-d)
            DETAILED=true
            shift
            ;;
        --watch|-w)
            WATCH_MODE=true
            shift
            ;;
        --test-health|-t)
            TEST_HEALTH=true
            shift
            ;;
        --json|-j)
            JSON_OUTPUT=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --detailed, -d    Show detailed health information"
            echo "  --watch, -w       Continuously watch pod status"
            echo "  --test-health, -t Test health check endpoints"
            echo "  --json, -j        Output results in JSON format"
            echo "  --help, -h        Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Function to print section headers
print_header() {
    if [ "$JSON_OUTPUT" = false ]; then
        echo ""
        echo -e "${BLUE}========================================${NC}"
        echo -e "${BLUE}$1${NC}"
        echo -e "${BLUE}========================================${NC}"
        echo ""
    fi
}

# Check if namespace exists
check_namespace() {
    if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
        echo -e "${RED}Error: Namespace '$NAMESPACE' does not exist${NC}"
        echo "Run ./deploy-staging.sh to deploy"
        exit 1
    fi
}

# Check pod status
check_pods() {
    print_header "Pod Status"

    local all_ready=true
    local total_pods=0
    local ready_pods=0
    local pod_data=()

    while IFS= read -r line; do
        if [ -z "$line" ]; then
            continue
        fi

        total_pods=$((total_pods + 1))

        pod_name=$(echo "$line" | awk '{print $1}')
        ready=$(echo "$line" | awk '{print $2}')
        status=$(echo "$line" | awk '{print $3}')
        restarts=$(echo "$line" | awk '{print $4}')
        age=$(echo "$line" | awk '{print $5}')

        # Check if pod is ready
        if [ "$status" = "Running" ]; then
            ready_current=$(echo "$ready" | cut -d'/' -f1)
            ready_total=$(echo "$ready" | cut -d'/' -f2)
            if [ "$ready_current" = "$ready_total" ]; then
                if [ "$JSON_OUTPUT" = false ]; then
                    echo -e "${GREEN}[OK]${NC} $pod_name - $status ($ready) - Restarts: $restarts - Age: $age"
                fi
                ready_pods=$((ready_pods + 1))
            else
                if [ "$JSON_OUTPUT" = false ]; then
                    echo -e "${YELLOW}[PARTIAL]${NC} $pod_name - $status ($ready) - Restarts: $restarts"
                fi
                all_ready=false
            fi
        else
            if [ "$JSON_OUTPUT" = false ]; then
                echo -e "${RED}[FAIL]${NC} $pod_name - $status ($ready) - Restarts: $restarts"
            fi
            all_ready=false

            # Show events for failed pods
            if [ "$DETAILED" = true ]; then
                echo "  Recent events:"
                kubectl get events -n "$NAMESPACE" --field-selector involvedObject.name="$pod_name" --sort-by='.lastTimestamp' | tail -5
                echo ""
            fi
        fi
    done < <(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null)

    echo ""
    echo -e "Pods Ready: ${CYAN}$ready_pods/$total_pods${NC}"

    if [ "$all_ready" = true ]; then
        echo -e "${GREEN}All pods are healthy${NC}"
        return 0
    else
        echo -e "${YELLOW}Some pods are not ready${NC}"
        return 1
    fi
}

# Check HPA status
check_hpa() {
    print_header "HorizontalPodAutoscaler Status"

    echo -e "${YELLOW}HPA Configuration:${NC}"
    kubectl get hpa -n "$NAMESPACE" 2>/dev/null

    if [ "$DETAILED" = true ]; then
        echo ""
        echo -e "${YELLOW}HPA Details:${NC}"
        kubectl describe hpa -n "$NAMESPACE" 2>/dev/null | grep -E "Name:|Min replicas:|Max replicas:|Deployment pods:|Current|Target"
    fi
}

# Check services
check_services() {
    print_header "Service Status"

    echo -e "${YELLOW}Services:${NC}"
    kubectl get svc -n "$NAMESPACE" 2>/dev/null

    if [ "$DETAILED" = true ]; then
        echo ""
        echo -e "${YELLOW}Endpoints:${NC}"
        kubectl get endpoints -n "$NAMESPACE" 2>/dev/null
    fi
}

# Check PVCs
check_storage() {
    print_header "Storage Status"

    local all_bound=true

    while IFS= read -r line; do
        if [ -z "$line" ]; then
            continue
        fi

        pvc_name=$(echo "$line" | awk '{print $1}')
        status=$(echo "$line" | awk '{print $2}')
        volume=$(echo "$line" | awk '{print $3}')
        capacity=$(echo "$line" | awk '{print $4}')

        if [ "$status" = "Bound" ]; then
            echo -e "${GREEN}[BOUND]${NC} $pvc_name - $capacity"
        else
            echo -e "${RED}[$status]${NC} $pvc_name"
            all_bound=false
        fi
    done < <(kubectl get pvc -n "$NAMESPACE" --no-headers 2>/dev/null)

    if [ "$all_bound" = true ]; then
        echo -e "${GREEN}All PVCs are bound${NC}"
    else
        echo -e "${RED}Some PVCs are not bound${NC}"
    fi
}

# Check database connectivity
check_databases() {
    print_header "Database Status"

    # PostgreSQL
    echo -n "PostgreSQL: "
    if kubectl get pod -n "$NAMESPACE" -l database=postgres --no-headers 2>/dev/null | grep -q "Running"; then
        echo -e "${GREEN}Running${NC}"
    else
        echo -e "${RED}Not Running${NC}"
    fi

    # TimescaleDB
    echo -n "TimescaleDB: "
    if kubectl get pod -n "$NAMESPACE" -l database=timescaledb --no-headers 2>/dev/null | grep -q "Running"; then
        echo -e "${GREEN}Running${NC}"
    else
        echo -e "${RED}Not Running${NC}"
    fi

    # Redis
    echo -n "Redis: "
    if kubectl get pod -n "$NAMESPACE" -l database=redis --no-headers 2>/dev/null | grep -q "Running"; then
        echo -e "${GREEN}Running${NC}"
    else
        echo -e "${RED}Not Running${NC}"
    fi

    # RabbitMQ
    echo -n "RabbitMQ: "
    if kubectl get pod -n "$NAMESPACE" -l component=messaging --no-headers 2>/dev/null | grep -q "Running"; then
        echo -e "${GREEN}Running${NC}"
    else
        echo -e "${RED}Not Running${NC}"
    fi
}

# Test health endpoints
test_health_endpoints() {
    print_header "Health Check Endpoints"

    local services=(
        "api-gateway-service:8000"
        "trading-engine-service:8005"
        "portfolio-manager-service:8003"
        "technical-analysis-service:8004"
        "bybit-connector-service:8001"
        "market-data-service:8002"
    )

    for service in "${services[@]}"; do
        svc_name=$(echo "$service" | cut -d: -f1)
        port=$(echo "$service" | cut -d: -f2)

        echo -n "Testing $svc_name: "

        # Create a temporary pod to test connectivity
        result=$(kubectl run -n "$NAMESPACE" -it --rm test-health-$RANDOM \
            --image=curlimages/curl:8.5.0 \
            --restart=Never \
            --timeout=30s \
            -- curl -s -o /dev/null -w "%{http_code}" \
            "http://${svc_name}:${port}/health" 2>/dev/null || echo "000")

        if [ "$result" = "200" ]; then
            echo -e "${GREEN}OK (200)${NC}"
        elif [ "$result" = "000" ]; then
            echo -e "${YELLOW}Unreachable${NC}"
        else
            echo -e "${RED}Error ($result)${NC}"
        fi
    done
}

# Check resource usage
check_resources() {
    print_header "Resource Usage"

    echo -e "${YELLOW}Pod Resource Usage:${NC}"
    if kubectl top pods -n "$NAMESPACE" &> /dev/null; then
        kubectl top pods -n "$NAMESPACE"
    else
        echo "Metrics server not available"
    fi
}

# Show recent events
show_events() {
    print_header "Recent Events"

    kubectl get events -n "$NAMESPACE" --sort-by='.lastTimestamp' | tail -20
}

# Watch mode
watch_pods() {
    print_header "Watching Pods (Ctrl+C to exit)"
    kubectl get pods -n "$NAMESPACE" -w
}

# Generate JSON report
generate_json_report() {
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    # Get pod data
    local pods_json=$(kubectl get pods -n "$NAMESPACE" -o json 2>/dev/null)
    local svc_json=$(kubectl get svc -n "$NAMESPACE" -o json 2>/dev/null)
    local hpa_json=$(kubectl get hpa -n "$NAMESPACE" -o json 2>/dev/null)
    local pvc_json=$(kubectl get pvc -n "$NAMESPACE" -o json 2>/dev/null)

    # Count status
    local total_pods=$(echo "$pods_json" | jq '.items | length')
    local running_pods=$(echo "$pods_json" | jq '[.items[] | select(.status.phase == "Running")] | length')

    cat << EOF
{
  "timestamp": "$timestamp",
  "namespace": "$NAMESPACE",
  "summary": {
    "total_pods": $total_pods,
    "running_pods": $running_pods,
    "status": "$( [ "$running_pods" -eq "$total_pods" ] && echo "healthy" || echo "degraded" )"
  },
  "pods": $pods_json,
  "services": $svc_json,
  "hpa": $hpa_json,
  "pvc": $pvc_json
}
EOF
}

# Main verification function
main() {
    # Check namespace first
    check_namespace

    if [ "$JSON_OUTPUT" = true ]; then
        generate_json_report
        exit 0
    fi

    if [ "$WATCH_MODE" = true ]; then
        watch_pods
        exit 0
    fi

    print_header "Staging Environment Verification"
    echo -e "Namespace: ${CYAN}$NAMESPACE${NC}"
    echo -e "Timestamp: $(date)"
    echo ""

    # Run all checks
    HEALTH_STATUS=0

    check_pods || HEALTH_STATUS=1
    check_hpa
    check_services
    check_storage
    check_databases

    if [ "$TEST_HEALTH" = true ]; then
        test_health_endpoints
    fi

    if [ "$DETAILED" = true ]; then
        check_resources
        show_events
    fi

    # Summary
    print_header "Verification Summary"

    if [ $HEALTH_STATUS -eq 0 ]; then
        echo -e "${GREEN}STAGING ENVIRONMENT IS HEALTHY${NC}"
        echo ""
        echo "All components are running and ready for testing."
    else
        echo -e "${YELLOW}STAGING ENVIRONMENT HAS ISSUES${NC}"
        echo ""
        echo "Some components are not healthy. Please check the details above."
        echo ""
        echo "Troubleshooting commands:"
        echo "  - View pod logs: kubectl logs -f <pod-name> -n $NAMESPACE"
        echo "  - Describe pod: kubectl describe pod <pod-name> -n $NAMESPACE"
        echo "  - View events: kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp'"
    fi

    echo ""
    exit $HEALTH_STATUS
}

# Run main function
main
