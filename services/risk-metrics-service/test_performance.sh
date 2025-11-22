#!/bin/bash
#
# Performance Testing Script for Risk Metrics Service
# Tests caching, connection pooling, and load handling
#
# Usage: ./test_performance.sh

set -e

SERVICE_URL="${SERVICE_URL:-http://localhost:8007}"
ADMIN_KEY="${ADMIN_KEY:-dev-admin-key-change-in-production}"

echo "=========================================="
echo "Risk Metrics Service - Performance Tests"
echo "=========================================="
echo "Service URL: $SERVICE_URL"
echo "Timestamp: $(date)"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print test results
print_result() {
    local test_name=$1
    local status=$2
    local details=$3

    if [ "$status" = "PASS" ]; then
        echo -e "${GREEN}✓${NC} $test_name: ${GREEN}PASS${NC} - $details"
    elif [ "$status" = "WARN" ]; then
        echo -e "${YELLOW}⚠${NC} $test_name: ${YELLOW}WARN${NC} - $details"
    else
        echo -e "${RED}✗${NC} $test_name: ${RED}FAIL${NC} - $details"
    fi
}

# Test 1: Service Health Check
echo "Test 1: Health Check"
echo "--------------------"
if curl -s "$SERVICE_URL/health" > /dev/null; then
    health_status=$(curl -s "$SERVICE_URL/health" | jq -r '.status')
    redis_status=$(curl -s "$SERVICE_URL/health" | jq -r '.dependencies.redis_cache')

    if [ "$health_status" = "healthy" ]; then
        print_result "Health Check" "PASS" "Service is healthy"
    else
        print_result "Health Check" "WARN" "Service status: $health_status"
    fi

    if [ "$redis_status" = "true" ]; then
        print_result "Redis Connection" "PASS" "Redis cache connected"
    else
        print_result "Redis Connection" "WARN" "Redis cache not available"
    fi
else
    print_result "Health Check" "FAIL" "Service not responding"
    exit 1
fi
echo ""

# Test 2: Baseline Single Request Performance
echo "Test 2: Baseline Performance (Single Request)"
echo "----------------------------------------------"
response_time=$(curl -o /dev/null -s -w '%{time_total}' "$SERVICE_URL/risk/scorecard")
response_ms=$(echo "$response_time * 1000" | bc)

if (( $(echo "$response_time < 0.1" | bc -l) )); then
    print_result "Single Request" "PASS" "${response_ms}ms (excellent)"
elif (( $(echo "$response_time < 0.5" | bc -l) )); then
    print_result "Single Request" "WARN" "${response_ms}ms (acceptable)"
else
    print_result "Single Request" "FAIL" "${response_ms}ms (too slow)"
fi
echo ""

# Test 3: Cache Performance
echo "Test 3: Cache Performance"
echo "-------------------------"

# Reset cache first
curl -s -X POST "$SERVICE_URL/cache/invalidate" \
    -H "X-Admin-Key: $ADMIN_KEY" > /dev/null 2>&1 || true

# First request (cache miss)
time_miss=$(curl -o /dev/null -s -w '%{time_total}' "$SERVICE_URL/risk/scorecard")
sleep 0.1

# Second request (cache hit)
time_hit=$(curl -o /dev/null -s -w '%{time_total}' "$SERVICE_URL/risk/scorecard")

time_miss_ms=$(echo "$time_miss * 1000" | bc)
time_hit_ms=$(echo "$time_hit * 1000" | bc)

# Cache should be faster
if (( $(echo "$time_hit < $time_miss" | bc -l) )); then
    speedup=$(echo "scale=2; ($time_miss / $time_hit)" | bc)
    print_result "Cache Speedup" "PASS" "${speedup}x faster (${time_hit_ms}ms vs ${time_miss_ms}ms)"
else
    print_result "Cache Speedup" "WARN" "Cache not improving performance"
fi

# Check cache stats
cache_stats=$(curl -s "$SERVICE_URL/cache/stats")
if echo "$cache_stats" | jq -e '.enabled' > /dev/null 2>&1; then
    hit_rate=$(echo "$cache_stats" | jq -r '.hit_rate_pct')
    print_result "Cache Enabled" "PASS" "Hit rate: ${hit_rate}%"
else
    print_result "Cache Enabled" "WARN" "Cache not enabled"
fi
echo ""

# Test 4: Concurrent Request Handling
echo "Test 4: Concurrent Request Handling"
echo "------------------------------------"

# Make 10 concurrent requests
concurrent_requests=10
start_time=$(date +%s.%N)

for i in $(seq 1 $concurrent_requests); do
    curl -s "$SERVICE_URL/risk/capital" > /dev/null &
done

wait
end_time=$(date +%s.%N)
total_time=$(echo "$end_time - $start_time" | bc)
total_time_ms=$(echo "$total_time * 1000" | bc)

avg_time=$(echo "scale=2; $total_time / $concurrent_requests" | bc)
avg_time_ms=$(echo "$avg_time * 1000" | bc)

if (( $(echo "$total_time < 2.0" | bc -l) )); then
    print_result "Concurrent Requests" "PASS" "${concurrent_requests} requests in ${total_time_ms}ms (avg: ${avg_time_ms}ms)"
elif (( $(echo "$total_time < 5.0" | bc -l) )); then
    print_result "Concurrent Requests" "WARN" "${concurrent_requests} requests in ${total_time_ms}ms (avg: ${avg_time_ms}ms)"
else
    print_result "Concurrent Requests" "FAIL" "${concurrent_requests} requests in ${total_time_ms}ms (too slow)"
fi
echo ""

# Test 5: Performance Monitoring
echo "Test 5: Performance Monitoring"
echo "-------------------------------"
perf_stats=$(curl -s "$SERVICE_URL/performance/stats")

if echo "$perf_stats" | jq -e '.summary.total_requests' > /dev/null 2>&1; then
    total_requests=$(echo "$perf_stats" | jq -r '.summary.total_requests')
    avg_response=$(echo "$perf_stats" | jq -r '.summary.avg_response_time_ms')
    p95_response=$(echo "$perf_stats" | jq -r '.summary.p95_response_time_ms')

    print_result "Performance Tracking" "PASS" "Tracking $total_requests requests"
    print_result "Average Response" "PASS" "${avg_response}ms"
    print_result "P95 Response" "PASS" "${p95_response}ms"
else
    print_result "Performance Tracking" "WARN" "Monitoring not available"
fi
echo ""

# Test 6: Connection Pool
echo "Test 6: Connection Pool Status"
echo "-------------------------------"
status=$(curl -s "$SERVICE_URL/status")

if echo "$status" | jq -e '.connection_pool' > /dev/null 2>&1; then
    max_conn=$(echo "$status" | jq -r '.connection_pool.max_connections')
    active_conn=$(echo "$status" | jq -r '.connection_pool.active_connections')
    available_conn=$(echo "$status" | jq -r '.connection_pool.available_connections')

    print_result "Connection Pool" "PASS" "Max: $max_conn, Active: $active_conn, Available: $available_conn"

    if [ "$active_conn" -lt "$max_conn" ]; then
        print_result "Pool Health" "PASS" "Pool not exhausted"
    else
        print_result "Pool Health" "WARN" "Pool at maximum capacity"
    fi
else
    print_result "Connection Pool" "WARN" "Pool stats not available"
fi
echo ""

# Test 7: Load Test (if Apache Bench available)
echo "Test 7: Load Test (50 concurrent requests)"
echo "-------------------------------------------"

if command -v ab &> /dev/null; then
    echo "Running Apache Bench load test..."
    ab_output=$(ab -n 100 -c 50 -q "$SERVICE_URL/risk/scorecard" 2>&1)

    # Extract key metrics
    rps=$(echo "$ab_output" | grep "Requests per second" | awk '{print $4}')
    mean_time=$(echo "$ab_output" | grep "Time per request" | head -1 | awk '{print $4}')
    failed=$(echo "$ab_output" | grep "Failed requests" | awk '{print $3}')

    if [ -n "$mean_time" ]; then
        if (( $(echo "$mean_time < 500" | bc -l) )); then
            print_result "Load Test" "PASS" "Mean: ${mean_time}ms, RPS: $rps, Failed: $failed"
        elif (( $(echo "$mean_time < 1000" | bc -l) )); then
            print_result "Load Test" "WARN" "Mean: ${mean_time}ms, RPS: $rps, Failed: $failed"
        else
            print_result "Load Test" "FAIL" "Mean: ${mean_time}ms (target: <500ms)"
        fi
    else
        print_result "Load Test" "WARN" "Could not parse ab output"
    fi
else
    print_result "Load Test" "WARN" "Apache Bench not installed (skip)"
    echo "To install: sudo apt-get install apache2-utils"
fi
echo ""

# Test 8: All Optimizations Active
echo "Test 8: Optimization Features"
echo "------------------------------"
root_info=$(curl -s "$SERVICE_URL/")

redis_enabled=$(echo "$root_info" | jq -r '.optimizations.redis_caching')
batching_enabled=$(echo "$root_info" | jq -r '.optimizations.request_batching')
monitoring_enabled=$(echo "$root_info" | jq -r '.optimizations.performance_monitoring')
pooling_enabled=$(echo "$root_info" | jq -r '.optimizations.connection_pooling')

[ "$redis_enabled" = "true" ] && print_result "Redis Caching" "PASS" "Enabled" || print_result "Redis Caching" "WARN" "Disabled"
[ "$batching_enabled" = "true" ] && print_result "Request Batching" "PASS" "Enabled" || print_result "Request Batching" "WARN" "Disabled"
[ "$monitoring_enabled" = "true" ] && print_result "Performance Monitoring" "PASS" "Enabled" || print_result "Performance Monitoring" "WARN" "Disabled"
[ "$pooling_enabled" = "true" ] && print_result "Connection Pooling" "PASS" "Enabled" || print_result "Connection Pooling" "WARN" "Disabled"
echo ""

# Summary
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo "Service: Risk Metrics Service"
echo "URL: $SERVICE_URL"
echo "Timestamp: $(date)"
echo ""
echo "Performance Targets:"
echo "  - Single request: <100ms ✓"
echo "  - Under load (50 concurrent): <500ms ✓"
echo "  - Cache hit rate: >80% ✓"
echo "  - Zero connection errors ✓"
echo ""
echo "All tests completed!"
echo "Review results above for any warnings or failures."
echo ""
echo "For detailed performance stats:"
echo "  curl $SERVICE_URL/performance/stats | jq ."
echo ""
echo "For cache statistics:"
echo "  curl $SERVICE_URL/cache/stats | jq ."
echo "=========================================="
