#!/bin/bash
#
# Docker Infrastructure Verification Script
# Verifies all Docker components are in place
#

echo "========================================="
echo "  Docker Infrastructure Verification"
echo "========================================="
echo ""

ERRORS=0
WARNINGS=0

# Check Dockerfiles
echo "Checking Dockerfiles..."
SERVICES=(
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

for service in "${SERVICES[@]}"; do
    dockerfile="./services/$service/Dockerfile"
    if [ -f "$dockerfile" ]; then
        # Check for multi-stage build
        if grep -q "FROM.*as builder" "$dockerfile"; then
            echo "✓ $service - Multi-stage Dockerfile found"
        else
            echo "⚠ $service - Dockerfile exists but not multi-stage"
            ((WARNINGS++))
        fi
    else
        echo "✗ $service - Dockerfile missing"
        ((ERRORS++))
    fi
done

echo ""
echo "Checking Docker Compose files..."

# Check docker-compose files
if [ -f "docker-compose.yml" ]; then
    echo "✓ docker-compose.yml exists"
else
    echo "✗ docker-compose.yml missing"
    ((ERRORS++))
fi

if [ -f "docker-compose.prod.yml" ]; then
    echo "✓ docker-compose.prod.yml exists"
else
    echo "✗ docker-compose.prod.yml missing"
    ((ERRORS++))
fi

echo ""
echo "Checking build scripts..."

# Check scripts
if [ -f "build-all.sh" ] && [ -x "build-all.sh" ]; then
    echo "✓ build-all.sh exists and is executable"
else
    echo "✗ build-all.sh missing or not executable"
    ((ERRORS++))
fi

if [ -f "docker-dev.sh" ] && [ -x "docker-dev.sh" ]; then
    echo "✓ docker-dev.sh exists and is executable"
else
    echo "✗ docker-dev.sh missing or not executable"
    ((ERRORS++))
fi

echo ""
echo "Checking configuration files..."

# Check config files
if [ -f ".dockerignore" ]; then
    echo "✓ .dockerignore exists"
else
    echo "⚠ .dockerignore missing"
    ((WARNINGS++))
fi

if [ -f ".env.production.example" ]; then
    echo "✓ .env.production.example exists"
else
    echo "⚠ .env.production.example missing"
    ((WARNINGS++))
fi

echo ""
echo "Checking documentation..."

if [ -f "DOCKER_INFRASTRUCTURE_COMPLETE.md" ]; then
    echo "✓ DOCKER_INFRASTRUCTURE_COMPLETE.md exists"
else
    echo "⚠ DOCKER_INFRASTRUCTURE_COMPLETE.md missing"
    ((WARNINGS++))
fi

if [ -f "DOCKER_QUICK_START.md" ]; then
    echo "✓ DOCKER_QUICK_START.md exists"
else
    echo "⚠ DOCKER_QUICK_START.md missing"
    ((WARNINGS++))
fi

echo ""
echo "========================================="
echo "  Verification Summary"
echo "========================================="
echo "Services checked: ${#SERVICES[@]}"
echo "Errors: $ERRORS"
echo "Warnings: $WARNINGS"
echo ""

if [ $ERRORS -eq 0 ]; then
    echo "✓ All critical components verified!"
    echo ""
    echo "Next steps:"
    echo "1. Review .env.production.example"
    echo "2. Run: ./build-all.sh"
    echo "3. Run: ./docker-dev.sh start -d"
    echo "4. Run: ./docker-dev.sh health"
    exit 0
else
    echo "✗ Verification failed with $ERRORS errors"
    exit 1
fi
