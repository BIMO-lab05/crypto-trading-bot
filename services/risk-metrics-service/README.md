# Risk & Metrics Service

**Port:** 8009
**Version:** 1.0.0

> Merged from `README_CIRCUIT_BREAKER.md`, `README_PERFORMANCE.md`, and `QUICK_REFERENCE.md` on 2026-07-30. All examples use port **8009** (older copies of these docs said 8007) and the current service map (portfolio-manager 8003, market-data 8002).

## Overview

The Risk & Metrics Service is a risk management and performance analytics layer that monitors capital, exposure, calculates performance metrics, and provides real-time risk alerts. The stack runs in **paper-trading mode**; risk metrics are computed over simulated positions.

### Features

1. **Capital Monitoring** — total/available/allocated/reserved capital, utilization %
2. **Exposure Management** — long/short, net and gross exposure, leverage, concentration risk, position size compliance
3. **Performance Metrics** — Sharpe, Sortino, Calmar ratios; win rate, profit factor, average win/loss
4. **Drawdown Tracking** — current and max drawdown, underwater period, recovery factor
5. **Value at Risk (VaR)** — 95%/99% confidence, CVaR/Expected Shortfall, historical simulation, time-scaled
6. **Risk Scoring** — composite 0-100 score from capital/exposure/concentration/volatility/drawdown components; LOW/MEDIUM/HIGH/CRITICAL classification
7. **Risk Alerts** — real-time threshold violation detection, categorized, with severity and recommendations
8. **Circuit Breaker** — automatic trading halt on critical conditions (see state machine reference below)

### API Endpoints

```
GET  /health                  - Service health check
GET  /status                  - Detailed service status (incl. optimization metrics)

GET  /risk/scorecard          - Complete risk assessment
GET  /risk/capital            - Capital metrics
GET  /risk/exposure           - Exposure analysis
GET  /risk/drawdown           - Drawdown metrics
GET  /risk/var                - Value at Risk calculation

GET  /performance/metrics     - Performance statistics
GET  /performance/sharpe      - Sharpe ratio calculation
GET  /performance/returns     - Historical returns
GET  /performance/stats       - Service latency/throughput stats
POST /performance/reset       - Reset perf stats (X-Admin-Key)

GET  /alerts                  - Active risk alerts
GET  /alerts/history          - Alert history
GET  /circuit-breaker         - Circuit breaker status
POST /circuit-breaker/reset   - Reset circuit breaker (admin)

GET  /cache/stats             - Cache statistics
POST /cache/invalidate        - Invalidate cache (X-Admin-Key)

GET  /config/limits           - Current risk limits
PUT  /config/limits           - Update risk limits (admin)
```

### Risk Limits (defaults, configurable)

```python
max_position_size = 0.02      # 2% max per position
max_portfolio_risk = 0.05     # 5% max portfolio risk
max_drawdown_threshold = 0.10 # 10% max drawdown alert
max_daily_loss = 0.05         # 5% daily loss limit
max_exposure = 0.20           # 20% max total exposure
```

> Note: paper mode currently relaxes the per-trade cap to 10% in trading-engine (ADR-010, 2026-05-06) to clear Bybit min-notional; the 2% cap above is the LIVE-mode invariant.

### Metric Formulas

```
Sharpe  = (Return - Risk_Free_Rate) / Volatility
Sortino = (Return - Risk_Free_Rate) / Downside_Deviation
Calmar  = Annualized_Return / Maximum_Drawdown
VaR_95  = Portfolio_Value × Percentile_5(Returns) × √(Time_Horizon)
Max_DD  = Max((Peak_Value - Trough_Value) / Peak_Value)
```

### Integration

- **Portfolio Manager (8003)** — fetches portfolio data, positions, historical values
- **Trading Engine (8005)** — pre-trade risk checks; trading permissions gated on circuit-breaker status
- **API Gateway (8000)** — exposes risk metrics to the frontend dashboard

### Install & Run

```bash
cd services/risk-metrics-service
pip install -r requirements.txt

# Development
uvicorn app.main:app --host 0.0.0.0 --port 8009 --reload

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8009 --workers 4
```

### Environment Variables

```bash
# Service
SERVICE_NAME=risk-metrics-service
SERVICE_PORT=8009
SERVICE_HOST=0.0.0.0
LOG_LEVEL=INFO

# Risk model
RISK_FREE_RATE=0.04                  # 4% annual
TARGET_SHARPE_RATIO=1.5
MAX_PORTFOLIO_RISK=0.05
MAX_POSITION_SIZE=0.02
MAX_DRAWDOWN_THRESHOLD=0.10
MAX_DAILY_LOSS=0.05
MAX_EXPOSURE=0.20

# Circuit breaker (see state machine reference below)
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_COOLDOWN=300              # base cooldown, seconds
CIRCUIT_BREAKER_MAX_COOLDOWN=3600
CIRCUIT_BREAKER_COOLDOWN_MULTIPLIER=2.0
CIRCUIT_BREAKER_HALF_OPEN_MAX_REQUESTS=1
CIRCUIT_BREAKER_DAILY_LOSS_THRESHOLD=0.05
CIRCUIT_BREAKER_DRAWDOWN_THRESHOLD=0.10
CIRCUIT_BREAKER_EXPOSURE_MULTIPLIER=1.2

# Redis cache
REDIS_ENABLED=true
REDIS_URL=redis://localhost:6379
REDIS_CACHE_TTL=30

# HTTP connection pool
MAX_HTTP_CONNECTIONS=100
HTTP_TIMEOUT=10.0

# Request batching
ENABLE_REQUEST_BATCHING=true
BATCH_SIZE=10
BATCH_MAX_WAIT_MS=50

# Performance monitoring
ENABLE_PERFORMANCE_MONITORING=true
PERFORMANCE_HISTORY_SIZE=1000

# External services
PORTFOLIO_MANAGER_URL=http://portfolio-manager:8003
MARKET_DATA_URL=http://market-data:8002
```

> Naming note (2026-07-30): older docs used `ENABLE_CIRCUIT_BREAKER` with a flat `CIRCUIT_BREAKER_COOLDOWN=3600`; the circuit-breaker reference (below) uses `CIRCUIT_BREAKER_ENABLED` with exponential backoff (base 300s, max 3600s). The backoff model is the implemented one (`app/risk_engine.py`); verify var names against `app/config.py` before deploying.

---

## Circuit Breaker — State Machine Reference

```
┌─────────┐  Threshold    ┌─────────┐  Cooldown   ┌────────────┐
│ CLOSED  │─────────────>│  OPEN   │──────────>│ HALF_OPEN  │
│         │   Exceeded    │         │  Expires   │            │
└─────────┘               └─────────┘            └────────────┘
     ↑                                                  │
     │                                                  │
     └──────────────────────────────────────────────────┘
              Success (Recovery Complete)
```

### States

| State | Trading | Description |
|-------|---------|-------------|
| `CLOSED` | Full | Normal operation |
| `OPEN` | None | Cooldown active |
| `HALF_OPEN` | Limited | Testing recovery |

### Trip Conditions

Circuit trips when **ANY** condition is met:
- Daily loss > 5%
- Drawdown > 10%
- Exposure > 24% (20% × 1.2 multiplier)

### Cooldown Progression (exponential backoff)

| Failure # | Cooldown Duration |
|-----------|-------------------|
| 1st | 300s (5 min) |
| 2nd | 600s (10 min) |
| 3rd | 1200s (20 min) |
| 4th | 2400s (40 min) |
| 5th+ | 3600s (1 hour max) |

### Usage

```python
# 1. Check circuit breaker before trading
status = risk_engine.check_circuit_breaker(
    daily_pnl=-0.03,      # -3% daily loss
    drawdown=0.07,        # 7% drawdown
    exposure_ratio=0.18   # 18% exposure
)

# 2. Handle response
if status.can_trade:
    execute_trade()
else:
    logger.warning(f"Trading halted: {status.reason}")
    logger.info(f"Cooldown ends: {status.cooldown_until}")

# 3. Record trade results while HALF_OPEN
if status.state == CircuitBreakerState.HALF_OPEN:
    result = execute_trade()
    risk_engine.record_trade_result(success=result)
```

### Scenarios

```python
# Normal trip and recovery
status = engine.check_circuit_breaker(-0.06, 0.05, 0.15)  # OPEN, can_trade: False
# ...wait 5 minutes...
status = engine.check_circuit_breaker(-0.02, 0.05, 0.15)  # HALF_OPEN, can_trade: True
engine.record_trade_result(success=True)
status = engine.check_circuit_breaker(-0.02, 0.05, 0.15)  # CLOSED

# Failed recovery (in HALF_OPEN)
engine.record_trade_result(success=False)                 # OPEN, cooldown doubled to 600s

# Manual reset (admin)
engine.reset_circuit_breaker()                            # CLOSED immediately
```

### HTTP Interface

- `GET /circuit-breaker` — current state and metrics
- `POST /circuit-breaker/reset` — manual reset (admin auth)

(Older circuit-breaker doc listed these under `/api/v1/circuit-breaker/*`; the service surface uses unprefixed paths — verify against `app/main.py` if a client 404s.)

### Monitoring the Breaker

Key metrics: trip frequency (per day), average cooldown duration, recovery success rate, time to recovery.

Log messages to watch:
```
CRITICAL: Circuit breaker TRIPPED
INFO: Transitioning to HALF_OPEN
INFO: Trade success in HALF_OPEN
WARNING: Trade failed in HALF_OPEN
INFO: Transitioning to CLOSED
```

### Breaker Troubleshooting

| Issue | Solution |
|-------|----------|
| Won't reset | Check if conditions still violated |
| Frequent trips | Review/adjust thresholds |
| Slow recovery | Increase `half_open_max_requests` |
| Extended cooldown | Check failure_count, consider manual reset |

### Files

- **Implementation**: `app/risk_engine.py`
- **Models**: `app/models.py`
- **Config**: `app/config.py`
- **Tests**: `tests/test_circuit_breaker_state_machine.py`
- **Docs**: `docs/CIRCUIT_BREAKER.md`

---

## Performance Metrics Reference (service optimizations)

Four optimizations are built in: Redis caching, HTTP connection pooling, performance monitoring, and request batching.

Measured improvement (2025-11-19 benchmark, local): 50 concurrent requests 1,201ms → <300ms; throughput 41.6 → 166.7 req/s; cache-hit latency <5ms.

### 1. Redis Caching

- **Cached endpoints**: `/risk/scorecard`, `/risk/capital`, `/risk/exposure`, `/risk/drawdown`, `/risk/var`, `/performance/metrics`
- **Cache keys**: `risk_metrics:<endpoint>:{hash}`
- **Config**: `REDIS_ENABLED`, `REDIS_URL`, `REDIS_CACHE_TTL` (default 30s)
- Expected: 85%+ hit rate under normal load, <5ms cached responses, automatic TTL expiration

```bash
# Cache statistics
curl http://localhost:8009/cache/stats

# Invalidate all cache (admin)
curl -X POST http://localhost:8009/cache/invalidate -H "X-Admin-Key: your-admin-key"
```

### 2. HTTP Connection Pooling

- **Config**: `MAX_HTTP_CONNECTIONS` (default 100), `HTTP_TIMEOUT` (default 10.0s)
- Persistent keep-alive connections to downstream services; eliminates TCP/TLS handshake overhead

```bash
curl http://localhost:8009/status | jq '.connection_pool'
# {"max_connections": 100, "active_connections": 5, "available_connections": 95}
```

### 3. Performance Monitoring

- **Config**: `ENABLE_PERFORMANCE_MONITORING`, `PERFORMANCE_HISTORY_SIZE` (default 1000)
- Tracks request counts, response times (p50/p95/p99), cache hit rate, error rate, per-endpoint stats

```bash
curl http://localhost:8009/performance/stats           # overall stats
curl http://localhost:8009/performance/stats | jq '.last_5_minutes'
curl -X POST http://localhost:8009/performance/reset -H "X-Admin-Key: your-admin-key"
```

### 4. Request Batching

- **Config**: `ENABLE_REQUEST_BATCHING`, `BATCH_SIZE` (default 10), `BATCH_MAX_WAIT_MS` (default 50)
- Similar requests grouped by batch key; batch processes when size reached or timer expires; all requests in batch share one result. Reduces duplicate calculation by up to 90% with ≤50ms added latency.

### Verify Optimizations Active

```bash
curl http://localhost:8009/ | jq '.optimizations'
# {"redis_caching": true, "request_batching": true,
#  "performance_monitoring": true, "connection_pooling": true}
```

### Alert Thresholds

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| Cache Hit Rate | <70% | <50% | Check Redis, review TTL |
| P95 Response Time | >500ms | >1000ms | Scale service, check deps |
| Error Rate | >1% | >5% | Check logs, review alerts |
| Pool Utilization | >80% | >95% | Increase pool size |

Targets: single request <100ms; 50-concurrent <500ms; cached <10ms; throughput 100+ req/s (target 200+); cache hit rate >80%.

### Scaling Guidance

| Load | Redis | Connections | Cache TTL | Instances |
|------|-------|-------------|-----------|-----------|
| <100 req/s | single instance | 50-100 | 30s | 1-2 |
| 100-500 req/s | single + persistence | 100-200 | 15-30s | 2-4 |
| >500 req/s | cluster/Sentinel | 200-500 | 10-15s | 4+ |

### Optimization Troubleshooting

**Redis not connected** (cache-disabled warnings, all misses):
```bash
docker ps | grep redis
redis-cli ping
docker logs risk-metrics-service | grep -i redis   # container name per unified compose
echo $REDIS_URL
```

**Low cache hit rate** (<50%): TTL too short, varying request parameters, or high invalidation.
```bash
export REDIS_CACHE_TTL=60
curl http://localhost:8009/cache/stats
curl http://localhost:8009/performance/stats | jq '.endpoints'
```

**Connection pool exhaustion** (timeouts, "too many connections"):
```bash
curl http://localhost:8009/status | jq '.connection_pool'
export MAX_HTTP_CONNECTIONS=200   # then restart service
```

**Slow responses** (p95 > 1000ms):
```bash
curl http://localhost:8009/cache/stats                    # 1. cache working?
curl http://localhost:8009/status | jq '.connection_pool' # 2. pool ok?
curl http://localhost:8003/health                         # 3. Portfolio Manager up?
curl http://localhost:8009/performance/stats              # 4. stats
redis-cli --latency                                       # 5. Redis latency
```

### Optimization Code Files

- `app/cache.py` — Redis caching
- `app/performance.py` — monitoring and batching
- `app/main.py` — application wiring
- `app/config.py` — settings
- Tests: `tests/test_cache.py`, `tests/test_performance.py`, `test_performance.sh`

---

## Quick Commands

### Health & Status
```bash
curl http://localhost:8009/health
curl http://localhost:8009/status
curl http://localhost:8009/ | jq '.optimizations'
```

### Risk Endpoints
```bash
curl http://localhost:8009/risk/scorecard      # complete assessment
curl http://localhost:8009/risk/capital
curl http://localhost:8009/risk/exposure
curl http://localhost:8009/risk/drawdown
curl http://localhost:8009/risk/var
curl http://localhost:8009/performance/metrics
curl http://localhost:8009/circuit-breaker
```

### Quick Health Checks
```bash
curl -s http://localhost:8009/cache/stats | jq '.hit_rate_pct'                          # >80%
curl -s http://localhost:8009/performance/stats | jq '.summary.p95_response_time_ms'    # <500ms
curl -s http://localhost:8009/performance/stats | jq '.summary.error_rate_pct'          # <1%
curl -s http://localhost:8009/status | jq '.connection_pool.active_connections'         # <80% of max
```

### Testing
```bash
./test_performance.sh                                     # full perf suite
./test_performance.sh --test cache                        # specific test
time curl http://localhost:8009/risk/scorecard            # single request timing
curl -w "\nTime: %{time_total}s\n" http://localhost:8009/risk/scorecard   # run twice: miss vs hit
ab -n 100 -c 50 http://localhost:8009/risk/scorecard      # load test (Apache Bench)
pytest tests/ -v --cov=app                                # unit tests
```

### Service Management
```bash
# Development / production
uvicorn app.main:app --reload --port 8009
uvicorn app.main:app --host 0.0.0.0 --port 8009 --workers 4

# Docker (canonical compose)
docker compose -f docker-compose.unified.yml up -d risk-metrics-service
docker compose -f docker-compose.unified.yml stop risk-metrics-service
docker compose -f docker-compose.unified.yml logs -f risk-metrics-service
docker logs risk-metrics-service | grep -i "performance\|cache"
```

### Live Monitoring
```bash
watch -n 5 'curl -s http://localhost:8009/performance/stats | jq ".summary"'
watch -n 5 'curl -s http://localhost:8009/cache/stats | jq ".hit_rate_pct"'
```

### Python Usage Example

```python
import httpx

# Get complete risk assessment
scorecard = httpx.get("http://localhost:8009/risk/scorecard").json()
print(f"Risk Level: {scorecard['overall_risk_level']}")
print(f"Risk Score: {scorecard['risk_score']}/100")
print(f"Sharpe Ratio: {scorecard['performance_metrics']['sharpe_ratio']}")
print(f"Current Drawdown: {scorecard['drawdown_metrics']['current_drawdown']*100}%")

# Check if trading is allowed
breaker = httpx.get("http://localhost:8009/circuit-breaker").json()
if not breaker['can_trade']:
    print(f"Trading halted: {breaker['reason']}")
```

---

## Security

- Risk limit updates and circuit-breaker reset require admin authentication (`X-Admin-Key`)
- Sensitive metrics are logged but not exposed publicly
- Rate limiting on all endpoints

## Dependencies

FastAPI, NumPy, Pydantic, httpx, redis (optional cache).

## Future Enhancements

- [ ] Monte Carlo VaR simulation
- [ ] Stress testing scenarios
- [ ] Correlation analysis
- [ ] Machine learning-based risk prediction
- [ ] Real-time WebSocket streaming
- [ ] Custom risk models
- [ ] Backtesting integration

---

**Integration:** Portfolio Manager, Trading Engine, API Gateway
**Critical:** Yes — halts trading on risk threshold breaches
