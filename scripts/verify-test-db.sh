#!/bin/bash
#
# Verify Test Database Infrastructure
# Purpose: Comprehensive health check and performance verification
# Usage: ./scripts/verify-test-db.sh
#

set -e

echo "=========================================="
echo "Test Database Verification"
echo "=========================================="
echo ""

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print success
print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

# Function to print error
print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Function to print warning
print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Track test results
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Function to run test
run_test() {
    local test_name="$1"
    local test_command="$2"

    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    if eval "$test_command" > /dev/null 2>&1; then
        print_success "$test_name"
        PASSED_TESTS=$((PASSED_TESTS + 1))
        return 0
    else
        print_error "$test_name"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return 1
    fi
}

echo "1. Container Status Checks"
echo "-------------------------------------------"

# Check if containers are running
run_test "PostgreSQL container running" \
    "docker ps --filter 'name=crypto-bot-test-postgres' --filter 'status=running' | grep -q postgres"

run_test "TimescaleDB container running" \
    "docker ps --filter 'name=crypto-bot-test-timescaledb' --filter 'status=running' | grep -q timescale"

run_test "Redis container running" \
    "docker ps --filter 'name=crypto-bot-test-redis' --filter 'status=running' | grep -q redis"

echo ""
echo "2. Health Status Checks"
echo "-------------------------------------------"

# Check health status
run_test "PostgreSQL is healthy" \
    "[ \$(docker inspect --format='{{.State.Health.Status}}' crypto-bot-test-postgres) = 'healthy' ]"

run_test "TimescaleDB is healthy" \
    "[ \$(docker inspect --format='{{.State.Health.Status}}' crypto-bot-test-timescaledb) = 'healthy' ]"

run_test "Redis is healthy" \
    "[ \$(docker inspect --format='{{.State.Health.Status}}' crypto-bot-test-redis) = 'healthy' ]"

echo ""
echo "3. Connection Tests"
echo "-------------------------------------------"

# Test database connections
run_test "PostgreSQL accepts connections" \
    "docker exec crypto-bot-test-postgres pg_isready -U cryptobot_test -d cryptobot_test"

run_test "TimescaleDB accepts connections" \
    "docker exec crypto-bot-test-timescaledb pg_isready -U cryptobot_test -d market_data_test"

run_test "Redis accepts connections" \
    "docker exec crypto-bot-test-redis redis-cli ping | grep -q PONG"

echo ""
echo "4. Database Functionality Tests"
echo "-------------------------------------------"

# Test PostgreSQL query execution
run_test "PostgreSQL can execute queries" \
    "docker exec crypto-bot-test-postgres psql -U cryptobot_test -d cryptobot_test -c 'SELECT 1;' | grep -q '1 row'"

# Test TimescaleDB query execution
run_test "TimescaleDB can execute queries" \
    "docker exec crypto-bot-test-timescaledb psql -U cryptobot_test -d market_data_test -c 'SELECT 1;' | grep -q '1 row'"

# Test Redis operations
run_test "Redis can SET/GET values" \
    "docker exec crypto-bot-test-redis redis-cli SET test_key test_value && docker exec crypto-bot-test-redis redis-cli GET test_key | grep -q test_value"

echo ""
echo "5. Port Accessibility Tests"
echo "-------------------------------------------"

# Check ports are accessible from host
run_test "PostgreSQL port 5434 accessible" \
    "timeout 2 bash -c '</dev/tcp/localhost/5434' 2>/dev/null"

run_test "TimescaleDB port 5435 accessible" \
    "timeout 2 bash -c '</dev/tcp/localhost/5435' 2>/dev/null"

run_test "Redis port 6380 accessible" \
    "timeout 2 bash -c '</dev/tcp/localhost/6380' 2>/dev/null"

echo ""
echo "6. Network Configuration Tests"
echo "-------------------------------------------"

# Check network exists
run_test "Test network exists" \
    "docker network inspect crypto-bot-test-network > /dev/null 2>&1"

# Check containers are on test network
run_test "PostgreSQL on test network" \
    "docker network inspect crypto-bot-test-network | grep -q crypto-bot-test-postgres"

run_test "TimescaleDB on test network" \
    "docker network inspect crypto-bot-test-network | grep -q crypto-bot-test-timescaledb"

run_test "Redis on test network" \
    "docker network inspect crypto-bot-test-network | grep -q crypto-bot-test-redis"

echo ""
echo "7. Configuration Verification"
echo "-------------------------------------------"

# Check tmpfs is configured
run_test "PostgreSQL using tmpfs" \
    "docker inspect crypto-bot-test-postgres --format='{{.HostConfig.Tmpfs}}' | grep -q '/var/lib/postgresql/data'"

run_test "TimescaleDB using tmpfs" \
    "docker inspect crypto-bot-test-timescaledb --format='{{.HostConfig.Tmpfs}}' | grep -q '/var/lib/postgresql/data'"

# Check restart policy
run_test "PostgreSQL has 'no' restart policy" \
    "[ \$(docker inspect crypto-bot-test-postgres --format='{{.HostConfig.RestartPolicy.Name}}') = 'no' ]"

echo ""
echo "8. Performance Metrics"
echo "-------------------------------------------"

# Measure query performance
echo -n "PostgreSQL query latency: "
START=$(date +%s%N)
docker exec crypto-bot-test-postgres psql -U cryptobot_test -d cryptobot_test -c 'SELECT 1;' > /dev/null 2>&1
END=$(date +%s%N)
LATENCY=$(( (END - START) / 1000000 ))
echo "${LATENCY}ms"
if [ $LATENCY -lt 100 ]; then
    print_success "PostgreSQL query latency acceptable (<100ms)"
    PASSED_TESTS=$((PASSED_TESTS + 1))
else
    print_warning "PostgreSQL query latency high (${LATENCY}ms)"
    FAILED_TESTS=$((FAILED_TESTS + 1))
fi
TOTAL_TESTS=$((TOTAL_TESTS + 1))

# Measure Redis performance
echo -n "Redis PING latency: "
START=$(date +%s%N)
docker exec crypto-bot-test-redis redis-cli PING > /dev/null 2>&1
END=$(date +%s%N)
LATENCY=$(( (END - START) / 1000000 ))
echo "${LATENCY}ms"
if [ $LATENCY -lt 50 ]; then
    print_success "Redis latency acceptable (<50ms)"
    PASSED_TESTS=$((PASSED_TESTS + 1))
else
    print_warning "Redis latency high (${LATENCY}ms)"
    FAILED_TESTS=$((FAILED_TESTS + 1))
fi
TOTAL_TESTS=$((TOTAL_TESTS + 1))

echo ""
echo "9. Resource Usage"
echo "-------------------------------------------"

# Show container resource usage
echo "Container resource usage:"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" \
    crypto-bot-test-postgres crypto-bot-test-timescaledb crypto-bot-test-redis

echo ""
echo "=========================================="
echo "Verification Summary"
echo "=========================================="
echo ""
echo "Total Tests:  $TOTAL_TESTS"
print_success "Passed: $PASSED_TESTS"
if [ $FAILED_TESTS -gt 0 ]; then
    print_error "Failed: $FAILED_TESTS"
fi
echo ""

# Calculate success rate
SUCCESS_RATE=$(( PASSED_TESTS * 100 / TOTAL_TESTS ))
echo "Success Rate: ${SUCCESS_RATE}%"
echo ""

if [ $FAILED_TESTS -eq 0 ]; then
    print_success "All tests passed! Test database infrastructure is operational."
    echo ""
    exit 0
else
    print_error "Some tests failed. Review output above for details."
    echo ""
    echo "Troubleshooting steps:"
    echo "1. Check container logs: docker logs crypto-bot-test-postgres"
    echo "2. Restart databases: ./scripts/test-db-stop.sh && ./scripts/test-db-start.sh"
    echo "3. Review documentation: docs/TEST_DATABASE_SETUP.md"
    echo ""
    exit 1
fi
