#!/bin/bash

################################################################################
# Post-Deployment Verification Script
#
# Purpose: Comprehensive deployment verification after deployment
# Usage: ./verify-deployment.sh [environment] [--verbose]
# Environment: dev|staging|prod (default: dev)
#
# Exit Codes:
#   0 - All verifications passed
#   1 - Critical verification failure
#   2 - Warning, some checks failed
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
VERBOSE=false
[[ "$2" == "--verbose" ]] && VERBOSE=true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_FILE="$PROJECT_ROOT/logs/verify-deployment-$(date +%Y%m%d-%H%M%S).log"
NAMESPACE="crypto-trading-bot-$ENVIRONMENT"

# Counters
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
WARNING_CHECKS=0

# Timeouts
HEALTH_CHECK_TIMEOUT=300  # 5 minutes
POD_READY_TIMEOUT=600     # 10 minutes

mkdir -p "$PROJECT_ROOT/logs"

################################################################################
# Utility Functions
################################################################################

log() {
    local level="$1"
    shift
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] [$level] $@" | tee -a "$LOG_FILE"
}

check_passed() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
    echo -e "${GREEN}✓${NC} $1" | tee -a "$LOG_FILE"
}

check_failed() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
    echo -e "${RED}✗${NC} $1" | tee -a "$LOG_FILE"
}

check_warning() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    WARNING_CHECKS=$((WARNING_CHECKS + 1))
    echo -e "${YELLOW}⚠${NC} $1" | tee -a "$LOG_FILE"
}

section_header() {
    echo -e "\n${BLUE}=== $1 ===${NC}" | tee -a "$LOG_FILE"
}

wait_for_condition() {
    local description="$1"
    local timeout="$2"
    local command="$3"

    log "INFO" "Waiting for: $description (timeout: ${timeout}s)"

    local elapsed=0
    while [ $elapsed -lt $timeout ]; do
        if eval "$command" &> /dev/null; then
            check_passed "$description (${elapsed}s)"
            return 0
        fi
        sleep 5
        elapsed=$((elapsed + 5))
    done

    check_failed "$description (timeout after ${timeout}s)"
    return 1
}

################################################################################
# Verification Functions
################################################################################

verify_pods() {
    section_header "Pod Status Verification"

    # Get all pods in namespace
    PODS=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null)

    if [ -z "$PODS" ]; then
        check_failed "No pods found in namespace $NAMESPACE"
        return 1
    fi

    TOTAL_PODS=$(echo "$PODS" | wc -l)
    log "INFO" "Found $TOTAL_PODS pods"

    # Check each pod status
    echo "$PODS" | while read line; do
        POD_NAME=$(echo $line | awk '{print $1}')
        STATUS=$(echo $line | awk '{print $3}')
        READY=$(echo $line | awk '{print $2}')

        if [ "$STATUS" == "Running" ]; then
            check_passed "Pod $POD_NAME is Running ($READY ready)"
        elif [ "$STATUS" == "Completed" ]; then
            check_passed "Pod $POD_NAME is Completed"
        else
            check_failed "Pod $POD_NAME status: $STATUS ($READY ready)"

            # Show pod events if verbose
            if [ "$VERBOSE" == "true" ]; then
                log "INFO" "Pod events for $POD_NAME:"
                kubectl describe pod "$POD_NAME" -n "$NAMESPACE" | grep -A 10 "Events:" | tee -a "$LOG_FILE"
            fi
        fi
    done

    # Wait for all pods to be ready
    wait_for_condition "All pods ready" $POD_READY_TIMEOUT \
        "kubectl wait --for=condition=ready pod --all -n $NAMESPACE --timeout=5s"
}

verify_services() {
    section_header "Service Status Verification"

    # Expected services
    EXPECTED_SERVICES=(
        "api-gateway"
        "trading-engine"
        "market-data-service"
        "technical-analysis"
        "portfolio-manager"
        "bybit-connector"
        "ml-service"
        "notification-service"
        "risk-metrics"
        "postgres"
        "redis"
        "rabbitmq"
    )

    for service in "${EXPECTED_SERVICES[@]}"; do
        if kubectl get service "$service" -n "$NAMESPACE" &> /dev/null; then
            ENDPOINTS=$(kubectl get endpoints "$service" -n "$NAMESPACE" -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null)
            if [ -n "$ENDPOINTS" ]; then
                check_passed "Service $service has endpoints"
            else
                check_warning "Service $service has no endpoints"
            fi
        else
            check_warning "Service $service not found"
        fi
    done
}

verify_database_connections() {
    section_header "Database Connection Verification"

    # Test PostgreSQL connection
    POSTGRES_POD=$(kubectl get pods -n "$NAMESPACE" -l app=postgres --no-headers -o custom-columns=":metadata.name" 2>/dev/null | head -1)

    if [ -n "$POSTGRES_POD" ]; then
        if kubectl exec -n "$NAMESPACE" "$POSTGRES_POD" -- psql -U postgres -c "SELECT 1" &> /dev/null; then
            check_passed "PostgreSQL connection successful"

            # Check databases
            DATABASES=$(kubectl exec -n "$NAMESPACE" "$POSTGRES_POD" -- psql -U postgres -t -c "SELECT datname FROM pg_database WHERE datistemplate = false;" 2>/dev/null)
            log "INFO" "Available databases: $(echo $DATABASES | tr '\n' ' ')"
        else
            check_failed "PostgreSQL connection failed"
        fi
    else
        check_warning "PostgreSQL pod not found"
    fi
}

verify_redis_connectivity() {
    section_header "Redis Connection Verification"

    REDIS_POD=$(kubectl get pods -n "$NAMESPACE" -l app=redis --no-headers -o custom-columns=":metadata.name" 2>/dev/null | head -1)

    if [ -n "$REDIS_POD" ]; then
        if kubectl exec -n "$NAMESPACE" "$REDIS_POD" -- redis-cli ping 2>/dev/null | grep -q "PONG"; then
            check_passed "Redis connection successful"

            # Check Redis info
            REDIS_INFO=$(kubectl exec -n "$NAMESPACE" "$REDIS_POD" -- redis-cli info server 2>/dev/null | grep "redis_version" || echo "Unknown")
            log "INFO" "Redis version: $REDIS_INFO"
        else
            check_failed "Redis connection failed"
        fi
    else
        check_warning "Redis pod not found"
    fi
}

verify_rabbitmq() {
    section_header "RabbitMQ Verification"

    RABBITMQ_POD=$(kubectl get pods -n "$NAMESPACE" -l app=rabbitmq --no-headers -o custom-columns=":metadata.name" 2>/dev/null | head -1)

    if [ -n "$RABBITMQ_POD" ]; then
        if kubectl exec -n "$NAMESPACE" "$RABBITMQ_POD" -- rabbitmqctl status &> /dev/null; then
            check_passed "RabbitMQ is operational"

            # Check queues
            QUEUES=$(kubectl exec -n "$NAMESPACE" "$RABBITMQ_POD" -- rabbitmqctl list_queues 2>/dev/null | wc -l)
            log "INFO" "RabbitMQ queues: $QUEUES"
        else
            check_failed "RabbitMQ is not operational"
        fi
    else
        check_warning "RabbitMQ pod not found"
    fi
}

verify_health_endpoints() {
    section_header "Health Endpoint Verification"

    # Services with health endpoints
    HEALTH_SERVICES=(
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

    for service_port in "${HEALTH_SERVICES[@]}"; do
        SERVICE=$(echo $service_port | cut -d: -f1)
        PORT=$(echo $service_port | cut -d: -f2)

        # Port-forward and check health
        POD=$(kubectl get pods -n "$NAMESPACE" -l app="$SERVICE" --no-headers -o custom-columns=":metadata.name" 2>/dev/null | head -1)

        if [ -n "$POD" ]; then
            # Use kubectl exec to check health from inside the pod
            HEALTH_CHECK=$(kubectl exec -n "$NAMESPACE" "$POD" -- curl -s -o /dev/null -w "%{http_code}" http://localhost:${PORT}/health 2>/dev/null || echo "000")

            if [ "$HEALTH_CHECK" == "200" ]; then
                check_passed "$SERVICE health endpoint responding (HTTP $HEALTH_CHECK)"
            elif [ "$HEALTH_CHECK" == "000" ]; then
                check_warning "$SERVICE health endpoint not accessible"
            else
                check_failed "$SERVICE health endpoint returned HTTP $HEALTH_CHECK"
            fi
        else
            check_warning "$SERVICE pod not found"
        fi
    done
}

verify_ingress() {
    section_header "Ingress Verification"

    INGRESS=$(kubectl get ingress -n "$NAMESPACE" --no-headers 2>/dev/null)

    if [ -n "$INGRESS" ]; then
        echo "$INGRESS" | while read line; do
            INGRESS_NAME=$(echo $line | awk '{print $1}')
            HOSTS=$(echo $line | awk '{print $3}')
            ADDRESS=$(echo $line | awk '{print $4}')

            if [ -n "$ADDRESS" ]; then
                check_passed "Ingress $INGRESS_NAME has address: $ADDRESS"
            else
                check_warning "Ingress $INGRESS_NAME has no address yet"
            fi
        done
    else
        check_warning "No ingress resources found"
    fi
}

verify_tls_certificates() {
    section_header "TLS Certificate Verification"

    # Check for TLS secrets
    TLS_SECRETS=$(kubectl get secrets -n "$NAMESPACE" --field-selector type=kubernetes.io/tls --no-headers 2>/dev/null)

    if [ -n "$TLS_SECRETS" ]; then
        echo "$TLS_SECRETS" | while read line; do
            SECRET_NAME=$(echo $line | awk '{print $1}')
            check_passed "TLS secret found: $SECRET_NAME"

            # Check certificate validity
            CERT_DATA=$(kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" -o jsonpath='{.data.tls\.crt}' 2>/dev/null | base64 -d)
            if [ -n "$CERT_DATA" ]; then
                EXPIRY=$(echo "$CERT_DATA" | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
                log "INFO" "Certificate expires: $EXPIRY"
            fi
        done
    else
        check_warning "No TLS certificates found"
    fi
}

verify_inter_service_communication() {
    section_header "Inter-Service Communication Verification"

    # Test communication from api-gateway to trading-engine
    API_POD=$(kubectl get pods -n "$NAMESPACE" -l app=api-gateway --no-headers -o custom-columns=":metadata.name" 2>/dev/null | head -1)

    if [ -n "$API_POD" ]; then
        # Test internal service communication
        COMM_TEST=$(kubectl exec -n "$NAMESPACE" "$API_POD" -- curl -s -o /dev/null -w "%{http_code}" http://trading-engine:8001/health 2>/dev/null || echo "000")

        if [ "$COMM_TEST" == "200" ]; then
            check_passed "Inter-service communication working (api-gateway -> trading-engine)"
        else
            check_failed "Inter-service communication failed (HTTP $COMM_TEST)"
        fi
    else
        check_warning "API Gateway pod not found for communication test"
    fi
}

verify_persistent_volumes() {
    section_header "Persistent Volume Verification"

    # Check PVCs
    PVCS=$(kubectl get pvc -n "$NAMESPACE" --no-headers 2>/dev/null)

    if [ -n "$PVCS" ]; then
        echo "$PVCS" | while read line; do
            PVC_NAME=$(echo $line | awk '{print $1}')
            STATUS=$(echo $line | awk '{print $2}')

            if [ "$STATUS" == "Bound" ]; then
                check_passed "PVC $PVC_NAME is Bound"
            else
                check_failed "PVC $PVC_NAME status: $STATUS"
            fi
        done
    else
        check_warning "No PVCs found"
    fi
}

verify_logs_for_errors() {
    section_header "Log Error Verification"

    # Check logs for errors in the last 5 minutes
    SERVICES=(
        "api-gateway"
        "trading-engine"
        "market-data-service"
    )

    for service in "${SERVICES[@]}"; do
        POD=$(kubectl get pods -n "$NAMESPACE" -l app="$service" --no-headers -o custom-columns=":metadata.name" 2>/dev/null | head -1)

        if [ -n "$POD" ]; then
            ERROR_COUNT=$(kubectl logs "$POD" -n "$NAMESPACE" --since=5m 2>/dev/null | grep -i "error\|exception\|fatal" | wc -l)

            if [ "$ERROR_COUNT" -eq 0 ]; then
                check_passed "$service has no errors in recent logs"
            elif [ "$ERROR_COUNT" -lt 5 ]; then
                check_warning "$service has $ERROR_COUNT errors in recent logs"
            else
                check_failed "$service has $ERROR_COUNT errors in recent logs"
            fi
        fi
    done
}

verify_metrics_collection() {
    section_header "Metrics Collection Verification"

    # Check if Prometheus is collecting metrics
    PROMETHEUS_POD=$(kubectl get pods -n "$NAMESPACE" -l app=prometheus --no-headers -o custom-columns=":metadata.name" 2>/dev/null | head -1)

    if [ -n "$PROMETHEUS_POD" ]; then
        # Check Prometheus targets
        TARGETS=$(kubectl exec -n "$NAMESPACE" "$PROMETHEUS_POD" -- wget -qO- http://localhost:9090/api/v1/targets 2>/dev/null | grep -o '"health":"up"' | wc -l)

        if [ "$TARGETS" -gt 0 ]; then
            check_passed "Prometheus collecting metrics from $TARGETS targets"
        else
            check_warning "Prometheus has no active targets"
        fi
    else
        check_warning "Prometheus pod not found"
    fi
}

verify_configmaps() {
    section_header "ConfigMap Verification"

    CONFIGMAPS=$(kubectl get configmap -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)

    if [ "$CONFIGMAPS" -gt 0 ]; then
        check_passed "Found $CONFIGMAPS ConfigMaps"
    else
        check_warning "No ConfigMaps found"
    fi
}

verify_resource_usage() {
    section_header "Resource Usage Verification"

    # Get top pods
    if kubectl top pods -n "$NAMESPACE" &> /dev/null; then
        log "INFO" "Top resource-consuming pods:"
        kubectl top pods -n "$NAMESPACE" --no-headers 2>/dev/null | head -5 | while read line; do
            log "INFO" "  $line"
        done
        check_passed "Resource metrics available"
    else
        check_warning "Resource metrics not available (metrics-server may not be installed)"
    fi
}

################################################################################
# Main Execution
################################################################################

main() {
    log "INFO" "Starting deployment verification for environment: $ENVIRONMENT"

    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║      Crypto Trading Bot - Deployment Verification           ║"
    echo "║                                                              ║"
    echo "║  Environment: $(printf "%-48s" "$ENVIRONMENT")║"
    echo "║  Namespace: $(printf "%-50s" "$NAMESPACE")║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    # Check if kubectl is available
    if ! command -v kubectl &> /dev/null; then
        log "ERROR" "kubectl not found"
        exit 1
    fi

    # Check if namespace exists
    if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
        log "ERROR" "Namespace $NAMESPACE does not exist"
        exit 1
    fi

    # Run all verifications
    verify_pods
    verify_services
    verify_database_connections
    verify_redis_connectivity
    verify_rabbitmq
    verify_health_endpoints
    verify_ingress
    verify_tls_certificates
    verify_inter_service_communication
    verify_persistent_volumes
    verify_logs_for_errors
    verify_metrics_collection
    verify_configmaps
    verify_resource_usage

    # Print summary
    echo -e "\n${BLUE}=== Verification Summary ===${NC}" | tee -a "$LOG_FILE"
    echo "Total checks: $TOTAL_CHECKS" | tee -a "$LOG_FILE"
    echo -e "${GREEN}Passed: $PASSED_CHECKS${NC}" | tee -a "$LOG_FILE"
    echo -e "${RED}Failed: $FAILED_CHECKS${NC}" | tee -a "$LOG_FILE"
    echo -e "${YELLOW}Warnings: $WARNING_CHECKS${NC}" | tee -a "$LOG_FILE"
    echo -e "\nLog file: $LOG_FILE" | tee -a "$LOG_FILE"

    # Determine exit code
    if [ "$FAILED_CHECKS" -gt 0 ]; then
        echo -e "\n${RED}❌ Deployment verification FAILED${NC}" | tee -a "$LOG_FILE"
        exit 1
    elif [ "$WARNING_CHECKS" -gt 0 ]; then
        echo -e "\n${YELLOW}⚠️  Deployment verification completed with warnings${NC}" | tee -a "$LOG_FILE"
        exit 2
    else
        echo -e "\n${GREEN}✅ Deployment verification PASSED${NC}" | tee -a "$LOG_FILE"
        exit 0
    fi
}

main "$@"
