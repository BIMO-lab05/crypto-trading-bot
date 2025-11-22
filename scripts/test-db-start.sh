#!/bin/bash
#
# Start Test Databases
# Purpose: Start Docker containers for test databases
# Usage: ./scripts/test-db-start.sh
#

set -e  # Exit on error

echo "=========================================="
echo "Starting Test Database Infrastructure"
echo "=========================================="

# Navigate to project root
cd "$(dirname "$0")/.."

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "ERROR: docker-compose not found. Please install Docker Compose."
    exit 1
fi

# Start test databases
echo "Starting test database containers..."
docker-compose -f docker-compose.test.yml up -d

# Wait for databases to be healthy
echo ""
echo "Waiting for databases to be ready..."
sleep 5

# Check health status
echo ""
echo "Checking database health..."

# Function to check if container is healthy
check_health() {
    local container_name=$1
    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        status=$(docker inspect --format='{{.State.Health.Status}}' "$container_name" 2>/dev/null || echo "not found")

        if [ "$status" = "healthy" ]; then
            echo "✓ $container_name is healthy"
            return 0
        fi

        echo "  Waiting for $container_name (attempt $attempt/$max_attempts)..."
        sleep 2
        attempt=$((attempt + 1))
    done

    echo "✗ $container_name failed to become healthy"
    return 1
}

# Check each test database
check_health "crypto-bot-test-postgres"
check_health "crypto-bot-test-timescaledb"
check_health "crypto-bot-test-redis"

echo ""
echo "=========================================="
echo "Test Database Infrastructure Ready"
echo "=========================================="
echo ""
echo "PostgreSQL:    localhost:5434"
echo "  Database:    cryptobot_test"
echo "  User:        cryptobot_test"
echo "  Password:    test_password_123"
echo ""
echo "TimescaleDB:   localhost:5435"
echo "  Database:    market_data_test"
echo "  User:        cryptobot_test"
echo "  Password:    test_password_123"
echo ""
echo "Redis:         localhost:6380"
echo ""
echo "Run tests with:"
echo "  cd services/trading-engine && pytest tests/"
echo ""
echo "Stop databases with:"
echo "  ./scripts/test-db-stop.sh"
echo "=========================================="
