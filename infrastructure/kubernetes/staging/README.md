# Kubernetes Staging Deployment

## Overview

This directory contains Kubernetes manifests for deploying the Crypto Trading Bot to a staging environment for pre-production validation.

**Namespace:** `trading-bot-staging`

## Components Deployed

### Microservices (10 Services)
| Service | Port | Replicas | Description |
|---------|------|----------|-------------|
| api-gateway | 8000 | 2 | External API interface |
| trading-engine | 8005 | 3 | Core trading logic (with HPA 2-10) |
| portfolio-manager | 8003 | 2 | Position tracking |
| technical-analysis | 8004 | 2 | TA indicators |
| bybit-connector | 8001 | 2 | Exchange integration |
| market-data-service | 8002 | 2 | Market data ingestion |
| notification-service | 8006 | 1 | Alerts and notifications |
| ml-prediction-service | 8007 | 2 | ML-based predictions |
| risk-metrics-service | 8008 | 2 | Risk calculations |
| sentiment-analysis-service | 8009 | 1 | Market sentiment |

### Databases (4 Services)
| Database | Port | Storage | Description |
|----------|------|---------|-------------|
| PostgreSQL | 5432 | 5Gi | Main application database |
| TimescaleDB | 5432 | 20Gi | Time-series market data |
| Redis | 6379 | 2Gi | Cache and session storage |
| RabbitMQ | 5672 | 2Gi | Message broker |

### Monitoring (2 Services)
| Service | Port | Description |
|---------|------|-------------|
| Prometheus | 9090 | Metrics collection |
| Grafana | 3000 | Visualization dashboards |

## Quick Start

### Prerequisites
- kubectl configured and connected to cluster
- Docker images built and pushed to registry (or using local images)
- Storage class configured (default: standard)

### Deploy

```bash
# Navigate to staging directory
cd /mnt/d/Bimo_max/crypto-trading-bot/infrastructure/kubernetes/staging

# Make scripts executable
chmod +x *.sh

# Deploy to staging
./deploy-staging.sh

# Or with dry-run first
./deploy-staging.sh --dry-run
```

### Verify

```bash
# Run verification script
./verify-staging.sh

# Detailed verification
./verify-staging.sh --detailed

# Watch pods
./verify-staging.sh --watch
```

## HPA Configuration

The Trading Engine is configured with HorizontalPodAutoscaler:

| Setting | Value |
|---------|-------|
| Min Replicas | 2 |
| Max Replicas | 10 |
| CPU Target | 70% |
| Memory Target | 80% |
| Scale Up Stabilization | 60s |
| Scale Down Stabilization | 300s |

## Health Check Endpoints

All services expose health check endpoints:

| Endpoint | Purpose |
|----------|---------|
| `/health` | Liveness check |
| `/ready` | Readiness check |
| `/metrics` | Prometheus metrics |

## Access Services

```bash
# API Gateway (LoadBalancer)
kubectl get svc api-gateway-service -n trading-bot-staging

# Port forward API Gateway
kubectl port-forward -n trading-bot-staging svc/api-gateway-service 8000:8000

# Port forward Trading Engine
kubectl port-forward -n trading-bot-staging svc/trading-engine-service 8005:8005

# Port forward Grafana
kubectl port-forward -n trading-bot-staging svc/grafana-service 3000:3000

# Port forward Prometheus
kubectl port-forward -n trading-bot-staging svc/prometheus-service 9090:9090
```

## Secret Management

**IMPORTANT:** Update secrets with real values before using!

```bash
# Generate base64 encoded password
echo -n "your-password" | base64

# Edit secrets
kubectl edit secret db-secrets -n trading-bot-staging
kubectl edit secret api-secrets -n trading-bot-staging
kubectl edit secret bybit-secrets -n trading-bot-staging
```

## Files

| File | Description |
|------|-------------|
| namespace.yaml | Namespace, ResourceQuota, LimitRange, NetworkPolicy |
| configmap.yaml | Application configuration |
| secrets.yaml | Credentials (templates) |
| storage.yaml | PersistentVolumeClaims |
| databases.yaml | PostgreSQL, TimescaleDB, Redis, RabbitMQ |
| trading-engine.yaml | Trading Engine with HPA, PDB, ServiceMonitor |
| microservices.yaml | All other microservices |
| monitoring.yaml | Prometheus and Grafana |
| deploy-staging.sh | Deployment script |
| verify-staging.sh | Verification script |
| kustomization.yaml | Kustomize configuration |

## Troubleshooting

### View Logs
```bash
kubectl logs -f deployment/trading-engine -n trading-bot-staging
kubectl logs -f deployment/api-gateway -n trading-bot-staging
```

### Check Events
```bash
kubectl get events -n trading-bot-staging --sort-by='.lastTimestamp'
```

### Describe Resources
```bash
kubectl describe pod <pod-name> -n trading-bot-staging
kubectl describe hpa trading-engine-hpa -n trading-bot-staging
```

### Check Resource Usage
```bash
kubectl top pods -n trading-bot-staging
```

## Cleanup

```bash
# Delete all staging resources
kubectl delete namespace trading-bot-staging

# Or delete specific resources
kubectl delete -k staging/
```

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-12-12 | Initial staging deployment |
