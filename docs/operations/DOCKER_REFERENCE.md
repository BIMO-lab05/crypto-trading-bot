# Docker Commands Reference Guide
# Crypto Trading Bot - DevOps Documentation
# Version: 1.0
# Last Updated: 2025-11-19

## Table of Contents
1. [Quick Start Commands](#quick-start-commands)
2. [Service Management](#service-management)
3. [Container Operations](#container-operations)
4. [Image Management](#image-management)
5. [Network Operations](#network-operations)
6. [Volume Management](#volume-management)
7. [Monitoring & Debugging](#monitoring--debugging)
8. [Health Checks](#health-checks)
9. [Backup & Restore](#backup--restore)
10. [Optimization Commands](#optimization-commands)
11. [Troubleshooting](#troubleshooting)

---

## Quick Start Commands

### Start All Services
```bash
# Start infrastructure services first
cd infrastructure/
docker compose up -d

# Wait for infrastructure to be ready (15-30 seconds)
sleep 15

# Start application services
cd ..
docker compose up -d

# Check status
docker ps --format "table {{.Names}}\t{{.Status}}"
```

### Stop All Services
```bash
# Stop application services
docker compose stop

# Stop infrastructure services
cd infrastructure/
docker compose stop
```

### Automated Scripts (Recommended)
```bash
# Use deployment automation script
./scripts/deploy.sh start      # Start all services
./scripts/deploy.sh stop       # Stop all services
./scripts/deploy.sh restart    # Quick restart all
./scripts/deploy.sh status     # Show status
./scripts/deploy.sh health     # Run health check
```

---

## Service Management

### Start Specific Service
```bash
docker compose up -d <service-name>

# Examples:
docker compose up -d trading-engine
docker compose up -d market-data
docker compose up -d technical-analysis
```

### Stop Specific Service
```bash
docker compose stop <service-name>

# Example:
docker compose stop trading-engine
```

### Restart Specific Service
```bash
docker compose restart <service-name>

# Example:
docker compose restart api-gateway
```

### Rebuild and Restart Service
```bash
# Stop service
docker compose stop <service-name>

# Rebuild without cache
docker compose build --no-cache <service-name>

# Start service
docker compose up -d <service-name>

# Or use automation script:
./scripts/deploy.sh rebuild <service-name>
```

### Scale Service (Multiple Instances)
```bash
# Note: Only works for stateless services without port conflicts
docker compose up -d --scale <service-name>=3

# Example:
docker compose up -d --scale sentiment-analysis=2
```

---

## Container Operations

### List Running Containers
```bash
# All containers
docker ps

# Crypto bot containers only
docker ps | grep crypto-bot

# With custom formatting
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# All containers (including stopped)
docker ps -a
```

### View Container Details
```bash
# Inspect container
docker inspect <container-name>

# Get specific field (e.g., IP address)
docker inspect -f '{{.NetworkSettings.IPAddress}}' crypto-bot-trading

# Get health status
docker inspect -f '{{.State.Health.Status}}' crypto-bot-trading

# Get environment variables
docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' crypto-bot-trading
```

### Execute Commands in Container
```bash
# Interactive shell
docker exec -it <container-name> /bin/bash

# Run specific command
docker exec <container-name> python -m pytest

# As specific user
docker exec -u root <container-name> apt-get update

# Examples:
docker exec -it crypto-bot-postgres psql -U cryptobot
docker exec crypto-bot-redis redis-cli
docker exec crypto-bot-trading python -c "import app; print(app.__version__)"
```

### Copy Files To/From Container
```bash
# Copy file from container to host
docker cp <container-name>:/path/in/container /path/on/host

# Copy file from host to container
docker cp /path/on/host <container-name>:/path/in/container

# Examples:
docker cp crypto-bot-trading:/app/logs/trading.log ./logs/
docker cp config.yaml crypto-bot-api-gateway:/app/config/
```

---

## Image Management

### List Images
```bash
# All images
docker images

# Crypto bot images only
docker images | grep crypto-bot

# Filter by name
docker images crypto-bot-*
```

### Build Images
```bash
# Build specific service
docker compose build <service-name>

# Build without cache
docker compose build --no-cache <service-name>

# Build with progress output
docker compose build --progress=plain <service-name>

# Build all services
docker compose build

# Build with specific Dockerfile
docker build -f Dockerfile.optimized -t crypto-bot-custom:latest .
```

### Remove Images
```bash
# Remove specific image
docker rmi <image-name>

# Remove multiple images
docker rmi crypto-bot-trading:latest crypto-bot-ta:latest

# Remove unused images
docker image prune -f

# Remove all unused images (including tagged)
docker image prune -a -f

# Remove images older than 24 hours
docker image prune -a --filter "until=24h"
```

### Tag and Push Images
```bash
# Tag image
docker tag crypto-bot-trading:latest myregistry.com/crypto-bot-trading:v1.0

# Push to registry
docker push myregistry.com/crypto-bot-trading:v1.0

# Pull from registry
docker pull myregistry.com/crypto-bot-trading:v1.0
```

---

## Network Operations

### List Networks
```bash
docker network ls

# Inspect crypto-bot network
docker network inspect crypto-bot-network
```

### Connect/Disconnect Containers
```bash
# Connect container to network
docker network connect crypto-bot-network <container-name>

# Disconnect container from network
docker network disconnect crypto-bot-network <container-name>
```

### Test Network Connectivity
```bash
# Ping between containers
docker exec crypto-bot-trading ping crypto-bot-market-data

# Check if port is open
docker exec crypto-bot-trading nc -zv crypto-bot-postgres 5432

# DNS resolution test
docker exec crypto-bot-trading nslookup crypto-bot-rabbitmq
```

---

## Volume Management

### List Volumes
```bash
# All volumes
docker volume ls

# Crypto bot volumes only
docker volume ls | grep crypto-bot

# Inspect specific volume
docker volume inspect crypto-bot-postgres_data
```

### Create and Remove Volumes
```bash
# Create volume
docker volume create crypto-bot-custom-data

# Remove volume
docker volume rm crypto-bot-custom-data

# Remove unused volumes
docker volume prune -f

# Remove all volumes (WARNING: DATA LOSS)
docker volume prune -a -f
```

### Backup Volume Data
```bash
# Backup PostgreSQL volume
docker run --rm \
  -v crypto-bot-postgres_data:/source \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/postgres-backup-$(date +%Y%m%d).tar.gz -C /source .

# Restore volume
docker run --rm \
  -v crypto-bot-postgres_data:/target \
  -v $(pwd)/backups:/backup \
  alpine tar xzf /backup/postgres-backup-20251119.tar.gz -C /target
```

---

## Monitoring & Debugging

### View Logs
```bash
# View logs for all services
docker compose logs

# Follow logs in real-time
docker compose logs -f

# Last 100 lines
docker compose logs --tail=100

# Logs for specific service
docker compose logs -f trading-engine

# Logs with timestamps
docker compose logs -f --timestamps market-data

# Logs since specific time
docker logs --since 1h crypto-bot-trading
docker logs --since 2025-11-19T10:00:00 crypto-bot-trading
```

### Resource Usage
```bash
# Live stats for all containers
docker stats

# Stats without live stream
docker stats --no-stream

# Stats for specific containers
docker stats crypto-bot-trading crypto-bot-ta

# Custom format
docker stats --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"
```

### Process Inspection
```bash
# Top processes in container
docker top <container-name>

# Detailed process info
docker top crypto-bot-trading aux

# Check running processes
docker exec crypto-bot-trading ps aux
```

### Port Mapping
```bash
# Show port mappings
docker port <container-name>

# Example:
docker port crypto-bot-api-gateway
# Output: 8000/tcp -> 0.0.0.0:8000
```

---

## Health Checks

### Manual Health Checks
```bash
# Check health endpoint
curl http://localhost:8000/health

# All service health endpoints
for port in 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009; do
  echo "Port $port: $(curl -s http://localhost:$port/health | jq -r .status)"
done

# Check container health status
docker inspect -f '{{.State.Health.Status}}' crypto-bot-trading
```

### Automated Health Monitoring
```bash
# Run health check script
./scripts/health-check-monitor.sh -c

# Continuous monitoring (every 30 seconds)
./scripts/health-check-monitor.sh -m 30

# Auto-restart unhealthy services
./scripts/health-check-monitor.sh -r

# Generate health report
./scripts/health-check-monitor.sh -R
```

---

## Backup & Restore

### Database Backup
```bash
# PostgreSQL backup
docker exec crypto-bot-postgres pg_dump -U cryptobot cryptobot > backup_postgres_$(date +%Y%m%d).sql

# TimescaleDB backup
docker exec crypto-bot-timescaledb pg_dump -U cryptobot market_data > backup_timescale_$(date +%Y%m%d).sql

# Redis backup
docker exec crypto-bot-redis redis-cli SAVE
docker cp crypto-bot-redis:/data/dump.rdb ./backups/redis_backup_$(date +%Y%m%d).rdb
```

### Database Restore
```bash
# PostgreSQL restore
cat backup_postgres_20251119.sql | docker exec -i crypto-bot-postgres psql -U cryptobot cryptobot

# TimescaleDB restore
cat backup_timescale_20251119.sql | docker exec -i crypto-bot-timescaledb psql -U cryptobot market_data

# Redis restore
docker cp ./backups/redis_backup.rdb crypto-bot-redis:/data/dump.rdb
docker restart crypto-bot-redis
```

### Complete System Backup
```bash
# Use automation script
./scripts/deploy.sh backup

# Manual comprehensive backup
tar -czf backup_complete_$(date +%Y%m%d).tar.gz \
  logs/ \
  services/*/logs/ \
  services/ml-prediction-service/models/ \
  --exclude='*.pyc' \
  --exclude='__pycache__'
```

---

## Optimization Commands

### Clean Up Resources
```bash
# Remove stopped containers
docker container prune -f

# Remove unused images
docker image prune -f

# Remove unused volumes
docker volume prune -f

# Remove unused networks
docker network prune -f

# Complete cleanup (be careful!)
docker system prune -a -f --volumes

# Use automation script
./scripts/deploy.sh clean
```

### Optimize Builds
```bash
# Build with BuildKit (faster, better caching)
DOCKER_BUILDKIT=1 docker compose build

# Multi-stage build for smaller images
# See Dockerfile.optimized.template

# Use .dockerignore to exclude files
echo "__pycache__" >> .dockerignore
echo "*.pyc" >> .dockerignore
echo ".git" >> .dockerignore
echo "tests/" >> .dockerignore
```

### Check Disk Usage
```bash
# Docker disk usage summary
docker system df

# Detailed disk usage
docker system df -v

# Size of each container
docker ps -s

# Size of each image
docker images --format "{{.Repository}}:{{.Tag}} - {{.Size}}"
```

---

## Troubleshooting

### Container Won't Start
```bash
# Check logs
docker compose logs <service-name>

# Check last 50 lines
docker logs --tail 50 <container-name>

# Check exit code
docker inspect -f '{{.State.ExitCode}}' <container-name>

# Check for port conflicts
netstat -tulpn | grep <port-number>
lsof -i :<port-number>

# Check Docker daemon
sudo systemctl status docker

# Restart Docker daemon (Linux)
sudo systemctl restart docker
```

### Service Not Healthy
```bash
# Check health check logs
docker inspect -f '{{range .State.Health.Log}}{{.Output}}{{end}}' <container-name>

# Test health endpoint manually
docker exec <container-name> curl -f http://localhost:8000/health

# Check dependencies
docker compose ps
```

### Connection Issues Between Services
```bash
# Test connectivity
docker exec crypto-bot-trading ping crypto-bot-market-data

# Check DNS resolution
docker exec crypto-bot-trading nslookup crypto-bot-postgres

# Check network
docker network inspect crypto-bot-network

# Verify environment variables
docker exec crypto-bot-trading env | grep URL
```

### Performance Issues
```bash
# Check resource usage
docker stats --no-stream

# Check container logs for errors
docker compose logs --tail=100 | grep -i error

# Check disk space
df -h
docker system df

# Check memory
free -h

# Restart resource-heavy services
docker restart crypto-bot-ml-prediction crypto-bot-ta
```

### Reset Specific Service
```bash
# Complete service reset
docker compose stop <service-name>
docker compose rm -f <service-name>
docker compose up -d <service-name>

# Or use automation
./scripts/deploy.sh rebuild <service-name>
```

### Complete System Reset
```bash
# WARNING: This will destroy all data!
./scripts/deploy.sh reset

# Manual reset
docker compose down -v
cd infrastructure/
docker compose down -v
docker system prune -a -f --volumes
```

---

## Environment-Specific Commands

**The canonical compose file is `docker-compose.unified.yml` (ADR-009).** The old plain `docker-compose.yml` could not boot on its own (no postgres/timescaledb/redis/rabbitmq) and carried pre-ADR risk values; it was renamed to `docker-compose.legacy.yml.DISABLED` — do not resurrect it. Always pass `-f docker-compose.unified.yml` explicitly; a bare `docker compose up` no longer finds a config file, by design.

### Development Environment
```bash
# Start the full stack
docker compose -f docker-compose.unified.yml up -d

# Rebuild one service (BuildKit hangs on WSL2 — disable it)
DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml up -d --build <service>
```

### Production Environment
```bash
# Start with production overrides
docker compose -f docker-compose.unified.yml -f docker-compose.prod.yml up -d
```

---

## Useful Aliases

Add these to your `~/.bashrc` or `~/.zshrc`:

```bash
# Docker compose shortcuts
alias dc='docker compose'
alias dcu='docker compose up -d'
alias dcd='docker compose down'
alias dcl='docker compose logs -f'
alias dcp='docker compose ps'

# Docker shortcuts
alias dps='docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"'
alias dlog='docker logs -f'
alias dex='docker exec -it'
alias dstats='docker stats --no-stream'

# Crypto bot specific
alias cb-start='./scripts/deploy.sh start'
alias cb-stop='./scripts/deploy.sh stop'
alias cb-restart='./scripts/deploy.sh restart'
alias cb-health='./scripts/health-check-monitor.sh -c'
alias cb-logs='docker compose logs -f'
alias cb-status='./scripts/deploy.sh status'
```

---

## Service Port Reference

| Service | Port | Health Endpoint |
|---------|------|-----------------|
| API Gateway | 8000 | http://localhost:8000/health |
| Bybit Connector | 8001 | http://localhost:8001/health |
| Market Data | 8002 | http://localhost:8002/health |
| Portfolio Manager | 8003 | http://localhost:8003/health |
| Technical Analysis | 8004 | http://localhost:8004/health |
| Trading Engine | 8005 | http://localhost:8005/health |
| Notification Service | 8006 | http://localhost:8006/health |
| ML Prediction | 8007 | http://localhost:8007/health |
| Sentiment Analysis | 8008 | http://localhost:8008/health |
| Risk Metrics | 8009 | http://localhost:8009/health |
| PostgreSQL | 5432 | Internal only |
| TimescaleDB | 5433 | Internal only |
| Redis | 6379 | Internal only |
| RabbitMQ | 5672 | http://localhost:15672 |
| Prometheus | 9090 | http://localhost:9090 |
| Grafana | 3001 | http://localhost:3001 |

---

## Additional Resources

- **Automation Scripts**: `/scripts/deploy.sh` and `/scripts/health-check-monitor.sh`
- **Docker Compose Files**: `/docker-compose.unified.yml` (canonical, ADR-009) and `/infrastructure/docker-compose.yml` (infra-only). The old `/docker-compose.yml` was renamed to `/docker-compose.legacy.yml.DISABLED`
- **Optimized Dockerfile Template**: `/Dockerfile.optimized.template`
- **Logs Directory**: `/logs/`
- **Backups Directory**: `/backups/`

---

## Best Practices

1. **Always use automation scripts** for common operations
2. **Run health checks** after any deployment operation
3. **Create backups** before major changes
4. **Monitor resource usage** regularly
5. **Clean up unused resources** periodically
6. **Use proper logging** for debugging
7. **Keep images updated** with security patches
8. **Use volumes** for persistent data
9. **Implement health checks** in all services
10. **Document** all custom configurations

---

**Last Updated**: 2025-11-19
**Maintained By**: DevOps Automation Agent
**Version**: 1.0
