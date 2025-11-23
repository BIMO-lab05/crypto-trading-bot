#!/bin/bash
# Helm installation script for Crypto Trading Bot
# Usage: ./install.sh [environment] [namespace] [release-name]
#
# Examples:
#   ./install.sh dev crypto-bot crypto-trading-bot
#   ./install.sh staging crypto-bot-staging crypto-trading-bot
#   ./install.sh prod crypto-bot-prod crypto-trading-bot

set -e  # Exit on error
set -u  # Exit on undefined variable

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
ENVIRONMENT=${1:-dev}
NAMESPACE=${2:-crypto-bot}
RELEASE_NAME=${3:-crypto-trading-bot}
CHART_PATH="../crypto-trading-bot"
TIMEOUT="10m"

# Function to print colored messages
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check prerequisites
check_prerequisites() {
    print_info "Checking prerequisites..."

    # Check if helm is installed
    if ! command -v helm &> /dev/null; then
        print_error "Helm is not installed. Please install Helm 3.x"
        exit 1
    fi

    # Check Helm version
    HELM_VERSION=$(helm version --short | grep -oP 'v\d+' | cut -d'v' -f2)
    if [ "$HELM_VERSION" -lt 3 ]; then
        print_error "Helm 3.x or higher is required. Current version: $(helm version --short)"
        exit 1
    fi

    # Check if kubectl is installed
    if ! command -v kubectl &> /dev/null; then
        print_error "kubectl is not installed. Please install kubectl"
        exit 1
    fi

    # Check Kubernetes connection
    if ! kubectl cluster-info &> /dev/null; then
        print_error "Cannot connect to Kubernetes cluster. Please check your kubeconfig"
        exit 1
    fi

    print_success "All prerequisites met"
}

# Function to validate environment
validate_environment() {
    print_info "Validating environment: $ENVIRONMENT"

    if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|prod)$ ]]; then
        print_error "Invalid environment: $ENVIRONMENT. Must be one of: dev, staging, prod"
        exit 1
    fi

    # Check if values file exists
    VALUES_FILE="$CHART_PATH/values-$ENVIRONMENT.yaml"
    if [ ! -f "$VALUES_FILE" ]; then
        print_error "Values file not found: $VALUES_FILE"
        exit 1
    fi

    print_success "Environment validation passed"
}

# Function to create namespace
create_namespace() {
    print_info "Creating namespace: $NAMESPACE"

    if kubectl get namespace "$NAMESPACE" &> /dev/null; then
        print_warning "Namespace $NAMESPACE already exists"
    else
        kubectl create namespace "$NAMESPACE"
        kubectl label namespace "$NAMESPACE" environment="$ENVIRONMENT"
        print_success "Namespace created: $NAMESPACE"
    fi
}

# Function to create secrets (if not exist)
create_secrets() {
    print_info "Checking required secrets..."

    REQUIRED_SECRETS=(
        "postgresql-secret"
        "timescaledb-secret"
        "redis-secret"
        "rabbitmq-secret"
        "bybit-secret"
        "grafana-secret"
    )

    MISSING_SECRETS=()

    for secret in "${REQUIRED_SECRETS[@]}"; do
        if ! kubectl get secret "$secret" -n "$NAMESPACE" &> /dev/null; then
            MISSING_SECRETS+=("$secret")
        fi
    done

    if [ ${#MISSING_SECRETS[@]} -ne 0 ]; then
        print_warning "The following secrets are missing and need to be created:"
        for secret in "${MISSING_SECRETS[@]}"; do
            echo "  - $secret"
        done
        print_warning "Please create these secrets before proceeding or the deployment may fail."
        print_info "Example command to create secrets:"
        echo "  kubectl create secret generic postgresql-secret --from-literal=password=YOUR_PASSWORD -n $NAMESPACE"

        read -p "Do you want to continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "Installation cancelled"
            exit 0
        fi
    else
        print_success "All required secrets exist"
    fi
}

# Function to perform dry-run
dry_run() {
    print_info "Performing dry-run validation..."

    if helm upgrade --install "$RELEASE_NAME" "$CHART_PATH" \
        --namespace "$NAMESPACE" \
        --values "$CHART_PATH/values-$ENVIRONMENT.yaml" \
        --dry-run --debug > /dev/null 2>&1; then
        print_success "Dry-run validation passed"
    else
        print_error "Dry-run validation failed. Please check your configuration"
        exit 1
    fi
}

# Function to install/upgrade chart
install_chart() {
    print_info "Installing/Upgrading Helm chart..."
    print_info "Release: $RELEASE_NAME"
    print_info "Namespace: $NAMESPACE"
    print_info "Environment: $ENVIRONMENT"
    print_info "Timeout: $TIMEOUT"

    helm upgrade --install "$RELEASE_NAME" "$CHART_PATH" \
        --namespace "$NAMESPACE" \
        --create-namespace \
        --values "$CHART_PATH/values-$ENVIRONMENT.yaml" \
        --wait \
        --timeout "$TIMEOUT" \
        --atomic \
        --cleanup-on-fail

    if [ $? -eq 0 ]; then
        print_success "Chart installed/upgraded successfully"
    else
        print_error "Chart installation/upgrade failed"
        exit 1
    fi
}

# Function to verify deployment
verify_deployment() {
    print_info "Verifying deployment..."

    # Wait for all pods to be ready
    print_info "Waiting for pods to be ready..."
    kubectl wait --for=condition=ready pod \
        --all \
        -n "$NAMESPACE" \
        --timeout=5m || true

    # Get pod status
    print_info "Pod status:"
    kubectl get pods -n "$NAMESPACE"

    # Get service status
    print_info "Service status:"
    kubectl get svc -n "$NAMESPACE"

    # Get ingress status
    if [ "$ENVIRONMENT" != "dev" ]; then
        print_info "Ingress status:"
        kubectl get ingress -n "$NAMESPACE"
    fi

    # Check for failed pods
    FAILED_PODS=$(kubectl get pods -n "$NAMESPACE" --field-selector=status.phase!=Running,status.phase!=Succeeded -o name | wc -l)
    if [ "$FAILED_PODS" -gt 0 ]; then
        print_warning "Some pods are not in Running state"
        kubectl get pods -n "$NAMESPACE" --field-selector=status.phase!=Running,status.phase!=Succeeded
    else
        print_success "All pods are running"
    fi
}

# Function to run Helm tests
run_tests() {
    print_info "Running Helm tests..."

    if helm test "$RELEASE_NAME" -n "$NAMESPACE" --timeout 5m; then
        print_success "All tests passed"
    else
        print_warning "Some tests failed. Check the test pod logs for details"
    fi
}

# Function to display summary
display_summary() {
    echo ""
    echo "======================================================================="
    echo "  Deployment Summary"
    echo "======================================================================="
    echo ""
    echo "  Release Name: $RELEASE_NAME"
    echo "  Namespace: $NAMESPACE"
    echo "  Environment: $ENVIRONMENT"
    echo ""
    echo "======================================================================="
    echo "  Useful Commands"
    echo "======================================================================="
    echo ""
    echo "  View release status:"
    echo "    helm status $RELEASE_NAME -n $NAMESPACE"
    echo ""
    echo "  View pods:"
    echo "    kubectl get pods -n $NAMESPACE"
    echo ""
    echo "  View logs:"
    echo "    kubectl logs -f -n $NAMESPACE -l app=api-gateway"
    echo ""
    echo "  Port forward API Gateway:"
    echo "    kubectl port-forward -n $NAMESPACE svc/api-gateway 8000:8000"
    echo ""
    echo "  Uninstall release:"
    echo "    helm uninstall $RELEASE_NAME -n $NAMESPACE"
    echo ""
    echo "======================================================================="

    # Display notes
    print_info "Deployment notes:"
    helm get notes "$RELEASE_NAME" -n "$NAMESPACE"
}

# Main installation flow
main() {
    print_info "Starting Crypto Trading Bot installation"
    print_info "==========================================="
    echo ""

    check_prerequisites
    validate_environment
    create_namespace
    create_secrets
    dry_run
    install_chart
    verify_deployment

    # Ask if user wants to run tests
    read -p "Do you want to run Helm tests? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        run_tests
    fi

    display_summary

    print_success "Installation completed successfully!"
}

# Run main function
main
