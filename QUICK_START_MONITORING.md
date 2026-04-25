# 🚀 Quick Start Monitoring Guide

## ✅ System Status: FULLY OPERATIONAL

All 11 services and 4 infrastructure components are healthy and running!

## 📊 Live Data Confirmed

### Market Data (Working ✅)
```bash
# Get Bitcoin price
curl http://localhost:8002/api/v1/ticker/BTCUSDT | python3 -m json.tool

# Real data example:
# {
#   "success": true,
#   "data": {
#     "symbol": "BTCUSDT",
#     "last_price": 92859.3,
#     "high_24h": 93931.1,
#     "low_24h": 86604.2,
#     "volume_24h": 118503.48
#   }
# }
```

### Trading Signals (Working ✅)
```bash
# Get Phase 1 metrics
curl "http://localhost:8005/api/v1/phase1/metrics?hours=24" | python3 -m json.tool

# Returns: 91 signals processed, all HOLD (bearish trend)
```

### System Health (Working ✅)
```bash
# Get system health
curl http://localhost:8005/api/v1/phase1/health | python3 -m json.tool

# Status: healthy, all filters active
```

---

## 🎯 Quick Monitoring Commands

### 1. Master Dashboard (Recommended)
```bash
cd /mnt/d/Bimo_max/crypto-trading-bot
./monitor_dashboard.sh
```
**Shows**: Live status of all services, prices, resources, and errors

### 2. System Monitor
```bash
./monitor_system.sh
```
**Shows**: Health checks, Docker status, system resources

### 3. Trading Activity
```bash
./monitor_trading.sh
```
**Shows**: Portfolio, positions, signals, orders, risk metrics

### 4. Performance Metrics
```bash
./monitor_performance.sh
```
**Shows**: API response times, CPU/memory usage, database stats

### 5. Live Logs
```bash
./monitor_logs.sh
```
**Shows**: Color-coded real-time logs from all services

---

## 🌐 Access Points

### Frontend Dashboard
```
http://localhost:3000
```

### API Gateway
```
http://localhost:8000
```

### Individual Services
- Bybit Connector: http://localhost:8001
- Market Data: http://localhost:8002
- Portfolio Manager: http://localhost:8003
- Technical Analysis: http://localhost:8004
- Trading Engine: http://localhost:8005
- Notification: http://localhost:8006
- ML Prediction: http://localhost:8007
- Sentiment Analysis: http://localhost:8008
- Risk Metrics: http://localhost:8009

### Grafana Dashboards
```
http://localhost:3001
Username: admin
Password: admin
```

### RabbitMQ Management
```
http://localhost:15672
Username: guest
Password: guest
```

---

## 📈 Test Market Data

```bash
# Get live prices for multiple symbols
for symbol in BTCUSDT ETHUSDT SOLUSDT BNBUSDT; do
  echo "=== $symbol ==="
  curl -s "http://localhost:8002/api/v1/ticker/$symbol" | python3 -m json.tool
  echo ""
done
```

---

## 🔧 Quick Fixes

### If services show unhealthy:
```bash
# Restart databases
docker start crypto-bot-postgres crypto-bot-timescaledb crypto-bot-redis crypto-bot-rabbitmq

# Wait 30 seconds
sleep 30

# Restart services
docker restart crypto-bot-trading crypto-bot-portfolio crypto-bot-market-data
```

### If frontend shows no data:
```bash
# Check browser console (F12)
# Verify CORS is not blocking requests
# Test API directly:
curl http://localhost:8002/api/v1/ticker/BTCUSDT
```

---

## 📊 Current System State

**Services**: 11/11 healthy (100%)
**Infrastructure**: 4/4 running
**Market Data**: ✅ Real-time from Bybit
**Trading Signals**: ✅ 91 signals processed
**Filters**: ✅ All active (Gatekeeper, Validator, ATR)

**Current Market Conditions**:
- BTC: $92,859 (-7.2% from ATH)
- Trend: Bearish (64/91 signals)
- Strategy: HOLD signals (risk management active)

---

## 🎮 Interactive Monitoring

For continuous monitoring, run the dashboard:

```bash
./monitor_dashboard.sh
```

**Features**:
- ⏱️ Auto-refresh every 10 seconds
- 🎨 Color-coded status indicators
- ⚡ Real-time API response times
- 📊 Live market prices
- 💰 Portfolio tracking
- ⚠️ Error detection

**Controls**:
- `R` - Refresh now
- `Q` - Quit
- `S` - Switch to system monitor
- `T` - Switch to trading monitor
- `P` - Switch to performance monitor

---

## 📝 Logging

All services log to:
- **Console**: `docker logs crypto-bot-[service-name]`
- **Files**: `services/[service-name]/logs/`

Aggregate logs:
```bash
./monitor_logs.sh  # All critical services
```

---

## 🆘 Support

For issues:
1. Check `./monitor_system.sh` for service health
2. View logs: `docker logs crypto-bot-[service]`
3. Restart service: `docker restart crypto-bot-[service]`
4. Full reset: `docker-compose restart`

---

**System Monitoring Active** ✅
**Last Updated**: 2025-12-03 10:45 UTC
**Status**: All systems operational
