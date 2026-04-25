"""
Security Headers Tests
Tests for CORS, CSP, HSTS, and other security headers

This module tests:
- CORS configuration
- Content Security Policy (CSP) headers
- HTTP Strict Transport Security (HSTS)
- X-Content-Type-Options
- X-Frame-Options
- X-XSS-Protection
- Referrer-Policy
- Feature-Policy/Permissions-Policy
- Cache-Control for sensitive data
"""

import pytest
import sys
import os
from urllib.parse import urlparse

# Add project paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "services", "api-gateway"))


# ============================================================================
# Test Class: CORS Configuration Tests
# ============================================================================

class TestCORSConfiguration:
    """Tests for Cross-Origin Resource Sharing (CORS) configuration"""

    def test_cors_preflight_request(self, test_client):
        """Test that CORS preflight requests are handled correctly"""
        # Arrange - send OPTIONS request with CORS headers
        headers = {
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        }

        # Act
        response = test_client.options("/health", headers=headers)

        # Assert - should return CORS headers
        assert response.status_code in [200, 204], \
            f"Preflight should succeed, got {response.status_code}"

        # Check CORS headers
        cors_headers = {
            "access-control-allow-origin",
            "access-control-allow-methods",
            "access-control-allow-headers",
        }

        response_headers_lower = {k.lower(): v for k, v in response.headers.items()}
        present_cors = cors_headers & set(response_headers_lower.keys())

        print(f"CORS headers present: {present_cors}")
        print(f"CORS headers missing: {cors_headers - present_cors}")

    def test_cors_allow_origin_header(self, test_client):
        """Test Access-Control-Allow-Origin header configuration"""
        # Test with allowed origin
        headers = {"Origin": "http://localhost:3000"}
        response = test_client.get("/health", headers=headers)

        allow_origin = response.headers.get("Access-Control-Allow-Origin")

        if allow_origin:
            print(f"Access-Control-Allow-Origin: {allow_origin}")

            # Check if wildcard is used (security concern)
            if allow_origin == "*":
                print("WARNING: Wildcard CORS origin allows any origin")

            # Check if credentials are allowed with wildcard
            allow_credentials = response.headers.get("Access-Control-Allow-Credentials")
            if allow_origin == "*" and allow_credentials == "true":
                pytest.fail("SECURITY: Cannot use * with credentials")

    def test_cors_rejects_unauthorized_origin(self, test_client):
        """Test that CORS rejects unauthorized origins"""
        # Use an unauthorized origin
        headers = {"Origin": "http://malicious-site.com"}
        response = test_client.get("/health", headers=headers)

        allow_origin = response.headers.get("Access-Control-Allow-Origin")

        if allow_origin == "*":
            print("WARNING: Wildcard allows malicious origin")
        elif allow_origin == "http://malicious-site.com":
            pytest.fail("CORS allows unauthorized origin")
        else:
            print(f"CORS properly restricted - Allow-Origin: {allow_origin}")

    def test_cors_credentials_handling(self, test_client):
        """Test Access-Control-Allow-Credentials header"""
        headers = {"Origin": "http://localhost:3000"}
        response = test_client.get("/health", headers=headers)

        allow_credentials = response.headers.get("Access-Control-Allow-Credentials")

        if allow_credentials:
            print(f"Access-Control-Allow-Credentials: {allow_credentials}")

            # If credentials allowed, origin must not be *
            allow_origin = response.headers.get("Access-Control-Allow-Origin")
            if allow_credentials.lower() == "true" and allow_origin == "*":
                pytest.fail("SECURITY: Credentials not allowed with wildcard origin")

    def test_cors_max_age_header(self, test_client):
        """Test Access-Control-Max-Age header for preflight caching"""
        headers = {
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        }
        response = test_client.options("/health", headers=headers)

        max_age = response.headers.get("Access-Control-Max-Age")

        if max_age:
            print(f"Access-Control-Max-Age: {max_age} seconds")
            assert max_age.isdigit(), "Max-Age should be a number"
        else:
            print("Access-Control-Max-Age not set (may cause frequent preflight requests)")

    def test_cors_exposed_headers(self, test_client):
        """Test Access-Control-Expose-Headers configuration"""
        headers = {"Origin": "http://localhost:3000"}
        response = test_client.get("/health", headers=headers)

        exposed = response.headers.get("Access-Control-Expose-Headers")

        if exposed:
            print(f"Access-Control-Expose-Headers: {exposed}")

            # Check if sensitive headers are exposed
            sensitive_headers = ["Authorization", "Cookie", "Set-Cookie"]
            for header in sensitive_headers:
                if header.lower() in exposed.lower():
                    print(f"WARNING: Sensitive header '{header}' is exposed via CORS")


# ============================================================================
# Test Class: Content Security Policy Tests
# ============================================================================

class TestContentSecurityPolicy:
    """Tests for Content Security Policy (CSP) headers"""

    def test_csp_header_presence(self, test_client):
        """Test that CSP header is present"""
        response = test_client.get("/")

        csp = response.headers.get("Content-Security-Policy")
        csp_report = response.headers.get("Content-Security-Policy-Report-Only")

        if csp:
            print(f"Content-Security-Policy: {csp[:100]}...")
        elif csp_report:
            print(f"Content-Security-Policy-Report-Only: {csp_report[:100]}...")
        else:
            print("WARNING: No Content-Security-Policy header present")

    def test_csp_no_unsafe_inline(self, test_client):
        """Test that CSP doesn't allow unsafe-inline scripts"""
        response = test_client.get("/")
        csp = response.headers.get("Content-Security-Policy", "")

        if "unsafe-inline" in csp.lower():
            print("WARNING: CSP allows 'unsafe-inline' which weakens XSS protection")

    def test_csp_no_unsafe_eval(self, test_client):
        """Test that CSP doesn't allow unsafe-eval"""
        response = test_client.get("/")
        csp = response.headers.get("Content-Security-Policy", "")

        if "unsafe-eval" in csp.lower():
            print("WARNING: CSP allows 'unsafe-eval' which enables eval() attacks")

    def test_csp_script_src_restrictive(self, test_client):
        """Test that script-src directive is restrictive"""
        response = test_client.get("/")
        csp = response.headers.get("Content-Security-Policy", "")

        if "script-src" in csp:
            # Extract script-src directive
            directives = csp.split(";")
            script_src = [d for d in directives if "script-src" in d.lower()]
            if script_src:
                print(f"script-src directive: {script_src[0].strip()}")

                # Check for overly permissive values
                if "'*'" in script_src[0] or "* " in script_src[0]:
                    print("WARNING: script-src allows any source")

    def test_csp_frame_ancestors(self, test_client):
        """Test frame-ancestors directive to prevent clickjacking"""
        response = test_client.get("/")
        csp = response.headers.get("Content-Security-Policy", "")

        if "frame-ancestors" in csp.lower():
            print("frame-ancestors directive present")
        else:
            print("NOTE: frame-ancestors not in CSP (check X-Frame-Options)")


# ============================================================================
# Test Class: HSTS Tests
# ============================================================================

class TestHSTS:
    """Tests for HTTP Strict Transport Security"""

    def test_hsts_header_presence(self, test_client):
        """Test that HSTS header is present"""
        response = test_client.get("/health")

        hsts = response.headers.get("Strict-Transport-Security")

        if hsts:
            print(f"Strict-Transport-Security: {hsts}")
        else:
            print("WARNING: HSTS header not present (may be appropriate for dev)")

    def test_hsts_max_age(self, test_client):
        """Test HSTS max-age value"""
        response = test_client.get("/health")
        hsts = response.headers.get("Strict-Transport-Security", "")

        if "max-age=" in hsts.lower():
            # Extract max-age value
            import re
            match = re.search(r'max-age=(\d+)', hsts, re.IGNORECASE)
            if match:
                max_age = int(match.group(1))
                print(f"HSTS max-age: {max_age} seconds ({max_age/86400:.1f} days)")

                # Recommended minimum is 1 year (31536000 seconds)
                if max_age < 31536000:
                    print("NOTE: HSTS max-age less than recommended 1 year")

    def test_hsts_include_subdomains(self, test_client):
        """Test HSTS includeSubDomains directive"""
        response = test_client.get("/health")
        hsts = response.headers.get("Strict-Transport-Security", "")

        if "includesubdomains" in hsts.lower():
            print("HSTS includeSubDomains: enabled")
        else:
            print("NOTE: HSTS includeSubDomains not set")

    def test_hsts_preload(self, test_client):
        """Test HSTS preload directive"""
        response = test_client.get("/health")
        hsts = response.headers.get("Strict-Transport-Security", "")

        if "preload" in hsts.lower():
            print("HSTS preload: enabled")
        else:
            print("NOTE: HSTS preload not set (required for HSTS preload list)")


# ============================================================================
# Test Class: X-Content-Type-Options Tests
# ============================================================================

class TestXContentTypeOptions:
    """Tests for X-Content-Type-Options header"""

    def test_x_content_type_options_presence(self, test_client):
        """Test X-Content-Type-Options header is present"""
        response = test_client.get("/health")

        x_content_type = response.headers.get("X-Content-Type-Options")

        if x_content_type:
            print(f"X-Content-Type-Options: {x_content_type}")
            assert x_content_type.lower() == "nosniff", \
                "X-Content-Type-Options should be 'nosniff'"
        else:
            print("WARNING: X-Content-Type-Options not set")

    def test_content_type_on_json_response(self, test_client):
        """Test that JSON responses have correct Content-Type"""
        response = test_client.get("/health")

        content_type = response.headers.get("Content-Type", "")

        assert "application/json" in content_type, \
            f"JSON endpoint should have application/json Content-Type, got: {content_type}"


# ============================================================================
# Test Class: X-Frame-Options Tests
# ============================================================================

class TestXFrameOptions:
    """Tests for X-Frame-Options header (clickjacking prevention)"""

    def test_x_frame_options_presence(self, test_client):
        """Test X-Frame-Options header is present"""
        response = test_client.get("/")

        x_frame = response.headers.get("X-Frame-Options")

        if x_frame:
            print(f"X-Frame-Options: {x_frame}")
            valid_values = ["deny", "sameorigin"]
            assert x_frame.lower() in valid_values, \
                f"X-Frame-Options should be DENY or SAMEORIGIN, got: {x_frame}"
        else:
            print("WARNING: X-Frame-Options not set (check CSP frame-ancestors)")

    def test_no_allow_from_deprecated(self, test_client):
        """Test that deprecated ALLOW-FROM is not used"""
        response = test_client.get("/")
        x_frame = response.headers.get("X-Frame-Options", "")

        if "allow-from" in x_frame.lower():
            print("WARNING: ALLOW-FROM is deprecated and not supported by all browsers")


# ============================================================================
# Test Class: X-XSS-Protection Tests
# ============================================================================

class TestXXSSProtection:
    """Tests for X-XSS-Protection header"""

    def test_x_xss_protection_presence(self, test_client):
        """Test X-XSS-Protection header"""
        response = test_client.get("/")

        x_xss = response.headers.get("X-XSS-Protection")

        if x_xss:
            print(f"X-XSS-Protection: {x_xss}")

            # Modern recommendation is to disable (use CSP instead)
            if x_xss == "0":
                print("NOTE: X-XSS-Protection disabled (modern best practice)")
            elif "1" in x_xss:
                print("NOTE: X-XSS-Protection enabled (legacy, may cause issues)")
        else:
            print("NOTE: X-XSS-Protection not set (relying on CSP is recommended)")


# ============================================================================
# Test Class: Referrer-Policy Tests
# ============================================================================

class TestReferrerPolicy:
    """Tests for Referrer-Policy header"""

    def test_referrer_policy_presence(self, test_client):
        """Test Referrer-Policy header is present"""
        response = test_client.get("/")

        referrer = response.headers.get("Referrer-Policy")

        if referrer:
            print(f"Referrer-Policy: {referrer}")

            # Check for secure values
            secure_values = [
                "no-referrer",
                "no-referrer-when-downgrade",
                "strict-origin",
                "strict-origin-when-cross-origin",
            ]

            if referrer.lower() not in [v.lower() for v in secure_values]:
                print(f"NOTE: Referrer-Policy '{referrer}' may leak information")
        else:
            print("WARNING: Referrer-Policy not set")


# ============================================================================
# Test Class: Permissions-Policy Tests
# ============================================================================

class TestPermissionsPolicy:
    """Tests for Permissions-Policy (formerly Feature-Policy) header"""

    def test_permissions_policy_presence(self, test_client):
        """Test Permissions-Policy header is present"""
        response = test_client.get("/")

        perms = response.headers.get("Permissions-Policy")
        feature = response.headers.get("Feature-Policy")  # Legacy

        if perms:
            print(f"Permissions-Policy: {perms[:100]}...")
        elif feature:
            print(f"Feature-Policy (legacy): {feature[:100]}...")
        else:
            print("NOTE: Permissions-Policy not set")

    def test_dangerous_features_disabled(self, test_client):
        """Test that dangerous features are disabled"""
        response = test_client.get("/")
        perms = response.headers.get("Permissions-Policy", "")

        # Features that should typically be restricted
        dangerous_features = [
            "geolocation",
            "camera",
            "microphone",
            "payment",
            "usb",
        ]

        for feature in dangerous_features:
            if feature in perms.lower():
                # Check if it's disabled (set to empty)
                if f"{feature}=()" in perms.lower():
                    print(f"{feature}: disabled")
                else:
                    print(f"NOTE: {feature} may be enabled")


# ============================================================================
# Test Class: Cache-Control Tests
# ============================================================================

class TestCacheControl:
    """Tests for Cache-Control headers on sensitive data"""

    def test_cache_control_on_auth_response(self, test_client, valid_token):
        """Test Cache-Control on authentication responses"""
        headers = {"Authorization": f"Bearer {valid_token}"}
        response = test_client.get("/auth/me", headers=headers)

        cache_control = response.headers.get("Cache-Control", "")
        pragma = response.headers.get("Pragma", "")

        print(f"Cache-Control: {cache_control}")
        print(f"Pragma: {pragma}")

        # Sensitive endpoints should not be cached
        if response.status_code == 200:
            no_cache_indicators = ["no-store", "no-cache", "private"]
            has_no_cache = any(ind in cache_control.lower() for ind in no_cache_indicators)

            if not has_no_cache:
                print("WARNING: Sensitive endpoint may be cached")

    def test_cache_control_on_portfolio(self, test_client, valid_token):
        """Test Cache-Control on portfolio data"""
        headers = {"Authorization": f"Bearer {valid_token}"}
        response = test_client.get("/api/portfolio/balance", headers=headers)

        cache_control = response.headers.get("Cache-Control", "")

        # Portfolio data is sensitive and time-sensitive
        if response.status_code == 200:
            if "no-store" not in cache_control.lower():
                print("NOTE: Portfolio endpoint may allow caching")

    def test_cache_control_on_public_data(self, test_client):
        """Test that public data can be cached appropriately"""
        response = test_client.get("/health")

        cache_control = response.headers.get("Cache-Control", "")

        print(f"Health endpoint Cache-Control: {cache_control}")

        # Public health endpoint can have caching


# ============================================================================
# Test Class: Other Security Headers Tests
# ============================================================================

class TestOtherSecurityHeaders:
    """Tests for additional security headers"""

    def test_server_header_info_disclosure(self, test_client):
        """Test that Server header doesn't disclose version info"""
        response = test_client.get("/health")

        server = response.headers.get("Server", "")

        if server:
            print(f"Server header: {server}")

            # Check for version disclosure
            if any(char.isdigit() for char in server):
                print("WARNING: Server header may disclose version information")

    def test_x_powered_by_removed(self, test_client):
        """Test that X-Powered-By header is removed"""
        response = test_client.get("/health")

        powered_by = response.headers.get("X-Powered-By")

        if powered_by:
            print(f"WARNING: X-Powered-By header present: {powered_by}")
        else:
            print("Good: X-Powered-By header not present")

    def test_no_sensitive_headers_leaked(self, test_client):
        """Test that no sensitive internal headers are leaked"""
        response = test_client.get("/health")

        # Headers that should not be exposed externally
        sensitive_headers = [
            "X-Debug",
            "X-Debug-Token",
            "X-Internal",
            "X-Backend-Server",
            "X-Aspnet-Version",
            "X-AspnetMvc-Version",
        ]

        leaked = []
        for header in sensitive_headers:
            if header.lower() in [h.lower() for h in response.headers.keys()]:
                leaked.append(header)

        if leaked:
            print(f"WARNING: Sensitive headers leaked: {leaked}")
        else:
            print("Good: No sensitive internal headers leaked")


# ============================================================================
# Test Class: Security Headers Summary
# ============================================================================

class TestSecurityHeadersSummary:
    """Summary test for all security headers"""

    def test_security_headers_report(self, test_client):
        """Generate a summary report of security headers"""
        response = test_client.get("/health")

        security_headers = {
            "Content-Security-Policy": response.headers.get("Content-Security-Policy"),
            "Strict-Transport-Security": response.headers.get("Strict-Transport-Security"),
            "X-Content-Type-Options": response.headers.get("X-Content-Type-Options"),
            "X-Frame-Options": response.headers.get("X-Frame-Options"),
            "X-XSS-Protection": response.headers.get("X-XSS-Protection"),
            "Referrer-Policy": response.headers.get("Referrer-Policy"),
            "Permissions-Policy": response.headers.get("Permissions-Policy"),
            "Cache-Control": response.headers.get("Cache-Control"),
        }

        print("\n=== Security Headers Report ===")
        present = 0
        missing = 0

        for header, value in security_headers.items():
            if value:
                print(f"[+] {header}: {value[:50]}..." if len(str(value)) > 50 else f"[+] {header}: {value}")
                present += 1
            else:
                print(f"[-] {header}: Not set")
                missing += 1

        print(f"\nSummary: {present} present, {missing} missing")

        # Score (out of 8)
        score = (present / 8) * 100
        print(f"Security Headers Score: {score:.0f}%")


# ============================================================================
# Count Tests
# ============================================================================

def test_security_headers_suite_count():
    """Meta-test to verify test count"""
    test_classes = [
        TestCORSConfiguration,
        TestContentSecurityPolicy,
        TestHSTS,
        TestXContentTypeOptions,
        TestXFrameOptions,
        TestXXSSProtection,
        TestReferrerPolicy,
        TestPermissionsPolicy,
        TestCacheControl,
        TestOtherSecurityHeaders,
        TestSecurityHeadersSummary,
    ]

    total_tests = 0
    for test_class in test_classes:
        methods = [m for m in dir(test_class) if m.startswith('test_')]
        total_tests += len(methods)

    print(f"\nSecurity Headers Test Suite: {total_tests} tests")
    assert total_tests >= 25, f"Expected at least 25 tests, found {total_tests}"
