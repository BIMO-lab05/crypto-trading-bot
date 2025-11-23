#!/bin/bash
# Helm uninstall script for Crypto Trading Bot
# Usage: ./uninstall.sh [namespace] [release-name]

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
DELETE_NAMESPACE=${3:-false}
DELETE_PVC=${4:-false}

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

# Display current resources
display_resources() {
    print_info "Current resources in namespace $NAMESPACE:"

    echo ""
    echo "Deployments:"
    kubectl get deployments -n "$NAMESPACE" 2>/dev/null || echo "  None"

    echo ""
    echo "StatefulSets:"
    kubectl get statefulsets -n "$NAMESPACE" 2>/dev/null || echo "  None"

    echo ""
    echo "Services:"
    kubectl get services -n "$NAMESPACE" 2>/dev/null || echo "  None"

    echo ""
    echo "PersistentVolumeClaims:"
    kubectl get pvc -n "$NAMESPACE" 2>/dev/null || echo "  None"

    echo ""
    echo "Secrets:"
    kubectl get secrets -n "$NAMESPACE" 2>/dev/null || echo "  None"

    echo ""
}

# Confirm uninstall
confirm_uninstall() {
    print_warning "You are about to uninstall the following:"
    echo "  Release: $RELEASE_NAME"
    echo "  Namespace: $NAMESPACE"
    echo "  Delete Namespace: $DELETE_NAMESPACE"
    echo "  Delete PVCs: $DELETE_PVC"
    echo ""
    print_warning "This action cannot be undone!"
    echo ""

    read -p "Are you sure you want to continue? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        print_info "Uninstall cancelled"
        exit 0
    fi
}

# Backup important data
backup_data() {
    print_info "Creating backup of important resources..."

    BACKUP_DIR="./backups/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"

    # Backup secrets (excluding default tokens)
    print_info "Backing up secrets..."
    kubectl get secrets -n "$NAMESPACE" -o yaml > "$BACKUP_DIR/secrets.yaml" 2>/dev/null || true

    # Backup configmaps
    print_info "Backing up configmaps..."
    kubectl get configmaps -n "$NAMESPACE" -o yaml > "$BACKUP_DIR/configmaps.yaml" 2>/dev/null || true

    # Backup PVCs
    print_info "Backing up PVC definitions..."
    kubectl get pvc -n "$NAMESPACE" -o yaml > "$BACKUP_DIR/pvcs.yaml" 2>/dev/null || true

    print_success "Backup created at: $BACKUP_DIR"
}

# Uninstall Helm release
uninstall_release() {
    print_info "Uninstalling Helm release..."

    if helm uninstall "$RELEASE_NAME" -n "$NAMESPACE"; then
        print_success "Helm release uninstalled successfully"
    else
        print_error "Failed to uninstall Helm release"
        exit 1
    fi
}

# Delete PVCs
delete_pvcs() {
    if [ "$DELETE_PVC" == "true" ]; then
        print_warning "Deleting PersistentVolumeClaims..."
        print_warning "THIS WILL DELETE ALL DATA!"

        read -p "Are you absolutely sure? (yes/no): " CONFIRM_PVC
        if [ "$CONFIRM_PVC" == "yes" ]; then
            kubectl delete pvc --all -n "$NAMESPACE"
            print_success "PVCs deleted"
        else
            print_info "Skipping PVC deletion"
        fi
    else
        print_info "Skipping PVC deletion (DELETE_PVC=false)"
        print_info "To delete PVCs, run: kubectl delete pvc --all -n $NAMESPACE"
    fi
}

# Delete namespace
delete_namespace() {
    if [ "$DELETE_NAMESPACE" == "true" ]; then
        print_warning "Deleting namespace: $NAMESPACE"

        read -p "Are you sure you want to delete the namespace? (yes/no): " CONFIRM_NS
        if [ "$CONFIRM_NS" == "yes" ]; then
            kubectl delete namespace "$NAMESPACE"
            print_success "Namespace deleted"
        else
            print_info "Skipping namespace deletion"
        fi
    else
        print_info "Skipping namespace deletion (DELETE_NAMESPACE=false)"
        print_info "To delete namespace, run: kubectl delete namespace $NAMESPACE"
    fi
}

# Cleanup orphaned resources
cleanup_orphaned() {
    print_info "Checking for orphaned resources..."

    # Check for orphaned PVs
    print_info "Orphaned PersistentVolumes:"
    kubectl get pv | grep "$NAMESPACE" || echo "  None"

    # Check for orphaned network policies
    print_info "Network policies:"
    kubectl get networkpolicies -n "$NAMESPACE" 2>/dev/null || echo "  None"
}

# Display summary
display_summary() {
    echo ""
    echo "======================================================================="
    echo "  Uninstall Summary"
    echo "======================================================================="
    echo ""
    echo "  Release: $RELEASE_NAME"
    echo "  Namespace: $NAMESPACE"
    echo "  Backup Location: $BACKUP_DIR"
    echo ""
    echo "======================================================================="
    echo "  Manual Cleanup (if needed)"
    echo "======================================================================="
    echo ""
    echo "  Check remaining resources:"
    echo "    kubectl get all -n $NAMESPACE"
    echo ""
    echo "  Delete PVCs:"
    echo "    kubectl delete pvc --all -n $NAMESPACE"
    echo ""
    echo "  Delete namespace:"
    echo "    kubectl delete namespace $NAMESPACE"
    echo ""
    echo "  Check orphaned PVs:"
    echo "    kubectl get pv | grep $NAMESPACE"
    echo ""
    echo "======================================================================="
}

# Main function
main() {
    print_info "Starting uninstall process"
    echo ""

    check_release
    display_resources
    confirm_uninstall
    backup_data
    uninstall_release
    delete_pvcs
    delete_namespace
    cleanup_orphaned
    display_summary

    print_success "Uninstall process completed!"
}

main
