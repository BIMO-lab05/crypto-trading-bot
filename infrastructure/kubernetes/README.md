# Kubernetes Deployment for Crypto Trading Bot

> **Note (2026-07-30):** The Kubernetes deployment described here was validated once on **2025-11-23**. The **current posture is docker-compose-only for v1.x** — K8s is out of scope per `.planning/REQUIREMENTS.md` ("K8s deployment | docker-compose only for v1.x"). The canonical stack is `docker compose -f docker-compose.unified.yml up -d` from the repo root. This document is retained for a future K8s deployment target.

> Merged from `infrastructure/kubernetes/DEPLOYMENT_GUIDE.md` (v1.0, created 2025-11-23) on 2026-07-30.

## 📋 Table of Contents
- [Overview](#overview)
- [Deployment Summary](#deployment-summary)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Directory Structure](#directory-structure)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [Monitoring](#monitoring)
- [Scaling](#scaling)
- [Troubleshooting](#troubleshooting)
- [Update and Rollback](#update-and-rollback)
- [Backup and Recovery](#backup-and-recovery)
- [Security Best Practices](#security-best-practices)
- [Deployment Checklist](#deployment-checklist)

## 🎯 Overview

This directory contains production-grade Kubernetes manifests for deploying the Crypto Trading Bot microservices architecture. The deployment includes:

- **10 Microservices**: API Gateway, Trading Engine, Portfolio Manager, Technical Analysis, Bybit Connector, Market Data Service, Notification Service, ML Prediction Service, Risk Metrics Service, Sentiment Analysis Service
- **4 Databases**: PostgreSQL (main DB), TimescaleDB (time-series data), Redis (cache), RabbitMQ (message queue)
- **Monitoring Stack**: Prometheus and Grafana
- **Auto-scaling**: Horizontal Pod Autoscalers for critical services
- **Ingress**: External access with TLS termination

## 📊 Deployment Summary

*(From the 2025-11-23 deployment guide.)*

### Files Created: 58 Total

| Category | Files | Lines | Purpose |
|----------|-------|-------|---------|
| YAML Manifests | 54 | 4,584 | Kubernetes resource definitions |
| Shell Scripts | 3 | 587 | Deployment automation |
| Documentation | 1 | 781 | Comprehensive README |
| **TOTAL** | **58** | **5,952** | **Complete infrastructure** |

### Infrastructure Components

#### Microservices (10 Services)

Canonical service ports (matching the compose stack; see repo root `CLAUDE.md`):

| Service | Port | Purpose |
|---|---|---|
| api-gateway | 8000 | External API interface |
| bybit-connector | 8001 | Exchange integration |
| market-data-service | 8002 | Market data ingestion |
| portfolio-manager | 8003 | Position tracking |
| technical-analysis | 8004 | TA indicators |
| trading-engine | 8005 | Core trading logic |
| notification-service | 8006 | Alerts and notifications |
| ml-prediction-service | 8007 | ML-based predictions |
| sentiment-analysis-service | 8008 | Market sentiment |
| risk-metrics-service | 8009 | Risk calculations |

> ⚠️ Contradiction fixed 2026-07-30: the original 2025-11-23 deployment guide listed a different port order (trading-engine 8001, portfolio-manager 8002, technical-analysis 8003, bybit-connector 8004, market-data 8005, risk-metrics 8008, sentiment 8009). That order does not match the running compose stack or the rest of the docs. If you resurrect the K8s manifests, verify each Deployment's `containerPort` against the table above before deploying.

#### Databases (4 Services)
- **PostgreSQL** - Main application database (Port 5432, 10Gi storage)
- **TimescaleDB** - Time-series market data (Port 5432, 50Gi storage)
- **Redis** - Cache and session storage (Port 6379, 5Gi storage)
- **RabbitMQ** - Message broker (Port 5672/15672, 5Gi storage)

#### Monitoring (2 Services)
- **Prometheus** - Metrics collection and alerting
- **Grafana** - Visualization and dashboards

#### Autoscaling (3 HPAs)
- **API Gateway HPA** - 3-10 replicas, 70% CPU target
- **Trading Engine HPA** - 2-8 replicas, 70% CPU target
- **ML Prediction HPA** - 2-6 replicas, 75% CPU target

## 🔧 Prerequisites

### Required Tools
- **kubectl** (v1.24+): Kubernetes command-line tool
- **kustomize** (v4.0+): Template-free Kubernetes configuration
- **docker** (20.10+): Container runtime (for building images)
- **helm** (v3.0+): Package manager (optional, for cert-manager)

### Cluster Requirements
- **Kubernetes cluster** (v1.24+)
  - Minimum 3 nodes
  - Total: 50 CPU cores, 64GB RAM
  - Storage class supporting dynamic provisioning

### Cloud Providers
Tested on:
- **AWS EKS** (Elastic Kubernetes Service)
- **GCP GKE** (Google Kubernetes Engine)
- **Azure AKS** (Azure Kubernetes Service)
- **Local**: Minikube, Kind, K3s (development only)

### Installation Commands

```bash
# Install kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# Install kustomize
curl -s "https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh" | bash
sudo mv kustomize /usr/local/bin/

# Verify installations
kubectl version --client
kustomize version

# Verify cluster access
kubectl cluster-info
```

### Cluster Setup (Cloud-Specific)

```bash
# For AWS EKS
eksctl create cluster \
  --name crypto-bot-cluster \
  --region us-east-1 \
  --nodegroup-name standard-workers \
  --node-type t3.xlarge \
  --nodes 3 \
  --nodes-min 3 \
  --nodes-max 10

# For GCP GKE
gcloud container clusters create crypto-bot-cluster \
  --zone us-central1-a \
  --num-nodes 3 \
  --machine-type n1-standard-4 \
  --enable-autoscaling \
  --min-nodes 3 \
  --max-nodes 10

# For Azure AKS
az aks create \
  --resource-group crypto-bot-rg \
  --name crypto-bot-cluster \
  --node-count 3 \
  --node-vm-size Standard_D4s_v3 \
  --enable-cluster-autoscaler \
  --min-count 3 \
  --max-count 10
```

## 🚀 Quick Start

### 1. Build Docker Images

```bash
# Navigate to project root (repo checkout root)
cd <repo-root>   # e.g. wherever crypto-trading-bot is cloned

# Build all service images
./infrastructure/scripts/build-all-images.sh

# Tag images for your registry
docker tag crypto-bot/api-gateway:latest your-registry/crypto-bot/api-gateway:v1.0.0
# ... repeat for all services
```

Build-and-push loop for all services:

```bash
export REGISTRY="your-registry.example.com"
export VERSION="v1.0.0"

for service in api-gateway trading-engine portfolio-manager technical-analysis \
               bybit-connector market-data-service notification-service \
               ml-prediction-service risk-metrics-service sentiment-analysis-service; do
    docker build -t crypto-bot/${service}:latest ../../services/${service}/
    docker tag crypto-bot/${service}:latest ${REGISTRY}/crypto-bot/${service}:${VERSION}
    docker push ${REGISTRY}/crypto-bot/${service}:${VERSION}
done

# Update image references in kustomization
sed -i "s|crypto-bot/|${REGISTRY}/crypto-bot/|g" kustomization/base/kustomization.yaml
sed -i "s|newTag: latest|newTag: ${VERSION}|g" kustomization/base/kustomization.yaml
```

### 2. Configure Secrets

```bash
cd infrastructure/kubernetes

# Copy secret templates
cp secrets/db-secrets.yaml secrets/db-secrets-prod.yaml
cp secrets/api-secrets.yaml secrets/api-secrets-prod.yaml
cp secrets/bybit-secrets.yaml secrets/bybit-secrets-prod.yaml

# Edit secrets with real base64-encoded values
# IMPORTANT: Never commit these files!
echo "secrets/*-prod.yaml" >> .gitignore

# Example: Generate base64-encoded password
echo -n "your-strong-password" | base64
```

#### Scripted Secret Generation (Database)

```bash
# Generate strong passwords
POSTGRES_PASS=$(openssl rand -base64 32)
TIMESCALE_PASS=$(openssl rand -base64 32)
REDIS_PASS=$(openssl rand -base64 32)
RABBITMQ_PASS=$(openssl rand -base64 32)

# Base64 encode
POSTGRES_PASS_B64=$(echo -n "$POSTGRES_PASS" | base64)
TIMESCALE_PASS_B64=$(echo -n "$TIMESCALE_PASS" | base64)
REDIS_PASS_B64=$(echo -n "$REDIS_PASS" | base64)
RABBITMQ_PASS_B64=$(echo -n "$RABBITMQ_PASS" | base64)

# Create secrets file
cat > secrets/db-secrets-prod.yaml << EOF
apiVersion: v1
kind: Secret
metadata:
  name: db-secrets
  namespace: crypto-bot
type: Opaque
data:
  POSTGRES_PASSWORD: ${POSTGRES_PASS_B64}
  TIMESCALE_PASSWORD: ${TIMESCALE_PASS_B64}
  REDIS_PASSWORD: ${REDIS_PASS_B64}
  RABBITMQ_PASSWORD: ${RABBITMQ_PASS_B64}
  POSTGRES_URL: $(echo -n "postgresql://cryptobot:${POSTGRES_PASS}@postgres-service:5432/cryptobot" | base64)
  TIMESCALE_URL: $(echo -n "postgresql://cryptobot:${TIMESCALE_PASS}@timescale-service:5432/market_data" | base64)
  REDIS_URL: $(echo -n "redis://:${REDIS_PASS}@redis-service:6379/0" | base64)
  RABBITMQ_URL: $(echo -n "amqp://cryptobot:${RABBITMQ_PASS}@rabbitmq-service:5672/cryptobot" | base64)
EOF

# Store passwords securely (optional - use password manager)
cat > .secrets.env << EOF
POSTGRES_PASSWORD=${POSTGRES_PASS}
TIMESCALE_PASSWORD=${TIMESCALE_PASS}
REDIS_PASSWORD=${REDIS_PASS}
RABBITMQ_PASSWORD=${RABBITMQ_PASS}
EOF

chmod 600 .secrets.env
```

#### Scripted Secret Generation (API + Bybit)

```bash
# Generate JWT secret
JWT_SECRET=$(openssl rand -base64 32)

# Get external API keys (from your accounts)
TELEGRAM_BOT_TOKEN="your-telegram-bot-token"
BYBIT_API_KEY="your-bybit-api-key"
BYBIT_API_SECRET="your-bybit-api-secret"

# Create API secrets
cat > secrets/api-secrets-prod.yaml << EOF
apiVersion: v1
kind: Secret
metadata:
  name: api-secrets
  namespace: crypto-bot
type: Opaque
data:
  JWT_SECRET_KEY: $(echo -n "$JWT_SECRET" | base64)
  TELEGRAM_BOT_TOKEN: $(echo -n "$TELEGRAM_BOT_TOKEN" | base64)
EOF

# Create Bybit secrets
cat > secrets/bybit-secrets-prod.yaml << EOF
apiVersion: v1
kind: Secret
metadata:
  name: bybit-secrets
  namespace: crypto-bot
type: Opaque
data:
  BYBIT_API_KEY: $(echo -n "$BYBIT_API_KEY" | base64)
  BYBIT_API_SECRET: $(echo -n "$BYBIT_API_SECRET" | base64)
  BYBIT_NETWORK: $(echo -n "testnet" | base64)  # Change to 'mainnet' for production
EOF
```

### 3. Deploy to Kubernetes

```bash
# Make scripts executable
chmod +x *.sh

# Deploy to development
./apply-all.sh development

# OR deploy to production (with confirmation)
./apply-all.sh production
```

### 4. Verify Deployment

```bash
# Run health check
./verify-deployment.sh --detailed

# Watch pods come up
kubectl get pods -n crypto-bot -w

# Check all resources
kubectl get all -n crypto-bot

# Check logs
kubectl logs -f deployment/api-gateway -n crypto-bot
```

### 5. Access Services

```bash
# API Gateway
kubectl port-forward -n crypto-bot svc/api-gateway-service 8000:8000
# Access: http://localhost:8000/health

# Grafana
kubectl port-forward -n crypto-bot svc/grafana-service 3000:3000
# Access: http://localhost:3000
# Credentials: see .env / grafana secret; rotate the default immediately

# Prometheus
kubectl port-forward -n crypto-bot svc/prometheus-service 9090:9090
# Access: http://localhost:9090
```

## 🏗️ Architecture

### Deployment Topology

```
┌─────────────────────────────────────────────────────────────┐
│                         Ingress Layer                        │
│  ┌──────────────────┐              ┌──────────────────┐    │
│  │ API Gateway      │              │ RabbitMQ Mgmt   │    │
│  │ Ingress          │              │ Ingress         │    │
│  └──────────────────┘              └──────────────────┘    │
└────────────────────┬──────────────────────────┬─────────────┘
                     │                          │
┌────────────────────▼──────────────────────────▼─────────────┐
│                    Service Layer (ClusterIP)                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ API Gateway │  │   Trading   │  │  Portfolio  │        │
│  │ (LoadBalancer) │   Engine    │  │   Manager   │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ Technical   │  │   Bybit     │  │   Market    │        │
│  │  Analysis   │  │  Connector  │  │    Data     │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │ Notification│  │  ML Predict │  │    Risk     │        │
│  │   Service   │  │   Service   │  │   Metrics   │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
│  ┌─────────────┐                                           │
│  │ Sentiment   │                                           │
│  │  Analysis   │                                           │
│  └─────────────┘                                           │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   Data Layer (StatefulSets)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  PostgreSQL  │  │ TimescaleDB  │  │    Redis     │     │
│  │ (StatefulSet)│  │(StatefulSet) │  │ (Deployment) │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│  ┌──────────────┐                                          │
│  │  RabbitMQ    │                                          │
│  │(StatefulSet) │                                          │
│  └──────────────┘                                          │
└─────────────────────────────────────────────────────────────┘
```

### Resource Allocation

| Component | Replicas | CPU Request | CPU Limit | Memory Request | Memory Limit |
|-----------|----------|-------------|-----------|----------------|--------------|
| API Gateway | 3-10 | 2 | 4 | 1Gi | 2Gi |
| Trading Engine | 2-8 | 2 | 4 | 1Gi | 2Gi |
| Portfolio Manager | 2 | 1 | 2 | 512Mi | 1Gi |
| Technical Analysis | 2 | 2 | 4 | 1Gi | 2Gi |
| Bybit Connector | 2 | 1 | 2 | 512Mi | 1Gi |
| Market Data Service | 2 | 1 | 2 | 512Mi | 1Gi |
| ML Prediction | 2-6 | 4 | 8 | 2Gi | 4Gi |
| PostgreSQL | 1 | 1 | 2 | 2Gi | 4Gi |
| TimescaleDB | 1 | 2 | 4 | 2Gi | 4Gi |
| Redis | 1-2 | 500m | 1 | 256Mi | 512Mi |
| RabbitMQ | 1-3 | 500m | 1 | 512Mi | 1Gi |

## 📁 Directory Structure

```
infrastructure/kubernetes/
├── namespaces/
│   └── crypto-bot-namespace.yaml        # Namespace, ResourceQuota, LimitRange
├── configmaps/
│   ├── app-config.yaml                  # Application configuration
│   └── monitoring-config.yaml           # Prometheus & Grafana config
├── secrets/
│   ├── db-secrets.yaml                  # Database credentials (template)
│   ├── api-secrets.yaml                 # API keys (template)
│   └── bybit-secrets.yaml               # Bybit API credentials (template)
├── storage/
│   ├── postgres-pvc.yaml                # PostgreSQL storage (10Gi)
│   ├── timescale-pvc.yaml               # TimescaleDB storage (50Gi)
│   ├── redis-pvc.yaml                   # Redis storage (5Gi)
│   └── rabbitmq-pvc.yaml                # RabbitMQ storage (5Gi)
├── databases/
│   ├── postgres-statefulset.yaml        # PostgreSQL deployment
│   ├── postgres-service.yaml            # PostgreSQL service
│   ├── timescale-statefulset.yaml       # TimescaleDB deployment
│   ├── timescale-service.yaml           # TimescaleDB service
│   ├── redis-deployment.yaml            # Redis deployment
│   ├── redis-service.yaml               # Redis service
│   ├── rabbitmq-statefulset.yaml        # RabbitMQ deployment
│   └── rabbitmq-service.yaml            # RabbitMQ service
├── services/
│   ├── api-gateway-deployment.yaml      # API Gateway deployment
│   ├── api-gateway-service.yaml         # API Gateway service
│   └── ... (similar for all 10 microservices)
├── ingress/
│   ├── api-gateway-ingress.yaml         # External API access
│   └── rabbitmq-ingress.yaml            # RabbitMQ management UI
├── monitoring/
│   ├── prometheus-deployment.yaml       # Prometheus deployment
│   ├── prometheus-service.yaml          # Prometheus service
│   ├── grafana-deployment.yaml          # Grafana deployment
│   └── grafana-service.yaml             # Grafana service
├── autoscaling/
│   ├── api-gateway-hpa.yaml             # API Gateway HPA (3-10 replicas)
│   ├── trading-engine-hpa.yaml          # Trading Engine HPA (2-8 replicas)
│   └── ml-prediction-hpa.yaml           # ML Service HPA (2-6 replicas)
├── kustomization/
│   ├── base/
│   │   └── kustomization.yaml           # Base kustomization
│   └── overlays/
│       ├── development/
│       │   └── kustomization.yaml       # Development overrides
│       └── production/
│           └── kustomization.yaml       # Production overrides
├── apply-all.sh                         # Deploy all resources
├── delete-all.sh                        # Delete all resources
├── verify-deployment.sh                 # Health check script
└── README.md                            # This file
```

## ⚙️ Configuration

### Environment Variables

All configuration is managed through ConfigMaps and Secrets:

**ConfigMap: app-config**
- `ENVIRONMENT`: development | production
- `LOG_LEVEL`: DEBUG | INFO | WARNING | ERROR
- `TRADING_MODE`: paper | live
- Database connection strings (non-sensitive parts)
- Service endpoints (internal DNS)
- Trading parameters (position sizes, limits)

**Secret: db-secrets**
- Database passwords
- Connection URLs with credentials

**Secret: api-secrets**
- JWT secret keys
- Service authentication tokens
- External API keys (Telegram, email, etc.)

**Secret: bybit-secrets**
- Bybit API key and secret
- Testnet vs production configuration

### Environment-Specific Settings

#### Development
- DEBUG logging
- Paper trading mode
- Bybit testnet
- Reduced replica counts (1-2)
- Relaxed resource limits

#### Production
- INFO logging
- Paper trading (initially - switch to live carefully!)
- Bybit mainnet (when ready)
- High replica counts (2-10)
- Strict resource limits
- Auto-scaling enabled
- Monitoring and alerting

### Feature Flags

Located in `configmaps/app-config.yaml`. The 2025-11-23 guide shipped these as:

```yaml
ENABLE_ML_PREDICTIONS: "true"    # STALE — see note below
ENABLE_SENTIMENT_ANALYSIS: "true" # STALE — see note below
ENABLE_NOTIFICATIONS: "true"
ENABLE_AUTO_TRADING: "false"  # IMPORTANT: Enable only when ready!
```

> ⚠️ Contradiction date-stamped 2026-07-30: since 2026-05 the project defaults are `ENABLE_ML_PREDICTIONS=false` and `ENABLE_SENTIMENT_ANALYSIS=false` (ML gated off pending rebuild; sentiment removed from the signal pipeline). In the compose stack, sentiment-analysis-service sits behind the `analytics` profile and ml-prediction-service behind the `ml` profile. Mirror those defaults in any K8s ConfigMap before deploying.

### Customizing Configuration

1. **Development Environment**:
   ```bash
   # Edit development overlay
   vim kustomization/overlays/development/kustomization.yaml

   # Deploy with development settings
   ./apply-all.sh development
   ```

2. **Production Environment**:
   ```bash
   # Edit production overlay
   vim kustomization/overlays/production/kustomization.yaml

   # Create production secrets
   cp secrets/db-secrets.yaml secrets/db-secrets-prod.yaml
   # Edit with real values

   # Deploy to production
   ./apply-all.sh production
   ```

### Updating Configuration at Runtime

```bash
# Edit ConfigMap
kubectl edit configmap app-config -n crypto-bot

# Or update from file
kubectl apply -f configmaps/app-config.yaml

# Restart pods to pick up changes
kubectl rollout restart deployment -n crypto-bot
```

### Storage Classes

Default storage class is `standard`. Update for your cloud provider:

**AWS EKS**:
```yaml
storageClassName: gp3  # or gp2, io2
```

**GCP GKE**:
```yaml
storageClassName: pd-ssd  # or pd-standard
```

**Azure AKS**:
```yaml
storageClassName: managed-premium  # or managed-standard
```

Storage class helpers:

```bash
# Check available storage classes
kubectl get storageclass

# Set default storage class (example for AWS)
kubectl patch storageclass gp3 -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'

# Update PVCs if needed
sed -i 's/storageClassName: standard/storageClassName: gp3/g' storage/*.yaml
```

## 📦 Deployment

### Standard Deployment

```bash
# 1. Deploy everything
./apply-all.sh development

# 2. Wait for pods to be ready
kubectl wait --for=condition=ready pod -l app=crypto-trading-bot -n crypto-bot --timeout=300s

# 3. Verify health
./verify-deployment.sh
```

### Using Kustomize

```bash
# Deploy development environment
kubectl apply -k kustomization/overlays/development

# Deploy production environment
kubectl apply -k kustomization/overlays/production

# Preview changes without applying
kubectl kustomize kustomization/overlays/production
```

### Manual Deployment (Fine-grained Control)

```bash
# 1. Create namespace
kubectl apply -f namespaces/crypto-bot-namespace.yaml

# 2. Create configmaps
kubectl apply -f configmaps/app-config.yaml
kubectl apply -f configmaps/monitoring-config.yaml

# 3. Create secrets (use prod versions in production)
kubectl apply -f secrets/db-secrets-prod.yaml
kubectl apply -f secrets/api-secrets-prod.yaml
kubectl apply -f secrets/bybit-secrets-prod.yaml

# 4. Create storage
kubectl apply -f storage/

# 5. Wait for PVCs to be bound
kubectl wait --for=condition=bound pvc --all -n crypto-bot --timeout=120s

# 6. Deploy databases
kubectl apply -f databases/

# 7. Wait for databases to be ready
kubectl wait --for=condition=ready pod -l component=database -n crypto-bot --timeout=300s

# 8. Deploy microservices
kubectl apply -f services/

# 9. Wait for services to be ready
kubectl wait --for=condition=ready pod -l component=microservice -n crypto-bot --timeout=300s

# 10. Setup ingress
kubectl apply -f ingress/

# 11. Deploy monitoring
kubectl apply -f monitoring/

# 12. Enable autoscaling
kubectl apply -f autoscaling/
```

### Post-Deployment Verification

```bash
# Comprehensive health check
./verify-deployment.sh --detailed

# Check specific components
kubectl get pods -n crypto-bot
kubectl get svc -n crypto-bot
kubectl get pvc -n crypto-bot
kubectl get ingress -n crypto-bot
kubectl get hpa -n crypto-bot

# Test API Gateway
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -n crypto-bot -- \
  curl http://api-gateway-service:8000/health

# Test database connections
kubectl run -it --rm debug --image=postgres:15-alpine --restart=Never -n crypto-bot -- \
  psql -h postgres-service -U cryptobot -d cryptobot -c "SELECT 1"

# Test Redis
kubectl run -it --rm debug --image=redis:7-alpine --restart=Never -n crypto-bot -- \
  redis-cli -h redis-service ping
```

## 📊 Monitoring

> For the full monitoring/alerting stack documentation, see `infrastructure/monitoring/README.md` and the living guides in `docs/operations/` (`MONITORING_GUIDE.md`, `ALERTING_GUIDE.md`, `ALERT_RUNBOOKS.md`).

### Access Prometheus

```bash
# Port forward to Prometheus
kubectl port-forward -n crypto-bot svc/prometheus-service 9090:9090

# Open in browser: http://localhost:9090
```

### Access Grafana

```bash
# Port forward to Grafana
kubectl port-forward -n crypto-bot svc/grafana-service 3000:3000

# Open in browser: http://localhost:3000
# Credentials: see .env / grafana secret; rotate the default immediately
```

### Key Metrics to Monitor

1. **Service Health**
   - Pod status and restarts
   - Request latency (p50, p95, p99)
   - Error rates

2. **Trading Metrics**
   - Active positions
   - P&L (realized and unrealized)
   - Trade execution latency
   - Order fill rates

3. **Resource Usage**
   - CPU utilization per service
   - Memory usage
   - Disk I/O
   - Network throughput

4. **Database Metrics**
   - Query performance
   - Connection pool usage
   - Replication lag (if applicable)

### Alerts Configuration

Pre-configured alerts in `configmaps/monitoring-config.yaml`:
- High CPU usage (>80%)
- High memory usage (>90%)
- Service down
- High error rate (>5%)
- Trading engine stopped
- Position loss threshold (-5%)

### View Metrics

```bash
# Pod resource usage
kubectl top pods -n crypto-bot

# Node resource usage
kubectl top nodes

# Watch pod status
kubectl get pods -n crypto-bot -w
```

### Logs

```bash
# View logs for a specific pod
kubectl logs -f <pod-name> -n crypto-bot

# View logs for a deployment
kubectl logs -f deployment/api-gateway -n crypto-bot

# View logs for all pods with a label
kubectl logs -f -l service=trading-engine -n crypto-bot

# View last 100 lines
kubectl logs --tail=100 <pod-name> -n crypto-bot

# View logs from last hour
kubectl logs --since=1h <pod-name> -n crypto-bot

# Database logs
kubectl logs -f statefulset/postgres -n crypto-bot

# All services
kubectl logs -f -l app=crypto-trading-bot -n crypto-bot --max-log-requests=20
```

## 🔄 Scaling

### Manual Scaling

```bash
# Scale API Gateway to 5 replicas
kubectl scale deployment api-gateway -n crypto-bot --replicas=5

# Scale Trading Engine
kubectl scale deployment trading-engine -n crypto-bot --replicas=3

# Scale several microservices at once
for svc in trading-engine portfolio-manager technical-analysis; do
    kubectl scale deployment $svc -n crypto-bot --replicas=3
done
```

### Auto-scaling

Horizontal Pod Autoscalers (HPA) are configured for:
- **API Gateway**: 3-10 replicas (70% CPU target)
- **Trading Engine**: 2-8 replicas (70% CPU target)
- **ML Prediction**: 2-6 replicas (75% CPU target)

```bash
# View HPA status
kubectl get hpa -n crypto-bot

# Describe HPA
kubectl describe hpa api-gateway-hpa -n crypto-bot

# Update HPA
kubectl edit hpa api-gateway-hpa -n crypto-bot

# Example: Change max replicas
kubectl patch hpa api-gateway-hpa -n crypto-bot -p '{"spec":{"maxReplicas":15}}'
```

### Cluster Auto-scaling

For cloud providers, enable cluster autoscaler:

**AWS EKS**:
```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/autoscaler/master/cluster-autoscaler/cloudprovider/aws/examples/cluster-autoscaler-autodiscover.yaml

# Scale node group directly
eksctl scale nodegroup --cluster=crypto-bot-cluster --name=standard-workers --nodes=5
```

**GCP GKE**:
```bash
gcloud container clusters update CLUSTER_NAME --enable-autoscaling --min-nodes=3 --max-nodes=10

# Resize directly
gcloud container clusters resize crypto-bot-cluster --num-nodes=5 --zone=us-central1-a
```

**Azure AKS**:
```bash
az aks scale --resource-group crypto-bot-rg --name crypto-bot-cluster --node-count 5
```

## 🔧 Troubleshooting

### Common Issues

#### 1. Pods Stuck in Pending

```bash
# Check events
kubectl get events -n crypto-bot --sort-by='.lastTimestamp'

# Describe pod
kubectl describe pod <pod-name> -n crypto-bot

# Common causes:
# - Insufficient resources
# - PVC not bound
# - Image pull errors
```

#### 2. Pods in CrashLoopBackOff

```bash
# Check pod logs (previous container)
kubectl logs <pod-name> -n crypto-bot --previous

# Describe pod for events
kubectl describe pod <pod-name> -n crypto-bot

# Common causes:
# - Database connection failure → Check secrets and database readiness
# - Missing environment variables → Check configmaps
# - Resource limits too low → Adjust in deployment manifest
```

#### 3. PVC Not Bound

```bash
# Check PVC status
kubectl get pvc -n crypto-bot

# Check storage class
kubectl get storageclass

# Check events
kubectl describe pvc <pvc-name> -n crypto-bot

# Solutions:
# - Verify storage class exists: kubectl get sc
# - Check available storage: kubectl get pv
# - Ensure storage class supports dynamic provisioning
```

#### 4. Image Pull Errors

```bash
# Check pod status
kubectl describe pod <pod-name> -n crypto-bot

# Common causes:
# - Image doesn't exist
# - Wrong image tag
# - Registry authentication required

# Solution: Verify image exists and create imagePullSecrets if needed
kubectl create secret docker-registry regcred \
  --docker-server=<registry> \
  --docker-username=<username> \
  --docker-password=<password>
```

#### 5. Database Connection Failures

```bash
# Check database pod
kubectl logs <postgres-pod> -n crypto-bot

# Test connection from another pod
kubectl run -it --rm debug --image=postgres:15-alpine --restart=Never -n crypto-bot -- \
  psql -h postgres-service -U cryptobot -d cryptobot

# Check secrets
kubectl get secret db-secrets -n crypto-bot -o yaml
```

#### 6. Service Not Accessible

```bash
# Check service endpoints
kubectl get endpoints -n crypto-bot

# Test service connectivity
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -n crypto-bot -- \
  curl http://api-gateway-service:8000/health

# Check service selector
kubectl describe svc api-gateway-service -n crypto-bot
```

#### 7. Ingress Not Working

```bash
# Check ingress controller
kubectl get pods -n ingress-nginx

# Check ingress configuration
kubectl describe ingress api-gateway-ingress -n crypto-bot

# Test internal connectivity first
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -n crypto-bot -- \
  curl http://api-gateway-service:8000/health
```

### Debug Commands

```bash
# Get all resources
kubectl get all -n crypto-bot

# Get events
kubectl get events -n crypto-bot --sort-by='.lastTimestamp' | tail -20

# Interactive debug pod (network tooling)
kubectl run -it --rm debug --image=nicolaka/netshoot --restart=Never -n crypto-bot -- /bin/bash

# Execute command in pod
kubectl exec -it <pod-name> -n crypto-bot -- /bin/sh

# Copy files from pod
kubectl cp crypto-bot/<pod-name>:/path/to/file ./local-file

# View resource usage
kubectl describe resourcequota -n crypto-bot
kubectl describe limitrange -n crypto-bot
```

### Emergency Procedures

**Trading Engine Failure:**
```bash
# 1. Check status
kubectl get pods -n crypto-bot -l service=trading-engine

# 2. View logs
kubectl logs -f deployment/trading-engine -n crypto-bot --tail=100

# 3. Restart if needed
kubectl rollout restart deployment/trading-engine -n crypto-bot
```

**Database Connection Issues:**
```bash
# 1. Verify database pods
kubectl get pods -n crypto-bot -l component=database

# 2. Test connectivity
kubectl run -it --rm debug --image=postgres:15-alpine --restart=Never -n crypto-bot -- \
  psql -h postgres-service -U cryptobot -d cryptobot

# 3. Check secrets
kubectl get secret db-secrets -n crypto-bot -o yaml
```

## 🔄 Update and Rollback

### Rolling Update

```bash
# Update image version
kubectl set image deployment/api-gateway api-gateway=crypto-bot/api-gateway:v1.1.0 -n crypto-bot

# Monitor rollout
kubectl rollout status deployment/api-gateway -n crypto-bot

# Pause rollout (if issues)
kubectl rollout pause deployment/api-gateway -n crypto-bot

# Resume rollout
kubectl rollout resume deployment/api-gateway -n crypto-bot
```

### Rollback

```bash
# View rollout history
kubectl rollout history deployment/api-gateway -n crypto-bot

# Rollback to previous version
kubectl rollout undo deployment/api-gateway -n crypto-bot

# Rollback to specific revision
kubectl rollout undo deployment/api-gateway -n crypto-bot --to-revision=2
```

## 💾 Backup and Recovery

### Database Backups

#### PostgreSQL Backup

```bash
# Create backup
kubectl exec -n crypto-bot <postgres-pod> -- \
  pg_dump -U cryptobot cryptobot > backup-$(date +%Y%m%d).sql

# Restore from backup
kubectl exec -i -n crypto-bot <postgres-pod> -- \
  psql -U cryptobot cryptobot < backup-20251123.sql
```

#### TimescaleDB Backup

```bash
# Create backup
kubectl exec -n crypto-bot <timescale-pod> -- \
  pg_dump -U cryptobot market_data > timescale-backup-$(date +%Y%m%d).sql

# Restore from backup
kubectl exec -i -n crypto-bot <timescale-pod> -- \
  psql -U cryptobot market_data < timescale-backup-20251123.sql
```

#### Automated Backup Script

```bash
#!/bin/bash
# backup-databases.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups"

# PostgreSQL backup
kubectl exec -n crypto-bot statefulset/postgres -- \
  pg_dump -U cryptobot cryptobot | \
  gzip > ${BACKUP_DIR}/postgres_${DATE}.sql.gz

# TimescaleDB backup
kubectl exec -n crypto-bot statefulset/timescale -- \
  pg_dump -U cryptobot market_data | \
  gzip > ${BACKUP_DIR}/timescale_${DATE}.sql.gz

# Upload to cloud storage (example: AWS S3)
aws s3 cp ${BACKUP_DIR}/ s3://crypto-bot-backups/$(date +%Y%m%d)/ --recursive

# Clean up old backups (keep last 30 days)
find ${BACKUP_DIR} -type f -mtime +30 -delete
```

#### Scheduled Backups (CronJob)

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: database-backup
  namespace: crypto-bot
spec:
  schedule: "0 2 * * *"  # Daily at 2 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: postgres:15-alpine
            command: ["/bin/bash", "/scripts/backup-databases.sh"]
            volumeMounts:
            - name: backup-scripts
              mountPath: /scripts
          volumes:
          - name: backup-scripts
            configMap:
              name: backup-scripts
          restartPolicy: OnFailure
```

#### Disaster Recovery (Restore from gzip)

```bash
# Restore PostgreSQL
gunzip < postgres_20251123_020000.sql.gz | \
  kubectl exec -i -n crypto-bot statefulset/postgres -- \
  psql -U cryptobot cryptobot

# Restore TimescaleDB
gunzip < timescale_20251123_020000.sql.gz | \
  kubectl exec -i -n crypto-bot statefulset/timescale -- \
  psql -U cryptobot market_data
```

### Volume Snapshots

```bash
# Create snapshot (if supported by storage class)
kubectl create -f - <<EOF
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: postgres-snapshot
  namespace: crypto-bot
spec:
  volumeSnapshotClassName: csi-snapclass
  source:
    persistentVolumeClaimName: postgres-pvc
EOF

# Restore from snapshot
kubectl create -f - <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-pvc-restored
  namespace: crypto-bot
spec:
  dataSource:
    name: postgres-snapshot
    kind: VolumeSnapshot
    apiGroup: snapshot.storage.k8s.io
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
EOF
```

### Automated Backups

Consider using:
- **Velero**: Kubernetes backup and restore
- **Kasten K10**: Data management platform
- Cloud-native backup solutions (AWS Backup, GCP Backup, Azure Backup)

## 🔒 Security Best Practices

### 1. Update Secrets

**NEVER** use default/template secrets in production:

```bash
# Generate strong passwords
openssl rand -base64 32

# Base64 encode for Kubernetes
echo -n "your-strong-password" | base64

# Update secrets
kubectl edit secret db-secrets -n crypto-bot
```

### 2. Network Policies

Create network policies to restrict traffic:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: api-gateway-policy
  namespace: crypto-bot
spec:
  podSelector:
    matchLabels:
      service: api-gateway
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: ingress-nginx
  egress:
  - to:
    - podSelector:
        matchLabels:
          component: database
```

Default-deny policy:

```bash
kubectl apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: crypto-bot
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
EOF
```

### 3. RBAC

Configure Role-Based Access Control:

```bash
# Create service account
kubectl create serviceaccount crypto-bot-sa -n crypto-bot

# Create role
kubectl create role pod-reader --verb=get,list,watch --resource=pods -n crypto-bot

# Create role binding
kubectl create rolebinding read-pods \
  --role=pod-reader \
  --serviceaccount=crypto-bot:crypto-bot-sa \
  -n crypto-bot
```

### 4. TLS Certificates

Use cert-manager for automated TLS:

```bash
# Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# Create ClusterIssuer
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: your-email@example.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
EOF
```

### 5. Pod Security Standards

Enable pod security admission:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: crypto-bot
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
```

### 6. Image Security

- Use official base images
- Scan images for vulnerabilities
- Use specific tags (not `latest`)
- Enable image pull policies

```bash
# Scan image with Trivy
trivy image crypto-bot/api-gateway:v1.0.0

# Scan running images for high/critical vulnerabilities
trivy image --severity HIGH,CRITICAL crypto-bot/api-gateway:v1.0.0

# Check for vulnerability reports
kubectl get vulnerabilityreports -n crypto-bot

# Update imagePullPolicy
kubectl patch deployment api-gateway -n crypto-bot \
  -p '{"spec":{"template":{"spec":{"containers":[{"name":"api-gateway","imagePullPolicy":"Always"}]}}}}'
```

### Security Checklist (Pre-Production)

- [ ] All secrets use strong, randomly generated passwords
- [ ] Secrets are not committed to version control
- [ ] TLS certificates configured for ingress
- [ ] Network policies implemented
- [ ] RBAC roles and bindings configured
- [ ] Pod Security Standards enforced
- [ ] Image scanning enabled
- [ ] Regular security updates scheduled
- [ ] Backup and disaster recovery tested
- [ ] Monitoring and alerting configured

## ✅ Deployment Checklist

### Pre-Deployment
- [ ] Kubernetes cluster is running and accessible
- [ ] kubectl is configured and working
- [ ] Docker images are built and pushed to registry
- [ ] Secrets are created with real credentials
- [ ] Storage class is configured for cloud provider
- [ ] Monitoring tools are installed (metrics-server)
- [ ] Backup strategy is in place

### Deployment
- [ ] Namespace created successfully
- [ ] ConfigMaps applied
- [ ] Secrets applied (production versions)
- [ ] PVCs created and bound
- [ ] Database pods are running
- [ ] Database initialization completed
- [ ] Microservice pods are running
- [ ] All health checks passing
- [ ] Ingress configured (if using)
- [ ] Monitoring deployed (Prometheus, Grafana)
- [ ] Autoscaling configured (HPA)

### Post-Deployment
- [ ] Health verification script passed
- [ ] All pods are running (kubectl get pods -n crypto-bot)
- [ ] Services are accessible
- [ ] Logs show no critical errors
- [ ] Metrics are being collected
- [ ] Alerts are configured
- [ ] Backup job is scheduled
- [ ] Documentation is updated
- [ ] Team is trained on operations

### Production Readiness
- [ ] TLS certificates installed
- [ ] Network policies enabled
- [ ] RBAC configured
- [ ] Resource quotas set
- [ ] Rate limiting configured
- [ ] Emergency procedures documented
- [ ] Monitoring dashboards created
- [ ] On-call rotation established
- [ ] Disaster recovery tested

## 📚 Additional Resources

- [Kubernetes Official Documentation](https://kubernetes.io/docs/)
- [Kustomize Documentation](https://kustomize.io/)
- [Prometheus Operator](https://github.com/prometheus-operator/prometheus-operator)
- [cert-manager Documentation](https://cert-manager.io/docs/)
- [Velero Backup](https://velero.io/)

## 🆘 Support

For issues or questions:
1. Check troubleshooting section above
2. Review pod logs and events
3. Run health verification script (`./verify-deployment.sh --detailed`)
4. Check events: `kubectl get events -n crypto-bot --sort-by='.lastTimestamp'`

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-11-23 | Initial release - Complete Kubernetes infrastructure (README + DEPLOYMENT_GUIDE) |
| 1.1 | 2026-07-30 | Merged DEPLOYMENT_GUIDE.md into this README; added compose-only posture note; corrected stale port table, feature-flag defaults, dead `/mnt/d/...` paths, and removed printed default credentials |

## 📝 License

Copyright © 2025 Crypto Trading Bot Team
