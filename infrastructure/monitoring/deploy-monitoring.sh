#!/bin/bash
# =============================================================================
# Monitoring Deployment Script
# Crypto Trading Bot - Staging Environment
# Version: 1.0.0
# =============================================================================
#
# This script deploys and configures:
# - Prometheus ServiceMonitors
# - Prometheus AlertRules
# - Grafana Dashboards
# - AlertManager Configuration
#
# Usage:
#   ./deploy-monitoring.sh [--namespace NAMESPACE] [--dry-run]
#
# =============================================================================

set -euo pipefail

# Configuration
NAMESPACE="${NAMESPACE:-crypto-bot-staging}"
MONITORING_NAMESPACE="${MONITORING_NAMESPACE:-monitoring}"
DRY_RUN="${DRY_RUN:-false}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_MONITORING_DIR="${SCRIPT_DIR}/../kubernetes/monitoring"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        --monitoring-namespace)
            MONITORING_NAMESPACE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN="true"
            shift
            ;;
        --help)
            echo "Usage: $0 [--namespace NAMESPACE] [--monitoring-namespace NAMESPACE] [--dry-run]"
            echo ""
            echo "Options:"
            echo "  --namespace            Target namespace for trading services (default: crypto-bot-staging)"
            echo "  --monitoring-namespace Namespace for monitoring stack (default: monitoring)"
            echo "  --dry-run             Print what would be done without making changes"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Kubectl apply wrapper
kubectl_apply() {
    local file="$1"
    if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "[DRY-RUN] Would apply: $file"
        kubectl apply --dry-run=client -f "$file"
    else
        kubectl apply -f "$file"
    fi
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed"
        exit 1
    fi

    # Check cluster connection
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi

    # Check namespace exists
    if ! kubectl get namespace "${NAMESPACE}" &> /dev/null; then
        log_warn "Namespace ${NAMESPACE} does not exist. Creating..."
        if [[ "${DRY_RUN}" != "true" ]]; then
            kubectl create namespace "${NAMESPACE}"
        fi
    fi

    # Check Prometheus Operator CRDs
    if ! kubectl get crd servicemonitors.monitoring.coreos.com &> /dev/null; then
        log_warn "Prometheus Operator CRDs not found. ServiceMonitors may not work."
    fi

    log_success "Prerequisites check completed"
}

# Deploy ServiceMonitors
deploy_servicemonitors() {
    log_info "Deploying ServiceMonitors..."

    local sm_dir="${K8S_MONITORING_DIR}/servicemonitors"

    if [[ -d "$sm_dir" ]]; then
        for file in "$sm_dir"/*.yaml; do
            if [[ -f "$file" ]]; then
                log_info "Applying ServiceMonitor: $(basename "$file")"
                kubectl_apply "$file"
            fi
        done
        log_success "ServiceMonitors deployed"
    else
        log_warn "ServiceMonitors directory not found: $sm_dir"
    fi
}

# Deploy Prometheus Rules
deploy_prometheus_rules() {
    log_info "Deploying Prometheus alert rules..."

    local rules_dir="${SCRIPT_DIR}/prometheus/alerts"

    # Create ConfigMap from alert rules
    if [[ -d "$rules_dir" ]]; then
        if [[ "${DRY_RUN}" == "true" ]]; then
            log_info "[DRY-RUN] Would create ConfigMap from alert rules"
        else
            kubectl create configmap prometheus-alerts \
                --namespace="${MONITORING_NAMESPACE}" \
                --from-file="$rules_dir" \
                --dry-run=client -o yaml | kubectl apply -f -
        fi
        log_success "Prometheus alert rules deployed"
    else
        log_warn "Alert rules directory not found: $rules_dir"
    fi

    # Apply PrometheusRule CRDs if they exist
    local prom_rules_dir="${K8S_MONITORING_DIR}/prometheus-rules"
    if [[ -d "$prom_rules_dir" ]]; then
        for file in "$prom_rules_dir"/*.yaml; do
            if [[ -f "$file" ]]; then
                log_info "Applying PrometheusRule: $(basename "$file")"
                kubectl_apply "$file"
            fi
        done
    fi
}

# Deploy Grafana Dashboards
deploy_grafana_dashboards() {
    log_info "Deploying Grafana dashboards..."

    local dashboards_dir="${SCRIPT_DIR}/grafana/dashboards"

    if [[ -d "$dashboards_dir" ]]; then
        # Create ConfigMap from dashboards
        if [[ "${DRY_RUN}" == "true" ]]; then
            log_info "[DRY-RUN] Would create ConfigMap from Grafana dashboards"
        else
            # Create individual ConfigMaps for each dashboard
            for file in "$dashboards_dir"/*.json; do
                if [[ -f "$file" ]]; then
                    local dashboard_name=$(basename "$file" .json | tr '[:upper:]' '[:lower:]' | sed 's/_/-/g')
                    log_info "Creating dashboard ConfigMap: grafana-dashboard-${dashboard_name}"

                    kubectl create configmap "grafana-dashboard-${dashboard_name}" \
                        --namespace="${MONITORING_NAMESPACE}" \
                        --from-file="$(basename "$file")=$file" \
                        --dry-run=client -o yaml | \
                    kubectl label --local -f - grafana_dashboard=1 -o yaml | \
                    kubectl apply -f -
                fi
            done
        fi
        log_success "Grafana dashboards deployed"
    else
        log_warn "Dashboards directory not found: $dashboards_dir"
    fi
}

# Deploy AlertManager Configuration
deploy_alertmanager_config() {
    log_info "Deploying AlertManager configuration..."

    local alertmanager_config="${SCRIPT_DIR}/alertmanager/alertmanager.yml"

    if [[ -f "$alertmanager_config" ]]; then
        if [[ "${DRY_RUN}" == "true" ]]; then
            log_info "[DRY-RUN] Would create Secret from AlertManager config"
        else
            kubectl create secret generic alertmanager-config \
                --namespace="${MONITORING_NAMESPACE}" \
                --from-file=alertmanager.yml="$alertmanager_config" \
                --dry-run=client -o yaml | kubectl apply -f -
        fi
        log_success "AlertManager configuration deployed"
    else
        log_warn "AlertManager config not found: $alertmanager_config"
    fi

    # Deploy AlertManager templates
    local templates_dir="${SCRIPT_DIR}/alertmanager/templates"
    if [[ -d "$templates_dir" ]]; then
        if [[ "${DRY_RUN}" == "true" ]]; then
            log_info "[DRY-RUN] Would create ConfigMap from AlertManager templates"
        else
            kubectl create configmap alertmanager-templates \
                --namespace="${MONITORING_NAMESPACE}" \
                --from-file="$templates_dir" \
                --dry-run=client -o yaml | kubectl apply -f -
        fi
        log_success "AlertManager templates deployed"
    fi
}

# Reload Prometheus configuration
reload_prometheus() {
    log_info "Reloading Prometheus configuration..."

    if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "[DRY-RUN] Would trigger Prometheus reload"
        return
    fi

    # Find Prometheus pod and trigger reload
    local prometheus_pod=$(kubectl get pods -n "${MONITORING_NAMESPACE}" -l app=prometheus -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [[ -n "$prometheus_pod" ]]; then
        kubectl exec -n "${MONITORING_NAMESPACE}" "$prometheus_pod" -- /bin/sh -c \
            "kill -HUP 1 || wget -q --post-data '' -O - http://localhost:9090/-/reload" 2>/dev/null || \
            log_warn "Could not reload Prometheus. Manual reload may be required."
        log_success "Prometheus reload triggered"
    else
        log_warn "Prometheus pod not found. Manual reload required."
    fi
}

# Reload AlertManager configuration
reload_alertmanager() {
    log_info "Reloading AlertManager configuration..."

    if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "[DRY-RUN] Would trigger AlertManager reload"
        return
    fi

    # Find AlertManager pod and trigger reload
    local alertmanager_pod=$(kubectl get pods -n "${MONITORING_NAMESPACE}" -l app=alertmanager -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [[ -n "$alertmanager_pod" ]]; then
        kubectl exec -n "${MONITORING_NAMESPACE}" "$alertmanager_pod" -- /bin/sh -c \
            "kill -HUP 1 || wget -q --post-data '' -O - http://localhost:9093/-/reload" 2>/dev/null || \
            log_warn "Could not reload AlertManager. Manual reload may be required."
        log_success "AlertManager reload triggered"
    else
        log_warn "AlertManager pod not found. Manual reload required."
    fi
}

# Verify deployment
verify_deployment() {
    log_info "Verifying deployment..."

    if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "[DRY-RUN] Would verify deployment"
        return
    fi

    # Check ServiceMonitors
    local sm_count=$(kubectl get servicemonitors -n "${NAMESPACE}" -o name 2>/dev/null | wc -l || echo "0")
    log_info "ServiceMonitors deployed: $sm_count"

    # Check ConfigMaps
    local dashboard_count=$(kubectl get configmaps -n "${MONITORING_NAMESPACE}" -l grafana_dashboard=1 -o name 2>/dev/null | wc -l || echo "0")
    log_info "Grafana dashboard ConfigMaps: $dashboard_count"

    # Check Prometheus targets
    log_info "Checking Prometheus targets..."
    local prometheus_pod=$(kubectl get pods -n "${MONITORING_NAMESPACE}" -l app=prometheus -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

    if [[ -n "$prometheus_pod" ]]; then
        kubectl exec -n "${MONITORING_NAMESPACE}" "$prometheus_pod" -- wget -q -O - 'http://localhost:9090/api/v1/targets' 2>/dev/null | \
            jq -r '.data.activeTargets | length' || log_warn "Could not query Prometheus targets"
    fi

    log_success "Deployment verification completed"
}

# Main execution
main() {
    echo "=========================================="
    echo "Monitoring Deployment Script"
    echo "=========================================="
    echo "Namespace: ${NAMESPACE}"
    echo "Monitoring Namespace: ${MONITORING_NAMESPACE}"
    echo "Dry Run: ${DRY_RUN}"
    echo "=========================================="
    echo ""

    check_prerequisites
    echo ""

    deploy_servicemonitors
    echo ""

    deploy_prometheus_rules
    echo ""

    deploy_grafana_dashboards
    echo ""

    deploy_alertmanager_config
    echo ""

    if [[ "${DRY_RUN}" != "true" ]]; then
        reload_prometheus
        echo ""

        reload_alertmanager
        echo ""
    fi

    verify_deployment
    echo ""

    echo "=========================================="
    if [[ "${DRY_RUN}" == "true" ]]; then
        log_info "DRY RUN completed. No changes were made."
    else
        log_success "Monitoring deployment completed successfully!"
    fi
    echo "=========================================="
    echo ""
    echo "Next steps:"
    echo "1. Access Grafana at: kubectl port-forward -n ${MONITORING_NAMESPACE} svc/grafana 3000:3000"
    echo "2. Access Prometheus at: kubectl port-forward -n ${MONITORING_NAMESPACE} svc/prometheus 9090:9090"
    echo "3. Access AlertManager at: kubectl port-forward -n ${MONITORING_NAMESPACE} svc/alertmanager 9093:9093"
    echo ""
    echo "To test alerts:"
    echo "  ./scripts/test_alerts.sh"
}

main "$@"
