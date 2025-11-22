# Crypto Trading Bot - Quick Reference Card

**Version:** 1.0.0 | **Last Updated:** 2025-11-14

---

## 🚀 Essential Commands

### **Daily Operations**

```bash
# Morning Startup (5 minutes)
./scripts/daily_startup.sh

# Quick Status Check (10 seconds)
./scripts/quick_check.sh

# Evening Shutdown (3 minutes)
./scripts/daily_shutdown.sh
```

### **System Management**

```bash
# Start System
./scripts/startup.sh                    # Full startup with build
./scripts/startup.sh --skip-build       # Fast restart (3 min)

# Health Check
./scripts/health_check.sh               # Quick check
./scripts/health_check.sh --verbose     # Detailed check

# Risk Validation
python3 scripts/validate_risk_limits.py --verbose

# Continuous Monitoring
python3 scripts/monitor.py --interval 60  # 1-minute checks
```

### **Maintenance & Utilities**

```bash
# Database Backup
./scripts/backup.sh                      # Quick backup
./scripts/backup.sh --full               # Full backup (includes logs)

# Log Cleanup
./scripts/cleanup_logs.sh --days 7       # Clean logs older than 7 days
./scripts/cleanup_logs.sh --dry-run      # Preview cleanup

# Database Optimization
./scripts/optimize_database.sh --analyze              # Daily (fast)
./scripts/optimize_database.sh --vacuum --analyze     # Weekly
./scripts/optimize_database.sh --all                  # Monthly (complete)

# Performance Reports
./scripts/generate_performance_report.sh --period daily --format txt
./scripts/generate_performance_report.sh --period weekly --format html

# System Status Report
./scripts/system_status_report.sh                     # Display
./scripts/system_status_report.sh --save ~/status.txt # Save to file
./scripts/system_status_report.sh --email you@domain.com  # Email
```

---

## 📊 Dashboard & APIs

| Service | URL | Purpose |
|---------|-----|---------|
| **Dashboard** | http://localhost:8080 | Real-time monitoring |
| **Trading Engine** | http://localhost:8005/docs | Trading API docs |
| **API Gateway** | http://localhost:8000/docs | Gateway API docs |
| **Portfolio** | http://localhost:8003/docs | Portfolio API docs |

---

## 🎛️ Trading Controls

### **Start/Stop Trading**

```bash
# Start auto-trading
curl -X POST http://localhost:8005/api/v1/start

# Stop auto-trading
curl -X POST http://localhost:8005/api/v1/stop

# Emergency stop (immediate halt)
curl -X POST http://localhost:8005/api/v1/emergency/stop

# Close all positions
curl -X POST http://localhost:8005/api/v1/emergency/close-all
```

### **Check Status**

```bash
# Trading status
curl -s http://localhost:8005/api/v1/status | jq

# Portfolio balance
curl -s http://localhost:8003/api/v1/balance | jq

# Open positions
curl -s http://localhost:8005/api/v1/positions?status=open | jq

# Daily performance
curl -s http://localhost:8003/api/v1/performance/daily | jq
```

---

## 🔍 Monitoring & Logs

### **View Logs**

```bash
# All services
docker-compose logs

# Specific service
docker-compose logs -f trading-engine

# Tail recent logs
docker-compose logs --tail 50 portfolio-manager

# Monitor logs
tail -f /tmp/monitor_$(date +%Y%m%d).log

# Startup logs
tail -f /tmp/startup_$(date +%Y%m%d).log
```

### **Service Status**

```bash
# Container status
docker-compose ps

# Service health (all 10)
for port in {8000..8009}; do
  curl -s http://localhost:$port/health | jq '.status'
done

# Quick service check
./scripts/quick_check.sh
```

---

## 🛠️ Troubleshooting

### **Service Issues**

```bash
# Restart specific service
docker-compose restart [service-name]

# Rebuild service
docker-compose build [service-name]
docker-compose up -d [service-name]

# Check service logs
docker-compose logs --tail 100 [service-name]

# Restart all services
docker-compose restart
```

### **Complete Recovery**

```bash
# Full system restart
docker-compose down
./scripts/startup.sh

# Nuclear option (clean rebuild)
docker-compose down -v
docker-compose build --no-cache
./scripts/startup.sh
```

### **Common Issues**

| Issue | Solution |
|-------|----------|
| Port already in use | `lsof -i :8000` to find process, kill it |
| Service won't start | Check logs: `docker-compose logs [service]` |
| Health check fails | Restart: `docker-compose restart [service]` |
| Out of disk space | `docker system prune -a` |
| Database issues | Check: `docker exec crypto-trading-bot-timescaledb-1 pg_isready` |

---

## 📈 Performance Checks

### **System Health**

```bash
# Full health check
./scripts/health_check.sh --verbose

# Risk validation
python3 scripts/validate_risk_limits.py --verbose

# Resource usage
docker stats --no-stream

# Disk space
df -h
```

### **Trading Performance**

```bash
# Win rate
curl -s http://localhost:8005/api/v1/stats | jq '.win_rate'

# Sharpe ratio
curl -s http://localhost:8009/api/v1/metrics/portfolio | jq '.sharpe_ratio'

# Max drawdown
curl -s http://localhost:8009/api/v1/metrics/portfolio | jq '.max_drawdown'

# Total trades today
curl -s http://localhost:8005/api/v1/stats | jq '.trades_today'
```

---

## ⚙️ Configuration

### **Environment Files**

```bash
# Bybit API keys
services/bybit-connector/.env
services/market-data-service/.env

# Telegram notifications
services/notification-service/.env

# Database credentials
services/*/db_config.env
```

### **API Configuration**

```bash
# Setup Bybit API
# See: docs/BYBIT_API_SETUP_GUIDE.md

# Setup Telegram
# See: docs/TELEGRAM_NOTIFICATIONS_SETUP.md
```

---

## 🚨 Emergency Procedures

### **Trading Emergency**

```bash
# 1. IMMEDIATE STOP
curl -X POST http://localhost:8005/api/v1/emergency/stop

# 2. Close all positions
curl -X POST http://localhost:8005/api/v1/emergency/close-all

# 3. Check positions closed
curl -s http://localhost:8005/api/v1/positions?status=open | jq

# 4. Stop services
docker-compose stop trading-engine

# 5. Log incident
echo "[$(date)] EMERGENCY STOP" >> /var/log/crypto-bot-incidents.log
```

### **System Emergency**

```bash
# 1. Stop everything
docker-compose down

# 2. Check what went wrong
docker-compose logs > /tmp/emergency_logs.txt

# 3. Backup database (if needed)
docker exec crypto-trading-bot-timescaledb-1 pg_dump \
  -U crypto_user crypto_trading | gzip > backup_emergency.sql.gz

# 4. Full recovery
./scripts/startup.sh
```

---

## 📝 File Locations

### **Scripts**

```
scripts/
├── startup.sh                  # System startup
├── health_check.sh            # Health validation
├── validate_risk_limits.py    # Risk checks
├── monitor.py                 # Continuous monitoring
├── daily_startup.sh           # Morning routine
├── quick_check.sh             # Fast status
└── daily_shutdown.sh          # Evening shutdown
```

### **Documentation**

```
docs/
├── BYBIT_API_SETUP_GUIDE.md           # API configuration
├── TELEGRAM_NOTIFICATIONS_SETUP.md    # Telegram setup
├── DEPLOYMENT_RUNBOOK.md              # Production deployment
├── TRADING_ENGINE_CAPABILITIES.md     # API reference
└── ...

SCRIPTS_OPERATIONAL_GUIDE.md           # Master operations guide
QUICK_REFERENCE.md                     # This file
```

### **Logs**

```
/tmp/startup_YYYYMMDD.log              # Startup logs
/tmp/monitor_YYYYMMDD.log              # Monitoring logs
/tmp/shutdown_YYYYMMDD.log             # Shutdown logs
/tmp/crypto-bot-logs/                  # Archived logs
/tmp/crypto_bot_metrics.json           # Exported metrics
```

---

## 🔑 Key Endpoints

### **Health Endpoints**

```
http://localhost:8000/health  # API Gateway
http://localhost:8001/health  # Bybit Connector
http://localhost:8002/health  # Market Data
http://localhost:8003/health  # Portfolio Manager
http://localhost:8004/health  # Technical Analysis
http://localhost:8005/health  # Trading Engine
http://localhost:8006/health  # Notification Service
http://localhost:8007/health  # ML Prediction
http://localhost:8008/health  # Sentiment Analysis
http://localhost:8009/health  # Risk Metrics
```

### **Trading Endpoints**

```
POST /api/v1/start                      # Start trading
POST /api/v1/stop                       # Stop trading
POST /api/v1/emergency/stop             # Emergency halt
POST /api/v1/emergency/close-all        # Close all positions
GET  /api/v1/status                     # Trading status
GET  /api/v1/positions?status=open      # Open positions
POST /api/v1/positions/{id}/close       # Close position
```

---

## 📊 Risk Limits (Critical)

| Limit | Value | Enforcement |
|-------|-------|-------------|
| **Max risk per trade** | 2% | Position sizing |
| **Daily loss limit** | 5% | Auto-stop trading |
| **Circuit breaker** | 10% drawdown | Emergency halt |
| **Max positions** | 5 concurrent | Order rejection |
| **Leverage** | 1x only | No margin trading |
| **Stop-loss** | ATR-based | Dynamic per trade |

---

## 🎯 Quick Troubleshooting Matrix

| Symptom | Likely Cause | Quick Fix |
|---------|--------------|-----------|
| Dashboard shows "Error Loading" | Services down | `docker-compose restart` |
| Red dots on dashboard | Service unhealthy | Check logs, restart service |
| 0 balance showing | Portfolio not initialized | `curl -X POST http://localhost:8005/api/v1/paper/reset` |
| No trades executing | Mock data or strict signals | Configure real API keys |
| High CPU usage | Too many services | Check `docker stats` |
| Disk full | Old logs/data | `docker system prune` |
| Can't access dashboard | Dashboard not running | `cd dashboard && python3 -m http.server 8080` |
| Monitor not running | Process crashed | `python3 scripts/monitor.py --interval 60 &` |

---

## 🔄 Typical Daily Workflow

### **Morning (9:00 AM)**

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot
./scripts/daily_startup.sh
# Wait 5 minutes for full startup and validation
# Open dashboard: http://localhost:8080
```

### **Throughout Day**

```bash
# Every 2-3 hours: Quick check
./scripts/quick_check.sh

# Monitor dashboard continuously
# Check for alerts in monitor log
tail -f /tmp/monitor_$(date +%Y%m%d).log
```

### **Evening (6:00 PM)**

```bash
# Safe shutdown with daily report
./scripts/daily_shutdown.sh

# Review daily report in logs
cat /tmp/shutdown_$(date +%Y%m%d).log | grep "Daily Performance"
```

---

## 🎓 Learning Resources

### **Getting Started**

1. [SCRIPTS_OPERATIONAL_GUIDE.md](SCRIPTS_OPERATIONAL_GUIDE.md) - Complete operations manual
2. [scripts/README.md](scripts/README.md) - Detailed script documentation
3. [dashboard/README.md](dashboard/README.md) - Dashboard usage guide

### **Configuration**

1. [BYBIT_API_SETUP_GUIDE.md](docs/BYBIT_API_SETUP_GUIDE.md) - API setup (450 lines)
2. [TELEGRAM_NOTIFICATIONS_SETUP.md](docs/TELEGRAM_NOTIFICATIONS_SETUP.md) - Alerts (600 lines)

### **Advanced**

1. [TRADING_ENGINE_CAPABILITIES.md](docs/TRADING_ENGINE_CAPABILITIES.md) - Complete API reference
2. [DEPLOYMENT_RUNBOOK.md](docs/DEPLOYMENT_RUNBOOK.md) - Production deployment

---

## 💡 Pro Tips

**Speed up restarts:**
```bash
./scripts/startup.sh --skip-build  # 3 min vs 10 min
```

**Monitor in background:**
```bash
nohup python3 scripts/monitor.py --interval 60 > /tmp/monitor.log 2>&1 &
```

**Quick service restart:**
```bash
docker-compose restart trading-engine  # Just one service
```

**Check all services at once:**
```bash
for port in {8000..8009}; do
  echo "Port $port: $(curl -s http://localhost:$port/health | jq -r '.status')"
done
```

**Export metrics for analysis:**
```bash
cat /tmp/crypto_bot_metrics.json | jq '.services'
```

**Find slow services:**
```bash
cat /tmp/crypto_bot_metrics.json | jq '.services | to_entries | sort_by(.value.response_time_ms) | reverse'
```

---

## 📞 Support & Help

**Self-Service:**
- Dashboard: http://localhost:8080
- Health check: `./scripts/health_check.sh --verbose`
- Quick check: `./scripts/quick_check.sh`
- Check logs: `docker-compose logs [service]`

**Documentation:**
- Master guide: [SCRIPTS_OPERATIONAL_GUIDE.md](SCRIPTS_OPERATIONAL_GUIDE.md)
- All guides: `docs/` directory
- Script help: `scripts/README.md`

**Emergency:**
- Stop trading: `curl -X POST http://localhost:8005/api/v1/emergency/stop`
- Close all: `curl -X POST http://localhost:8005/api/v1/emergency/close-all`
- Full stop: `docker-compose down`

---

## ✅ Pre-Flight Checklist

**Before Starting Trading:**
- [ ] All 10 services healthy (`./scripts/health_check.sh`)
- [ ] Risk limits validated (`python3 scripts/validate_risk_limits.py`)
- [ ] Dashboard accessible (http://localhost:8080)
- [ ] Monitor running (`pgrep -f monitor.py`)
- [ ] API keys configured (if live trading)
- [ ] Telegram alerts configured (recommended)
- [ ] Backup recent database
- [ ] Review trading strategy parameters
- [ ] Check available balance
- [ ] Verify stop-loss settings

**Daily Pre-Trading:**
- [ ] Run `./scripts/daily_startup.sh`
- [ ] Wait for all validations to pass
- [ ] Check dashboard shows green
- [ ] Review previous day's performance
- [ ] Check for system updates/alerts

---

## 🚀 Production Checklist

**Before Live Trading:**
- [ ] Mainnet API keys configured
- [ ] 30+ days real data collected
- [ ] ML models trained on real data
- [ ] 7+ days paper trading validated
- [ ] All risk limits tested
- [ ] Emergency procedures practiced
- [ ] Team trained on operations
- [ ] Backup/restore tested
- [ ] Monitoring alerts configured
- [ ] Incident response plan ready

---

**Last Updated:** 2025-11-14
**Version:** 1.0.0
**System Status:** ✅ Production-Ready (Paper Trading)

---

**Print this page and keep it handy for quick reference!**
