#!/bin/bash
# Database Integration Tests Runner
# Purpose: Execute database persistence tests with proper environment setup

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}Database Integration Tests${NC}"
echo -e "${YELLOW}========================================${NC}"

# Navigate to trading-engine directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if PostgreSQL is running
echo -e "\n${YELLOW}1. Checking PostgreSQL...${NC}"
if docker ps | grep -q crypto-bot-postgres; then
    echo -e "${GREEN}✓ PostgreSQL is running${NC}"
else
    echo -e "${RED}✗ PostgreSQL is not running${NC}"
    echo -e "${YELLOW}Starting PostgreSQL...${NC}"
    cd ../.. && docker-compose up -d postgres && cd services/trading-engine
    sleep 5
fi

# Check if test database exists
echo -e "\n${YELLOW}2. Checking test database...${NC}"
if docker exec crypto-bot-postgres psql -U cryptobot -d postgres -lqt | cut -d \| -f 1 | grep -qw cryptobot_test; then
    echo -e "${GREEN}✓ Test database exists${NC}"
else
    echo -e "${YELLOW}Creating test database...${NC}"
    docker exec crypto-bot-postgres psql -U cryptobot -d postgres -c "CREATE DATABASE cryptobot_test;"
    echo -e "${GREEN}✓ Test database created${NC}"
fi

# Load test environment variables
echo -e "\n${YELLOW}3. Loading test environment...${NC}"
if [ -f .env.test ]; then
    export $(cat .env.test | grep -v '^#' | xargs)
    echo -e "${GREEN}✓ Test environment loaded${NC}"
else
    echo -e "${RED}✗ .env.test not found${NC}"
    exit 1
fi

# Check Python dependencies
echo -e "\n${YELLOW}4. Checking dependencies...${NC}"
if python -c "import pytest_asyncio" 2>/dev/null; then
    echo -e "${GREEN}✓ pytest-asyncio installed${NC}"
else
    echo -e "${YELLOW}Installing test dependencies...${NC}"
    pip install pytest-asyncio pytest-cov asyncpg
fi

# Run tests based on arguments
echo -e "\n${YELLOW}5. Running tests...${NC}"
echo -e "${YELLOW}========================================${NC}\n"

# Default: run all tests with coverage
TEST_CMD="pytest tests/integration/test_database_persistence.py"

# Parse command line arguments
case "${1:-all}" in
    fast)
        echo -e "${YELLOW}Running fast tests only (excluding slow tests)...${NC}"
        TEST_CMD="$TEST_CMD -m 'not slow' -v"
        ;;
    slow)
        echo -e "${YELLOW}Running performance tests only...${NC}"
        TEST_CMD="$TEST_CMD -m slow -v"
        ;;
    coverage)
        echo -e "${YELLOW}Running tests with coverage report...${NC}"
        TEST_CMD="$TEST_CMD --cov=app.repositories --cov-report=term --cov-report=html -v"
        ;;
    verbose)
        echo -e "${YELLOW}Running tests with verbose output...${NC}"
        TEST_CMD="$TEST_CMD -v -s"
        ;;
    debug)
        echo -e "${YELLOW}Running tests with SQL debugging...${NC}"
        export DB_ECHO=true
        TEST_CMD="$TEST_CMD -v -s --log-cli-level=DEBUG"
        ;;
    *)
        echo -e "${YELLOW}Running all tests...${NC}"
        TEST_CMD="$TEST_CMD -v"
        ;;
esac

# Execute tests
eval $TEST_CMD
TEST_EXIT_CODE=$?

# Report results
echo -e "\n${YELLOW}========================================${NC}"
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"

    # Show coverage report if generated
    if [ -d "htmlcov" ]; then
        echo -e "${YELLOW}Coverage report: file://$(pwd)/htmlcov/index.html${NC}"
    fi
else
    echo -e "${RED}✗ Some tests failed${NC}"
fi
echo -e "${YELLOW}========================================${NC}"

exit $TEST_EXIT_CODE
