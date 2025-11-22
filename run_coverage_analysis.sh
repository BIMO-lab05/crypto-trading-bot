#!/bin/bash
# Test Coverage Analysis Script
# Purpose: Run pytest coverage for all services and generate comprehensive report

echo "========================================="
echo "TEST COVERAGE ANALYSIS"
echo "Crypto Trading Bot - All Services"
echo "========================================="
echo ""

# Define services to test
SERVICES=(
    "api-gateway"
    "bybit-connector"
    "market-data-service"
    "portfolio-manager"
    "technical-analysis"
    "trading-engine"
    "notification-service"
    "ml-prediction-service"
    "sentiment-analysis-service"
    "risk-metrics-service"
)

# Output file
REPORT_FILE="coverage_report_$(date +%Y%m%d_%H%M%S).txt"

echo "Coverage Report - $(date)" > "$REPORT_FILE"
echo "=========================================" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# Summary arrays
declare -A coverage_results
declare -A test_counts
declare -A test_status

# Run coverage for each service
for service in "${SERVICES[@]}"; do
    echo "========================================="
    echo "Testing: $service"
    echo "========================================="

    SERVICE_PATH="services/$service"

    if [ ! -d "$SERVICE_PATH" ]; then
        echo "⚠️  Service directory not found: $SERVICE_PATH"
        echo "---" >> "$REPORT_FILE"
        echo "Service: $service - NOT FOUND" >> "$REPORT_FILE"
        echo "" >> "$REPORT_FILE"
        continue
    fi

    # Check if tests directory exists
    if [ ! -d "$SERVICE_PATH/tests" ]; then
        echo "❌ No tests directory found"
        coverage_results[$service]="0%"
        test_counts[$service]="0"
        test_status[$service]="NO_TESTS"

        echo "---" >> "$REPORT_FILE"
        echo "Service: $service" >> "$REPORT_FILE"
        echo "Status: NO TESTS" >> "$REPORT_FILE"
        echo "Coverage: 0%" >> "$REPORT_FILE"
        echo "" >> "$REPORT_FILE"
        continue
    fi

    # Count test files
    TEST_FILE_COUNT=$(find "$SERVICE_PATH/tests" -name "test_*.py" -o -name "*_test.py" | wc -l)
    test_counts[$service]=$TEST_FILE_COUNT

    echo "📝 Test files found: $TEST_FILE_COUNT"

    # Run pytest with coverage
    cd "$SERVICE_PATH" || continue

    echo "Running tests..."

    # Run pytest and capture output
    PYTEST_OUTPUT=$(python3 -m pytest tests/ --cov=app --cov-report=term-missing --cov-report=html -v 2>&1)
    PYTEST_EXIT_CODE=$?

    # Extract coverage percentage
    COVERAGE=$(echo "$PYTEST_OUTPUT" | grep "TOTAL" | awk '{print $NF}')

    if [ -z "$COVERAGE" ]; then
        COVERAGE="N/A"
        test_status[$service]="ERROR"
    else
        coverage_results[$service]=$COVERAGE

        # Determine status based on coverage
        COVERAGE_NUM=$(echo $COVERAGE | sed 's/%//')
        if [ "$COVERAGE_NUM" -ge 80 ]; then
            test_status[$service]="✅ PASS"
        elif [ "$COVERAGE_NUM" -ge 60 ]; then
            test_status[$service]="⚠️  MEDIUM"
        else
            test_status[$service]="❌ LOW"
        fi
    fi

    # Extract test results
    PASSED=$(echo "$PYTEST_OUTPUT" | grep -oP '\d+(?= passed)' | head -1)
    FAILED=$(echo "$PYTEST_OUTPUT" | grep -oP '\d+(?= failed)' | head -1)

    [ -z "$PASSED" ] && PASSED=0
    [ -z "$FAILED" ] && FAILED=0

    echo "Coverage: $COVERAGE"
    echo "Tests Passed: $PASSED"
    echo "Tests Failed: $FAILED"
    echo ""

    # Append to report
    echo "---" >> "../../../$REPORT_FILE"
    echo "Service: $service" >> "../../../$REPORT_FILE"
    echo "Test Files: $TEST_FILE_COUNT" >> "../../../$REPORT_FILE"
    echo "Tests Passed: $PASSED" >> "../../../$REPORT_FILE"
    echo "Tests Failed: $FAILED" >> "../../../$REPORT_FILE"
    echo "Coverage: $COVERAGE" >> "../../../$REPORT_FILE"
    echo "Status: ${test_status[$service]}" >> "../../../$REPORT_FILE"
    echo "" >> "../../../$REPORT_FILE"

    cd - > /dev/null
done

# Generate summary
echo "" >> "$REPORT_FILE"
echo "=========================================" >> "$REPORT_FILE"
echo "SUMMARY" >> "$REPORT_FILE"
echo "=========================================" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# Create summary table
printf "%-30s %-15s %-15s %-10s\n" "Service" "Test Files" "Coverage" "Status" >> "$REPORT_FILE"
printf "%-30s %-15s %-15s %-10s\n" "-------" "----------" "--------" "------" >> "$REPORT_FILE"

for service in "${SERVICES[@]}"; do
    printf "%-30s %-15s %-15s %-10s\n" \
        "$service" \
        "${test_counts[$service]:-0}" \
        "${coverage_results[$service]:-N/A}" \
        "${test_status[$service]:-UNKNOWN}" >> "$REPORT_FILE"
done

echo "" >> "$REPORT_FILE"

# Calculate total statistics
TOTAL_SERVICES=${#SERVICES[@]}
SERVICES_WITH_TESTS=0
SERVICES_ABOVE_80=0

for service in "${SERVICES[@]}"; do
    COUNT=${test_counts[$service]:-0}
    if [ "$COUNT" -gt 0 ]; then
        SERVICES_WITH_TESTS=$((SERVICES_WITH_TESTS + 1))
    fi

    COVERAGE=${coverage_results[$service]:-0%}
    COVERAGE_NUM=$(echo $COVERAGE | sed 's/%//')

    if [ ! -z "$COVERAGE_NUM" ] && [ "$COVERAGE_NUM" -ge 80 ] 2>/dev/null; then
        SERVICES_ABOVE_80=$((SERVICES_ABOVE_80 + 1))
    fi
done

echo "Statistics:" >> "$REPORT_FILE"
echo "- Total Services: $TOTAL_SERVICES" >> "$REPORT_FILE"
echo "- Services with Tests: $SERVICES_WITH_TESTS" >> "$REPORT_FILE"
echo "- Services with 80%+ Coverage: $SERVICES_ABOVE_80" >> "$REPORT_FILE"
echo "- Services Needing Tests: $((TOTAL_SERVICES - SERVICES_WITH_TESTS))" >> "$REPORT_FILE"

# Console output
echo "========================================="
echo "COVERAGE ANALYSIS COMPLETE"
echo "========================================="
echo ""
echo "Summary:"
echo "- Total Services: $TOTAL_SERVICES"
echo "- Services with Tests: $SERVICES_WITH_TESTS"
echo "- Services with 80%+ Coverage: $SERVICES_ABOVE_80"
echo "- Services Needing Tests: $((TOTAL_SERVICES - SERVICES_WITH_TESTS))"
echo ""
echo "Detailed report saved to: $REPORT_FILE"
echo ""

# Display summary table
echo "Service Coverage Summary:"
echo "-----------------------------------------------------------"
printf "%-30s %-15s %-10s\n" "Service" "Coverage" "Status"
echo "-----------------------------------------------------------"

for service in "${SERVICES[@]}"; do
    printf "%-30s %-15s %-10s\n" \
        "$service" \
        "${coverage_results[$service]:-N/A}" \
        "${test_status[$service]:-UNKNOWN}"
done

echo "-----------------------------------------------------------"
echo ""
echo "Next Steps:"
echo "1. Fix failing tests in services with errors"
echo "2. Add tests to services with <80% coverage"
echo "3. Create tests for services without test directories"
echo ""
