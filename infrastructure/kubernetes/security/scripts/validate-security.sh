#!/bin/bash
# Kubernetes Security Validation Script
# Validates security configurations before deployment
# Version: 1.0
# Created: 2025-12-12
#
# USAGE:
#   ./validate-security.sh [staging|production]
#
# This script checks:
# - Pod Security Standards compliance
# - SecurityContext configurations
# - RBAC configurations
# - Network Policies
# - Secret management

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ENVIRONMENT=${1:-staging}
NAMESPACE=""
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
echo "Kubernetes Security Validation"
echo "Environment: $ENVIRONMENT"
echo "Namespace: $NAMESPACE"
echo "=============================================="

ERRORS=0
WARNINGS=0

# Function to log success
log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

# Function to log warning
log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    ((WARNINGS++))
}

# Function to log error
log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((ERRORS++))
}

echo ""
echo "--- Checking YAML Syntax ---"

# Check YAML syntax for all security manifests
find "$SECURITY_DIR" -name "*.yaml" -type f | while read -r file; do
    if command -v yamllint &> /dev/null; then
        if yamllint -d relaxed "$file" > /dev/null 2>&1; then
            echo -e "${GREEN}[OK]${NC} $file"
        else
            log_error "YAML syntax error in $file"
        fi
    else
        # Fallback to kubectl dry-run
        if kubectl apply --dry-run=client -f "$file" > /dev/null 2>&1; then
            echo -e "${GREEN}[OK]${NC} $file"
        else
            log_warning "Could not validate $file (install yamllint for better validation)"
        fi
    fi
done

echo ""
echo "--- Checking Pod Security Standards ---"

# Check namespace labels for Pod Security Standards
if kubectl get namespace "$NAMESPACE" &> /dev/null; then
    PSS_ENFORCE=$(kubectl get namespace "$NAMESPACE" -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/enforce}' 2>/dev/null || echo "")

    if [ -z "$PSS_ENFORCE" ]; then
        log_error "Namespace $NAMESPACE does not have Pod Security Standards labels"
    elif [ "$ENVIRONMENT" == "production" ] && [ "$PSS_ENFORCE" != "restricted" ]; then
        log_error "Production namespace should use 'restricted' PSS (found: $PSS_ENFORCE)"
    else
        log_success "Pod Security Standards: $PSS_ENFORCE"
    fi
else
    log_warning "Namespace $NAMESPACE does not exist yet (will be created during deployment)"
fi

echo ""
echo "--- Checking SecurityContext in Deployments ---"

# Validate security context in deployment files
check_security_context() {
    local file=$1
    local errors_in_file=0

    # Check for runAsNonRoot
    if ! grep -q "runAsNonRoot: true" "$file"; then
        log_error "Missing 'runAsNonRoot: true' in $file"
        ((errors_in_file++))
    fi

    # Check for allowPrivilegeEscalation: false
    if ! grep -q "allowPrivilegeEscalation: false" "$file"; then
        log_error "Missing 'allowPrivilegeEscalation: false' in $file"
        ((errors_in_file++))
    fi

    # Check for capabilities drop
    if ! grep -q "drop:" "$file"; then
        log_warning "Consider dropping all capabilities in $file"
    fi

    # Check for readOnlyRootFilesystem
    if ! grep -q "readOnlyRootFilesystem: true" "$file"; then
        log_warning "Consider using 'readOnlyRootFilesystem: true' in $file"
    fi

    if [ $errors_in_file -eq 0 ]; then
        log_success "SecurityContext validated: $file"
    fi
}

# Check hardened deployment files
if [ -f "$SECURITY_DIR/$ENVIRONMENT/hardened-deployments.yaml" ]; then
    check_security_context "$SECURITY_DIR/$ENVIRONMENT/hardened-deployments.yaml"
fi

echo ""
echo "--- Checking ServiceAccount Configuration ---"

# Validate service accounts
if [ -f "$SECURITY_DIR/rbac/service-accounts.yaml" ]; then
    # Check for automountServiceAccountToken: false
    SA_COUNT=$(grep -c "kind: ServiceAccount" "$SECURITY_DIR/rbac/service-accounts.yaml" || echo "0")
    AUTOMOUNT_FALSE=$(grep -c "automountServiceAccountToken: false" "$SECURITY_DIR/rbac/service-accounts.yaml" || echo "0")

    if [ "$SA_COUNT" == "$AUTOMOUNT_FALSE" ]; then
        log_success "All $SA_COUNT ServiceAccounts have automountServiceAccountToken: false"
    else
        log_warning "$AUTOMOUNT_FALSE/$SA_COUNT ServiceAccounts have automountServiceAccountToken: false"
    fi
fi

echo ""
echo "--- Checking Network Policies ---"

# Check for default deny policies
if [ -f "$SECURITY_DIR/network-policies/default-deny.yaml" ]; then
    if grep -q "default-deny-ingress" "$SECURITY_DIR/network-policies/default-deny.yaml"; then
        log_success "Default deny ingress policy exists"
    else
        log_error "Missing default deny ingress policy"
    fi

    if grep -q "default-deny-egress" "$SECURITY_DIR/network-policies/default-deny.yaml"; then
        log_success "Default deny egress policy exists"
    else
        log_error "Missing default deny egress policy"
    fi
else
    log_error "Default deny network policies file not found"
fi

# Check for DNS allow policy
if grep -q "allow-dns" "$SECURITY_DIR/network-policies/default-deny.yaml" 2>/dev/null; then
    log_success "DNS resolution policy exists"
else
    log_warning "DNS resolution policy may be missing"
fi

echo ""
echo "--- Checking Secrets Management ---"

# Check for External Secrets configuration
if [ -f "$SECURITY_DIR/external-secrets/external-secrets-operator.yaml" ]; then
    log_success "External Secrets Operator configuration exists"
else
    log_warning "External Secrets Operator not configured"
fi

# Check for plain secrets in git (should not exist)
PLAIN_SECRETS=$(find "$SECURITY_DIR" -name "*.yaml" -exec grep -l "CHANGE_ME\|password:" {} \; 2>/dev/null | wc -l)
if [ "$PLAIN_SECRETS" -gt 0 ]; then
    log_warning "Found $PLAIN_SECRETS files with potential plain secrets (ensure they are templates only)"
fi

echo ""
echo "--- Checking RBAC Configuration ---"

if [ -f "$SECURITY_DIR/rbac/roles-and-bindings.yaml" ]; then
    # Check for least privilege (no * in verbs)
    WILDCARD_VERBS=$(grep -c 'verbs: \["\*"\]' "$SECURITY_DIR/rbac/roles-and-bindings.yaml" 2>/dev/null || echo "0")
    if [ "$WILDCARD_VERBS" -gt 0 ]; then
        log_error "Found $WILDCARD_VERBS roles with wildcard verbs (security risk)"
    else
        log_success "No wildcard verbs in RBAC roles"
    fi

    # Check for resource restrictions
    if grep -q "resourceNames:" "$SECURITY_DIR/rbac/roles-and-bindings.yaml"; then
        log_success "RBAC roles use resource name restrictions"
    else
        log_warning "Consider adding resourceNames restrictions to RBAC roles"
    fi
fi

echo ""
echo "--- Checking Resource Limits ---"

# Check for resource limits in deployments
if [ -f "$SECURITY_DIR/$ENVIRONMENT/hardened-deployments.yaml" ]; then
    if grep -q "limits:" "$SECURITY_DIR/$ENVIRONMENT/hardened-deployments.yaml"; then
        log_success "Resource limits defined in deployments"
    else
        log_error "Missing resource limits in deployments"
    fi

    if grep -q "requests:" "$SECURITY_DIR/$ENVIRONMENT/hardened-deployments.yaml"; then
        log_success "Resource requests defined in deployments"
    else
        log_warning "Missing resource requests in deployments"
    fi
fi

echo ""
echo "=============================================="
echo "Security Validation Summary"
echo "=============================================="
echo -e "Errors:   ${RED}$ERRORS${NC}"
echo -e "Warnings: ${YELLOW}$WARNINGS${NC}"
echo ""

if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}Security validation FAILED${NC}"
    echo "Please fix the errors before deploying to $ENVIRONMENT"
    exit 1
elif [ $WARNINGS -gt 5 ]; then
    echo -e "${YELLOW}Security validation passed with warnings${NC}"
    echo "Consider addressing warnings before production deployment"
    exit 0
else
    echo -e "${GREEN}Security validation PASSED${NC}"
    exit 0
fi
