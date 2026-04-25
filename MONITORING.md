# 🔍 System Monitoring Guide

## Quick Start

The crypto trading bot includes comprehensive monitoring tools. All services are currently **FULLY OPERATIONAL** (11/11 healthy).

## Monitoring Scripts

### 1. System Monitor (`monitor_system.sh`)
**Real-time overview of all services and infrastructure**

```bash
# Single check
./monitor_system.sh

# Continuous monitoring (refreshes every 5 seconds)
./monitor_system.sh --continuous
```

**Monitors:**
- ✅ Docker container health status
- 📊 Service health endpoints (all 11 services)
- 💻 CPU & memory usage per container
- 📝 Recent error logs from critical services
- 🎯 System status summary (100% operational)

---

### 2. Trading Activity Monitor (`monitor_trading.sh`)
**Focus on trading operations, positions, and signals**

```bash
# Single check
./monitor_trading.sh

# Continuous monitoring (refreshes every 10 seconds)
./monitor_trading.sh --continuous
```

**Monitors:**
- 💰 Portfolio summary (balance, equity, P&L)
- 📈 Active trading positions
- 📊 Recent trading signals (BUY/SELL/HOLD)
- 💵 Current market prices for major pairs
- ⚙️ Trading engine status
- 📋 Recent order history
- ⚠️ Risk metrics and exposure

---

### 3. Live Log Monitor (`monitor_logs.sh`)
**Aggregate real-time logs from all services**

```bash
# Monitor all critical services
./monitor_logs.sh

# Monitor specific service
./monitor_logs.sh crypto-bot-trading
```

**Features:**
- 🎨 Color-coded by service
- 📝 Real-time log streaming
- 🔍 Easy to spot errors and warnings
- 🏷️ Service name prefixed on each line

**Services monitored:**
- [TRADING] - Trading Engine
- [PORTFOLIO] - Portfolio Manager
- [BYBIT] - Bybit Connector
- [MARKET-DATA] - Market Data Service
- [TECH-ANALYSIS] - Technical Analysis

---

### 4. Performance Monitor (`monitor_performance.sh`)
**API response times and resource metrics**

```bash
# Single performance check
./monitor_performance.sh

# Continuous monitoring (refreshes every 5 seconds)
./monitor_performance.sh --continuous
```

**Monitors:**
- ⚡ API response times (ms) for all endpoints
- 🎯 Color-coded performance (Green <50ms, Yellow <100ms, Red >100ms)
- 💻 CPU and memory usage per service
- 🌐 Network I/O statistics
- 🗄️ Database connection counts
- 📊 Redis memory usage
- 📮 RabbitMQ queue status
- 💪 System load average

---

## Service Endpoints

### Main Services
| Service | Port | Health Check | Purpose |
|---------|------|--------------|---------|
| API Gateway | 8000 | `http://localhost:8000/health` | Main entry point, routing |
| Bybit Connector | 8001 | `http://localhost:8001/health` | Exchange API integration |
| Market Data | 8002 | `http://localhost:8002/health` | Price data, candles, orderbook |
| Portfolio Manager | 8003 | `http://localhost:8003/health` | Positions, balance, P&L |
| Technical Analysis | 8004 | `http://localhost:8004/health` | Indicators, signals |
| Trading Engine | 8005 | `http://localhost:8005/health` | Strategy execution |
| Notification | 8006 | `http://localhost:8006/health` | Alerts and notifications |
| ML Prediction | 8007 | `http://localhost:8007/health` | AI price predictions |
| Sentiment Analysis | 8008 | `http://localhost:8008/health` | Market sentiment scoring |
| Risk Metrics | 8009 | `http://localhost:8009/health` | Risk calculations |
| Frontend | 3000 | `http://localhost:3000` | Web dashboard |

### Infrastructure
| Service | Port | Purpose |
|---------|------|---------|
| PostgreSQL | 5432 | Main database |
| TimescaleDB | 5433 | Time-series data |
| Redis | 6379 | Caching |
| RabbitMQ | 5672, 15672 | Message queue |

---

## Health Check Commands

### Quick health check all services
```bash
for port in 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009 3000; do
    status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$port/health 2>/dev/null)
    if [ "$status" = "200" ]; then
        echo "✅ Port $port: HEALTHY"
    else
        echo "❌ Port $port: UNHEALTHY ($status)"
    fi
done
```

### Check specific service logs
```bash
docker logs --tail 50 crypto-bot-trading
docker logs --tail 50 crypto-bot-portfolio
docker logs --tail 50 crypto-bot-market-data
```

### View service resource usage
```bash
docker stats crypto-bot-trading
docker stats --no-stream | grep crypto-bot
```

---

## Common Issues & Fixes

### Issue: Services showing unhealthy
**Fix:**
```bash
# 1. Check if databases are running
docker ps | grep -E "postgres|redis|rabbit|timescale"

# 2. Restart databases if needed
docker start crypto-bot-postgres crypto-bot-timescaledb crypto-bot-redis crypto-bot-rabbitmq

# 3. Wait 30 seconds for services to reconnect
sleep 30

# 4. Check health again
./monitor_system.sh
```

### Issue: Log permission errors
**Fix:**
```bash
# Fix log directory permissions
find services/ -type d -name "logs" -exec chmod -R 777 {} \;

# Restart affected services
docker restart crypto-bot-api-gateway crypto-bot-portfolio
```

### Issue: Service won't start
**Fix:**
```bash
# Check container logs
docker logs crypto-bot-[service-name]

# Restart specific service
docker restart crypto-bot-[service-name]

# Full restart if needed
docker-compose restart
```

### Issue: No market data available
**Fix:**
```bash
# Check market data service
curl http://localhost:8002/health

# Check if Bybit connector is working
curl http://localhost:8001/health

# Restart market data service
docker restart crypto-bot-market-data
```

---

## Monitoring Best Practices

### Daily Checks
Run these checks daily:
```bash
# 1. System overview
./monitor_system.sh

# 2. Trading activity
./monitor_trading.sh

# 3. Performance metrics
./monitor_performance.sh
```

### Before Trading
Before enabling live trading:
```bash
# Verify all services are healthy
./monitor_system.sh | grep "FULLY OPERATIONAL"

# Check trading engine status
curl http://localhost:8005/api/v1/status

# Verify portfolio connection
curl http://localhost:8003/api/v1/portfolio/summary

# Test order placement (paper trading)
curl -X POST http://localhost:8005/api/v1/orders/paper -H "Content-Type: application/json" -d '{
  "symbol": "BTCUSDT",
  "side": "BUY",
  "qty": 0.001
}'
```

### Continuous Monitoring
For 24/7 operation, run in separate terminals:
```bash
# Terminal 1: System monitor
./monitor_system.sh --continuous

# Terminal 2: Trading activity
./monitor_trading.sh --continuous

# Terminal 3: Live logs
./monitor_logs.sh

# Terminal 4: Performance
./monitor_performance.sh --continuous
```

---

## Alert Thresholds

### Critical Alerts (Immediate Action Required)
- ❌ Any service health check fails
- ❌ Database connection lost
- ❌ Trading engine errors
- ❌ Portfolio manager unreachable
- ❌ API response time > 500ms
- ❌ Memory usage > 90%
- ❌ Unexpected position changes

### Warning Alerts (Monitor Closely)
- ⚠️ API response time > 100ms
- ⚠️ Memory usage > 75%
- ⚠️ CPU usage > 80%
- ⚠️ Unusual trading volumes
- ⚠️ Signal conflicts

---

## Prometheus & Grafana Integration

### Access Prometheus
```bash
# Prometheus UI
http://localhost:9090

# Check targets
http://localhost:9090/targets
```

### Access Grafana
```bash
# Grafana UI
http://localhost:3001

# Default credentials
Username: admin
Password: admin
```

### Pre-configured Dashboards
1. **System Overview** - All services health
2. **Trading Performance** - P&L, positions, orders
3. **Market Data** - Price charts, volumes
4. **Resource Usage** - CPU, memory, network
5. **API Metrics** - Response times, error rates

---

## Emergency Procedures

### Emergency Stop
```bash
# Stop all trading immediately
curl -X POST http://localhost:8005/api/v1/emergency-stop

# Close all positions
curl -X POST http://localhost:8005/api/v1/close-all-positions

# Stop all services
docker-compose stop
```

### Full System Restart
```bash
# Stop everything
docker-compose down

# Start infrastructure first
docker start crypto-bot-postgres crypto-bot-timescaledb crypto-bot-redis crypto-bot-rabbitmq

# Wait for databases
sleep 30

# Start services
docker-compose up -d

# Verify health
./monitor_system.sh
```

---

## Support & Troubleshooting

For issues not covered here:
1. Check service logs: `docker logs crypto-bot-[service-name]`
2. Review `docs/TROUBLESHOOTING.md`
3. Check recent changes: `git log --oneline -20`
4. Restore from backup if needed

---

**Last Updated:** 2025-12-03
**System Status:** ✅ FULLY OPERATIONAL (11/11 services)
**Monitoring Version:** 1.0.0
