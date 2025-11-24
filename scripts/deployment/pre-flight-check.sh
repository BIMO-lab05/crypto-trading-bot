#!/bin/bash

################################################################################
# Pre-Flight Deployment Check Script
#
# Purpose: Validates environment before deployment to prevent failures
# Usage: ./pre-flight-check.sh [environment]
# Environment: dev|staging|prod (default: dev)
#
# Exit Codes:
#   0 - All checks passed
#   1 - Critical failure, deployment must not proceed
#   2 - Warning, proceed with caution
################################################################################

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
ENVIRONMENT="${1:-dev}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_FILE="$PROJECT_ROOT/logs/pre-flight-check-$(date +%Y%m%d-%H%M%S).log"

# Counters
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
WARNING_CHECKS=0

# Ensure log directory exists
mkdir -p "$PROJECT_ROOT/logs"

################################################################################
# Utility Functions
################################################################################

log() {
    local level="$1"
    shift
    local message="$@"
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] [$level] $message" | tee -a "$LOG_FILE"
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

################################################################################
# Check Functions
################################################################################

check_docker() {
    section_header "Docker Checks"

    # Check if Docker is installed
    if command -v docker &> /dev/null; then
        check_passed "Docker is installed ($(docker --version))"
    else
        check_failed "Docker is not installed"
        return 1
    fi

    # Check if Docker daemon is running
    if docker info &> /dev/null; then
        check_passed "Docker daemon is running"
    else
        check_failed "Docker daemon is not running"
        return 1
    fi

    # Check Docker version
    DOCKER_VERSION=$(docker version --format '{{.Server.Version}}' 2>/dev/null)
    REQUIRED_DOCKER_VERSION="20.10.0"
    if [ -n "$DOCKER_VERSION" ]; then
        check_passed "Docker version: $DOCKER_VERSION"
    else
        check_warning "Could not determine Docker version"
    fi

    # Check Docker disk space
    DOCKER_DISK_USAGE=$(docker system df --format "table {{.Type}}\t{{.Size}}" 2>/dev/null | grep -i "total" || echo "Unknown")
    if [ "$DOCKER_DISK_USAGE" != "Unknown" ]; then
        check_passed "Docker disk usage: $DOCKER_DISK_USAGE"
    else
        check_warning "Could not determine Docker disk usage"
    fi

    # Check Docker Compose
    if command -v docker-compose &> /dev/null || docker compose version &> /dev/null; then
        COMPOSE_VERSION=$(docker-compose --version 2>/dev/null || docker compose version 2>/dev/null)
        check_passed "Docker Compose is available: $COMPOSE_VERSION"
    else
        check_failed "Docker Compose is not available"
        return 1
    fi
}

check_kubernetes() {
    section_header "Kubernetes Checks"

    # Check if kubectl is installed
    if command -v kubectl &> /dev/null; then
        check_passed "kubectl is installed ($(kubectl version --client --short 2>/dev/null || kubectl version --client))"
    else
        check_failed "kubectl is not installed"
        return 1
    fi

    # Check cluster access
    if kubectl cluster-info &> /dev/null; then
        check_passed "Kubernetes cluster is accessible"

        # Get cluster info
        CLUSTER_VERSION=$(kubectl version --short 2>/dev/null | grep "Server Version" || kubectl version -o json 2>/dev/null | grep -o '"serverVersion":{"major":"[^"]*","minor":"[^"]*"' || echo "Unknown")
        check_passed "Cluster version: $CLUSTER_VERSION"

        # Check current context
        CURRENT_CONTEXT=$(kubectl config current-context 2>/dev/null)
        if [ "$ENVIRONMENT" == "prod" ] && [[ "$CURRENT_CONTEXT" != *"prod"* ]]; then
            check_warning "Current context '$CURRENT_CONTEXT' may not be production"
        else
            check_passed "Current context: $CURRENT_CONTEXT"
        fi

        # Check node status
        NODE_COUNT=$(kubectl get nodes --no-headers 2>/dev/null | wc -l)
        READY_NODES=$(kubectl get nodes --no-headers 2>/dev/null | grep -c " Ready" || echo 0)
        if [ "$NODE_COUNT" -eq "$READY_NODES" ]; then
            check_passed "All $NODE_COUNT nodes are Ready"
        else
            check_warning "$READY_NODES/$NODE_COUNT nodes are Ready"
        fi
    else
        check_failed "Cannot access Kubernetes cluster"
        return 1
    fi

    # Check namespace
    NAMESPACE="crypto-trading-bot-$ENVIRONMENT"
    if kubectl get namespace "$NAMESPACE" &> /dev/null; then
        check_passed "Namespace '$NAMESPACE' exists"
    else
        check_warning "Namespace '$NAMESPACE' does not exist (will be created during deployment)"
    fi
}

check_helm() {
    section_header "Helm Checks"

    # Check if Helm is installed
    if command -v helm &> /dev/null; then
        HELM_VERSION=$(helm version --short 2>/dev/null || helm version)
        check_passed "Helm is installed: $HELM_VERSION"
    else
        check_failed "Helm is not installed"
        return 1
    fi

    # Check Helm repositories
    REPO_COUNT=$(helm repo list 2>/dev/null | tail -n +2 | wc -l)
    if [ "$REPO_COUNT" -gt 0 ]; then
        check_passed "Helm repositories configured: $REPO_COUNT"
    else
        check_warning "No Helm repositories configured"
    fi
}

check_secrets() {
    section_header "Secrets Validation"

    # Check for required environment variables
    REQUIRED_VARS=(
        "BYBIT_API_KEY"
        "BYBIT_API_SECRET"
        "POSTGRES_PASSWORD"
        "REDIS_PASSWORD"
        "RABBITMQ_PASSWORD"
        "JWT_SECRET"
    )

    ENV_FILE="$PROJECT_ROOT/.env.$ENVIRONMENT"
    if [ -f "$ENV_FILE" ]; then
        check_passed "Environment file exists: $ENV_FILE"

        for var in "${REQUIRED_VARS[@]}"; do
            if grep -q "^$var=" "$ENV_FILE" 2>/dev/null; then
                VALUE=$(grep "^$var=" "$ENV_FILE" | cut -d'=' -f2)
                if [ -n "$VALUE" ] && [ "$VALUE" != "your_key_here" ] && [ "$VALUE" != "change_me" ]; then
                    check_passed "Secret '$var' is configured"
                else
                    check_failed "Secret '$var' has placeholder value"
                fi
            else
                check_failed "Secret '$var' is missing"
            fi
        done
    else
        check_warning "Environment file not found: $ENV_FILE"
    fi

    # Check Kubernetes secrets
    if command -v kubectl &> /dev/null && kubectl cluster-info &> /dev/null; then
        NAMESPACE="crypto-trading-bot-$ENVIRONMENT"
        if kubectl get namespace "$NAMESPACE" &> /dev/null; then
            SECRET_NAME="crypto-trading-bot-secrets"
            if kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" &> /dev/null; then
                check_passed "Kubernetes secret '$SECRET_NAME' exists in namespace '$NAMESPACE'"
            else
                check_warning "Kubernetes secret '$SECRET_NAME' not found in namespace '$NAMESPACE'"
            fi
        fi
    fi
}

check_dns() {
    section_header "DNS Configuration"

    # Check DNS resolution
    TEST_DOMAINS=("google.com" "api.bybit.com")

    for domain in "${TEST_DOMAINS[@]}"; do
        if nslookup "$domain" &> /dev/null || host "$domain" &> /dev/null; then
            check_passed "DNS resolution working for $domain"
        else
            check_warning "DNS resolution failed for $domain"
        fi
    done
}

check_storage() {
    section_header "Storage Checks"

    # Check disk space
    DISK_USAGE=$(df -h "$PROJECT_ROOT" | awk 'NR==2 {print $5}' | sed 's/%//')
    if [ "$DISK_USAGE" -lt 80 ]; then
        check_passed "Disk usage: ${DISK_USAGE}%"
    elif [ "$DISK_USAGE" -lt 90 ]; then
        check_warning "Disk usage high: ${DISK_USAGE}%"
    else
        check_failed "Disk usage critical: ${DISK_USAGE}%"
    fi

    # Check storage classes in Kubernetes
    if command -v kubectl &> /dev/null && kubectl cluster-info &> /dev/null; then
        STORAGE_CLASSES=$(kubectl get storageclass --no-headers 2>/dev/null | wc -l)
        if [ "$STORAGE_CLASSES" -gt 0 ]; then
            check_passed "Storage classes available: $STORAGE_CLASSES"
            kubectl get storageclass --no-headers 2>/dev/null | while read line; do
                log "INFO" "  - $(echo $line | awk '{print $1}')"
            done
        else
            check_warning "No storage classes found"
        fi
    fi
}

check_network() {
    section_header "Network Connectivity"

    # Check internet connectivity
    if ping -c 1 8.8.8.8 &> /dev/null; then
        check_passed "Internet connectivity available"
    else
        check_warning "Internet connectivity issues detected"
    fi

    # Check Bybit API connectivity
    if curl -s --max-time 5 https://api.bybit.com/v2/public/time &> /dev/null; then
        check_passed "Bybit API is accessible"
    else
        check_warning "Cannot reach Bybit API"
    fi

    # Check required ports
    REQUIRED_PORTS=(5432 6379 5672 15672 8080)
    for port in "${REQUIRED_PORTS[@]}"; do
        if ! netstat -tuln 2>/dev/null | grep -q ":$port " && ! ss -tuln 2>/dev/null | grep -q ":$port "; then
            check_passed "Port $port is available"
        else
            check_warning "Port $port is already in use"
        fi
    done
}

check_certificates() {
    section_header "TLS Certificates"

    CERT_DIR="$PROJECT_ROOT/infrastructure/certs"

    if [ -d "$CERT_DIR" ]; then
        check_passed "Certificate directory exists"

        # Check for certificate files
        if [ -f "$CERT_DIR/tls.crt" ]; then
            # Check certificate expiry
            EXPIRY_DATE=$(openssl x509 -enddate -noout -in "$CERT_DIR/tls.crt" 2>/dev/null | cut -d= -f2)
            if [ -n "$EXPIRY_DATE" ]; then
                EXPIRY_EPOCH=$(date -d "$EXPIRY_DATE" +%s 2>/dev/null)
                CURRENT_EPOCH=$(date +%s)
                DAYS_UNTIL_EXPIRY=$(( ($EXPIRY_EPOCH - $CURRENT_EPOCH) / 86400 ))

                if [ "$DAYS_UNTIL_EXPIRY" -gt 30 ]; then
                    check_passed "TLS certificate valid (expires in $DAYS_UNTIL_EXPIRY days)"
                elif [ "$DAYS_UNTIL_EXPIRY" -gt 0 ]; then
                    check_warning "TLS certificate expires soon (in $DAYS_UNTIL_EXPIRY days)"
                else
                    check_failed "TLS certificate has expired"
                fi
            fi
        else
            check_warning "TLS certificate not found (may use self-signed or external cert)"
        fi
    else
        check_warning "Certificate directory not found"
    fi
}

check_resource_quotas() {
    section_header "Resource Quotas"

    if command -v kubectl &> /dev/null && kubectl cluster-info &> /dev/null; then
        NAMESPACE="crypto-trading-bot-$ENVIRONMENT"

        if kubectl get namespace "$NAMESPACE" &> /dev/null; then
            # Check resource quotas
            QUOTAS=$(kubectl get resourcequota -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)
            if [ "$QUOTAS" -gt 0 ]; then
                check_passed "Resource quotas configured: $QUOTAS"
            else
                check_warning "No resource quotas configured"
            fi

            # Check limit ranges
            LIMITS=$(kubectl get limitrange -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)
            if [ "$LIMITS" -gt 0 ]; then
                check_passed "Limit ranges configured: $LIMITS"
            else
                check_warning "No limit ranges configured"
            fi
        fi
    fi
}

check_docker_images() {
    section_header "Docker Images"

    # Check if required images exist locally or can be pulled
    REQUIRED_IMAGES=(
        "postgres:15-alpine"
        "redis:7-alpine"
        "rabbitmq:3-management-alpine"
        "timescale/timescaledb:latest-pg15"
    )

    for image in "${REQUIRED_IMAGES[@]}"; do
        if docker image inspect "$image" &> /dev/null; then
            check_passed "Image available: $image"
        else
            check_warning "Image not found locally: $image (will be pulled during deployment)"
        fi
    done
}

check_configuration_files() {
    section_header "Configuration Files"

    # Check for required configuration files
    CONFIG_FILES=(
        "$PROJECT_ROOT/docker-compose.yml"
        "$PROJECT_ROOT/docker-compose.prod.yml"
        "$PROJECT_ROOT/infrastructure/kubernetes/namespace.yaml"
        "$PROJECT_ROOT/infrastructure/helm/crypto-trading-bot/Chart.yaml"
    )

    for file in "${CONFIG_FILES[@]}"; do
        if [ -f "$file" ]; then
            check_passed "Configuration file exists: $(basename $file)"
        else
            check_warning "Configuration file missing: $(basename $file)"
        fi
    done
}

check_dependencies() {
    section_header "System Dependencies"

    # Check for required system commands
    REQUIRED_COMMANDS=(
        "curl"
        "jq"
        "git"
        "python3"
        "pip3"
    )

    for cmd in "${REQUIRED_COMMANDS[@]}"; do
        if command -v "$cmd" &> /dev/null; then
            check_passed "Command available: $cmd"
        else
            check_warning "Command not found: $cmd"
        fi
    done
}

check_python_environment() {
    section_header "Python Environment"

    # Check Python version
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version)
        check_passed "Python installed: $PYTHON_VERSION"

        # Check if virtual environment exists
        if [ -d "$PROJECT_ROOT/venv" ]; then
            check_passed "Virtual environment exists"
        else
            check_warning "Virtual environment not found"
        fi
    else
        check_failed "Python3 not found"
    fi
}

################################################################################
# Main Execution
################################################################################

main() {
    log "INFO" "Starting pre-flight checks for environment: $ENVIRONMENT"
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║         Crypto Trading Bot - Pre-Flight Check               ║"
    echo "║                                                              ║"
    echo "║  Environment: $(printf "%-48s" "$ENVIRONMENT")║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    # Run all checks
    check_docker || true
    check_kubernetes || true
    check_helm || true
    check_secrets || true
    check_dns || true
    check_storage || true
    check_network || true
    check_certificates || true
    check_resource_quotas || true
    check_docker_images || true
    check_configuration_files || true
    check_dependencies || true
    check_python_environment || true

    # Print summary
    echo -e "\n${BLUE}=== Summary ===${NC}" | tee -a "$LOG_FILE"
    echo "Total checks: $TOTAL_CHECKS" | tee -a "$LOG_FILE"
    echo -e "${GREEN}Passed: $PASSED_CHECKS${NC}" | tee -a "$LOG_FILE"
    echo -e "${RED}Failed: $FAILED_CHECKS${NC}" | tee -a "$LOG_FILE"
    echo -e "${YELLOW}Warnings: $WARNING_CHECKS${NC}" | tee -a "$LOG_FILE"
    echo -e "\nLog file: $LOG_FILE" | tee -a "$LOG_FILE"

    # Determine exit code
    if [ "$FAILED_CHECKS" -gt 0 ]; then
        echo -e "\n${RED}❌ Pre-flight checks FAILED. Deployment should not proceed.${NC}" | tee -a "$LOG_FILE"
        log "ERROR" "Pre-flight checks failed with $FAILED_CHECKS failures"
        exit 1
    elif [ "$WARNING_CHECKS" -gt 0 ]; then
        echo -e "\n${YELLOW}⚠️  Pre-flight checks completed with warnings. Proceed with caution.${NC}" | tee -a "$LOG_FILE"
        log "WARNING" "Pre-flight checks completed with $WARNING_CHECKS warnings"
        exit 2
    else
        echo -e "\n${GREEN}✅ All pre-flight checks passed. Ready for deployment.${NC}" | tee -a "$LOG_FILE"
        log "INFO" "All pre-flight checks passed"
        exit 0
    fi
}

# Run main function
main "$@"
