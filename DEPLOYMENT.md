# Crypto Trading Bot - Production Deployment Guide

## 📋 Pre-Deployment Checklist

### ✅ Security & Stability Fixes Completed
- [x] All 23 critical fixes applied across 5 microservices
- [x] Division by zero errors fixed (5 indicators)
- [x] CORS security hardening complete
- [x] HTTP client lifecycle management implemented
- [x] Resource leak prevention in place
- [x] Startup safety guaranteed
- [x] API credentials security verified

### 🔐 Environment Configuration

#### Required Environment Variables

Each service requires `.env` file with following variables:

**All Services:**
```bash
# Environment
DEBUG=false
LOG_LEVEL=INFO
ALLOWED_ORIGINS=https://yourdomain.com

# Service Ports
API_GATEWAY_PORT=8000
BYBIT_CONNECTOR_PORT=8002
TECHNICAL_ANALYSIS_PORT=8004
TRADING_ENGINE_PORT=8005
PORTFOLIO_MANAGER_PORT=8006
```

**Bybit Connector:**
```bash
# Bybit API Credentials (NEVER commit these!)
BYBIT_API_KEY=your_api_key_here
BYBIT_API_SECRET=your_api_secret_here
BYBIT_TESTNET=false  # Set to true for testing

# Bybit REST API Configuration
BYBIT_BASE_URL=https://api.bybit.com
BYBIT_WS_URL=wss://stream.bybit.com/v5/public/linear

# Rate Limiting
RATE_LIMIT_CALLS=100
RATE_LIMIT_PERIOD=60
```

---

## 🐳 Docker Deployment

### 1. Build Docker Images

Create `docker-compose.yml` in project root:

```yaml
version: '3.8'

services:
  api-gateway:
    build: ./services/api-gateway
    container_name: crypto-bot-api-gateway
    ports:
      - "8000:8000"
    environment:
      - DEBUG=false
      - LOG_LEVEL=INFO
    volumes:
      - ./services/api-gateway/logs:/app/logs
    restart: unless-stopped
    networks:
      - crypto-bot-network

  bybit-connector:
    build: ./services/bybit-connector
    container_name: crypto-bot-bybit
    ports:
      - "8002:8002"
    env_file:
      - ./services/bybit-connector/.env
    volumes:
      - ./services/bybit-connector/logs:/app/logs
    restart: unless-stopped
    networks:
      - crypto-bot-network

  technical-analysis:
    build: ./services/technical-analysis
    container_name: crypto-bot-ta
    ports:
      - "8004:8004"
    environment:
      - DEBUG=false
    volumes:
      - ./services/technical-analysis/logs:/app/logs
    restart: unless-stopped
    networks:
      - crypto-bot-network

  trading-engine:
    build: ./services/trading-engine
    container_name: crypto-bot-trading
    ports:
      - "8005:8005"
    environment:
      - DEBUG=false
      - MAX_RISK_PER_TRADE=0.02
      - EMERGENCY_STOP_LOSS=0.05
    volumes:
      - ./services/trading-engine/logs:/app/logs
    restart: unless-stopped
    networks:
      - crypto-bot-network
    depends_on:
      - bybit-connector
      - technical-analysis

  portfolio-manager:
    build: ./services/portfolio-manager
    container_name: crypto-bot-portfolio
    ports:
      - "8006:8006"
    environment:
      - DEBUG=false
    volumes:
      - ./services/portfolio-manager/logs:/app/logs
    restart: unless-stopped
    networks:
      - crypto-bot-network
    depends_on:
      - bybit-connector

networks:
  crypto-bot-network:
    driver: bridge

volumes:
  logs:
```

### 2. Create Dockerfiles

**services/*/Dockerfile** (template for all services):
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create logs directory
RUN mkdir -p /app/logs

# Run service
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 3. Deploy Services

```bash
# Build all images
docker-compose build

# Start all services
docker-compose up -d

# Check service health
docker-compose ps

# View logs
docker-compose logs -f
```

### 4. Verify Deployment

```bash
# Check all services are healthy
curl http://localhost:8000/health  # API Gateway
curl http://localhost:8002/health  # Bybit Connector
curl http://localhost:8004/health  # Technical Analysis
curl http://localhost:8005/health  # Trading Engine
curl http://localhost:8006/health  # Portfolio Manager
```

---

## ☁️ Cloud Deployment Options

### Option 1: AWS ECS (Elastic Container Service)

1. **Push images to ECR:**
```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

docker tag crypto-bot-api-gateway:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/crypto-bot-api-gateway:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/crypto-bot-api-gateway:latest
```

2. **Create ECS Task Definitions** for each service
3. **Deploy ECS Service** with load balancer
4. **Configure Auto Scaling** based on CPU/Memory

### Option 2: Kubernetes

1. **Create Kubernetes manifests:**
```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/deployments/
kubectl apply -f k8s/services/
kubectl apply -f k8s/ingress.yaml
```

2. **Set up secrets:**
```bash
kubectl create secret generic bybit-credentials \
  --from-literal=api-key=your_key \
  --from-literal=api-secret=your_secret
```

### Option 3: DigitalOcean App Platform

1. Connect your Git repository
2. Configure each service as a component
3. Set environment variables in UI
4. Deploy with one click

---

## 🔒 Production Security Checklist

- [ ] Use HTTPS only (TLS 1.3)
- [ ] Enable API rate limiting
- [ ] Set up firewall rules (only allow necessary ports)
- [ ] Use secrets management (AWS Secrets Manager / HashiCorp Vault)
- [ ] Enable audit logging for all trades
- [ ] Set up monitoring and alerting
- [ ] Configure backup strategy
- [ ] Enable 2FA for admin access
- [ ] Regular security audits
- [ ] Keep dependencies updated

---

## 📊 Monitoring & Logging

### Recommended Tools

1. **Logging**: ELK Stack (Elasticsearch, Logstash, Kibana)
2. **Metrics**: Prometheus + Grafana
3. **Tracing**: Jaeger or Zipkin
4. **Alerting**: PagerDuty or OpsGenie

### Key Metrics to Monitor

- **System Metrics:**
  - CPU usage per service
  - Memory usage per service
  - Network throughput
  - Disk I/O

- **Application Metrics:**
  - Request latency (p50, p95, p99)
  - Error rate per endpoint
  - Trade execution time
  - API call success rate

- **Business Metrics:**
  - Total trades executed
  - Win/loss ratio
  - Portfolio value
  - Daily P&L

### Log Aggregation

All services write structured JSON logs to `logs/service.log`. Configure log rotation:

```bash
# /etc/logrotate.d/crypto-bot
/path/to/crypto-bot/services/*/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    missingok
    create 0644 app app
}
```

---

## 🔄 Deployment Strategies

### Blue-Green Deployment

1. Deploy new version (green) alongside old (blue)
2. Run smoke tests on green
3. Switch traffic from blue to green
4. Keep blue running for 24h as fallback
5. Decommission blue if no issues

### Canary Deployment

1. Deploy new version to 10% of traffic
2. Monitor for 1 hour
3. If metrics look good, increase to 50%
4. Monitor for 1 hour
5. If still good, roll out to 100%

### Rolling Update (Kubernetes)

```yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxUnavailable: 1
    maxSurge: 1
```

---

## 🚨 Rollback Procedure

If issues are detected after deployment:

### Docker Compose
```bash
# Stop services
docker-compose down

# Restore previous version from git
git checkout <previous-commit>

# Rebuild and start
docker-compose up -d --build
```

### Kubernetes
```bash
# Rollback to previous deployment
kubectl rollout undo deployment/trading-engine

# Check rollback status
kubectl rollout status deployment/trading-engine
```

---

## 🧪 Pre-Production Testing

### 1. Paper Trading Mode

Test in paper trading mode for minimum 2 weeks:

```bash
# Set in Trading Engine .env
PAPER_TRADING_MODE=true
PAPER_TRADING_BALANCE=10000
```

### 2. Integration Tests

```bash
# Run full test suite
pytest tests/integration/ --cov=services --cov-report=html

# Test critical flows
pytest tests/integration/test_order_execution.py -v
pytest tests/integration/test_risk_management.py -v
```

### 3. Load Testing

```bash
# Install k6
brew install k6  # or apt-get install k6

# Run load test
k6 run tests/load/api_gateway_test.js
```

---

## 📦 Backup & Recovery

### Database Backup (if using PostgreSQL)

```bash
# Daily backup script
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump crypto_bot > /backups/crypto_bot_$DATE.sql
gzip /backups/crypto_bot_$DATE.sql

# Keep last 30 days
find /backups/ -name "crypto_bot_*.sql.gz" -mtime +30 -delete
```

### Configuration Backup

```bash
# Backup all .env files and configs
tar -czf config_backup_$(date +%Y%m%d).tar.gz \
  services/*/.env \
  docker-compose.yml \
  k8s/
```

---

## 🎯 Performance Optimization

### 1. Enable HTTP/2

Update Nginx config:
```nginx
listen 443 ssl http2;
```

### 2. Database Connection Pooling

```python
# In each service
from sqlalchemy import create_engine
engine = create_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True
)
```

### 3. Redis Caching

Cache frequent API calls:
```python
@cache(ttl=60)
async def get_ticker(symbol: str):
    return await bybit_client.get_ticker(symbol)
```

---

## 📞 Support & Maintenance

### Daily Tasks
- [ ] Check service health endpoints
- [ ] Review error logs
- [ ] Monitor trading performance
- [ ] Verify API connectivity

### Weekly Tasks
- [ ] Review security logs
- [ ] Check disk space
- [ ] Review and optimize slow queries
- [ ] Update dependencies if needed

### Monthly Tasks
- [ ] Security audit
- [ ] Performance review
- [ ] Backup verification
- [ ] Disaster recovery drill

---

## 🛠️ Troubleshooting

### Service Won't Start
```bash
# Check logs
docker-compose logs <service-name>

# Common issues:
# 1. Port already in use
lsof -i :<port>
kill -9 <PID>

# 2. Missing .env file
cp .env.example .env
# Edit with your values

# 3. Permission issues
chmod -R 755 logs/
```

### High CPU Usage
```bash
# Check which service
docker stats

# Scale down if needed
docker-compose up -d --scale trading-engine=1
```

### Memory Leak
```bash
# Monitor memory
watch -n 1 'docker stats --no-stream'

# Restart leaking service
docker-compose restart <service-name>
```

---

## ✅ Deployment Complete!

After completing all steps, your crypto trading bot should be:

✅ Running securely in production
✅ Fully monitored and logged
✅ Backed up and recoverable
✅ Optimized for performance
✅ Ready for 24/7 operation

**Remember:** Always test thoroughly in paper trading mode before using real funds!

---

**Last Updated:** 2025-11-07
**Version:** 1.0.0
**Status:** Production Ready ✨
