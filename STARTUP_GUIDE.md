# Crypto Trading Bot - Startup Guide

## Quick Start

```bash
# Start all services
docker-compose up -d

# Open dashboard
http://localhost:3000
```

---

## Prerequisites

Before starting the system, ensure you have:

- **Docker Desktop** installed and running
- **Docker Compose** v2.0+
- **Node.js** v18+ (for frontend development only)
- **Git** (optional, for updates)

### Verify Docker is Running

```bash
docker --version
docker-compose --version
docker ps  # Should show no errors
```

---

## Starting the System

### Option 1: Start Everything (Recommended)

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot
docker-compose up -d
```

This starts all 15 services:
- Infrastructure (PostgreSQL, TimescaleDB, Redis, RabbitMQ)
- Backend services (8 microservices)
- Frontend dashboard

### Option 2: Start Services Individually

```bash
# Start infrastructure first
docker-compose up -d postgres timescaledb redis rabbitmq

# Wait 30 seconds for databases to initialize
sleep 30

# Start backend services
docker-compose up -d bybit-connector market-data portfolio-manager
docker-compose up -d technical-analysis trading-engine notification-service
docker-compose up -d ml-prediction sentiment-analysis risk-metrics

# Start API gateway and frontend
docker-compose up -d api-gateway frontend
```

### Option 3: Start with Logs Visible

```bash
# Start and watch logs in real-time
docker-compose up

# Press Ctrl+C to stop watching (services keep running)
# Or Ctrl+C twice to stop everything
```

---

## Verify System is Running

### Check All Containers

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Expected output - all should show "Up" and "(healthy)":

| Service | Port | Status |
|---------|------|--------|
| crypto-bot-frontend | 3000 | healthy |
| crypto-bot-api-gateway | 8000 | healthy |
| crypto-bot-bybit | 8001 | healthy |
| crypto-bot-market-data | 8002 | healthy |
| crypto-bot-portfolio | 8003 | healthy |
| crypto-bot-ta | 8004 | healthy |
| crypto-bot-trading | 8005 | healthy |
| crypto-bot-notification | 8006 | healthy |
| crypto-bot-ml-prediction | 8007 | healthy |
| crypto-bot-sentiment | 8008 | healthy |
| crypto-bot-risk-metrics | 8009 | healthy |

### Quick Health Check

```bash
# Check all service health endpoints
curl -s http://localhost:8000/health  # API Gateway
curl -s http://localhost:8001/health  # Bybit Connector
curl -s http://localhost:8002/health  # Market Data
curl -s http://localhost:8003/health  # Portfolio
curl -s http://localhost:8004/health  # Technical Analysis
curl -s http://localhost:8005/health  # Trading Engine
curl -s http://localhost:8008/health  # Sentiment Analysis
curl -s http://localhost:3000/health  # Frontend
```

---

## Access Points

| Component | URL | Description |
|-----------|-----|-------------|
| **Dashboard** | http://localhost:3000 | Main trading interface |
| **API Gateway** | http://localhost:8000 | REST API endpoint |
| **API Docs** | http://localhost:8000/docs | Swagger documentation |
| **RabbitMQ** | http://localhost:15672 | Message queue UI (guest/guest) |

---

## Stopping the System

### Stop All Services (Keep Data)

```bash
docker-compose stop
```

### Stop and Remove Containers (Keep Data)

```bash
docker-compose down
```

### Stop and Remove Everything (Including Data)

```bash
# WARNING: This deletes all data!
docker-compose down -v
```

---

## Restarting Services

### Restart a Single Service

```bash
docker-compose restart frontend
docker-compose restart api-gateway
docker-compose restart sentiment-analysis
```

### Restart All Services

```bash
docker-compose restart
```

### Rebuild and Restart a Service

```bash
# If you made code changes
docker-compose build <service-name>
docker-compose up -d <service-name>

# Example for frontend
cd frontend && npm run build && cd ..
docker-compose build frontend
docker-compose up -d frontend
```

---

## Viewing Logs

### View Logs for All Services

```bash
docker-compose logs -f
```

### View Logs for Specific Service

```bash
docker-compose logs -f frontend
docker-compose logs -f api-gateway
docker-compose logs -f trading-engine
docker-compose logs -f sentiment-analysis
```

### View Last 100 Lines

```bash
docker-compose logs --tail 100 <service-name>
```

---

## Troubleshooting

### Service Won't Start

```bash
# Check logs for errors
docker-compose logs <service-name>

# Rebuild the service
docker-compose build --no-cache <service-name>
docker-compose up -d <service-name>
```

### Port Already in Use

```bash
# Find what's using the port (e.g., 3000)
netstat -ano | findstr :3000  # Windows
lsof -i :3000                  # Linux/Mac

# Stop conflicting service or change port in docker-compose.yml
```

### Database Connection Issues

```bash
# Restart database services
docker-compose restart postgres timescaledb redis

# Wait for them to be healthy
docker-compose ps
```

### Clear Everything and Start Fresh

```bash
# Stop all containers
docker-compose down -v

# Remove all images (optional)
docker system prune -a

# Start fresh
docker-compose up -d
```

---

## Service Ports Reference

| Service | Internal Port | External Port |
|---------|--------------|---------------|
| Frontend | 80 | 3000 |
| API Gateway | 8000 | 8000 |
| Bybit Connector | 8001 | 8001 |
| Market Data | 8002 | 8002 |
| Portfolio Manager | 8003 | 8003 |
| Technical Analysis | 8004 | 8004 |
| Trading Engine | 8005 | 8005 |
| Notification | 8006 | 8006 |
| ML Prediction | 8007 | 8007 |
| Sentiment Analysis | 8008 | 8008 |
| Risk Metrics | 8009 | 8009 |
| PostgreSQL | 5432 | - |
| TimescaleDB | 5432 | 5433 |
| Redis | 6379 | - |
| RabbitMQ | 5672/15672 | 5672/15672 |

---

## Environment Configuration

### API Keys (Optional)

Edit `.env` files in each service directory to add real API keys:

```bash
# services/bybit-connector/.env
BYBIT_API_KEY=your_api_key
BYBIT_API_SECRET=your_api_secret
BYBIT_TESTNET=true

# services/sentiment-analysis-service/.env
NEWS_API_KEY=your_newsapi_key
TWITTER_BEARER_TOKEN=your_twitter_token
```

### Trading Mode

By default, the system runs in **paper trading mode** (no real money).

To enable live trading (after thorough testing):
1. Set `BYBIT_TESTNET=false` in bybit-connector
2. Use mainnet API keys
3. Configure risk limits in trading-engine

---

## Daily Operations

### Morning Startup

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot
docker-compose up -d
# Wait 1-2 minutes for all services to initialize
# Open http://localhost:3000
```

### End of Day Shutdown

```bash
docker-compose stop
```

### Check System Status

```bash
# Quick status check
docker ps --format "table {{.Names}}\t{{.Status}}"

# Check for any unhealthy services
docker ps --filter "health=unhealthy"
```

---

## Need Help?

- Check service logs: `docker-compose logs -f <service>`
- View API docs: http://localhost:8000/docs
- Check this guide for common issues

---

*Last Updated: November 2025*
