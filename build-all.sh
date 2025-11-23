#!/bin/bash
#
# Build All Docker Images Script
# Purpose: Build production-ready Docker images for all microservices
# Usage: ./build-all.sh [--no-cache] [--parallel] [--push]
#

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="crypto-trading-bot"
REGISTRY="${DOCKER_REGISTRY:-localhost:5000}"
VERSION="${VERSION:-latest}"

# Service list with their ports
declare -A SERVICES=(
    ["api-gateway"]="8000"
    ["trading-engine"]="8001"
    ["portfolio-manager"]="8002"
    ["technical-analysis"]="8003"
    ["bybit-connector"]="8004"
    ["market-data-service"]="8005"
    ["notification-service"]="8006"
    ["ml-prediction-service"]="8007"
    ["risk-metrics-service"]="8008"
    ["sentiment-analysis-service"]="8009"
)

# Parse command line arguments
NO_CACHE=""
PARALLEL=false
PUSH=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --no-cache)
            NO_CACHE="--no-cache"
            shift
            ;;
        --parallel)
            PARALLEL=true
            shift
            ;;
        --push)
            PUSH=true
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Function to build a single service
build_service() {
    local service=$1
    local port=$2
    local context_path="./services/${service}"
    local image_tag="${REGISTRY}/${PROJECT_NAME}/${service}:${VERSION}"

    echo -e "${BLUE}Building ${service} (port ${port})...${NC}"

    if [ ! -d "$context_path" ]; then
        echo -e "${RED}Error: Service directory not found: $context_path${NC}"
        return 1
    fi

    if [ ! -f "$context_path/Dockerfile" ]; then
        echo -e "${RED}Error: Dockerfile not found for $service${NC}"
        return 1
    fi

    # Build the image
    if docker build $NO_CACHE \
        -t "${PROJECT_NAME}/${service}:${VERSION}" \
        -t "${PROJECT_NAME}/${service}:latest" \
        -t "${image_tag}" \
        --label "service=${service}" \
        --label "port=${port}" \
        --label "version=${VERSION}" \
        --label "build-date=$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
        "$context_path"; then
        echo -e "${GREEN}Successfully built ${service}${NC}"

        # Push if requested
        if [ "$PUSH" = true ]; then
            echo -e "${BLUE}Pushing ${service}...${NC}"
            docker push "${image_tag}"
            echo -e "${GREEN}Successfully pushed ${service}${NC}"
        fi

        return 0
    else
        echo -e "${RED}Failed to build ${service}${NC}"
        return 1
    fi
}

# Function to build services in parallel
build_parallel() {
    local pids=()

    for service in "${!SERVICES[@]}"; do
        build_service "$service" "${SERVICES[$service]}" &
        pids+=($!)
    done

    # Wait for all builds to complete
    local failed=0
    for pid in "${pids[@]}"; do
        if ! wait $pid; then
            ((failed++))
        fi
    done

    return $failed
}

# Function to build services sequentially
build_sequential() {
    local failed=0

    for service in "${!SERVICES[@]}"; do
        if ! build_service "$service" "${SERVICES[$service]}"; then
            ((failed++))
        fi
    done

    return $failed
}

# Main execution
echo "========================================="
echo "  Crypto Trading Bot - Build All Images"
echo "========================================="
echo ""
echo "Project: $PROJECT_NAME"
echo "Version: $VERSION"
echo "Registry: $REGISTRY"
echo "No Cache: ${NO_CACHE:-false}"
echo "Parallel: $PARALLEL"
echo "Push: $PUSH"
echo ""
echo "Services to build: ${#SERVICES[@]}"
echo ""

# Start build
start_time=$(date +%s)

if [ "$PARALLEL" = true ]; then
    echo -e "${YELLOW}Building services in parallel...${NC}"
    build_parallel
    result=$?
else
    echo -e "${YELLOW}Building services sequentially...${NC}"
    build_sequential
    result=$?
fi

# Calculate elapsed time
end_time=$(date +%s)
elapsed=$((end_time - start_time))

echo ""
echo "========================================="
echo "  Build Summary"
echo "========================================="
echo "Total services: ${#SERVICES[@]}"
echo "Failed builds: $result"
echo "Elapsed time: ${elapsed}s"
echo ""

if [ $result -eq 0 ]; then
    echo -e "${GREEN}All images built successfully!${NC}"

    # Display image information
    echo ""
    echo "Built images:"
    docker images | grep "$PROJECT_NAME" | head -20

    exit 0
else
    echo -e "${RED}Some builds failed. Check the output above for details.${NC}"
    exit 1
fi
