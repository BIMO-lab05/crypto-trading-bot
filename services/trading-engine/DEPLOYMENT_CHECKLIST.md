# Deployment Checklist
**Trading Engine Service - Production Deployment Guide**

**Version:** 1.0
**Last Updated:** 2025-11-10
**Service:** trading-engine
**Port:** 8005

---

## Table of Contents
1. [Pre-Deployment Verification](#pre-deployment-verification)
2. [Environment Setup](#environment-setup)
3. [Database Setup](#database-setup)
4. [Security Configuration](#security-configuration)
5. [Service Deployment](#service-deployment)
6. [Post-Deployment Validation](#post-deployment-validation)
7. [Rollback Procedures](#rollback-procedures)
8. [Monitoring Setup](#monitoring-setup)

---

## Pre-Deployment Verification

### Code Quality Checks
- [ ] All tests passing (`pytest tests/ -v`)
- [ ] Test coverage ≥ 80% (`pytest --cov=app --cov-report=term`)
- [ ] No linting errors (`black . && isort . && flake8`)
- [ ] Type checking passed (`mypy app/`)
- [ ] Security audit reviewed (see SECURITY_AUDIT.md)
- [ ] No hardcoded secrets in codebase
- [ ] `.gitignore` configured correctly

### Version Control
- [ ] Code merged to `main` branch
- [ ] Git tag created (e.g., `v1.0.0`)
- [ ] Release notes documented
- [ ] Changelog updated
- [ ] No uncommitted changes

### Documentation
- [ ] README.md up to date
- [ ] API documentation current
- [ ] Environment variables documented (.env.example)
- [ ] Deployment guide reviewed
- [ ] Troubleshooting guide available

### Dependencies
- [ ] `requirements.txt` pinned to specific versions
- [ ] No known security vulnerabilities (`safety check` or `pip-audit`)
- [ ] All dependencies compatible with production Python version
- [ ] Virtual environment tested

---

## Environment Setup

### Development Environment
```bash
# 1. Clone repository
git clone <repo-url>
cd crypto-trading-bot/services/trading-engine

# 2. Create virtual environment
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment template
cp .env.example .env

# 5. Configure development settings
# Edit .env with development values
nano .env
```

**Development .env Settings:**
```bash
SERVICE_NAME=trading-engine
SERVICE_HOST=0.0.0.0
SERVICE_PORT=8005
DEBUG=true
LOG_LEVEL=DEBUG

TRADING_MODE=PAPER
AUTO_TRADING_ENABLED=false

POSTGRES_HOST=localhost
POSTGRES_PORT=5433
REDIS_HOST=localhost
REDIS_PORT=6380
```

### Staging Environment
```bash
# 1. Deploy to staging server
ssh user@staging-server

# 2. Setup environment (same as dev, but with staging values)
cd /opt/trading-engine
source venv/bin/activate

# 3. Configure staging settings
cp .env.example .env
```

**Staging .env Settings:**
```bash
SERVICE_NAME=trading-engine
SERVICE_HOST=0.0.0.0
SERVICE_PORT=8005
DEBUG=false
LOG_LEVEL=INFO

TRADING_MODE=PAPER  # Still paper trading in staging!
AUTO_TRADING_ENABLED=false

POSTGRES_HOST=staging-db.internal
POSTGRES_PORT=5432
REDIS_HOST=staging-redis.internal
REDIS_PORT=6379

# Use staging database credentials
POSTGRES_USER=${STAGING_POSTGRES_USER}
POSTGRES_PASSWORD=${STAGING_POSTGRES_PASSWORD}
```

### Production Environment
```bash
# 1. SSH to production server
ssh user@production-server

# 2. Navigate to deployment directory
cd /opt/trading-engine

# 3. Activate virtual environment
source venv/bin/activate

# 4. Create production .env (NEVER copy from staging!)
# Use secrets manager or secure vault
```

**Production .env Settings:**
```bash
SERVICE_NAME=trading-engine
SERVICE_HOST=0.0.0.0
SERVICE_PORT=8005
DEBUG=false  # CRITICAL: Must be false!
LOG_LEVEL=WARNING  # Only warnings and errors

TRADING_MODE=PAPER  # Start with PAPER, switch to LIVE after validation!
AUTO_TRADING_ENABLED=false  # Enable manually after validation

# Production database (separate from staging!)
POSTGRES_HOST=prod-db.internal
POSTGRES_PORT=5432
POSTGRES_DB=trading_engine_prod
POSTGRES_USER=${PROD_POSTGRES_USER}  # From secrets manager
POSTGRES_PASSWORD=${PROD_POSTGRES_PASSWORD}  # From secrets manager

REDIS_HOST=prod-redis.internal
REDIS_PORT=6379
REDIS_PASSWORD=${PROD_REDIS_PASSWORD}  # From secrets manager

# Risk management (conservative settings)
MAX_POSITION_SIZE_PCT=1.0  # More conservative in production
MAX_DAILY_LOSS_PCT=3.0
MAX_TOTAL_EXPOSURE_PCT=10.0

# Optional: Enable monitoring
SENTRY_DSN=${SENTRY_DSN}
SLACK_WEBHOOK_URL=${SLACK_WEBHOOK_URL}
```

---

## Database Setup

### PostgreSQL Setup (Development)
```bash
# 1. Start PostgreSQL container
docker run -d \
  --name trading-engine-postgres \
  -e POSTGRES_DB=trading_engine \
  -e POSTGRES_USER=trading_user \
  -e POSTGRES_PASSWORD=dev_password \
  -p 5433:5432 \
  postgres:15-alpine

# 2. Wait for PostgreSQL to be ready
docker exec trading-engine-postgres pg_isready -U trading_user

# 3. Run database migrations (if using Alembic)
alembic upgrade head

# 4. Verify database connection
psql -h localhost -p 5433 -U trading_user -d trading_engine -c "\dt"
```

### PostgreSQL Setup (Staging/Production)
```bash
# 1. Verify database exists
psql -h ${POSTGRES_HOST} -U ${POSTGRES_USER} -d ${POSTGRES_DB} -c "SELECT version();"

# 2. Create database schema (if first deployment)
psql -h ${POSTGRES_HOST} -U ${POSTGRES_USER} -d ${POSTGRES_DB} -f schema.sql

# 3. Run migrations
alembic upgrade head

# 4. Verify tables created
psql -h ${POSTGRES_HOST} -U ${POSTGRES_USER} -d ${POSTGRES_DB} -c "\dt"

# Expected tables:
# - orders
# - positions
# - performance_metrics
# - trading_signals
# - alembic_version (if using Alembic)
```

### Redis Setup (Development)
```bash
# 1. Start Redis container
docker run -d \
  --name trading-engine-redis \
  -p 6380:6379 \
  redis:7-alpine \
  redis-server --requirepass dev_redis_password

# 2. Test Redis connection
redis-cli -p 6380 -a dev_redis_password PING
# Expected: PONG
```

### Redis Setup (Staging/Production)
```bash
# 1. Verify Redis connection
redis-cli -h ${REDIS_HOST} -p ${REDIS_PORT} -a ${REDIS_PASSWORD} PING

# 2. Test read/write
redis-cli -h ${REDIS_HOST} -p ${REDIS_PORT} -a ${REDIS_PASSWORD} SET test_key "test_value"
redis-cli -h ${REDIS_HOST} -p ${REDIS_PORT} -a ${REDIS_PASSWORD} GET test_key
redis-cli -h ${REDIS_HOST} -p ${REDIS_PORT} -a ${REDIS_PASSWORD} DEL test_key
```

### Database Backup (Production)
```bash
# 1. Create backup directory
mkdir -p /var/backups/trading-engine

# 2. Backup PostgreSQL database
pg_dump -h ${POSTGRES_HOST} -U ${POSTGRES_USER} -d ${POSTGRES_DB} \
  -F c -b -v -f "/var/backups/trading-engine/trading_engine_$(date +%Y%m%d_%H%M%S).backup"

# 3. Verify backup
ls -lh /var/backups/trading-engine/

# 4. Setup automated backups (cron)
# Add to crontab: 0 2 * * * /opt/trading-engine/scripts/backup.sh
```

---

## Security Configuration

### Secrets Management

**Using HashiCorp Vault (Recommended):**
```bash
# 1. Install Vault CLI
# https://www.vaultproject.io/downloads

# 2. Login to Vault
vault login -method=token token=${VAULT_TOKEN}

# 3. Store secrets
vault kv put secret/trading-engine/production \
  postgres_password="${PROD_POSTGRES_PASSWORD}" \
  redis_password="${PROD_REDIS_PASSWORD}" \
  bybit_api_key="${BYBIT_API_KEY}" \
  bybit_api_secret="${BYBIT_API_SECRET}"

# 4. Retrieve secrets in deployment script
export POSTGRES_PASSWORD=$(vault kv get -field=postgres_password secret/trading-engine/production)
```

**Using AWS Secrets Manager:**
```bash
# 1. Install AWS CLI
# https://aws.amazon.com/cli/

# 2. Store secret
aws secretsmanager create-secret \
  --name trading-engine/production/postgres \
  --secret-string '{"username":"trading_user","password":"SECURE_PASSWORD"}'

# 3. Retrieve in deployment
aws secretsmanager get-secret-value \
  --secret-id trading-engine/production/postgres \
  --query SecretString --output text | jq -r '.password'
```

### SSL/TLS Configuration (Nginx Reverse Proxy)

**Install Certbot (Let's Encrypt):**
```bash
# 1. Install Certbot
sudo apt install certbot python3-certbot-nginx

# 2. Obtain certificate
sudo certbot --nginx -d trading-engine.yourdomain.com

# 3. Configure nginx
sudo nano /etc/nginx/sites-available/trading-engine
```

**Nginx Configuration:**
```nginx
# /etc/nginx/sites-available/trading-engine

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name trading-engine.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS server
server {
    listen 443 ssl http2;
    server_name trading-engine.yourdomain.com;

    # SSL certificates (managed by Certbot)
    ssl_certificate /etc/letsencrypt/live/trading-engine.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/trading-engine.yourdomain.com/privkey.pem;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
    limit_req zone=api_limit burst=20 nodelay;

    # Proxy to FastAPI
    location / {
        proxy_pass http://127.0.0.1:8005;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Health check endpoint (no rate limit)
    location /health {
        proxy_pass http://127.0.0.1:8005/health;
        access_log off;
    }
}
```

```bash
# 4. Enable site
sudo ln -s /etc/nginx/sites-available/trading-engine /etc/nginx/sites-enabled/

# 5. Test nginx configuration
sudo nginx -t

# 6. Reload nginx
sudo systemctl reload nginx

# 7. Setup auto-renewal
sudo certbot renew --dry-run
```

### Firewall Configuration
```bash
# 1. Install UFW (Ubuntu)
sudo apt install ufw

# 2. Default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# 3. Allow SSH (important - don't lock yourself out!)
sudo ufw allow 22/tcp

# 4. Allow HTTP/HTTPS (for nginx)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# 5. Allow application port (only from localhost or internal network)
# Trading engine should NOT be directly exposed!
# sudo ufw allow from 10.0.0.0/8 to any port 8005

# 6. Enable firewall
sudo ufw enable

# 7. Verify status
sudo ufw status verbose
```

### Security Checklist
- [ ] All passwords changed from defaults
- [ ] Passwords are 32+ characters, randomly generated
- [ ] API keys stored in secrets manager (not .env)
- [ ] SSL/TLS enabled (HTTPS only)
- [ ] Firewall configured (UFW or iptables)
- [ ] Nginx reverse proxy configured with rate limiting
- [ ] Security headers enabled
- [ ] CORS origins restricted to known domains
- [ ] DEBUG mode disabled
- [ ] Log level set to WARNING or ERROR
- [ ] Database connections encrypted (SSL mode)
- [ ] Redis password authentication enabled
- [ ] No sensitive data in logs
- [ ] Automated security updates enabled

---

## Service Deployment

### Systemd Service Setup (Production)

**Create systemd service file:**
```bash
sudo nano /etc/systemd/system/trading-engine.service
```

**Service Configuration:**
```ini
[Unit]
Description=Trading Engine Service
After=network.target postgresql.service redis.service
Requires=postgresql.service redis.service

[Service]
Type=simple
User=trading-engine
Group=trading-engine
WorkingDirectory=/opt/trading-engine

# Environment file (contains non-secret config)
EnvironmentFile=/opt/trading-engine/.env.production

# Load secrets from vault (example)
ExecStartPre=/opt/trading-engine/scripts/load-secrets.sh

# Start the service
ExecStart=/opt/trading-engine/venv/bin/uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8005 \
  --workers 4 \
  --log-level warning

# Restart policy
Restart=always
RestartSec=10

# Resource limits
LimitNOFILE=65536
MemoryLimit=2G
CPUQuota=200%

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/trading-engine/logs

[Install]
WantedBy=multi-user.target
```

**Create dedicated user:**
```bash
# 1. Create trading-engine user (no login shell)
sudo useradd -r -s /bin/false -d /opt/trading-engine trading-engine

# 2. Set ownership
sudo chown -R trading-engine:trading-engine /opt/trading-engine

# 3. Set permissions (restrictive)
sudo chmod 750 /opt/trading-engine
sudo chmod 640 /opt/trading-engine/.env.production
```

**Enable and start service:**
```bash
# 1. Reload systemd
sudo systemctl daemon-reload

# 2. Enable service (start on boot)
sudo systemctl enable trading-engine

# 3. Start service
sudo systemctl start trading-engine

# 4. Check status
sudo systemctl status trading-engine

# 5. View logs
sudo journalctl -u trading-engine -f
```

### Docker Deployment (Alternative)

**Dockerfile:**
```dockerfile
# /opt/trading-engine/Dockerfile

FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create non-root user
RUN useradd -r -u 1000 -g users trading-engine && \
    chown -R trading-engine:users /app

# Switch to non-root user
USER trading-engine

# Expose port
EXPOSE 8005

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8005/health')"

# Start application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
```

**Build and run Docker container:**
```bash
# 1. Build image
docker build -t trading-engine:1.0.0 .

# 2. Run container
docker run -d \
  --name trading-engine \
  --restart unless-stopped \
  -p 8005:8005 \
  --env-file .env.production \
  --network trading-network \
  -v /opt/trading-engine/logs:/app/logs \
  trading-engine:1.0.0

# 3. Check container status
docker ps

# 4. View logs
docker logs -f trading-engine

# 5. Check health
docker exec trading-engine curl http://localhost:8005/health
```

### Kubernetes Deployment (Advanced)

**deployment.yaml:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: trading-engine
  namespace: trading
spec:
  replicas: 3
  selector:
    matchLabels:
      app: trading-engine
  template:
    metadata:
      labels:
        app: trading-engine
    spec:
      containers:
      - name: trading-engine
        image: trading-engine:1.0.0
        ports:
        - containerPort: 8005
        env:
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: trading-secrets
              key: postgres-password
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8005
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8005
          initialDelaySeconds: 10
          periodSeconds: 5
```

```bash
# Deploy to Kubernetes
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml

# Check deployment
kubectl get pods -n trading
kubectl logs -f deployment/trading-engine -n trading
```

---

## Post-Deployment Validation

### Health Checks
```bash
# 1. Service health check
curl http://localhost:8005/health
# Expected: {"status": "healthy", "service": "trading-engine"}

# 2. Database connectivity
curl http://localhost:8005/health/db
# Expected: {"database": "connected"}

# 3. Redis connectivity
curl http://localhost:8005/health/redis
# Expected: {"redis": "connected"}

# 4. Service readiness (via nginx/load balancer)
curl https://trading-engine.yourdomain.com/health
```

### Functional Tests
```bash
# 1. Get trading signal (test API)
curl -X GET "http://localhost:8005/api/v1/signals/BTCUSDT?interval=60" \
  -H "Accept: application/json"

# Expected: {"signal": "BUY|SELL|NEUTRAL", "confidence": 0.75, ...}

# 2. Check paper trading balance
curl -X GET "http://localhost:8005/api/v1/paper-trading/balance" \
  -H "Accept: application/json"

# Expected: {"balance": 10000.00, "available": 10000.00}

# 3. Get open positions
curl -X GET "http://localhost:8005/api/v1/positions/open" \
  -H "Accept: application/json"

# Expected: []

# 4. Test error handling (invalid symbol)
curl -X GET "http://localhost:8005/api/v1/signals/INVALID?interval=60" \
  -H "Accept: application/json"

# Expected: HTTP 400 or 404 with error message
```

### Performance Validation
```bash
# 1. Check response time (should be < 100ms for health checks)
time curl http://localhost:8005/health

# 2. Load test with Apache Bench
ab -n 1000 -c 10 http://localhost:8005/health

# 3. Monitor resource usage
top -p $(pgrep -f "uvicorn app.main:app")

# 4. Check memory usage
ps aux | grep uvicorn

# 5. Database connection pool
psql -h ${POSTGRES_HOST} -U ${POSTGRES_USER} -d ${POSTGRES_DB} \
  -c "SELECT count(*) FROM pg_stat_activity WHERE datname = 'trading_engine';"
```

### Log Verification
```bash
# 1. Check application logs
tail -f /opt/trading-engine/logs/trading-engine.log

# 2. Check systemd logs
sudo journalctl -u trading-engine -n 100 --no-pager

# 3. Check nginx access logs
sudo tail -f /var/log/nginx/access.log

# 4. Check nginx error logs
sudo tail -f /var/log/nginx/error.log

# 5. Verify no errors in logs
sudo journalctl -u trading-engine -p err -n 50
```

### Post-Deployment Checklist
- [ ] Service is running (`systemctl status trading-engine`)
- [ ] Health check returns 200 OK
- [ ] Database connection successful
- [ ] Redis connection successful
- [ ] API endpoints responding correctly
- [ ] Response times < 100ms for health checks
- [ ] No errors in logs
- [ ] Nginx reverse proxy working
- [ ] HTTPS working (SSL certificate valid)
- [ ] Rate limiting configured and working
- [ ] Monitoring agents running
- [ ] Metrics being collected
- [ ] Alerts configured
- [ ] Backup job scheduled and tested
- [ ] Paper trading mode enabled (initially)
- [ ] Auto-trading disabled (initially)

---

## Rollback Procedures

### Quick Rollback (Systemd)
```bash
# 1. Stop current service
sudo systemctl stop trading-engine

# 2. Navigate to previous version
cd /opt/trading-engine
mv current current-failed
mv previous current

# 3. Start service with previous version
sudo systemctl start trading-engine

# 4. Verify service is healthy
curl http://localhost:8005/health

# 5. Check logs for errors
sudo journalctl -u trading-engine -n 100
```

### Docker Rollback
```bash
# 1. Stop current container
docker stop trading-engine
docker rm trading-engine

# 2. Run previous version
docker run -d \
  --name trading-engine \
  --restart unless-stopped \
  -p 8005:8005 \
  --env-file .env.production \
  trading-engine:0.9.0  # Previous version tag

# 3. Verify
docker ps
curl http://localhost:8005/health
```

### Database Rollback
```bash
# 1. Stop application
sudo systemctl stop trading-engine

# 2. Restore database from backup
pg_restore -h ${POSTGRES_HOST} -U ${POSTGRES_USER} -d ${POSTGRES_DB} \
  -c /var/backups/trading-engine/trading_engine_20251110_020000.backup

# 3. Verify database
psql -h ${POSTGRES_HOST} -U ${POSTGRES_USER} -d ${POSTGRES_DB} -c "\dt"

# 4. Start application
sudo systemctl start trading-engine
```

### Rollback Checklist
- [ ] Incident documented with reason for rollback
- [ ] Stakeholders notified
- [ ] Service stopped gracefully
- [ ] Previous version deployed
- [ ] Database restored if needed
- [ ] Service health verified
- [ ] Logs checked for errors
- [ ] Monitoring confirms stability
- [ ] Root cause analysis scheduled
- [ ] Fix planned for next deployment

---

## Monitoring Setup

### Application Metrics (Prometheus)

**Install Prometheus client:**
```bash
pip install prometheus-client
```

**Add metrics to FastAPI app:**
```python
# app/main.py
from prometheus_client import Counter, Histogram, Gauge
from prometheus_client import make_asgi_app

# Define metrics
http_requests_total = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
http_request_duration = Histogram('http_request_duration_seconds', 'HTTP request duration')
active_positions = Gauge('active_positions', 'Number of active trading positions')
trading_signals_total = Counter('trading_signals_total', 'Total trading signals', ['signal_type'])

# Add metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
```

**Prometheus configuration:**
```yaml
# /etc/prometheus/prometheus.yml
scrape_configs:
  - job_name: 'trading-engine'
    scrape_interval: 15s
    static_configs:
      - targets: ['localhost:8005']
```

### Logging (Centralized)

**Sentry Integration:**
```python
# app/main.py
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    environment="production",
    traces_sample_rate=1.0,
    integrations=[FastApiIntegration()]
)
```

**ELK Stack (Elasticsearch, Logstash, Kibana):**
```bash
# Install Filebeat
sudo apt install filebeat

# Configure filebeat
sudo nano /etc/filebeat/filebeat.yml
```

```yaml
filebeat.inputs:
  - type: log
    enabled: true
    paths:
      - /opt/trading-engine/logs/*.log
    json.keys_under_root: true
    json.add_error_key: true

output.elasticsearch:
  hosts: ["http://localhost:9200"]
  index: "trading-engine-%{+yyyy.MM.dd}"
```

### Alerting (Slack/Email)

**Slack Webhook:**
```python
# app/utils/alerts.py
import httpx
import os

async def send_slack_alert(message: str, level: str = "warning"):
    """Send alert to Slack channel"""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")

    if not webhook_url:
        return

    payload = {
        "text": f"[{level.upper()}] Trading Engine Alert",
        "attachments": [{
            "text": message,
            "color": "warning" if level == "warning" else "danger"
        }]
    }

    async with httpx.AsyncClient() as client:
        await client.post(webhook_url, json=payload)
```

**Email Alerts:**
```python
# app/utils/alerts.py
import smtplib
from email.mime.text import MIMEText

def send_email_alert(subject: str, message: str):
    """Send email alert"""
    smtp_server = os.getenv("EMAIL_SMTP_SERVER")
    smtp_port = int(os.getenv("EMAIL_SMTP_PORT", 587))
    from_email = os.getenv("EMAIL_FROM")
    to_email = os.getenv("EMAIL_TO")
    password = os.getenv("EMAIL_PASSWORD")

    msg = MIMEText(message)
    msg['Subject'] = f"[Trading Engine] {subject}"
    msg['From'] = from_email
    msg['To'] = to_email

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(from_email, password)
        server.send_message(msg)
```

### Monitoring Checklist
- [ ] Prometheus metrics endpoint configured
- [ ] Grafana dashboard created
- [ ] Application logs centralized (ELK/Sentry)
- [ ] Error rate alerts configured (> 5%)
- [ ] Response time alerts configured (> 500ms)
- [ ] CPU usage alerts (> 80%)
- [ ] Memory usage alerts (> 90%)
- [ ] Disk usage alerts (> 85%)
- [ ] Database connection pool alerts
- [ ] Trading-specific alerts:
  - [ ] Daily loss limit reached
  - [ ] Position size limit exceeded
  - [ ] Unusual trading volume
  - [ ] Failed order executions
  - [ ] API connection failures
- [ ] Uptime monitoring configured (UptimeRobot, Pingdom)
- [ ] On-call rotation defined
- [ ] Incident response runbook created

---

## Emergency Procedures

### Circuit Breaker - Emergency Stop Trading
```bash
# 1. Stop auto-trading immediately
curl -X POST http://localhost:8005/api/v1/trading/emergency-stop \
  -H "Content-Type: application/json"

# 2. Close all open positions (manual approval required)
curl -X POST http://localhost:8005/api/v1/positions/close-all \
  -H "Content-Type: application/json"

# 3. Disable service
sudo systemctl stop trading-engine

# 4. Notify team
# Send alert via Slack/Email
```

### Service Recovery
```bash
# 1. Check service status
sudo systemctl status trading-engine

# 2. View recent errors
sudo journalctl -u trading-engine -p err -n 50

# 3. Restart service
sudo systemctl restart trading-engine

# 4. Monitor logs in real-time
sudo journalctl -u trading-engine -f

# 5. Verify health
curl http://localhost:8005/health
```

---

## Deployment Timeline

### Week Before Deployment
- [ ] Code freeze on main branch
- [ ] Final testing in staging environment
- [ ] Security audit completed
- [ ] Deployment plan reviewed with team
- [ ] Rollback plan tested
- [ ] Monitoring dashboards configured
- [ ] On-call schedule confirmed

### Day Before Deployment
- [ ] All tests passing in staging
- [ ] Performance benchmarks met
- [ ] Database backups verified
- [ ] Deployment scripts tested
- [ ] Team notified of deployment window
- [ ] Rollback procedure reviewed

### Deployment Day
- [ ] **09:00** - Final staging validation
- [ ] **10:00** - Database backup
- [ ] **10:30** - Deploy to production
- [ ] **10:45** - Run post-deployment validation
- [ ] **11:00** - Monitor for 1 hour (no issues)
- [ ] **12:00** - Deployment complete notification
- [ ] **EOD** - Post-deployment report

### Post-Deployment (First Week)
- [ ] Day 1: Hourly monitoring
- [ ] Day 2-3: Monitor every 4 hours
- [ ] Day 4-7: Daily monitoring
- [ ] Collect performance metrics
- [ ] Review logs for warnings
- [ ] Document any issues encountered
- [ ] Plan improvements for next deployment

---

## Sign-Off

### Pre-Deployment Sign-Off
- [ ] **Developer**: Code ready for production
  Name: _________________ Date: _______

- [ ] **QA Lead**: All tests passing
  Name: _________________ Date: _______

- [ ] **Security**: Security audit approved
  Name: _________________ Date: _______

- [ ] **DevOps**: Infrastructure ready
  Name: _________________ Date: _______

### Post-Deployment Sign-Off
- [ ] **Deployment Lead**: Deployment successful
  Name: _________________ Date: _______

- [ ] **Operations**: Monitoring confirmed
  Name: _________________ Date: _______

- [ ] **Business Owner**: Service validated
  Name: _________________ Date: _______

---

## Appendix

### Useful Commands

**Check service status:**
```bash
systemctl status trading-engine
```

**View logs:**
```bash
journalctl -u trading-engine -f
```

**Test API:**
```bash
curl http://localhost:8005/health
```

**Database connection:**
```bash
psql -h localhost -p 5433 -U trading_user -d trading_engine
```

**Redis connection:**
```bash
redis-cli -p 6380 -a your_password
```

**Resource monitoring:**
```bash
htop  # or: top
```

### Contacts

**Development Team:**
- Lead Developer: dev@yourdomain.com
- DevOps Engineer: devops@yourdomain.com

**Operations:**
- On-Call: oncall@yourdomain.com
- Incident Response: incidents@yourdomain.com

**Business:**
- Product Owner: product@yourdomain.com
- CTO: cto@yourdomain.com

### References
- [SECURITY_AUDIT.md](./SECURITY_AUDIT.md)
- [.env.example](./.env.example)
- [API Documentation](./docs/api/)
- [Troubleshooting Guide](./docs/TROUBLESHOOTING.md)

---

**Document Version:** 1.0
**Last Updated:** 2025-11-10
**Next Review:** 2025-12-10
