# Crypto Trading Bot - Deployment Runbook
**Last Updated:** 2025-11-14
**Version:** 1.0.0
**Environment:** Development → Production

---

## Table of Contents

1. [Pre-Deployment Checklist](#pre-deployment-checklist)
2. [Development Environment](#development-environment)
3. [Production Deployment](#production-deployment)
4. [Post-Deployment Validation](#post-deployment-validation)
5. [Monitoring & Maintenance](#monitoring--maintenance)
6. [Troubleshooting](#troubleshooting)
7. [Rollback Procedures](#rollback-procedures)
8. [Emergency Procedures](#emergency-procedures)

---

## Pre-Deployment Checklist

### ✅ Infrastructure Requirements

**Hardware:**
- [ ] CPU: 4+ cores (8+ recommended for production)
- [ ] RAM: 16GB minimum (32GB recommended)
- [ ] Storage: 100GB SSD (500GB for long-term data)
- [ ] Network: Stable internet (< 50ms latency to Bybit)

**Software:**
- [ ] Docker 24.0+ installed
- [ ] Docker Compose 2.20+ installed
- [ ] Python 3.12+ (for local development)
- [ ] Git for version control
- [ ] curl, jq for testing

**Services:**
- [ ] Bybit testnet/mainnet account created
- [ ] API keys generated (see [BYBIT_API_SETUP_GUIDE.md](BYBIT_API_SETUP_GUIDE.md))
- [ ] Telegram bot created (optional, see [TELEGRAM_NOTIFICATIONS_SETUP.md](TELEGRAM_NOTIFICATIONS_SETUP.md))
- [ ] Email SMTP configured (optional)

### ✅ Data Requirements

**Before Production:**
- [ ] 90+ days of historical market data collected
- [ ] ML models trained with real data (not mock)
- [ ] Backtests completed with positive results
- [ ] Paper trading validated for 30+ days
- [ ] Strategy performance metrics documented

### ✅ Security Checklist

- [ ] API keys stored in `.env` files only
- [ ] `.env` files added to `.gitignore`
- [ ] 2FA enabled on all exchange accounts
- [ ] IP restrictions configured for API keys
- [ ] Withdrawal permissions DISABLED on bot API keys
- [ ] Database passwords rotated
- [ ] Firewall rules configured
- [ ] SSH keys passwordless login disabled (production)

### ✅ Testing Requirements

- [ ] All 10 services pass health checks
- [ ] End-to-end integration test passes (80%+ pass rate)
- [ ] Unit tests pass (>80% coverage)
- [ ] Load testing completed (if production)
- [ ] Failover testing completed
- [ ] Manual emergency stop tested

---

## Development Environment

### Step 1: Clone Repository

```bash
# Clone repository
git clone https://github.com/your-org/crypto-trading-bot.git
cd crypto-trading-bot

# Verify structure
tree -L 2 -d
```

### Step 2: Configure Environment Variables

```bash
# Create .env files for each service
cp services/bybit-connector/.env.example services/bybit-connector/.env
cp services/market-data-service/.env.example services/market-data-service/.env
cp services/notification-service/.env.example services/notification-service/.env

# Edit configuration (see guides)
# - BYBIT_API_SETUP_GUIDE.md for API keys
# - TELEGRAM_NOTIFICATIONS_SETUP.md for alerts
nano services/bybit-connector/.env
nano services/market-data-service/.env
nano services/notification-service/.env
```

**Key Variables to Set:**

```bash
# Bybit Connector
BYBIT_API_KEY=your_testnet_key
BYBIT_API_SECRET=your_testnet_secret
BYBIT_TESTNET=true

# Market Data
COLLECTION_ENABLED=true
SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT

# Notifications
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### Step 3: Start Development Environment

```bash
# Build all services
docker-compose build

# Start infrastructure (databases, cache, queue)
docker-compose up -d timescaledb redis rabbitmq

# Wait for databases to initialize (30-60 seconds)
sleep 60

# Start all services
docker-compose up -d

# Verify all services are running
docker-compose ps
```

**Expected Output:**
```
NAME                   STATUS    PORTS
crypto-bot-api         Up        0.0.0.0:8000->8000/tcp
crypto-bot-bybit       Up        0.0.0.0:8001->8001/tcp
crypto-bot-market      Up        0.0.0.0:8002->8002/tcp
crypto-bot-portfolio   Up        0.0.0.0:8003->8003/tcp
crypto-bot-technical   Up        0.0.0.0:8004->8004/tcp
crypto-bot-trading     Up        0.0.0.0:8005->8005/tcp
crypto-bot-notify      Up        0.0.0.0:8006->8006/tcp
crypto-bot-ml          Up        0.0.0.0:8007->8007/tcp
crypto-bot-sentiment   Up        0.0.0.0:8008->8008/tcp
crypto-bot-risk        Up        0.0.0.0:8009->8009/tcp
```

### Step 4: Verify Health

```bash
# Run health check script
bash scripts/health_check.sh

# Or check manually
for port in {8000..8009}; do
  echo "Port $port:"
  curl -s http://localhost:$port/health | jq '.status'
done
```

### Step 5: Run Integration Tests

```bash
# Run end-to-end test
cd tests/integration
python3 test_e2e_trading_flow.py

# Expected: 80%+ pass rate
```

---

## Production Deployment

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         LOAD BALANCER                       │
│                     (NGINX / AWS ALB)                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
       ┌───────────────┼───────────────┐
       │               │               │
       ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│  API GW #1  │ │  API GW #2  │ │  API GW #3  │
└──────┬──────┘ └──────┬──────┘ └──────┬──────┘
       │               │               │
       └───────────────┼───────────────┘
                       │
       ┌───────────────┴───────────────┐
       │                               │
       ▼                               ▼
┌─────────────────┐           ┌─────────────────┐
│  MICROSERVICES  │           │   DATA LAYER    │
│   (Kubernetes)  │◄─────────►│ PostgreSQL/Redis│
└─────────────────┘           └─────────────────┘
```

### Option 1: Docker Swarm (Simpler, Recommended for Start)

#### 1.1 Initialize Swarm

```bash
# On manager node
docker swarm init --advertise-addr <MANAGER-IP>

# On worker nodes (optional for HA)
docker swarm join --token <TOKEN> <MANAGER-IP>:2377
```

#### 1.2 Deploy Stack

```bash
# Create production docker-compose-prod.yml
cat > docker-compose-prod.yml << 'EOF'
version: '3.8'

services:
  api-gateway:
    image: crypto-bot/api-gateway:latest
    deploy:
      replicas: 3
      update_config:
        parallelism: 1
        delay: 10s
      restart_policy:
        condition: on-failure
        max_attempts: 3
    environment:
      - ENV=production
    networks:
      - crypto-net

  # ... (similar for other services)

networks:
  crypto-net:
    driver: overlay

volumes:
  postgres-data:
  redis-data:
  model-data:
EOF

# Deploy stack
docker stack deploy -c docker-compose-prod.yml crypto-bot

# Verify deployment
docker service ls
```

### Option 2: Kubernetes (Advanced, High Availability)

#### 2.1 Create Namespace

```bash
kubectl create namespace crypto-trading-bot
kubectl config set-context --current --namespace=crypto-trading-bot
```

#### 2.2 Deploy ConfigMaps & Secrets

```bash
# Create secrets for API keys
kubectl create secret generic bybit-api \
  --from-literal=api-key=<YOUR_KEY> \
  --from-literal=api-secret=<YOUR_SECRET>

kubectl create secret generic telegram \
  --from-literal=bot-token=<BOT_TOKEN> \
  --from-literal=chat-id=<CHAT_ID>

# Create configmap for service endpoints
kubectl create configmap service-config \
  --from-file=config/production.yaml
```

#### 2.3 Deploy Services

```bash
# Apply all Kubernetes manifests
kubectl apply -f infrastructure/kubernetes/

# Verify deployments
kubectl get deployments
kubectl get pods
kubectl get services
```

#### 2.4 Set Up Ingress

```yaml
# infrastructure/kubernetes/ingress.yaml
apiVersion: networking.k8.io/v1
kind: Ingress
metadata:
  name: crypto-bot-ingress
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  rules:
  - host: trading-bot.yourdomain.com
    http:
      paths:
      - path: /api
        pathType: Prefix
        backend:
          service:
            name: api-gateway
            port:
              number: 8000
```

```bash
kubectl apply -f infrastructure/kubernetes/ingress.yaml
```

### Production Environment Variables

**Critical Settings for Production:**

```bash
# Bybit Connector
BYBIT_TESTNET=false  # MAINNET!
BYBIT_BASE_URL=https://api.bybit.com

# Trading Engine
PAPER_TRADING=true   # Start with paper trading
MAX_POSITION_SIZE=1000.0  # $1000 max per trade
DAILY_LOSS_LIMIT=500.0    # Stop if lose $500/day

# Risk Management
ENABLE_CIRCUIT_BREAKER=true
MAX_DRAWDOWN=0.10   # 10% max drawdown
RISK_PER_TRADE=0.02  # 2% risk per trade

# Monitoring
LOG_LEVEL=INFO
ENABLE_METRICS=true
SENTRY_DSN=your_sentry_dsn  # Error tracking

# Notifications
TELEGRAM_ENABLED=true
EMAIL_ENABLED=true
ALERT_ON_DAILY_LIMIT=true
```

---

## Post-Deployment Validation

### Step 1: Health Checks

```bash
# Kubernetes
kubectl get pods
kubectl logs -l app=api-gateway --tail=50

# Docker Swarm
docker service ls
docker service logs crypto-bot_api-gateway --tail=50

# Manual health check
for port in {8000..8009}; do
  curl -s https://your-domain.com:$port/health | jq .
done
```

### Step 2: Run Integration Tests

```bash
# From external host
curl -X POST https://your-domain.com/api/v1/test/e2e

# Or run Python test
python3 tests/integration/test_e2e_trading_flow.py
```

### Step 3: Verify Data Flow

```bash
# Check market data collection
curl https://your-domain.com:8002/api/v1/klines/BTCUSDT?limit=10 | jq .

# Check ML predictions
curl https://your-domain.com:8007/api/v1/predictions/BTCUSDT | jq .

# Check portfolio balance
curl https://your-domain.com:8003/api/v1/balance | jq .
```

### Step 4: Test Notifications

```bash
# Trigger test alert
curl -X POST https://your-domain.com:8006/api/v1/notify/test \
  -H "Content-Type: application/json" \
  -d '{"message": "Production deployment successful"}'

# Verify Telegram message received
```

---

## Monitoring & Maintenance

### Daily Monitoring

**Morning Checks (9:00 AM):**
```bash
# 1. Check all services are running
docker service ls  # or kubectl get pods

# 2. Check logs for errors
docker service logs crypto-bot_trading-engine --since 24h | grep ERROR

# 3. Check portfolio balance
curl https://your-domain.com:8003/api/v1/balance | jq .

# 4. Review yesterday's trades
curl https://your-domain.com:8005/api/v1/trades?since=24h | jq .

# 5. Check ML model performance
curl https://your-domain.com:8007/api/v1/models/stats | jq .
```

**Evening Checks (6:00 PM):**
```bash
# 1. Review P&L for today
curl https://your-domain.com:8003/api/v1/performance/daily | jq .

# 2. Check risk metrics
curl https://your-domain.com:8009/api/v1/portfolio/risk | jq .

# 3. Verify data collection still running
curl https://your-domain.com:8002/api/v1/collection/status | jq .

# 4. Check database size
docker exec crypto-bot-db psql -U crypto_user -c "SELECT pg_size_pretty(pg_database_size('crypto_trading'));"
```

### Weekly Maintenance

**Sunday 12:00 PM (Low Trading Volume):**

1. **Retrain ML Models:**
```bash
for symbol in BTCUSDT ETHUSDT BNBUSDT SOLUSDT XRPUSDT; do
  curl -X POST https://your-domain.com:8007/api/v1/models/train \
    -H "Content-Type: application/json" \
    -d "{\"symbol\":\"$symbol\",\"force_retrain\":true}"
  sleep 60
done
```

2. **Backup Database:**
```bash
# Create backup
docker exec crypto-bot-db pg_dump -U crypto_user crypto_trading > backup_$(date +%Y%m%d).sql

# Upload to S3/cloud storage
aws s3 cp backup_$(date +%Y%m%d).sql s3://your-backup-bucket/
```

3. **Rotate Logs:**
```bash
# Docker logs
docker service logs crypto-bot_trading-engine > logs_$(date +%Y%m%d).log
docker service update --log-opt max-size=50m crypto-bot_trading-engine
```

4. **Review Performance Metrics:**
```bash
# Generate weekly report
curl https://your-domain.com:8003/api/v1/performance/weekly | jq . > weekly_report_$(date +%Y%m%d).json
```

### Monthly Maintenance

**First Sunday of Month:**

1. **Full System Backup**
2. **Review and Update API Keys** (rotate every 90 days)
3. **Security Audit** (check firewall rules, access logs)
4. **Performance Analysis** (review strategy effectiveness)
5. **Update Dependencies** (Docker images, Python packages)

---

## Troubleshooting

### Service Won't Start

**Symptom:** Service stuck in "Starting" state

**Diagnosis:**
```bash
# Check logs
docker logs <container-id> --tail=100

# Check resource usage
docker stats

# Check dependencies
docker-compose ps
```

**Solutions:**
1. Verify database is running and accessible
2. Check environment variables are set correctly
3. Ensure ports are not already in use
4. Rebuild image: `docker-compose build --no-cache <service>`

### No Trades Executing

**Symptom:** Bot running but not placing trades

**Diagnosis:**
```bash
# Check signal generation
curl https://your-domain.com:8004/api/v1/signals/BTCUSDT | jq .

# Check ML predictions
curl https://your-domain.com:8007/api/v1/predictions/BTCUSDT | jq .

# Check trading engine logs
docker logs crypto-bot-trading --tail=100 | grep SIGNAL
```

**Possible Causes:**
1. **Insufficient data** - Need 50+ candles
2. **Overly restrictive thresholds** - Lower signal threshold
3. **Paper trading disabled** - Check `PAPER_TRADING=true`
4. **Risk limits exceeded** - Check daily loss limit not hit
5. **Market hours** - Some pairs have low activity times

**Solutions:**
```bash
# Lower signal threshold temporarily
curl -X POST https://your-domain.com:8005/api/v1/config/update \
  -d '{"signal_threshold": 50}'

# Force signal generation test
curl -X POST https://your-domain.com:8004/api/v1/test/generate-signal \
  -d '{"symbol": "BTCUSDT"}'
```

### High Memory Usage

**Symptom:** Services crashing with OOM errors

**Diagnosis:**
```bash
# Check memory usage
docker stats --no-stream

# Kubernetes
kubectl top pods
```

**Solutions:**
```bash
# Increase memory limits (docker-compose.unified.yml)
mem_limit: 2g
mem_reservation: 1g

# Or Kubernetes (deployment.yaml)
resources:
  limits:
    memory: "2Gi"
  requests:
    memory: "1Gi"

# Restart services
docker-compose restart <service>
```

### Database Connection Errors

**Symptom:** Services can't connect to PostgreSQL

**Diagnosis:**
```bash
# Test database connection
docker exec -it crypto-bot-db psql -U crypto_user -d crypto_trading

# Check database logs
docker logs crypto-bot-db --tail=50
```

**Solutions:**
```bash
# Verify DATABASE_URL in .env
DATABASE_URL=postgresql://crypto_user:crypto_pass@timescaledb:5432/crypto_trading

# Restart database
docker-compose restart timescaledb

# Recreate database (CAUTION: Data loss!)
docker-compose down timescaledb
docker volume rm crypto-trading-bot_postgres-data
docker-compose up -d timescaledb
```

---

## Rollback Procedures

### Quick Rollback (Docker Swarm)

```bash
# Rollback to previous version
docker service rollback crypto-bot_trading-engine

# Or specific version
docker service update --image crypto-bot/trading-engine:v1.0.0 \
  crypto-bot_trading-engine
```

### Quick Rollback (Kubernetes)

```bash
# Rollback deployment
kubectl rollout undo deployment/trading-engine

# Check status
kubectl rollout status deployment/trading-engine

# Rollback to specific revision
kubectl rollout undo deployment/trading-engine --to-revision=2
```

### Full System Rollback

```bash
# 1. Stop new deployments
docker stack rm crypto-bot  # or kubectl scale deployment --replicas=0

# 2. Restore database backup
docker exec -i crypto-bot-db psql -U crypto_user crypto_trading < backup_20251113.sql

# 3. Deploy previous version
git checkout v1.0.0
docker-compose -f docker-compose-prod.yml up -d

# 4. Verify health
bash scripts/health_check.sh
```

---

## Emergency Procedures

### Emergency Stop Trading

**Use when:**
- Market flash crash detected
- Bot behaving erratically
- Unexpected losses accumulating
- API connectivity issues

**Procedure:**

1. **Immediate Stop (via API):**
```bash
curl -X POST https://your-domain.com:8005/api/v1/emergency/stop \
  -H "Authorization: Bearer $EMERGENCY_TOKEN"
```

2. **Force Stop (via Container):**
```bash
# Stop trading engine only
docker stop crypto-bot-trading

# Or Kubernetes
kubectl scale deployment trading-engine --replicas=0
```

3. **Close All Positions (if needed):**
```bash
curl -X POST https://your-domain.com:8005/api/v1/positions/close-all \
  -H "Authorization: Bearer $EMERGENCY_TOKEN" \
  -d '{"force": true}'
```

4. **Verify No Active Trades:**
```bash
curl https://your-domain.com:8003/api/v1/positions | jq .
```

### Recovery from Emergency Stop

```bash
# 1. Analyze what went wrong
docker logs crypto-bot-trading --since 1h > emergency_logs.txt

# 2. Fix issue (update config, rollback, etc.)

# 3. Restart in paper trading mode
curl -X POST https://your-domain.com:8005/api/v1/config/update \
  -d '{"paper_trading": true}'

# 4. Restart trading engine
docker start crypto-bot-trading

# 5. Monitor closely for 24 hours before re-enabling live trading
```

---

## Support & Escalation

**Tier 1 (Self-Service):**
- Check this runbook
- Review `/docs/TROUBLESHOOTING.md`
- Search GitHub issues

**Tier 2 (Team Lead):**
- Critical system failures
- Security incidents
- Data corruption

**Tier 3 (Exchange Support):**
- Bybit API issues: support@bybit.com
- Withdrawal problems
- Account verification

**Emergency Contacts:**
- System Admin: admin@yourcompany.com
- Security Team: security@yourcompany.com
- On-Call Engineer: +1-XXX-XXX-XXXX

---

## Appendix

### Useful Commands

```bash
# View all service logs in real-time
docker-compose logs -f

# Restart single service
docker-compose restart trading-engine

# Rebuild and restart service
docker-compose up -d --build trading-engine

# Enter container shell
docker exec -it crypto-bot-trading bash

# Check resource usage
docker stats

# Prune unused resources
docker system prune -a

# Export logs
docker-compose logs > all_logs.txt
```

### Configuration Files

- `docker-compose.unified.yml` - Canonical local/dev stack (ADR-009; the old `docker-compose.yml` was renamed `docker-compose.legacy.yml.DISABLED`)
- `docker-compose-prod.yml` - Production deployment (generated in the Docker Swarm section above)
- `infrastructure/kubernetes/` - K8s manifests
- `services/*/\.env` - Service configurations
- `scripts/health_check.sh` - Health check script

### Monitoring URLs

- **Grafana:** https://monitoring.yourdomain.com
- **Prometheus:** https://metrics.yourdomain.com
- **Logs:** https://logs.yourdomain.com (Kibana/Grafana Loki)

---

**Last Reviewed:** 2025-11-14
**Next Review:** 2025-12-14
**Owner:** DevOps Team
