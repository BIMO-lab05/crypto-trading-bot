#!/bin/bash

# ============================================================================
# Phase 3 Test Runner Script
# ============================================================================
# Runs all tests for ML Prediction and Sentiment Analysis services
# Generates combined coverage reports
#
# Usage:
#   ./scripts/run_phase3_tests.sh [options]
#
# Options:
#   --unit          Run only unit tests
#   --integration   Run only integration tests
#   --performance   Run only performance tests
#   --coverage      Generate HTML coverage reports
#   --watch         Run in watch mode (auto-rerun on changes)
#   --verbose       Verbose output
#   --help          Show this help message
# ============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SERVICES_DIR="$PROJECT_ROOT/services"

# Services to test
ML_SERVICE_DIR="$SERVICES_DIR/ml-prediction-service"
SENTIMENT_SERVICE_DIR="$SERVICES_DIR/sentiment-analysis-service"

# Test options
RUN_UNIT=false
RUN_INTEGRATION=false
RUN_PERFORMANCE=false
GENERATE_COVERAGE=false
WATCH_MODE=false
VERBOSE=""

# ============================================================================
# Helper Functions
# ============================================================================

print_header() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

show_help() {
    head -n 23 "$0" | tail -n 17
    exit 0
}

# ============================================================================
# Parse Arguments
# ============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        --unit)
            RUN_UNIT=true
            shift
            ;;
        --integration)
            RUN_INTEGRATION=true
            shift
            ;;
        --performance)
            RUN_PERFORMANCE=true
            shift
            ;;
        --coverage)
            GENERATE_COVERAGE=true
            shift
            ;;
        --watch)
            WATCH_MODE=true
            shift
            ;;
        --verbose|-v)
            VERBOSE="-v"
            shift
            ;;
        --help|-h)
            show_help
            ;;
        *)
            print_error "Unknown option: $1"
            show_help
            ;;
    esac
done

# If no specific test type selected, run all
if [[ "$RUN_UNIT" == false && "$RUN_INTEGRATION" == false && "$RUN_PERFORMANCE" == false ]]; then
    RUN_UNIT=true
    RUN_INTEGRATION=true
    RUN_PERFORMANCE=true
fi

# ============================================================================
# Pre-flight Checks
# ============================================================================

print_header "Phase 3 Test Suite - Pre-flight Checks"

# Check if services exist
if [[ ! -d "$ML_SERVICE_DIR" ]]; then
    print_error "ML Prediction Service not found at $ML_SERVICE_DIR"
    exit 1
fi

if [[ ! -d "$SENTIMENT_SERVICE_DIR" ]]; then
    print_error "Sentiment Analysis Service not found at $SENTIMENT_SERVICE_DIR"
    exit 1
fi

print_success "Services found"

# Check if test directories exist
if [[ ! -d "$ML_SERVICE_DIR/tests" ]]; then
    print_error "ML service tests not found"
    exit 1
fi

if [[ ! -d "$SENTIMENT_SERVICE_DIR/tests" ]]; then
    print_error "Sentiment service tests not found"
    exit 1
fi

print_success "Test directories found"

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    print_error "pytest not found. Install with: pip install pytest"
    exit 1
fi

print_success "pytest installed"

# ============================================================================
# Build Test Command
# ============================================================================

build_test_command() {
    local markers=""

    # Add markers based on test types
    if [[ "$RUN_UNIT" == true && "$RUN_INTEGRATION" == false && "$RUN_PERFORMANCE" == false ]]; then
        markers="-m unit"
    elif [[ "$RUN_UNIT" == false && "$RUN_INTEGRATION" == true && "$RUN_PERFORMANCE" == false ]]; then
        markers="-m integration"
    elif [[ "$RUN_UNIT" == false && "$RUN_INTEGRATION" == false && "$RUN_PERFORMANCE" == true ]]; then
        markers="-m performance"
    fi

    # Build command
    local cmd="pytest tests/ $VERBOSE $markers"

    # Add coverage if requested
    if [[ "$GENERATE_COVERAGE" == true ]]; then
        cmd="$cmd --cov=app --cov-report=html --cov-report=term-missing"
    fi

    echo "$cmd"
}

# ============================================================================
# Run Tests
# ============================================================================

run_service_tests() {
    local service_name=$1
    local service_dir=$2

    print_header "Running $service_name Tests"

    cd "$service_dir"

    # Check if requirements-test.txt exists and install
    if [[ -f "requirements-test.txt" ]]; then
        print_info "Installing test dependencies..."
        pip install -q -r requirements-test.txt
    fi

    # Build and run test command
    local test_cmd=$(build_test_command)
    print_info "Running: $test_cmd"

    if eval "$test_cmd"; then
        print_success "$service_name tests passed"
        return 0
    else
        print_error "$service_name tests failed"
        return 1
    fi
}

# ============================================================================
# Main Execution
# ============================================================================

print_header "Phase 3 Test Suite"
print_info "Running tests for ML Prediction and Sentiment Analysis services"
echo ""

# Track results
ML_RESULT=0
SENTIMENT_RESULT=0

# Run ML Prediction Service tests
if ! run_service_tests "ML Prediction Service" "$ML_SERVICE_DIR"; then
    ML_RESULT=1
fi

echo ""

# Run Sentiment Analysis Service tests
if ! run_service_tests "Sentiment Analysis Service" "$SENTIMENT_SERVICE_DIR"; then
    SENTIMENT_RESULT=1
fi

# ============================================================================
# Generate Combined Coverage Report
# ============================================================================

if [[ "$GENERATE_COVERAGE" == true ]]; then
    print_header "Coverage Reports Generated"

    print_info "ML Prediction Service coverage:"
    echo "  file://$ML_SERVICE_DIR/htmlcov/index.html"

    print_info "Sentiment Analysis Service coverage:"
    echo "  file://$SENTIMENT_SERVICE_DIR/htmlcov/index.html"
fi

# ============================================================================
# Summary
# ============================================================================

print_header "Test Summary"

if [[ $ML_RESULT -eq 0 ]]; then
    print_success "ML Prediction Service: ALL TESTS PASSED"
else
    print_error "ML Prediction Service: TESTS FAILED"
fi

if [[ $SENTIMENT_RESULT -eq 0 ]]; then
    print_success "Sentiment Analysis Service: ALL TESTS PASSED"
else
    print_error "Sentiment Analysis Service: TESTS FAILED"
fi

# Final status
TOTAL_RESULT=$((ML_RESULT + SENTIMENT_RESULT))

if [[ $TOTAL_RESULT -eq 0 ]]; then
    print_header "✓ ALL PHASE 3 TESTS PASSED"
    exit 0
else
    print_header "✗ SOME TESTS FAILED"
    exit 1
fi
