# Kubernetes Deployment for Crypto Trading Bot

## 📋 Table of Contents
- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Directory Structure](#directory-structure)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [Monitoring](#monitoring)
- [Scaling](#scaling)
- [Troubleshooting](#troubleshooting)
- [Backup and Recovery](#backup-and-recovery)
- [Security Best Practices](#security-best-practices)

## 🎯 Overview

This directory contains production-grade Kubernetes manifests for deploying the Crypto Trading Bot microservices architecture. The deployment includes:

- **10 Microservices**: API Gateway, Trading Engine, Portfolio Manager, Technical Analysis, Bybit Connector, Market Data Service, Notification Service, ML Prediction Service, Risk Metrics Service, Sentiment Analysis Service
- **4 Databases**: PostgreSQL (main DB), TimescaleDB (time-series data), Redis (cache), RabbitMQ (message queue)
- **Monitoring Stack**: Prometheus and Grafana
- **Auto-scaling**: Horizontal Pod Autoscalers for critical services
- **Ingress**: External access with TLS termination

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
```

## 🚀 Quick Start

### 1. Build Docker Images

```bash
# Navigate to project root
cd /mnt/d/Bimo_max/crypto-trading-bot

# Build all service images
./infrastructure/scripts/build-all-images.sh

# Tag images for your registry
docker tag crypto-bot/api-gateway:latest your-registry/crypto-bot/api-gateway:v1.0.0
# ... repeat for all services
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

# Check logs
kubectl logs -f deployment/api-gateway -n crypto-bot
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
kubectl apply -f namespaces/

# 2. Create configmaps and secrets
kubectl apply -f configmaps/
kubectl apply -f secrets/

# 3. Create storage
kubectl apply -f storage/

# 4. Deploy databases
kubectl apply -f databases/

# 5. Wait for databases
kubectl wait --for=condition=ready pod -l component=database -n crypto-bot --timeout=120s

# 6. Deploy microservices
kubectl apply -f services/

# 7. Setup ingress
kubectl apply -f ingress/

# 8. Deploy monitoring
kubectl apply -f monitoring/

# 9. Enable autoscaling
kubectl apply -f autoscaling/
```

## 📊 Monitoring

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
# Default credentials: admin/admin (change immediately!)
```

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
```

## 🔄 Scaling

### Manual Scaling

```bash
# Scale API Gateway to 5 replicas
kubectl scale deployment api-gateway -n crypto-bot --replicas=5

# Scale Trading Engine
kubectl scale deployment trading-engine -n crypto-bot --replicas=3
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
```

### Cluster Auto-scaling

For cloud providers, enable cluster autoscaler:

**AWS EKS**:
```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/autoscaler/master/cluster-autoscaler/cloudprovider/aws/examples/cluster-autoscaler-autodiscover.yaml
```

**GCP GKE**:
```bash
gcloud container clusters update CLUSTER_NAME --enable-autoscaling --min-nodes=3 --max-nodes=10
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

#### 2. PVC Not Bound

```bash
# Check PVC status
kubectl get pvc -n crypto-bot

# Check storage class
kubectl get storageclass

# Check events
kubectl describe pvc <pvc-name> -n crypto-bot

# Solution: Ensure storage class supports dynamic provisioning
```

#### 3. Image Pull Errors

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

#### 4. Database Connection Failures

```bash
# Check database pod
kubectl logs <postgres-pod> -n crypto-bot

# Test connection from another pod
kubectl run -it --rm debug --image=postgres:15-alpine --restart=Never -n crypto-bot -- \
  psql -h postgres-service -U cryptobot -d cryptobot

# Check secrets
kubectl get secret db-secrets -n crypto-bot -o yaml
```

#### 5. Service Not Accessible

```bash
# Check service endpoints
kubectl get endpoints -n crypto-bot

# Test service connectivity
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -n crypto-bot -- \
  curl http://api-gateway-service:8000/health

# Check service selector
kubectl describe svc api-gateway-service -n crypto-bot
```

### Debug Commands

```bash
# Get all resources
kubectl get all -n crypto-bot

# Get events
kubectl get events -n crypto-bot --sort-by='.lastTimestamp' | tail -20

# Execute command in pod
kubectl exec -it <pod-name> -n crypto-bot -- /bin/sh

# Copy files from pod
kubectl cp crypto-bot/<pod-name>:/path/to/file ./local-file

# View resource usage
kubectl describe resourcequota -n crypto-bot
kubectl describe limitrange -n crypto-bot
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

# Update imagePullPolicy
kubectl patch deployment api-gateway -n crypto-bot \
  -p '{"spec":{"template":{"spec":{"containers":[{"name":"api-gateway","imagePullPolicy":"Always"}]}}}}'
```

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
3. Run health verification script
4. Contact DevOps team

## 📝 License

Copyright © 2025 Crypto Trading Bot Team
