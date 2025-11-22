# Security Quick Fix Guide

**CRITICAL: Run these fixes IMMEDIATELY**

## Executive Summary

Your crypto trading bot has **3 CRITICAL** and **5 HIGH** severity security vulnerabilities that must be fixed before production use.

### Immediate Risk:
- PostgreSQL and TimescaleDB databases exposed to host
- Redis authentication not properly configured in services
- Multiple internal services unnecessarily exposed
- Superuser database privileges (SQL injection risk)

### Time to Fix: 30 minutes

---

## Quick Fix (Automated)

### Step 1: Run Emergency Hardening Script (5 minutes)

```bash
# From project root
./scripts/security/emergency_hardening.sh
```

**This will:**
- Backup all configurations
- Add Redis passwords to service .env files
- Generate strong passwords
- Remove dangerous port mappings
- Bind monitoring to localhost

### Step 2: Manually Update Passwords (10 minutes)

The script generates new passwords in `.secrets/` directory. You need to update:

**File: `infrastructure/docker-compose.yml`**
```yaml
postgres:
  environment:
    POSTGRES_PASSWORD: <paste from .secrets/postgres_password>

timescaledb:
  environment:
    POSTGRES_PASSWORD: <paste from .secrets/timescale_password>

redis:
  command: redis-server ... --requirepass <paste from .secrets/redis_password>

rabbitmq:
  environment:
    RABBITMQ_DEFAULT_PASS: <paste from .secrets/rabbitmq_password>
```

**File: `.env` (root directory)**
```bash
REDIS_PASSWORD=<paste from .secrets/redis_password>
POSTGRES_PASSWORD=<paste from .secrets/postgres_password>
TIMESCALE_PASSWORD=<paste from .secrets/timescale_password>
RABBITMQ_PASSWORD=<paste from .secrets/rabbitmq_password>
```

### Step 3: Create Limited Privilege Database Users (5 minutes)

```bash
./scripts/security/create_db_users.sh
```

Then update service .env files:
```bash
# In each service .env that uses database:
DB_USER=cryptobot_app
DB_PASSWORD=<paste from .secrets/db_app_password>
```

**Files to update:**
- `services/portfolio-manager/.env`
- `services/trading-engine/.env`
- `services/market-data-service/.env`
- `services/risk-metrics-service/.env`

### Step 4: Restart All Services (5 minutes)

```bash
# Stop everything
docker-compose down
docker-compose -f infrastructure/docker-compose.yml down

# Start infrastructure
docker-compose -f infrastructure/docker-compose.yml up -d

# Wait 30 seconds for databases to be ready
sleep 30

# Start services
docker-compose up -d
```

### Step 5: Validate Security (5 minutes)

```bash
./scripts/security/validate_security.sh
```

**Expected output:**
```
✅ Passed:   15+
❌ Failed:   0
⚠️  Warnings: 5 or less

🎉 EXCELLENT! All security checks passed!
```

---

## Manual Fix (If Scripts Fail)

### Fix 1: Remove Database Port Exposure (CRITICAL)

**File: `infrastructure/docker-compose.yml`**

**Before:**
```yaml
postgres:
  ports:
    - "5432:5432"  # ❌ EXPOSED
```

**After:**
```yaml
postgres:
  # ports:  # ✅ REMOVED - access via Docker network only
```

**Do the same for:**
- TimescaleDB (port 5433)
- Redis (port 6379)

### Fix 2: Add Redis Password to All Services (CRITICAL)

**Check each file in `services/*/.env` contains:**
```bash
REDIS_HOST=crypto-bot-redis
REDIS_PORT=6379
REDIS_PASSWORD=redis_dev_password
REDIS_DB=0
```

**Services to check:**
- api-gateway
- market-data-service
- portfolio-manager
- technical-analysis
- trading-engine
- notification-service
- risk-metrics-service

### Fix 3: Bind RabbitMQ Management to Localhost (HIGH)

**File: `infrastructure/docker-compose.yml`**

**Before:**
```yaml
rabbitmq:
  ports:
    - "15672:15672"  # ❌ WORLD ACCESSIBLE
```

**After:**
```yaml
rabbitmq:
  ports:
    - "127.0.0.1:15672:15672"  # ✅ LOCALHOST ONLY
```

### Fix 4: Bind Monitoring to Localhost (HIGH)

**File: `docker-compose.yml` (root)**

**Before:**
```yaml
prometheus:
  ports:
    - "9090:9090"  # ❌ EXPOSED

grafana:
  ports:
    - "3001:3000"  # ❌ EXPOSED
```

**After:**
```yaml
prometheus:
  ports:
    - "127.0.0.1:9090:9090"  # ✅ LOCALHOST ONLY

grafana:
  ports:
    - "127.0.0.1:3001:3000"  # ✅ LOCALHOST ONLY
```

---

## Verification Checklist

After applying fixes, verify:

```bash
# 1. PostgreSQL not exposed
docker ps | grep postgres
# Should NOT show 0.0.0.0:5432

# 2. TimescaleDB not exposed
docker ps | grep timescale
# Should NOT show 0.0.0.0:5433

# 3. Redis requires password
docker exec crypto-bot-redis redis-cli PING
# Should return: NOAUTH Authentication required

# 4. Redis accepts correct password
docker exec crypto-bot-redis redis-cli -a "redis_dev_password" PING
# Should return: PONG

# 5. RabbitMQ management on localhost
docker ps | grep rabbitmq
# Should show: 127.0.0.1:15672->15672/tcp

# 6. Prometheus on localhost
docker ps | grep prometheus
# Should show: 127.0.0.1:9090->9090/tcp

# 7. Grafana on localhost
docker ps | grep grafana
# Should show: 127.0.0.1:3001->3000/tcp

# 8. All services healthy
curl http://localhost:8000/health
# Should return: {"status":"healthy"}
```

---

## What's Still Exposed (Expected)

### Ports on 0.0.0.0 (world accessible):
- **8000** - API Gateway (✅ Expected - this is your public API)
- **8001-8009** - Individual services (⚠️ Should be internal - see Advanced Fixes)

### Ports on 127.0.0.1 (localhost only):
- **9090** - Prometheus (✅ Good)
- **3001** - Grafana (✅ Good)
- **15672** - RabbitMQ Management (✅ Good)

---

## Advanced Fixes (Optional but Recommended)

### 1. Remove Internal Service Port Mappings

Currently, all services (8001-8009) are exposed on the host. They should only be accessible via the API Gateway.

**For each service in `docker-compose.yml`, change:**

**Before:**
```yaml
bybit-connector:
  ports:
    - "8001:8001"  # ❌ EXPOSED
```

**After:**
```yaml
bybit-connector:
  # ports:  # ✅ REMOVED - access via API Gateway only
```

**Keep exposed:**
- `8000` - API Gateway (public entry point)

**Services to update:**
- bybit-connector (8001)
- market-data (8002)
- portfolio-manager (8003)
- technical-analysis (8004)
- trading-engine (8005)
- notification-service (8006)
- ml-prediction (8007)
- sentiment-analysis (8008)
- risk-metrics (8009)

### 2. Implement API Authentication

**File: `services/api-gateway/app/main.py`**

Add authentication middleware:

```python
from fastapi import HTTPException, Security, Depends
from fastapi.security import APIKeyHeader
import os

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: str = Security(API_KEY_HEADER)):
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")

    valid_keys = os.getenv("API_KEYS", "").split(",")
    if api_key not in valid_keys:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return api_key

# Apply to protected routes
@app.get("/api/v1/portfolio/summary", dependencies=[Depends(verify_api_key)])
async def get_portfolio():
    ...
```

**Generate API keys:**
```bash
# Generate a secure API key
openssl rand -hex 32 > .secrets/api_key

# Add to .env
echo "API_KEYS=$(cat .secrets/api_key)" >> .env
```

### 3. Enable TLS/HTTPS

**File: `docker-compose.yml`**

```yaml
api-gateway:
  environment:
    - ENABLE_HTTPS=true
  volumes:
    - ./certs:/app/certs:ro
```

**Generate self-signed certificate (development):**
```bash
mkdir -p certs
openssl req -x509 -newkey rsa:4096 -keyout certs/key.pem -out certs/cert.pem -days 365 -nodes
```

---

## Common Issues

### Issue 1: Services Can't Connect to Redis

**Symptom:** Logs show "Connection refused" or "Authentication failed"

**Fix:**
1. Ensure `REDIS_PASSWORD` in service .env file
2. Restart service: `docker-compose restart <service-name>`

### Issue 2: Services Can't Connect to Database

**Symptom:** "Connection refused" on port 5432

**Fix:**
1. Check database is running: `docker ps | grep postgres`
2. Use Docker network hostname: `POSTGRES_HOST=crypto-bot-postgres`
3. Don't use localhost or 127.0.0.1 (those refer to container itself)

### Issue 3: Can't Access Grafana/Prometheus

**Symptom:** Connection refused on ports 9090/3001

**Fix:**
1. These are now localhost-only
2. Access from host: `http://localhost:9090` (not 0.0.0.0)
3. For remote access, use SSH tunnel:
   ```bash
   ssh -L 9090:localhost:9090 user@server
   ```

### Issue 4: API Gateway Returns 502

**Symptom:** API Gateway can't reach backend services

**Fix:**
1. Ensure all services are on same Docker network
2. Use container names, not localhost:
   ```env
   BYBIT_CONNECTOR_URL=http://crypto-bot-bybit:8001
   ```

---

## Security Score

### Before Fixes:
- **CRITICAL**: 3 issues
- **HIGH**: 5 issues
- **Security Score**: 45%

### After Quick Fixes:
- **CRITICAL**: 0 issues
- **HIGH**: 2 issues (internal services still exposed)
- **Security Score**: 75%

### After Advanced Fixes:
- **CRITICAL**: 0 issues
- **HIGH**: 0 issues
- **Security Score**: 95%

---

## Production Readiness

### Minimum Requirements (Quick Fixes):
- ✅ Databases not exposed to host
- ✅ Redis authentication enforced
- ✅ Limited privilege database users
- ✅ Monitoring bound to localhost
- ✅ Strong passwords generated

### Recommended for Production (Advanced Fixes):
- ⚠️ Internal services not exposed
- ⚠️ API authentication enabled
- ⚠️ TLS/HTTPS enabled
- ⚠️ Network segmentation
- ⚠️ Secrets management (Vault)

### Production Deployment Checklist:
- [ ] All quick fixes applied
- [ ] All advanced fixes applied
- [ ] Unique passwords for production (different from dev)
- [ ] API keys generated and distributed
- [ ] TLS certificates from trusted CA
- [ ] Firewall rules configured
- [ ] Monitoring alerts configured
- [ ] Incident response plan documented
- [ ] Regular security audits scheduled
- [ ] Backup and recovery tested

---

## Support

### Full Documentation:
- Complete audit: `SECURITY_AUDIT_REPORT.md`
- Architecture: `SYSTEM_ARCHITECTURE.md`
- Deployment: `DEPLOYMENT.md`

### Security Scripts:
- Emergency hardening: `./scripts/security/emergency_hardening.sh`
- Validation: `./scripts/security/validate_security.sh`
- DB users: `./scripts/security/create_db_users.sh`

### Get Help:
1. Review full audit report for detailed explanations
2. Check logs: `docker-compose logs <service-name>`
3. Health check: `curl http://localhost:8000/health`
4. System status: `docker ps`

---

## Summary

**Run these commands in order:**

```bash
# 1. Emergency hardening
./scripts/security/emergency_hardening.sh

# 2. Update passwords in config files (manual - see Step 2 above)

# 3. Create limited privilege users
./scripts/security/create_db_users.sh

# 4. Update service .env files (manual - see Step 3 above)

# 5. Restart services
docker-compose down && docker-compose -f infrastructure/docker-compose.yml down
docker-compose -f infrastructure/docker-compose.yml up -d
sleep 30
docker-compose up -d

# 6. Validate
./scripts/security/validate_security.sh

# 7. Test API
curl http://localhost:8000/health
```

**Total Time:** 30 minutes
**Result:** CRITICAL issues eliminated, security score improved from 45% to 75%

---

**Last Updated:** 2025-11-19
**Next Review:** 2025-12-19 (Monthly security audits recommended)
