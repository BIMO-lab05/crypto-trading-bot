#!/bin/bash
#
# Test Runner for Trading Engine
# Runs unit tests, integration tests, and benchmarks
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "================================================================================"
echo "                     TRADING ENGINE TEST SUITE"
echo "================================================================================"
echo ""

# Parse command line arguments
TEST_TYPE="${1:-all}"  # all, unit, integration, benchmark
VERBOSE="${2:-false}"

# Test configuration
PYTHONPATH=".:../..:../../../../shared"
export PYTHONPATH

# Function to run tests
run_tests() {
    local test_type=$1
    local test_path=$2
    local markers=$3
    
    echo ""
    echo -e "${YELLOW}Running ${test_type} tests...${NC}"
    echo "--------------------------------------------------------------------------------"
    
    if [ "$VERBOSE" = "true" ]; then
        pytest ${test_path} -v -s ${markers} --tb=short --color=yes
    else
        pytest ${test_path} -v ${markers} --tb=short --color=yes
    fi
    
    local exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}✓ ${test_type} tests passed!${NC}"
    else
        echo -e "${RED}✗ ${test_type} tests failed!${NC}"
        return $exit_code
    fi
}

# Install dependencies if needed
if ! command -v pytest &> /dev/null; then
    echo "Installing test dependencies..."
    pip install pytest pytest-asyncio pytest-cov
fi

# Run migrations
echo ""
echo -e "${YELLOW}Checking database schema...${NC}"
if [ -f "../../../../infrastructure/migrations/001_initial_schema.sql" ]; then
    echo "  Migration file found: 001_initial_schema.sql"
    echo "  (Run manually with: psql -U cryptobot -d cryptobot -f 001_initial_schema.sql)"
else
    echo "  No migration files found"
fi

# Run tests based on type
case "$TEST_TYPE" in
    unit)
        run_tests "Unit" "tests/unit/" ""
        ;;
    
    integration)
        run_tests "Integration" "tests/integration/" "-m integration"
        ;;
    
    benchmark)
        run_tests "Benchmark" "tests/benchmarks/" "-m benchmark"
        ;;
    
    all)
        # Run all test types
        run_tests "Unit" "tests/unit/" ""
        UNIT_EXIT=$?
        
        run_tests "Integration" "tests/integration/" "-m integration"
        INTEGRATION_EXIT=$?
        
        run_tests "Benchmark" "tests/benchmarks/" "-m benchmark"
        BENCHMARK_EXIT=$?
        
        # Summary
        echo ""
        echo "================================================================================"
        echo "                          TEST SUMMARY"
        echo "================================================================================"
        
        if [ $UNIT_EXIT -eq 0 ]; then
            echo -e "  ${GREEN}✓${NC} Unit Tests: PASSED"
        else
            echo -e "  ${RED}✗${NC} Unit Tests: FAILED"
        fi
        
        if [ $INTEGRATION_EXIT -eq 0 ]; then
            echo -e "  ${GREEN}✓${NC} Integration Tests: PASSED"
        else
            echo -e "  ${RED}✗${NC} Integration Tests: FAILED"
        fi
        
        if [ $BENCHMARK_EXIT -eq 0 ]; then
            echo -e "  ${GREEN}✓${NC} Benchmark Tests: PASSED"
        else
            echo -e "  ${RED}✗${NC} Benchmark Tests: FAILED"
        fi
        
        echo "================================================================================"
        
        # Exit with error if any tests failed
        if [ $UNIT_EXIT -ne 0 ] || [ $INTEGRATION_EXIT -ne 0 ] || [ $BENCHMARK_EXIT -ne 0 ]; then
            exit 1
        fi
        ;;
    
    *)
        echo -e "${RED}Unknown test type: $TEST_TYPE${NC}"
        echo "Usage: $0 [all|unit|integration|benchmark] [verbose]"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}All tests completed successfully!${NC}"
echo ""
