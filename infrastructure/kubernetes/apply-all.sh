#!/bin/bash
# Apply all Kubernetes manifests for Crypto Trading Bot
# Version: 1.0
# Created: 2025-11-23
#
# Usage:
#   ./apply-all.sh [environment]
#
# Arguments:
#   environment: development|production (default: development)
#
# Examples:
#   ./apply-all.sh development
#   ./apply-all.sh production

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default environment
ENVIRONMENT="${1:-development}"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Crypto Trading Bot - Kubernetes Deployment${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Environment: ${YELLOW}${ENVIRONMENT}${NC}"
echo ""

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(development|production)$ ]]; then
    echo -e "${RED}Error: Invalid environment '${ENVIRONMENT}'${NC}"
    echo "Valid options: development, production"
    exit 1
fi

# Check if kubectl is installed
if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}Error: kubectl is not installed${NC}"
    exit 1
fi

# Check if kustomize is installed
if ! command -v kustomize &> /dev/null; then
    echo -e "${YELLOW}Warning: kustomize not found, using kubectl kustomize${NC}"
    KUSTOMIZE_CMD="kubectl kustomize"
else
    KUSTOMIZE_CMD="kustomize build"
fi

# Check cluster connection
echo -e "${YELLOW}Checking cluster connection...${NC}"
if ! kubectl cluster-info &> /dev/null; then
    echo -e "${RED}Error: Cannot connect to Kubernetes cluster${NC}"
    echo "Please configure kubectl to connect to your cluster"
    exit 1
fi

CURRENT_CONTEXT=$(kubectl config current-context)
echo -e "${GREEN}Connected to cluster: ${CURRENT_CONTEXT}${NC}"
echo ""

# Confirmation for production
if [ "$ENVIRONMENT" = "production" ]; then
    echo -e "${RED}WARNING: You are about to deploy to PRODUCTION!${NC}"
    echo -e "${YELLOW}Current context: ${CURRENT_CONTEXT}${NC}"
    read -p "Are you sure you want to continue? (yes/no): " -r
    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        echo "Deployment cancelled"
        exit 0
    fi
fi

# Function to apply manifests in order
apply_in_order() {
    local resource_type=$1
    local description=$2

    echo -e "${YELLOW}Deploying ${description}...${NC}"

    # Apply based on resource type
    case $resource_type in
        "namespace")
            kubectl apply -f namespaces/
            ;;
        "storage")
            kubectl apply -f storage/
            ;;
        "configmaps")
            kubectl apply -f configmaps/
            ;;
        "secrets")
            echo -e "${YELLOW}Note: Using template secrets. Update with real values!${NC}"
            kubectl apply -f secrets/
            ;;
        "databases")
            kubectl apply -f databases/
            ;;
        "services")
            kubectl apply -f services/
            ;;
        "ingress")
            kubectl apply -f ingress/
            ;;
        "monitoring")
            kubectl apply -f monitoring/
            ;;
        "autoscaling")
            kubectl apply -f autoscaling/
            ;;
        *)
            echo -e "${RED}Unknown resource type: ${resource_type}${NC}"
            return 1
            ;;
    esac

    echo -e "${GREEN}✓ ${description} deployed${NC}"
    echo ""
}

# Deployment order (critical for dependencies)
echo -e "${GREEN}Starting deployment in dependency order...${NC}"
echo ""

# 1. Namespace first
apply_in_order "namespace" "Namespace"
sleep 2

# 2. ConfigMaps and Secrets
apply_in_order "configmaps" "ConfigMaps"
apply_in_order "secrets" "Secrets (templates)"
sleep 2

# 3. Storage
apply_in_order "storage" "Persistent Volume Claims"
sleep 5  # Wait for PVCs to be bound

# 4. Databases (critical dependencies)
apply_in_order "databases" "Database services"
echo -e "${YELLOW}Waiting for databases to be ready (60s)...${NC}"
sleep 60

# 5. Microservices
apply_in_order "services" "Microservices"
echo -e "${YELLOW}Waiting for services to start (30s)...${NC}"
sleep 30

# 6. Ingress
apply_in_order "ingress" "Ingress controllers"

# 7. Monitoring
apply_in_order "monitoring" "Monitoring stack"

# 8. Autoscaling
apply_in_order "autoscaling" "Horizontal Pod Autoscalers"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Summary${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Show deployment status
echo -e "${YELLOW}Namespaces:${NC}"
kubectl get namespaces | grep crypto-bot

echo ""
echo -e "${YELLOW}Persistent Volumes:${NC}"
kubectl get pvc -n crypto-bot

echo ""
echo -e "${YELLOW}Pods:${NC}"
kubectl get pods -n crypto-bot

echo ""
echo -e "${YELLOW}Services:${NC}"
kubectl get svc -n crypto-bot

echo ""
echo -e "${YELLOW}Ingress:${NC}"
kubectl get ingress -n crypto-bot

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Verify all pods are running: ${GREEN}kubectl get pods -n crypto-bot${NC}"
echo "2. Check logs: ${GREEN}kubectl logs -f <pod-name> -n crypto-bot${NC}"
echo "3. Access services: ${GREEN}kubectl port-forward -n crypto-bot svc/api-gateway-service 8000:8000${NC}"
echo "4. Monitor: ${GREEN}kubectl top pods -n crypto-bot${NC}"
echo ""
echo -e "${RED}IMPORTANT:${NC}"
echo "- Update secrets with real values before using in production"
echo "- Configure TLS certificates for ingress"
echo "- Set up backup and monitoring"
echo "- Review and adjust resource limits based on actual usage"
echo ""
