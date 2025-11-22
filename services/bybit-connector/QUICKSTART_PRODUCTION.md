# Quick Start: Production Features

## TL;DR

Three production features added to `/mnt/d/Bimo_max/crypto-trading-bot/services/bybit-connector/app/main.py`:

1. **Rate Limiting** - Prevents API abuse
2. **JSON Logging** - Machine-readable logs with secret masking
3. **Prometheus Metrics** - Real-time monitoring

## Start the Service

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot/services/bybit-connector

# Install dependencies (if needed)
pip install -r requirements.txt

# Start the service
python3 app/main.py
```

## Quick Tests

### 1. Health Check
```bash
curl http://localhost:8000/health
```

**Expected:**
```json
{"status": "healthy", "service": "bybit-connector"}
```

### 2. View Prometheus Metrics
```bash
curl http://localhost:8000/metrics
```

**Expected:**
```
http_requests_total{method="GET",endpoint="/health",status_code="200"} 1.0
http_request_duration_seconds_sum{method="GET",endpoint="/health"} 0.0023
http_requests_active 0.0
circuit_breaker_state 0.0
```

### 3. Trigger Rate Limit
```bash
# Send 65 requests (limit is 60/min)
for i in {1..65}; do curl http://localhost:8000/health; done
```

**Expected:** After ~60 requests, you'll see:
```json
{"error": "Rate limit exceeded: 60 per 1 minute"}
```

### 4. Check Structured Logs
Look at the console where the service is running. You should see JSON formatted logs:

```json
{
  "timestamp": "2025-11-05T14:30:45",
  "level": "INFO",
  "message": "GET /health 200",
  "method": "GET",
  "endpoint": "/health",
  "status_code": 200,
  "duration_seconds": 0.0023
}
```

## Run Comprehensive Tests

```bash
python3 test_production_features.py
```

This will test:
- Rate limiting behavior
- Metrics collection
- Structured logging output
- Secret masking

## Rate Limits Reference

| Endpoint Category | Limit | Example |
|------------------|-------|---------|
| Health (`/health`, `/ready`) | 60/min | Health checks |
| Account (`/api/v1/account/*`) | 20/min | Balance queries |
| Trading Writes (`/order/place`, `/order/cancel`) | 10/min | Place/cancel orders |
| Trading Reads (`/order/open`, `/order/history`) | 20/min | Query orders |
| Market Data (`/api/v1/market/*`) | 30/min | Price data |
| Monitoring (`/api/v1/status/*`) | 10-20/min | Circuit breaker |

## Key Endpoints

```bash
# Health Check
GET  /health

# Readiness Check (tests Bybit connection)
GET  /ready

# Prometheus Metrics
GET  /metrics

# Market Data (rate limited to 30/min)
GET  /api/v1/market/ticker?symbol=BTCUSDT

# Account Balance (rate limited to 20/min)
GET  /api/v1/account/balance

# Place Order (rate limited to 10/min)
POST /api/v1/order/place
```

## Environment Variables

```bash
# Required
export BYBIT_API_KEY="your_key"
export BYBIT_API_SECRET="your_secret"

# Optional
export BYBIT_TESTNET="true"           # Use testnet
export SERVICE_HOST="0.0.0.0"         # Bind address
export SERVICE_PORT="8000"            # Port
export LOG_LEVEL="INFO"               # Log level
export ALLOWED_ORIGINS="*"            # CORS origins
```

## Docker Quick Start

```bash
# Build image
docker build -t bybit-connector .

# Run container
docker run -p 8000:8000 \
  -e BYBIT_API_KEY="your_key" \
  -e BYBIT_API_SECRET="your_secret" \
  -e BYBIT_TESTNET="true" \
  bybit-connector

# Check logs (JSON formatted)
docker logs bybit-connector

# Check metrics
curl http://localhost:8000/metrics
```

## Monitoring with Prometheus

1. **Create `prometheus.yml`:**
```yaml
scrape_configs:
  - job_name: 'bybit-connector'
    scrape_interval: 15s
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
```

2. **Run Prometheus:**
```bash
docker run -p 9090:9090 \
  -v $(pwd)/prometheus.yml:/etc/prometheus/prometheus.yml \
  prom/prometheus
```

3. **Access Prometheus UI:**
```
http://localhost:9090
```

4. **Example Queries:**
```promql
# Request rate
rate(http_requests_total[5m])

# Error rate
rate(http_requests_total{status_code=~"5.."}[5m])

# P95 latency
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Rate limit hits
rate(http_requests_total{status_code="429"}[5m])
```

## Grafana Dashboard

1. **Run Grafana:**
```bash
docker run -p 3000:3000 grafana/grafana
```

2. **Login:** `admin` / `admin`

3. **Add Prometheus Data Source:**
   - URL: `http://prometheus:9090` (or `http://localhost:9090`)

4. **Create Dashboard with Panels:**
   - Request Rate: `rate(http_requests_total[5m])`
   - Error Rate: `rate(http_requests_total{status_code=~"5.."}[5m])`
   - Latency (P95): `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))`
   - Active Requests: `http_requests_active`
   - Circuit Breaker: `circuit_breaker_state`

## Troubleshooting

### Service won't start
```bash
# Check if port is in use
lsof -i :8000

# Check dependencies
pip list | grep -E "(fastapi|slowapi|prometheus|pythonjson)"

# Check environment variables
env | grep BYBIT
```

### Rate limits too strict
Edit `/mnt/d/Bimo_max/crypto-trading-bot/services/bybit-connector/app/main.py`:

```python
# Example: Increase health check limit
@app.get("/health")
@limiter.limit("120/minute")  # Changed from 60
```

### Logs not in JSON format
Check the console output. Uvicorn's own logs will still be plain text, but application logs should be JSON.

To see only application logs:
```bash
python3 app/main.py 2>&1 | grep '"message"'
```

### Metrics not showing
```bash
# Test metrics endpoint
curl -v http://localhost:8000/metrics

# Should return Content-Type: text/plain; version=0.0.4
# And metrics in Prometheus format
```

## Performance Testing

```bash
# Install hey (HTTP load generator)
# brew install hey  # macOS
# or download from: https://github.com/rakyll/hey

# Test with 100 requests, 10 concurrent
hey -n 100 -c 10 http://localhost:8000/health

# View metrics after load test
curl http://localhost:8000/metrics | grep http_requests
```

## Files Modified/Created

| File | Purpose |
|------|---------|
| `/app/main.py` | Core application with all 3 features |
| `PRODUCTION_FEATURES.md` | Comprehensive documentation |
| `test_production_features.py` | Test suite for features |
| `QUICKSTART_PRODUCTION.md` | This quick start guide |

## Next Steps

1. **Set up Prometheus + Grafana** for monitoring
2. **Configure log aggregation** (ELK, Loki, CloudWatch)
3. **Set up alerts** for error rates and slow requests
4. **Tune rate limits** based on actual usage patterns
5. **Add authentication** to `/metrics` endpoint for production

## Full Documentation

For detailed information, see:
- `PRODUCTION_FEATURES.md` - Complete feature documentation
- `README.md` - General service documentation
- `IMPLEMENTATION_SUMMARY.md` - Implementation details

## Support

- Test suite: `python3 test_production_features.py`
- Check logs: `tail -f logs/app.log` or `docker logs bybit-connector`
- View metrics: `curl http://localhost:8000/metrics`
- API docs: `http://localhost:8000/docs` (Swagger UI)

---

**Ready to deploy!** All three production features are fully integrated and tested.
