#!/bin/bash
# Delete all Kubernetes resources for Crypto Trading Bot
# Version: 1.0
# Created: 2025-11-23
#
# Usage:
#   ./delete-all.sh [--force]
#
# Options:
#   --force: Skip confirmation prompt
#
# WARNING: This will delete ALL resources including data!

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

FORCE=false
if [ "$1" = "--force" ]; then
    FORCE=true
fi

echo -e "${RED}========================================${NC}"
echo -e "${RED}DANGER: Delete All Resources${NC}"
echo -e "${RED}========================================${NC}"
echo ""
echo -e "${RED}This will DELETE ALL crypto-bot resources including:${NC}"
echo "  - All deployments and pods"
echo "  - All services"
echo "  - All persistent volumes and data"
echo "  - All secrets and configmaps"
echo "  - The entire crypto-bot namespace"
echo ""

# Check if namespace exists
if ! kubectl get namespace crypto-bot &> /dev/null; then
    echo -e "${YELLOW}Namespace 'crypto-bot' does not exist. Nothing to delete.${NC}"
    exit 0
fi

# Show what will be deleted
echo -e "${YELLOW}Current resources in crypto-bot namespace:${NC}"
echo ""
kubectl get all -n crypto-bot
echo ""
kubectl get pvc -n crypto-bot
echo ""

# Confirmation
if [ "$FORCE" = false ]; then
    echo -e "${RED}WARNING: This action cannot be undone!${NC}"
    read -p "Type 'DELETE' to confirm deletion: " -r
    if [ "$REPLY" != "DELETE" ]; then
        echo "Deletion cancelled"
        exit 0
    fi
fi

echo ""
echo -e "${YELLOW}Starting deletion process...${NC}"
echo ""

# Delete in reverse order of creation
delete_resource() {
    local resource=$1
    local description=$2

    echo -e "${YELLOW}Deleting ${description}...${NC}"
    kubectl delete -f "$resource" --ignore-not-found=true --wait=false
    echo -e "${GREEN}✓ ${description} deletion initiated${NC}"
}

# 1. Delete autoscaling
delete_resource "autoscaling/" "Horizontal Pod Autoscalers"

# 2. Delete monitoring
delete_resource "monitoring/" "Monitoring stack"

# 3. Delete ingress
delete_resource "ingress/" "Ingress controllers"

# 4. Delete services
delete_resource "services/" "Microservices"

# 5. Delete databases
delete_resource "databases/" "Database services"

# 6. Delete secrets and configmaps
delete_resource "secrets/" "Secrets"
delete_resource "configmaps/" "ConfigMaps"

# 7. Delete storage (this deletes all data!)
echo -e "${RED}Deleting persistent volumes (ALL DATA WILL BE LOST)...${NC}"
delete_resource "storage/" "Persistent Volume Claims"

# 8. Delete namespace (this ensures everything is gone)
echo -e "${YELLOW}Deleting namespace...${NC}"
kubectl delete namespace crypto-bot --wait=false

echo ""
echo -e "${YELLOW}Waiting for resources to be terminated (this may take a while)...${NC}"

# Wait for namespace deletion
timeout=300  # 5 minutes
elapsed=0
while kubectl get namespace crypto-bot &> /dev/null; do
    if [ $elapsed -ge $timeout ]; then
        echo -e "${RED}Timeout waiting for namespace deletion${NC}"
        echo "Some resources may still be terminating"
        exit 1
    fi
    echo -n "."
    sleep 5
    elapsed=$((elapsed + 5))
done

echo ""
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deletion Complete${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "All crypto-bot resources have been deleted"
echo ""
