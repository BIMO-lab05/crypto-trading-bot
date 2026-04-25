#!/bin/bash
# =============================================================================
# Production Deployment Script for Crypto Trading Bot
# =============================================================================
# Version: 1.0
# Created: 2025-12-12
#
# This script deploys the crypto trading bot to Kubernetes PRODUCTION environment
# Namespace: crypto-bot-prod
#
# IMPORTANT: This script deploys to PRODUCTION with REAL trading capabilities
# Ensure all security measures are in place before running.
#
# Usage:
#   ./deploy-production.sh [options]
#
# Options:
#   --dry-run           Preview changes without applying
#   --skip-secrets      Skip secrets (if already configured or using External Secrets)
#   --skip-security     Skip security validation (NOT RECOMMENDED)
#   --skip-databases    Skip database deployment (if already running)
#   --force             Skip confirmation prompts (use with caution)
#   --rollback          Rollback to previous deployment
#   --help              Show this help message
#
# Prerequisites:
#   - kubectl configured and connected to production cluster
#   - Docker images built, tested, and pushed to registry
#   - Security scan passed with no HIGH/CRITICAL issues
#   - All secrets properly configured (NOT template values)
#   - Staging deployment validated and approved
# =============================================================================

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Script directory and namespace
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
NAMESPACE="crypto-bot-prod"
SECURITY_DIR="$PROJECT_ROOT/infrastructure/kubernetes/security"

# Default options
DRY_RUN=false
SKIP_SECRETS=false
SKIP_SECURITY=false
SKIP_DATABASES=false
FORCE=false
ROLLBACK=false

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
        --skip-security)
            SKIP_SECURITY=true
            shift
            ;;
        --skip-databases)
            SKIP_DATABASES=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --rollback)
            ROLLBACK=true
            shift
            ;;
        --help|-h)
            head -40 "$0" | tail -35
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Logging functions
log_header() {
    echo ""
    echo -e "${MAGENTA}==================================================${NC}"
    echo -e "${MAGENTA}$1${NC}"
    echo -e "${MAGENTA}==================================================${NC}"
    echo ""
}

log_step() {
    echo -e "${CYAN}[STEP]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Function to apply manifest
apply_manifest() {
    local file=$1
    local description=$2

    log_step "Applying $description..."

    if [ "$DRY_RUN" = true ]; then
        kubectl apply -f "$file" --dry-run=client -o yaml | head -50
        log_warning "DRY RUN - Not applied"
    else
        if kubectl apply -f "$file"; then
            log_success "$description applied"
        else
            log_error "Failed to apply $description"
            return 1
        fi
    fi
}

# Function to wait for pods
wait_for_pods() {
    local label=$1
    local timeout=$2
    local description=$3

    log_step "Waiting for $description (timeout: ${timeout}s)..."

    if [ "$DRY_RUN" = true ]; then
        log_warning "DRY RUN - Skipping wait"
        return 0
    fi

    if kubectl wait --for=condition=ready pod -l "$label" -n "$NAMESPACE" --timeout="${timeout}s" 2>/dev/null; then
        log_success "$description ready"
        return 0
    else
        log_warning "Some $description may not be ready yet"
        kubectl get pods -n "$NAMESPACE" -l "$label"
        return 1
    fi
}

# Function to check prerequisites
check_prerequisites() {
    log_header "Checking Prerequisites"

    local errors=0

    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed"
        ((errors++))
    else
        log_success "kubectl is installed"
    fi

    # Check cluster connection
    log_step "Checking cluster connection..."
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        ((errors++))
    else
        CURRENT_CONTEXT=$(kubectl config current-context)
        log_success "Connected to cluster: $CURRENT_CONTEXT"
    fi

    # Verify production cluster (warning if context doesn't indicate production)
    if [[ ! "$CURRENT_CONTEXT" =~ "prod" ]]; then
        log_warning "Cluster context '$CURRENT_CONTEXT' doesn't contain 'prod'"
        log_warning "Please verify you're deploying to the correct cluster!"
    fi

    # Check required files
    local required_files=(
        "$SCRIPT_DIR/namespace.yaml"
        "$SCRIPT_DIR/configmap.yaml"
        "$SCRIPT_DIR/storage.yaml"
        "$SCRIPT_DIR/databases.yaml"
        "$SCRIPT_DIR/microservices.yaml"
        "$SCRIPT_DIR/monitoring.yaml"
    )

    for file in "${required_files[@]}"; do
        if [ ! -f "$file" ]; then
            log_error "Required file not found: $file"
            ((errors++))
        fi
    done

    if [ $errors -gt 0 ]; then
        log_error "Prerequisites check failed with $errors error(s)"
        exit 1
    fi

    log_success "All prerequisites met"
}

# Function to run security validation
run_security_validation() {
    log_header "Running Security Validation"

    if [ "$SKIP_SECURITY" = true ]; then
        log_warning "Security validation SKIPPED (--skip-security flag)"
        log_warning "THIS IS NOT RECOMMENDED FOR PRODUCTION"
        return 0
    fi

    # Run security validation script
    if [ -f "$SECURITY_DIR/scripts/validate-security.sh" ]; then
        log_step "Running security validation script..."
        chmod +x "$SECURITY_DIR/scripts/validate-security.sh"
        if ! "$SECURITY_DIR/scripts/validate-security.sh" production; then
            log_error "Security validation FAILED"
            log_error "Please fix security issues before deploying to production"
            exit 1
        fi
        log_success "Security validation passed"
    else
        log_warning "Security validation script not found"
    fi

    # Check for security scan script
    if [ -f "$PROJECT_ROOT/scripts/security_scan.py" ]; then
        log_step "Running security scan..."
        if python3 "$PROJECT_ROOT/scripts/security_scan.py" --fail-on HIGH 2>/dev/null; then
            log_success "Security scan passed"
        else
            log_error "Security scan found HIGH/CRITICAL issues"
            exit 1
        fi
    fi

    # Verify secrets are not templates
    log_step "Verifying secrets are not templates..."
    if grep -r "CHANGE_ME" "$SCRIPT_DIR/secrets.yaml" 2>/dev/null; then
        log_error "Secrets file contains CHANGE_ME placeholders!"
        log_error "Please configure real secrets before deploying"
        exit 1
    fi
}

# Function to perform rollback
perform_rollback() {
    log_header "Rolling Back Production Deployment"

    log_step "Rolling back deployments..."

    local deployments=(
        "api-gateway"
        "trading-engine"
        "portfolio-manager"
        "technical-analysis"
        "market-data-service"
        "bybit-connector"
        "ml-prediction-service"
        "notification-service"
        "risk-metrics-service"
        "sentiment-analysis-service"
    )

    for deployment in "${deployments[@]}"; do
        log_step "Rolling back $deployment..."
        kubectl rollout undo deployment/$deployment -n "$NAMESPACE" 2>/dev/null || true
    done

    log_step "Waiting for rollback to complete..."
    for deployment in "${deployments[@]}"; do
        kubectl rollout status deployment/$deployment -n "$NAMESPACE" --timeout=120s 2>/dev/null || true
    done

    log_success "Rollback completed"
    display_status
    exit 0
}

# Deployment functions
deploy_namespace() {
    log_header "Step 1: Creating Production Namespace"
    apply_manifest "$SCRIPT_DIR/namespace.yaml" "Namespace, ResourceQuota, and PriorityClasses"

    if [ "$DRY_RUN" = false ]; then
        sleep 3
    fi
}

deploy_security() {
    log_header "Step 2: Applying Security Configuration"

    if [ -f "$SECURITY_DIR/scripts/apply-security.sh" ]; then
        log_step "Applying security manifests..."
        chmod +x "$SECURITY_DIR/scripts/apply-security.sh"

        if [ "$DRY_RUN" = true ]; then
            "$SECURITY_DIR/scripts/apply-security.sh" production --dry-run
        else
            "$SECURITY_DIR/scripts/apply-security.sh" production
        fi
    else
        log_warning "Security script not found, applying basic security..."
        # Apply pod security standards
        if [ -f "$SECURITY_DIR/pod-security/pod-security-standards.yaml" ]; then
            apply_manifest "$SECURITY_DIR/pod-security/pod-security-standards.yaml" "Pod Security Standards"
        fi
        # Apply network policies
        if [ -f "$SECURITY_DIR/network-policies/default-deny.yaml" ]; then
            apply_manifest "$SECURITY_DIR/network-policies/default-deny.yaml" "Default Deny Network Policies"
        fi
        # Apply RBAC
        if [ -f "$SECURITY_DIR/rbac/service-accounts.yaml" ]; then
            apply_manifest "$SECURITY_DIR/rbac/service-accounts.yaml" "Service Accounts"
        fi
    fi
}

deploy_configmaps() {
    log_header "Step 3: Deploying ConfigMaps"
    apply_manifest "$SCRIPT_DIR/configmap.yaml" "ConfigMaps"
}

deploy_secrets() {
    log_header "Step 4: Deploying Secrets"

    if [ "$SKIP_SECRETS" = true ]; then
        log_warning "Secrets deployment SKIPPED (--skip-secrets flag)"
        log_info "Assuming secrets are managed by External Secrets Operator"
        return 0
    fi

    if [ -f "$SCRIPT_DIR/secrets.yaml" ]; then
        apply_manifest "$SCRIPT_DIR/secrets.yaml" "Secrets"
    else
        log_warning "secrets.yaml not found"
        log_info "Copy secrets-template.yaml to secrets.yaml and configure real values"
    fi
}

deploy_storage() {
    log_header "Step 5: Creating Persistent Volume Claims"
    apply_manifest "$SCRIPT_DIR/storage.yaml" "PVCs"

    if [ "$DRY_RUN" = false ]; then
        log_step "Waiting for PVCs to be created..."
        sleep 10
        kubectl get pvc -n "$NAMESPACE" --no-headers 2>/dev/null | while read line; do
            pvc_name=$(echo "$line" | awk '{print $1}')
            status=$(echo "$line" | awk '{print $2}')
            if [ "$status" = "Bound" ]; then
                log_success "PVC $pvc_name is bound"
            else
                log_warning "PVC $pvc_name status: $status"
            fi
        done
    fi
}

deploy_databases() {
    log_header "Step 6: Deploying Databases"

    if [ "$SKIP_DATABASES" = true ]; then
        log_warning "Database deployment SKIPPED (--skip-databases flag)"
        return 0
    fi

    apply_manifest "$SCRIPT_DIR/databases.yaml" "PostgreSQL, TimescaleDB, Redis, RabbitMQ"

    if [ "$DRY_RUN" = false ]; then
        log_step "Waiting for databases to be ready (this may take 2-3 minutes)..."
        sleep 30
        wait_for_pods "database=postgres" 180 "PostgreSQL" || true
        wait_for_pods "database=redis" 120 "Redis" || true
        wait_for_pods "component=messaging" 180 "RabbitMQ" || true
    fi
}

deploy_microservices() {
    log_header "Step 7: Deploying Microservices"
    apply_manifest "$SCRIPT_DIR/microservices.yaml" "All Microservices"

    if [ "$DRY_RUN" = false ]; then
        log_step "Waiting for microservices to start..."
        sleep 30

        log_step "Checking critical services..."
        wait_for_pods "service=api-gateway" 180 "API Gateway" || true
        wait_for_pods "service=trading-engine" 180 "Trading Engine" || true
        wait_for_pods "service=portfolio-manager" 120 "Portfolio Manager" || true
    fi
}

deploy_monitoring() {
    log_header "Step 8: Deploying Monitoring Stack"
    apply_manifest "$SCRIPT_DIR/monitoring.yaml" "Prometheus, Grafana, AlertManager"

    if [ "$DRY_RUN" = false ]; then
        wait_for_pods "service=prometheus" 120 "Prometheus" || true
        wait_for_pods "service=grafana" 120 "Grafana" || true
    fi
}

deploy_autoscaling() {
    log_header "Step 9: Configuring Autoscaling"

    if [ -f "$SCRIPT_DIR/autoscaling.yaml" ]; then
        apply_manifest "$SCRIPT_DIR/autoscaling.yaml" "Horizontal Pod Autoscalers"
    else
        log_info "Creating default HPAs..."

        if [ "$DRY_RUN" = false ]; then
            # API Gateway HPA
            kubectl autoscale deployment api-gateway -n "$NAMESPACE" \
                --cpu-percent=70 --min=3 --max=10 2>/dev/null || true

            # Trading Engine HPA
            kubectl autoscale deployment trading-engine -n "$NAMESPACE" \
                --cpu-percent=60 --min=3 --max=15 2>/dev/null || true

            log_success "Autoscaling configured"
        fi
    fi
}

# Function to display deployment status
display_status() {
    log_header "Deployment Status"

    echo -e "${YELLOW}Namespace:${NC}"
    kubectl get namespace "$NAMESPACE" 2>/dev/null || echo "Not found"

    echo ""
    echo -e "${YELLOW}Pods:${NC}"
    kubectl get pods -n "$NAMESPACE" -o wide 2>/dev/null || echo "None"

    echo ""
    echo -e "${YELLOW}Services:${NC}"
    kubectl get svc -n "$NAMESPACE" 2>/dev/null || echo "None"

    echo ""
    echo -e "${YELLOW}HPAs:${NC}"
    kubectl get hpa -n "$NAMESPACE" 2>/dev/null || echo "None"

    echo ""
    echo -e "${YELLOW}PVCs:${NC}"
    kubectl get pvc -n "$NAMESPACE" 2>/dev/null || echo "None"
}

# Function to run post-deployment validation
run_post_deployment_validation() {
    log_header "Running Post-Deployment Validation"

    if [ "$DRY_RUN" = true ]; then
        log_warning "DRY RUN - Skipping validation"
        return 0
    fi

    local errors=0

    # Check all critical deployments
    log_step "Checking deployment health..."
    local deployments=(
        "api-gateway"
        "trading-engine"
        "portfolio-manager"
        "bybit-connector"
    )

    for deployment in "${deployments[@]}"; do
        if kubectl get deployment "$deployment" -n "$NAMESPACE" &>/dev/null; then
            ready=$(kubectl get deployment "$deployment" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
            desired=$(kubectl get deployment "$deployment" -n "$NAMESPACE" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "0")

            if [ "$ready" -ge "$desired" ] && [ "$ready" -gt "0" ]; then
                log_success "$deployment: $ready/$desired replicas ready"
            else
                log_warning "$deployment: $ready/$desired replicas ready"
            fi
        else
            log_error "$deployment not found"
            ((errors++))
        fi
    done

    # Check health endpoints
    log_step "Checking service health endpoints..."
    local api_pod=$(kubectl get pods -n "$NAMESPACE" -l service=api-gateway -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [ -n "$api_pod" ]; then
        if kubectl exec -n "$NAMESPACE" "$api_pod" -- curl -s http://localhost:8000/health 2>/dev/null | grep -q "healthy"; then
            log_success "API Gateway health check passed"
        else
            log_warning "API Gateway health check inconclusive"
        fi
    fi

    if [ $errors -gt 0 ]; then
        log_error "Post-deployment validation found $errors error(s)"
        return 1
    fi

    log_success "Post-deployment validation passed"
}

# Display summary and next steps
display_summary() {
    log_header "Production Deployment Complete!"

    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}DRY RUN COMPLETE - No changes were applied${NC}"
        return 0
    fi

    echo -e "${GREEN}The crypto trading bot has been deployed to production.${NC}"
    echo ""
    echo -e "${YELLOW}Important Next Steps:${NC}"
    echo ""
    echo "1. Verify all pods are running:"
    echo "   ${GREEN}kubectl get pods -n $NAMESPACE${NC}"
    echo ""
    echo "2. Check service health:"
    echo "   ${GREEN}kubectl exec -it \$(kubectl get pod -n $NAMESPACE -l service=api-gateway -o jsonpath='{.items[0].metadata.name}') -n $NAMESPACE -- curl http://localhost:8000/health${NC}"
    echo ""
    echo "3. Access Grafana dashboard:"
    echo "   ${GREEN}kubectl port-forward -n $NAMESPACE svc/grafana-service 3000:3000${NC}"
    echo "   Then open: http://localhost:3000"
    echo ""
    echo "4. View API Gateway:"
    echo "   ${GREEN}kubectl port-forward -n $NAMESPACE svc/api-gateway-service 8000:8000${NC}"
    echo "   Then open: http://localhost:8000/docs"
    echo ""
    echo "5. Monitor trading engine logs:"
    echo "   ${GREEN}kubectl logs -f deployment/trading-engine -n $NAMESPACE${NC}"
    echo ""
    echo "6. Check alerting:"
    echo "   ${GREEN}kubectl port-forward -n $NAMESPACE svc/alertmanager-service 9093:9093${NC}"
    echo ""
    echo -e "${RED}CRITICAL REMINDERS:${NC}"
    echo "- Verify emergency stop mechanism is working"
    echo "- Monitor initial trades closely"
    echo "- Have rollback plan ready: ./deploy-production.sh --rollback"
    echo "- Review rate limits on exchange API"
}

# Main deployment sequence
main() {
    log_header "PRODUCTION DEPLOYMENT - Crypto Trading Bot"
    echo -e "Namespace: ${YELLOW}$NAMESPACE${NC}"
    echo -e "Dry Run: ${YELLOW}$DRY_RUN${NC}"
    echo -e "Skip Secrets: ${YELLOW}$SKIP_SECRETS${NC}"
    echo -e "Skip Security: ${YELLOW}$SKIP_SECURITY${NC}"
    echo ""

    # Handle rollback
    if [ "$ROLLBACK" = true ]; then
        perform_rollback
    fi

    # Check prerequisites
    check_prerequisites

    # Run security validation
    run_security_validation

    # Confirmation prompt
    if [ "$FORCE" = false ] && [ "$DRY_RUN" = false ]; then
        echo ""
        echo -e "${RED}========================================${NC}"
        echo -e "${RED}WARNING: PRODUCTION DEPLOYMENT${NC}"
        echo -e "${RED}========================================${NC}"
        echo ""
        echo "You are about to deploy to PRODUCTION with LIVE trading capabilities."
        echo "This will affect real funds if trading is enabled."
        echo ""
        read -p "Type 'DEPLOY PRODUCTION' to confirm: " -r
        if [[ "$REPLY" != "DEPLOY PRODUCTION" ]]; then
            echo "Deployment cancelled"
            exit 0
        fi
    fi

    # Record deployment start
    DEPLOY_START=$(date +%s)

    # Deploy in order
    deploy_namespace
    deploy_security
    deploy_configmaps
    deploy_secrets
    deploy_storage
    deploy_databases
    deploy_microservices
    deploy_monitoring
    deploy_autoscaling

    # Post-deployment validation
    run_post_deployment_validation

    # Display status
    display_status

    # Calculate deployment time
    DEPLOY_END=$(date +%s)
    DEPLOY_TIME=$((DEPLOY_END - DEPLOY_START))

    log_info "Deployment completed in ${DEPLOY_TIME} seconds"

    # Display summary
    display_summary
}

# Run main function
main
