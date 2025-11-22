# Monitoring Documentation Index

**Last Updated:** 2025-11-21
**Status:** Complete

This index provides quick access to all monitoring-related documentation for the crypto trading bot.

---

## Quick Access

### For Operators

**Start Here:**
1. [MONITORING_QUICK_REFERENCE.txt](/mnt/d/Bimo_max/crypto-trading-bot/MONITORING_QUICK_REFERENCE.txt) - Visual status and quick commands
2. [Grafana Dashboard](http://localhost:3001) - Login: admin / crypto-bot-admin
3. [Prometheus](http://localhost:9090) - Metrics explorer

**When Issues Occur:**
- [Operations Runbook](/mnt/d/Bimo_max/crypto-trading-bot/docs/operations/RUNBOOK.md)
- [Troubleshooting Section in MONITORING_GUIDE.md](/mnt/d/Bimo_max/crypto-trading-bot/docs/MONITORING_GUIDE.md#troubleshooting)

### For Developers

**Start Here:**
1. [MONITORING_GUIDE.md](/mnt/d/Bimo_max/crypto-trading-bot/docs/MONITORING_GUIDE.md) - Complete reference
2. [PROMETHEUS_INSTRUMENTATION_GUIDE.md](/mnt/d/Bimo_max/crypto-trading-bot/infrastructure/monitoring/PROMETHEUS_INSTRUMENTATION_GUIDE.md) - Add metrics to services

**For Implementation:**
- [Metrics Endpoint Fix Instructions](#fixing-metrics-endpoints)
- [Dashboard Creation Guide](/mnt/d/Bimo_max/crypto-trading-bot/docs/MONITORING_GUIDE.md#grafana-dashboards)

### For Management

**Start Here:**
1. [MONITORING_STATUS_REPORT.md](/mnt/d/Bimo_max/crypto-trading-bot/MONITORING_STATUS_REPORT.md) - Executive summary
2. [Current Issues and Priorities](#current-status-summary)

---

## Documentation Files

### Primary Documentation (New - 2025-11-21)

| Document | Purpose | Location | Size |
|----------|---------|----------|------|
| **MONITORING_GUIDE.md** | Complete monitoring reference | `/docs/` | 30KB |
| **MONITORING_STATUS_REPORT.md** | Current status and action plan | `/` | 15KB |
| **MONITORING_QUICK_REFERENCE.txt** | Visual quick reference | `/` | 8KB |
| **MONITORING_INDEX.md** | This file - documentation index | `/docs/` | 5KB |

### Infrastructure Documentation (Existing)

| Document | Purpose | Location |
|----------|---------|----------|
| **monitoring/README.md** | Monitoring stack overview | `/infrastructure/monitoring/` |
| **MONITORING_SETUP_GUIDE.md** | Setup procedures | `/infrastructure/monitoring/` |
| **PROMETHEUS_INSTRUMENTATION_GUIDE.md** | Metrics implementation | `/infrastructure/monitoring/` |
| **QUICK_REFERENCE.md** | Infrastructure quick ref | `/infrastructure/monitoring/` |

### Operations Documentation (Existing)

| Document | Purpose | Location |
|----------|---------|----------|
| **operations/RUNBOOK.md** | Operational procedures | `/docs/operations/` |
| **operations/DISASTER_RECOVERY.md** | DR procedures | `/docs/operations/` |
| **operations/PERFORMANCE_REPORTING.md** | Performance reports | `/docs/operations/` |

---

## Current Status Summary

### What's Working ✅

- **Prometheus**: Running and collecting metrics from 2/10 services
- **Grafana**: Accessible at http://localhost:3001
- **Bybit Connector**: Full metrics exposure (HTTP + custom)
- **Market Data Service**: Standard metrics exposed

### What Needs Work ❌

- **8 Services**: Missing `/metrics` endpoint (404 errors)
- **Custom Metrics**: Defined but not exposed
- **Dashboards**: Only 1 configured (showing "No data")
- **AlertManager**: Not deployed
- **Alerting**: No rules configured

### Priority Actions

1. **Fix Metrics Endpoints** (1-2 hours) - See [guide below](#fixing-metrics-endpoints)
2. **Create Dashboards** (2-3 hours) - See [MONITORING_GUIDE.md](/mnt/d/Bimo_max/crypto-trading-bot/docs/MONITORING_GUIDE.md#grafana-dashboards)
3. **Configure Alerting** (1-2 hours) - See [alert rules](/mnt/d/Bimo_max/crypto-trading-bot/docs/MONITORING_GUIDE.md#alerting-rules)

---

## Common Tasks

### Accessing Monitoring Tools

```bash
# Open Grafana
open http://localhost:3001
# Credentials: admin / crypto-bot-admin

# Open Prometheus
open http://localhost:9090

# Check monitoring stack status
docker ps | grep -E "(prometheus|grafana)"
```

### Checking Service Health

```bash
# View Prometheus targets status
curl -s http://localhost:9090/api/v1/targets | python3 -m json.tool | grep health

# Test all service metrics endpoints
for port in 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009; do
  status=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:$port/metrics)
  echo "Port $port: $status"
done
```

### Viewing Metrics

```bash
# View bybit-connector metrics
curl http://localhost:8001/metrics | grep -E "(http_requests|process_)"

# View market-data metrics
curl http://localhost:8002/metrics | grep -E "(http_requests|process_)"

# Query Prometheus directly
curl "http://localhost:9090/api/v1/query?query=up"
```

---

## Fixing Metrics Endpoints

This is the **highest priority** task. 8 services need metrics endpoints added.

### Services Requiring Fix

- api-gateway (8000)
- portfolio-manager (8003)
- technical-analysis (8004)
- trading-engine (8005)
- notification (8006)
- ml-prediction (8007)
- sentiment-analysis (8008)
- risk-metrics (8009)

### Quick Fix Steps

**For each service:**

1. **Edit the main.py file:**
```bash
nano /mnt/d/Bimo_max/crypto-trading-bot/services/[SERVICE]/app/main.py
```

2. **Add these imports (if not present):**
```python
from prometheus_client import make_asgi_app
```

3. **Add metrics endpoint (before app.run()):**
```python
# Mount Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
```

4. **Restart the service:**
```bash
docker restart crypto-bot-[SERVICE]
```

5. **Verify it works:**
```bash
curl http://localhost:[PORT]/metrics | head -20
```

### Example: Trading Engine

**File:** `/mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine/app/main.py`

**Add near the top (imports section):**
```python
from prometheus_client import make_asgi_app
```

**Add before `if __name__ == "__main__"`:**
```python
# Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
```

**Restart and verify:**
```bash
docker restart crypto-bot-trading
curl http://localhost:8005/metrics | grep http_requests_total
```

### Verification Script

After fixing all services, run:

```bash
#!/bin/bash
echo "Checking all service metrics endpoints..."
services=(
  "api-gateway:8000"
  "bybit-connector:8001"
  "market-data:8002"
  "portfolio-manager:8003"
  "technical-analysis:8004"
  "trading-engine:8005"
  "notification:8006"
  "ml-prediction:8007"
  "sentiment-analysis:8008"
  "risk-metrics:8009"
)

success=0
failed=0

for service in "${services[@]}"; do
  name="${service%:*}"
  port="${service#*:}"
  status=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:$port/metrics)

  if [ "$status" = "200" ]; then
    echo "✅ $name (port $port): OK"
    ((success++))
  else
    echo "❌ $name (port $port): HTTP $status"
    ((failed++))
  fi
done

echo ""
echo "Summary: $success OK, $failed Failed"
```

---

## Creating Dashboards

### Dashboard Priority Order

1. **System Health Overview** (Priority 1)
   - Service uptime indicators
   - Memory and CPU usage
   - Request rate by service
   - Error rate tracking

2. **Trading Performance** (Priority 2)
   - Active positions gauge
   - Daily P&L tracking
   - Win rate percentage
   - Trade execution rate

3. **API Performance** (Priority 3)
   - Request rate by endpoint
   - Latency percentiles (P50, P95, P99)
   - Error rate by service
   - Status code distribution

4. **Market Data Quality** (Priority 4)
   - Data fetch rate
   - Bybit API rate limit usage
   - Data freshness metrics

5. **Risk Management** (Priority 5)
   - Risk scores
   - Capital utilization
   - Drawdown tracking
   - Circuit breaker status

### Dashboard Creation Guide

Full dashboard creation instructions with panel definitions and queries are in:
**[MONITORING_GUIDE.md - Grafana Dashboards Section](/mnt/d/Bimo_max/crypto-trading-bot/docs/MONITORING_GUIDE.md#grafana-dashboards)**

---

## Available Metrics Reference

### Standard Metrics (All Services)

| Metric | Type | Description |
|--------|------|-------------|
| `up` | Gauge | Service health (1=up, 0=down) |
| `http_requests_total` | Counter | Total HTTP requests |
| `http_request_duration_seconds` | Histogram | Request latency |
| `process_resident_memory_bytes` | Gauge | Memory usage |
| `process_cpu_seconds_total` | Counter | CPU time consumed |
| `process_open_fds` | Gauge | Open file descriptors |

### Custom Business Metrics

| Metric | Service | Type | Description |
|--------|---------|------|-------------|
| `trading_signals_total` | trading-engine | Counter | Signals generated |
| `trade_executions_total` | trading-engine | Counter | Trades executed |
| `active_positions` | trading-engine | Gauge | Open positions |
| `account_balance` | trading-engine | Gauge | Account balance |
| `daily_loss_percentage` | trading-engine | Gauge | Daily loss % |
| `win_rate` | trading-engine | Gauge | Win rate % |
| `risk_score_gauge` | risk-metrics | Gauge | Current risk score |
| `portfolio_value_gauge` | risk-metrics | Gauge | Portfolio value |
| `circuit_breaker_trips` | risk-metrics | Counter | CB activations |

**Full metrics catalog:** [MONITORING_GUIDE.md - Available Metrics](/mnt/d/Bimo_max/crypto-trading-bot/docs/MONITORING_GUIDE.md#available-metrics)

---

## Alert Rules Reference

### Critical Alerts (4)

1. **TradingEngineDown** - Trading engine offline >30s
2. **DailyLossExceeded** - Daily loss >5%
3. **ServiceDown** - Any service offline >1min
4. **HighErrorRate** - Error rate >5% for 5min

### Warning Alerts (5)

5. **HighAPILatency** - P99 latency >1s for 5min
6. **HighMemoryUsage** - Memory >1GB for 10min
7. **CircuitBreakerOpen** - Circuit breaker activated
8. **LowWinRate** - Win rate <40% for 1hr
9. **BybitRateLimitHit** - Rate limit errors detected

**Full alert definitions with YAML config:** [MONITORING_GUIDE.md - Alerting Rules](/mnt/d/Bimo_max/crypto-trading-bot/docs/MONITORING_GUIDE.md#alerting-rules)

---

## Useful Prometheus Queries

### Service Health

```promql
# All services status
up{job=~".*"}

# Request rate by service
sum by (job) (rate(http_requests_total[5m]))

# Memory usage by service (MB)
process_resident_memory_bytes{job=~".*"} / 1024 / 1024
```

### API Performance

```promql
# P99 latency
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))

# Error rate percentage
sum(rate(http_requests_total{status_code=~"5.."}[5m]))
/ sum(rate(http_requests_total[5m])) * 100

# Requests by endpoint
sum by (endpoint) (rate(http_requests_total[5m]))
```

### Trading Metrics (When Available)

```promql
# Active positions
sum(active_positions)

# Daily P&L
daily_loss_percentage

# Win rate
win_rate

# Trades per minute
rate(trade_executions_total[1m]) * 60
```

**More queries:** [MONITORING_GUIDE.md - Example Queries](/mnt/d/Bimo_max/crypto-trading-bot/docs/MONITORING_GUIDE.md#available-metrics)

---

## Troubleshooting

### Issue: Grafana Shows "No Data"

**Diagnosis:**
```bash
# Check if Prometheus is scraping
curl http://localhost:9090/api/v1/targets | python3 -m json.tool | grep health

# Verify metrics exist
curl http://localhost:8001/metrics | grep http_requests_total
```

**Solution:** See [MONITORING_GUIDE.md - Troubleshooting](/mnt/d/Bimo_max/crypto-trading-bot/docs/MONITORING_GUIDE.md#troubleshooting)

### Issue: Service Metrics Return 404

**Diagnosis:**
```bash
curl -I http://localhost:8005/metrics
# HTTP/1.1 404 Not Found
```

**Solution:** [Fix metrics endpoints](#fixing-metrics-endpoints) (documented above)

### Issue: High Prometheus Memory Usage

**Solution:**
- Reduce retention period in docker-compose.yml
- Increase scrape intervals for non-critical services
- Use recording rules for expensive queries

**Full troubleshooting guide:** [MONITORING_GUIDE.md - Troubleshooting](/mnt/d/Bimo_max/crypto-trading-bot/docs/MONITORING_GUIDE.md#troubleshooting)

---

## Related Documentation

### Project Documentation
- [README.md](/mnt/d/Bimo_max/crypto-trading-bot/README.md) - Project overview
- [SYSTEM_ARCHITECTURE.md](/mnt/d/Bimo_max/crypto-trading-bot/SYSTEM_ARCHITECTURE.md) - Architecture
- [DEPLOYMENT.md](/mnt/d/Bimo_max/crypto-trading-bot/DEPLOYMENT.md) - Deployment guide

### Operations
- [RUNBOOK.md](/mnt/d/Bimo_max/crypto-trading-bot/docs/operations/RUNBOOK.md) - Operational procedures
- [DISASTER_RECOVERY.md](/mnt/d/Bimo_max/crypto-trading-bot/docs/operations/DISASTER_RECOVERY.md) - DR procedures

### Development
- [GETTING_STARTED.md](/mnt/d/Bimo_max/crypto-trading-bot/GETTING_STARTED.md) - Dev setup
- [API Documentation](/mnt/d/Bimo_max/crypto-trading-bot/docs/api/) - API reference

---

## External Resources

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [PromQL Tutorial](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Grafana Dashboard Examples](https://grafana.com/grafana/dashboards/)

---

## Support and Contact

For issues or questions about monitoring:

1. Check this documentation first
2. Review [MONITORING_GUIDE.md](/mnt/d/Bimo_max/crypto-trading-bot/docs/MONITORING_GUIDE.md) troubleshooting section
3. Check service logs: `docker logs crypto-bot-[service-name]`
4. Refer to project issue tracker

---

**Last Updated:** 2025-11-21
**Maintained By:** DevOps Team
**Status:** Complete - Ready for implementation
