# Monitoring Infrastructure
**Complete Observability Stack for Crypto Trading Bot**

## Overview

This monitoring stack provides comprehensive observability for the crypto trading bot microservices including metrics collection, log aggregation, alerting, and visualization.

### Components

| Component | Purpose | Port | URL |
|-----------|---------|------|-----|
| **Prometheus** | Metrics collection and storage | 9090 | http://localhost:9090 |
| **Grafana** | Visualization and dashboards | 3000 | http://localhost:3000 |
| **AlertManager** | Alert routing and management | 9093 | http://localhost:9093 |
| **Loki** | Log aggregation | 3100 | http://localhost:3100 |
| **Promtail** | Log shipping agent | 9080 | - |
| **Node Exporter** | System metrics | 9100 | - |
| **cAdvisor** | Container metrics | 8080 | http://localhost:8080 |
| **Redis Exporter** | Redis metrics | 9121 | - |
| **Postgres Exporter** | Database metrics | 9187 | - |

---

## Quick Start

### Prerequisites

```bash
# Ensure Docker and Docker Compose are installed
docker --version
docker-compose --version

# Ensure the crypto-bot-network exists
docker network create crypto-bot-network 2>/dev/null || true
```

### Start Monitoring Stack

```bash
# From project root
cd infrastructure/monitoring

# Start all monitoring services
docker-compose -f docker-compose.monitoring.yml up -d

# Verify all services are running
docker-compose -f docker-compose.monitoring.yml ps

# Check logs
docker-compose -f docker-compose.monitoring.yml logs -f
```

### Access Dashboards

1. **Grafana Dashboard**
   ```
   URL: http://localhost:3000
   Username: admin
   Password: admin (change on first login)
   ```

2. **Prometheus**
   ```
   URL: http://localhost:9090
   Query interface for raw metrics
   ```

3. **AlertManager**
   ```
   URL: http://localhost:9093
   View and manage active alerts
   ```

---

## Configuration

### Prometheus

**File:** `prometheus/prometheus.yml`

Scrapes metrics from all microservices every 15 seconds:
- API Gateway (port 8000)
- Trading Engine (port 8001)
- Market Data Service (port 8002)
- Technical Analysis (port 8003)
- Portfolio Manager (port 8004)
- Bybit Connector (port 8005)
- Risk Metrics Service (port 8006)
- System metrics (Node Exporter, cAdvisor)
- Database metrics (Postgres, Redis)

**Alert Rules:** `prometheus/alerts.yml`

Defines when to trigger alerts:
- Service health (service down, high error rate)
- Trading engine (stopped, high latency, daily loss)
- Database (down, high connections, slow queries)
- System resources (CPU, memory, disk)

### Grafana

**Datasources:** Auto-provisioned via `grafana/provisioning/datasources/`
- Prometheus (metrics)
- Loki (logs)
- AlertManager (alerts)

**Dashboards:** Auto-loaded from `grafana/dashboards/`
1. **System Overview** - Overall system health and performance
2. **Trading Performance** - Trading metrics, P&L, positions
3. **Database Performance** - Database and Redis metrics

### AlertManager

**File:** `alertmanager/alertmanager.yml`

Routes alerts to different channels:
- **Critical alerts** → PagerDuty + Slack
- **Trading alerts** → Telegram
- **Database alerts** → Slack #database
- **Warning alerts** → Slack #warnings

### Loki & Promtail

**Loki Config:** `loki/loki-config.yml`
- Log storage and retention (30 days)
- Query optimization
- Compression settings

**Promtail Config:** `promtail/promtail-config.yml`
- Collects logs from all services
- Parses JSON structured logs
- Extracts labels for filtering

---

## Environment Variables

Create `.env` file in `infrastructure/monitoring/`:

```bash
# Grafana
GRAFANA_USER=admin
GRAFANA_PASSWORD=your-secure-password

# Database credentials
DB_USER=cryptobot
DB_PASSWORD=your-db-password
DB_NAME=cryptobot

# Redis
REDIS_PASSWORD=your-redis-password

# Alerting
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
SLACK_WEBHOOK_URL_CRITICAL=https://hooks.slack.com/services/YOUR/CRITICAL/URL
SLACK_WEBHOOK_URL_DATABASE=https://hooks.slack.com/services/YOUR/DATABASE/URL
PAGERDUTY_SERVICE_KEY=your-pagerduty-key
ALERT_EMAIL=alerts@example.com
SMTP_USERNAME=smtp-user
SMTP_PASSWORD=smtp-password
WEBHOOK_TOKEN=your-webhook-token
```

---

## Key Metrics

### Trading Engine Metrics

```promql
# Total trades executed
trades_executed_total

# Trade execution latency (P99)
histogram_quantile(0.99, rate(trade_execution_duration_seconds_bucket[5m]))

# Active positions
active_positions_gauge

# Portfolio value
portfolio_value_gauge

# Daily P&L
portfolio_daily_pnl_usd
portfolio_daily_pnl_percentage
```

### API Gateway Metrics

```promql
# Request rate
rate(http_requests_total[5m])

# Request latency (P99)
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))

# Error rate
rate(http_requests_total{status_code=~"5.."}[5m])

# Cache hit rate
cache_hits_total / (cache_hits_total + cache_misses_total)
```

### Database Metrics

```promql
# Active connections
pg_stat_database_numbackends

# Cache hit ratio
pg_stat_database_blks_hit / (pg_stat_database_blks_hit + pg_stat_database_blks_read)

# Query performance
rate(pg_stat_statements_mean_exec_time[5m])

# Replication lag
pg_replication_lag_seconds
```

### System Metrics

```promql
# CPU usage
100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# Memory usage
(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100

# Disk space
(node_filesystem_avail_bytes / node_filesystem_size_bytes) * 100
```

---

## Alerting

### Critical Alerts (Immediate Action Required)

1. **TradingEngineStopped**
   - Condition: Trading engine down for 30s
   - Action: Check service logs, restart if needed

2. **DailyLossExceeded**
   - Condition: Daily loss > 5%
   - Action: Review trades, consider emergency stop

3. **DatabaseDown**
   - Condition: Database unreachable for 1 minute
   - Action: Check database health, restore if needed

### Warning Alerts (Investigation Required)

1. **HighAPILatency**
   - Condition: P99 latency > 1 second for 5 minutes
   - Action: Check database connections, cache hit rate

2. **HighDatabaseConnections**
   - Condition: Connections > 180 for 5 minutes
   - Action: Check for connection leaks, increase pool size

3. **SlowQueries**
   - Condition: Average query time > 1 second
   - Action: Review slow query log, optimize indexes

### Alert Management

```bash
# View active alerts
curl http://localhost:9093/api/v1/alerts

# Silence an alert for 2 hours
curl -X POST http://localhost:9093/api/v1/silences \
  -H "Content-Type: application/json" \
  -d '{
    "matchers": [{"name": "alertname", "value": "HighLatency"}],
    "startsAt": "2025-01-01T00:00:00Z",
    "endsAt": "2025-01-01T02:00:00Z",
    "createdBy": "admin",
    "comment": "Maintenance window"
  }'
```

---

## Log Querying

### Loki Query Examples

```logql
# All logs from trading engine
{job="trading-engine"}

# Errors across all services
{level="error"}

# Logs for specific request ID
{request_id="abc-123"}

# Trading actions
{job="trading-engine", action=~"BUY|SELL"}

# Slow requests (>1s)
{job="api-gateway"} | json | duration_ms > 1000
```

### Grafana Explore

1. Go to Grafana → Explore
2. Select "Loki" datasource
3. Enter LogQL query
4. View logs with filtering and highlighting

---

## Maintenance

### Daily Tasks

```bash
# Check service health
docker-compose -f docker-compose.monitoring.yml ps

# View recent alerts
curl -s http://localhost:9093/api/v1/alerts | jq '.data[] | select(.state=="firing")'

# Check Prometheus targets
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.health!="up")'
```

### Weekly Tasks

```bash
# Cleanup old data (handled automatically by retention policies)

# Review dashboard usage
# Grafana → Server Admin → Stats

# Update alert rules if needed
vim prometheus/alerts.yml
docker-compose -f docker-compose.monitoring.yml restart prometheus
```

### Backup

```bash
# Backup Grafana dashboards
docker exec crypto-bot-grafana grafana-cli admin export-dashboard > grafana-backup.json

# Backup Prometheus data
docker run --rm -v prometheus-data:/data -v $(pwd):/backup \
  alpine tar czf /backup/prometheus-backup.tar.gz /data

# Backup AlertManager data
docker run --rm -v alertmanager-data:/data -v $(pwd):/backup \
  alpine tar czf /backup/alertmanager-backup.tar.gz /data
```

---

## Troubleshooting

### Prometheus Not Scraping Metrics

```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq

# Check if service exposes /metrics endpoint
curl http://localhost:8000/metrics

# Verify network connectivity
docker exec crypto-bot-prometheus wget -O- http://api-gateway:8000/metrics
```

### Grafana Dashboards Not Loading

```bash
# Check datasource connectivity
docker exec crypto-bot-grafana grafana-cli admin reset-admin-password newpassword

# Verify Prometheus datasource
curl http://localhost:3000/api/datasources

# Check dashboard provisioning
docker exec crypto-bot-grafana ls -la /var/lib/grafana/dashboards/
```

### Alerts Not Firing

```bash
# Check AlertManager configuration
docker exec crypto-bot-alertmanager amtool check-config /etc/alertmanager/alertmanager.yml

# Test alert routing
curl -X POST http://localhost:9093/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '[{"labels":{"alertname":"TestAlert","severity":"warning"}}]'

# Check Prometheus alert rules
curl http://localhost:9090/api/v1/rules | jq
```

### Loki Not Receiving Logs

```bash
# Check Promtail status
docker logs crypto-bot-promtail

# Verify log files exist
docker exec crypto-bot-promtail ls -la /services/*/logs/

# Test Loki query
curl -G 'http://localhost:3100/loki/api/v1/query' --data-urlencode 'query={job="trading-engine"}'
```

---

## Performance Optimization

### Prometheus

- Adjust scrape interval in `prometheus.yml`
- Configure retention period: `--storage.tsdb.retention.time=30d`
- Enable remote write for long-term storage

### Grafana

- Enable caching
- Optimize dashboard queries (use recording rules)
- Limit dashboard refresh rate

### Loki

- Adjust retention period in `loki-config.yml`
- Configure compression
- Use appropriate index period

---

## Security Considerations

1. **Change default passwords**
   ```bash
   # Grafana admin password
   docker exec crypto-bot-grafana grafana-cli admin reset-admin-password NewSecurePassword123
   ```

2. **Enable HTTPS**
   - Configure reverse proxy (nginx/Traefik)
   - Use Let's Encrypt certificates

3. **Restrict network access**
   ```yaml
   # In docker-compose.monitoring.yml
   ports:
     - "127.0.0.1:3000:3000"  # Only localhost can access
   ```

4. **Enable authentication**
   - Grafana: Built-in auth or LDAP/OAuth
   - Prometheus: Use reverse proxy with auth
   - AlertManager: Basic auth or OAuth2 proxy

---

## Integration with Services

Each microservice automatically exports metrics via the `/metrics` endpoint thanks to the integrated structured logging and metrics utilities.

**Example service integration:**

```python
from utils.structured_logging import setup_logging
from prometheus_client import Counter, Histogram

# Metrics are automatically created and exposed
trades_counter = Counter('trades_executed_total', 'Total trades executed')
trade_latency = Histogram('trade_execution_duration_seconds', 'Trade execution time')

# Metrics endpoint is automatically added to FastAPI
app.add_middleware(PrometheusMiddleware)
app.add_route("/metrics", metrics)
```

---

## Next Steps

1. **Configure alert channels** (Slack, PagerDuty, Telegram)
2. **Customize dashboards** for your specific needs
3. **Set up recording rules** for frequently used queries
4. **Enable remote storage** for long-term metrics retention
5. **Add custom alerts** based on business metrics

---

## Resources

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Loki Documentation](https://grafana.com/docs/loki/)
- [AlertManager Documentation](https://prometheus.io/docs/alerting/latest/alertmanager/)

---

**Status:** ✅ Production Ready
**Last Updated:** 2025-11-16
**Maintained By:** DevOps Team
