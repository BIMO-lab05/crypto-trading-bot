# Security Best Practices Guide - Crypto Trading Bot

**Version:** 1.0
**Last Updated:** 2025-12-12
**Purpose:** Developer guide for maintaining security in the crypto trading bot

---

## Table of Contents

1. [Secrets Management](#1-secrets-management)
2. [API Security](#2-api-security)
3. [Authentication & Authorization](#3-authentication--authorization)
4. [Input Validation](#4-input-validation)
5. [Secure Coding Practices](#5-secure-coding-practices)
6. [Container Security](#6-container-security)
7. [Kubernetes Security](#7-kubernetes-security)
8. [Monitoring & Logging](#8-monitoring--logging)

---

## 1. Secrets Management

### DO:

```python
# Load secrets from environment variables
import os

API_KEY = os.environ.get("BYBIT_API_KEY")
if not API_KEY:
    raise ValueError("BYBIT_API_KEY environment variable must be set")
```

### DON'T:

```python
# NEVER hardcode secrets
API_KEY = "abc123xyz789"  # WRONG!

# NEVER commit .env files with real credentials
```

### Best Practices:

1. **Use environment variables** for all secrets
2. **Use a secrets manager** for production:
   - HashiCorp Vault
   - AWS Secrets Manager
   - Azure Key Vault
   - Kubernetes Secrets with encryption

3. **Rotate secrets regularly**:
   - API keys: Every 90 days
   - Database passwords: Every 90 days
   - JWT secrets: On any suspected compromise

4. **Secret file patterns** to exclude in `.gitignore`:
   ```
   .env
   .env.*
   *.secret
   *-secrets.yaml
   credentials.json
   ```

### Generating Strong Secrets:

```bash
# Generate JWT secret (64 characters hex)
openssl rand -hex 32

# Generate password (24 characters)
openssl rand -base64 24

# Generate API key style secret
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 2. API Security

### Rate Limiting

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/v1/orders")
@limiter.limit("10/minute")  # Limit order creation
async def create_order(request: Request, order: OrderRequest):
    ...

@app.post("/auth/login")
@limiter.limit("5/minute")  # Stricter limit for auth
async def login(request: Request):
    ...
```

### CORS Configuration

```python
# Production CORS settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://yourdomain.com",
        "https://app.yourdomain.com"
    ],  # Specific domains only
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

### Security Headers

```python
from starlette.middleware import Middleware
from secure import SecureHeaders

secure_headers = SecureHeaders()

@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    secure_headers.framework.fastapi(response)
    return response
```

### Request Validation

```python
from pydantic import BaseModel, Field, validator

class TradeRequest(BaseModel):
    symbol: str = Field(..., regex=r"^[A-Z]{2,10}USDT$")
    quantity: Decimal = Field(..., gt=0, le=Decimal("1000000"))

    @validator('symbol')
    def validate_symbol(cls, v):
        allowed = {"BTCUSDT", "ETHUSDT", "BNBUSDT"}
        if v not in allowed:
            raise ValueError(f"Symbol {v} not allowed")
        return v
```

---

## 3. Authentication & Authorization

### JWT Best Practices

```python
# Short-lived access tokens
ACCESS_TOKEN_EXPIRE_MINUTES = 30  # Not 24 hours!

# Include essential claims
def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode.update({
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": datetime.utcnow(),
        "type": "access"
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")
```

### Password Security

```python
from passlib.context import CryptContext

# Use bcrypt with sufficient rounds
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=14  # Increase for production
)

# Validate password strength
def validate_password(password: str) -> bool:
    if len(password) < 12:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"[a-z]", password):
        return False
    if not re.search(r"\d", password):
        return False
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False
    return True
```

### Protect Endpoints

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def get_current_user(credentials = Depends(security)):
    token = credentials.credentials
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )
    return payload

# Protected endpoint
@app.get("/api/v1/account")
async def get_account(user = Depends(get_current_user)):
    ...
```

---

## 4. Input Validation

### Trading Parameters

```python
from decimal import Decimal
from pydantic import BaseModel, Field, validator
from enum import Enum

class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"

class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"

class OrderRequest(BaseModel):
    symbol: str = Field(..., min_length=5, max_length=20)
    side: OrderSide
    order_type: OrderType
    quantity: Decimal = Field(..., gt=0, le=Decimal("1000"))
    price: Optional[Decimal] = Field(None, gt=0, le=Decimal("1000000"))

    @validator('symbol')
    def validate_symbol(cls, v):
        # Only allow approved trading pairs
        allowed_symbols = {
            "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT",
            "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT"
        }
        if v.upper() not in allowed_symbols:
            raise ValueError(f"Symbol {v} is not available for trading")
        return v.upper()

    @validator('price')
    def validate_price(cls, v, values):
        if values.get('order_type') == OrderType.LIMIT and v is None:
            raise ValueError("Price is required for limit orders")
        return v
```

### SQL Injection Prevention

```python
# ALWAYS use parameterized queries
from sqlalchemy import text

# CORRECT
async def get_user(db: AsyncSession, username: str):
    query = text("SELECT * FROM users WHERE username = :username")
    result = await db.execute(query, {"username": username})
    return result.fetchone()

# WRONG - SQL Injection vulnerable
async def get_user_bad(db: AsyncSession, username: str):
    query = f"SELECT * FROM users WHERE username = '{username}'"  # NEVER DO THIS!
```

### Path Traversal Prevention

```python
import os
from pathlib import Path

BASE_DIR = Path("/app/data")

def safe_join(base: Path, user_path: str) -> Path:
    """Safely join paths preventing directory traversal"""
    # Resolve the full path
    full_path = (base / user_path).resolve()

    # Verify it's still within base directory
    if not str(full_path).startswith(str(base.resolve())):
        raise ValueError("Invalid path - directory traversal detected")

    return full_path
```

---

## 5. Secure Coding Practices

### Logging Without Secrets

```python
import re

class SecureLogger:
    SECRET_PATTERNS = [
        (re.compile(r'(api_key["\s:=]+)([^\s,}"]+)', re.I), r'\1***'),
        (re.compile(r'(password["\s:=]+)([^\s,}"]+)', re.I), r'\1***'),
        (re.compile(r'(secret["\s:=]+)([^\s,}"]+)', re.I), r'\1***'),
        (re.compile(r'(token["\s:=]+)([^\s,}"]+)', re.I), r'\1***'),
    ]

    @classmethod
    def sanitize(cls, message: str) -> str:
        for pattern, replacement in cls.SECRET_PATTERNS:
            message = pattern.sub(replacement, message)
        return message

    def info(self, message: str):
        logger.info(self.sanitize(message))
```

### Safe Deserialization

```python
import json
import hashlib

# For ML models, use integrity verification
def load_model_safely(filepath: str, expected_hash: str):
    """Load model with integrity check"""
    with open(filepath, 'rb') as f:
        content = f.read()

    actual_hash = hashlib.sha256(content).hexdigest()
    if actual_hash != expected_hash:
        raise ValueError("Model file integrity check failed!")

    # Use joblib instead of pickle when possible
    import joblib
    return joblib.load(filepath)
```

### Error Handling

```python
from fastapi import HTTPException

async def process_trade(order: OrderRequest):
    try:
        result = await execute_order(order)
        return result
    except InsufficientBalanceError:
        # Generic message to user
        raise HTTPException(
            status_code=400,
            detail="Unable to process order"
        )
    except Exception as e:
        # Log detailed error internally
        logger.error(f"Trade failed: {type(e).__name__}: {str(e)}")
        # Generic message to user
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )
```

---

## 6. Container Security

### Dockerfile Best Practices

```dockerfile
# Use specific version, not :latest
FROM python:3.12-slim as builder

# Run as non-root user
RUN useradd --create-home --shell /bin/bash appuser

# Set secure environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Image Scanning

```bash
# Scan with Trivy
trivy image crypto-bot/trading-engine:latest

# Scan with Grype
grype crypto-bot/trading-engine:latest

# Integrate in CI/CD
docker build -t myimage . && trivy image --exit-code 1 --severity HIGH,CRITICAL myimage
```

---

## 7. Kubernetes Security

### Pod Security Context

```yaml
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        runAsGroup: 1000
        fsGroup: 1000
      containers:
        - name: app
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
```

### Network Policies

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: trading-engine-policy
  namespace: crypto-bot
spec:
  podSelector:
    matchLabels:
      app: trading-engine
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: api-gateway
      ports:
        - port: 8005
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: postgres
      ports:
        - port: 5432
```

### Secrets Management

```yaml
# Use External Secrets Operator
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: trading-secrets
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: SecretStore
  target:
    name: trading-secrets
  data:
    - secretKey: BYBIT_API_KEY
      remoteRef:
        key: crypto-bot/bybit
        property: api_key
```

---

## 8. Monitoring & Logging

### Security Events to Monitor

1. **Authentication Events**
   - Failed login attempts
   - Successful logins from new IPs
   - Password reset requests

2. **Trading Events**
   - Large orders (>threshold)
   - Rapid order submissions
   - Orders from unusual IPs

3. **System Events**
   - Container restarts
   - Resource exhaustion
   - Error rate spikes

### Alerting Rules

```yaml
# Prometheus alerting rule
groups:
  - name: security-alerts
    rules:
      - alert: HighAuthFailureRate
        expr: rate(auth_failures_total[5m]) > 10
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: High authentication failure rate

      - alert: UnusualTradingVolume
        expr: sum(rate(orders_total[5m])) > 100
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: Unusual trading volume detected
```

### Audit Logging

```python
import structlog

audit_logger = structlog.get_logger("audit")

def log_trade_action(user_id: str, action: str, details: dict):
    audit_logger.info(
        "trade_action",
        user_id=user_id,
        action=action,
        details=details,
        timestamp=datetime.utcnow().isoformat(),
        ip_address=request.client.host
    )
```

---

## Quick Reference Commands

### Generate Secrets
```bash
# JWT Secret
openssl rand -hex 32

# Database password
openssl rand -base64 32

# API key
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Security Scanning
```bash
# Python dependencies
pip-audit
safety check

# Docker images
trivy image myimage:latest

# Kubernetes manifests
checkov -d infrastructure/kubernetes/

# Source code
bandit -r services/
```

### Check for Secrets in Git
```bash
# Scan repository
trufflehog filesystem .

# Check git history
git log --all --full-history -- "*.env" "*secret*"
```

---

**Document Owner:** Security Engineering Team
**Review Frequency:** Quarterly
**Next Review:** Q1 2026
