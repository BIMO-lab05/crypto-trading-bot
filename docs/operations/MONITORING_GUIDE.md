# Crypto Trading Bot - Monitoring Guide

**Version:** 1.0
**Last Updated:** 2025-11-21
**Status:** Production Ready

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Available Metrics](#available-metrics)
4. [Grafana Dashboards](#grafana-dashboards)
5. [Alerting Rules](#alerting-rules)
6. [Troubleshooting](#troubleshooting)
7. [Best Practices](#best-practices)

---

## Overview

The crypto trading bot uses a comprehensive monitoring stack based on **Prometheus** (metrics collection) and **Grafana** (visualization). This guide documents all available metrics, dashboards, and alerting configurations.

### Monitoring Stack Status

| Component | Status | URL | Default Credentials |
|-----------|--------|-----|---------------------|
| **Prometheus** | ✅ Running | http://localhost:9090 | N/A |
| **Grafana** | ✅ Running | http://localhost:3001 | see `.env` — **rotate the burned default** |
| **Services** | ✅ 9/11 services exposing metrics | Various ports | N/A |

### Current Configuration

- **Prometheus Data Retention:** 15 days
- **Scrape Interval:** 10-30 seconds (varies by service)
- **Metrics Format:** Prometheus exposition format
- **Network:** crypto-bot-network (Docker bridge)

---

## Quick Start

### Access Monitoring Dashboards

```bash
# 1. Verify monitoring services are running
docker ps | grep -E "(prometheus|grafana)"

# Expected output:
# crypto-bot-grafana       Up X minutes (healthy)   0.0.0.0:3001->3000/tcp
# crypto-bot-prometheus    Up X minutes (healthy)   0.0.0.0:9090->9090/tcp

# 2. Access Grafana
open http://localhost:3001
# Login: see `.env` — **rotate the burned default**

# 3. Access Prometheus (for raw metrics)
open http://localhost:9090
```

### Verify Metrics Collection

```bash
# Check Prometheus targets status
curl -s http://localhost:9090/api/v1/targets | python3 -m json.tool

# Check specific service metrics
curl http://localhost:8001/metrics  # Bybit Connector
curl http://localhost:8002/metrics  # Market Data Service

# View all available metrics
curl -s http://localhost:9090/api/v1/label/__name__/values | python3 -m json.tool
```

---

## Available Metrics

### Service Health Metrics (All Services)

These metrics are available from **all microservices** at their `/metrics` endpoint:

#### HTTP Request Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `http_requests_total` | Counter | method, endpoint, status_code | Total HTTP requests by endpoint |
| `http_request_duration_seconds` | Histogram | method, endpoint | Request latency distribution |
| `http_requests_in_progress` | Gauge | - | Currently processing requests |
| `http_requests_active` | Gauge | - | Active HTTP connections |

**Example Queries:**
```promql
# Request rate per endpoint
rate(http_requests_total[5m])

# P99 latency by endpoint
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))

# Error rate (5xx responses)
rate(http_requests_total{status_code=~"5.."}[5m])

# Success rate percentage
sum(rate(http_requests_total{status_code=~"2.."}[5m]))
/
sum(rate(http_requests_total[5m])) * 100
```

#### Python Runtime Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `python_info` | Gauge | Python version information |
| `python_gc_collections_total` | Counter | Garbage collection runs by generation |
| `process_cpu_seconds_total` | Counter | Total CPU time consumed |
| `process_resident_memory_bytes` | Gauge | Resident memory size |
| `process_virtual_memory_bytes` | Gauge | Virtual memory size |
| `process_open_fds` | Gauge | Number of open file descriptors |
| `process_max_fds` | Gauge | Maximum file descriptors allowed |

**Example Queries:**
```promql
# Memory usage by service
process_resident_memory_bytes{job=~".*"}

# CPU usage rate
rate(process_cpu_seconds_total[5m])

# File descriptor usage percentage
process_open_fds / process_max_fds * 100
```

---

### Trading Engine Metrics (Port 8005)

**Status:** ⚠️ Metrics endpoint not exposing all custom metrics (404 errors in Prometheus)

#### Trading Performance Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `trading_signals_total` | Counter | symbol, signal_type, strategy | Trading signals generated |
| `trade_executions_total` | Counter | symbol, side, status | Completed trade executions |
| `trade_errors_total` | Counter | symbol, error_type | Trade execution errors |
| `active_positions` | Gauge | symbol | Current open positions |
| `position_unrealized_pnl` | Gauge | symbol, position_id | Unrealized P&L per position |
| `total_trades` | Counter | result | Total trades (win/loss) |

**Example Queries:**
```promql
# Trades per minute
rate(trade_executions_total[1m]) * 60

# Trade success rate
sum(rate(trade_executions_total{status="success"}[5m]))
/
sum(rate(trade_executions_total[5m])) * 100

# Total active positions
sum(active_positions)

# Total unrealized P&L
sum(position_unrealized_pnl)

# Win rate percentage
sum(total_trades{result="win"})
/
sum(total_trades) * 100
```

#### Portfolio & Balance Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `account_balance` | Gauge | account_type | Current cash balance |
| `account_total_equity` | Gauge | account_type | Total equity (balance + unrealized P&L) |
| `win_rate` | Gauge | - | Win rate percentage |
| `roi` | Gauge | - | Return on investment percentage |

**Example Queries:**
```promql
# Total account equity
account_total_equity{account_type="paper"}

# Portfolio growth over time
rate(account_total_equity[1h])

# Current win rate
win_rate

# ROI percentage
roi
```

#### Risk Management Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `daily_loss_amount` | Gauge | - | Current daily loss in USD |
| `daily_loss_percentage` | Gauge | - | Current daily loss as percentage |
| `risk_limit_violations_total` | Counter | violation_type | Risk limit breaches |

**Example Queries:**
```promql
# Current daily loss
daily_loss_amount

# Daily loss percentage
daily_loss_percentage

# Risk violations in last hour
increase(risk_limit_violations_total[1h])

# Alert if daily loss exceeds 5%
daily_loss_percentage > 5
```

---

### Risk Metrics Service (Port 8009)

**Status:** ⚠️ Metrics endpoint not configured (404 errors in Prometheus)

#### Risk Calculation Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `risk_calculations_total` | Counter | calculation_type | Risk calculations performed |
| `risk_calculation_duration_seconds` | Histogram | calculation_type | Risk calculation latency |
| `risk_score_gauge` | Gauge | risk_type | Current risk score |
| `risk_alerts_total` | Counter | alert_type | Risk alerts triggered |

#### Portfolio Risk Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `portfolio_value_gauge` | Gauge | - | Current portfolio value |
| `capital_utilization_gauge` | Gauge | - | Capital utilization percentage |
| `exposure_ratio_gauge` | Gauge | - | Market exposure ratio |
| `drawdown_current_gauge` | Gauge | - | Current drawdown percentage |
| `sharpe_ratio_gauge` | Gauge | - | Sharpe ratio |

#### Circuit Breaker Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `circuit_breaker_trips` | Counter | breaker_name | Circuit breaker activations |
| `circuit_breaker_active_gauge` | Gauge | breaker_name | Circuit breaker state (0=closed, 1=open) |

**Example Queries:**
```promql
# Portfolio value over time
portfolio_value_gauge

# Capital utilization
capital_utilization_gauge

# Current drawdown
drawdown_current_gauge

# Alert if drawdown exceeds 10%
drawdown_current_gauge > 10

# Circuit breaker activations in last 24h
increase(circuit_breaker_trips[24h])
```

---

### Market Data Service (Port 8002)

**Status:** ✅ Metrics exposed successfully

#### Data Collection Metrics

Available via standard HTTP metrics, specific custom metrics to be documented once exposed.

**Example Queries:**
```promql
# Market data request rate
rate(http_requests_total{job="market-data-service"}[5m])

# Data fetch latency
histogram_quantile(0.95,
  rate(http_request_duration_seconds_bucket{job="market-data-service"}[5m])
)
```

---

### Bybit Connector (Port 8001)

**Status:** ✅ Metrics exposed successfully

The Bybit connector tracks API usage and rate limiting:

#### API Call Metrics

| Metric | Type | Example Labels | Description |
|--------|------|----------------|-------------|
| `http_requests_total` | Counter | endpoint="/api/v1/market/kline", status_code="200" | Bybit API calls |
| `http_requests_total` | Counter | endpoint="/api/v1/market/kline", status_code="429" | Rate limit hits |

**Example Queries:**
```promql
# Bybit API call rate
rate(http_requests_total{job="bybit-connector"}[5m])

# Rate limit violations
sum(rate(http_requests_total{job="bybit-connector", status_code="429"}[5m]))

# API success rate
sum(rate(http_requests_total{job="bybit-connector", status_code="200"}[5m]))
/
sum(rate(http_requests_total{job="bybit-connector"}[5m])) * 100
```

---

### ML Prediction Service (Port 8007)

**Status:** ⚠️ Metrics endpoint not configured (404 errors in Prometheus)

**Expected Metrics (when configured):**
- `ml_prediction_requests_total` - Prediction requests
- `ml_model_inference_duration_seconds` - Model inference time
- `ml_prediction_accuracy` - Prediction accuracy metrics

---

### Sentiment Analysis Service (Port 8008)

**Status:** ⚠️ Metrics endpoint not configured (404 errors in Prometheus)

**Expected Metrics (when configured):**
- `sentiment_analysis_requests_total` - Analysis requests
- `sentiment_score_gauge` - Current sentiment scores
- `news_articles_processed_total` - Processed news articles

---

### Technical Analysis Service (Port 8004)

**Status:** ⚠️ Metrics endpoint not configured (404 errors in Prometheus)

**Expected Metrics (when configured):**
- `indicator_calculations_total` - Indicator calculations
- `signal_generation_total` - Generated signals
- `indicator_calculation_duration_seconds` - Calculation latency

---

### Portfolio Manager (Port 8003)

**Status:** ⚠️ Metrics endpoint not configured (404 errors in Prometheus)

**Expected Metrics (when configured):**
- `portfolio_update_total` - Portfolio updates
- `position_changes_total` - Position changes
- `pnl_calculation_duration_seconds` - P&L calculation time

---

### API Gateway (Port 8000)

**Status:** ⚠️ Metrics endpoint not configured (404 errors in Prometheus)

**Expected Metrics (when configured):**
- `gateway_requests_total` - Total gateway requests
- `upstream_requests_total` - Requests to upstream services
- `gateway_response_time_seconds` - Response time

---

## Grafana Dashboards

### Available Dashboards

#### 1. Phase 3 AI Services Dashboard

**Location:** Pre-configured at `/etc/grafana/provisioning/dashboards/phase3.json`

**Panels:**
- ML Prediction request rate
- Sentiment analysis request rate
- Risk calculations per second
- Service health status
- API latency percentiles

**Access:**
```
http://localhost:3001
Folder: "Crypto Trading Bot"
Dashboard: "Phase 3 AI Services"
```

### Creating Custom Dashboards

#### Dashboard 1: System Health Overview

**Purpose:** Monitor overall system health and container status

**Panels to Create:**

1. **Service Uptime**
```promql
# Query
up{job=~".*"}

# Panel Type: Stat
# Thresholds: 0 (red), 1 (green)
```

2. **Request Rate by Service**
```promql
# Query
sum by (job) (rate(http_requests_total[5m]))

# Panel Type: Time series
# Legend: {{job}}
```

3. **Memory Usage by Service**
```promql
# Query
process_resident_memory_bytes{job=~".*"} / 1024 / 1024

# Panel Type: Time series
# Unit: MB
# Legend: {{job}}
```

4. **CPU Usage by Service**
```promql
# Query
rate(process_cpu_seconds_total{job=~".*"}[5m])

# Panel Type: Time series
# Legend: {{job}}
```

5. **Error Rate Dashboard**
```promql
# Query
sum by (job) (rate(http_requests_total{status_code=~"5.."}[5m]))

# Panel Type: Time series
# Color: Red
# Legend: {{job}} errors
```

---

#### Dashboard 2: Trading Performance

**Purpose:** Track trading activity, P&L, and positions

**Panels to Create:**

1. **Active Positions Gauge**
```promql
# Query
sum(active_positions)

# Panel Type: Gauge
# Min: 0, Max: 10
# Thresholds: 0-3 (green), 3-7 (yellow), 7+ (red)
```

2. **Daily P&L**
```promql
# Query
daily_loss_percentage

# Panel Type: Gauge
# Min: -10, Max: 10
# Thresholds: <-5 (red), -5 to 0 (yellow), >0 (green)
```

3. **Trades Executed Today**
```promql
# Query
increase(trade_executions_total[24h])

# Panel Type: Stat
```

4. **Win Rate**
```promql
# Query
win_rate

# Panel Type: Gauge
# Min: 0, Max: 100
# Unit: percent
```

5. **Portfolio Value Over Time**
```promql
# Query
account_total_equity{account_type="paper"}

# Panel Type: Time series
# Unit: currency ($)
```

6. **Trade Execution Rate**
```promql
# Query
rate(trade_executions_total[5m]) * 60

# Panel Type: Time series
# Unit: trades per minute
```

---

#### Dashboard 3: API Performance

**Purpose:** Monitor API response times and error rates

**Panels to Create:**

1. **Request Rate by Endpoint**
```promql
# Query
sum by (endpoint) (rate(http_requests_total[5m]))

# Panel Type: Bar chart
# Legend: {{endpoint}}
```

2. **P50, P95, P99 Latency**
```promql
# Query 1 (P50)
histogram_quantile(0.50,
  sum by (le) (rate(http_request_duration_seconds_bucket[5m]))
)

# Query 2 (P95)
histogram_quantile(0.95,
  sum by (le) (rate(http_request_duration_seconds_bucket[5m]))
)

# Query 3 (P99)
histogram_quantile(0.99,
  sum by (le) (rate(http_request_duration_seconds_bucket[5m]))
)

# Panel Type: Time series
# Unit: seconds
```

3. **Error Rate by Service**
```promql
# Query
sum by (job) (
  rate(http_requests_total{status_code=~"[45].."}[5m])
) / sum by (job) (
  rate(http_requests_total[5m])
) * 100

# Panel Type: Time series
# Unit: percent
```

4. **Requests by Status Code**
```promql
# Query
sum by (status_code) (rate(http_requests_total[5m]))

# Panel Type: Pie chart
```

---

#### Dashboard 4: ML Model Performance

**Purpose:** Monitor ML prediction accuracy and performance

**Panels to Create (when metrics are available):**

1. **Prediction Request Rate**
```promql
# Query
rate(ml_prediction_requests_total[5m])

# Panel Type: Time series
```

2. **Model Inference Time**
```promql
# Query
histogram_quantile(0.95,
  rate(ml_model_inference_duration_seconds_bucket[5m])
)

# Panel Type: Time series
# Unit: seconds
```

3. **Prediction Accuracy**
```promql
# Query
ml_prediction_accuracy

# Panel Type: Gauge
# Min: 0, Max: 100
# Unit: percent
```

---

#### Dashboard 5: Market Data Quality

**Purpose:** Monitor data collection and freshness

**Panels to Create:**

1. **Data Fetch Rate**
```promql
# Query
rate(http_requests_total{job="market-data-service"}[5m])

# Panel Type: Time series
```

2. **Data Fetch Latency**
```promql
# Query
histogram_quantile(0.95,
  rate(http_request_duration_seconds_bucket{job="market-data-service"}[5m])
)

# Panel Type: Time series
```

3. **Bybit API Rate Limit Usage**
```promql
# Query
sum(rate(http_requests_total{job="bybit-connector", status_code="429"}[5m]))

# Panel Type: Time series
# Color: Red
# Alert when > 0
```

---

## Alerting Rules

### Critical Alerts (Immediate Action Required)

#### Alert 1: Trading Engine Down
```yaml
- alert: TradingEngineDown
  expr: up{job="trading-engine"} == 0
  for: 30s
  labels:
    severity: critical
    component: trading-engine
  annotations:
    summary: "Trading Engine is down"
    description: "Trading Engine has been down for 30 seconds. No trades can be executed."
    action: "Check service logs: docker logs crypto-bot-trading"
```

#### Alert 2: Daily Loss Exceeded
```yaml
- alert: DailyLossExceeded
  expr: daily_loss_percentage > 5
  for: 1m
  labels:
    severity: critical
    component: risk-management
  annotations:
    summary: "Daily loss limit exceeded"
    description: "Current daily loss: {{ $value }}%. Emergency stop may be required."
    action: "Review trades and consider emergency stop"
```

#### Alert 3: Service Down
```yaml
- alert: ServiceDown
  expr: up{job=~".*"} == 0
  for: 1m
  labels:
    severity: critical
    service: "{{ $labels.job }}"
  annotations:
    summary: "Service {{ $labels.job }} is down"
    description: "Service {{ $labels.job }} has been down for 1 minute."
    action: "Restart service: docker restart crypto-bot-{{ $labels.job }}"
```

#### Alert 4: High Error Rate
```yaml
- alert: HighErrorRate
  expr: |
    sum by (job) (rate(http_requests_total{status_code=~"5.."}[5m]))
    /
    sum by (job) (rate(http_requests_total[5m]))
    * 100 > 5
  for: 5m
  labels:
    severity: critical
    service: "{{ $labels.job }}"
  annotations:
    summary: "High error rate in {{ $labels.job }}"
    description: "Error rate is {{ $value }}% in the last 5 minutes."
    action: "Check service logs for errors"
```

### Warning Alerts (Investigation Required)

#### Alert 5: High API Latency
```yaml
- alert: HighAPILatency
  expr: |
    histogram_quantile(0.99,
      rate(http_request_duration_seconds_bucket[5m])
    ) > 1
  for: 5m
  labels:
    severity: warning
    component: api
  annotations:
    summary: "High API latency detected"
    description: "P99 latency is {{ $value }}s for the last 5 minutes."
    action: "Check database connections and cache hit rate"
```

#### Alert 6: Memory Usage High
```yaml
- alert: HighMemoryUsage
  expr: |
    process_resident_memory_bytes{job=~".*"}
    / 1024 / 1024 / 1024 > 1
  for: 10m
  labels:
    severity: warning
    service: "{{ $labels.job }}"
  annotations:
    summary: "High memory usage in {{ $labels.job }}"
    description: "Memory usage is {{ $value }}GB."
    action: "Check for memory leaks"
```

#### Alert 7: Circuit Breaker Triggered
```yaml
- alert: CircuitBreakerOpen
  expr: circuit_breaker_active_gauge == 1
  for: 1m
  labels:
    severity: warning
    component: circuit-breaker
  annotations:
    summary: "Circuit breaker {{ $labels.breaker_name }} is open"
    description: "Circuit breaker has been open for 1 minute."
    action: "Check downstream service health"
```

#### Alert 8: Low Win Rate
```yaml
- alert: LowWinRate
  expr: win_rate < 40
  for: 1h
  labels:
    severity: warning
    component: trading-strategy
  annotations:
    summary: "Win rate below threshold"
    description: "Current win rate is {{ $value }}%."
    action: "Review trading strategy parameters"
```

#### Alert 9: Bybit Rate Limit Hit
```yaml
- alert: BybitRateLimitHit
  expr: |
    rate(http_requests_total{
      job="bybit-connector",
      status_code="429"
    }[5m]) > 0
  for: 1m
  labels:
    severity: warning
    component: bybit-connector
  annotations:
    summary: "Bybit API rate limit exceeded"
    description: "Rate limit errors detected: {{ $value }} per second."
    action: "Reduce API call frequency or implement request queuing"
```

### Implementing Alerts

**Step 1: Create alert rules file**

Create `/mnt/d/Bimo_max/crypto-trading-bot/infrastructure/monitoring/rules/trading_alerts.yml`:

```yaml
groups:
  - name: trading_engine_alerts
    interval: 30s
    rules:
      # Add alert rules from above
      - alert: TradingEngineDown
        expr: up{job="trading-engine"} == 0
        for: 30s
        labels:
          severity: critical
        annotations:
          summary: "Trading Engine is down"

      # Add more rules...
```

**Step 2: Configure AlertManager**

Edit `/mnt/d/Bimo_max/crypto-trading-bot/infrastructure/monitoring/alertmanager/alertmanager.yml`:

```yaml
route:
  receiver: 'slack-notifications'
  group_by: ['alertname', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h

  routes:
    - match:
        severity: critical
      receiver: 'pagerduty-critical'

    - match:
        component: trading-engine
      receiver: 'telegram-trading'

receivers:
  - name: 'slack-notifications'
    slack_configs:
      - api_url: 'YOUR_SLACK_WEBHOOK_URL'
        channel: '#crypto-bot-alerts'
        title: '{{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'

  - name: 'telegram-trading'
    webhook_configs:
      - url: 'YOUR_TELEGRAM_BOT_WEBHOOK'

  - name: 'pagerduty-critical'
    pagerduty_configs:
      - service_key: 'YOUR_PAGERDUTY_KEY'
```

**Step 3: Reload Prometheus configuration**

```bash
# Reload Prometheus to pick up new alert rules
curl -X POST http://localhost:9090/-/reload

# Or restart Prometheus container
docker restart crypto-bot-prometheus
```

---

## Troubleshooting

### Issue 1: Metrics Endpoint Returning 404

**Symptoms:**
- Prometheus shows service as "down" with "404 Not Found" error
- Services: api-gateway, portfolio-manager, technical-analysis, trading-engine, ml-prediction, sentiment-analysis, risk-metrics

**Diagnosis:**
```bash
# Check if service is running
docker ps | grep crypto-bot-trading

# Try to access metrics endpoint directly
curl http://localhost:8005/metrics

# Check service logs
docker logs crypto-bot-trading | grep -i metrics
```

**Solutions:**

1. **Add metrics endpoint to service:**

Edit service `main.py` to add metrics endpoint:

```python
from prometheus_client import make_asgi_app

# Mount metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
```

2. **Restart the service:**

```bash
docker restart crypto-bot-[service-name]
```

3. **Verify metrics are exposed:**

```bash
curl http://localhost:8005/metrics | grep -E "(http_requests|trading_signals)"
```

---

### Issue 2: Grafana Shows "No Data"

**Symptoms:**
- Dashboard panels show "No data"
- Queries return empty results

**Diagnosis:**
```bash
# Check Prometheus datasource connectivity
curl http://localhost:3001/api/datasources

# Check if metrics are being collected
curl http://localhost:9090/api/v1/query?query=up
```

**Solutions:**

1. **Verify Prometheus is scraping:**
```bash
# Check targets status
curl http://localhost:9090/api/v1/targets | python3 -m json.tool | grep health
```

2. **Check time range in Grafana:**
- Ensure dashboard time range includes periods with data
- Try "Last 1 hour" instead of "Last 15 minutes"

3. **Verify metric names:**
```bash
# List all available metrics
curl -s http://localhost:9090/api/v1/label/__name__/values | python3 -m json.tool
```

---

### Issue 3: High Prometheus Memory Usage

**Symptoms:**
- Prometheus container using excessive memory
- Slow query performance

**Solutions:**

1. **Adjust retention period:**

Edit `docker-compose.monitoring.yml`:

```yaml
services:
  prometheus:
    command:
      - '--storage.tsdb.retention.time=7d'  # Reduce from 15d to 7d
```

2. **Reduce scrape frequency for less critical services:**

Edit `infrastructure/monitoring/prometheus.yml`:

```yaml
- job_name: 'sentiment-analysis-service'
  scrape_interval: 60s  # Increase from 30s to 60s
```

3. **Restart Prometheus:**
```bash
docker restart crypto-bot-prometheus
```

---

### Issue 4: Alerts Not Firing

**Symptoms:**
- Expected alerts are not triggering
- No notifications received

**Diagnosis:**
```bash
# Check alert rules status
curl http://localhost:9090/api/v1/rules | python3 -m json.tool

# Check active alerts
curl http://localhost:9090/api/v1/alerts | python3 -m json.tool
```

**Solutions:**

1. **Verify alert rule syntax:**
```bash
# Use promtool to validate rules
docker exec crypto-bot-prometheus promtool check rules /etc/prometheus/rules/*.yml
```

2. **Check AlertManager is running:**
```bash
docker ps | grep alertmanager
```

3. **Test alert manually:**
```bash
# Send test alert to AlertManager
curl -X POST http://localhost:9093/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '[{
    "labels": {"alertname": "TestAlert", "severity": "warning"},
    "annotations": {"summary": "Test alert"}
  }]'
```

---

## Best Practices

### 1. Dashboard Organization

- **Create role-specific dashboards:**
  - Operators: System health, errors, latency
  - Traders: P&L, positions, trade history
  - Developers: API performance, error rates, logs

- **Use dashboard folders:**
  - "Production Monitoring"
  - "Trading Performance"
  - "System Health"
  - "Development"

### 2. Alert Configuration

- **Set appropriate thresholds:**
  - Critical: Requires immediate action (service down, data loss)
  - Warning: Requires investigation (high latency, low win rate)
  - Info: For awareness (deployment completed)

- **Avoid alert fatigue:**
  - Use `for` clause to avoid flapping alerts
  - Group related alerts
  - Set reasonable repeat intervals

### 3. Metric Naming Conventions

- **Follow Prometheus conventions:**
  - Counters: `_total` suffix (e.g., `trades_executed_total`)
  - Gauges: No suffix (e.g., `active_positions`)
  - Histograms: `_seconds`, `_bytes` suffixes

- **Use consistent labels:**
  - `symbol`: Trading pair (BTCUSDT)
  - `strategy`: Trading strategy name
  - `status`: Operation status (success, error)

### 4. Query Performance

- **Use recording rules for expensive queries:**

Create recording rules in `prometheus.yml`:

```yaml
groups:
  - name: trading_recording_rules
    interval: 30s
    rules:
      - record: job:http_request_rate:5m
        expr: sum by (job) (rate(http_requests_total[5m]))

      - record: job:error_rate:5m
        expr: |
          sum by (job) (rate(http_requests_total{status_code=~"5.."}[5m]))
          /
          sum by (job) (rate(http_requests_total[5m]))
```

- **Limit cardinality:**
  - Avoid high-cardinality labels (user IDs, request IDs)
  - Use aggregation to reduce series count

### 5. Data Retention

- **Balance retention vs storage:**
  - Production: 15-30 days in Prometheus
  - Long-term: Export to remote storage (Thanos, Cortex)
  - Aggregated data: Keep longer (recording rules)

### 6. Regular Maintenance

- **Weekly tasks:**
  - Review dashboard usage (remove unused dashboards)
  - Check for stale alerts
  - Update alert thresholds based on observed behavior

- **Monthly tasks:**
  - Review metric cardinality
  - Archive old dashboards
  - Update documentation

---

## Next Steps

### Immediate Actions Required

1. **Fix Metrics Endpoints (Priority 1)**
   - Add `/metrics` endpoint to services returning 404
   - Services affected:
     - api-gateway (port 8000)
     - portfolio-manager (port 8003)
     - technical-analysis (port 8004)
     - trading-engine (port 8005) - partially working
     - ml-prediction (port 8007)
     - sentiment-analysis (port 8008)
     - risk-metrics (port 8009)

2. **Configure AlertManager**
   - Set up Slack/Telegram notification channels
   - Configure alert routing rules
   - Test alert delivery

3. **Create Custom Dashboards**
   - System Health Overview
   - Trading Performance
   - API Performance
   - ML Model Performance
   - Market Data Quality

4. **Set Up Backup and Export**
   - Export Grafana dashboards regularly
   - Configure remote storage for long-term metrics
   - Set up automated dashboard backups

### Future Enhancements

1. **Advanced Monitoring**
   - Distributed tracing (Jaeger)
   - Log aggregation (Loki)
   - APM integration (Datadog, New Relic)

2. **SLO/SLA Monitoring**
   - Define Service Level Indicators (SLIs)
   - Set Service Level Objectives (SLOs)
   - Track error budgets

3. **Capacity Planning**
   - Forecast resource requirements
   - Set up auto-scaling based on metrics
   - Cost optimization dashboards

---

## Resources

### Documentation
- [Prometheus Query Language (PromQL)](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Grafana Dashboards](https://grafana.com/docs/grafana/latest/dashboards/)
- [AlertManager Configuration](https://prometheus.io/docs/alerting/latest/configuration/)

### Existing Project Documentation
- [Monitoring Infrastructure README](/mnt/d/Bimo_max/crypto-trading-bot/infrastructure/monitoring/README.md)
- [Prometheus Setup Guide](/mnt/d/Bimo_max/crypto-trading-bot/infrastructure/monitoring/PROMETHEUS_INSTRUMENTATION_GUIDE.md)
- [Operations Runbook](/mnt/d/Bimo_max/crypto-trading-bot/docs/operations/RUNBOOK.md)

### Quick Commands Reference

```bash
# Check service health
docker ps | grep crypto-bot

# View Prometheus targets
curl http://localhost:9090/api/v1/targets | python3 -m json.tool

# Check specific service metrics
curl http://localhost:8002/metrics | head -50

# Restart monitoring stack
docker-compose -f docker-compose.monitoring.yml restart

# View Grafana logs
docker logs crypto-bot-grafana

# Reload Prometheus configuration
curl -X POST http://localhost:9090/-/reload
```

---

**Document Status:** ✅ Complete
**Last Reviewed:** 2025-11-21
**Maintained By:** DevOps Team
**Contact:** For issues or updates, refer to the project's issue tracker
