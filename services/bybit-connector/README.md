# Bybit Connector Service

Microservice for interfacing with Bybit exchange API. Runs on **port 8001**. The stack runs in **paper-trading mode**: this service wraps Bybit REST (mainnet prices); orders are simulated downstream, not executed for real money.

> Merged from `PRODUCTION_FEATURES.md` on 2026-07-30.

## Features

- REST API client with authentication (HMAC request signing in `app/auth.py`)
- Circuit breaker pattern for resilience
- Exponential backoff retry logic
- Rate limiting (slowapi, IP-based)
- Structured JSON logging with automatic secret masking
- Prometheus metrics at `/metrics`
- Account management (balance, positions)
- Order management (place, cancel, query)
- Market data (ticker, kline, orderbook)

## Setup

1. **Create virtual environment**
   ```bash
   python3.12 -m venv venv
   source venv/bin/activate
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your Bybit testnet API keys
   ```

4. **Run tests**
   ```bash
   pytest tests/ -v
   ```

5. **Start service**
   ```bash
   uvicorn app.main:app --reload --port 8001
   ```

## API Documentation

Once running, visit: http://localhost:8001/docs

## Endpoints

- `GET /health` - Health check
- `GET /ready` - Readiness check
- `GET /metrics` - Prometheus metrics
- `GET /api/v1/account/balance` - Get wallet balance
- `GET /api/v1/account/positions` - Get positions
- `POST /api/v1/order/place` - Place order
- `POST /api/v1/order/cancel` - Cancel order
- `GET /api/v1/order/open` - Get open orders
- `GET /api/v1/market/ticker` - Get ticker data
- `GET /api/v1/market/kline` - Get candlestick data
- `GET /api/v1/status/circuit-breaker` - Circuit breaker status
- `POST /api/v1/status/circuit-breaker/reset` - Reset circuit breaker

## Testing

```bash
# Run all tests
pytest tests/ -v --cov=app

# Run specific test file
pytest tests/test_bybit_client.py -v

# Generate coverage report
pytest tests/ --cov=app --cov-report=html
open htmlcov/index.html
```

## Architecture

```
app/
├── __init__.py
├── main.py                 # FastAPI application
├── config.py              # Configuration management
├── exceptions.py          # Custom exceptions
├── auth.py                # Authentication & signatures
├── bybit_rest_client.py   # REST API client
└── circuit_breaker.py     # Circuit breaker pattern
```

## Circuit Breaker

The service implements circuit breaker pattern:
- Opens after 5 consecutive failures
- Stays open for 60 seconds
- Moves to half-open to test recovery
- Closes on successful request

Check status: `GET /api/v1/status/circuit-breaker`
Reset: `POST /api/v1/status/circuit-breaker/reset`

Circuit breaker state is exported as the Prometheus gauge `circuit_breaker_state` (0=closed, 1=open, 2=half-open).

## Rate Limiting

IP-based throttling via `slowapi`. Exceeding a limit returns **HTTP 429** with `{"error": "Rate limit exceeded: N per 1 minute"}`.

| Category | Endpoints | Limit |
|----------|-----------|-------|
| Health | `/health`, `/ready` | 60/minute |
| Account | `/api/v1/account/*` | 20/minute |
| Trading (write) | `/api/v1/order/place`, `/api/v1/order/cancel` | 10/minute |
| Trading (query) | `/api/v1/order/open`, `/api/v1/order/history` | 20/minute |
| Market data | `/api/v1/market/*` | 30/minute |
| Monitoring | `/api/v1/status/*` | 10-20/minute |

Limits are set per endpoint with the `@limiter.limit("N/minute")` decorator in `app/main.py`. Note: IP-based throttling can be spoofed via proxies; API-key-based limits and a Redis backend would be needed for distributed enforcement.

## Structured JSON Logging

All logs go to stdout as JSON (via `python-json-logger`) with fields: `timestamp`, `level`, `logger`, `message`, `method`, `endpoint`, `status_code`, `duration_seconds`, `client_ip`, `thread`. Compatible with ELK, Loki, Splunk, CloudWatch, Datadog.

**Secret masking** — a custom formatter replaces values matching these field patterns with `***MASKED***`:
`api_key`, `api_secret`, `password`, `token`, `secret`, `authorization`, `bearer`.
Add custom patterns to `SECRET_PATTERNS` in the formatter for service-specific secrets. Test with `logger.info("Test api_key=ABC123")` — output must show `***MASKED***`.

Prefer structured context over string concatenation:
```python
logger.info("Order placed successfully",
            extra={"order_id": "12345", "symbol": "BTCUSDT", "side": "Buy", "qty": "0.01"})
```

## Prometheus Metrics

Exposed at `GET /metrics` (collected via middleware):

| Metric | Type | Labels |
|--------|------|--------|
| `http_requests_total` | Counter | `method`, `endpoint`, `status_code` |
| `http_request_duration_seconds` | Histogram | `method`, `endpoint` |
| `http_requests_active` | Gauge | - |
| `circuit_breaker_state` | Gauge (0/1/2) | - |

Scrape config (`prometheus.yml`):
```yaml
scrape_configs:
  - job_name: 'bybit-connector'
    scrape_interval: 15s
    static_configs:
      - targets: ['bybit-connector:8001']
    metrics_path: '/metrics'
```

Useful queries:
```promql
rate(http_requests_total[5m])                                              # request rate
rate(http_requests_total{status_code=~"5.."}[5m])                          # error rate
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))   # p95 latency
rate(http_requests_total{status_code="429"}[5m])                           # rate-limit hits
circuit_breaker_state                                                      # breaker status
```

Recommended alerts: `HighErrorRate` (5xx rate > 0.05/s for 5m), `SlowRequests` (p95 > 1s for 5m), `CircuitBreakerOpen` (`circuit_breaker_state == 1` for 1m), `HighRateLimiting` (429 rate > 1/s for 5m).

Note: `/metrics` is unauthenticated — add auth before exposing beyond the internal network.

## Troubleshooting

- **Logs not JSON**: ensure `setup_json_logging()` runs before any logging; `python-json-logger` installed; uvicorn's own logs use a separate formatter.
- **`/metrics` 404**: verify `prometheus-client` installed and `PrometheusMiddleware` added to the app.
- **Secrets visible in logs**: field name must match a `SECRET_PATTERNS` entry — add a custom pattern if not.
- **Rate limited too quickly**: adjust the `@limiter.limit(...)` value on the endpoint in `app/main.py`.
- Check logs: `docker compose -f docker-compose.unified.yml logs -f bybit-connector` (unified compose is canonical).
