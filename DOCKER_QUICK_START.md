# Docker Infrastructure - Quick Start Guide

## Instant Commands

### Build Everything
```bash
cd /mnt/d/Bimo_max/crypto-trading-bot

# Sequential build (slower, safer)
./build-all.sh

# Parallel build (faster)
./build-all.sh --parallel

# Clean build (no cache)
./build-all.sh --no-cache
```

### Development Environment
```bash
# Start all services
./docker-dev.sh start -d

# Check status
./docker-dev.sh status

# Check health
./docker-dev.sh health

# View logs
./docker-dev.sh logs api-gateway -f

# Restart
./docker-dev.sh restart

# Stop
./docker-dev.sh stop
```

### Production Deployment
```bash
# 1. Setup environment
cp .env.production.example .env.production
nano .env.production  # Edit with your values

# 2. Build images
VERSION=1.0.0 ./build-all.sh

# 3. Deploy
docker-compose -f docker-compose.prod.yml --env-file .env.production up -d

# 4. Check health
./docker-dev.sh health
```

## Service Ports

| Service | Port | Purpose |
|---------|------|---------|
| api-gateway | 8000 | Main API entry point |
| trading-engine | 8001 | Core trading logic |
| portfolio-manager | 8002 | Position tracking |
| technical-analysis | 8003 | Trading indicators |
| bybit-connector | 8004 | Exchange API |
| market-data-service | 8005 | Market data collection |
| notification-service | 8006 | Alerts |
| ml-prediction-service | 8007 | ML predictions |
| risk-metrics-service | 8008 | Risk analysis |
| sentiment-analysis-service | 8009 | Sentiment analysis |

## Health Check

```bash
# Check all services
for port in 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009; do
    echo -n "Port $port: "
    curl -sf http://localhost:$port/health && echo "OK" || echo "FAIL"
done
```

## Troubleshooting

**Services won't start:**
```bash
docker-compose logs SERVICE_NAME
docker-compose restart SERVICE_NAME
```

**Port conflicts:**
```bash
# Check what's using the port
sudo netstat -tulpn | grep :8000
# or
sudo lsof -i :8000
```

**Clean everything:**
```bash
./docker-dev.sh clean
```

**Rebuild single service:**
```bash
docker-compose build api-gateway
docker-compose up -d api-gateway
```

## File Locations

```
/mnt/d/Bimo_max/crypto-trading-bot/
├── services/
│   ├── api-gateway/Dockerfile
│   ├── trading-engine/Dockerfile
│   ├── portfolio-manager/Dockerfile
│   ├── technical-analysis/Dockerfile
│   ├── bybit-connector/Dockerfile
│   ├── market-data-service/Dockerfile
│   ├── notification-service/Dockerfile
│   ├── ml-prediction-service/Dockerfile
│   ├── risk-metrics-service/Dockerfile
│   └── sentiment-analysis-service/Dockerfile
├── build-all.sh                  # Build automation
├── docker-dev.sh                 # Dev environment helper
├── docker-compose.yml            # Development compose
├── docker-compose.prod.yml       # Production compose
├── .dockerignore                 # Build exclusions
└── .env.production.example       # Config template
```

## What Was Built

- **10 Production Dockerfiles** - Multi-stage, optimized, secure
- **Build Automation** - Parallel builds, push to registry
- **Production Compose** - Resource limits, health checks, logging
- **Dev Tools** - Quick start/stop/status/logs/health
- **Security** - Non-root users, minimal images, secrets management

## Next Steps

1. **Test locally:** `./docker-dev.sh start -d && ./docker-dev.sh health`
2. **Configure production:** `cp .env.production.example .env.production`
3. **Build images:** `./build-all.sh`
4. **Deploy:** Use docker-compose.prod.yml
5. **Monitor:** Setup Prometheus/Grafana (docker-compose.monitoring.yml)
6. **Scale:** Move to Kubernetes for production

## Support

- **Full Documentation:** `DOCKER_INFRASTRUCTURE_COMPLETE.md`
- **Issues:** Check service logs with `./docker-dev.sh logs SERVICE_NAME`
- **Health:** Run `./docker-dev.sh health` regularly
