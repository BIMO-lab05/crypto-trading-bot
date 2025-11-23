#!/bin/bash
# Verify Kubernetes deployment health
# Version: 1.0
# Created: 2025-11-23
#
# Usage:
#   ./verify-deployment.sh [--detailed]
#
# Options:
#   --detailed: Show detailed health information

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

DETAILED=false
if [ "$1" = "--detailed" ]; then
    DETAILED=true
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Crypto Trading Bot - Health Check${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if namespace exists
if ! kubectl get namespace crypto-bot &> /dev/null; then
    echo -e "${RED}Error: Namespace 'crypto-bot' does not exist${NC}"
    echo "Run ./apply-all.sh to deploy"
    exit 1
fi

# Function to check pod status
check_pods() {
    echo -e "${YELLOW}Checking Pod Status...${NC}"
    echo ""

    local all_ready=true
    local total_pods=0
    local ready_pods=0

    while IFS= read -r line; do
        if [ -z "$line" ]; then
            continue
        fi

        total_pods=$((total_pods + 1))

        # Extract pod name and status
        pod_name=$(echo "$line" | awk '{print $1}')
        status=$(echo "$line" | awk '{print $3}')
        ready=$(echo "$line" | awk '{print $2}')

        if [ "$status" = "Running" ] && [[ "$ready" =~ ^([0-9]+)/\1$ ]]; then
            echo -e "${GREEN}✓${NC} $pod_name - ${GREEN}$status${NC} ($ready)"
            ready_pods=$((ready_pods + 1))
        else
            echo -e "${RED}✗${NC} $pod_name - ${RED}$status${NC} ($ready)"
            all_ready=false

            if [ "$DETAILED" = true ]; then
                echo -e "  ${YELLOW}Events:${NC}"
                kubectl get events -n crypto-bot --field-selector involvedObject.name="$pod_name" | tail -3
                echo ""
            fi
        fi
    done < <(kubectl get pods -n crypto-bot --no-headers)

    echo ""
    echo -e "Pods Ready: ${ready_pods}/${total_pods}"

    if [ "$all_ready" = true ]; then
        echo -e "${GREEN}✓ All pods are running${NC}"
        return 0
    else
        echo -e "${RED}✗ Some pods are not ready${NC}"
        return 1
    fi
}

# Function to check services
check_services() {
    echo ""
    echo -e "${YELLOW}Checking Services...${NC}"
    echo ""

    kubectl get svc -n crypto-bot --no-headers | while read -r line; do
        svc_name=$(echo "$line" | awk '{print $1}')
        svc_type=$(echo "$line" | awk '{print $2}')
        echo -e "${GREEN}✓${NC} $svc_name (${svc_type})"
    done
}

# Function to check persistent volumes
check_storage() {
    echo ""
    echo -e "${YELLOW}Checking Persistent Volumes...${NC}"
    echo ""

    local all_bound=true

    while IFS= read -r line; do
        pvc_name=$(echo "$line" | awk '{print $1}')
        status=$(echo "$line" | awk '{print $2}')

        if [ "$status" = "Bound" ]; then
            echo -e "${GREEN}✓${NC} $pvc_name - ${GREEN}Bound${NC}"
        else
            echo -e "${RED}✗${NC} $pvc_name - ${RED}$status${NC}"
            all_bound=false
        fi
    done < <(kubectl get pvc -n crypto-bot --no-headers)

    if [ "$all_bound" = true ]; then
        echo -e "${GREEN}✓ All PVCs are bound${NC}"
    else
        echo -e "${RED}✗ Some PVCs are not bound${NC}"
    fi
}

# Function to check database connectivity
check_databases() {
    echo ""
    echo -e "${YELLOW}Checking Database Connectivity...${NC}"
    echo ""

    # Check PostgreSQL
    if kubectl get pod -n crypto-bot -l database=postgres --no-headers | grep -q "Running"; then
        echo -e "${GREEN}✓${NC} PostgreSQL - Running"
        if [ "$DETAILED" = true ]; then
            kubectl exec -n crypto-bot -it $(kubectl get pod -n crypto-bot -l database=postgres -o name | head -1) -- pg_isready || true
        fi
    else
        echo -e "${RED}✗${NC} PostgreSQL - Not Running"
    fi

    # Check TimescaleDB
    if kubectl get pod -n crypto-bot -l database=timescaledb --no-headers | grep -q "Running"; then
        echo -e "${GREEN}✓${NC} TimescaleDB - Running"
    else
        echo -e "${RED}✗${NC} TimescaleDB - Not Running"
    fi

    # Check Redis
    if kubectl get pod -n crypto-bot -l database=redis --no-headers | grep -q "Running"; then
        echo -e "${GREEN}✓${NC} Redis - Running"
    else
        echo -e "${RED}✗${NC} Redis - Not Running"
    fi

    # Check RabbitMQ
    if kubectl get pod -n crypto-bot -l component=messaging --no-headers | grep -q "Running"; then
        echo -e "${GREEN}✓${NC} RabbitMQ - Running"
    else
        echo -e "${RED}✗${NC} RabbitMQ - Not Running"
    fi
}

# Function to check endpoints
check_endpoints() {
    echo ""
    echo -e "${YELLOW}Checking Service Endpoints...${NC}"
    echo ""

    # Check if API gateway is accessible
    if kubectl get svc -n crypto-bot api-gateway-service &> /dev/null; then
        port=$(kubectl get svc -n crypto-bot api-gateway-service -o jsonpath='{.spec.ports[0].port}')
        echo -e "${GREEN}✓${NC} API Gateway service exists (port: $port)"

        if [ "$DETAILED" = true ]; then
            echo "  To access: kubectl port-forward -n crypto-bot svc/api-gateway-service 8000:$port"
        fi
    else
        echo -e "${RED}✗${NC} API Gateway service not found"
    fi
}

# Function to check resource usage
check_resources() {
    echo ""
    echo -e "${YELLOW}Checking Resource Usage...${NC}"
    echo ""

    if kubectl top nodes &> /dev/null; then
        echo -e "${BLUE}Node Resources:${NC}"
        kubectl top nodes
        echo ""
    fi

    if kubectl top pods -n crypto-bot &> /dev/null; then
        echo -e "${BLUE}Pod Resources:${NC}"
        kubectl top pods -n crypto-bot
    else
        echo -e "${YELLOW}Note: Metrics server not available${NC}"
    fi
}

# Function to check ingress
check_ingress() {
    echo ""
    echo -e "${YELLOW}Checking Ingress...${NC}"
    echo ""

    if kubectl get ingress -n crypto-bot --no-headers | grep -q "api-gateway-ingress"; then
        echo -e "${GREEN}✓${NC} API Gateway ingress configured"
        if [ "$DETAILED" = true ]; then
            kubectl get ingress -n crypto-bot api-gateway-ingress
        fi
    else
        echo -e "${YELLOW}Note: API Gateway ingress not configured${NC}"
    fi
}

# Run all checks
HEALTH_STATUS=0

check_pods || HEALTH_STATUS=1
check_services
check_storage
check_databases
check_endpoints
check_ingress

if [ "$DETAILED" = true ]; then
    check_resources
fi

# Summary
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Health Check Summary${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

if [ $HEALTH_STATUS -eq 0 ]; then
    echo -e "${GREEN}✓ System is healthy${NC}"
    echo ""
    echo "All components are running and ready"
else
    echo -e "${RED}✗ System has issues${NC}"
    echo ""
    echo "Some components are not healthy. Check the details above."
    echo ""
    echo "Troubleshooting commands:"
    echo "  - View pod logs: kubectl logs -f <pod-name> -n crypto-bot"
    echo "  - Describe pod: kubectl describe pod <pod-name> -n crypto-bot"
    echo "  - View events: kubectl get events -n crypto-bot --sort-by='.lastTimestamp'"
fi

echo ""
exit $HEALTH_STATUS
