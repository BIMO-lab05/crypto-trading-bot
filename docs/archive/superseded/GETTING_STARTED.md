# Getting Started - Crypto Trading Bot

**Complete Setup Guide for New Users**
**Version:** 2.0.0
**Last Updated:** 2025-11-14

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [System Requirements](#system-requirements)
3. [Quick Start (5 Minutes)](#quick-start-5-minutes)
4. [Detailed Setup](#detailed-setup)
5. [First Run](#first-run)
6. [Configuration Options](#configuration-options)
7. [Operating Modes](#operating-modes)
8. [Troubleshooting](#troubleshooting)
9. [Next Steps](#next-steps)

---

## Overview

### What is This System?

This is an **enterprise-grade automated cryptocurrency trading bot** with:
- 10 microservices (API Gateway, Market Data, Trading Engine, Portfolio Manager, etc.)
- ML-powered predictions (LSTM models)
- Sentiment analysis
- Risk management (max 2% per trade, 5% daily loss limit, 10% circuit breaker)
- Real-time dashboard
- Complete operational automation (35+ scripts)
- Disaster recovery capabilities

### Current Status

✅ **96% Complete - Production Ready (Paper Trading)**
- Infrastructure: 100%
- Microservices: 100% (10/10)
- Operational Tools: 100% (35+ scripts)
- Documentation: 100%
- ⚠️ Live Trading: 40% (requires real API configuration)

---

## System Requirements

### Hardware
- **CPU:** 4+ cores (8+ recommended)
- **RAM:** 8GB minimum (16GB recommended)
- **Disk:** 50GB available space
- **Network:** Stable internet connection

### Software
```bash
# Required
- Docker 20.10+
- Docker Compose 1.29+
- Python 3.8+
- Git

# Optional (for development)
- Node.js 16+ (for dashboard development)
- PostgreSQL client tools
```

### Operating System
- ✅ Linux (Ubuntu 20.04+, Debian 11+)
- ✅ macOS 11+
- ✅ Windows 10/11 (via WSL2)

---

## Quick Start (5 Minutes)

### Option 1: Manual Mode (Recommended for First Time)

```bash
# 1. Navigate to project directory
cd /mnt/d/Bimo_max/crypto-trading-bot

# 2. Validate configuration
./scripts/validate_configuration.sh

# 3. Start the system
./scripts/daily_startup.sh

# 4. Open dashboard in browser
# Visit: http://localhost:8080

# 5. Monitor in real-time
./scripts/quick_check.sh
```

**That's it!** The system is now running in paper trading mode.

### Option 2: Fully Automated Mode

```bash
# 1. Install automation (one-time setup)
./scripts/setup_automation.sh --install

# 2. Verify installation
crontab -l
sudo systemctl status crypto-bot-monitor

# 3. Everything runs automatically from now on!
```

---

## Detailed Setup

### Step 1: Clone Repository (if not already done)

```bash
git clone https://github.com/yourusername/crypto-trading-bot.git
cd crypto-trading-bot
```

### Step 2: Verify Docker Installation

```bash
# Check Docker
docker --version
# Expected: Docker version 20.10.x or higher

# Check Docker Compose
docker-compose --version
# Expected: Docker Compose version 1.29.x or higher

# Test Docker
docker run hello-world
# Should see "Hello from Docker!"
```

If Docker is not installed:
```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
# Log out and back in

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### Step 3: Verify Python Environment

```bash
# Check Python version
python3 --version
# Expected: Python 3.8 or higher

# Install required packages
pip install requests python-dotenv redis psycopg2-binary pandas numpy
```

### Step 4: Make Scripts Executable

```bash
chmod +x scripts/*.sh
chmod +x scripts/*.py
```

### Step 5: Validate Configuration

```bash
# Run configuration validator
./scripts/validate_configuration.sh --verbose

# If errors, try auto-fix
./scripts/validate_configuration.sh --fix

# Manually configure remaining values
# Edit .env files as instructed
```

### Step 6: Build Services (First Time Only)

```bash
# Build all Docker images
docker-compose build

# This takes 10-15 minutes on first run
# Subsequent builds use cache and are much faster
```

---

## First Run

### Starting the System

```bash
# Full startup with all validations
./scripts/daily_startup.sh
```

**What happens during startup:**
1. ✅ Checks for existing services (offers restart option)
2. ✅ Starts Docker containers
3. ✅ Waits for services to initialize
4. ✅ Runs comprehensive health checks
5. ✅ Validates risk management limits
6. ✅ Starts continuous monitoring
7. ✅ Launches dashboard

**Expected Duration:** 5 minutes

### Accessing the Dashboard

Once startup completes:
1. Open browser
2. Navigate to: `http://localhost:8080`
3. You should see real-time monitoring dashboard

**Dashboard Features:**
- Service health status (10 services)
- Trading status (auto-trading on/off)
- Portfolio balance and P&L
- Open positions
- Recent trades
- System alerts

### Verifying Everything Works

```bash
# Quick health check
./scripts/quick_check.sh

# Detailed health check
./scripts/health_check.sh --verbose

# Check specific service
curl http://localhost:8005/health | jq

# View logs
docker-compose logs --tail 50
```

Expected output:
```
[OK] Services: 10/10 healthy
[OK] Trading Status: RUNNING
[OK] Portfolio Balance: $10,000.00 (paper trading)
[OK] Risk Limits: All validated
[OK] System Status: HEALTHY
```

---

## Configuration Options

### Paper Trading vs Live Trading

**Paper Trading (Default - SAFE)**
```bash
# Already configured by default
# Uses mock data and simulated trades
# Perfect for testing strategies
# No real money at risk
```

**Live Trading (Requires Setup)**
```bash
# 1. Get Bybit API keys
#    - Login to Bybit
#    - Create API key with trading permissions
#    - Copy API key and secret

# 2. Configure API keys
nano services/bybit-connector/.env

# Set:
BYBIT_API_KEY=your_real_api_key
BYBIT_API_SECRET=your_real_api_secret
BYBIT_TESTNET=false  # Change to false for mainnet

# 3. Validate configuration
./scripts/validate_configuration.sh --verbose

# 4. Test on testnet first!
BYBIT_TESTNET=true  # Test with testnet for 7+ days
```

⚠️ **WARNING:** Never use live trading without thoroughly testing on paper trading and testnet first!

### Risk Management Configuration

Edit `services/trading-engine/.env`:
```bash
# Maximum risk per trade (2% recommended)
MAX_RISK_PER_TRADE=2.0

# Daily loss limit (5% recommended)
DAILY_LOSS_LIMIT=5.0

# Circuit breaker threshold (10% recommended)
CIRCUIT_BREAKER_THRESHOLD=10.0

# Maximum concurrent positions
MAX_POSITIONS=5

# Leverage (1x recommended - no margin)
MAX_LEVERAGE=1
```

**Never change these without understanding the implications!**

### Telegram Notifications (Optional)

```bash
# 1. Create Telegram bot
#    - Message @BotFather on Telegram
#    - Send: /newbot
#    - Follow instructions

# 2. Get your chat ID
./scripts/get_telegram_chat_id.sh

# 3. Configure
nano services/notification-service/.env

# Set:
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# 4. Test
curl -X POST http://localhost:8006/api/v1/send \
  -H "Content-Type: application/json" \
  -d '{"message":"Test notification"}'
```

---

## Operating Modes

### Mode 1: Manual Operations (Full Control)

**Daily Workflow:**
```bash
# Morning (9:00 AM)
./scripts/validate_configuration.sh
./scripts/daily_startup.sh
# Open dashboard: http://localhost:8080

# Throughout Day (every 2-3 hours)
./scripts/quick_check.sh

# Evening (6:00 PM)
./scripts/generate_performance_report.sh --period daily --format html
./scripts/daily_shutdown.sh
```

**Advantages:**
- Full control over timing
- Review each step
- Learn the system

**Disadvantages:**
- Must remember to run scripts
- Manual intervention required

### Mode 2: Fully Automated (Set and Forget)

**One-Time Setup:**
```bash
# Preview automation schedule
./scripts/setup_automation.sh --preview

# Install automation
./scripts/setup_automation.sh --install

# Verify
crontab -l
```

**What Gets Automated:**
- ✅ Morning startup (9 AM, Mon-Fri)
- ✅ Health checks every 30 minutes
- ✅ Evening shutdown (6 PM, Mon-Fri)
- ✅ Daily backups (11 PM)
- ✅ Daily database optimization (2 AM)
- ✅ Daily performance reports (8 PM)
- ✅ Weekly maintenance (Sundays)
- ✅ Monthly full optimization
- ✅ Continuous monitoring (systemd service)

**Advantages:**
- No manual intervention
- Never forget tasks
- Professional automation

**Disadvantages:**
- Less control over timing
- Need to monitor logs

### Mode 3: Hybrid (Recommended)

```bash
# Automate routine tasks
./scripts/setup_automation.sh --install

# But manually control trading
# Start trading when ready:
./scripts/daily_startup.sh

# Stop when needed:
./scripts/daily_shutdown.sh
```

---

## Troubleshooting

### Services Won't Start

**Problem:** Docker containers not starting

**Solution:**
```bash
# Check Docker daemon
sudo systemctl status docker

# Check ports
lsof -i :8000-8009

# View logs
docker-compose logs [service-name]

# Nuclear option: full rebuild
docker-compose down -v
docker-compose build --no-cache
./scripts/startup.sh
```

### Dashboard Not Accessible

**Problem:** Cannot access http://localhost:8080

**Solution:**
```bash
# Check if dashboard is running
pgrep -f "http.server 8080"

# Restart dashboard
cd dashboard
python3 -m http.server 8080 &

# Check firewall
sudo ufw status
```

### Health Checks Failing

**Problem:** Services report unhealthy

**Solution:**
```bash
# Detailed health check
./scripts/health_check.sh --verbose

# Check individual service
curl http://localhost:8005/health

# View service logs
docker-compose logs --tail 100 trading-engine

# Restart unhealthy service
docker-compose restart trading-engine
```

### Configuration Errors

**Problem:** Configuration validation fails

**Solution:**
```bash
# Run validator with verbose output
./scripts/validate_configuration.sh --verbose

# Auto-fix common issues
./scripts/validate_configuration.sh --fix

# Check specific .env file
cat services/trading-engine/.env

# Restore from backup if needed
./scripts/disaster_recovery.sh --restore-configs backups/configs_[date].tar.gz
```

### Database Issues

**Problem:** Database connection errors

**Solution:**
```bash
# Check database container
docker ps | grep timescaledb

# Test database connection
docker exec crypto-trading-bot-timescaledb-1 pg_isready

# View database logs
docker logs crypto-trading-bot-timescaledb-1

# Optimize database
./scripts/optimize_database.sh --analyze

# Restore from backup if corrupted
./scripts/disaster_recovery.sh --restore-db backups/db_[latest].sql.gz
```

### Trading Not Working

**Problem:** No trades executing

**Solution:**
```bash
# Check trading status
curl http://localhost:8005/api/v1/status

# Check if auto-trading is enabled
# Should show: "auto_trading_enabled": true

# Enable trading
curl -X POST http://localhost:8005/api/v1/start

# Check for errors
docker-compose logs trading-engine

# Validate risk limits
python3 scripts/validate_risk_limits.py --verbose
```

---

## Next Steps

### After First Successful Run

1. **Review Dashboard** (30 minutes)
   - Understand all metrics
   - Watch real-time updates
   - Check all 10 service statuses

2. **Generate First Report** (5 minutes)
   ```bash
   ./scripts/generate_performance_report.sh --period daily --format html
   # Open: /tmp/crypto-bot-reports/performance_daily_[date].html
   ```

3. **Test Emergency Procedures** (15 minutes)
   ```bash
   # Practice emergency stop
   curl -X POST http://localhost:8005/api/v1/emergency/stop

   # Close all positions
   curl -X POST http://localhost:8005/api/v1/emergency/close-all

   # Restart trading
   curl -X POST http://localhost:8005/api/v1/start
   ```

4. **Create Your First Backup** (5 minutes)
   ```bash
   ./scripts/backup.sh --full
   # Verify: ls -lh backups/
   ```

5. **Test Disaster Recovery** (10 minutes)
   ```bash
   # List available backups
   ./scripts/disaster_recovery.sh --list-backups

   # Practice restore (don't do full recovery yet)
   # Just review the commands
   ```

### Week 1: Learning Phase

- [ ] Run system daily in paper trading mode
- [ ] Review daily performance reports
- [ ] Monitor dashboard throughout the day
- [ ] Practice quick checks every 2-3 hours
- [ ] Test emergency stop procedures
- [ ] Generate weekly performance report
- [ ] Review all logs to understand patterns

### Week 2: Optimization Phase

- [ ] Enable automation: `./scripts/setup_automation.sh --install`
- [ ] Configure Telegram notifications
- [ ] Test backup and restore procedures
- [ ] Optimize trading parameters if needed
- [ ] Review ML model performance
- [ ] Check sentiment analysis accuracy
- [ ] Fine-tune risk management settings

### Week 3-4: Validation Phase (Before Live Trading)

- [ ] Switch to Bybit testnet with real API keys
- [ ] Run for 7+ consecutive days
- [ ] Validate all trades execute correctly
- [ ] Verify risk limits are enforced
- [ ] Test with different market conditions
- [ ] Create comprehensive backups
- [ ] Document any issues and resolutions

### Month 2: Live Trading Transition (Optional)

⚠️ **Only proceed if:**
- [ ] 30+ days successful paper trading
- [ ] 7+ days successful testnet trading
- [ ] All risk limits validated
- [ ] Emergency procedures practiced
- [ ] Backup/restore tested
- [ ] Monitoring automation working
- [ ] Comfortable with all operations

**Transition Steps:**
1. Start with very small capital (test amount)
2. Enable live trading with 1x leverage only
3. Monitor closely for first 48 hours
4. Gradually increase if successful
5. Never risk more than you can afford to lose

---

## Important Commands Reference

### Daily Operations
```bash
# Start
./scripts/daily_startup.sh

# Quick check
./scripts/quick_check.sh

# Shutdown
./scripts/daily_shutdown.sh
```

### Maintenance
```bash
# Backup
./scripts/backup.sh --full

# Cleanup logs
./scripts/cleanup_logs.sh --days 7

# Optimize database
./scripts/optimize_database.sh --analyze
```

### Monitoring
```bash
# Health check
./scripts/health_check.sh --verbose

# System status
./scripts/system_status_report.sh

# Performance report
./scripts/generate_performance_report.sh --period daily --format html
```

### Emergency
```bash
# Stop trading
curl -X POST http://localhost:8005/api/v1/emergency/stop

# Close all positions
curl -X POST http://localhost:8005/api/v1/emergency/close-all

# Full recovery
./scripts/disaster_recovery.sh --full-recovery
```

### Configuration
```bash
# Validate
./scripts/validate_configuration.sh --verbose

# Auto-fix
./scripts/validate_configuration.sh --fix

# Risk validation
python3 scripts/validate_risk_limits.py --verbose
```

---

## Documentation Index

**Start Here:**
- `GETTING_STARTED.md` (this file) - Complete setup guide
- `QUICK_REFERENCE.md` - Fast command lookup
- `README.md` - Project overview

**Detailed Guides:**
- `SCRIPTS_INDEX.md` - All 35+ scripts documented
- `SCRIPTS_OPERATIONAL_GUIDE.md` - Complete operations manual

**Technical Documentation:**
- `TRADING_ENGINE_CAPABILITIES.md` - Complete API reference
- `BYBIT_API_SETUP_GUIDE.md` - Live trading setup
- `TELEGRAM_NOTIFICATIONS_SETUP.md` - Alert configuration
- `DEPLOYMENT_RUNBOOK.md` - Production deployment

---

## Support and Help

### Self-Service Resources

1. **Quick Check:** `./scripts/quick_check.sh`
2. **Health Check:** `./scripts/health_check.sh --verbose`
3. **Logs:** `docker-compose logs [service]`
4. **Configuration:** `./scripts/validate_configuration.sh --verbose`

### Common Issues

See [Troubleshooting](#troubleshooting) section above.

### Getting Help

1. Check documentation in `docs/` folder
2. Review `TROUBLESHOOTING.md`
3. Check logs: `/tmp/monitor_[date].log`
4. Review backup/recovery procedures

---

## Safety Reminders

⚠️ **CRITICAL:**
- **NEVER** use live trading without extensive testing
- **ALWAYS** test on paper trading first (30+ days)
- **ALWAYS** test on testnet before mainnet (7+ days)
- **NEVER** risk more than 2% per trade
- **NEVER** disable risk management features
- **ALWAYS** have recent backups
- **ALWAYS** practice emergency procedures
- **NEVER** share API keys or credentials

🎯 **Best Practices:**
- Start small with paper trading
- Learn all features before live trading
- Monitor system daily
- Review performance weekly
- Create backups daily
- Test disaster recovery monthly
- Keep documentation updated
- Practice emergency procedures

---

## Quick Start Checklist

Before first run:
- [ ] Docker and Docker Compose installed
- [ ] Python 3.8+ installed
- [ ] All scripts executable (`chmod +x scripts/*.sh`)
- [ ] Configuration validated (`./scripts/validate_configuration.sh`)
- [ ] Services built (`docker-compose build`)

First run:
- [ ] System started (`./scripts/daily_startup.sh`)
- [ ] Dashboard accessible (http://localhost:8080)
- [ ] Health check passed (`./scripts/health_check.sh`)
- [ ] Risk limits validated (`python3 scripts/validate_risk_limits.py`)
- [ ] Trading status confirmed (`curl http://localhost:8005/api/v1/status`)

Daily operations:
- [ ] Morning startup
- [ ] Quick checks throughout day
- [ ] Evening shutdown
- [ ] Review daily reports

Weekly tasks:
- [ ] Full backup
- [ ] Log cleanup
- [ ] Database optimization
- [ ] Performance review

---

**Version:** 2.0.0
**Last Updated:** 2025-11-14
**Status:** Production-Ready (Paper Trading)

**Ready to start? Run:** `./scripts/daily_startup.sh`

**Questions? Check:** `QUICK_REFERENCE.md` for fast answers

---

Good luck with your trading bot! 🚀
