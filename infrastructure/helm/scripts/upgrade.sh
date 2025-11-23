#!/bin/bash
# Helm upgrade script for Crypto Trading Bot
# Usage: ./upgrade.sh [environment] [namespace] [release-name]

set -e
set -u

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Default values
ENVIRONMENT=${1:-dev}
NAMESPACE=${2:-crypto-bot}
RELEASE_NAME=${3:-crypto-trading-bot}
CHART_PATH="../crypto-trading-bot"
TIMEOUT="10m"

print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if release exists
check_release() {
    print_info "Checking if release exists..."

    if ! helm list -n "$NAMESPACE" | grep -q "$RELEASE_NAME"; then
        print_error "Release $RELEASE_NAME not found in namespace $NAMESPACE"
        print_info "Use install.sh to install the chart first"
        exit 1
    fi

    print_success "Release found: $RELEASE_NAME"
}

# Get current release info
get_current_info() {
    print_info "Current release information:"
    helm list -n "$NAMESPACE" | grep "$RELEASE_NAME"

    print_info "Current revision:"
    CURRENT_REVISION=$(helm history "$RELEASE_NAME" -n "$NAMESPACE" --max 1 -o json | jq -r '.[0].revision')
    echo "  Revision: $CURRENT_REVISION"
}

# Show what will change
show_diff() {
    print_info "Checking for changes..."

    if command -v helm-diff &> /dev/null; then
        print_info "Showing differences (helm-diff plugin):"
        helm diff upgrade "$RELEASE_NAME" "$CHART_PATH" \
            --namespace "$NAMESPACE" \
            --values "$CHART_PATH/values-$ENVIRONMENT.yaml" \
            --allow-unreleased || true
    else
        print_warning "helm-diff plugin not installed. Skipping diff"
        print_info "Install with: helm plugin install https://github.com/databus23/helm-diff"
    fi
}

# Perform upgrade
perform_upgrade() {
    print_info "Performing upgrade..."
    print_info "Release: $RELEASE_NAME"
    print_info "Namespace: $NAMESPACE"
    print_info "Environment: $ENVIRONMENT"

    # Confirm upgrade in production
    if [ "$ENVIRONMENT" == "prod" ]; then
        print_warning "You are about to upgrade PRODUCTION environment!"
        read -p "Are you sure you want to continue? (yes/no): " CONFIRM
        if [ "$CONFIRM" != "yes" ]; then
            print_info "Upgrade cancelled"
            exit 0
        fi
    fi

    helm upgrade "$RELEASE_NAME" "$CHART_PATH" \
        --namespace "$NAMESPACE" \
        --values "$CHART_PATH/values-$ENVIRONMENT.yaml" \
        --wait \
        --timeout "$TIMEOUT" \
        --atomic \
        --cleanup-on-fail \
        --force \
        --reset-values

    if [ $? -eq 0 ]; then
        print_success "Upgrade completed successfully"
    else
        print_error "Upgrade failed"
        print_warning "The release has been rolled back automatically (--atomic flag)"
        exit 1
    fi
}

# Monitor rollout status
monitor_rollout() {
    print_info "Monitoring rollout status..."

    # List of deployments to monitor
    DEPLOYMENTS=(
        "api-gateway"
        "trading-engine"
        "portfolio-manager"
        "technical-analysis"
        "bybit-connector"
        "market-data-service"
        "notification-service"
        "ml-prediction-service"
        "risk-metrics-service"
        "sentiment-analysis-service"
    )

    for deployment in "${DEPLOYMENTS[@]}"; do
        if kubectl get deployment "$deployment" -n "$NAMESPACE" &> /dev/null; then
            print_info "Checking rollout status for $deployment..."
            kubectl rollout status deployment/"$deployment" -n "$NAMESPACE" --timeout=5m || true
        fi
    done
}

# Verify upgrade
verify_upgrade() {
    print_info "Verifying upgrade..."

    # Check new revision
    NEW_REVISION=$(helm history "$RELEASE_NAME" -n "$NAMESPACE" --max 1 -o json | jq -r '.[0].revision')
    print_success "Upgraded to revision: $NEW_REVISION"

    # Check pod status
    print_info "Pod status:"
    kubectl get pods -n "$NAMESPACE"

    # Check for failed pods
    FAILED_PODS=$(kubectl get pods -n "$NAMESPACE" --field-selector=status.phase!=Running,status.phase!=Succeeded -o name | wc -l)
    if [ "$FAILED_PODS" -gt 0 ]; then
        print_warning "Some pods are not in Running state"
        kubectl get pods -n "$NAMESPACE" --field-selector=status.phase!=Running,status.phase!=Succeeded
        print_warning "Check pod logs with: kubectl logs <pod-name> -n $NAMESPACE"
    else
        print_success "All pods are running"
    fi
}

# Display rollback info
display_rollback_info() {
    echo ""
    echo "======================================================================="
    echo "  Upgrade Completed"
    echo "======================================================================="
    echo ""
    print_info "If you need to rollback, use:"
    echo "  ./rollback.sh $ENVIRONMENT $NAMESPACE $RELEASE_NAME"
    echo ""
    print_info "Or manually:"
    echo "  helm rollback $RELEASE_NAME -n $NAMESPACE"
    echo ""
    print_info "View upgrade history:"
    echo "  helm history $RELEASE_NAME -n $NAMESPACE"
    echo ""
    echo "======================================================================="
}

# Main function
main() {
    print_info "Starting upgrade process"
    echo ""

    check_release
    get_current_info
    show_diff
    perform_upgrade
    monitor_rollout
    verify_upgrade
    display_rollback_info

    print_success "Upgrade process completed!"
}

main
