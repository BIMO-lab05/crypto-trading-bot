#!/bin/bash
#
# Clean Test Databases
# Purpose: Stop containers and remove all test data
# Usage: ./scripts/test-db-clean.sh
#

set -e  # Exit on error

echo "=========================================="
echo "Cleaning Test Database Infrastructure"
echo "=========================================="

# Navigate to project root
cd "$(dirname "$0")/.."

# Stop and remove everything
echo "Removing test database containers and volumes..."
docker-compose -f docker-compose.test.yml down -v --remove-orphans

echo ""
echo "✓ Test databases cleaned"
echo "✓ All test data removed"
echo ""
echo "Run ./scripts/test-db-start.sh to recreate"
echo "=========================================="
