# 🐳 Docker Quick Start Guide

## Prerequisites

1. **Install Docker Desktop:**
   - Windows/Mac: Download from https://www.docker.com/products/docker-desktop/
   - Linux: `sudo apt-get install docker.io docker-compose`

2. **Verify installation:**
   ```bash
   docker --version
   docker-compose --version
   ```

---

## Step 1: Configure Environment Variables

**IMPORTANT:** Set up your Bybit API credentials before deploying.

```bash
# Navigate to bybit-connector directory
cd services/bybit-connector

# Copy example environment file
cp .env.example .env

# Edit .env with your credentials
nano .env  # or use any text editor
```

**Required variables in `.env`:**
```bash
BYBIT_API_KEY=your_actual_api_key_here
BYBIT_API_SECRET=your_actual_api_secret_here
BYBIT_TESTNET=true  # Keep true for testing!
```

**Get Bybit Testnet API Keys:**
1. Go to https://testnet.bybit.com/
2. Register/Login
3. Go to API Management
4. Create new API key with trading permissions

---

## Step 2: Build Docker Images

From the project root directory:

```bash
# Build all services (first time will take 5-10 minutes)
docker-compose build

# Expected output:
# ✓ api-gateway built
# ✓ bybit-connector built
# ✓ technical-analysis built
# ✓ trading-engine built
# ✓ portfolio-manager built
```

---

## Step 3: Start All Services

```bash
# Start all services in background
docker-compose up -d

# View startup logs
docker-compose logs -f

# Wait for "Application startup complete" from all services
# Press Ctrl+C to exit logs view
```

---

## Step 4: Verify Deployment

**Check service status:**
```bash
docker-compose ps

# All services should show "Up" and "(healthy)"
```

**Test health endpoints:**
```bash
curl http://localhost:8000/health  # API Gateway
curl http://localhost:8002/health  # Bybit Connector
curl http://localhost:8004/health  # Technical Analysis
curl http://localhost:8005/health  # Trading Engine
curl http://localhost:8006/health  # Portfolio Manager

# All should return: {"status":"healthy","service":"..."}
```

---

## Step 5: Monitor Services

**View live logs:**
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f trading-engine
docker-compose logs -f bybit-connector
```

**Check resource usage:**
```bash
docker stats

# Monitor CPU, Memory, Network usage
```

---

## Common Commands

### Service Management

```bash
# Stop all services
docker-compose stop

# Start stopped services
docker-compose start

# Restart specific service
docker-compose restart trading-engine

# Stop and remove all containers
docker-compose down

# Stop, remove, and clean volumes
docker-compose down -v
```

### Rebuilding After Code Changes

```bash
# Rebuild specific service
docker-compose build bybit-connector

# Rebuild and restart
docker-compose up -d --build bybit-connector

# Rebuild all services
docker-compose build --no-cache
docker-compose up -d
```

### Viewing Logs

```bash
# Last 100 lines
docker-compose logs --tail=100

# Follow logs from specific time
docker-compose logs --since 1h

# Export logs to file
docker-compose logs > logs/deployment_$(date +%Y%m%d).log
```

### Container Shell Access

```bash
# Access running container
docker-compose exec trading-engine /bin/bash

# Or use sh if bash not available
docker-compose exec trading-engine /bin/sh

# View logs inside container
docker-compose exec trading-engine cat /app/logs/service.log
```

---

## Troubleshooting

### Issue: Services won't start

```bash
# Check what went wrong
docker-compose logs

# Common fixes:
# 1. Port already in use
sudo lsof -i :8000  # Check which process
sudo kill -9 <PID>  # Kill that process

# 2. Missing .env file
cp services/bybit-connector/.env.example services/bybit-connector/.env

# 3. Permission issues
sudo chmod -R 755 services/
```

### Issue: Service keeps restarting

```bash
# View logs to see error
docker-compose logs trading-engine

# Check configuration
docker-compose config

# Restart with fresh build
docker-compose down
docker-compose build --no-cache trading-engine
docker-compose up -d
```

### Issue: Can't connect to Bybit API

```bash
# Check Bybit Connector logs
docker-compose logs bybit-connector

# Verify credentials
docker-compose exec bybit-connector cat /app/.env

# Test connectivity
docker-compose exec bybit-connector curl https://api-testnet.bybit.com/v5/market/time
```

### Issue: High CPU/Memory usage

```bash
# Check resource usage
docker stats

# Restart heavy service
docker-compose restart trading-engine

# Limit resources in docker-compose.yml:
deploy:
  resources:
    limits:
      cpus: '0.5'
      memory: 512M
```

---

## Production Deployment Changes

When ready for production (after 2 weeks paper trading):

1. **Update docker-compose.yml:**
   ```yaml
   trading-engine:
     environment:
       - PAPER_TRADING_MODE=false  # Enable real trading
       - DEBUG=false
       - LOG_LEVEL=WARNING
   ```

2. **Update Bybit connector .env:**
   ```bash
   BYBIT_TESTNET=false  # Use mainnet
   BYBIT_API_KEY=<mainnet_key>
   BYBIT_API_SECRET=<mainnet_secret>
   ```

3. **Rebuild and deploy:**
   ```bash
   docker-compose down
   docker-compose build
   docker-compose up -d
   ```

---

## Monitoring in Production

### Set up log rotation:

```bash
# Add to docker-compose.yml for each service:
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

### Health check monitoring:

```bash
# Create a monitoring script
#!/bin/bash
# monitor.sh

while true; do
  for port in 8000 8002 8004 8005 8006; do
    status=$(curl -s http://localhost:$port/health | jq -r '.status')
    if [ "$status" != "healthy" ]; then
      echo "ALERT: Service on port $port is unhealthy!"
      # Send notification (email, Slack, etc.)
    fi
  done
  sleep 60
done
```

---

## Backup Strategy

```bash
# Daily backup script
#!/bin/bash
# backup.sh

DATE=$(date +%Y%m%d_%H%M%S)

# Backup configurations
tar -czf backup_config_$DATE.tar.gz \
  docker-compose.yml \
  services/*/.env \
  services/*/requirements.txt

# Backup logs
docker-compose logs > backup_logs_$DATE.log

# Keep last 30 days
find . -name "backup_*" -mtime +30 -delete
```

---

## Security Checklist

- [ ] `.env` files are NOT committed to git
- [ ] Using testnet for initial testing
- [ ] PAPER_TRADING_MODE=true initially
- [ ] All services have health checks
- [ ] Logs are being rotated
- [ ] Resource limits configured
- [ ] CORS properly configured
- [ ] Regular backups scheduled

---

## Performance Optimization

### 1. Use Docker BuildKit:
```bash
export DOCKER_BUILDKIT=1
docker-compose build
```

### 2. Multi-stage builds (optional):
Add to Dockerfile:
```dockerfile
# Build stage
FROM python:3.12-slim as builder
COPY requirements.txt .
RUN pip install --user -r requirements.txt

# Runtime stage
FROM python:3.12-slim
COPY --from=builder /root/.local /root/.local
COPY app/ ./app/
```

### 3. Use Docker volumes for logs:
Already configured in docker-compose.yml:
```yaml
volumes:
  - ./services/api-gateway/logs:/app/logs
```

---

## Quick Reference

| Command | Description |
|---------|-------------|
| `docker-compose up -d` | Start all services |
| `docker-compose down` | Stop all services |
| `docker-compose ps` | Check service status |
| `docker-compose logs -f` | View live logs |
| `docker-compose restart <service>` | Restart specific service |
| `docker-compose build` | Rebuild all images |
| `docker stats` | Monitor resources |
| `docker-compose exec <service> /bin/bash` | Access container shell |

---

## Support

**Issues?** Check:
1. Docker logs: `docker-compose logs`
2. Service health: `curl http://localhost:<port>/health`
3. Container status: `docker-compose ps`
4. Resource usage: `docker stats`

**For detailed deployment guide:** See `DEPLOYMENT.md`

---

## Next Steps

1. ✅ Services are running
2. ✅ Health checks passing
3. ⏳ Monitor for 24 hours
4. ⏳ Paper trade for 2 weeks minimum
5. ⏳ Review performance metrics
6. ⏳ Switch to production (if satisfied)

**Remember:** NEVER use real funds without thorough testing! 🚨

---

**Quick Start Complete!** Your crypto trading bot is now running in Docker containers. 🎉
