# Phase 7: High Availability & Monitoring Infrastructure - Deployment Guide

**Version:** 2.0
**Date:** 2025-12-11
**Status:** PRODUCTION READY

## Overview

This document provides comprehensive deployment instructions for the Phase 7 High Availability and Monitoring infrastructure for the Crypto Trading Bot.

## Components Created

### 1. Kubernetes Deployment Configuration

**File:** `/infrastructure/kubernetes/trading-engine-deployment.yaml`

Features:
- 3 replicas with rolling update strategy (zero-downtime deployments)
- Init containers for dependency verification
- Comprehensive health probes (liveness, readiness, startup)
- Resource limits and requests
- Horizontal Pod Autoscaler (3-10 replicas)
- Pod Disruption Budget (min 2 available)
- Pod anti-affinity for HA across nodes/zones
- ConfigMap and Secret integration
- Graceful shutdown with preStop hooks
- Prometheus metrics scraping annotations

### 2. Core Application Components

**Location:** `/services/trading-engine/app/core/`

#### Circuit Breaker (`circuit_breaker.py`)
- Prevents cascading failures when external services fail
- Three states: CLOSED, OPEN, HALF_OPEN
- Configurable thresholds and timeouts
- Prometheus metrics integration
- Context manager and decorator support
- Global registry for multiple breakers

```python
# Usage example
from app.core import get_circuit_breaker, circuit_protected

# Context manager
async with get_circuit_breaker("bybit_api"):
    result = await exchange.place_order(order)

# Decorator
@circuit_protected("market_data")
async def fetch_price(symbol: str):
    return await exchange.get_price(symbol)
```

#### Health Checker (`health.py`)
- Comprehensive health check system
- Database, cache, message queue, and API checks
- Kubernetes probe endpoints (/health, /ready)
- Background health monitoring
- System resource metrics (CPU, memory, disk)
- Prometheus metrics for health status

#### Metrics Collector (`metrics.py`)
- Prometheus metrics for all trading operations
- HTTP request middleware
- Trading metrics (orders, trades, signals)
- Risk metrics (exposure, drawdown, losses)
- Performance metrics (win rate, profit factor)
- External API tracking

### 3. Monitoring Infrastructure

**Location:** `/infrastructure/monitoring/`

#### Prometheus Configuration
- **File:** `/prometheus/prometheus-ha.yml` (existing, enhanced)
- Service discovery via Consul
- File-based discovery for Docker Compose
- Comprehensive scrape configurations
- Alert rules integration

#### Alert Rules
- **File:** `/rules/trading-alerts.yml`
- Service health alerts
- Trading operations alerts
- Risk management alerts
- Exchange connectivity alerts
- Database and cache alerts

#### Grafana Dashboards
- **File:** `/grafana/dashboards/trading-overview.json` (NEW)
- System health overview panel
- Trading performance metrics
- Risk metrics gauges
- API latency charts
- Request rate visualization

### 4. Backup and Disaster Recovery

**Location:** `/infrastructure/backup/`

#### Database Backup Script (`backup-database.sh`)
- Full and incremental backup support
- Compression (gzip level 9)
- Encryption (GPG) support
- Remote storage upload (S3 compatible)
- Retention policy management
- Checksum verification
- Slack/Telegram notifications

#### Database Restore Script (`restore-database.sh`)
- Restore from local or remote backups
- Encrypted and compressed file support
- Point-in-time recovery (PITR) support
- Pre-restore verification
- Service coordination (stop/start)

## Deployment Instructions

### Prerequisites

1. Kubernetes cluster (1.25+) or Docker Compose
2. PostgreSQL 15+
3. Redis 7+
4. RabbitMQ 3.12+
5. Prometheus 2.45+
6. Grafana 10+

### Step 1: Deploy Kubernetes Resources

```bash
# Create namespace
kubectl create namespace crypto-bot

# Apply configurations in order
cd /mnt/d/Bimo_max/crypto-trading-bot/infrastructure/kubernetes

# 1. Namespaces
kubectl apply -f namespaces/

# 2. ConfigMaps
kubectl apply -f configmaps/

# 3. Secrets (template - edit with actual values)
kubectl apply -f secrets/

# 4. Storage (PVCs)
kubectl apply -f storage/

# 5. Databases
kubectl apply -f databases/

# 6. Services
kubectl apply -f services/trading-engine-deployment.yaml

# 7. Autoscaling
kubectl apply -f autoscaling/

# 8. Ingress
kubectl apply -f ingress/

# Verify deployment
kubectl get pods -n crypto-bot
kubectl get hpa -n crypto-bot
```

### Step 2: Deploy Monitoring Stack

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot/infrastructure/monitoring

# Start monitoring stack with Docker Compose
docker-compose -f docker-compose.ha.yml up -d

# Verify services
docker-compose -f docker-compose.ha.yml ps

# Import Grafana dashboard
curl -X POST -H "Content-Type: application/json" \
  -d @grafana/dashboards/trading-overview.json \
  http://admin:admin@localhost:3000/api/dashboards/db
```

### Step 3: Configure Backup Schedule

```bash
# Edit crontab
crontab -e

# Add backup schedule
# Full backup daily at 2 AM
0 2 * * * /mnt/d/Bimo_max/crypto-trading-bot/infrastructure/backup/backup-database.sh full >> /var/log/backup.log 2>&1

# Incremental backup every 6 hours
0 */6 * * * /mnt/d/Bimo_max/crypto-trading-bot/infrastructure/backup/backup-database.sh incremental >> /var/log/backup.log 2>&1
```

### Step 4: Verify Health Checks

```bash
# Check health endpoint
curl http://trading-engine-service:8005/health

# Check readiness
curl http://trading-engine-service:8005/ready

# Check metrics
curl http://trading-engine-service:8005/metrics

# Verify in Prometheus
curl http://prometheus:9090/api/v1/targets | jq '.data.activeTargets[] | select(.job=="trading-engine")'
```

## Configuration

### Environment Variables

```bash
# Database
PGHOST=postgres-service
PGPORT=5432
PGUSER=trading_user
PGDATABASE=trading_db

# Redis
REDIS_URL=redis://redis-service:6379/0

# RabbitMQ
RABBITMQ_URL=amqp://rabbitmq-service:5672

# Service URLs
TECHNICAL_ANALYSIS_URL=http://technical-analysis-service:8004
BYBIT_CONNECTOR_URL=http://bybit-connector-service:8001
PORTFOLIO_MANAGER_URL=http://portfolio-manager-service:8003

# Monitoring
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger-collector:4317
```

### Alert Routing

Edit Alertmanager configuration:

```yaml
# /infrastructure/monitoring/alertmanager/alertmanager.yml
global:
  smtp_smarthost: 'smtp.gmail.com:587'
  smtp_from: 'alerts@crypto-bot.com'

route:
  group_by: ['alertname', 'service']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'default'
  routes:
    - match:
        severity: critical
      receiver: 'pagerduty'
    - match:
        severity: warning
      receiver: 'slack'

receivers:
  - name: 'default'
    email_configs:
      - to: 'team@crypto-bot.com'
  - name: 'pagerduty'
    pagerduty_configs:
      - service_key: '<pagerduty-key>'
  - name: 'slack'
    slack_configs:
      - api_url: '<slack-webhook-url>'
        channel: '#trading-alerts'
```

## Verification Checklist

### Health Checks
- [ ] `/health` returns status: healthy
- [ ] `/ready` returns ready: true
- [ ] `/metrics` returns Prometheus metrics
- [ ] Kubernetes probes passing

### Monitoring
- [ ] Prometheus scraping all targets
- [ ] Grafana dashboards loading
- [ ] Alert rules active
- [ ] AlertManager receiving alerts

### High Availability
- [ ] Multiple replicas running
- [ ] HPA scaling working
- [ ] Pod anti-affinity enforced
- [ ] Circuit breakers functional

### Backup
- [ ] Full backup completing
- [ ] Checksums verified
- [ ] Remote upload working
- [ ] Restore tested

## Troubleshooting

### Pod Not Starting

```bash
# Check pod status
kubectl describe pod trading-engine-xxx -n crypto-bot

# Check init container logs
kubectl logs trading-engine-xxx -n crypto-bot -c wait-for-postgres

# Check main container logs
kubectl logs trading-engine-xxx -n crypto-bot
```

### Health Check Failing

```bash
# Test from within cluster
kubectl exec -it trading-engine-xxx -n crypto-bot -- curl localhost:8005/health

# Check service connectivity
kubectl exec -it trading-engine-xxx -n crypto-bot -- nc -zv postgres-service 5432
```

### Circuit Breaker Open

```bash
# Check circuit breaker status
curl http://trading-engine-service:8005/api/v1/circuit-breakers

# Force close circuit breaker (emergency)
curl -X POST http://trading-engine-service:8005/api/v1/circuit-breakers/bybit_api/close
```

### Alert Not Firing

```bash
# Check alert status in Prometheus
curl http://prometheus:9090/api/v1/alerts

# Check AlertManager status
curl http://alertmanager:9093/api/v2/status
```

## Files Summary

| File | Purpose |
|------|---------|
| `/infrastructure/kubernetes/trading-engine-deployment.yaml` | K8s deployment with HA |
| `/services/trading-engine/app/core/__init__.py` | Core module initialization |
| `/services/trading-engine/app/core/circuit_breaker.py` | Circuit breaker implementation |
| `/services/trading-engine/app/core/health.py` | Health check system |
| `/services/trading-engine/app/core/metrics.py` | Prometheus metrics |
| `/infrastructure/monitoring/grafana/dashboards/trading-overview.json` | Grafana dashboard |
| `/infrastructure/backup/backup-database.sh` | Database backup script |
| `/infrastructure/backup/restore-database.sh` | Database restore script |

## Success Metrics

| Metric | Target | Description |
|--------|--------|-------------|
| Uptime | 99.9% | Service availability |
| Recovery Time | <15 min | Mean time to recovery |
| Deployment Success | >98% | Zero-downtime deployments |
| Alert Latency | <30s | Time from issue to alert |
| Health Check | <100ms | Response time |

## Contact

For issues with Phase 7 implementation:
- Review logs: `kubectl logs -f deployment/trading-engine -n crypto-bot`
- Check Grafana: http://localhost:3000/d/trading-overview
- Check Prometheus: http://localhost:9090/targets

---
*Phase 7: High Availability & Monitoring Infrastructure - Production Ready*
