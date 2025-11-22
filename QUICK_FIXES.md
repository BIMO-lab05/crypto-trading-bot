# Quick Fixes for Failing Tests and Endpoints

## Priority 1: Start Data Collection Pipeline (CRITICAL)

### Problem
- All kline endpoints return empty arrays
- Technical indicators return "No data available"
- Trading bot cannot generate accurate signals without real data

### Solution
```bash
# Check if scheduler is running
curl http://localhost:8002/api/v1/scheduler/status

# Start the scheduler
curl -X POST http://localhost:8002/api/v1/scheduler/start

# Manually collect initial data for BTCUSDT
# Note: Check the exact parameter requirements in the service
curl -X POST "http://localhost:8002/api/v1/scheduler/collect"
```

### Verification
```bash
# Check if kline data is now available
curl "http://localhost:8002/api/v1/klines/BTCUSDT?interval=1h&limit=5"

# Should return array of candles instead of empty array
```

---

## Priority 2: Fix E2E Test Import Error

### Problem
```
NameError: name 'Optional' is not defined
File: tests/e2e/fixtures/mock_data.py:211
```

### Solution
```python
# File: /mnt/d/Bimo_max/crypto-trading-bot/tests/e2e/fixtures/mock_data.py
# Line 1 - Add missing import

from typing import Optional, List, Dict, Any  # Add Optional if missing
```

### Verification
```bash
cd /mnt/d/Bimo_max/crypto-trading-bot
python3 -m pytest tests/e2e/ -v
```

---

## Priority 3: Fix Risk Metrics Service Tests (68 failures)

### Problem 1: Logger Configuration
```
TypeError: Logger._log() got an unexpected keyword argument 'service'
```

### Solution
Find all logger calls with 'service' parameter and update:

```python
# BEFORE:
logger.info("Message", service="risk-metrics")

# AFTER:
logger.info("Message", extra={"service": "risk-metrics"})
```

### Problem 2: Missing Pydantic Field
```
pydantic_core._pydantic_core.ValidationError: 1 validation error for CapitalMetrics
reserved_capital - Field required
```

### Solution
```python
# File: /mnt/d/Bimo_max/crypto-trading-bot/services/risk-metrics-service/app/models.py

class CapitalMetrics(BaseModel):
    total_capital: Decimal
    available_capital: Decimal
    allocated_capital: Decimal
    reserved_capital: Decimal  # ADD THIS FIELD
    capital_utilization: float
    position_size: Optional[Decimal] = None
```

### Verification
```bash
cd /mnt/d/Bimo_max/crypto-trading-bot/services/risk-metrics-service
python3 -m pytest tests/ -v
```

---

## Priority 4: Fix API Gateway JWT Test

### Problem
```
AssertionError: assert 'bdbfd42f2b90...' == 'your-secret-key-change-in-production'
```

### Solution Option 1 (Update Test):
```python
# File: /mnt/d/Bimo_max/crypto-trading-bot/services/api-gateway/tests/test_config.py
# Line 142

def test_default_jwt_secret_is_insecure():
    settings = Settings()
    # Update assertion to check it's not the old insecure default
    assert settings.jwt_secret_key != "your-secret-key-change-in-production"
    # Verify it's a proper length secret
    assert len(settings.jwt_secret_key) >= 32
```

### Solution Option 2 (Document Security Improvement):
```python
# This is actually GOOD - the system now generates a secure random key
# Update test to verify security instead of checking for insecure default
def test_jwt_secret_is_secure():
    settings = Settings()
    # Verify it's long enough
    assert len(settings.jwt_secret_key) >= 32
    # Verify it's hexadecimal (secure generated key)
    assert all(c in '0123456789abcdef' for c in settings.jwt_secret_key)
```

---

## Priority 5: Fix Portfolio Optimizer Tests (9 failures)

### Problem
```
WARNING: Optimization warning: Inequality constraints incompatible
```

### Analysis
The scipy optimization constraints are conflicting. Common causes:
1. Sum of weights must equal 1.0
2. Weights must be non-negative
3. Position limits conflicting with weight constraints

### Solution
```python
# File: /mnt/d/Bimo_max/crypto-trading-bot/services/portfolio-manager/app/optimization/portfolio_optimizer.py

# Review constraint definitions around line 200-300
# Typical fix - relax constraints slightly

constraints = [
    {
        'type': 'eq',
        'fun': lambda w: np.sum(w) - 1.0  # Sum to 1
    }
]

# Ensure bounds allow feasible solution
bounds = tuple((0.0, 1.0) for _ in range(n_assets))

# If using position limits, ensure they're compatible:
# Example: If max_position=0.3 and you have 3 assets,
# 3 * 0.3 = 0.9 < 1.0, making sum=1.0 constraint impossible!

# Fix: Either increase max_position or reduce min_position requirement
```

### Verification
```bash
cd /mnt/d/Bimo_max/crypto-trading-bot/services/portfolio-manager
python3 -m pytest tests/test_portfolio_optimizer.py -v
```

---

## Quick Test Commands

### Test Individual Services
```bash
# API Gateway
cd /mnt/d/Bimo_max/crypto-trading-bot/services/api-gateway
python3 -m pytest tests/ -v --tb=short

# Trading Engine
cd /mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine
python3 -m pytest tests/unit/ -v --tb=short

# Technical Analysis
cd /mnt/d/Bimo_max/crypto-trading-bot/services/technical-analysis
python3 -m pytest tests/unit/ -v --tb=short

# Portfolio Manager
cd /mnt/d/Bimo_max/crypto-trading-bot/services/portfolio-manager
python3 -m pytest tests/ -v --tb=short

# Risk Metrics
cd /mnt/d/Bimo_max/crypto-trading-bot/services/risk-metrics-service
python3 -m pytest tests/ -v --tb=short

# E2E Tests
cd /mnt/d/Bimo_max/crypto-trading-bot
python3 -m pytest tests/e2e/ -v --tb=short
```

### Test Specific Endpoints
```bash
# Health checks
for port in 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009; do
  echo "Testing port $port:"
  curl -s http://localhost:$port/health | python3 -m json.tool
done

# Market data
curl "http://localhost:8002/api/v1/ticker/BTCUSDT" | python3 -m json.tool
curl "http://localhost:8002/api/v1/klines/BTCUSDT?interval=1h&limit=5" | python3 -m json.tool

# Trading signals
curl "http://localhost:8000/api/trading/signals/BTCUSDT" | python3 -m json.tool

# Portfolio
curl "http://localhost:8000/api/portfolio" | python3 -m json.tool
curl "http://localhost:8000/api/portfolio/performance" | python3 -m json.tool

# Risk metrics
curl "http://localhost:8000/api/risk/scorecard" | python3 -m json.tool

# Dashboard
curl "http://localhost:8000/api/dashboard/BTCUSDT" | python3 -m json.tool
```

---

## Automated Fix Script

Create this script to apply all fixes automatically:

```bash
#!/bin/bash
# File: /mnt/d/Bimo_max/crypto-trading-bot/scripts/apply_test_fixes.sh

echo "Applying test fixes..."

# Fix 1: Add Optional import to E2E fixtures
echo "Fix 1: Adding Optional import..."
sed -i '1s/^/from typing import Optional, List, Dict, Any\n/' \
  /mnt/d/Bimo_max/crypto-trading-bot/tests/e2e/fixtures/mock_data.py

# Fix 2: Start data collection
echo "Fix 2: Starting data collection..."
curl -X POST http://localhost:8002/api/v1/scheduler/start

# Fix 3: Update API Gateway JWT test
echo "Fix 3: Updating JWT test..."
# (Manual fix required - see Priority 4 above)

echo "Fixes applied! Run tests to verify:"
echo "  python3 -m pytest tests/e2e/ -v"
echo "  python3 -m pytest services/api-gateway/tests/ -v"
```

---

## Testing Checklist

After applying fixes, verify:

- [ ] E2E tests can import and run
- [ ] Market data klines endpoint returns data
- [ ] Technical indicators can calculate (no "No data" errors)
- [ ] Trading signals use real data instead of mock data
- [ ] Risk Metrics tests pass >90%
- [ ] Portfolio Optimizer tests pass >80%
- [ ] API Gateway tests all pass (60/60)
- [ ] All services health checks pass
- [ ] Dashboard endpoint aggregates real data

---

## Expected Test Results After Fixes

| Service | Current | Target | Status |
|---------|---------|--------|---------|
| API Gateway | 59/60 (98.3%) | 60/60 (100%) | Easy fix |
| Trading Engine | 356/356 (100%) | 356/356 (100%) | ✅ Already perfect |
| Technical Analysis | 241/241 (100%) | 241/241 (100%) | ✅ Already perfect |
| Portfolio Manager | 19/28 (67.9%) | 24/28 (85%+) | Medium fix |
| Risk Metrics | 25/93 (26.9%) | 85/93 (90%+) | Easy fix |
| E2E Tests | ERROR | PASS | Easy fix |

**Overall Target**: 90%+ test pass rate across all services

---

## Support and Debugging

### Enable Debug Logging
```bash
# For any service, set log level to DEBUG
export LOG_LEVEL=DEBUG

# Restart service to see detailed logs
docker-compose restart market-data-service
```

### Check Service Logs
```bash
# View logs for specific service
docker-compose logs -f market-data-service
docker-compose logs -f trading-engine
docker-compose logs -f risk-metrics-service
```

### Database Inspection
```bash
# Connect to PostgreSQL
docker exec -it postgres psql -U trading_user -d trading_db

# Check if kline data exists
SELECT COUNT(*) FROM klines WHERE symbol = 'BTCUSDT';

# Check ticker data
SELECT * FROM tickers WHERE symbol = 'BTCUSDT' ORDER BY timestamp DESC LIMIT 1;
```

---

**Last Updated**: 2025-11-19
**Testing Guardian Agent**
