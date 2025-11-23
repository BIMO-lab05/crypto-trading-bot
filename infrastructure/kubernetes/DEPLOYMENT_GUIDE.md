# Kubernetes Deployment Guide
## Crypto Trading Bot - Production Deployment

**Version:** 1.0
**Created:** 2025-11-23
**Status:** Ready for Production

---

## 📊 Deployment Summary

### Files Created: 58 Total

| Category | Files | Lines | Purpose |
|----------|-------|-------|---------|
| YAML Manifests | 54 | 4,584 | Kubernetes resource definitions |
| Shell Scripts | 3 | 587 | Deployment automation |
| Documentation | 1 | 781 | Comprehensive README |
| **TOTAL** | **58** | **5,952** | **Complete infrastructure** |

### Infrastructure Components

#### Microservices (10 Services)
1. **api-gateway** - External API interface (Port 8000)
2. **trading-engine** - Core trading logic (Port 8001)
3. **portfolio-manager** - Position tracking (Port 8002)
4. **technical-analysis** - TA indicators (Port 8003)
5. **bybit-connector** - Exchange integration (Port 8004)
6. **market-data-service** - Market data ingestion (Port 8005)
7. **notification-service** - Alerts and notifications (Port 8006)
8. **ml-prediction-service** - ML-based predictions (Port 8007)
9. **risk-metrics-service** - Risk calculations (Port 8008)
10. **sentiment-analysis-service** - Market sentiment (Port 8009)

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

---

## 🚀 Quick Start (5 Minutes)

### Prerequisites Check
```bash
# Verify kubectl
kubectl version --client

# Verify cluster access
kubectl cluster-info

# Verify kustomize (optional)
kustomize version
```

### Step 1: Prepare Secrets
```bash
cd /mnt/d/Bimo_max/crypto-trading-bot/infrastructure/kubernetes

# Copy secret templates
cp secrets/db-secrets.yaml secrets/db-secrets-prod.yaml
cp secrets/api-secrets.yaml secrets/api-secrets-prod.yaml
cp secrets/bybit-secrets.yaml secrets/bybit-secrets-prod.yaml

# Generate base64-encoded values
echo -n "your-postgres-password" | base64
# Output: eW91ci1wb3N0Z3Jlcy1wYXNzd29yZA==

# Edit secrets with real values
vim secrets/db-secrets-prod.yaml
vim secrets/api-secrets-prod.yaml
vim secrets/bybit-secrets-prod.yaml

# IMPORTANT: Add to .gitignore
echo "secrets/*-prod.yaml" >> .gitignore
```

### Step 2: Deploy
```bash
# Make scripts executable
chmod +x *.sh

# Deploy to Kubernetes
./apply-all.sh development  # or 'production'
```

### Step 3: Verify
```bash
# Run health check
./verify-deployment.sh --detailed

# Watch deployment progress
kubectl get pods -n crypto-bot -w

# Check all resources
kubectl get all -n crypto-bot
```

### Step 4: Access Services
```bash
# API Gateway
kubectl port-forward -n crypto-bot svc/api-gateway-service 8000:8000
# Access: http://localhost:8000/health

# Grafana
kubectl port-forward -n crypto-bot svc/grafana-service 3000:3000
# Access: http://localhost:3000 (admin/admin)

# Prometheus
kubectl port-forward -n crypto-bot svc/prometheus-service 9090:9090
# Access: http://localhost:9090
```

---

## 📋 Detailed Deployment Steps

### Phase 1: Pre-Deployment Preparation

#### 1.1 Cluster Setup
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

#### 1.2 Storage Class Configuration
```bash
# Check available storage classes
kubectl get storageclass

# Set default storage class (example for AWS)
kubectl patch storageclass gp3 -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'

# Update PVCs if needed
sed -i 's/storageClassName: standard/storageClassName: gp3/g' storage/*.yaml
```

#### 1.3 Build and Push Docker Images
```bash
# Tag images for your registry
export REGISTRY="your-registry.example.com"
export VERSION="v1.0.0"

# Build and push all images
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

### Phase 2: Secrets Configuration

#### 2.1 Database Secrets
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

#### 2.2 API Secrets
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

### Phase 3: Deployment Execution

#### 3.1 Using apply-all.sh (Recommended)
```bash
# Deploy to development
./apply-all.sh development

# Deploy to production (with confirmation)
./apply-all.sh production
```

#### 3.2 Using Kustomize
```bash
# Preview changes
kubectl kustomize kustomization/overlays/production

# Apply
kubectl apply -k kustomization/overlays/production
```

#### 3.3 Manual Step-by-Step
```bash
# 1. Create namespace
kubectl apply -f namespaces/crypto-bot-namespace.yaml

# 2. Create ConfigMaps
kubectl apply -f configmaps/app-config.yaml
kubectl apply -f configmaps/monitoring-config.yaml

# 3. Create Secrets (use prod versions)
kubectl apply -f secrets/db-secrets-prod.yaml
kubectl apply -f secrets/api-secrets-prod.yaml
kubectl apply -f secrets/bybit-secrets-prod.yaml

# 4. Create PVCs
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

# 10. Deploy ingress
kubectl apply -f ingress/

# 11. Deploy monitoring
kubectl apply -f monitoring/

# 12. Enable autoscaling
kubectl apply -f autoscaling/
```

### Phase 4: Post-Deployment Verification

#### 4.1 Run Health Checks
```bash
# Comprehensive health check
./verify-deployment.sh --detailed

# Check specific components
kubectl get pods -n crypto-bot
kubectl get svc -n crypto-bot
kubectl get pvc -n crypto-bot
kubectl get ingress -n crypto-bot
kubectl get hpa -n crypto-bot
```

#### 4.2 Test Service Connectivity
```bash
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

#### 4.3 View Logs
```bash
# API Gateway logs
kubectl logs -f deployment/api-gateway -n crypto-bot

# Trading Engine logs
kubectl logs -f deployment/trading-engine -n crypto-bot

# Database logs
kubectl logs -f statefulset/postgres -n crypto-bot

# All services
kubectl logs -f -l app=crypto-trading-bot -n crypto-bot --max-log-requests=20
```

---

## 🔧 Configuration Management

### Environment-Specific Settings

#### Development
```bash
# Features enabled in development
- DEBUG logging
- Paper trading mode
- Bybit testnet
- Reduced replica counts (1-2)
- Relaxed resource limits
```

#### Production
```bash
# Features in production
- INFO logging
- Paper trading (initially - switch to live carefully!)
- Bybit mainnet (when ready)
- High replica counts (2-10)
- Strict resource limits
- Auto-scaling enabled
- Monitoring and alerting
```

### Updating Configuration

```bash
# Edit ConfigMap
kubectl edit configmap app-config -n crypto-bot

# Or update from file
kubectl apply -f configmaps/app-config.yaml

# Restart pods to pick up changes
kubectl rollout restart deployment -n crypto-bot
```

### Feature Flags

Located in `configmaps/app-config.yaml`:
```yaml
ENABLE_ML_PREDICTIONS: "true"
ENABLE_SENTIMENT_ANALYSIS: "true"
ENABLE_NOTIFICATIONS: "true"
ENABLE_AUTO_TRADING: "false"  # IMPORTANT: Enable only when ready!
```

---

## 📊 Monitoring and Observability

### Access Monitoring Stack

```bash
# Prometheus
kubectl port-forward -n crypto-bot svc/prometheus-service 9090:9090
# Access: http://localhost:9090

# Grafana
kubectl port-forward -n crypto-bot svc/grafana-service 3000:3000
# Access: http://localhost:3000
# Default credentials: admin/admin (change immediately!)
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

---

## 🔄 Scaling Operations

### Manual Scaling
```bash
# Scale API Gateway
kubectl scale deployment api-gateway -n crypto-bot --replicas=5

# Scale all microservices
for svc in trading-engine portfolio-manager technical-analysis; do
    kubectl scale deployment $svc -n crypto-bot --replicas=3
done
```

### Auto-Scaling Configuration
```bash
# View HPA status
kubectl get hpa -n crypto-bot

# Edit HPA
kubectl edit hpa api-gateway-hpa -n crypto-bot

# Example: Change max replicas
kubectl patch hpa api-gateway-hpa -n crypto-bot -p '{"spec":{"maxReplicas":15}}'
```

### Cluster Scaling (Cloud-Specific)

**AWS EKS:**
```bash
eksctl scale nodegroup --cluster=crypto-bot-cluster --name=standard-workers --nodes=5
```

**GCP GKE:**
```bash
gcloud container clusters resize crypto-bot-cluster --num-nodes=5 --zone=us-central1-a
```

**Azure AKS:**
```bash
az aks scale --resource-group crypto-bot-rg --name crypto-bot-cluster --node-count 5
```

---

## 🛡️ Security Checklist

### Pre-Production Security

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

### Runtime Security

```bash
# Enable network policies
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

# Scan running images
trivy image --severity HIGH,CRITICAL crypto-bot/api-gateway:v1.0.0

# Check for vulnerabilities
kubectl get vulnerabilityreports -n crypto-bot
```

---

## 💾 Backup and Disaster Recovery

### Database Backups

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

### Disaster Recovery

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

---

## 🐛 Troubleshooting

### Common Issues and Solutions

#### Issue 1: Pods in CrashLoopBackOff
```bash
# Check pod logs
kubectl logs <pod-name> -n crypto-bot --previous

# Describe pod for events
kubectl describe pod <pod-name> -n crypto-bot

# Common causes:
# - Database connection failure → Check secrets and database readiness
# - Missing environment variables → Check configmaps
# - Resource limits too low → Adjust in deployment manifest
```

#### Issue 2: PVC Not Binding
```bash
# Check PVC status
kubectl describe pvc <pvc-name> -n crypto-bot

# Solutions:
# - Verify storage class exists: kubectl get sc
# - Check available storage: kubectl get pv
# - Ensure dynamic provisioning is enabled
```

#### Issue 3: Ingress Not Working
```bash
# Check ingress controller
kubectl get pods -n ingress-nginx

# Check ingress configuration
kubectl describe ingress api-gateway-ingress -n crypto-bot

# Test internal connectivity first
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -n crypto-bot -- \
  curl http://api-gateway-service:8000/health
```

### Debug Tools

```bash
# Interactive debug pod
kubectl run -it --rm debug --image=nicolaka/netshoot --restart=Never -n crypto-bot -- /bin/bash

# Copy files from pod
kubectl cp crypto-bot/<pod-name>:/path/to/file ./local-file

# Execute commands in pod
kubectl exec -it <pod-name> -n crypto-bot -- /bin/sh

# View resource quotas
kubectl describe quota -n crypto-bot
kubectl describe limitrange -n crypto-bot
```

---

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

---

## 📞 Support and Contacts

### Getting Help

1. **Documentation**: `/mnt/d/Bimo_max/crypto-trading-bot/infrastructure/kubernetes/README.md`
2. **Health Check**: `./verify-deployment.sh --detailed`
3. **Logs**: `kubectl logs -f deployment/<service-name> -n crypto-bot`
4. **Events**: `kubectl get events -n crypto-bot --sort-by='.lastTimestamp'`

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

---

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

---

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-11-23 | Initial release - Complete Kubernetes infrastructure |

---

**End of Deployment Guide**
