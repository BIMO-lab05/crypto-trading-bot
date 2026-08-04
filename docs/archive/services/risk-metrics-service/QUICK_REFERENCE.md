# Risk Metrics Service - Quick Reference

## Performance Optimization Commands

### Health & Status
```bash
# Check service health
curl http://localhost:8007/health

# Get detailed status
curl http://localhost:8007/status

# Check optimizations active
curl http://localhost:8007/ | jq '.optimizations'
```

### Cache Management
```bash
# Get cache statistics
curl http://localhost:8007/cache/stats

# Invalidate all cache (requires admin key)
curl -X POST http://localhost:8007/cache/invalidate \
  -H "X-Admin-Key: dev-admin-key-change-in-production"
```

### Performance Monitoring
```bash
# Get performance stats
curl http://localhost:8007/performance/stats

# Get last 5 minutes only
curl http://localhost:8007/performance/stats | jq '.last_5_minutes'

# Reset stats (requires admin key)
curl -X POST http://localhost:8007/performance/reset \
  -H "X-Admin-Key: dev-admin-key-change-in-production"
```

### Testing
```bash
# Run full performance test suite
./test_performance.sh

# Single request timing
time curl http://localhost:8007/risk/scorecard

# Cache performance test
curl -w "\nTime: %{time_total}s\n" http://localhost:8007/risk/scorecard

# Load test (requires Apache Bench)
ab -n 100 -c 50 http://localhost:8007/risk/scorecard
```

## Configuration

### Environment Variables
```bash
# Redis Cache
REDIS_ENABLED=true
REDIS_URL=redis://localhost:6379
REDIS_CACHE_TTL=30

# Connection Pool
MAX_HTTP_CONNECTIONS=100
HTTP_TIMEOUT=10.0

# Performance
ENABLE_PERFORMANCE_MONITORING=true
ENABLE_REQUEST_BATCHING=true
```

## Key Metrics

### Target Values
| Metric | Target | Critical |
|--------|--------|----------|
| Cache Hit Rate | >80% | <50% |
| P95 Response Time | <500ms | >1000ms |
| Error Rate | <1% | >5% |
| Pool Utilization | <80% | >95% |

### Quick Checks
```bash
# Cache hit rate
curl -s http://localhost:8007/cache/stats | jq '.hit_rate_pct'

# P95 response time
curl -s http://localhost:8007/performance/stats | jq '.summary.p95_response_time_ms'

# Error rate
curl -s http://localhost:8007/performance/stats | jq '.summary.error_rate_pct'

# Pool utilization
curl -s http://localhost:8007/status | jq '.connection_pool.active_connections'
```

## Troubleshooting

### Redis Not Connected
```bash
# Check Redis
docker ps | grep redis
redis-cli ping

# Restart Redis
docker restart redis-cache

# Check service logs
docker logs risk-metrics-service | grep -i redis
```

### Slow Response Times
```bash
# 1. Check cache is working
curl http://localhost:8007/cache/stats

# 2. Check connection pool
curl http://localhost:8007/status | jq '.connection_pool'

# 3. Check performance stats
curl http://localhost:8007/performance/stats

# 4. Check downstream services
curl http://localhost:8006/health
```

### High Error Rate
```bash
# Get error details
curl http://localhost:8007/performance/stats | jq '.endpoints'

# Check service logs
docker logs risk-metrics-service --tail 100

# Check Redis connection
redis-cli ping
```

## Service Management

### Start/Stop
```bash
# Development
uvicorn app.main:app --reload --port 8007

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8007 --workers 4

# Docker
docker-compose up -d risk-metrics-service

# Stop
docker-compose stop risk-metrics-service
```

### View Logs
```bash
# Development
tail -f logs/service.log

# Docker
docker logs -f risk-metrics-service

# Filter for performance
docker logs risk-metrics-service | grep -i "performance\|cache"
```

## Testing Endpoints

### All Cached Endpoints
```bash
# Risk scorecard (most comprehensive)
curl http://localhost:8007/risk/scorecard

# Capital metrics
curl http://localhost:8007/risk/capital

# Exposure metrics
curl http://localhost:8007/risk/exposure

# Drawdown metrics
curl http://localhost:8007/risk/drawdown

# Value at Risk
curl http://localhost:8007/risk/var

# Performance metrics
curl http://localhost:8007/performance/metrics
```

## Performance Targets

### Response Times
- **Single request:** <100ms
- **Under load (50 concurrent):** <500ms
- **Cached request:** <10ms

### Throughput
- **Minimum:** 100 req/s
- **Target:** 200+ req/s

### Cache
- **Hit rate:** >80%
- **TTL:** 30 seconds
- **Invalidation:** Automatic + manual

## Quick Wins

### Improve Cache Hit Rate
```bash
# Increase TTL
export REDIS_CACHE_TTL=60

# Check what's being cached
curl http://localhost:8007/cache/stats
```

### Reduce Response Time
```bash
# Increase connection pool
export MAX_HTTP_CONNECTIONS=200

# Enable all optimizations
export REDIS_ENABLED=true
export ENABLE_REQUEST_BATCHING=true
export ENABLE_PERFORMANCE_MONITORING=true
```

### Monitor Performance
```bash
# Watch performance in real-time
watch -n 5 'curl -s http://localhost:8007/performance/stats | jq ".summary"'

# Monitor cache hit rate
watch -n 5 'curl -s http://localhost:8007/cache/stats | jq ".hit_rate_pct"'
```

## Files Reference

### Code Files
- `/app/cache.py` - Redis caching implementation
- `/app/performance.py` - Monitoring and batching
- `/app/main.py` - Main application with optimizations
- `/app/config.py` - Configuration settings

### Documentation
- `/OPTIMIZATION_SUMMARY.md` - Summary of changes
- `/PERFORMANCE_OPTIMIZATION_REPORT.md` - Detailed report
- `/README_PERFORMANCE.md` - User guide
- `/QUICK_REFERENCE.md` - This file

### Tests
- `/tests/test_cache.py` - Cache unit tests
- `/tests/test_performance.py` - Performance unit tests
- `/test_performance.sh` - Performance test script

---

**Keep this file handy for daily operations!**
