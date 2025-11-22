# Crypto Trading Bot - Phase 3 Monitoring Setup Guide

Complete guide to setting up Prometheus and Grafana monitoring for Phase 3 AI services (ML Prediction, Sentiment Analysis, and Risk Metrics).

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Architecture](#architecture)
4. [Installation](#installation)
5. [Configuration](#configuration)
6. [Dashboard Access](#dashboard-access)
7. [Key Metrics](#key-metrics)
8. [Alerts](#alerts)
9. [Troubleshooting](#troubleshooting)
10. [Advanced Configuration](#advanced-configuration)

---

## Overview

This monitoring stack provides:

- **Prometheus**: Metrics collection and storage from all Phase 3 services
- **Grafana**: Rich visualization dashboards with 18+ panels
- **Alert Rules**: Automated alerts for critical conditions
- **Service Health**: Real-time health checks and status monitoring
- **Performance Tracking**: Latency, throughput, and error rates

### What Gets Monitored

#### ML Prediction Service (Port 8007)
- Prediction accuracy and confidence scores
- Model inference time (p50, p95, p99)
- Cache hit/miss rates
- Prediction correctness over time
- Error rates and types

#### Sentiment Analysis Service (Port 8008)
- Current sentiment scores by symbol
- News fetch success rates
- API call latency to external services
- Articles processed per minute
- Sentiment distribution (bearish/neutral/bullish)

#### Risk Metrics Service (Port 8009)
- Portfolio risk percentage
- Drawdown metrics (current and max)
- Value at Risk (VaR) at 95% and 99%
- Sharpe and Sortino ratios
- Position sizes and win rates

---

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- All Phase 3 services running
- Ports 3001 (Grafana) and 9090 (Prometheus) available

### Start Monitoring Stack

```bash
# Navigate to project root
cd /mnt/d/Bimo_max/crypto-trading-bot

# Start all services including monitoring
docker-compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d

# Check if monitoring services are running
docker ps | grep -E "prometheus|grafana"

# View logs
docker logs crypto-bot-prometheus
docker logs crypto-bot-grafana
```

### Access Dashboards

1. **Grafana Dashboard**: http://localhost:3001
   - Username: `admin`
   - Password: `crypto-bot-admin` (CHANGE IN PRODUCTION!)

2. **Prometheus UI**: http://localhost:9090
   - No authentication required (configure for production)

3. **Phase 3 Dashboard**:
   - Navigate to Dashboards → Crypto Trading Bot → Phase 3 AI Services

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Monitoring Stack                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐         ┌──────────────┐                │
│  │   Grafana    │────────▶│  Prometheus  │                │
│  │  (Port 3001) │  Query  │  (Port 9090) │                │
│  └──────────────┘         └───────┬──────┘                │
│         │                          │                        │
│         │                          │ Scrape Metrics        │
│         │                          │ Every 15s             │
│         ▼                          ▼                        │
│  ┌──────────────────────────────────────────────────────┐  │
│  │            Phase 3 Services                          │  │
│  │                                                      │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────┐  │  │
│  │  │ ML Prediction│  │  Sentiment   │  │   Risk   │  │  │
│  │  │   :8007      │  │  Analysis    │  │ Metrics  │  │  │
│  │  │              │  │   :8008      │  │  :8009   │  │  │
│  │  │ /metrics     │  │ /metrics     │  │ /metrics │  │  │
│  │  └──────────────┘  └──────────────┘  └──────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Services** expose metrics at `/metrics` endpoint
2. **Prometheus** scrapes metrics every 15-30 seconds
3. **Prometheus** stores time-series data (15-day retention)
4. **Grafana** queries Prometheus for visualization
5. **Alert Rules** evaluate conditions and trigger alerts

---

## Installation

### Step 1: Add Prometheus Client to Services

Add to each service's `requirements.txt`:

```bash
# For ML Prediction Service
cd services/ml-prediction-service
echo -e "\n# Monitoring\nprometheus-client==0.19.0\nprometheus-fastapi-instrumentator==6.1.0" >> requirements.txt

# For Sentiment Analysis Service
cd ../sentiment-analysis-service
echo -e "\n# Monitoring\nprometheus-client==0.19.0\nprometheus-fastapi-instrumentator==6.1.0" >> requirements.txt

# For Risk Metrics Service
cd ../risk-metrics-service
echo -e "\n# Monitoring\nprometheus-client==0.19.0\nprometheus-fastapi-instrumentator==6.1.0" >> requirements.txt
```

### Step 2: Instrument Services

See [PROMETHEUS_INSTRUMENTATION_GUIDE.md](./PROMETHEUS_INSTRUMENTATION_GUIDE.md) for detailed implementation.

Quick example for any FastAPI service:

```python
# app/main.py
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title="Service Name")

# Enable Prometheus metrics
Instrumentator().instrument(app).expose(app)
```

### Step 3: Deploy Monitoring Stack

```bash
# Start monitoring services
docker-compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d prometheus grafana

# Wait for services to be healthy
docker-compose ps

# Verify Prometheus is scraping targets
curl http://localhost:9090/api/v1/targets
```

---

## Configuration

### Prometheus Configuration

Location: `/mnt/d/Bimo_max/crypto-trading-bot/infrastructure/monitoring/prometheus.yml`

Key settings:
- **Scrape interval**: 15 seconds (adjustable per service)
- **Data retention**: 15 days
- **Evaluation interval**: 15 seconds for alert rules

To reload configuration without restart:

```bash
# Send reload signal
curl -X POST http://localhost:9090/-/reload

# Or restart service
docker-compose restart prometheus
```

### Grafana Configuration

Location: `/mnt/d/Bimo_max/crypto-trading-bot/infrastructure/monitoring/grafana-provisioning/`

- **Datasources**: Auto-configured Prometheus
- **Dashboards**: Auto-imported Phase 3 dashboard
- **Admin Password**: `crypto-bot-admin` (CHANGE IN PRODUCTION!)

To change admin password:

```bash
# Method 1: Environment variable in docker-compose.monitoring.yml
GF_SECURITY_ADMIN_PASSWORD=your-new-password

# Method 2: Grafana CLI
docker exec -it crypto-bot-grafana grafana-cli admin reset-admin-password <new-password>
```

### Alert Rules

Location: `/mnt/d/Bimo_max/crypto-trading-bot/infrastructure/monitoring/rules/phase3-alerts.yml`

Configured alerts include:
- Low ML prediction accuracy (<70%)
- High inference latency (>500ms)
- High portfolio risk (>5%)
- Service downtime (>1 minute)
- High error rates (>0.1 errors/sec)

---

## Dashboard Access

### Grafana Dashboard

1. Open browser: http://localhost:3001
2. Login with credentials:
   - Username: `admin`
   - Password: `crypto-bot-admin`
3. Navigate to: Dashboards → Crypto Trading Bot → Phase 3 AI Services

### Dashboard Panels

The Phase 3 dashboard includes 18 panels organized in 6 rows:

#### Row 1: Service Overview
- Request rates for all Phase 3 services
- Service latency (p95) gauges

#### Row 2: ML Prediction Quality
- Prediction accuracy trends
- Model inference performance
- Cache hit rate gauge

#### Row 3: Sentiment Analysis
- Current market sentiment gauge
- News fetch success rate
- API latency gauge
- Sentiment score trends

#### Row 4: News Processing
- News articles processed per minute
- News processing rate trends

#### Row 5: Risk Metrics
- Portfolio risk percentage
- Value at Risk (VaR) trends
- Sharpe ratio gauge
- Sortino ratio gauge
- Average position size
- Win rate percentage

#### Row 6: System Health
- Error rates for all services
- CPU and memory usage

### Prometheus UI

1. Open browser: http://localhost:9090
2. Use PromQL queries to explore metrics:

```promql
# Example queries

# ML prediction rate
rate(ml_prediction_requests_total[5m])

# Current sentiment score
avg(sentiment_score)

# Portfolio risk
portfolio_risk_percentage

# Service uptime
up{job=~"ml-prediction-service|sentiment-analysis-service|risk-metrics-service"}
```

---

## Key Metrics

### ML Prediction Service

| Metric | Type | Description | Alert Threshold |
|--------|------|-------------|----------------|
| `ml_prediction_accuracy` | Gauge | Prediction accuracy (0-1) | <0.70 |
| `ml_model_inference_seconds` | Histogram | Model inference time | p95 >0.5s |
| `ml_cache_hits_total` | Counter | Cache hits | Hit rate <70% |
| `ml_prediction_errors_total` | Counter | Total errors | >0.1/sec |

### Sentiment Analysis Service

| Metric | Type | Description | Alert Threshold |
|--------|------|-------------|----------------|
| `sentiment_score` | Gauge | Current sentiment (-1 to 1) | <-0.7 or >0.7 |
| `sentiment_news_fetch_success_total` | Counter | Successful news fetches | Success rate <90% |
| `sentiment_api_latency_seconds` | Histogram | External API latency | p95 >1.0s |
| `sentiment_analysis_errors_total` | Counter | Total errors | >0.1/sec |

### Risk Metrics Service

| Metric | Type | Description | Alert Threshold |
|--------|------|-------------|----------------|
| `portfolio_risk_percentage` | Gauge | Portfolio risk % | >5% |
| `portfolio_drawdown_percentage` | Gauge | Current drawdown % | >10% |
| `sharpe_ratio` | Gauge | Risk-adjusted returns | <1.0 |
| `value_at_risk_95` | Gauge | VaR at 95% confidence | N/A |
| `winning_trades_total` | Counter | Winning trades count | Win rate <50% |

---

## Alerts

### Viewing Active Alerts

**In Prometheus:**
1. Go to http://localhost:9090/alerts
2. View all configured alert rules and their status

**In Grafana:**
1. Navigate to Alerting → Alert Rules
2. View active alerts and their history

### Alert States

- **Inactive**: Condition not met
- **Pending**: Condition met, waiting for duration
- **Firing**: Alert is active and triggering

### Critical Alerts

| Alert | Condition | Duration | Action |
|-------|-----------|----------|--------|
| MLPredictionServiceDown | Service unreachable | 1 minute | Check service logs |
| HighPortfolioRisk | Risk >5% | 5 minutes | Review open positions |
| LowMLPredictionAccuracy | Accuracy <70% | 5 minutes | Retrain model |
| HighMLInferenceLatency | p95 >500ms | 5 minutes | Optimize model |

### Testing Alerts

```bash
# Manually trigger an alert by stopping a service
docker stop crypto-bot-ml-prediction

# Wait 1-2 minutes and check Prometheus alerts
curl http://localhost:9090/api/v1/alerts | jq

# Restart service
docker start crypto-bot-ml-prediction
```

---

## Troubleshooting

### Prometheus Not Scraping Services

**Symptom**: No data in Grafana, targets show as "DOWN" in Prometheus

**Solutions**:

1. Check if services are running:
   ```bash
   docker ps | grep -E "ml-prediction|sentiment|risk-metrics"
   ```

2. Verify services expose /metrics endpoint:
   ```bash
   curl http://localhost:8007/metrics
   curl http://localhost:8008/metrics
   curl http://localhost:8009/metrics
   ```

3. Check Prometheus targets:
   ```bash
   curl http://localhost:9090/api/v1/targets | jq
   ```

4. Check Prometheus logs:
   ```bash
   docker logs crypto-bot-prometheus
   ```

### Grafana Shows "No Data"

**Symptom**: Dashboard panels show "No Data" or "N/A"

**Solutions**:

1. Verify Prometheus datasource is configured:
   - Go to Configuration → Data Sources
   - Ensure Prometheus is set as default
   - Test connection

2. Check if metrics exist in Prometheus:
   - Go to http://localhost:9090
   - Run query: `up{job="ml-prediction-service"}`
   - Should return 1 if service is up

3. Verify metric names match dashboard queries:
   - Edit panel → View query
   - Test query in Prometheus UI

4. Check time range:
   - Ensure time range includes periods when services were running
   - Try "Last 6 hours" or "Last 24 hours"

### High Memory Usage

**Symptom**: Prometheus or Grafana consuming too much memory

**Solutions**:

1. Reduce Prometheus retention:
   ```yaml
   # In docker-compose.monitoring.yml
   command:
     - '--storage.tsdb.retention.time=7d'  # Reduce from 15d to 7d
   ```

2. Reduce scrape frequency:
   ```yaml
   # In prometheus.yml
   global:
     scrape_interval: 30s  # Increase from 15s to 30s
   ```

3. Reduce metric cardinality:
   - Avoid high-cardinality labels (user IDs, timestamps)
   - Limit number of unique label combinations

### Metrics Not Updating

**Symptom**: Metrics stuck at old values

**Solutions**:

1. Check service is recording metrics:
   ```bash
   # Look for metrics code in service
   grep -r "prometheus" services/ml-prediction-service/app/
   ```

2. Verify metrics are being incremented:
   ```bash
   # Watch metrics endpoint for changes
   watch -n 1 "curl -s http://localhost:8007/metrics | grep ml_prediction"
   ```

3. Check for exceptions in service logs:
   ```bash
   docker logs crypto-bot-ml-prediction | grep -i error
   ```

---

## Advanced Configuration

### Adding Custom Metrics

See [PROMETHEUS_INSTRUMENTATION_GUIDE.md](./PROMETHEUS_INSTRUMENTATION_GUIDE.md) for detailed instructions.

### Creating Custom Dashboards

1. In Grafana, click "Create" → "Dashboard"
2. Add panels with PromQL queries
3. Save dashboard
4. Export JSON to `/infrastructure/monitoring/` for version control

### Enabling Alertmanager

Uncomment Alertmanager section in `docker-compose.monitoring.yml` and create config:

```yaml
# infrastructure/monitoring/alertmanager.yml
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'severity']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'default'

receivers:
  - name: 'default'
    slack_configs:
      - api_url: 'YOUR_SLACK_WEBHOOK_URL'
        channel: '#alerts'
```

### Adding System Metrics

Uncomment `node-exporter` and `cadvisor` sections in `docker-compose.monitoring.yml` to monitor:
- Host CPU, memory, disk, network
- Container-level resource usage

### Multi-environment Setup

Create environment-specific configurations:

```bash
# Development
docker-compose -f docker-compose.yml -f docker-compose.monitoring.yml up

# Production
docker-compose -f docker-compose.yml -f docker-compose.monitoring.prod.yml up
```

---

## Security Best Practices

### 1. Change Default Passwords

```bash
# Update in docker-compose.monitoring.yml
GF_SECURITY_ADMIN_PASSWORD: "strong-random-password"
```

### 2. Enable Authentication for Prometheus

Add nginx proxy with basic auth:

```yaml
# Add to docker-compose.monitoring.yml
nginx-prometheus:
  image: nginx:alpine
  volumes:
    - ./nginx-prometheus.conf:/etc/nginx/nginx.conf
    - ./htpasswd:/etc/nginx/.htpasswd
  ports:
    - "9090:80"
```

### 3. Use HTTPS

Configure TLS certificates for Grafana:

```yaml
# In docker-compose.monitoring.yml
environment:
  - GF_SERVER_PROTOCOL=https
  - GF_SERVER_CERT_FILE=/etc/grafana/grafana.crt
  - GF_SERVER_CERT_KEY=/etc/grafana/grafana.key
volumes:
  - ./certs/grafana.crt:/etc/grafana/grafana.crt
  - ./certs/grafana.key:/etc/grafana/grafana.key
```

### 4. Restrict Network Access

Use Docker networks to isolate monitoring:

```yaml
networks:
  monitoring:
    internal: true  # No external access
  crypto-bot-network:
    external: true
```

---

## Backup and Restore

### Backup Prometheus Data

```bash
# Create backup
docker run --rm -v crypto-bot-prometheus-data:/data -v $(pwd):/backup alpine tar czf /backup/prometheus-backup.tar.gz /data

# Restore backup
docker run --rm -v crypto-bot-prometheus-data:/data -v $(pwd):/backup alpine tar xzf /backup/prometheus-backup.tar.gz -C /
```

### Backup Grafana Dashboards

```bash
# Export dashboard via API
curl -H "Authorization: Bearer YOUR_API_KEY" \
  http://localhost:3001/api/dashboards/uid/crypto-bot-phase3 > dashboard-backup.json

# Import dashboard
curl -X POST -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d @dashboard-backup.json \
  http://localhost:3001/api/dashboards/db
```

---

## Performance Tuning

### Optimize Prometheus Storage

```yaml
# In docker-compose.monitoring.yml, add to command:
- '--storage.tsdb.retention.size=10GB'  # Limit storage size
- '--storage.tsdb.min-block-duration=2h'
- '--storage.tsdb.max-block-duration=2h'
```

### Optimize Grafana

```yaml
# In docker-compose.monitoring.yml environment:
- GF_DATABASE_TYPE=postgres  # Use external DB instead of SQLite
- GF_DATABASE_HOST=postgres:5432
- GF_DATABASE_NAME=grafana
```

### Reduce Metric Cardinality

```python
# Bad: High cardinality
request_counter.labels(user_id=user.id).inc()

# Good: Low cardinality
request_counter.labels(user_type=user.type).inc()
```

---

## Monitoring Checklist

Before going to production:

- [ ] Change Grafana admin password
- [ ] Enable Prometheus authentication
- [ ] Configure HTTPS for Grafana
- [ ] Set up Alertmanager with Slack/email
- [ ] Configure alert rules for all critical metrics
- [ ] Set up automated backups
- [ ] Document runbooks for common alerts
- [ ] Test disaster recovery procedures
- [ ] Configure log aggregation (ELK/Loki)
- [ ] Set up metric-based autoscaling
- [ ] Create operational dashboards for on-call
- [ ] Configure retention policies based on storage

---

## Support and Resources

### Documentation
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [PromQL Tutorial](https://prometheus.io/docs/prometheus/latest/querying/basics/)

### Community
- [Prometheus Slack](https://slack.prometheus.io/)
- [Grafana Community Forum](https://community.grafana.com/)

### Project-Specific
- [Phase 3 Implementation Summary](../../PHASE3_COMPLETE.md)
- [Prometheus Instrumentation Guide](./PROMETHEUS_INSTRUMENTATION_GUIDE.md)

---

## Next Steps

1. **Instrument Services**: Add Prometheus client to all Phase 3 services
2. **Create Metrics**: Implement custom business metrics
3. **Set Up Alerts**: Configure Alertmanager for notifications
4. **Optimize Dashboards**: Create role-specific dashboards (dev, ops, business)
5. **Add Tracing**: Integrate Jaeger for distributed tracing
6. **Log Aggregation**: Set up ELK or Loki for centralized logging

---

**Version**: 1.0
**Last Updated**: 2025-11-11
**Maintained by**: DevOps Team
