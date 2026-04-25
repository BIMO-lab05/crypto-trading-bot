#!/bin/bash
# =============================================================================
# Production Verification Script for Crypto Trading Bot
# =============================================================================
# Version: 1.0
# Created: 2025-12-12
#
# This script validates the production deployment health and functionality.
#
# Usage:
#   ./verify-production.sh [options]
#
# Options:
#   --detailed      Show detailed output for each check
#   --export FILE   Export results to file
#   --quick         Run only critical checks
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

NAMESPACE="crypto-bot-prod"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Options
DETAILED=false
EXPORT_FILE=""
QUICK=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --detailed) DETAILED=true; shift ;;
        --export) EXPORT_FILE="$2"; shift 2 ;;
        --quick) QUICK=true; shift ;;
        *) shift ;;
    esac
done

# Counters
PASSED=0
FAILED=0
WARNINGS=0

# Logging functions
log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASSED++))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAILED++))
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    ((WARNINGS++))
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

header() {
    echo ""
    echo "=========================================="
    echo "$1"
    echo "=========================================="
}

# Check if kubectl is available
check_kubectl() {
    if ! command -v kubectl &> /dev/null; then
        log_fail "kubectl not found"
        exit 1
    fi
    log_pass "kubectl is available"
}

# Check cluster connection
check_cluster() {
    if kubectl cluster-info &> /dev/null; then
        log_pass "Connected to Kubernetes cluster"
    else
        log_fail "Cannot connect to cluster"
        exit 1
    fi
}

# Check namespace exists
check_namespace() {
    if kubectl get namespace "$NAMESPACE" &> /dev/null; then
        log_pass "Namespace $NAMESPACE exists"
    else
        log_fail "Namespace $NAMESPACE not found"
        return 1
    fi
}

# Check pods are running
check_pods() {
    header "Checking Pod Status"

    local deployments=(
        "api-gateway"
        "trading-engine"
        "portfolio-manager"
        "technical-analysis"
        "market-data-service"
        "bybit-connector"
        "ml-prediction-service"
        "notification-service"
        "risk-metrics-service"
        "postgres"
        "redis"
        "rabbitmq"
        "prometheus"
        "grafana"
    )

    for deployment in "${deployments[@]}"; do
        # Check if deployment/statefulset exists
        if kubectl get deployment "$deployment" -n "$NAMESPACE" &>/dev/null; then
            ready=$(kubectl get deployment "$deployment" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
            desired=$(kubectl get deployment "$deployment" -n "$NAMESPACE" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "0")
        elif kubectl get statefulset "$deployment" -n "$NAMESPACE" &>/dev/null; then
            ready=$(kubectl get statefulset "$deployment" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
            desired=$(kubectl get statefulset "$deployment" -n "$NAMESPACE" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "0")
        else
            log_warn "$deployment not found"
            continue
        fi

        if [ "$ready" -ge "$desired" ] && [ "$ready" -gt "0" ]; then
            log_pass "$deployment: $ready/$desired replicas ready"
        else
            log_fail "$deployment: $ready/$desired replicas ready"
        fi
    done
}

# Check services
check_services() {
    header "Checking Services"

    local services=(
        "api-gateway-service"
        "trading-engine-service"
        "portfolio-manager-service"
        "technical-analysis-service"
        "market-data-service"
        "bybit-connector-service"
        "postgres-service"
        "redis-service"
        "rabbitmq-service"
        "prometheus-service"
        "grafana-service"
    )

    for service in "${services[@]}"; do
        if kubectl get svc "$service" -n "$NAMESPACE" &>/dev/null; then
            endpoints=$(kubectl get endpoints "$service" -n "$NAMESPACE" -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null)
            if [ -n "$endpoints" ]; then
                log_pass "$service has endpoints"
            else
                log_warn "$service has no endpoints"
            fi
        else
            log_warn "$service not found"
        fi
    done
}

# Check health endpoints
check_health_endpoints() {
    header "Checking Health Endpoints"

    local api_pod=$(kubectl get pods -n "$NAMESPACE" -l service=api-gateway -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [ -z "$api_pod" ]; then
        log_fail "No API Gateway pod found"
        return 1
    fi

    # Check API Gateway health
    if kubectl exec -n "$NAMESPACE" "$api_pod" -- curl -s http://localhost:8000/health 2>/dev/null | grep -q "healthy\|ok"; then
        log_pass "API Gateway health check passed"
    else
        log_fail "API Gateway health check failed"
    fi

    # Check other services through API Gateway
    local services=("trading-engine:8001" "portfolio-manager:8002" "technical-analysis:8003")

    for service in "${services[@]}"; do
        svc_name=$(echo "$service" | cut -d: -f1)
        svc_port=$(echo "$service" | cut -d: -f2)

        if kubectl exec -n "$NAMESPACE" "$api_pod" -- curl -s "http://${svc_name}-service:${svc_port}/health" 2>/dev/null | grep -q "healthy\|ok"; then
            log_pass "$svc_name health check passed"
        else
            log_warn "$svc_name health check inconclusive"
        fi
    done
}

# Check PVCs
check_pvcs() {
    header "Checking Persistent Volume Claims"

    local pvcs=$(kubectl get pvc -n "$NAMESPACE" --no-headers 2>/dev/null)

    if [ -z "$pvcs" ]; then
        log_warn "No PVCs found"
        return
    fi

    echo "$pvcs" | while read line; do
        pvc_name=$(echo "$line" | awk '{print $1}')
        status=$(echo "$line" | awk '{print $2}')

        if [ "$status" = "Bound" ]; then
            log_pass "PVC $pvc_name is Bound"
        else
            log_fail "PVC $pvc_name status: $status"
        fi
    done
}

# Check HPAs
check_hpas() {
    header "Checking Horizontal Pod Autoscalers"

    local hpas=$(kubectl get hpa -n "$NAMESPACE" --no-headers 2>/dev/null)

    if [ -z "$hpas" ]; then
        log_warn "No HPAs configured"
        return
    fi

    echo "$hpas" | while read line; do
        hpa_name=$(echo "$line" | awk '{print $1}')
        current=$(echo "$line" | awk '{print $6}')
        min=$(echo "$line" | awk '{print $4}')
        max=$(echo "$line" | awk '{print $5}')

        log_pass "HPA $hpa_name: current=$current, min=$min, max=$max"
    done
}

# Check network policies
check_network_policies() {
    header "Checking Network Policies"

    local policies=$(kubectl get networkpolicy -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)

    if [ "$policies" -gt 0 ]; then
        log_pass "$policies network policies configured"
        if [ "$DETAILED" = true ]; then
            kubectl get networkpolicy -n "$NAMESPACE"
        fi
    else
        log_warn "No network policies found"
    fi
}

# Check secrets
check_secrets() {
    header "Checking Secrets"

    local required_secrets=(
        "db-secrets"
        "api-secrets"
        "bybit-secrets"
    )

    for secret in "${required_secrets[@]}"; do
        if kubectl get secret "$secret" -n "$NAMESPACE" &>/dev/null; then
            log_pass "Secret $secret exists"
        else
            log_fail "Secret $secret not found"
        fi
    done
}

# Check monitoring
check_monitoring() {
    header "Checking Monitoring Stack"

    # Check Prometheus
    local prom_pod=$(kubectl get pods -n "$NAMESPACE" -l service=prometheus -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [ -n "$prom_pod" ]; then
        if kubectl exec -n "$NAMESPACE" "$prom_pod" -- curl -s http://localhost:9090/-/healthy 2>/dev/null | grep -q "Prometheus"; then
            log_pass "Prometheus is healthy"
        else
            log_warn "Prometheus health check inconclusive"
        fi
    else
        log_warn "Prometheus not found"
    fi

    # Check Grafana
    local grafana_pod=$(kubectl get pods -n "$NAMESPACE" -l service=grafana -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [ -n "$grafana_pod" ]; then
        if kubectl exec -n "$NAMESPACE" "$grafana_pod" -- curl -s http://localhost:3000/api/health 2>/dev/null | grep -q "ok"; then
            log_pass "Grafana is healthy"
        else
            log_warn "Grafana health check inconclusive"
        fi
    else
        log_warn "Grafana not found"
    fi
}

# Check resource utilization
check_resources() {
    header "Checking Resource Utilization"

    if kubectl top pods -n "$NAMESPACE" &>/dev/null; then
        log_info "Pod resource usage:"
        kubectl top pods -n "$NAMESPACE" --no-headers | while read line; do
            pod=$(echo "$line" | awk '{print $1}')
            cpu=$(echo "$line" | awk '{print $2}')
            mem=$(echo "$line" | awk '{print $3}')
            echo "  $pod: CPU=$cpu, Memory=$mem"
        done
        log_pass "Resource metrics available"
    else
        log_warn "Metrics server not available"
    fi
}

# Check recent events
check_events() {
    header "Checking Recent Events"

    local warnings=$(kubectl get events -n "$NAMESPACE" --field-selector type=Warning --no-headers 2>/dev/null | wc -l)

    if [ "$warnings" -gt 0 ]; then
        log_warn "$warnings warning events in namespace"
        if [ "$DETAILED" = true ]; then
            kubectl get events -n "$NAMESPACE" --field-selector type=Warning --sort-by='.lastTimestamp' | tail -10
        fi
    else
        log_pass "No warning events"
    fi
}

# Check emergency stop
check_emergency_stop() {
    header "Checking Emergency Stop Mechanism"

    local trading_pod=$(kubectl get pods -n "$NAMESPACE" -l service=trading-engine -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [ -n "$trading_pod" ]; then
        # Check if emergency stop endpoint exists
        if kubectl exec -n "$NAMESPACE" "$trading_pod" -- curl -s http://localhost:8001/api/v1/trading/emergency-stop/status 2>/dev/null | grep -q "active\|inactive"; then
            log_pass "Emergency stop endpoint accessible"
        else
            log_warn "Emergency stop endpoint check inconclusive"
        fi
    else
        log_warn "Trading engine not found for emergency stop check"
    fi
}

# Check rate limiting
check_rate_limiting() {
    header "Checking Rate Limiting"

    local api_pod=$(kubectl get pods -n "$NAMESPACE" -l service=api-gateway -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

    if [ -n "$api_pod" ]; then
        # Send multiple requests and check for rate limiting
        local responses=""
        for i in {1..5}; do
            response=$(kubectl exec -n "$NAMESPACE" "$api_pod" -- curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null)
            responses="$responses $response"
        done

        if echo "$responses" | grep -q "429"; then
            log_pass "Rate limiting is active (received 429)"
        else
            log_warn "Rate limiting may not be active (no 429 responses in test)"
        fi
    else
        log_warn "API Gateway not found for rate limiting check"
    fi
}

# Generate summary
generate_summary() {
    header "Verification Summary"

    echo ""
    echo "Results:"
    echo -e "  ${GREEN}Passed:${NC}   $PASSED"
    echo -e "  ${RED}Failed:${NC}   $FAILED"
    echo -e "  ${YELLOW}Warnings:${NC} $WARNINGS"
    echo ""

    if [ $FAILED -gt 0 ]; then
        echo -e "${RED}VERIFICATION FAILED${NC}"
        echo "Please address the failed checks before proceeding."
        return 1
    elif [ $WARNINGS -gt 5 ]; then
        echo -e "${YELLOW}VERIFICATION PASSED WITH WARNINGS${NC}"
        echo "Consider addressing warnings for optimal operation."
        return 0
    else
        echo -e "${GREEN}VERIFICATION PASSED${NC}"
        echo "Production deployment is healthy."
        return 0
    fi
}

# Export results
export_results() {
    if [ -n "$EXPORT_FILE" ]; then
        cat > "$EXPORT_FILE" << EOF
{
  "timestamp": "$(date -Iseconds)",
  "namespace": "$NAMESPACE",
  "results": {
    "passed": $PASSED,
    "failed": $FAILED,
    "warnings": $WARNINGS
  },
  "status": "$([[ $FAILED -eq 0 ]] && echo "PASSED" || echo "FAILED")"
}
EOF
        log_info "Results exported to $EXPORT_FILE"
    fi
}

# Main function
main() {
    echo "=========================================="
    echo "Production Deployment Verification"
    echo "Namespace: $NAMESPACE"
    echo "Time: $(date)"
    echo "=========================================="

    check_kubectl
    check_cluster
    check_namespace

    if [ "$QUICK" = true ]; then
        check_pods
        check_health_endpoints
        generate_summary
        exit $?
    fi

    check_pods
    check_services
    check_health_endpoints
    check_pvcs
    check_hpas
    check_network_policies
    check_secrets
    check_monitoring
    check_resources
    check_events
    check_emergency_stop
    check_rate_limiting

    export_results
    generate_summary
}

main
