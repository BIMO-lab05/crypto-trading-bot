# Automated Monitoring & Maintenance Setup Guide
**Created:** 2025-12-05
**Purpose:** Set up automated model retraining and performance monitoring

---

## 📋 **Scripts Created**

### 1. **auto_retrain_models.sh**
- **Purpose**: Automatically retrain ML models weekly
- **Features**:
  - Retrains 6 core models (BTC, BNB, SOL, ADA, AVAX, LINK)
  - 90-day lookback period
  - Logs all training results
  - Sends notifications on completion/failure
- **Location**: `/mnt/d/Bimo_max/crypto-trading-bot/auto_retrain_models.sh`

### 2. **performance_monitor.sh**
- **Purpose**: Monitor trading performance and send alerts
- **Features**:
  - Overall win rate monitoring
  - Per-symbol performance tracking
  - Daily P&L checks
  - Entry confidence tracking
  - ML model freshness
  - Stuck position detection
- **Location**: `/mnt/d/Bimo_max/crypto-trading-bot/performance_monitor.sh`

### 3. **monitor_system.sh**
- **Purpose**: Real-time system health monitoring
- **Features**:
  - Docker container status
  - Service health checks
  - Resource usage
  - Trading activity
- **Location**: `/mnt/d/Bimo_max/crypto-trading-bot/monitor_system.sh`

---

## 🔧 **Manual Usage**

### Run Model Retraining (Manual)
```bash
# One-time manual retraining
bash /mnt/d/Bimo_max/crypto-trading-bot/auto_retrain_models.sh

# Check logs
tail -f /mnt/d/Bimo_max/crypto-trading-bot/logs/model_retraining.log
```

### Run Performance Monitor (Manual)
```bash
# Check performance now
bash /mnt/d/Bimo_max/crypto-trading-bot/performance_monitor.sh

# Check logs
tail -f /mnt/d/Bimo_max/crypto-trading-bot/logs/performance_monitor.log
```

### Run System Monitor (Manual)
```bash
# Single check
bash /mnt/d/Bimo_max/crypto-trading-bot/monitor_system.sh

# Continuous monitoring (refreshes every 5 seconds)
bash /mnt/d/Bimo_max/crypto-trading-bot/monitor_system.sh --continuous
```

---

## ⏰ **Automated Scheduling (Cron Setup)**

### Option 1: Linux/WSL Cron (Recommended)

**Step 1: Open crontab**
```bash
crontab -e
```

**Step 2: Add these lines**
```bash
# ML Model Retraining - Every Sunday at 2 AM
0 2 * * 0 /mnt/d/Bimo_max/crypto-trading-bot/auto_retrain_models.sh >> /mnt/d/Bimo_max/crypto-trading-bot/logs/model_retrain_cron.log 2>&1

# Performance Monitoring - Every 6 hours
0 */6 * * * /mnt/d/Bimo_max/crypto-trading-bot/performance_monitor.sh >> /mnt/d/Bimo_max/crypto-trading-bot/logs/performance_cron.log 2>&1

# Daily Summary - Every day at 9 AM
0 9 * * * /mnt/d/Bimo_max/crypto-trading-bot/monitor_system.sh >> /mnt/d/Bimo_max/crypto-trading-bot/logs/daily_summary.log 2>&1
```

**Step 3: Verify cron is running**
```bash
# Check if cron service is active
sudo service cron status

# List your cron jobs
crontab -l
```

### Option 2: Windows Task Scheduler (Alternative)

**For Windows users running WSL:**

1. Open **Task Scheduler** (taskschd.msc)
2. Create New Task → "ML Model Retraining"
3. Trigger: Weekly, Sunday, 2:00 AM
4. Action: Start a program
   - Program: `C:\Windows\System32\wsl.exe`
   - Arguments: `bash /mnt/d/Bimo_max/crypto-trading-bot/auto_retrain_models.sh`
5. Repeat for performance monitor (every 6 hours)

---

## 📊 **Monitoring Thresholds**

### Performance Monitor Alerts

| Metric | Threshold | Action |
|--------|-----------|--------|
| Overall Win Rate | < 40% | Review strategy |
| Symbol Win Rate | < 30% | Consider removing symbol |
| Daily Loss | < -$50 | Reduce risk |
| ML Confidence | < 40% | Retrain model |
| Stuck Position | > 48 hours | Manual review |
| Confidence Tracking | < 50% tracked | Check code fix |

### Customizing Thresholds

Edit the configuration section in `performance_monitor.sh`:

```bash
# Configuration
MIN_WIN_RATE=40.0          # Minimum acceptable win rate (%)
MIN_SYMBOL_WIN_RATE=30.0   # Minimum win rate per symbol (%)
MAX_DAILY_LOSS=-50.0       # Maximum acceptable daily loss ($)
MIN_CONFIDENCE_TRACKED=50  # Minimum % of trades with confidence tracked
```

---

## 📧 **Notification Setup**

### Email Notifications (Optional)

Both scripts support sending notifications via the notification service (port 8006).

**To enable email alerts:**

1. Configure notification service with email settings
2. Scripts will automatically send alerts to configured endpoints

**Current notification endpoints:**
- `/api/v1/notify/system` - System alerts
- `/api/v1/notify/alert` - Performance alerts
- `/api/v1/notify/pnl` - P&L updates

---

## 📁 **Log Files**

All logs are stored in `/mnt/d/Bimo_max/crypto-trading-bot/logs/`:

```
logs/
├── model_retraining.log       # Manual retraining logs
├── model_retrain_cron.log     # Automated retraining logs
├── performance_monitor.log    # Manual monitoring logs
├── performance_cron.log       # Automated monitoring logs
└── daily_summary.log          # Daily system reports
```

**View logs:**
```bash
# Recent model retraining
tail -100 /mnt/d/Bimo_max/crypto-trading-bot/logs/model_retraining.log

# Recent performance alerts
tail -100 /mnt/d/Bimo_max/crypto-trading-bot/logs/performance_monitor.log

# Follow live
tail -f /mnt/d/Bimo_max/crypto-trading-bot/logs/performance_monitor.log
```

---

## 🔍 **Troubleshooting**

### Cron Not Running

**Check cron service:**
```bash
sudo service cron status
# If not running:
sudo service cron start
```

**Check cron logs:**
```bash
# WSL/Ubuntu
grep CRON /var/log/syslog

# Or check our custom logs
ls -lh /mnt/d/Bimo_max/crypto-trading-bot/logs/
```

### Script Permissions

```bash
# Make sure scripts are executable
chmod +x /mnt/d/Bimo_max/crypto-trading-bot/*.sh

# Verify
ls -lh /mnt/d/Bimo_max/crypto-trading-bot/*.sh
```

### Database Connection Issues

```bash
# Test database connection
docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -c "SELECT COUNT(*) FROM positions;"

# Check if container is running
docker ps | grep postgres
```

### ML Service Not Available

```bash
# Check ML service health
curl http://localhost:8007/health

# Restart if needed
docker restart crypto-bot-ml-prediction
```

---

## 📅 **Recommended Schedule**

### Daily
- **9:00 AM** - System health check
- **Every 6 hours** - Performance monitoring

### Weekly
- **Sunday 2:00 AM** - ML model retraining
- **Sunday 10:00 AM** - Weekly performance review (manual)

### Monthly
- **First Sunday** - Full system audit
- **Review logs** - Check for recurring alerts
- **Update thresholds** - Adjust based on performance

---

## 🎯 **Quick Start**

### 1. Test Scripts Manually (First Time)
```bash
# Test system monitor
bash /mnt/d/Bimo_max/crypto-trading-bot/monitor_system.sh

# Test performance monitor
bash /mnt/d/Bimo_max/crypto-trading-bot/performance_monitor.sh

# Test model retraining (takes ~5 minutes)
bash /mnt/d/Bimo_max/crypto-trading-bot/auto_retrain_models.sh
```

### 2. Set Up Cron (Automated)
```bash
# Edit crontab
crontab -e

# Add the 3 lines from "Cron Setup" section above

# Save and exit
# Cron will now run automatically!
```

### 3. Monitor Results
```bash
# Check if cron jobs ran
tail -f /mnt/d/Bimo_max/crypto-trading-bot/logs/performance_cron.log

# View all logs
ls -lh /mnt/d/Bimo_max/crypto-trading-bot/logs/
```

---

## ✅ **Verification Checklist**

After setup, verify everything works:

- [ ] Scripts are executable (`chmod +x *.sh`)
- [ ] Manual test of each script succeeds
- [ ] Cron jobs added to crontab (`crontab -l`)
- [ ] Log directory exists and is writable
- [ ] Database connection works
- [ ] ML service is accessible
- [ ] Notification service responds (optional)
- [ ] First automated run completes successfully

---

## 🚀 **Next Steps**

1. **Test all scripts manually** to ensure they work
2. **Set up cron** for automated execution
3. **Monitor logs** for first few runs
4. **Adjust thresholds** based on your trading strategy
5. **Review alerts** weekly and act on them

---

## 📞 **Support**

If you encounter issues:

1. Check the logs in `/mnt/d/Bimo_max/crypto-trading-bot/logs/`
2. Verify all services are running (`bash monitor_system.sh`)
3. Test database connection
4. Check cron service status
5. Review this guide's Troubleshooting section

---

**Last Updated:** 2025-12-05
**Version:** 1.0
**Status:** ✅ Ready for production use
