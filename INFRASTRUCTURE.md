# Crypto Trading Bot - Infrastructure Guide

## Quick Start

```bash
# Start all services
docker-compose -f docker-compose.unified.yml up -d

# Start with monitoring (Prometheus + Grafana)
docker-compose -f docker-compose.unified.yml --profile monitoring up -d
```

## Architecture Overview

```
                    ┌─────────────────────────────────────────────────────────────┐
                    │                     FRONTEND                                 │
                    │                   (React Dashboard)                          │
                    │                     Port: 3000                               │
                    └────────────────────────┬────────────────────────────────────┘
                                             │
                    ┌────────────────────────▼────────────────────────────────────┐
                    │                   API GATEWAY                                │
                    │                    Port: 8000                                │
                    └──┬───────┬───────┬───────┬───────┬───────┬───────┬───────┬──┘
                       │       │       │       │       │       │       │       │
          ┌────────────▼──┐ ┌──▼──┐ ┌──▼──┐ ┌──▼──┐ ┌──▼──┐ ┌──▼──┐ ┌──▼──┐ ┌──▼──┐
          │    Bybit      │ │Mkt  │ │Port │ │ TA  │ │Trade│ │Notif│ │ ML  │ │Sent │
          │   Connector   │ │Data │ │Mgr  │ │     │ │Eng  │ │     │ │Pred │ │Anlys│
          │    :8001      │ │:8002│ │:8003│ │:8004│ │:8005│ │:8006│ │:8007│ │:8008│
          └───────────────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘
                       │       │       │       │       │       │       │       │
                    ┌──▼───────▼───────▼───────▼───────▼───────▼───────▼───────▼──┐
                    │              INFRASTRUCTURE LAYER                            │
                    │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │
                    │  │PostgreSQL│ │TimescaleDB│ │  Redis   │ │ RabbitMQ │        │
                    │  │  :5432   │ │   :5433   │ │  :6379   │ │  :5672   │        │
                    │  └──────────┘ └──────────┘ └──────────┘ └──────────┘        │
                    └─────────────────────────────────────────────────────────────┘
```

## Services

### Infrastructure Services

| Service | Port | Description |
|---------|------|-------------|
| PostgreSQL | 5432 | Main application database |
| TimescaleDB | 5433 | Time-series database for market data |
| Redis | 6379 | Caching and session storage |
| RabbitMQ | 5672, 15672 | Message broker |

### Application Services

| Service | Port | Description |
|---------|------|-------------|
| API Gateway | 8000 | Entry point for all API requests |
| Bybit Connector | 8001 | Exchange API integration |
| Market Data | 8002 | Real-time market data collection |
| Portfolio Manager | 8003 | Balance and position tracking |
| Technical Analysis | 8004 | Trading indicators (RSI, MACD, etc.) |
| Trading Engine | 8005 | Core trading logic |
| Notification | 8006 | Alerts and notifications |
| ML Prediction | 8007 | LSTM price forecasting |
| Sentiment Analysis | 8008 | News and social sentiment |
| Risk Metrics | 8009 | Risk analysis |
| Frontend | 3000 | React dashboard |

### Monitoring (Optional)

| Service | Port | Description |
|---------|------|-------------|
| Prometheus | 9090 | Metrics collection |
| Grafana | 3001 | Metrics visualization |

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Key variables:
- `BYBIT_API_KEY` / `BYBIT_API_SECRET` - Exchange credentials
- `BYBIT_TESTNET=true` - Use testnet (recommended for testing)
- `PAPER_TRADING_MODE=true` - No real trades
- `NEWS_API_KEY` - For sentiment analysis

### Network Configuration

All services communicate over the `crypto-bot-network` bridge network.

## Commands

### Start/Stop

```bash
# Start all services
docker-compose -f docker-compose.unified.yml up -d

# Stop all services
docker-compose -f docker-compose.unified.yml down

# Restart a specific service
docker-compose -f docker-compose.unified.yml restart sentiment-analysis

# View logs
docker-compose -f docker-compose.unified.yml logs -f api-gateway
```

### Health Checks

```bash
# Check all service health
for port in 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009 3000; do
  echo -n "Port $port: "
  curl -s "http://localhost:$port/health" | jq -r '.status // "error"'
done
```

### Rebuild Services

```bash
# Rebuild a single service
docker-compose -f docker-compose.unified.yml build api-gateway
docker-compose -f docker-compose.unified.yml up -d api-gateway

# Rebuild all services (no cache)
docker-compose -f docker-compose.unified.yml build --no-cache
docker-compose -f docker-compose.unified.yml up -d
```

## Migration from Old Setup

If migrating from the old dual docker-compose setup:

```bash
./scripts/migrate-infrastructure.sh
```

## Troubleshooting

### Service Won't Start

```bash
# Check logs
docker-compose -f docker-compose.unified.yml logs service-name

# Check if port is in use
netstat -tulpn | grep :8000
```

### Database Connection Issues

```bash
# Test PostgreSQL connection
docker exec crypto-bot-postgres pg_isready -U cryptobot

# Test Redis connection
docker exec crypto-bot-redis redis-cli ping
```

### Clear Everything and Start Fresh

```bash
# Stop and remove all containers and volumes
docker-compose -f docker-compose.unified.yml down -v

# Remove all images
docker system prune -a

# Start fresh
docker-compose -f docker-compose.unified.yml up -d
```

## Access Points

| Component | URL |
|-----------|-----|
| Dashboard | http://localhost:3000 |
| API Gateway | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| RabbitMQ Management | http://localhost:15672 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3001 |

## Resource Requirements

Minimum recommended:
- CPU: 4 cores
- RAM: 8GB
- Disk: 20GB

For ML prediction service with full models:
- RAM: 16GB recommended
