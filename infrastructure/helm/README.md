# Crypto Trading Bot - Helm Charts

> Merged from `infrastructure/helm/QUICK_REFERENCE.md` on 2026-07-30.

> **Deployment posture (2026-07-30):** These Helm charts exist and were exercised against a cluster once (2025-11-23), but the current project posture is **docker-compose-only for v1.x** — Kubernetes/Helm deployment is out of scope per `.planning/REQUIREMENTS.md`. The canonical way to run the stack is `docker compose -f docker-compose.unified.yml up -d` from the repo root. Keep this document for when/if a K8s deployment target returns.

Production-ready Helm charts for deploying the Crypto Trading Bot microservices architecture to Kubernetes.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Chart Structure](#chart-structure)
- [Configuration](#configuration)
- [Installation](#installation)
- [Upgrading](#upgrading)
- [Uninstallation](#uninstallation)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Advanced Configuration](#advanced-configuration)
- [Quick Reference](#quick-reference)

## Overview

This Helm chart deploys a complete crypto trading bot platform with:

- **10 Microservices**: API Gateway, Trading Engine, Portfolio Manager, Technical Analysis, Bybit Connector, Market Data Service, Notification Service, ML Prediction, Risk Metrics, Sentiment Analysis
- **4 Databases**: PostgreSQL, TimescaleDB, Redis, RabbitMQ
- **Monitoring**: Prometheus and Grafana
- **Auto-scaling**: Horizontal Pod Autoscaling for all services
- **Security**: Network policies, secret management, RBAC
- **High Availability**: Pod anti-affinity, pod disruption budgets

## Prerequisites

### Required Tools

- **Kubernetes Cluster**: 1.24+ (tested on 1.28)
- **Helm**: 3.12+
- **kubectl**: 1.24+
- **Storage Class**: For persistent volumes
- **Ingress Controller**: NGINX Ingress Controller (for production)
- **Cert Manager**: For TLS certificates (optional)

### Minimum Cluster Resources

#### Development Environment
- **Nodes**: 1 node
- **CPU**: 4 cores total
- **Memory**: 8 GB total
- **Storage**: 20 GB

#### Staging Environment
- **Nodes**: 2 nodes
- **CPU**: 8 cores total
- **Memory**: 16 GB total
- **Storage**: 50 GB

#### Production Environment
- **Nodes**: 3+ nodes
- **CPU**: 16+ cores total
- **Memory**: 32+ GB total
- **Storage**: 200+ GB

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/crypto-trading-bot/crypto-trading-bot.git
cd crypto-trading-bot/infrastructure/helm
```

### 2. Create Secrets

```bash
# Navigate to scripts directory
cd scripts

# Create namespace
kubectl create namespace crypto-bot

# Create required secrets
kubectl create secret generic postgresql-secret \
  --from-literal=password=your_postgres_password \
  -n crypto-bot

kubectl create secret generic timescaledb-secret \
  --from-literal=password=your_timescale_password \
  -n crypto-bot

kubectl create secret generic redis-secret \
  --from-literal=password=your_redis_password \
  -n crypto-bot

kubectl create secret generic rabbitmq-secret \
  --from-literal=password=your_rabbitmq_password \
  -n crypto-bot

kubectl create secret generic bybit-secret \
  --from-literal=api-key=your_bybit_api_key \
  --from-literal=api-secret=your_bybit_api_secret \
  -n crypto-bot

kubectl create secret generic grafana-secret \
  --from-literal=password=your_grafana_password \
  -n crypto-bot
```

### 3. Install Chart

```bash
# Development environment
./install.sh dev crypto-bot crypto-trading-bot

# Staging environment
./install.sh staging crypto-bot-staging crypto-trading-bot

# Production environment
./install.sh prod crypto-bot-prod crypto-trading-bot
```

### 4. Verify Installation

```bash
# Check deployment status
kubectl get pods -n crypto-bot

# Check services
kubectl get svc -n crypto-bot

# Run tests
./test.sh crypto-bot crypto-trading-bot
```

## Chart Structure

```
infrastructure/helm/
├── crypto-trading-bot/              # Main umbrella chart
│   ├── Chart.yaml                   # Chart metadata
│   ├── values.yaml                  # Default values (production)
│   ├── values-dev.yaml             # Development overrides
│   ├── values-staging.yaml         # Staging overrides
│   ├── values-prod.yaml            # Production overrides
│   ├── templates/                   # Main templates
│   │   ├── _helpers.tpl            # Template helpers
│   │   ├── NOTES.txt               # Post-install notes
│   │   └── namespace.yaml          # Namespace definition
│   └── charts/                      # Subcharts
│       ├── api-gateway/            # API Gateway subchart
│       │   ├── Chart.yaml
│       │   ├── values.yaml
│       │   └── templates/
│       │       ├── deployment.yaml
│       │       ├── service.yaml
│       │       ├── hpa.yaml
│       │       ├── ingress.yaml
│       │       ├── configmap.yaml
│       │       ├── serviceaccount.yaml
│       │       └── tests/
│       │           └── test-connection.yaml
│       ├── trading-engine/         # Similar structure
│       ├── portfolio-manager/
│       ├── technical-analysis/
│       ├── bybit-connector/
│       ├── market-data-service/
│       ├── notification-service/
│       ├── ml-prediction-service/
│       ├── risk-metrics-service/
│       ├── sentiment-analysis-service/
│       ├── postgresql/
│       ├── timescaledb/
│       ├── redis/
│       ├── rabbitmq/
│       ├── prometheus/
│       └── grafana/
├── scripts/                         # Helper scripts
│   ├── install.sh                  # Installation script
│   ├── upgrade.sh                  # Upgrade script
│   ├── uninstall.sh                # Uninstallation script
│   └── test.sh                     # Test runner
└── README.md                        # This file
```

## Configuration

### Global Configuration

The `global` section in `values.yaml` contains shared configuration for all services:

```yaml
global:
  imageRegistry: docker.io          # Container registry
  environment: production            # Environment name
  namespace: crypto-bot              # Kubernetes namespace
  storageClass: standard             # Storage class for PVCs

  # Database connections
  postgresql:
    host: postgresql
    port: 5432
    database: cryptobot
    username: cryptobot

  # Security
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000

  # Monitoring
  metrics:
    enabled: true
    port: 9090
```

### Service-Specific Configuration

Each service has its own configuration section:

```yaml
api-gateway:
  enabled: true                      # Enable/disable service
  replicaCount: 3                    # Number of replicas

  image:
    repository: crypto-bot/api-gateway
    tag: "1.0.0"

  resources:
    limits:
      cpu: 2000m
      memory: 1Gi
    requests:
      cpu: 500m
      memory: 512Mi

  autoscaling:
    enabled: true
    minReplicas: 3
    maxReplicas: 10
    targetCPUUtilizationPercentage: 70
```

### Environment-Specific Overrides

Use environment-specific values files to override defaults:

- `values-dev.yaml`: Minimal resources, single replicas, no ingress
- `values-staging.yaml`: Moderate resources, testnet, production-like setup
- `values-prod.yaml`: Full resources, mainnet, high availability

## Installation

### Using Installation Script (Recommended)

```bash
cd scripts

# Development
./install.sh dev crypto-bot crypto-trading-bot

# Staging
./install.sh staging crypto-bot-staging crypto-trading-bot

# Production
./install.sh prod crypto-bot-prod crypto-trading-bot
```

The installation script will:
1. Check prerequisites
2. Validate environment
3. Create namespace
4. Check for required secrets
5. Perform dry-run validation
6. Install/upgrade the chart
7. Verify deployment
8. Optionally run tests

### Manual Installation

```bash
# Install with default values (production)
helm install crypto-trading-bot ./crypto-trading-bot \
  --namespace crypto-bot \
  --create-namespace \
  --wait \
  --timeout 10m

# Install with environment-specific values
helm install crypto-trading-bot ./crypto-trading-bot \
  --namespace crypto-bot \
  --create-namespace \
  --values ./crypto-trading-bot/values-dev.yaml \
  --wait \
  --timeout 10m
```

### Installation Options

```bash
# Dry-run to preview changes
helm install crypto-trading-bot ./crypto-trading-bot \
  --namespace crypto-bot \
  --values ./crypto-trading-bot/values-dev.yaml \
  --dry-run --debug

# Install with custom release name
helm install my-trading-bot ./crypto-trading-bot \
  --namespace crypto-bot

# Install with value overrides
helm install crypto-trading-bot ./crypto-trading-bot \
  --namespace crypto-bot \
  --set api-gateway.replicaCount=5 \
  --set global.environment=staging
```

## Upgrading

### Using Upgrade Script (Recommended)

```bash
cd scripts

# Upgrade any environment
./upgrade.sh [dev|staging|prod] [namespace] [release-name]

# Upgrade development
./upgrade.sh dev crypto-bot crypto-trading-bot

# Upgrade production (with confirmation)
./upgrade.sh prod crypto-bot-prod crypto-trading-bot
```

The upgrade script will:
1. Check if release exists
2. Display current release info
3. Show diff (if helm-diff plugin installed)
4. Perform upgrade with atomic rollback
5. Monitor rollout status
6. Verify upgrade
7. Display rollback instructions

### Manual Upgrade

```bash
# Upgrade with new values
helm upgrade crypto-trading-bot ./crypto-trading-bot \
  --namespace crypto-bot \
  --values ./crypto-trading-bot/values-prod.yaml \
  --wait \
  --timeout 10m \
  --atomic

# Upgrade specific service only
helm upgrade crypto-trading-bot ./crypto-trading-bot \
  --namespace crypto-bot \
  --reuse-values \
  --set api-gateway.image.tag=1.1.0
```

### Upgrade Strategies

#### Rolling Update (Default)
- Zero downtime
- Gradual pod replacement
- Automatic rollback on failure (with --atomic)

```yaml
# Configured in deployment.yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 1
    maxUnavailable: 0
```

#### Blue-Green Deployment

```bash
# Deploy new version with different release name
helm install crypto-trading-bot-green ./crypto-trading-bot \
  --namespace crypto-bot \
  --values ./crypto-trading-bot/values-prod.yaml \
  --set global.environment=production-green

# Test green deployment
# Switch traffic (update ingress)
# Remove blue deployment
```

### Rollback

```bash
# Rollback to previous version
helm rollback crypto-trading-bot -n crypto-bot

# Rollback to specific revision
helm rollback crypto-trading-bot 3 -n crypto-bot

# View rollback history
helm history crypto-trading-bot -n crypto-bot
```

## Uninstallation

### Using Uninstall Script

```bash
cd scripts

# Basic uninstall (keeps PVCs and namespace)
./uninstall.sh crypto-bot crypto-trading-bot

# Complete uninstall (deletes everything)
./uninstall.sh crypto-bot crypto-trading-bot true true
```

### Manual Uninstallation

```bash
# Uninstall release
helm uninstall crypto-trading-bot -n crypto-bot

# Delete PVCs (WARNING: This deletes all data)
kubectl delete pvc --all -n crypto-bot

# Delete namespace
kubectl delete namespace crypto-bot
```

## Testing

### Using Test Script

```bash
cd scripts
./test.sh crypto-bot crypto-trading-bot
```

The test script runs:
1. Helm built-in tests
2. Connectivity tests for all services
3. Health checks for all pods
4. Database connectivity tests
5. Basic performance tests

### Manual Testing

```bash
# Run Helm tests
helm test crypto-trading-bot -n crypto-bot

# Test API Gateway
kubectl run test-curl --image=curlimages/curl --rm -i --restart=Never \
  -n crypto-bot \
  -- curl -s http://api-gateway:8000/health

# Check pod health
kubectl get pods -n crypto-bot

# View service logs
kubectl logs -f -n crypto-bot -l app=api-gateway

# Port forward for local testing
kubectl port-forward -n crypto-bot svc/api-gateway 8000:8000
curl http://localhost:8000/health

# Health check all services
for svc in api-gateway trading-engine portfolio-manager technical-analysis; do
  kubectl run test-$svc --image=curlimages/curl --rm -i --restart=Never \
    -n crypto-bot \
    -- curl -s http://$svc:800x/health && echo "$svc: OK" || echo "$svc: FAIL"
done
```

## Troubleshooting

### Common Issues

#### 1. Pods Not Starting

```bash
# Check pod status
kubectl get pods -n crypto-bot

# Describe problematic pod
kubectl describe pod <pod-name> -n crypto-bot

# View pod logs
kubectl logs <pod-name> -n crypto-bot

# View previous container logs (for CrashLoopBackOff)
kubectl logs <pod-name> -n crypto-bot --previous

# Check events
kubectl get events -n crypto-bot --sort-by='.lastTimestamp'
```

**Common causes:**
- Missing secrets
- Insufficient resources
- Image pull errors
- Failed health checks

#### 2. Database Connection Errors

```bash
# Check database pod status
kubectl get pods -n crypto-bot -l app=postgresql

# Test database connectivity
kubectl run test-db --image=postgres:16-alpine --rm -i --restart=Never \
  -n crypto-bot \
  --env="PGPASSWORD=your_password" \
  -- psql -h postgresql -U cryptobot -d cryptobot -c "SELECT 1"

# Check database logs
kubectl logs -n crypto-bot -l app=postgresql
```

#### 3. Service Not Reachable

```bash
# Check service endpoints
kubectl get endpoints -n crypto-bot

# Check if pods are ready
kubectl get pods -n crypto-bot -l app=service-name

# Test service connectivity
kubectl run test-svc --image=curlimages/curl --rm -i --restart=Never \
  -n crypto-bot \
  -- curl -v http://api-gateway:8000/health

# Check network policies
kubectl get networkpolicies -n crypto-bot
```

#### 4. Ingress Not Working

```bash
# Check ingress status
kubectl get ingress -n crypto-bot

# Describe ingress
kubectl describe ingress api-gateway -n crypto-bot

# Check ingress controller logs
kubectl logs -n ingress-nginx -l app.kubernetes.io/component=controller

# Verify DNS
nslookup api.cryptobot.example.com
```

#### 5. ImagePullBackOff

```bash
# Check image name
kubectl describe pod pod-name -n crypto-bot | grep Image

# Verify image pull secrets
kubectl get secrets -n crypto-bot

# Test image pull
docker pull registry/image:tag
```

#### 6. Pending Pods

```bash
# Check node resources
kubectl top nodes

# Describe pod to see reason
kubectl describe pod pod-name -n crypto-bot

# Check PVC status
kubectl get pvc -n crypto-bot
```

### Debug Mode

Enable debug logging for services:

```bash
helm upgrade crypto-trading-bot ./crypto-trading-bot \
  --namespace crypto-bot \
  --reuse-values \
  --set global.logging.level=DEBUG
```

### Resource Issues

```bash
# Check node resources
kubectl top nodes

# Check pod resource usage
kubectl top pods -n crypto-bot

# View resource requests/limits
kubectl describe nodes | grep -A 5 "Allocated resources"

# Scale down services temporarily
kubectl scale deployment api-gateway --replicas=1 -n crypto-bot
```

## Advanced Configuration

### Custom Values File

Create your own values file:

```yaml
# custom-values.yaml
global:
  environment: production
  imageRegistry: my-registry.azurecr.io

api-gateway:
  replicaCount: 5
  resources:
    limits:
      cpu: 4000m
      memory: 2Gi
```

Install with custom values:

```bash
helm install crypto-trading-bot ./crypto-trading-bot \
  -n crypto-bot \
  -f crypto-trading-bot/values-prod.yaml \
  -f custom-values.yaml
```

### Enable/Disable Services

```yaml
# Disable services not needed
ml-prediction-service:
  enabled: false

sentiment-analysis-service:
  enabled: false

grafana:
  enabled: false
```

### Custom Resource Limits

```yaml
trading-engine:
  resources:
    limits:
      cpu: 8000m
      memory: 4Gi
    requests:
      cpu: 2000m
      memory: 2Gi
```

### External Databases

Use external managed databases:

```yaml
postgresql:
  enabled: false  # Disable built-in PostgreSQL

global:
  postgresql:
    host: my-postgres.database.azure.com
    port: 5432
    database: cryptobot
    username: admin@my-postgres
    existingSecret: external-db-secret
```

### Multi-Region Deployment

Deploy to multiple regions:

```bash
# Region 1 (US East)
helm install crypto-bot-us-east ./crypto-trading-bot \
  -n crypto-bot-us-east \
  -f values-prod.yaml \
  -f values-region-us-east.yaml

# Region 2 (EU West)
helm install crypto-bot-eu-west ./crypto-trading-bot \
  -n crypto-bot-eu-west \
  -f values-prod.yaml \
  -f values-region-eu-west.yaml
```

### Monitoring Integration

#### Prometheus ServiceMonitor

```yaml
global:
  metrics:
    enabled: true
    serviceMonitor: true
```

#### Grafana Dashboards

Grafana dashboards are automatically provisioned via ConfigMaps in the Grafana subchart.

Access Grafana:
```bash
# Port forward
kubectl port-forward -n crypto-bot svc/grafana 3000:3000

# Retrieve the admin password from the grafana-secret you created
# (do not use a default password; rotate if one was ever set)
kubectl get secret grafana-secret -n crypto-bot -o jsonpath='{.data.password}' | base64 -d

# Open browser
http://localhost:3000
```

### Security Hardening

#### Network Policies

```yaml
global:
  networkPolicy:
    enabled: true
```

#### Pod Security Standards

```yaml
global:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    fsGroup: 1000
    seccompProfile:
      type: RuntimeDefault
```

#### Secret Management

Use external secret management:

```bash
# Using External Secrets Operator
kubectl apply -f - <<EOF
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: postgresql-secret
  namespace: crypto-bot
spec:
  secretStoreRef:
    name: vault-backend
    kind: SecretStore
  target:
    name: postgresql-secret
  data:
  - secretKey: password
    remoteRef:
      key: database/postgresql
      property: password
EOF
```

## Maintenance

### Backup and Restore

#### Backup

```bash
# Backup Helm values
helm get values crypto-trading-bot -n crypto-bot > backup-values.yaml

# Backup Kubernetes resources
kubectl get all,pvc,secrets,configmaps -n crypto-bot -o yaml > backup-k8s.yaml

# Backup databases (example for PostgreSQL)
kubectl exec -n crypto-bot postgresql-0 -- \
  pg_dump -U cryptobot cryptobot > backup-db.sql

# Backup PostgreSQL with dated filename
kubectl exec -n crypto-bot postgresql-0 -- \
  pg_dump -U cryptobot cryptobot > backup-$(date +%Y%m%d).sql
```

#### Restore

```bash
# Restore from backup values
helm install crypto-trading-bot ./crypto-trading-bot \
  -n crypto-bot \
  -f backup-values.yaml

# Restore database
kubectl exec -i -n crypto-bot postgresql-0 -- \
  psql -U cryptobot cryptobot < backup-db.sql
```

### Monitoring

```bash
# Watch deployment status
kubectl get pods -n crypto-bot --watch

# Monitor HPA
kubectl get hpa -n crypto-bot --watch

# View metrics
kubectl top pods -n crypto-bot
```

### Log Aggregation

Collect logs from all services:

```bash
# Stream all logs
kubectl logs -f -n crypto-bot --all-containers=true

# Export logs
kubectl logs -n crypto-bot --all-containers=true > all-logs.txt
```

## Performance Tuning

### Resource Optimization

1. Monitor actual usage:
```bash
kubectl top pods -n crypto-bot
```

2. Adjust resource requests/limits based on usage

3. Enable vertical pod autoscaling (VPA) for automatic optimization

```bash
# View resource requests/limits
kubectl describe nodes | grep -A 5 "Allocated resources"

# Edit resource limits in place
kubectl edit deployment api-gateway -n crypto-bot

# Update HPA thresholds
kubectl patch hpa api-gateway -n crypto-bot \
  -p '{"spec":{"targetCPUUtilizationPercentage":60}}'
```

### Database Performance

#### PostgreSQL Tuning

```yaml
postgresql:
  config:
    maxConnections: 200
    sharedBuffers: "2GB"
    effectiveCacheSize: "6GB"
    workMem: "32MB"
```

#### TimescaleDB Compression

```yaml
timescaledb:
  timescale:
    compressionEnabled: true
    retentionDays: 365
    chunkTimeInterval: "1 day"
```

### Caching Strategy

```yaml
redis:
  config:
    maxmemory: "2gb"
    maxmemoryPolicy: "allkeys-lru"
```

## CI/CD Integration

### GitLab CI Example

```yaml
deploy:
  stage: deploy
  script:
    - cd infrastructure/helm/scripts
    - ./upgrade.sh prod crypto-bot-prod crypto-trading-bot
  only:
    - main
```

### GitHub Actions Example

```yaml
name: Deploy to Production
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Install Helm
        run: |
          curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
      - name: Deploy
        run: |
          cd infrastructure/helm/scripts
          ./upgrade.sh prod crypto-bot-prod crypto-trading-bot
```

## Quick Reference

> Merged from `infrastructure/helm/QUICK_REFERENCE.md` (last updated 2025-11-23) on 2026-07-30. Daily-operations commands for a Helm-deployed cluster. Remember: current v1.x posture is compose-only — these apply only when a K8s deployment is active.

### Monitoring Status

```bash
# Check pod status
kubectl get pods -n crypto-bot

# Watch pods
kubectl get pods -n crypto-bot --watch

# Check resource usage
kubectl top pods -n crypto-bot
kubectl top nodes

# View HPA status
kubectl get hpa -n crypto-bot

# Check service status
kubectl get svc -n crypto-bot

# View ingress
kubectl get ingress -n crypto-bot
```

### Logs

```bash
# View logs for specific service
kubectl logs -f -n crypto-bot -l app=api-gateway

# View logs for specific pod
kubectl logs -f -n crypto-bot pod-name

# View logs from all containers
kubectl logs -f -n crypto-bot pod-name --all-containers

# View previous container logs
kubectl logs -n crypto-bot pod-name --previous

# Tail last 100 lines
kubectl logs -n crypto-bot pod-name --tail=100
```

### Debugging

```bash
# Describe pod
kubectl describe pod pod-name -n crypto-bot

# Get events
kubectl get events -n crypto-bot --sort-by='.lastTimestamp'

# Execute command in pod
kubectl exec -it pod-name -n crypto-bot -- /bin/sh

# Port forward to local
kubectl port-forward -n crypto-bot svc/api-gateway 8000:8000
```

### Scaling

```bash
# Manual scaling
kubectl scale deployment api-gateway --replicas=5 -n crypto-bot

# Edit HPA
kubectl edit hpa api-gateway -n crypto-bot

# Disable autoscaling temporarily
kubectl patch hpa api-gateway -n crypto-bot -p '{"spec":{"minReplicas":1,"maxReplicas":1}}'
```

### Configuration

```bash
# View current values
helm get values crypto-trading-bot -n crypto-bot

# View all values (including defaults)
helm get values crypto-trading-bot -n crypto-bot --all

# Update single value
helm upgrade crypto-trading-bot ./crypto-trading-bot \
  -n crypto-bot \
  --reuse-values \
  --set api-gateway.replicaCount=5

# Update with new values file
helm upgrade crypto-trading-bot ./crypto-trading-bot \
  -n crypto-bot \
  -f custom-values.yaml
```

### Secrets

```bash
# Create secret
kubectl create secret generic my-secret \
  --from-literal=key=value \
  -n crypto-bot

# View secrets (names only)
kubectl get secrets -n crypto-bot

# Decode secret
kubectl get secret postgresql-secret -n crypto-bot -o jsonpath='{.data.password}' | base64 -d

# Edit secret
kubectl edit secret postgresql-secret -n crypto-bot

# Delete secret
kubectl delete secret my-secret -n crypto-bot
```

### Database Operations

```bash
# PostgreSQL
kubectl exec -it postgresql-0 -n crypto-bot -- psql -U cryptobot

# TimescaleDB
kubectl exec -it timescaledb-0 -n crypto-bot -- psql -U timescale

# Redis
kubectl exec -it redis-0 -n crypto-bot -- redis-cli

# RabbitMQ Management
kubectl port-forward -n crypto-bot svc/rabbitmq 15672:15672
# Open: http://localhost:15672
```

### Restart Services

```bash
# Restart deployment
kubectl rollout restart deployment api-gateway -n crypto-bot

# Restart all deployments
kubectl rollout restart deployment --all -n crypto-bot

# Check rollout status
kubectl rollout status deployment api-gateway -n crypto-bot

# View rollout history
kubectl rollout history deployment api-gateway -n crypto-bot
```

### Emergency Operations

```bash
# Stop all trading (scale trading-engine to 0)
kubectl scale deployment trading-engine --replicas=0 -n crypto-bot

# Emergency pod deletion
kubectl delete pod pod-name -n crypto-bot --force --grace-period=0

# Drain node for maintenance
kubectl drain node-name --ignore-daemonsets --delete-emptydir-data

# Uncordon node after maintenance
kubectl uncordon node-name
```

> Note (2026-07-30): in the current compose deployment the equivalent emergency stop is the kill-switch file (`touch safety/EMERGENCY_STOP`) or `POST /api/portfolio/emergency-stop` — see the repo root `RUNBOOK.md`.

### Helm Commands

```bash
# List releases
helm list -n crypto-bot

# Get release info
helm status crypto-trading-bot -n crypto-bot

# Get manifest
helm get manifest crypto-trading-bot -n crypto-bot

# Get notes
helm get notes crypto-trading-bot -n crypto-bot

# Get hooks
helm get hooks crypto-trading-bot -n crypto-bot

# Dry-run upgrade
helm upgrade crypto-trading-bot ./crypto-trading-bot \
  -n crypto-bot \
  -f values-prod.yaml \
  --dry-run --debug
```

### Resource Cleanup

```bash
# Delete completed pods
kubectl delete pods -n crypto-bot --field-selector=status.phase==Succeeded

# Delete evicted pods
kubectl delete pods -n crypto-bot --field-selector=status.phase==Failed

# Delete old replica sets
kubectl delete replicaset -n crypto-bot --all

# Cleanup orphaned PVCs
kubectl get pvc -n crypto-bot | grep Released | awk '{print $1}' | xargs kubectl delete pvc -n crypto-bot
```

### Networking

```bash
# View services
kubectl get svc -n crypto-bot

# View endpoints
kubectl get endpoints -n crypto-bot

# View network policies
kubectl get networkpolicies -n crypto-bot

# Test DNS
kubectl run test-dns --image=busybox --rm -i --restart=Never \
  -n crypto-bot \
  -- nslookup api-gateway
```

### Prometheus Access

```bash
# Port forward
kubectl port-forward -n crypto-bot svc/prometheus 9090:9090

# Open browser
http://localhost:9090
```

### Quick Health Check Script

```bash
#!/bin/bash
# Save as health-check.sh

NAMESPACE="crypto-bot"

echo "=== Pod Status ==="
kubectl get pods -n $NAMESPACE

echo -e "\n=== Unhealthy Pods ==="
kubectl get pods -n $NAMESPACE --field-selector=status.phase!=Running,status.phase!=Succeeded

echo -e "\n=== HPA Status ==="
kubectl get hpa -n $NAMESPACE

echo -e "\n=== Resource Usage ==="
kubectl top pods -n $NAMESPACE 2>/dev/null || echo "Metrics server not available"

echo -e "\n=== Recent Events ==="
kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp' | tail -10
```

### Environment Variables

Common environment variables to set:

```bash
export KUBECONFIG=~/.kube/config
export NAMESPACE=crypto-bot
export RELEASE_NAME=crypto-trading-bot
export HELM_CHART_PATH=./infrastructure/helm/crypto-trading-bot

# Then use
kubectl get pods -n $NAMESPACE
helm status $RELEASE_NAME -n $NAMESPACE
```

### Aliases

Add to ~/.bashrc or ~/.zshrc:

```bash
# Kubernetes aliases
alias k='kubectl'
alias kgp='kubectl get pods'
alias kgs='kubectl get svc'
alias kd='kubectl describe'
alias kl='kubectl logs'
alias ke='kubectl exec -it'

# Namespace-specific
alias kcb='kubectl -n crypto-bot'
alias kcbp='kubectl get pods -n crypto-bot'
alias kcbl='kubectl logs -n crypto-bot'

# Helm aliases
alias h='helm'
alias hls='helm list'
alias hst='helm status'
alias hup='helm upgrade'
```

### Important Files

```
Main Chart: infrastructure/helm/crypto-trading-bot/
Values:     infrastructure/helm/crypto-trading-bot/values-[env].yaml
Scripts:    infrastructure/helm/scripts/
Docs:       infrastructure/helm/README.md (this file)
```

## Support

- **Documentation**: https://docs.cryptobot.example.com
- **Issues**: https://github.com/crypto-trading-bot/issues
- **Discussions**: https://github.com/crypto-trading-bot/discussions

## License

Apache License 2.0
