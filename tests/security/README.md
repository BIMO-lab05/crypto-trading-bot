# Security Test Suite

## Overview

This directory contains comprehensive security tests for the Crypto Trading Bot API. The tests cover authentication, authorization, input validation, rate limiting, and security headers.

## Test Files

| File | Description | Test Count |
|------|-------------|------------|
| `test_authentication.py` | JWT validation, password security, login/logout flows | ~35+ |
| `test_input_validation.py` | SQL injection, XSS, input sanitization | ~50+ |
| `test_authorization.py` | Access control, permissions, privilege escalation | ~35+ |
| `test_rate_limiting.py` | Rate limit enforcement, headers, bypass prevention | ~20+ |
| `test_security_headers.py` | CORS, CSP, HSTS, security headers | ~30+ |

**Total: 170+ security tests**

## Running Security Tests

### Run All Security Tests

```bash
# From project root
cd /mnt/d/Bimo_max/crypto-trading-bot

# Run all security tests
pytest tests/security/ -v --tb=short

# Run with coverage
pytest tests/security/ --cov=services/api-gateway/app --cov-report=html --cov-report=term

# Run with detailed output
pytest tests/security/ -v --tb=long -s
```

### Run Specific Test Categories

```bash
# Authentication tests only
pytest tests/security/test_authentication.py -v

# Input validation tests only
pytest tests/security/test_input_validation.py -v

# Authorization tests only
pytest tests/security/test_authorization.py -v

# Rate limiting tests only
pytest tests/security/test_rate_limiting.py -v

# Security headers tests only
pytest tests/security/test_security_headers.py -v
```

### Run Tests with Markers

```bash
# Run only parametrized tests
pytest tests/security/ -v -k "parametrize"

# Run SQL injection tests
pytest tests/security/ -v -k "sql_injection"

# Run XSS tests
pytest tests/security/ -v -k "xss"
```

### Run Tests in Parallel

```bash
# Install pytest-xdist if not available
pip install pytest-xdist

# Run tests in parallel
pytest tests/security/ -n auto -v
```

## Test Categories

### 1. Authentication Tests (`test_authentication.py`)

Tests for JWT token security and authentication flows:

- **JWT Token Validation**
  - Valid token acceptance
  - Expired token rejection
  - Invalid signature rejection
  - Tampered token rejection
  - Malformed token handling
  - Token type validation

- **Authentication Endpoints**
  - Successful login flow
  - Wrong password handling
  - Non-existent user handling
  - Timing attack prevention
  - Duplicate registration prevention

- **Password Security**
  - Weak password rejection
  - Password complexity enforcement
  - Common password blocking

- **Username Validation**
  - Reserved username blocking
  - Special character handling
  - Length validation

### 2. Input Validation Tests (`test_input_validation.py`)

Tests for preventing injection attacks and input abuse:

- **SQL Injection Prevention**
  - Symbol parameter injection
  - Login username injection
  - Registration field injection
  - Query parameter injection

- **XSS Prevention**
  - Symbol parameter XSS
  - Registration field XSS
  - Error response XSS reflection

- **Invalid Input Handling**
  - Invalid symbol names
  - Negative values (quantity, price)
  - Zero values
  - Extremely large values

- **Oversized Request Handling**
  - Large JSON payloads
  - Long URLs
  - Many query parameters
  - Deeply nested JSON

- **Path Traversal Prevention**
  - Symbol parameter traversal
  - Query parameter traversal

- **Command Injection Prevention**
  - Symbol parameter injection
  - Registration field injection

### 3. Authorization Tests (`test_authorization.py`)

Tests for access control and permission validation:

- **Unauthenticated Access**
  - Protected endpoint protection
  - Public endpoint accessibility

- **User Data Isolation**
  - Cross-user portfolio access
  - Cross-user modification prevention

- **Admin-Only Endpoints**
  - Admin privilege enforcement
  - Regular user rejection

- **Privilege Escalation Prevention**
  - Token claim injection
  - User ID tampering

- **Trading Permissions**
  - Active user requirements
  - Emergency stop access

- **IDOR Prevention**
  - Resource ID guessing
  - ID injection attacks

### 4. Rate Limiting Tests (`test_rate_limiting.py`)

Tests for rate limit enforcement:

- **Rate Limit Enforcement**
  - Health endpoint limiting
  - Login endpoint limiting
  - Registration limiting
  - Market data limiting

- **Rate Limit Headers**
  - X-RateLimit-Limit presence
  - X-RateLimit-Remaining presence
  - X-RateLimit-Reset presence
  - Retry-After on 429

- **Rate Limit Reset**
  - Window reset behavior
  - Per-endpoint limits

- **Bypass Prevention**
  - IP header spoofing
  - User-Agent variation
  - URL case variation

### 5. Security Headers Tests (`test_security_headers.py`)

Tests for HTTP security headers:

- **CORS Configuration**
  - Preflight handling
  - Origin validation
  - Credentials handling

- **Content Security Policy**
  - CSP presence
  - unsafe-inline prevention
  - unsafe-eval prevention

- **HSTS**
  - Header presence
  - max-age value
  - includeSubDomains
  - preload directive

- **Other Security Headers**
  - X-Content-Type-Options
  - X-Frame-Options
  - X-XSS-Protection
  - Referrer-Policy
  - Permissions-Policy
  - Cache-Control

## Coverage Requirements

Target coverage: **>90%** for security-related code

### Key Files to Cover

- `services/api-gateway/app/auth_models.py`
- `services/api-gateway/app/auth_middleware.py`
- `services/api-gateway/app/config.py`
- `services/api-gateway/app/main.py`

### Generating Coverage Reports

```bash
# Generate HTML coverage report
pytest tests/security/ --cov=services/api-gateway/app --cov-report=html

# View report
open htmlcov/index.html
```

## Penetration Testing Scenarios

The test suite includes penetration testing scenarios:

1. **Authentication Bypass**
   - Token manipulation
   - Signature forgery
   - Expired token reuse

2. **Injection Attacks**
   - SQL injection (10 payloads)
   - XSS (10 payloads)
   - Command injection (8 payloads)
   - Path traversal (7 payloads)

3. **Authorization Bypass**
   - IDOR attacks
   - Privilege escalation
   - Cross-user access

4. **Denial of Service**
   - Rate limit exhaustion
   - Oversized requests
   - Deep nesting attacks

## Adding New Tests

When adding new security tests:

1. Follow the naming convention: `test_<category>_<scenario>.py`
2. Use descriptive test names: `test_<what>_<condition>_<expected>`
3. Add docstrings explaining the security concern
4. Include both positive and negative test cases
5. Use parametrized tests for payload variations

Example:

```python
@pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
def test_sql_injection_in_new_endpoint(self, test_client, payload):
    """
    Test SQL injection prevention in new endpoint

    Security Concern: SQL injection can lead to data breach
    Attack Vector: Malicious SQL in user input
    """
    response = test_client.get(f"/api/new/{payload}")
    assert response.status_code != 500
```

## CI/CD Integration

Add to your CI/CD pipeline:

```yaml
security_tests:
  stage: test
  script:
    - pip install -r requirements-test.txt
    - pytest tests/security/ -v --junitxml=security-results.xml
  artifacts:
    reports:
      junit: security-results.xml
```

## Troubleshooting

### Tests Fail to Import

```bash
# Ensure project root is in PYTHONPATH
export PYTHONPATH=/mnt/d/Bimo_max/crypto-trading-bot:$PYTHONPATH
```

### Redis Tests Skipped

Redis tests require Redis to be running:

```bash
docker run -d -p 6379:6379 redis:alpine
```

### Rate Limit Tests Timeout

Some rate limit tests wait for window reset. Use:

```bash
pytest tests/security/test_rate_limiting.py -v --timeout=120
```

## Security Best Practices Verified

This test suite verifies:

- [ ] JWT tokens are properly validated
- [ ] Passwords meet complexity requirements
- [ ] SQL injection is prevented
- [ ] XSS is prevented
- [ ] Authorization is enforced
- [ ] Rate limiting protects endpoints
- [ ] Security headers are present
- [ ] CORS is properly configured
- [ ] Sensitive data is not cached
- [ ] Error messages don't leak information

## Contact

For security vulnerabilities, please contact the security team directly.
Do not create public issues for security bugs.
