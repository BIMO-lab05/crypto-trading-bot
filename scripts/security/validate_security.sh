#!/bin/bash
# Security Validation Script
# Validates that security hardening was successful
# Run from project root: ./scripts/security/validate_security.sh

set -e

echo "==================================================================="
echo "   SECURITY VALIDATION - CRYPTO TRADING BOT"
echo "==================================================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0

# Check function
check() {
    local test_name="$1"
    local command="$2"
    local expected="$3"

    echo -n "Testing: $test_name ... "

    if eval "$command"; then
        echo -e "${GREEN}✅ PASS${NC}"
        ((PASS++))
    else
        echo -e "${RED}❌ FAIL${NC}"
        echo -e "${RED}   Expected: $expected${NC}"
        ((FAIL++))
    fi
}

warn_check() {
    local test_name="$1"
    local command="$2"

    echo -n "Testing: $test_name ... "

    if eval "$command"; then
        echo -e "${GREEN}✅ PASS${NC}"
        ((PASS++))
    else
        echo -e "${YELLOW}⚠️  WARNING${NC}"
        ((WARN++))
    fi
}

echo "=== CRITICAL SECURITY CHECKS ==="
echo ""

# CHECK 1: PostgreSQL not exposed on host
check \
    "PostgreSQL not exposed on 0.0.0.0:5432" \
    '! docker ps | grep crypto-bot-postgres | grep -q "0.0.0.0:5432"' \
    "PostgreSQL should not be accessible from host network"

# CHECK 2: TimescaleDB not exposed on host
check \
    "TimescaleDB not exposed on 0.0.0.0:5433" \
    '! docker ps | grep crypto-bot-timescaledb | grep -q "0.0.0.0:5433"' \
    "TimescaleDB should not be accessible from host network"

# CHECK 3: Redis not exposed on host
check \
    "Redis not exposed on 0.0.0.0:6379" \
    '! docker ps | grep crypto-bot-redis | grep -q "0.0.0.0:6379"' \
    "Redis should not be accessible from host network"

# CHECK 4: Redis requires authentication
check \
    "Redis requires authentication" \
    'docker exec crypto-bot-redis redis-cli PING 2>&1 | grep -q "NOAUTH"' \
    "Redis should require password"

# CHECK 5: Redis password works
check \
    "Redis accepts correct password" \
    'docker exec crypto-bot-redis redis-cli -a "redis_dev_password" PING 2>&1 | grep -q "PONG"' \
    "Redis should accept correct password"

echo ""
echo "=== SERVICE CONFIGURATION CHECKS ==="
echo ""

# CHECK 6: All services have REDIS_PASSWORD in .env
MISSING_REDIS=0
for env_file in services/*/.env; do
    if [ -f "$env_file" ]; then
        if ! grep -q "REDIS_PASSWORD" "$env_file"; then
            echo -e "${RED}❌ Missing REDIS_PASSWORD in: $env_file${NC}"
            ((MISSING_REDIS++))
        fi
    fi
done

if [ $MISSING_REDIS -eq 0 ]; then
    echo -e "All services have REDIS_PASSWORD ... ${GREEN}✅ PASS${NC}"
    ((PASS++))
else
    echo -e "All services have REDIS_PASSWORD ... ${RED}❌ FAIL ($MISSING_REDIS missing)${NC}"
    ((FAIL++))
fi

echo ""
echo "=== HIGH PRIORITY CHECKS ==="
echo ""

# CHECK 7: RabbitMQ management bound to localhost
check \
    "RabbitMQ management on localhost only" \
    'docker ps | grep crypto-bot-rabbitmq | grep -q "127.0.0.1:15672"' \
    "RabbitMQ management should be 127.0.0.1:15672"

# CHECK 8: RabbitMQ requires authentication
check \
    "RabbitMQ has authentication configured" \
    'docker exec crypto-bot-rabbitmq rabbitmqctl list_users 2>&1 | grep -q "cryptobot"' \
    "RabbitMQ should have user cryptobot"

echo ""
echo "=== MONITORING SERVICE CHECKS ==="
echo ""

# CHECK 9: Prometheus bound to localhost
warn_check \
    "Prometheus on localhost only" \
    'docker ps | grep crypto-bot-prometheus | grep -q "127.0.0.1:9090"'

# CHECK 10: Grafana bound to localhost
warn_check \
    "Grafana on localhost only" \
    'docker ps | grep crypto-bot-grafana | grep -q "127.0.0.1:3001"'

echo ""
echo "=== DATABASE SECURITY CHECKS ==="
echo ""

# CHECK 11: PostgreSQL has multiple users (not just superuser)
warn_check \
    "PostgreSQL has limited privilege users" \
    'docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -c "\du" 2>&1 | grep -q "cryptobot_app"'

# CHECK 12: TimescaleDB has multiple users
warn_check \
    "TimescaleDB has limited privilege users" \
    'docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data -c "\du" 2>&1 | grep -q "cryptobot_app"'

echo ""
echo "=== NETWORK ISOLATION CHECKS ==="
echo ""

# CHECK 13: Containers are on crypto-bot-network
CONTAINERS_ON_NETWORK=$(docker network inspect crypto-bot-network --format '{{range .Containers}}{{.Name}} {{end}}' 2>/dev/null | wc -w)
if [ $CONTAINERS_ON_NETWORK -gt 10 ]; then
    echo -e "Containers on crypto-bot-network ($CONTAINERS_ON_NETWORK) ... ${GREEN}✅ PASS${NC}"
    ((PASS++))
else
    echo -e "Containers on crypto-bot-network ($CONTAINERS_ON_NETWORK) ... ${YELLOW}⚠️  WARNING (expected >10)${NC}"
    ((WARN++))
fi

echo ""
echo "=== FILE SECURITY CHECKS ==="
echo ""

# CHECK 14: .env files in .gitignore
check \
    ".env files in .gitignore" \
    'grep -q "^\.env$" .gitignore || grep -q "^\.env" .gitignore' \
    ".env should be in .gitignore"

# CHECK 15: .secrets directory in .gitignore
check \
    ".secrets/ in .gitignore" \
    'grep -q "\.secrets" .gitignore' \
    ".secrets/ should be in .gitignore"

# CHECK 16: .secrets directory exists and protected
if [ -d ".secrets" ]; then
    SECRETS_PERM=$(stat -c "%a" .secrets 2>/dev/null || stat -f "%A" .secrets 2>/dev/null)
    if [ "$SECRETS_PERM" = "700" ]; then
        echo -e ".secrets directory permissions (700) ... ${GREEN}✅ PASS${NC}"
        ((PASS++))
    else
        echo -e ".secrets directory permissions ($SECRETS_PERM) ... ${YELLOW}⚠️  WARNING (should be 700)${NC}"
        ((WARN++))
    fi
else
    echo -e ".secrets directory exists ... ${YELLOW}⚠️  WARNING (not found)${NC}"
    ((WARN++))
fi

echo ""
echo "=== SERVICE HEALTH CHECKS ==="
echo ""

# CHECK 17: API Gateway is healthy
warn_check \
    "API Gateway health check" \
    'curl -sf http://localhost:8000/health | grep -q "healthy"'

# CHECK 18: Key services are running
REQUIRED_SERVICES=(
    "crypto-bot-api-gateway"
    "crypto-bot-postgres"
    "crypto-bot-redis"
    "crypto-bot-rabbitmq"
)

RUNNING_SERVICES=0
for service in "${REQUIRED_SERVICES[@]}"; do
    if docker ps --format '{{.Names}}' | grep -q "^$service$"; then
        ((RUNNING_SERVICES++))
    else
        echo -e "${RED}❌ Service not running: $service${NC}"
    fi
done

if [ $RUNNING_SERVICES -eq ${#REQUIRED_SERVICES[@]} ]; then
    echo -e "All critical services running (${RUNNING_SERVICES}/${#REQUIRED_SERVICES[@]}) ... ${GREEN}✅ PASS${NC}"
    ((PASS++))
else
    echo -e "All critical services running (${RUNNING_SERVICES}/${#REQUIRED_SERVICES[@]}) ... ${RED}❌ FAIL${NC}"
    ((FAIL++))
fi

echo ""
echo "=== EXPOSURE ANALYSIS ==="
echo ""

echo -e "${BLUE}Exposed ports on host:${NC}"
docker ps --format "table {{.Names}}\t{{.Ports}}" | grep "0.0.0.0" | while read line; do
    if echo "$line" | grep -q "api-gateway"; then
        echo -e "  ${GREEN}$line${NC} (Expected - public API)"
    elif echo "$line" | grep -q "127.0.0.1"; then
        echo -e "  ${YELLOW}$line${NC} (Localhost only - OK)"
    else
        echo -e "  ${RED}$line${NC} (⚠️ Consider restricting)"
    fi
done

echo ""
echo "==================================================================="
echo "   VALIDATION SUMMARY"
echo "==================================================================="
echo ""
echo -e "${GREEN}Passed:   $PASS${NC}"
echo -e "${RED}Failed:   $FAIL${NC}"
echo -e "${YELLOW}Warnings: $WARN${NC}"
echo ""

# Overall status
TOTAL=$((PASS + FAIL + WARN))
SCORE=$((PASS * 100 / TOTAL))

if [ $FAIL -eq 0 ]; then
    if [ $WARN -eq 0 ]; then
        echo -e "${GREEN}🎉 EXCELLENT! All security checks passed!${NC}"
        echo -e "${GREEN}Security Score: ${SCORE}%${NC}"
        exit 0
    else
        echo -e "${YELLOW}⚠️  GOOD! All critical checks passed, but there are warnings.${NC}"
        echo -e "${YELLOW}Security Score: ${SCORE}%${NC}"
        echo ""
        echo "Review warnings above and consider addressing them."
        exit 0
    fi
else
    echo -e "${RED}❌ SECURITY ISSUES FOUND!${NC}"
    echo -e "${RED}Security Score: ${SCORE}%${NC}"
    echo ""
    echo "Critical issues must be fixed before production deployment."
    echo ""
    echo "To fix issues:"
    echo "  1. Review failures above"
    echo "  2. Run: ./scripts/security/emergency_hardening.sh"
    echo "  3. Review: SECURITY_AUDIT_REPORT.md"
    exit 1
fi
