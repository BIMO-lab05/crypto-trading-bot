"""
API Gateway Security Module
===========================
Comprehensive security controls for the API Gateway:
- Rate limiting with Redis backend
- Input validation for trading parameters
- Security headers middleware

Version: 1.0.0
Created: 2025-12-12
"""

from app.security.rate_limiter import (
    RateLimiter,
    get_rate_limiter,
    rate_limit_middleware,
    RateLimitConfig,
)

from app.security.input_validation import (
    InputValidator,
    ValidationError,
    validate_symbol,
    validate_quantity,
    validate_price,
    validate_trading_request,
    ALLOWED_SYMBOLS,
)

from app.security.security_headers import (
    SecurityHeadersMiddleware,
    get_security_headers_middleware,
)

__all__ = [
    # Rate Limiting
    "RateLimiter",
    "get_rate_limiter",
    "rate_limit_middleware",
    "RateLimitConfig",
    # Input Validation
    "InputValidator",
    "ValidationError",
    "validate_symbol",
    "validate_quantity",
    "validate_price",
    "validate_trading_request",
    "ALLOWED_SYMBOLS",
    # Security Headers
    "SecurityHeadersMiddleware",
    "get_security_headers_middleware",
]
