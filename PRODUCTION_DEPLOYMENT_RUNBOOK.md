# Production Deployment Runbook

## Crypto Trading Bot - Production Deployment Guide

**Version:** 1.0
**Last Updated:** 2025-12-12
**Owner:** DevOps Team
**Review Cycle:** Monthly

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Pre-Deployment Checklist](#pre-deployment-checklist)
4. [Deployment Procedure](#deployment-procedure)
5. [Post-Deployment Validation](#post-deployment-validation)
6. [Rollback Procedures](#rollback-procedures)
7. [Emergency Procedures](#emergency-procedures)
8. [Monitoring and Alerting](#monitoring-and-alerting)
9. [Troubleshooting Guide](#troubleshooting-guide)
10. [Contact Information](#contact-information)

---

## 1. Overview

### System Description

The Crypto Trading Bot is an autonomous trading system consisting of 15+ microservices that:
- Performs real-time market data analysis
- Executes automated trading strategies via Bybit API
- Manages portfolio risk and positions
- Provides monitoring and alerting

### Architecture

```
                              [Ingress/LoadBalancer]
                                       |
                              [API Gateway (3 replicas)]
                                       |
        +------------+--------+--------+--------+------------+
        |            |        |        |        |            |
  [Trading     [Portfolio  [Technical [Market   [Risk      [ML
   Engine]      Manager]    Analysis]  Data]    Metrics]   Prediction]
   (3 rep)      (2 rep)     (2 rep)   (2 rep)   (2 rep)    (2 rep)
        |            |        |        |        |            |
        +------------+--------+--------+--------+------------+
                              |
              +---------------+---------------+
              |               |               |
        [PostgreSQL]   [TimescaleDB]    [Redis]    [RabbitMQ]
```

### Service Inventory

| Service | Port | Replicas | Priority |
|---------|------|----------|----------|
| api-gateway | 8000 | 3 | Critical |
| trading-engine | 8001 | 3 | Critical |
| portfolio-manager | 8002 | 2 | Critical |
| technical-analysis | 8003 | 2 | High |
| bybit-connector | 8004 | 2 | Critical |
| market-data-service | 8005 | 2 | High |
| ml-prediction-service | 8007 | 2 | Medium |
| notification-service | 8008 | 2 | Medium |
| risk-metrics-service | 8009 | 2 | High |
| sentiment-analysis | 8010 | 1 | Low |

---

## 2. Prerequisites

### Required Access

- [ ] Kubernetes cluster admin access
- [ ] Container registry push/pull permissions
- [ ] Vault/secrets manager access
- [ ] Bybit API credentials (production)
- [ ] Monitoring dashboard access

### Required Tools

```bash
# Verify all tools are installed
kubectl version --client
helm version
docker version
python3 --version

# Minimum versions
# kubectl: v1.28+
# helm: v3.12+
# docker: 24.0+
# python: 3.10+
```

### Environment Variables

Ensure these are set in your deployment environment:

```bash
export KUBECONFIG=/path/to/production/kubeconfig
export DOCKER_REGISTRY=your-registry.io
export IMAGE_TAG=v2.0.0  # or specific version
```

---

## 3. Pre-Deployment Checklist

### Security Validation

- [ ] Security scan passed: `python scripts/security_scan.py --fail-on HIGH`
- [ ] Security tests passed: `pytest tests/security/ -v`
- [ ] No hardcoded secrets in codebase
- [ ] All secrets properly configured (not templates)
- [ ] Network policies reviewed
- [ ] RBAC configurations verified

### Code Quality

- [ ] All tests passing: `pytest tests/ -v`
- [ ] Code coverage > 80%
- [ ] Static analysis clean
- [ ] Docker images built and scanned
- [ ] Images pushed to registry with version tag

### Infrastructure

- [ ] Kubernetes cluster healthy
- [ ] Sufficient node capacity
- [ ] Storage classes available
- [ ] Ingress controller configured
- [ ] SSL certificates valid

### Staging Validation

- [ ] Staging deployment successful
- [ ] Staging tests passed
- [ ] Performance baseline established
- [ ] No critical bugs in staging

### Approval

- [ ] Change ticket created and approved
- [ ] Stakeholder notification sent
- [ ] On-call team notified
- [ ] Rollback plan reviewed

---

## 4. Deployment Procedure

### Step 1: Prepare Environment

```bash
# Navigate to project directory
cd /path/to/crypto-trading-bot

# Verify cluster connection
kubectl config current-context
kubectl cluster-info

# Verify namespace doesn't exist (for fresh deploy)
kubectl get namespace crypto-bot-prod

# If upgrading, check current state
kubectl get all -n crypto-bot-prod
```

### Step 2: Run Security Validation

```bash
# Run security scan
python scripts/security_scan.py --fail-on HIGH --verbose

# Run security tests
pytest tests/security/ -v --tb=short

# Validate Kubernetes security configs
./infrastructure/kubernetes/security/scripts/validate-security.sh production
```

### Step 3: Prepare Secrets

```bash
# Generate production secrets (first time only)
./scripts/generate-secrets.sh production

# Or copy and configure secrets template
cd infrastructure/production
cp secrets-template.yaml secrets.yaml
# Edit secrets.yaml with real values - DO NOT COMMIT

# Apply secrets
kubectl apply -f secrets.yaml -n crypto-bot-prod
rm secrets.yaml  # Remove after applying
```

### Step 4: Deploy Infrastructure

```bash
# Option A: Full deployment script
cd infrastructure/production
./deploy-production.sh

# Option B: Step-by-step deployment
kubectl apply -f namespace.yaml
kubectl apply -f configmap.yaml
kubectl apply -f storage.yaml
kubectl apply -f databases.yaml

# Wait for databases
kubectl wait --for=condition=ready pod -l component=database -n crypto-bot-prod --timeout=300s
```

### Step 5: Apply Security Configurations

```bash
# Apply security hardening
./infrastructure/kubernetes/security/scripts/apply-security.sh production

# Verify security policies
kubectl get networkpolicies -n crypto-bot-prod
kubectl get podsecuritypolicies
```

### Step 6: Deploy Microservices

```bash
# Deploy all services
kubectl apply -f microservices.yaml -n crypto-bot-prod

# Wait for deployments
kubectl rollout status deployment/api-gateway -n crypto-bot-prod --timeout=300s
kubectl rollout status deployment/trading-engine -n crypto-bot-prod --timeout=300s
kubectl rollout status deployment/portfolio-manager -n crypto-bot-prod --timeout=300s
```

### Step 7: Deploy Monitoring

```bash
# Deploy monitoring stack
kubectl apply -f monitoring.yaml -n crypto-bot-prod

# Wait for monitoring
kubectl wait --for=condition=ready pod -l service=prometheus -n crypto-bot-prod --timeout=180s
kubectl wait --for=condition=ready pod -l service=grafana -n crypto-bot-prod --timeout=180s
```

### Step 8: Configure Autoscaling

```bash
# Configure HPAs
kubectl autoscale deployment api-gateway -n crypto-bot-prod --cpu-percent=70 --min=3 --max=10
kubectl autoscale deployment trading-engine -n crypto-bot-prod --cpu-percent=60 --min=3 --max=15

# Verify HPAs
kubectl get hpa -n crypto-bot-prod
```

---

## 5. Post-Deployment Validation

### Automated Verification

```bash
# Run verification script
./infrastructure/production/verify-production.sh --detailed

# Export results
./infrastructure/production/verify-production.sh --export verification-results.json
```

### Manual Verification

```bash
# Check all pods are running
kubectl get pods -n crypto-bot-prod -o wide

# Check all services have endpoints
kubectl get endpoints -n crypto-bot-prod

# Check resource utilization
kubectl top pods -n crypto-bot-prod

# Check for events/issues
kubectl get events -n crypto-bot-prod --sort-by='.lastTimestamp' | tail -20
```

### Health Endpoint Checks

```bash
# Port forward API Gateway
kubectl port-forward -n crypto-bot-prod svc/api-gateway-service 8000:8000 &

# Check health endpoints
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/api/v1/trading/status

# Kill port forward
pkill -f "port-forward.*8000"
```

### Functional Validation

1. **API Gateway**
   - [ ] Health endpoint returns 200
   - [ ] Authentication working
   - [ ] Rate limiting active

2. **Trading Engine**
   - [ ] Connected to Bybit
   - [ ] Emergency stop accessible
   - [ ] Order validation working

3. **Portfolio Manager**
   - [ ] Balance fetch working
   - [ ] Position tracking active
   - [ ] PnL calculation correct

4. **Monitoring**
   - [ ] Prometheus collecting metrics
   - [ ] Grafana dashboards loading
   - [ ] Alerts configured

---

## 6. Rollback Procedures

### Automatic Rollback

```bash
# Rollback all deployments to previous revision
./infrastructure/production/deploy-production.sh --rollback
```

### Manual Rollback

```bash
# Rollback specific deployment
kubectl rollout undo deployment/trading-engine -n crypto-bot-prod

# Rollback to specific revision
kubectl rollout undo deployment/trading-engine -n crypto-bot-prod --to-revision=2

# Check rollout history
kubectl rollout history deployment/trading-engine -n crypto-bot-prod
```

### Database Rollback

```bash
# Connect to postgres
kubectl exec -it postgres-0 -n crypto-bot-prod -- psql -U cryptobot_prod

# List backups (if using backup solution)
# Restore from backup following backup tool procedures
```

### Full Environment Rollback

```bash
# Scale down all services
kubectl scale deployment --all --replicas=0 -n crypto-bot-prod

# Delete and recreate from previous known-good state
kubectl delete namespace crypto-bot-prod
kubectl apply -f infrastructure/production/ --previous-version
```

---

## 7. Emergency Procedures

### Emergency Stop Trading

```bash
# Via API
curl -X POST http://api-gateway:8000/api/v1/trading/emergency-stop \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Via kubectl
kubectl exec -it $(kubectl get pod -n crypto-bot-prod -l service=trading-engine -o jsonpath='{.items[0].metadata.name}') \
  -n crypto-bot-prod -- curl -X POST http://localhost:8001/api/v1/trading/emergency-stop

# Scale trading engine to 0
kubectl scale deployment/trading-engine --replicas=0 -n crypto-bot-prod
```

### Critical Service Failure

```bash
# 1. Check pod status
kubectl get pods -n crypto-bot-prod | grep -v Running

# 2. Get pod logs
kubectl logs deployment/[failed-service] -n crypto-bot-prod --tail=100

# 3. Describe pod for events
kubectl describe pod [pod-name] -n crypto-bot-prod

# 4. Restart deployment
kubectl rollout restart deployment/[service-name] -n crypto-bot-prod

# 5. If restart fails, rollback
kubectl rollout undo deployment/[service-name] -n crypto-bot-prod
```

### Database Emergency

```bash
# Check database status
kubectl exec -it postgres-0 -n crypto-bot-prod -- pg_isready

# Check database logs
kubectl logs postgres-0 -n crypto-bot-prod --tail=100

# Connect for emergency queries
kubectl exec -it postgres-0 -n crypto-bot-prod -- psql -U cryptobot_prod

# Failover to backup (if configured)
# Follow database-specific failover procedures
```

### Complete System Failure

1. **Activate Incident Response**
   - Page on-call team
   - Open incident bridge
   - Notify stakeholders

2. **Stop All Trading**
   ```bash
   kubectl scale deployment --all --replicas=0 -n crypto-bot-prod
   ```

3. **Preserve Evidence**
   ```bash
   kubectl get all -n crypto-bot-prod -o yaml > incident-state.yaml
   kubectl logs --all-containers --selector=app=crypto-trading-bot -n crypto-bot-prod > incident-logs.txt
   ```

4. **Root Cause Analysis**
   - Review logs
   - Check metrics
   - Review recent changes

5. **Recovery**
   - Fix root cause
   - Test fix in staging
   - Redeploy with fix

---

## 8. Monitoring and Alerting

### Access Monitoring

```bash
# Grafana
kubectl port-forward -n crypto-bot-prod svc/grafana-service 3000:3000
# Open http://localhost:3000

# Prometheus
kubectl port-forward -n crypto-bot-prod svc/prometheus-service 9090:9090
# Open http://localhost:9090

# AlertManager
kubectl port-forward -n crypto-bot-prod svc/alertmanager-service 9093:9093
# Open http://localhost:9093
```

### Key Dashboards

| Dashboard | URL | Purpose |
|-----------|-----|---------|
| Trading Overview | /d/trading | Trading performance |
| System Health | /d/health | Service health |
| Resource Usage | /d/resources | CPU/Memory |
| Alerts | /d/alerts | Active alerts |

### Critical Alerts

| Alert | Severity | Response |
|-------|----------|----------|
| TradingEngineDown | Critical | Immediate investigation |
| EmergencyStopTriggered | Critical | Review and acknowledge |
| HighErrorRate | Critical | Investigate errors |
| DailyLossLimitApproaching | Warning | Monitor closely |
| HighMemoryUsage | Warning | Scale or optimize |
| DatabaseConnectionPoolLow | Warning | Check connections |

### Log Aggregation

```bash
# View trading engine logs
kubectl logs -f deployment/trading-engine -n crypto-bot-prod

# View all service logs
kubectl logs -l app=crypto-trading-bot -n crypto-bot-prod --tail=100

# Filter for errors
kubectl logs deployment/trading-engine -n crypto-bot-prod | grep ERROR
```

---

## 9. Troubleshooting Guide

### Pod Not Starting

**Symptoms:** Pod stuck in Pending, CrashLoopBackOff, or ImagePullBackOff

**Steps:**
```bash
# Check pod status
kubectl describe pod [pod-name] -n crypto-bot-prod

# Common issues:
# - ImagePullBackOff: Check registry credentials, image exists
# - Pending: Check node resources, PVC binding
# - CrashLoopBackOff: Check logs, resource limits
```

### Service Unavailable

**Symptoms:** 503 errors, connection refused

**Steps:**
```bash
# Check endpoints
kubectl get endpoints [service-name] -n crypto-bot-prod

# Check pod health
kubectl get pods -l service=[service-name] -n crypto-bot-prod

# Check network policy
kubectl get networkpolicy -n crypto-bot-prod
```

### High Latency

**Symptoms:** Slow API responses, timeout errors

**Steps:**
```bash
# Check resource usage
kubectl top pods -n crypto-bot-prod

# Check HPA status
kubectl get hpa -n crypto-bot-prod

# Check database connections
kubectl exec -it postgres-0 -n crypto-bot-prod -- psql -c "SELECT count(*) FROM pg_stat_activity"
```

### Trading Not Executing

**Symptoms:** No trades despite signals

**Steps:**
```bash
# Check trading engine status
curl http://localhost:8001/api/v1/trading/status

# Check risk limits
curl http://localhost:8001/api/v1/risk/limits

# Check Bybit connection
curl http://localhost:8004/api/v1/exchange/status

# Review logs
kubectl logs deployment/trading-engine -n crypto-bot-prod | grep -i "trade\|order"
```

---

## 10. Contact Information

### Escalation Path

| Level | Team | Contact | Response Time |
|-------|------|---------|---------------|
| L1 | On-Call Engineer | oncall@company.com | 15 min |
| L2 | Platform Team | platform@company.com | 30 min |
| L3 | Architecture | arch@company.com | 1 hour |

### Key Contacts

| Role | Name | Contact |
|------|------|---------|
| DevOps Lead | [Name] | [email] |
| Platform Lead | [Name] | [email] |
| Trading Lead | [Name] | [email] |

### External Contacts

| Service | Support | Emergency |
|---------|---------|-----------|
| Bybit | support@bybit.com | [hotline] |
| Cloud Provider | [support] | [hotline] |

---

## Appendix A: Command Reference

```bash
# Deployment
./deploy-production.sh                    # Full deployment
./deploy-production.sh --dry-run          # Preview changes
./deploy-production.sh --rollback         # Rollback deployment

# Verification
./verify-production.sh                    # Full verification
./verify-production.sh --quick            # Quick check
./verify-production.sh --detailed         # Detailed output

# Security
python scripts/security_scan.py --fail-on HIGH
./infrastructure/kubernetes/security/scripts/validate-security.sh production

# Monitoring
kubectl port-forward svc/grafana-service 3000:3000 -n crypto-bot-prod
kubectl port-forward svc/prometheus-service 9090:9090 -n crypto-bot-prod

# Logs
kubectl logs -f deployment/[service] -n crypto-bot-prod
kubectl logs --all-containers -l app=crypto-trading-bot -n crypto-bot-prod

# Scaling
kubectl scale deployment/[service] --replicas=N -n crypto-bot-prod
kubectl autoscale deployment/[service] --cpu-percent=70 --min=3 --max=10 -n crypto-bot-prod
```

---

## Appendix B: Configuration Reference

### Resource Requests/Limits

| Service | CPU Request | CPU Limit | Memory Request | Memory Limit |
|---------|-------------|-----------|----------------|--------------|
| api-gateway | 500m | 2 | 512Mi | 2Gi |
| trading-engine | 1 | 4 | 1Gi | 4Gi |
| portfolio-manager | 250m | 1 | 512Mi | 2Gi |
| technical-analysis | 500m | 2 | 1Gi | 4Gi |
| ml-prediction | 1 | 4 | 2Gi | 8Gi |

### Database Connections

| Database | Max Connections | Pool Size |
|----------|-----------------|-----------|
| PostgreSQL | 100 | 20 |
| TimescaleDB | 100 | 20 |
| Redis | 10000 | N/A |

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-12 | DevOps Team | Initial version |

**Next Review Date:** 2026-01-12
