# Network Connectivity Fix - Frontend Ticker Timeouts

**Date:** 2025-12-03  
**Issue:** Frontend experiencing 20-second timeouts on ticker API calls  
**Status:** ✅ RESOLVED (runtime fix applied)

---

## Problem Summary

### Symptoms
```
api.js:36 API Error: timeout of 20000ms exceeded
useTicker.js:46 [useMultipleTickers] Failed to fetch BNBUSDT: timeout of 20000ms exceeded
```

All ticker endpoints (`/api/market/ticker/{symbol}`) were timing out, causing frontend to fail loading price data.

### Root Cause Analysis

**Network Architecture Issue:**
- Main services (trading-engine, market-data, etc.) run on `crypto-bot-network`
- Infrastructure services (Redis, RabbitMQ) run on `infrastructure_crypto-bot-network`
- These networks were not bridged, preventing communication

**Why Tickers Failed:**
```python
# market-data-service/app/handlers/query.py:117
cached_data = await cache_get(cache_key)  # ← Hangs waiting for Redis
```

The ticker endpoint tries to check Redis cache before querying database/live data. When Redis is unreachable, the connection attempt hangs until timeout.

---

## Runtime Fix Applied

Connected infrastructure services to main network:
```bash
docker network connect crypto-bot-network crypto-bot-redis
docker network connect crypto-bot-network crypto-bot-rabbitmq
```

### Verification
```bash
# Before fix: 5s+ timeout
$ curl http://localhost:8002/api/v1/ticker/BNBUSDT --max-time 5
Exit code 28 (timeout)

# After fix: <50ms response
$ curl http://localhost:8002/api/v1/ticker/BNBUSDT
{"success":true,"data":{"last_price":910.9,...},"source":"database"}
Time: 0.014307s ✅
```

### Current Network Status
```
crypto-bot-redis:      crypto-bot-network + infrastructure_crypto-bot-network ✅
crypto-bot-rabbitmq:   crypto-bot-network + infrastructure_crypto-bot-network ✅
crypto-bot-postgres:   crypto-bot-network + infrastructure_crypto-bot-network ✅
crypto-bot-timescaledb: crypto-bot-network + infrastructure_crypto-bot-network ✅
```

---

## Permanent Solution Options

### Option 1: Update Infrastructure Docker-Compose (Recommended)

Edit `/mnt/d/Bimo_max/crypto-trading-bot/infrastructure/docker-compose.yml`:

```yaml
services:
  redis:
    # ... existing config ...
    networks:
      - crypto-bot-network
      - main-services-network  # Add bridge to main services

  rabbitmq:
    # ... existing config ...
    networks:
      - crypto-bot-network
      - main-services-network  # Add bridge to main services

networks:
  crypto-bot-network:
    external: true
    name: infrastructure_crypto-bot-network
  
  main-services-network:  # NEW: Bridge to main docker-compose network
    external: true
    name: crypto-bot-network
```

### Option 2: Use Docker Compose Profiles

Create a unified compose file that manages both infrastructure and services together, eliminating the network split.

### Option 3: Service Mesh / Network Policy

Implement a service mesh (Istio, Linkerd) for production to properly manage inter-service communication with policies.

---

## Prevention: Cache Timeout Handling

Add fallback handling in cache layer to prevent similar issues:

```python
# services/market-data-service/app/cache.py
async def cache_get(key: str, timeout: float = 0.1):  # 100ms max
    """Get from cache with timeout fallback"""
    try:
        return await asyncio.wait_for(
            _redis_get(key), 
            timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.warning(f"Cache timeout for {key}, skipping cache")
        return None  # Fallback to database/live fetch
```

This ensures a single infrastructure failure (Redis down) doesn't cascade to frontend failures.

---

## Testing Checklist

- [x] BNBUSDT ticker loads in <100ms
- [x] BTCUSDT ticker loads successfully  
- [x] ETHUSDT ticker loads successfully
- [x] SOLUSDT ticker loads successfully
- [x] Frontend displays prices without timeout errors
- [x] Multiple ticker requests (useMultipleTickers) work
- [x] Redis caching functional (check logs for "Cache hit")
- [x] Backend services can publish to RabbitMQ
- [x] Trading engine can access Redis for signal caching

---

## Rollback Plan

If issues arise, disconnect the networks:
```bash
docker network disconnect crypto-bot-network crypto-bot-redis
docker network disconnect crypto-bot-network crypto-bot-rabbitmq
```

Services will fail to connect to infrastructure, but won't hang indefinitely.

---

## Related Files

**Backend:**
- `services/market-data-service/app/handlers/query.py:83-158` - Ticker endpoint
- `services/market-data-service/app/cache.py` - Redis cache layer

**Frontend:**
- `frontend/src/services/api.js:36` - Error logging  
- `frontend/src/hooks/useTicker.js:46` - Timeout error origin

**Infrastructure:**
- `infrastructure/docker-compose.yml:78-120` - Redis/RabbitMQ definitions
- `docker-compose.yml:544-546` - Network configuration

---

## Additional Notes

- Postgres and TimescaleDB were already on both networks (worked correctly)
- This issue only affected Redis and RabbitMQ
- Runtime fix is stable but will be lost on `docker-compose down`
- Permanent fix requires infrastructure/docker-compose.yml update

**Next Steps:**
1. ✅ Runtime fix verified working
2. ⏳ Update docker-compose for permanent solution
3. ⏳ Add cache timeout handling for resilience
4. ⏳ Test with infrastructure service restart
