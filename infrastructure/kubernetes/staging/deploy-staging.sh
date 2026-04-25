#!/bin/bash
# =============================================================================
# Staging Deployment Script for Crypto Trading Bot
# =============================================================================
# Version: 1.0
# Created: 2025-12-12
#
# This script deploys the crypto trading bot to Kubernetes staging environment
# Namespace: trading-bot-staging
#
# Usage:
#   ./deploy-staging.sh [options]
#
# Options:
#   --dry-run       Preview changes without applying
#   --skip-secrets  Skip secrets (if already configured)
#   --fast          Skip wait times (for testing)
#   --help          Show this help message
#
# Prerequisites:
#   - kubectl configured and connected to cluster
#   - Docker images built and pushed to registry
#   - Secrets updated with real values
# =============================================================================

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="trading-bot-staging"

# Default options
DRY_RUN=false
SKIP_SECRETS=false
FAST_MODE=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --skip-secrets)
            SKIP_SECRETS=true
            shift
            ;;
        --fast)
            FAST_MODE=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --dry-run       Preview changes without applying"
            echo "  --skip-secrets  Skip secrets (if already configured)"
            echo "  --fast          Skip wait times (for testing)"
            echo "  --help          Show this help message"
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
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

# Function to print step status
print_step() {
    echo -e "${CYAN}[STEP]${NC} $1"
}

# Function to print success
print_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

# Function to print warning
print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Function to print error
print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to apply manifest
apply_manifest() {
    local file=$1
    local description=$2

    print_step "Applying $description..."

    if [ "$DRY_RUN" = true ]; then
        kubectl apply -f "$file" --dry-run=client
        print_warning "DRY RUN - Not applied"
    else
        kubectl apply -f "$file"
        print_success "$description applied"
    fi
}

# Function to wait for pods
wait_for_pods() {
    local label=$1
    local timeout=$2

    if [ "$FAST_MODE" = true ]; then
        echo "Fast mode - skipping wait"
        return 0
    fi

    print_step "Waiting for pods with label '$label' (timeout: ${timeout}s)..."

    if [ "$DRY_RUN" = true ]; then
        print_warning "DRY RUN - Skipping wait"
        return 0
    fi

    if kubectl wait --for=condition=ready pod -l "$label" -n "$NAMESPACE" --timeout="${timeout}s" 2>/dev/null; then
        print_success "Pods are ready"
        return 0
    else
        print_warning "Some pods may not be ready yet"
        return 1
    fi
}

# Function to check prerequisites
check_prerequisites() {
    print_header "Checking Prerequisites"

    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        print_error "kubectl is not installed"
        exit 1
    fi
    print_success "kubectl is installed"

    # Check cluster connection
    print_step "Checking cluster connection..."
    if ! kubectl cluster-info &> /dev/null; then
        print_error "Cannot connect to Kubernetes cluster"
        echo "Please configure kubectl to connect to your cluster"
        exit 1
    fi

    CURRENT_CONTEXT=$(kubectl config current-context)
    print_success "Connected to cluster: $CURRENT_CONTEXT"

    # Display cluster info
    echo ""
    kubectl cluster-info | head -2
}

# Function to deploy namespace
deploy_namespace() {
    print_header "Step 1: Creating Namespace"
    apply_manifest "$SCRIPT_DIR/namespace.yaml" "Namespace and ResourceQuotas"

    # Wait for namespace to be created
    if [ "$DRY_RUN" = false ]; then
        sleep 2
    fi
}

# Function to deploy configmaps
deploy_configmaps() {
    print_header "Step 2: Deploying ConfigMaps"
    apply_manifest "$SCRIPT_DIR/configmap.yaml" "ConfigMaps"
}

# Function to deploy secrets
deploy_secrets() {
    print_header "Step 3: Deploying Secrets"

    if [ "$SKIP_SECRETS" = true ]; then
        print_warning "Skipping secrets (--skip-secrets flag)"
        return 0
    fi

    print_warning "IMPORTANT: Update secrets with real values before production use!"
    apply_manifest "$SCRIPT_DIR/secrets.yaml" "Secrets (templates)"
}

# Function to deploy storage
deploy_storage() {
    print_header "Step 4: Creating Persistent Volume Claims"
    apply_manifest "$SCRIPT_DIR/storage.yaml" "PVCs"

    # Wait for PVCs to be bound
    if [ "$DRY_RUN" = false ] && [ "$FAST_MODE" = false ]; then
        print_step "Waiting for PVCs to be bound..."
        sleep 10
        kubectl get pvc -n "$NAMESPACE" --no-headers | while read line; do
            pvc_name=$(echo "$line" | awk '{print $1}')
            status=$(echo "$line" | awk '{print $2}')
            if [ "$status" = "Bound" ]; then
                print_success "PVC $pvc_name is bound"
            else
                print_warning "PVC $pvc_name status: $status"
            fi
        done
    fi
}

# Function to deploy databases
deploy_databases() {
    print_header "Step 5: Deploying Databases"
    apply_manifest "$SCRIPT_DIR/databases.yaml" "PostgreSQL, TimescaleDB, Redis, RabbitMQ"

    # Wait for databases
    if [ "$DRY_RUN" = false ] && [ "$FAST_MODE" = false ]; then
        print_step "Waiting for databases to be ready (this may take 60-90 seconds)..."
        sleep 30
        wait_for_pods "database=postgres" 120 || true
        wait_for_pods "database=redis" 60 || true
    fi
}

# Function to deploy trading engine
deploy_trading_engine() {
    print_header "Step 6: Deploying Trading Engine"
    apply_manifest "$SCRIPT_DIR/trading-engine.yaml" "Trading Engine (3 replicas with HPA)"

    # Wait for trading engine pods
    wait_for_pods "service=trading-engine" 120 || true
}

# Function to deploy microservices
deploy_microservices() {
    print_header "Step 7: Deploying Microservices"
    apply_manifest "$SCRIPT_DIR/microservices.yaml" "All Microservices"

    # Wait for services
    if [ "$DRY_RUN" = false ] && [ "$FAST_MODE" = false ]; then
        print_step "Waiting for microservices to start..."
        sleep 30
    fi
}

# Function to deploy monitoring
deploy_monitoring() {
    print_header "Step 8: Deploying Monitoring Stack"
    apply_manifest "$SCRIPT_DIR/monitoring.yaml" "Prometheus and Grafana"
}

# Function to display summary
display_summary() {
    print_header "Deployment Summary"

    if [ "$DRY_RUN" = true ]; then
        print_warning "DRY RUN COMPLETE - No changes were applied"
        return 0
    fi

    echo -e "${YELLOW}Namespace:${NC}"
    kubectl get namespace "$NAMESPACE" 2>/dev/null || echo "Not found"

    echo ""
    echo -e "${YELLOW}Persistent Volumes:${NC}"
    kubectl get pvc -n "$NAMESPACE" 2>/dev/null || echo "None"

    echo ""
    echo -e "${YELLOW}Pods:${NC}"
    kubectl get pods -n "$NAMESPACE" 2>/dev/null || echo "None"

    echo ""
    echo -e "${YELLOW}Services:${NC}"
    kubectl get svc -n "$NAMESPACE" 2>/dev/null || echo "None"

    echo ""
    echo -e "${YELLOW}HorizontalPodAutoscalers:${NC}"
    kubectl get hpa -n "$NAMESPACE" 2>/dev/null || echo "None"

    print_header "Next Steps"
    echo "1. Verify all pods are running:"
    echo "   ${GREEN}kubectl get pods -n $NAMESPACE${NC}"
    echo ""
    echo "2. Check HPA status:"
    echo "   ${GREEN}kubectl get hpa -n $NAMESPACE${NC}"
    echo ""
    echo "3. View pod logs:"
    echo "   ${GREEN}kubectl logs -f deployment/trading-engine -n $NAMESPACE${NC}"
    echo ""
    echo "4. Access API Gateway:"
    echo "   ${GREEN}kubectl port-forward -n $NAMESPACE svc/api-gateway-service 8000:8000${NC}"
    echo ""
    echo "5. Access Grafana:"
    echo "   ${GREEN}kubectl port-forward -n $NAMESPACE svc/grafana-service 3000:3000${NC}"
    echo ""
    echo "6. Run verification script:"
    echo "   ${GREEN}./verify-staging.sh${NC}"
    echo ""
    print_warning "IMPORTANT: Update secrets with real values before using for trading!"
}

# Main deployment sequence
main() {
    print_header "Crypto Trading Bot - Staging Deployment"
    echo -e "Namespace: ${YELLOW}$NAMESPACE${NC}"
    echo -e "Dry Run: ${YELLOW}$DRY_RUN${NC}"
    echo -e "Skip Secrets: ${YELLOW}$SKIP_SECRETS${NC}"
    echo -e "Fast Mode: ${YELLOW}$FAST_MODE${NC}"
    echo ""

    # Check prerequisites
    check_prerequisites

    # Confirm deployment
    if [ "$DRY_RUN" = false ]; then
        echo ""
        read -p "Continue with deployment? (yes/no): " -r
        if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
            echo "Deployment cancelled"
            exit 0
        fi
    fi

    # Deploy in order
    deploy_namespace
    deploy_configmaps
    deploy_secrets
    deploy_storage
    deploy_databases
    deploy_trading_engine
    deploy_microservices
    deploy_monitoring

    # Display summary
    display_summary

    print_header "Deployment Complete!"
}

# Run main function
main
