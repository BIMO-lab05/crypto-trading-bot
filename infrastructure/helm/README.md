# Crypto Trading Bot - Helm Charts

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

## Support

- **Documentation**: https://docs.cryptobot.example.com
- **Issues**: https://github.com/crypto-trading-bot/issues
- **Discussions**: https://github.com/crypto-trading-bot/discussions

## License

Apache License 2.0

---

**Happy Trading!** 🚀📈
