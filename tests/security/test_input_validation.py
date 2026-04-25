"""
Input Validation Security Tests
Tests for SQL injection, XSS, and input validation vulnerabilities

This module tests:
- SQL injection prevention
- Cross-site scripting (XSS) prevention
- Input validation for all endpoints
- Negative quantity/price handling
- Oversized request handling
- Special character handling
- Path traversal prevention
- Command injection prevention
"""

import pytest
import json
import sys
import os
from typing import List

# Add project paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "services", "api-gateway"))

# Malicious payloads for security testing (defined locally to avoid import issues)
SQL_INJECTION_PAYLOADS = [
    "'; DROP TABLE users; --",
    "' OR '1'='1",
    "1; SELECT * FROM users",
    "admin'--",
    "' UNION SELECT * FROM users--",
    "1' AND '1'='1",
    "'; INSERT INTO users VALUES('hacker', 'hacker@evil.com');--",
    "1; TRUNCATE TABLE users;--",
    "' OR 1=1 LIMIT 1;--",
    "admin') OR ('1'='1",
]

XSS_PAYLOADS = [
    "<script>alert('XSS')</script>",
    "<img src=x onerror=alert('XSS')>",
    "<svg onload=alert('XSS')>",
    "javascript:alert('XSS')",
    "<body onload=alert('XSS')>",
    "<iframe src='javascript:alert(1)'></iframe>",
    "'\"><script>alert('XSS')</script>",
    "<a href='javascript:alert(1)'>click</a>",
    "<input onfocus=alert(1) autofocus>",
    "<marquee onstart=alert('XSS')>",
]

PATH_TRAVERSAL_PAYLOADS = [
    "../../../etc/passwd",
    "..\\..\\..\\windows\\system32\\config\\sam",
    "....//....//....//etc/passwd",
    "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "..%252f..%252f..%252fetc/passwd",
    "/etc/passwd",
    "C:\\Windows\\System32\\config\\SAM",
]

COMMAND_INJECTION_PAYLOADS = [
    "; ls -la",
    "| cat /etc/passwd",
    "& whoami",
    "`whoami`",
    "$(whoami)",
    "; rm -rf /",
    "|| cat /etc/passwd",
    "&& id",
]

INVALID_SYMBOLS = [
    "",  # Empty string
    " " * 100,  # Whitespace only
    "A" * 1000,  # Extremely long
    "BTCUSDT\x00",  # Null byte injection
    "BTC<>USDT",  # Special characters
    "../BTCUSDT",  # Path traversal attempt
    "BTC'USDT",  # SQL injection character
    "BTC\"USDT",  # Quote injection
    "BTC;USDT",  # Command separator
    "BTC|USDT",  # Pipe character
]


# ============================================================================
# Test Class: SQL Injection Prevention Tests
# ============================================================================

class TestSQLInjectionPrevention:
    """Tests for SQL injection attack prevention"""

    @pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
    def test_sql_injection_in_symbol_parameter(self, test_client, payload):
        """Test SQL injection attempts in symbol parameter are blocked"""
        # Arrange - try SQL injection in symbol parameter
        encoded_payload = payload.replace("'", "%27").replace(" ", "%20")

        # Act
        response = test_client.get(f"/api/market/ticker/{encoded_payload}")

        # Assert - should not return 500 (which might indicate SQL error)
        # Valid responses: 400 (bad request), 404 (not found), 422 (validation error)
        assert response.status_code != 500, \
            f"SQL injection payload may have caused server error: {payload}"

        # Should not contain SQL error messages
        response_text = response.text.lower()
        sql_errors = ["sql", "syntax error", "database", "query", "mysql", "postgresql"]
        for error in sql_errors:
            assert error not in response_text, \
                f"Response may contain SQL error message for payload: {payload}"

    @pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
    def test_sql_injection_in_login_username(self, test_client, payload):
        """Test SQL injection attempts in login username are blocked"""
        # Arrange
        login_data = {
            "username": payload,
            "password": "AnyPassword123!"
        }

        # Act
        response = test_client.post("/auth/login", json=login_data)

        # Assert
        assert response.status_code in [401, 422], \
            f"SQL injection in username should fail gracefully: {payload}"

        # Should not expose SQL errors
        response_text = response.text.lower()
        assert "sql" not in response_text
        assert "syntax error" not in response_text

    @pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
    def test_sql_injection_in_registration(self, test_client, payload):
        """Test SQL injection attempts in registration are blocked"""
        # Arrange
        register_data = {
            "username": payload[:50],  # Truncate to fit validation
            "email": "sqli@example.com",
            "password": "ValidPassword123!",
            "full_name": payload
        }

        # Act
        response = test_client.post("/auth/register", json=register_data)

        # Assert - should be rejected or handled safely
        assert response.status_code in [400, 422], \
            f"SQL injection in registration should be rejected: {payload}"

    def test_sql_injection_in_query_params(self, test_client):
        """Test SQL injection in query parameters"""
        # Test various endpoints with SQL injection in query params
        endpoints = [
            "/api/market/kline/BTCUSDT?interval='; DROP TABLE users;--",
            "/api/market/klines/BTCUSDT?limit=1; DELETE FROM trades;--",
            "/api/portfolio?portfolio_id=' OR '1'='1",
            "/api/trading/positions?status=' UNION SELECT * FROM users--",
        ]

        for endpoint in endpoints:
            response = test_client.get(endpoint)

            # Should not cause server error
            assert response.status_code != 500, \
                f"SQL injection in query param may have caused error: {endpoint}"


# ============================================================================
# Test Class: XSS Prevention Tests
# ============================================================================

class TestXSSPrevention:
    """Tests for Cross-Site Scripting (XSS) attack prevention"""

    @pytest.mark.parametrize("payload", XSS_PAYLOADS)
    def test_xss_in_symbol_parameter(self, test_client, payload):
        """Test XSS payloads in symbol parameter are sanitized"""
        # Arrange
        import urllib.parse
        encoded_payload = urllib.parse.quote(payload, safe='')

        # Act
        response = test_client.get(f"/api/market/ticker/{encoded_payload}")

        # Assert - response should not contain raw script
        if response.status_code == 200:
            response_text = response.text
            assert "<script>" not in response_text.lower(), \
                f"XSS payload was reflected: {payload}"
            assert "javascript:" not in response_text.lower(), \
                f"JavaScript URI was reflected: {payload}"
            assert "onerror=" not in response_text.lower(), \
                f"Event handler was reflected: {payload}"

    @pytest.mark.parametrize("payload", XSS_PAYLOADS)
    def test_xss_in_registration_full_name(self, test_client, payload):
        """Test XSS payloads in registration full_name are sanitized"""
        # Arrange
        import hashlib
        unique_suffix = hashlib.md5(payload.encode()).hexdigest()[:8]

        register_data = {
            "username": f"xsstest{unique_suffix}",
            "email": f"xss_{unique_suffix}@example.com",
            "password": "ValidPassword123!",
            "full_name": payload
        }

        # Act
        response = test_client.post("/auth/register", json=register_data)

        # Assert - either rejected or sanitized
        if response.status_code == 201:
            # If accepted, verify it doesn't contain raw XSS
            response_text = response.text
            assert "<script>" not in response_text.lower(), \
                f"XSS payload in response: {payload}"

    @pytest.mark.parametrize("payload", XSS_PAYLOADS)
    def test_xss_in_login_error_response(self, test_client, payload):
        """Test that XSS in username doesn't reflect in error messages"""
        # Arrange
        login_data = {
            "username": payload,
            "password": "SomePassword123!"
        }

        # Act
        response = test_client.post("/auth/login", json=login_data)

        # Assert - error message should not reflect XSS payload
        response_text = response.text
        assert "<script>" not in response_text.lower(), \
            f"XSS reflected in error response: {payload}"

    def test_xss_in_json_response(self, test_client):
        """Test that JSON responses have proper content type"""
        # Act
        response = test_client.get("/health")

        # Assert - should have JSON content type
        content_type = response.headers.get("content-type", "")
        assert "application/json" in content_type, \
            "Response should have JSON content type to prevent XSS"


# ============================================================================
# Test Class: Invalid Symbol Name Tests
# ============================================================================

class TestInvalidSymbolNames:
    """Tests for invalid symbol name handling"""

    @pytest.mark.parametrize("invalid_symbol", INVALID_SYMBOLS)
    def test_invalid_symbol_in_ticker(self, test_client, invalid_symbol):
        """Test handling of invalid symbol names in ticker endpoint"""
        # Arrange
        import urllib.parse
        encoded_symbol = urllib.parse.quote(invalid_symbol, safe='')

        # Act
        response = test_client.get(f"/api/market/ticker/{encoded_symbol}")

        # Assert - should not cause server error
        assert response.status_code != 500, \
            f"Invalid symbol '{invalid_symbol[:20]}' caused server error"

    @pytest.mark.parametrize("invalid_symbol", INVALID_SYMBOLS)
    def test_invalid_symbol_in_klines(self, test_client, invalid_symbol):
        """Test handling of invalid symbol names in klines endpoint"""
        # Arrange
        import urllib.parse
        encoded_symbol = urllib.parse.quote(invalid_symbol, safe='')

        # Act
        response = test_client.get(f"/api/market/klines/{encoded_symbol}")

        # Assert
        assert response.status_code != 500, \
            f"Invalid symbol '{invalid_symbol[:20]}' caused server error"

    @pytest.mark.parametrize("invalid_symbol", INVALID_SYMBOLS)
    def test_invalid_symbol_in_signals(self, test_client, invalid_symbol):
        """Test handling of invalid symbol names in signals endpoint"""
        # Arrange
        import urllib.parse
        encoded_symbol = urllib.parse.quote(invalid_symbol, safe='')

        # Act
        response = test_client.get(f"/api/trading/signals/{encoded_symbol}")

        # Assert
        assert response.status_code != 500, \
            f"Invalid symbol '{invalid_symbol[:20]}' caused server error"

    def test_symbol_with_null_byte(self, test_client):
        """Test symbol with null byte injection"""
        # Act
        response = test_client.get("/api/market/ticker/BTCUSDT%00malicious")

        # Assert - should be rejected or handled safely
        assert response.status_code != 500


# ============================================================================
# Test Class: Negative Values Tests
# ============================================================================

class TestNegativeValues:
    """Tests for negative quantity and price handling"""

    def test_negative_quantity_in_buy(self, test_client, auth_headers):
        """Test that negative quantities are rejected in buy orders"""
        # Arrange
        params = {
            "portfolio_id": "default",
            "symbol": "BTCUSDT",
            "quantity": "-10",
            "price": "50000"
        }

        # Act
        response = test_client.post("/api/portfolio/buy", params=params, headers=auth_headers)

        # Assert - should be rejected
        assert response.status_code in [400, 422, 401, 403, 502], \
            "Negative quantity should be handled"

    def test_negative_price_in_buy(self, test_client, auth_headers):
        """Test that negative prices are rejected in buy orders"""
        # Arrange
        params = {
            "portfolio_id": "default",
            "symbol": "BTCUSDT",
            "quantity": "1",
            "price": "-50000"
        }

        # Act
        response = test_client.post("/api/portfolio/buy", params=params, headers=auth_headers)

        # Assert - should be rejected
        assert response.status_code in [400, 422, 401, 403, 502], \
            "Negative price should be handled"

    def test_negative_quantity_in_sell(self, test_client, auth_headers):
        """Test that negative quantities are rejected in sell orders"""
        # Arrange
        params = {
            "portfolio_id": "default",
            "symbol": "BTCUSDT",
            "quantity": "-5",
            "price": "50000"
        }

        # Act
        response = test_client.post("/api/portfolio/sell", params=params, headers=auth_headers)

        # Assert
        assert response.status_code in [400, 422, 401, 403, 502], \
            "Negative quantity should be handled"

    def test_zero_quantity(self, test_client, auth_headers):
        """Test that zero quantity is rejected"""
        # Arrange
        params = {
            "portfolio_id": "default",
            "symbol": "BTCUSDT",
            "quantity": "0",
            "price": "50000"
        }

        # Act
        response = test_client.post("/api/portfolio/buy", params=params, headers=auth_headers)

        # Assert - zero quantity should be handled
        assert response.status_code in [400, 422, 401, 403, 502], \
            "Zero quantity should be handled"

    def test_extremely_large_quantity(self, test_client, auth_headers):
        """Test that extremely large quantities are handled"""
        # Arrange
        params = {
            "portfolio_id": "default",
            "symbol": "BTCUSDT",
            "quantity": "999999999999999999999999999999",
            "price": "50000"
        }

        # Act
        response = test_client.post("/api/portfolio/buy", params=params, headers=auth_headers)

        # Assert - should be rejected or handled safely
        assert response.status_code != 500, \
            "Extremely large quantity should not cause server error"

    def test_negative_kline_limit(self, test_client):
        """Test negative limit parameter in klines request"""
        # Act
        response = test_client.get("/api/market/klines/BTCUSDT?limit=-100")

        # Assert
        assert response.status_code in [400, 422] or response.status_code != 500, \
            "Negative limit should not cause server error"

    def test_negative_rsi_period(self, test_client):
        """Test negative period parameter in RSI request"""
        # Act
        response = test_client.get("/api/analysis/rsi/BTCUSDT?period=-14")

        # Assert
        assert response.status_code != 500, \
            "Negative RSI period should not cause server error"


# ============================================================================
# Test Class: Oversized Request Tests
# ============================================================================

class TestOversizedRequests:
    """Tests for oversized request handling"""

    def test_oversized_json_body(self, test_client):
        """Test handling of oversized JSON request body"""
        # Arrange - create very large JSON payload
        large_data = {
            "username": "a" * 10000,
            "email": "test@example.com",
            "password": "ValidPassword123!",
            "full_name": "b" * 100000
        }

        # Act
        response = test_client.post("/auth/register", json=large_data)

        # Assert - should be rejected (422 or 400) not cause server error (500)
        assert response.status_code in [400, 413, 422], \
            f"Oversized request should be rejected, got {response.status_code}"

    def test_oversized_symbol(self, test_client):
        """Test handling of very long symbol name"""
        # Arrange
        long_symbol = "A" * 10000

        # Act
        response = test_client.get(f"/api/market/ticker/{long_symbol}")

        # Assert
        assert response.status_code in [400, 404, 414, 422] or response.status_code != 500, \
            "Oversized symbol should not cause server error"

    def test_many_query_parameters(self, test_client):
        """Test handling of many query parameters"""
        # Arrange - add many query parameters
        params = "&".join([f"param{i}=value{i}" for i in range(1000)])
        url = f"/api/market/ticker/BTCUSDT?{params}"

        # Act
        response = test_client.get(url)

        # Assert - should handle gracefully
        assert response.status_code != 500, \
            "Many query parameters should not cause server error"

    def test_deeply_nested_json(self, test_client):
        """Test handling of deeply nested JSON"""
        # Arrange - create deeply nested structure
        nested = {"level": "0"}
        current = nested
        for i in range(100):
            current["nested"] = {"level": str(i)}
            current = current["nested"]

        # Act
        response = test_client.post("/auth/register", json=nested)

        # Assert
        assert response.status_code in [400, 422], \
            "Deeply nested JSON should be rejected"


# ============================================================================
# Test Class: Path Traversal Prevention Tests
# ============================================================================

class TestPathTraversalPrevention:
    """Tests for path traversal attack prevention"""

    @pytest.mark.parametrize("payload", PATH_TRAVERSAL_PAYLOADS)
    def test_path_traversal_in_symbol(self, test_client, payload):
        """Test path traversal attempts in symbol parameter"""
        # Arrange
        import urllib.parse
        encoded_payload = urllib.parse.quote(payload, safe='')

        # Act
        response = test_client.get(f"/api/market/ticker/{encoded_payload}")

        # Assert - should not return file contents
        response_text = response.text.lower()
        assert "root:" not in response_text, \
            f"Path traversal may have succeeded: {payload}"
        assert "[boot loader]" not in response_text.lower(), \
            f"Path traversal may have succeeded: {payload}"

    @pytest.mark.parametrize("payload", PATH_TRAVERSAL_PAYLOADS)
    def test_path_traversal_in_query_param(self, test_client, payload):
        """Test path traversal in query parameters"""
        # Arrange
        import urllib.parse
        encoded_payload = urllib.parse.quote(payload, safe='')

        # Act
        response = test_client.get(f"/api/portfolio?portfolio_id={encoded_payload}")

        # Assert
        assert response.status_code != 500
        response_text = response.text.lower()
        assert "root:" not in response_text


# ============================================================================
# Test Class: Command Injection Prevention Tests
# ============================================================================

class TestCommandInjectionPrevention:
    """Tests for command injection attack prevention"""

    @pytest.mark.parametrize("payload", COMMAND_INJECTION_PAYLOADS)
    def test_command_injection_in_symbol(self, test_client, payload):
        """Test command injection attempts in symbol parameter"""
        # Arrange
        import urllib.parse
        encoded_payload = urllib.parse.quote(payload, safe='')

        # Act
        response = test_client.get(f"/api/market/ticker/{encoded_payload}")

        # Assert - should not execute command
        response_text = response.text.lower()
        # Check for typical command output indicators
        assert "uid=" not in response_text, \
            f"Command injection may have succeeded: {payload}"
        assert "gid=" not in response_text, \
            f"Command injection may have succeeded: {payload}"

    @pytest.mark.parametrize("payload", COMMAND_INJECTION_PAYLOADS)
    def test_command_injection_in_registration(self, test_client, payload):
        """Test command injection in registration fields"""
        # Arrange
        register_data = {
            "username": f"cmdtest_{abs(hash(payload)) % 10000}",
            "email": f"cmd_{abs(hash(payload)) % 10000}@example.com",
            "password": "ValidPassword123!",
            "full_name": payload
        }

        # Act
        response = test_client.post("/auth/register", json=register_data)

        # Assert
        assert response.status_code in [201, 400, 422], \
            f"Command injection should be handled: {payload}"


# ============================================================================
# Test Class: Special Character Handling Tests
# ============================================================================

class TestSpecialCharacterHandling:
    """Tests for special character handling in inputs"""

    @pytest.mark.parametrize("special_char", [
        "\n", "\r", "\t",  # Whitespace
        "\x00", "\x1f",  # Control characters
        "\u0000", "\uffff",  # Unicode extremes
        "&", "|", ";",  # Shell metacharacters
        "$", "`",  # Variable/command substitution
        "\\", "/",  # Path separators
        "'", '"', "`",  # Quotes
        "<", ">",  # HTML/XML
        "{", "}", "[", "]",  # Brackets
    ])
    def test_special_characters_in_symbol(self, test_client, special_char):
        """Test special characters in symbol parameter"""
        # Arrange
        import urllib.parse
        test_symbol = f"BTC{special_char}USDT"
        encoded_symbol = urllib.parse.quote(test_symbol, safe='')

        # Act
        response = test_client.get(f"/api/market/ticker/{encoded_symbol}")

        # Assert - should not cause server error
        assert response.status_code != 500, \
            f"Special character '{repr(special_char)}' caused server error"

    def test_unicode_symbols(self, test_client):
        """Test handling of unicode in symbol names"""
        # Arrange
        unicode_symbols = [
            "BTC\u200bUSDT",  # Zero-width space
            "BTC\u00a0USDT",  # Non-breaking space
            "\u4e2d\u6587USDT",  # Chinese characters
            "\U0001f4b0USDT",  # Emoji (money bag)
            "BTC\u202eUSDT",  # Right-to-left override
        ]

        for symbol in unicode_symbols:
            import urllib.parse
            encoded = urllib.parse.quote(symbol, safe='')

            response = test_client.get(f"/api/market/ticker/{encoded}")

            assert response.status_code != 500, \
                f"Unicode symbol '{repr(symbol)}' caused server error"


# ============================================================================
# Test Class: Content Type Validation Tests
# ============================================================================

class TestContentTypeValidation:
    """Tests for content type validation"""

    def test_wrong_content_type_for_json_endpoint(self, test_client):
        """Test that wrong content type is handled"""
        # Arrange
        headers = {"Content-Type": "text/plain"}
        data = "username=test&password=test"

        # Act
        response = test_client.post("/auth/login", data=data, headers=headers)

        # Assert - should be rejected
        assert response.status_code == 422, \
            "Wrong content type should be rejected"

    def test_multipart_form_when_json_expected(self, test_client):
        """Test that multipart form is handled when JSON expected"""
        # Act
        response = test_client.post(
            "/auth/login",
            data={"username": "test", "password": "test"}
        )

        # Assert
        assert response.status_code in [400, 422], \
            "Multipart form should be rejected when JSON expected"


# ============================================================================
# Count Tests
# ============================================================================

def test_input_validation_security_suite_count():
    """Meta-test to verify test count"""
    test_classes = [
        TestSQLInjectionPrevention,
        TestXSSPrevention,
        TestInvalidSymbolNames,
        TestNegativeValues,
        TestOversizedRequests,
        TestPathTraversalPrevention,
        TestCommandInjectionPrevention,
        TestSpecialCharacterHandling,
        TestContentTypeValidation,
    ]

    total_tests = 0
    for test_class in test_classes:
        methods = [m for m in dir(test_class) if m.startswith('test_')]
        total_tests += len(methods)

    print(f"\nInput Validation Security Test Suite: {total_tests} base tests")
    assert total_tests >= 20, f"Expected at least 20 base tests, found {total_tests}"
