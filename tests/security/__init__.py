"""
Security Tests Package
Comprehensive security testing suite for the Crypto Trading Bot API

This package contains:
- test_authentication.py: JWT token validation tests
- test_input_validation.py: SQL injection, XSS, and input validation tests
- test_authorization.py: Access control and permission tests
- test_rate_limiting.py: Rate limiter enforcement tests
- test_security_headers.py: CORS, CSP, HSTS, and security header tests

Run all security tests:
    pytest tests/security/ -v --tb=short

Run with coverage:
    pytest tests/security/ --cov=services/api-gateway/app --cov-report=html
"""

__version__ = "1.0.0"
__author__ = "Testing Guardian Agent"
