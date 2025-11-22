#!/bin/bash
#
# Stop Test Databases
# Purpose: Stop and remove test database containers
# Usage: ./scripts/test-db-stop.sh
#

set -e  # Exit on error

echo "=========================================="
echo "Stopping Test Database Infrastructure"
echo "=========================================="

# Navigate to project root
cd "$(dirname "$0")/.."

# Stop test databases
echo "Stopping test database containers..."
docker-compose -f docker-compose.test.yml down

echo ""
echo "✓ Test databases stopped"
echo ""
echo "Note: Data is stored in tmpfs and is NOT persisted"
echo "Next start will create fresh databases"
echo "=========================================="
