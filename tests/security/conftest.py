"""
Security Tests Configuration and Fixtures
Provides shared fixtures and utilities for security testing
"""

import pytest
import sys
import os
from datetime import datetime, timedelta
from typing import Generator, Dict, Any
from unittest.mock import patch, MagicMock

# Add project root to path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "services", "api-gateway"))

# Import FastAPI test utilities
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport


# ============================================================================
# Test Configuration Constants
# ============================================================================

# Test JWT secret key for consistent testing
TEST_JWT_SECRET = "test-secret-key-for-security-tests-32-chars-long"
TEST_JWT_ALGORITHM = "HS256"

# Test user credentials
TEST_USER = {
    "username": "testuser",
    "email": "testuser@example.com",
    "password": "TestPassword123!",
    "full_name": "Test User"
}

TEST_ADMIN_USER = {
    "username": "adminuser",
    "email": "admin@example.com",
    "password": "AdminPassword123!",
    "full_name": "Admin User"
}

# Malicious payloads for security testing
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

# Invalid input test cases
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
# Pytest Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def test_jwt_secret():
    """Provide test JWT secret key"""
    return TEST_JWT_SECRET


@pytest.fixture(scope="function")
def mock_jwt_settings():
    """Mock JWT settings for testing"""
    with patch.dict(os.environ, {
        "JWT_SECRET_KEY": TEST_JWT_SECRET,
        "ACCESS_TOKEN_EXPIRE_MINUTES": "30"
    }):
        yield


@pytest.fixture(scope="function")
def api_gateway_app(mock_jwt_settings):
    """Create API Gateway FastAPI application for testing"""
    # Clear any cached modules
    modules_to_remove = [key for key in sys.modules.keys()
                        if key.startswith('app') or key.startswith('services.api-gateway')]
    for mod in modules_to_remove:
        del sys.modules[mod]

    # Import with mocked settings
    try:
        from app.main import app
        return app
    except ImportError as e:
        pytest.skip(f"Could not import API Gateway app: {e}")


@pytest.fixture(scope="function")
def test_client(api_gateway_app):
    """Create synchronous test client for API Gateway"""
    with TestClient(api_gateway_app) as client:
        yield client


@pytest.fixture(scope="function")
async def async_client(api_gateway_app):
    """Create async test client for API Gateway"""
    transport = ASGITransport(app=api_gateway_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(scope="function")
def registered_user(test_client):
    """Register a test user and return credentials"""
    # Clear the user database first
    try:
        from app.auth_models import USERS_DB
        USERS_DB.clear()
    except ImportError:
        pass

    # Register new user
    response = test_client.post("/auth/register", json=TEST_USER)
    if response.status_code == 201:
        return TEST_USER.copy()
    elif response.status_code == 400 and "already registered" in response.text.lower():
        return TEST_USER.copy()
    else:
        pytest.skip(f"Could not register test user: {response.text}")


@pytest.fixture(scope="function")
def valid_token(test_client, registered_user):
    """Get a valid JWT token for testing"""
    response = test_client.post("/auth/login", json={
        "username": registered_user["username"],
        "password": registered_user["password"]
    })
    if response.status_code == 200:
        return response.json()["access_token"]
    pytest.skip(f"Could not get valid token: {response.text}")


@pytest.fixture(scope="function")
def auth_headers(valid_token):
    """Return authorization headers with valid token"""
    return {"Authorization": f"Bearer {valid_token}"}


@pytest.fixture(scope="function")
def expired_token():
    """Create an expired JWT token for testing"""
    try:
        from jose import jwt

        payload = {
            "sub": "testuser",
            "user_id": "user_test123",
            "exp": datetime.utcnow() - timedelta(hours=1),  # Expired 1 hour ago
            "iat": datetime.utcnow() - timedelta(hours=2),
            "type": "access"
        }
        return jwt.encode(payload, TEST_JWT_SECRET, algorithm=TEST_JWT_ALGORITHM)
    except ImportError:
        pytest.skip("jose library not available")


@pytest.fixture(scope="function")
def invalid_signature_token():
    """Create a token with invalid signature"""
    try:
        from jose import jwt

        payload = {
            "sub": "testuser",
            "user_id": "user_test123",
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iat": datetime.utcnow(),
            "type": "access"
        }
        # Sign with different secret
        return jwt.encode(payload, "wrong-secret-key-for-testing", algorithm=TEST_JWT_ALGORITHM)
    except ImportError:
        pytest.skip("jose library not available")


@pytest.fixture(scope="function")
def tampered_token(valid_token):
    """Create a tampered JWT token by modifying payload"""
    if not valid_token:
        pytest.skip("No valid token available")

    parts = valid_token.split('.')
    if len(parts) != 3:
        pytest.skip("Invalid token format")

    # Modify the payload part
    import base64
    try:
        payload = base64.urlsafe_b64decode(parts[1] + '==')
        # Just change the token slightly to invalidate signature
        parts[1] = base64.urlsafe_b64encode(payload + b'tampered').decode().rstrip('=')
        return '.'.join(parts)
    except Exception as e:
        pytest.skip(f"Could not create tampered token: {e}")


@pytest.fixture(scope="function")
def malformed_tokens():
    """Return list of malformed tokens for testing"""
    return [
        "",  # Empty token
        "not.a.token",  # Wrong format
        "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9",  # Only header
        "invalid.token.format.extra.parts",  # Too many parts
        "a.b.c",  # Too short
        "Bearer ",  # Just prefix
        " " * 100,  # Whitespace
        "null",  # Literal null
        "undefined",  # Literal undefined
        "\x00\x00\x00",  # Null bytes
    ]


@pytest.fixture(scope="function")
def rate_limit_test_params():
    """Parameters for rate limiting tests"""
    return {
        "requests_per_minute": 60,
        "burst_limit": 10,
        "test_endpoint": "/health"
    }


# ============================================================================
# Helper Functions
# ============================================================================

def create_test_token(
    username: str = "testuser",
    user_id: str = "user_test123",
    secret: str = TEST_JWT_SECRET,
    algorithm: str = TEST_JWT_ALGORITHM,
    expires_delta: timedelta = None,
    extra_claims: Dict[str, Any] = None
) -> str:
    """Create a custom JWT token for testing"""
    try:
        from jose import jwt

        if expires_delta is None:
            expires_delta = timedelta(hours=1)

        payload = {
            "sub": username,
            "user_id": user_id,
            "exp": datetime.utcnow() + expires_delta,
            "iat": datetime.utcnow(),
            "type": "access"
        }

        if extra_claims:
            payload.update(extra_claims)

        return jwt.encode(payload, secret, algorithm=algorithm)
    except ImportError:
        return None


def verify_error_response(response, expected_status: int, expected_detail: str = None):
    """Verify error response format and status"""
    assert response.status_code == expected_status, \
        f"Expected {expected_status}, got {response.status_code}: {response.text}"

    if expected_detail:
        data = response.json()
        assert "detail" in data, f"Missing 'detail' in response: {data}"
        assert expected_detail.lower() in data["detail"].lower(), \
            f"Expected '{expected_detail}' in detail, got: {data['detail']}"


def measure_response_time(client, method: str, url: str, **kwargs) -> float:
    """Measure response time for a request"""
    import time
    start = time.perf_counter()

    if method.upper() == "GET":
        client.get(url, **kwargs)
    elif method.upper() == "POST":
        client.post(url, **kwargs)
    elif method.upper() == "PUT":
        client.put(url, **kwargs)
    elif method.upper() == "DELETE":
        client.delete(url, **kwargs)

    return time.perf_counter() - start
