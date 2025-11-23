#!/bin/bash
# Helm test runner for Crypto Trading Bot
# Usage: ./test.sh [namespace] [release-name]

set -e
set -u

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Default values
NAMESPACE=${1:-crypto-bot}
RELEASE_NAME=${2:-crypto-trading-bot}
TIMEOUT="5m"

print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if release exists
check_release() {
    print_info "Checking if release exists..."

    if ! helm list -n "$NAMESPACE" | grep -q "$RELEASE_NAME"; then
        print_error "Release $RELEASE_NAME not found in namespace $NAMESPACE"
        exit 1
    fi

    print_success "Release found: $RELEASE_NAME"
}

# Run Helm tests
run_helm_tests() {
    print_info "Running Helm tests..."

    if helm test "$RELEASE_NAME" -n "$NAMESPACE" --timeout "$TIMEOUT"; then
        print_success "Helm tests passed"
        return 0
    else
        print_error "Helm tests failed"
        return 1
    fi
}

# Run connectivity tests
run_connectivity_tests() {
    print_info "Running connectivity tests..."

    SERVICES=(
        "api-gateway:8000"
        "trading-engine:8001"
        "portfolio-manager:8002"
        "technical-analysis:8003"
        "bybit-connector:8004"
        "market-data-service:8005"
        "notification-service:8006"
        "ml-prediction-service:8007"
        "risk-metrics-service:8008"
        "sentiment-analysis-service:8009"
    )

    PASSED=0
    FAILED=0

    for service_port in "${SERVICES[@]}"; do
        SERVICE=$(echo "$service_port" | cut -d: -f1)
        PORT=$(echo "$service_port" | cut -d: -f2)

        print_info "Testing $SERVICE..."

        if kubectl get svc "$SERVICE" -n "$NAMESPACE" &> /dev/null; then
            # Create test pod
            kubectl run test-$SERVICE-$RANDOM \
                --image=curlimages/curl:latest \
                --rm -i --restart=Never \
                --timeout=30s \
                -n "$NAMESPACE" \
                -- curl -s -f -m 10 "http://$SERVICE:$PORT/health" &> /dev/null

            if [ $? -eq 0 ]; then
                print_success "$SERVICE is reachable"
                ((PASSED++))
            else
                print_error "$SERVICE is not reachable"
                ((FAILED++))
            fi
        else
            print_warning "$SERVICE not found, skipping"
        fi
    done

    echo ""
    print_info "Connectivity Test Results: $PASSED passed, $FAILED failed"
}

# Run health checks
run_health_checks() {
    print_info "Running health checks..."

    # Check pod health
    print_info "Checking pod health..."
    UNHEALTHY_PODS=$(kubectl get pods -n "$NAMESPACE" --field-selector=status.phase!=Running,status.phase!=Succeeded -o name | wc -l)

    if [ "$UNHEALTHY_PODS" -eq 0 ]; then
        print_success "All pods are healthy"
    else
        print_error "$UNHEALTHY_PODS unhealthy pods found"
        kubectl get pods -n "$NAMESPACE" --field-selector=status.phase!=Running,status.phase!=Succeeded
    fi

    # Check for restarting pods
    print_info "Checking for restarting pods..."
    kubectl get pods -n "$NAMESPACE" -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{range .status.containerStatuses[*]}{.restartCount}{"\n"}{end}{end}' | \
        awk '$2 > 5 {print "  " $1 " has " $2 " restarts"}'
}

# Run database connectivity tests
run_database_tests() {
    print_info "Running database connectivity tests..."

    # Test PostgreSQL
    if kubectl get svc postgresql -n "$NAMESPACE" &> /dev/null; then
        print_info "Testing PostgreSQL connection..."
        kubectl run test-postgres-$RANDOM \
            --image=postgres:16-alpine \
            --rm -i --restart=Never \
            --timeout=30s \
            -n "$NAMESPACE" \
            --env="PGPASSWORD=test" \
            -- pg_isready -h postgresql -p 5432 &> /dev/null

        if [ $? -eq 0 ]; then
            print_success "PostgreSQL is reachable"
        else
            print_error "PostgreSQL is not reachable"
        fi
    fi

    # Test TimescaleDB
    if kubectl get svc timescaledb -n "$NAMESPACE" &> /dev/null; then
        print_info "Testing TimescaleDB connection..."
        kubectl run test-timescale-$RANDOM \
            --image=postgres:16-alpine \
            --rm -i --restart=Never \
            --timeout=30s \
            -n "$NAMESPACE" \
            --env="PGPASSWORD=test" \
            -- pg_isready -h timescaledb -p 5432 &> /dev/null

        if [ $? -eq 0 ]; then
            print_success "TimescaleDB is reachable"
        else
            print_error "TimescaleDB is not reachable"
        fi
    fi

    # Test Redis
    if kubectl get svc redis -n "$NAMESPACE" &> /dev/null; then
        print_info "Testing Redis connection..."
        kubectl run test-redis-$RANDOM \
            --image=redis:7-alpine \
            --rm -i --restart=Never \
            --timeout=30s \
            -n "$NAMESPACE" \
            -- redis-cli -h redis ping &> /dev/null

        if [ $? -eq 0 ]; then
            print_success "Redis is reachable"
        else
            print_error "Redis is not reachable"
        fi
    fi

    # Test RabbitMQ
    if kubectl get svc rabbitmq -n "$NAMESPACE" &> /dev/null; then
        print_info "Testing RabbitMQ connection..."
        kubectl run test-rabbitmq-$RANDOM \
            --image=curlimages/curl:latest \
            --rm -i --restart=Never \
            --timeout=30s \
            -n "$NAMESPACE" \
            -- curl -s -f -m 10 "http://rabbitmq:15672" &> /dev/null

        if [ $? -eq 0 ]; then
            print_success "RabbitMQ is reachable"
        else
            print_error "RabbitMQ is not reachable"
        fi
    fi
}

# Performance tests
run_performance_tests() {
    print_info "Running basic performance tests..."

    # Check resource usage
    print_info "Current resource usage:"
    kubectl top pods -n "$NAMESPACE" 2>/dev/null || print_warning "Metrics server not available"

    print_info "Current node usage:"
    kubectl top nodes 2>/dev/null || print_warning "Metrics server not available"
}

# Display test summary
display_summary() {
    echo ""
    echo "======================================================================="
    echo "  Test Summary"
    echo "======================================================================="
    echo ""

    # Get test pod logs
    print_info "Recent test pod logs:"
    kubectl get pods -n "$NAMESPACE" -l "test=connection" --sort-by=.metadata.creationTimestamp | tail -5

    echo ""
    echo "======================================================================="
    echo "  Useful Debugging Commands"
    echo "======================================================================="
    echo ""
    echo "  View test logs:"
    echo "    kubectl logs -n $NAMESPACE -l test=connection"
    echo ""
    echo "  View pod events:"
    echo "    kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp'"
    echo ""
    echo "  Describe failed pods:"
    echo "    kubectl describe pods -n $NAMESPACE --field-selector=status.phase!=Running"
    echo ""
    echo "======================================================================="
}

# Main function
main() {
    print_info "Starting test suite"
    echo ""

    check_release

    # Run all tests
    run_helm_tests || true
    echo ""

    run_connectivity_tests
    echo ""

    run_health_checks
    echo ""

    run_database_tests
    echo ""

    run_performance_tests
    echo ""

    display_summary

    print_success "Test suite completed!"
}

main
