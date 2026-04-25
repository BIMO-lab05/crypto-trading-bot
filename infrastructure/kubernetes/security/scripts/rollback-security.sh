#!/bin/bash
# Security Configuration Rollback Script
# Rolls back security configurations in case of issues
# Version: 1.0
# Created: 2025-12-12
#
# USAGE:
#   ./rollback-security.sh [staging|production] [component]
#
# Components:
#   all             - Rollback all security configurations
#   network         - Rollback network policies only
#   rbac            - Rollback RBAC only
#   deployments     - Rollback hardened deployments only

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ENVIRONMENT=${1:-staging}
COMPONENT=${2:-all}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECURITY_DIR="$(dirname "$SCRIPT_DIR")"

if [ "$ENVIRONMENT" == "staging" ]; then
    NAMESPACE="trading-bot-staging"
elif [ "$ENVIRONMENT" == "production" ]; then
    NAMESPACE="crypto-bot"
else
    echo -e "${RED}Invalid environment. Use 'staging' or 'production'${NC}"
    exit 1
fi

echo "=============================================="
echo "Security Configuration Rollback"
echo "Environment: $ENVIRONMENT"
echo "Namespace: $NAMESPACE"
echo "Component: $COMPONENT"
echo "=============================================="
echo ""

# Confirmation prompt
echo -e "${RED}WARNING: This will remove security configurations!${NC}"
read -p "Are you sure you want to continue? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Rollback cancelled."
    exit 0
fi

rollback_network_policies() {
    echo ""
    echo "--- Rolling back Network Policies ---"

    # Delete network policies
    kubectl delete networkpolicy -n "$NAMESPACE" --all 2>/dev/null || true
    echo -e "${GREEN}Network policies removed${NC}"
}

rollback_rbac() {
    echo ""
    echo "--- Rolling back RBAC Configuration ---"

    # Delete role bindings first
    kubectl delete rolebinding -n "$NAMESPACE" -l app=crypto-trading-bot 2>/dev/null || true

    # Delete roles
    kubectl delete role -n "$NAMESPACE" -l app=crypto-trading-bot 2>/dev/null || true

    # Note: Service accounts are usually not deleted as pods depend on them
    echo -e "${YELLOW}NOTE: ServiceAccounts not deleted - pods may depend on them${NC}"
    echo -e "${GREEN}RBAC configuration rolled back${NC}"
}

rollback_deployments() {
    echo ""
    echo "--- Rolling back Hardened Deployments ---"

    # Delete hardened deployments
    kubectl delete deployment -n "$NAMESPACE" -l security-hardened=true 2>/dev/null || true
    echo -e "${GREEN}Hardened deployments removed${NC}"

    echo ""
    echo -e "${YELLOW}To restore original deployments, apply from staging/production directory:${NC}"
    echo "kubectl apply -f infrastructure/kubernetes/staging/"
}

rollback_external_secrets() {
    echo ""
    echo "--- Rolling back External Secrets ---"

    # Delete external secrets
    kubectl delete externalsecret -n "$NAMESPACE" --all 2>/dev/null || true
    kubectl delete secretstore -n "$NAMESPACE" --all 2>/dev/null || true
    echo -e "${GREEN}External Secrets configuration removed${NC}"
}

case $COMPONENT in
    "all")
        rollback_network_policies
        rollback_rbac
        rollback_deployments
        rollback_external_secrets
        ;;
    "network")
        rollback_network_policies
        ;;
    "rbac")
        rollback_rbac
        ;;
    "deployments")
        rollback_deployments
        ;;
    "secrets")
        rollback_external_secrets
        ;;
    *)
        echo -e "${RED}Unknown component: $COMPONENT${NC}"
        echo "Valid components: all, network, rbac, deployments, secrets"
        exit 1
        ;;
esac

echo ""
echo "=============================================="
echo "Rollback Complete"
echo "=============================================="
echo ""
echo "To restore previous configuration:"
echo "1. Network Policies: kubectl apply -f $SECURITY_DIR/network-policies/"
echo "2. RBAC: kubectl apply -f $SECURITY_DIR/rbac/"
echo "3. Deployments: kubectl apply -f $SECURITY_DIR/$ENVIRONMENT/"
echo ""
