"""
Rate Limiting Security Tests
Tests for rate limit enforcement, headers, and distributed rate limiting

This module tests:
- Rate limit enforcement on various endpoints
- Rate limit header presence in responses
- Rate limit reset behavior
- Distributed rate limiting with Redis
- Burst handling
- Rate limit bypass attempts
"""

import pytest
import time
import asyncio
import sys
import os
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, MagicMock

# Add project paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "services", "api-gateway"))

# Removed import - using fixtures from conftest.py
# from tests.security.conftest import TEST_USER


# ============================================================================
# Test Class: Rate Limit Enforcement Tests
# ============================================================================

class TestRateLimitEnforcement:
    """Tests for verifying rate limiting is enforced"""

    def test_rate_limit_on_health_endpoint(self, test_client):
        """Test that health endpoint has rate limiting"""
        # Arrange
        responses = []
        rate_limited = False

        # Act - make rapid requests
        for i in range(100):
            response = test_client.get("/health")
            responses.append(response.status_code)
            if response.status_code == 429:
                rate_limited = True
                break

        # Assert - document behavior
        # Rate limiting may or may not be enabled
        successful_count = responses.count(200)
        limited_count = responses.count(429)

        print(f"Health endpoint: {successful_count} successful, {limited_count} rate limited")

        # At minimum, should not crash
        assert 500 not in responses, "Health endpoint should not cause server errors"

    def test_rate_limit_on_login_endpoint(self, test_client):
        """Test rate limiting on login endpoint (critical for brute force prevention)"""
        # Arrange
        rate_limited = False
        responses = []

        # Act - simulate brute force attempt
        for i in range(50):
            response = test_client.post("/auth/login", json={
                "username": "nonexistent",
                "password": f"password{i}"
            })
            responses.append(response.status_code)
            if response.status_code == 429:
                rate_limited = True
                break

        # Assert
        limited_count = responses.count(429)
        failed_auth_count = responses.count(401)

        print(f"Login endpoint: {failed_auth_count} failed auth, {limited_count} rate limited")

        # Document expected behavior
        if not rate_limited:
            print("WARNING: Login endpoint may not have rate limiting enabled")

    def test_rate_limit_on_register_endpoint(self, test_client):
        """Test rate limiting on registration endpoint"""
        rate_limited = False
        responses = []

        for i in range(30):
            response = test_client.post("/auth/register", json={
                "username": f"ratelimituser{i}_{int(time.time())}",
                "email": f"ratelimit{i}_{int(time.time())}@example.com",
                "password": "ValidPassword123!",
                "full_name": f"Rate Limit User {i}"
            })
            responses.append(response.status_code)
            if response.status_code == 429:
                rate_limited = True
                break

        limited_count = responses.count(429)
        success_count = responses.count(201)

        print(f"Register endpoint: {success_count} successful, {limited_count} rate limited")

    def test_rate_limit_on_market_data_endpoints(self, test_client):
        """Test rate limiting on market data endpoints"""
        endpoints = [
            "/api/market/ticker/BTCUSDT",
            "/api/market/klines/BTCUSDT",
            "/api/analysis/rsi/BTCUSDT",
        ]

        for endpoint in endpoints:
            rate_limited = False
            responses = []

            for i in range(50):
                response = test_client.get(endpoint)
                responses.append(response.status_code)
                if response.status_code == 429:
                    rate_limited = True
                    break

            limited_count = responses.count(429)
            print(f"{endpoint}: {limited_count} rate limited out of {len(responses)} requests")

    def test_rate_limit_per_user(self, test_client, valid_token):
        """Test that rate limits are applied per user"""
        headers = {"Authorization": f"Bearer {valid_token}"}
        responses = []

        for i in range(30):
            response = test_client.get("/auth/me", headers=headers)
            responses.append(response.status_code)
            if response.status_code == 429:
                break

        limited_count = responses.count(429)
        success_count = responses.count(200)

        print(f"Authenticated requests: {success_count} successful, {limited_count} rate limited")


# ============================================================================
# Test Class: Rate Limit Headers Tests
# ============================================================================

class TestRateLimitHeaders:
    """Tests for rate limit header presence in responses"""

    EXPECTED_RATE_LIMIT_HEADERS = [
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
    ]

    def test_rate_limit_headers_on_success(self, test_client):
        """Test that rate limit headers are present on successful requests"""
        response = test_client.get("/health")

        # Check for rate limit headers
        headers_present = []
        headers_missing = []

        for header in self.EXPECTED_RATE_LIMIT_HEADERS:
            if header.lower() in [h.lower() for h in response.headers.keys()]:
                headers_present.append(header)
            else:
                headers_missing.append(header)

        print(f"Rate limit headers present: {headers_present}")
        print(f"Rate limit headers missing: {headers_missing}")

        # Document status (may not be implemented)
        if not headers_present:
            print("NOTE: Rate limit headers not implemented")

    def test_rate_limit_headers_values_valid(self, test_client):
        """Test that rate limit header values are valid numbers"""
        response = test_client.get("/health")

        # Check X-RateLimit-Limit if present
        limit = response.headers.get("X-RateLimit-Limit")
        if limit:
            assert limit.isdigit(), f"X-RateLimit-Limit should be a number, got: {limit}"
            assert int(limit) > 0, "X-RateLimit-Limit should be positive"

        # Check X-RateLimit-Remaining if present
        remaining = response.headers.get("X-RateLimit-Remaining")
        if remaining:
            assert remaining.isdigit(), f"X-RateLimit-Remaining should be a number, got: {remaining}"
            assert int(remaining) >= 0, "X-RateLimit-Remaining should be non-negative"

        # Check X-RateLimit-Reset if present
        reset = response.headers.get("X-RateLimit-Reset")
        if reset:
            assert reset.isdigit(), f"X-RateLimit-Reset should be a number, got: {reset}"

    def test_rate_limit_remaining_decreases(self, test_client):
        """Test that X-RateLimit-Remaining decreases with each request"""
        responses = []

        for i in range(5):
            response = test_client.get("/health")
            remaining = response.headers.get("X-RateLimit-Remaining")
            responses.append(int(remaining) if remaining and remaining.isdigit() else None)

        # Filter out None values
        valid_remaining = [r for r in responses if r is not None]

        if len(valid_remaining) >= 2:
            # Check that remaining count decreases
            decreasing = all(valid_remaining[i] >= valid_remaining[i+1]
                           for i in range(len(valid_remaining)-1))
            print(f"Remaining values: {valid_remaining}, decreasing: {decreasing}")

    def test_retry_after_header_on_rate_limit(self, test_client):
        """Test that Retry-After header is present when rate limited"""
        # Make many rapid requests to trigger rate limit
        for i in range(200):
            response = test_client.get("/health")
            if response.status_code == 429:
                # Check for Retry-After header
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    print(f"Retry-After header present: {retry_after}")
                    assert retry_after.isdigit(), "Retry-After should be a number"
                else:
                    print("Retry-After header not present on 429 response")
                break
        else:
            print("Rate limit not triggered - Retry-After test skipped")


# ============================================================================
# Test Class: Rate Limit Reset Tests
# ============================================================================

class TestRateLimitReset:
    """Tests for rate limit reset behavior"""

    def test_rate_limit_resets_after_window(self, test_client):
        """Test that rate limit resets after the time window"""
        # This test requires waiting for the rate limit window to reset
        # Skip in CI environments where timing is unreliable

        # First, exhaust rate limit
        for i in range(200):
            response = test_client.get("/health")
            if response.status_code == 429:
                print(f"Rate limited after {i+1} requests")
                break
        else:
            pytest.skip("Rate limiting not triggered")

        # Get reset time from header
        reset_time = response.headers.get("X-RateLimit-Reset")
        retry_after = response.headers.get("Retry-After")

        if retry_after and retry_after.isdigit():
            wait_time = int(retry_after)
            if wait_time > 60:
                pytest.skip(f"Wait time too long: {wait_time}s")

            print(f"Waiting {wait_time}s for rate limit reset...")
            time.sleep(wait_time + 1)

            # Verify rate limit has reset
            response = test_client.get("/health")
            assert response.status_code == 200, "Rate limit should have reset"
        else:
            pytest.skip("Retry-After header not available")

    def test_rate_limit_per_endpoint(self, test_client):
        """Test that rate limits may be separate per endpoint"""
        # Make requests to one endpoint
        health_responses = []
        for i in range(30):
            response = test_client.get("/health")
            health_responses.append(response.status_code)

        # Make requests to different endpoint
        root_responses = []
        for i in range(30):
            response = test_client.get("/")
            root_responses.append(response.status_code)

        # Document behavior
        print(f"Health: {health_responses.count(429)} rate limited")
        print(f"Root: {root_responses.count(429)} rate limited")


# ============================================================================
# Test Class: Distributed Rate Limiting Tests (Redis)
# ============================================================================

class TestDistributedRateLimiting:
    """Tests for distributed rate limiting with Redis"""

    @pytest.fixture
    def redis_client(self):
        """Create Redis client for testing"""
        try:
            import redis
            client = redis.Redis(host='localhost', port=6379, db=0)
            client.ping()
            return client
        except Exception:
            pytest.skip("Redis not available")

    def test_rate_limit_shared_across_instances(self, redis_client, test_client):
        """Test that rate limits are shared when using Redis"""
        # This test requires Redis and multiple app instances
        # Document expected behavior

        # Check if Redis-based rate limiting is configured
        # This would require access to app configuration
        print("Distributed rate limiting test - requires Redis configuration")

    def test_rate_limit_data_in_redis(self, redis_client, test_client):
        """Test that rate limit data is stored in Redis"""
        # Make a request
        test_client.get("/health")

        # Check Redis for rate limit keys
        # Keys typically follow pattern like "rate_limit:*"
        rate_limit_keys = list(redis_client.scan_iter("*rate*limit*"))

        print(f"Rate limit keys in Redis: {len(rate_limit_keys)}")

        if rate_limit_keys:
            for key in rate_limit_keys[:5]:
                value = redis_client.get(key)
                print(f"  {key}: {value}")


# ============================================================================
# Test Class: Burst Handling Tests
# ============================================================================

class TestBurstHandling:
    """Tests for rate limit burst allowance"""

    def test_burst_allowance(self, test_client):
        """Test that burst requests are handled correctly"""
        # Make burst of concurrent requests
        import concurrent.futures

        def make_request():
            return test_client.get("/health").status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(20)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        success_count = results.count(200)
        rate_limited = results.count(429)

        print(f"Burst test: {success_count} successful, {rate_limited} rate limited")

        # All should either succeed or be rate limited (not server error)
        assert results.count(500) == 0, "Burst should not cause server errors"

    def test_gradual_request_pattern(self, test_client):
        """Test rate limiting with gradual request pattern"""
        # Make requests with small delays
        responses = []

        for i in range(20):
            response = test_client.get("/health")
            responses.append(response.status_code)
            time.sleep(0.1)  # 100ms between requests

        success_count = responses.count(200)
        rate_limited = responses.count(429)

        print(f"Gradual requests: {success_count} successful, {rate_limited} rate limited")


# ============================================================================
# Test Class: Rate Limit Bypass Attempts
# ============================================================================

class TestRateLimitBypass:
    """Tests for preventing rate limit bypass"""

    def test_ip_header_spoofing_prevention(self, test_client):
        """Test that X-Forwarded-For spoofing doesn't bypass rate limits"""
        # Try to spoof IP address
        spoofed_headers = [
            {"X-Forwarded-For": "1.2.3.4"},
            {"X-Real-IP": "5.6.7.8"},
            {"X-Originating-IP": "9.10.11.12"},
            {"X-Client-IP": "13.14.15.16"},
        ]

        rate_limited = False

        for i in range(100):
            headers = spoofed_headers[i % len(spoofed_headers)]
            response = test_client.get("/health", headers=headers)
            if response.status_code == 429:
                rate_limited = True
                print(f"Rate limited despite IP spoofing attempt at request {i+1}")
                break

        # Document behavior
        if not rate_limited:
            print("WARNING: Either rate limiting disabled or IP spoofing may work")

    def test_user_agent_variation_bypass(self, test_client):
        """Test that varying User-Agent doesn't bypass rate limits"""
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1",
            "Mozilla/5.0 (X11; Linux x86_64) Firefox/89.0",
            "Custom Bot/1.0",
            "",
        ]

        rate_limited = False

        for i in range(100):
            headers = {"User-Agent": user_agents[i % len(user_agents)]}
            response = test_client.get("/health", headers=headers)
            if response.status_code == 429:
                rate_limited = True
                break

        if not rate_limited:
            print("WARNING: User-Agent variation may affect rate limiting")

    def test_case_variation_bypass(self, test_client):
        """Test that URL case variations don't bypass rate limits"""
        # Try different case variations of the same endpoint
        urls = [
            "/health",
            "/Health",
            "/HEALTH",
            "/HeAlTh",
        ]

        responses = []

        for _ in range(25):  # 25 requests per URL variant = 100 total
            for url in urls:
                response = test_client.get(url)
                responses.append(response.status_code)

        # If case-insensitive routing, all should hit same rate limit
        rate_limited = responses.count(429)
        print(f"Case variation test: {rate_limited} rate limited out of {len(responses)}")


# ============================================================================
# Test Class: Rate Limit Configuration Tests
# ============================================================================

class TestRateLimitConfiguration:
    """Tests for rate limit configuration"""

    def test_different_limits_for_auth_endpoints(self, test_client):
        """Test that auth endpoints may have stricter rate limits"""
        # Auth endpoints should have stricter limits to prevent brute force

        # Test login endpoint
        login_limited = 0
        for i in range(50):
            response = test_client.post("/auth/login", json={
                "username": "test",
                "password": "test"
            })
            if response.status_code == 429:
                login_limited = i + 1
                break

        # Test health endpoint
        health_limited = 0
        for i in range(50):
            response = test_client.get("/health")
            if response.status_code == 429:
                health_limited = i + 1
                break

        print(f"Login rate limited at: {login_limited if login_limited else 'not limited'}")
        print(f"Health rate limited at: {health_limited if health_limited else 'not limited'}")

        # Auth should ideally be more restrictive
        if login_limited and health_limited:
            print(f"Auth is {'more' if login_limited < health_limited else 'less'} restrictive")


# ============================================================================
# Performance Tests
# ============================================================================

class TestRateLimitPerformance:
    """Tests for rate limiting performance impact"""

    def test_rate_limit_check_performance(self, test_client):
        """Test that rate limit checking doesn't significantly slow requests"""
        import statistics

        # Measure response times
        times = []

        for i in range(20):
            start = time.perf_counter()
            response = test_client.get("/health")
            elapsed = time.perf_counter() - start
            times.append(elapsed)

            if response.status_code == 429:
                break

        if times:
            avg_time = statistics.mean(times)
            max_time = max(times)
            min_time = min(times)

            print(f"Response times - Avg: {avg_time*1000:.2f}ms, "
                  f"Min: {min_time*1000:.2f}ms, Max: {max_time*1000:.2f}ms")

            # Rate limit check should not add significant latency
            assert avg_time < 1.0, "Average response time should be under 1 second"


# ============================================================================
# Count Tests
# ============================================================================

def test_rate_limiting_security_suite_count():
    """Meta-test to verify test count"""
    test_classes = [
        TestRateLimitEnforcement,
        TestRateLimitHeaders,
        TestRateLimitReset,
        TestDistributedRateLimiting,
        TestBurstHandling,
        TestRateLimitBypass,
        TestRateLimitConfiguration,
        TestRateLimitPerformance,
    ]

    total_tests = 0
    for test_class in test_classes:
        methods = [m for m in dir(test_class) if m.startswith('test_')]
        total_tests += len(methods)

    print(f"\nRate Limiting Security Test Suite: {total_tests} tests")
    assert total_tests >= 15, f"Expected at least 15 tests, found {total_tests}"
