# Monitoring Quick Reference Card

Quick commands and URLs for daily monitoring operations.

## Quick Access URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana Dashboard | http://localhost:3001 | admin / crypto-bot-admin |
| Prometheus UI | http://localhost:9090 | None |
| ML Prediction Metrics | http://localhost:8007/metrics | None |
| Sentiment Metrics | http://localhost:8008/metrics | None |
| Risk Metrics | http://localhost:8009/metrics | None |

## Quick Start Commands

```bash
# Start monitoring stack
docker-compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d

# Stop monitoring stack
docker-compose -f docker-compose.yml -f docker-compose.monitoring.yml down

# View logs
docker logs crypto-bot-prometheus
docker logs crypto-bot-grafana

# Restart services
docker-compose restart prometheus grafana

# Check service health
docker-compose ps prometheus grafana
```

## Essential PromQL Queries

```promql
# Service uptime
up{job=~"ml-prediction-service|sentiment-analysis-service|risk-metrics-service"}

# Request rate (req/sec)
rate(http_requests_total[5m])

# ML prediction accuracy
avg(ml_prediction_accuracy) * 100

# Current sentiment score
avg(sentiment_score)

# Portfolio risk
portfolio_risk_percentage

# Error rate
rate(service_errors_total[5m])

# Service latency p95
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Memory usage
process_resident_memory_bytes / 1024 / 1024
```

## Common Operations

### Check if Prometheus is Scraping

```bash
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'
```

### Test Metrics Endpoint

```bash
# ML Prediction
curl http://localhost:8007/metrics | grep ml_prediction

# Sentiment Analysis
curl http://localhost:8008/metrics | grep sentiment

# Risk Metrics
curl http://localhost:8009/metrics | grep risk
```

### Reload Prometheus Config

```bash
curl -X POST http://localhost:9090/-/reload
```

### View Active Alerts

```bash
curl http://localhost:9090/api/v1/alerts | jq '.data.alerts[]'
```

## Critical Metrics Thresholds

| Metric | Good | Warning | Critical |
|--------|------|---------|----------|
| ML Accuracy | >80% | 70-80% | <70% |
| Inference Latency | <100ms | 100-500ms | >500ms |
| Cache Hit Rate | >85% | 70-85% | <70% |
| Sentiment API Latency | <500ms | 500-1000ms | >1000ms |
| News Fetch Success | >95% | 90-95% | <90% |
| Portfolio Risk | <3% | 3-5% | >5% |
| Drawdown | <5% | 5-10% | >10% |
| Win Rate | >55% | 50-55% | <50% |

## Troubleshooting Quick Fixes

### Service Down
```bash
docker ps -a | grep crypto-bot
docker restart crypto-bot-ml-prediction
```

### No Data in Grafana
```bash
# Check Prometheus datasource
curl http://prometheus:9090/api/v1/query?query=up

# Reload Grafana
docker restart crypto-bot-grafana
```

### High Memory Usage
```bash
# Check container stats
docker stats crypto-bot-prometheus crypto-bot-grafana

# Restart if needed
docker-compose restart prometheus
```

### Metrics Not Updating
```bash
# Check service logs
docker logs crypto-bot-ml-prediction | tail -50

# Verify metrics are exposed
curl http://localhost:8007/metrics | head -20
```

## Alert Response Guide

| Alert | Immediate Action | Investigation |
|-------|------------------|---------------|
| MLPredictionServiceDown | Check service status, restart if needed | Review logs for errors |
| HighPortfolioRisk | Review open positions, consider reducing exposure | Check risk calculations |
| LowMLPredictionAccuracy | Switch to backup model | Analyze prediction errors, retrain |
| HighMLInferenceLatency | Check system resources | Optimize model, add caching |
| LowNewsFetchSuccessRate | Check API keys and rate limits | Review external API status |

## Useful Docker Commands

```bash
# View all monitoring containers
docker ps | grep -E "prometheus|grafana"

# View container logs
docker logs -f crypto-bot-prometheus
docker logs -f crypto-bot-grafana

# Execute commands in container
docker exec -it crypto-bot-prometheus sh
docker exec -it crypto-bot-grafana sh

# Remove all monitoring data (DESTRUCTIVE!)
docker-compose -f docker-compose.monitoring.yml down -v

# Backup Prometheus data
docker run --rm -v crypto-bot-prometheus-data:/data -v $(pwd):/backup \
  alpine tar czf /backup/prometheus-backup-$(date +%Y%m%d).tar.gz /data
```

## Grafana Navigation

```
Home → Dashboards → Crypto Trading Bot → Phase 3 AI Services

Key Panels:
- Row 1: Service Overview (Request Rates, Latency)
- Row 2: ML Prediction Quality
- Row 3: Sentiment Analysis
- Row 4: News Processing
- Row 5: Risk Metrics
- Row 6: System Health
```

## Prometheus Navigation

```
http://localhost:9090

- Graph: Query and visualize metrics
- Alerts: View active alerts
- Targets: Check scrape target status
- Configuration: View current config
- Status → Runtime & Build Info: Check Prometheus status
```

## Emergency Procedures

### Stop All Trading (Risk Too High)

```bash
# Check current risk
curl http://localhost:8009/api/portfolio/risk | jq

# Stop trading engine
docker stop crypto-bot-trading

# Review positions
curl http://localhost:8003/api/positions | jq
```

### Rollback to Previous Model

```bash
# For ML service
docker exec crypto-bot-ml-prediction \
  cp /app/models/backup/model.h5 /app/models/active/model.h5

docker restart crypto-bot-ml-prediction
```

### Clear Cache (Performance Issues)

```bash
# Redis cache clear (if used)
docker exec crypto-bot-redis redis-cli FLUSHALL

# Restart services
docker-compose restart ml-prediction sentiment-analysis
```

## Maintenance Schedule

| Task | Frequency | Command |
|------|-----------|---------|
| Check dashboards | Daily | Open Grafana, review Phase 3 dashboard |
| Review alerts | Daily | Check Prometheus alerts page |
| Check disk space | Weekly | `df -h` and check Prometheus volume |
| Backup metrics | Weekly | Run backup script |
| Update services | Monthly | `docker-compose pull` and restart |
| Review retention | Monthly | Adjust if storage is an issue |

## Contact Information

| Issue Type | Contact | Method |
|------------|---------|--------|
| Service Down | On-call Engineer | PagerDuty / Phone |
| High Risk Alert | Trading Team Lead | Slack #trading-alerts |
| ML Model Issues | ML Team | Slack #ml-models |
| Infrastructure | DevOps Team | Slack #devops |

---

**Keep this card handy for quick reference during operations!**
