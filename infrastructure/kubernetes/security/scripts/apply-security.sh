#!/bin/bash
# Apply Security Configuration Script
# Applies all security manifests in the correct order
# Version: 1.0
# Created: 2025-12-12
#
# USAGE:
#   ./apply-security.sh [staging|production] [--dry-run]
#
# This script applies:
# 1. Namespace with Pod Security Standards
# 2. RBAC (ServiceAccounts, Roles, RoleBindings)
# 3. Network Policies
# 4. External Secrets configuration (if Vault is available)
# 5. Hardened deployments

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ENVIRONMENT=${1:-staging}
DRY_RUN=""

if [ "$2" == "--dry-run" ]; then
    DRY_RUN="--dry-run=client"
    echo -e "${YELLOW}Running in DRY-RUN mode${NC}"
fi

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
echo "Applying Kubernetes Security Configuration"
echo "Environment: $ENVIRONMENT"
echo "Namespace: $NAMESPACE"
echo "=============================================="

# Function to apply manifest
apply_manifest() {
    local file=$1
    local description=$2

    if [ -f "$file" ]; then
        echo -e "${BLUE}Applying:${NC} $description"
        if kubectl apply -f "$file" $DRY_RUN; then
            echo -e "${GREEN}[OK]${NC} $description applied successfully"
        else
            echo -e "${RED}[FAILED]${NC} Failed to apply $description"
            return 1
        fi
    else
        echo -e "${YELLOW}[SKIP]${NC} $file not found"
    fi
}

# Step 1: Validate security configuration
echo ""
echo "--- Step 1: Validating Security Configuration ---"
if [ -f "$SCRIPT_DIR/validate-security.sh" ]; then
    chmod +x "$SCRIPT_DIR/validate-security.sh"
    if ! "$SCRIPT_DIR/validate-security.sh" "$ENVIRONMENT"; then
        echo -e "${RED}Security validation failed. Aborting deployment.${NC}"
        exit 1
    fi
fi

# Step 2: Apply Pod Security Standards (Namespace)
echo ""
echo "--- Step 2: Applying Pod Security Standards ---"
apply_manifest "$SECURITY_DIR/pod-security/pod-security-standards.yaml" "Pod Security Standards"

# Wait for namespace to be ready
if [ -z "$DRY_RUN" ]; then
    echo "Waiting for namespace to be ready..."
    kubectl wait --for=condition=Active namespace/$NAMESPACE --timeout=30s 2>/dev/null || true
fi

# Step 3: Apply RBAC Configuration
echo ""
echo "--- Step 3: Applying RBAC Configuration ---"
apply_manifest "$SECURITY_DIR/rbac/service-accounts.yaml" "Service Accounts"
apply_manifest "$SECURITY_DIR/rbac/roles-and-bindings.yaml" "Roles and RoleBindings"

# Step 4: Apply Network Policies
echo ""
echo "--- Step 4: Applying Network Policies ---"
echo -e "${YELLOW}NOTE: Network Policies require a CNI that supports them (Calico, Cilium, etc.)${NC}"
apply_manifest "$SECURITY_DIR/network-policies/default-deny.yaml" "Default Deny Policies"
apply_manifest "$SECURITY_DIR/network-policies/microservices-policies.yaml" "Microservice Network Policies"
apply_manifest "$SECURITY_DIR/network-policies/database-policies.yaml" "Database Network Policies"

# Step 5: Apply External Secrets (if Vault is available)
echo ""
echo "--- Step 5: Checking External Secrets Configuration ---"

# Check if External Secrets Operator is installed
if kubectl get crd externalsecrets.external-secrets.io &> /dev/null; then
    echo -e "${GREEN}External Secrets Operator detected${NC}"
    apply_manifest "$SECURITY_DIR/external-secrets/external-secrets-operator.yaml" "External Secrets Operator Config"
    apply_manifest "$SECURITY_DIR/external-secrets/external-secret-templates.yaml" "External Secret Templates"
else
    echo -e "${YELLOW}External Secrets Operator not installed${NC}"
    echo "To install, run:"
    echo "  helm repo add external-secrets https://charts.external-secrets.io"
    echo "  helm install external-secrets external-secrets/external-secrets -n external-secrets-system --create-namespace"
fi

# Step 6: Apply Hardened Deployments
echo ""
echo "--- Step 6: Applying Hardened Deployments ---"
if [ "$ENVIRONMENT" == "staging" ]; then
    apply_manifest "$SECURITY_DIR/staging/hardened-deployments.yaml" "Staging Hardened Deployments"
elif [ "$ENVIRONMENT" == "production" ]; then
    apply_manifest "$SECURITY_DIR/production/hardened-deployments.yaml" "Production Hardened Deployments"
fi

# Step 7: Verify deployment
echo ""
echo "--- Step 7: Verifying Deployment ---"

if [ -z "$DRY_RUN" ]; then
    echo "Checking resources in $NAMESPACE..."

    echo ""
    echo "Service Accounts:"
    kubectl get serviceaccounts -n "$NAMESPACE" -l app=crypto-trading-bot 2>/dev/null || echo "No service accounts found"

    echo ""
    echo "Network Policies:"
    kubectl get networkpolicies -n "$NAMESPACE" 2>/dev/null || echo "No network policies found"

    echo ""
    echo "Deployments:"
    kubectl get deployments -n "$NAMESPACE" -l security-hardened=true 2>/dev/null || echo "No hardened deployments found"
fi

echo ""
echo "=============================================="
echo "Security Configuration Applied Successfully"
echo "=============================================="
echo ""
echo "Next steps:"
echo "1. Configure HashiCorp Vault with required secrets"
echo "2. Update External Secret paths if using different secret store"
echo "3. Verify pods are running: kubectl get pods -n $NAMESPACE"
echo "4. Check for security violations: kubectl get events -n $NAMESPACE"
echo ""
