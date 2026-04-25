# Production Deployment Infrastructure

## Overview

This directory contains all Kubernetes manifests and scripts required to deploy the Crypto Trading Bot to a production environment.

**IMPORTANT:** This deploys a LIVE trading system with real funds. Review all configurations carefully before deploying.

## Directory Structure

```
infrastructure/production/
|-- namespace.yaml          # Production namespace with ResourceQuotas and PriorityClasses
|-- configmap.yaml          # Non-sensitive configuration and alerting rules
|-- secrets-template.yaml   # Template for sensitive configuration (DO NOT COMMIT REAL SECRETS)
|-- storage.yaml            # Persistent Volume Claims
|-- databases.yaml          # PostgreSQL, TimescaleDB, Redis, RabbitMQ
|-- microservices.yaml      # All 10+ microservices
|-- monitoring.yaml         # Prometheus, Grafana, AlertManager
|-- autoscaling.yaml        # HPA and PodDisruptionBudgets
|-- kustomization.yaml      # Kustomize configuration
|-- deploy-production.sh    # Deployment script
|-- verify-production.sh    # Verification script
`-- README.md               # This file
```

## Prerequisites

1. **Kubernetes Cluster** (v1.28+)
   - 3+ worker nodes recommended
   - Ingress controller installed
   - Metrics server installed

2. **Tools Required**
   - kubectl (v1.28+)
   - helm (v3.12+)
   - kustomize (v5.0+)

3. **Access Required**
   - Cluster admin access
   - Container registry access
   - Secrets management access

## Quick Start

### 1. Configure Secrets

```bash
# Copy template and edit with real values
cp secrets-template.yaml secrets.yaml
vim secrets.yaml  # Edit with real values

# NEVER commit secrets.yaml to version control
```

### 2. Deploy

```bash
# Option A: Full deployment with script
./deploy-production.sh

# Option B: Dry run first
./deploy-production.sh --dry-run

# Option C: Using kustomize
kubectl apply -k .
```

### 3. Verify

```bash
./verify-production.sh --detailed
```

## Service Inventory

| Service | Port | Replicas | HPA Min/Max |
|---------|------|----------|-------------|
| api-gateway | 8000 | 3 | 3/10 |
| trading-engine | 8001 | 3 | 3/15 |
| portfolio-manager | 8002 | 2 | 2/6 |
| technical-analysis | 8003 | 2 | 2/8 |
| bybit-connector | 8004 | 2 | - |
| market-data-service | 8005 | 2 | 2/6 |
| ml-prediction-service | 8007 | 2 | 2/5 |
| notification-service | 8008 | 2 | - |
| risk-metrics-service | 8009 | 2 | 2/6 |
| sentiment-analysis | 8010 | 1 | - |

## Security Features

- **Pod Security Standards:** Restricted mode enforced
- **Network Policies:** Default deny with explicit allow rules
- **RBAC:** Service accounts with minimal permissions
- **Security Context:** Non-root containers, read-only filesystems, dropped capabilities
- **Resource Limits:** Prevents resource exhaustion attacks
- **Secrets Management:** Template-based, supports External Secrets Operator

## Monitoring

### Access Dashboards

```bash
# Grafana (port 3000)
kubectl port-forward -n crypto-bot-prod svc/grafana-service 3000:3000

# Prometheus (port 9090)
kubectl port-forward -n crypto-bot-prod svc/prometheus-service 9090:9090

# AlertManager (port 9093)
kubectl port-forward -n crypto-bot-prod svc/alertmanager-service 9093:9093
```

### Key Metrics

- Trading engine latency
- Order execution rate
- Portfolio PnL
- Error rates
- Resource utilization

## Rollback

```bash
# Automatic rollback
./deploy-production.sh --rollback

# Manual rollback
kubectl rollout undo deployment/[service-name] -n crypto-bot-prod
```

## Emergency Procedures

### Emergency Stop Trading

```bash
# Scale trading engine to 0
kubectl scale deployment/trading-engine --replicas=0 -n crypto-bot-prod

# Or use API
curl -X POST http://api-gateway:8000/api/v1/trading/emergency-stop
```

### Complete Shutdown

```bash
# Scale all services to 0
kubectl scale deployment --all --replicas=0 -n crypto-bot-prod
```

## Troubleshooting

### Check Pod Status
```bash
kubectl get pods -n crypto-bot-prod -o wide
```

### View Logs
```bash
kubectl logs -f deployment/[service-name] -n crypto-bot-prod
```

### Check Events
```bash
kubectl get events -n crypto-bot-prod --sort-by='.lastTimestamp'
```

## Related Documentation

- [Production Deployment Runbook](/PRODUCTION_DEPLOYMENT_RUNBOOK.md)
- [Security Hardening Guide](/docs/security/SECURITY_HARDENING.md)
- [Monitoring Setup](/infrastructure/monitoring/README.md)
- [Kubernetes Security](/infrastructure/kubernetes/security/README.md)

## Support

For issues or questions:
1. Check the troubleshooting guide
2. Review logs and events
3. Contact the DevOps team
