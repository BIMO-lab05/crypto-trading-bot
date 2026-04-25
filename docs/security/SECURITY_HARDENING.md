# API Security Hardening Documentation

**Version:** 1.0.0
**Date:** 2025-12-12
**Status:** Implemented

## Overview

This document describes the comprehensive security controls implemented for the Crypto Trading Bot API Gateway and Trading Engine services.

## Security Controls Implemented

### 1. Rate Limiting

Rate limiting is implemented using `slowapi` with Redis backend for distributed rate limiting across multiple instances.

#### Rate Limits by Endpoint Type

| Endpoint Category | Rate Limit | Purpose |
|------------------|------------|---------|
| Trading endpoints (`/api/trading/*`, `/api/portfolio/buy`, `/api/portfolio/sell`) | 10 requests/minute | Prevent rapid-fire trading, reduce risk |
| Auth endpoints (`/auth/*`) | 5 requests/minute | Prevent brute force attacks |
| Health checks (`/health`, `/ready`) | 60 requests/minute | Allow frequent monitoring |
| General API | 30 requests/minute | Prevent API abuse |

#### Rate Limit Error Response

When rate limit is exceeded, the API returns:

```json
{
  "success": false,
  "error": "rate_limit_exceeded",
  "message": "Too many requests. Please slow down.",
  "detail": "10 per 1 minute",
  "retry_after_seconds": 60,
  "path": "/api/trading/signals/BTCUSDT",
  "timestamp": 1702396800000
}
```

**HTTP Status:** `429 Too Many Requests`

**Headers:**
- `Retry-After: 60` (seconds until limit resets)
- `X-RateLimit-Limit: varies by endpoint`
- `X-RateLimit-Remaining: 0`

#### Configuration

Rate limiting can be configured via environment variables or settings:

```python
rate_limit_config = RateLimitConfig(
    trading_limit=10,      # Trading endpoints: 10 req/min
    auth_limit=5,          # Auth endpoints: 5 req/min
    health_limit=60,       # Health checks: 60 req/min
    general_limit=30,      # General API: 30 req/min
    enabled=True,          # Enable/disable rate limiting
    redis_url="redis://localhost:6379",  # Redis for distributed limiting
)
```

### 2. Input Validation

All trading-related inputs are validated before processing.

#### Symbol Whitelist

Only pre-approved trading symbols are allowed:

**Tier 1 (High Liquidity):**
- BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT
- ADAUSDT, DOGEUSDT, DOTUSDT, MATICUSDT, AVAXUSDT
- LINKUSDT, ATOMUSDT, LTCUSDT, UNIUSDT, AAVEUSDT

**Tier 2 (Popular Altcoins):**
- ARBUSDT, OPUSDT, APTUSDT, SUIUSDT, SEIUSDT
- TIAUSDT, NEARUSDT, FTMUSDT, ALGOUSDT, ICPUSDT
- And more...

#### Validation Bounds

| Parameter | Minimum | Maximum |
|-----------|---------|---------|
| Quantity | 0.0001 | 1,000,000 |
| Price | $0.00000001 | $1,000,000 |
| Limit | 1 | 1,000 |
| Confidence Level | 0.9 | 0.99 |
| Time Horizon (days) | 1 | 365 |

#### Validation Error Response

```json
{
  "success": false,
  "error": "validation_error",
  "field": "symbol",
  "message": "Symbol 'INVALID' is not in the allowed trading pairs",
  "provided_value": "INVALID",
  "allowed_values": ["BTCUSDT", "ETHUSDT", "..."],
  "timestamp": 1702396800000
}
```

**HTTP Status:** `400 Bad Request`

#### SQL Injection Prevention

All string inputs are checked for SQL injection patterns:
- SQL keywords (SELECT, INSERT, UPDATE, DELETE, DROP, UNION)
- SQL comments (`--`, `/*`, `*/`)
- Common injection patterns

### 3. Security Headers

All responses include OWASP-recommended security headers:

| Header | Value | Purpose |
|--------|-------|---------|
| Content-Security-Policy | `default-src 'self'; script-src 'self'; ...` | Prevent XSS |
| X-Content-Type-Options | `nosniff` | Prevent MIME sniffing |
| X-Frame-Options | `DENY` | Prevent clickjacking |
| Strict-Transport-Security | `max-age=31536000; includeSubDomains` | Force HTTPS |
| X-XSS-Protection | `1; mode=block` | Legacy XSS protection |
| Referrer-Policy | `strict-origin-when-cross-origin` | Control referrer info |
| Permissions-Policy | `camera=(), microphone=(), geolocation=()` | Disable unused features |
| Cache-Control | `no-store, no-cache, must-revalidate` | Prevent caching |

### 4. CORS Configuration

Strict CORS is configured with specific origins (no wildcards in production):

**Allowed Origins:**
```python
allow_origins = [
    "http://localhost:3000",     # React frontend development
    "http://localhost:8000",     # API Gateway
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
]
```

**Allowed Methods:**
- GET, POST, PUT, DELETE, OPTIONS, PATCH

**Allowed Headers:**
- Accept, Accept-Language, Authorization, Content-Language
- Content-Type, Origin, X-Requested-With, X-Request-ID

**Exposed Headers:**
- X-Request-ID, X-RateLimit-Limit, X-RateLimit-Remaining
- X-RateLimit-Reset, Retry-After

## Files Modified

| File | Description |
|------|-------------|
| `services/api-gateway/app/security/__init__.py` | Security module package |
| `services/api-gateway/app/security/rate_limiter.py` | Rate limiting implementation |
| `services/api-gateway/app/security/input_validation.py` | Input validation with whitelist |
| `services/api-gateway/app/security/security_headers.py` | Security headers middleware |
| `services/api-gateway/app/main.py` | Integrated security controls |
| `services/api-gateway/requirements.txt` | Added security dependencies |
| `services/trading-engine/app/config.py` | Added CORS configuration |
| `services/trading-engine/app/main.py` | Updated CORS middleware |

## Testing

Run security tests:

```bash
cd services/api-gateway
pytest tests/test_security.py -v
```

Test rate limiting manually:

```bash
# Test rate limit (should fail after 10 requests in 1 minute)
for i in {1..15}; do
  curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/trading/signals/BTCUSDT
  sleep 1
done
```

Test input validation:

```bash
# Valid symbol (should succeed)
curl http://localhost:8000/api/market/ticker/BTCUSDT

# Invalid symbol (should return 400)
curl http://localhost:8000/api/market/ticker/INVALID123

# SQL injection attempt (should return 400)
curl "http://localhost:8000/api/market/ticker/BTCUSDT'; DROP TABLE users;--"
```

## Logging

All security events are logged:

- Rate limit violations: `WARNING` level
- Validation failures: `WARNING` level
- SQL injection attempts: `ERROR` level

Log format:
```
2025-12-12 10:00:00 - security - WARNING - Rate limit exceeded: client=ip:192.168.1.1, path=/api/trading/signals/BTCUSDT, method=GET
2025-12-12 10:00:01 - security - WARNING - Validation failed: field=symbol, message=Symbol not in whitelist, value=INVALID
2025-12-12 10:00:02 - security - ERROR - Potential SQL injection detected: field=symbol, pattern=DROP, value_snippet=BTCUSDT'; DROP
```

## Recommendations

### Production Deployment

1. **Redis for Rate Limiting**: Ensure Redis is configured for distributed rate limiting
2. **HTTPS Only**: Enable HSTS and ensure all traffic uses HTTPS
3. **Environment Variables**: Store sensitive configuration in environment variables
4. **Monitoring**: Set up alerts for rate limit violations and validation failures
5. **IP Blacklisting**: Consider implementing IP blacklisting for repeated violations

### Future Enhancements

1. **API Key Management**: Implement API key rotation
2. **Request Signing**: Add request signature verification for trading operations
3. **Audit Logging**: Enhanced logging to database for compliance
4. **Web Application Firewall**: Consider adding WAF rules
5. **Token Blacklisting**: Implement JWT token blacklisting for logout

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-12-12 | Initial security hardening implementation |
