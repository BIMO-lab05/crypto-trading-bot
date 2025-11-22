# Scripts Index - Complete Operational Utilities Catalog

**Version:** 1.1.0
**Last Updated:** 2025-11-14
**Total Scripts:** 36+ (NEW: System Testing Suite)

---

## Quick Navigation

| Category | Scripts | Purpose |
|----------|---------|---------|
| [Daily Workflow](#daily-workflow-scripts) | 3 scripts | Morning startup, quick checks, evening shutdown |
| [System Management](#system-management-scripts) | 4 scripts | Startup, health checks, monitoring, validation |
| [Maintenance](#maintenance-scripts) | 3 scripts | Backup, log cleanup, database optimization |
| [Reporting](#reporting-scripts) | 2 scripts | Performance reports, system status |
| [Advanced Utilities](#advanced-utilities-scripts) | 3 scripts | Automation, disaster recovery, config validation |
| [Infrastructure](#infrastructure-scripts) | 3 scripts | Database setup, network config, service checks |
| [Testing](#testing-scripts) | 4 scripts | System tests, phase tests, ML validation ⭐ |
| [Monitoring](#monitoring-scripts) | 3 scripts | Continuous monitoring, trading alerts, bot monitoring |

---

## Daily Workflow Scripts

### 1. `daily_startup.sh` ⭐ RECOMMENDED
**Purpose:** Automated morning startup routine
**Duration:** 5 minutes
**Exit Codes:** 0=success, 1=warnings, 2=critical failure

**Features:**
- Checks for existing services (with restart option)
- Orchestrated system startup
- Comprehensive health validation
- Risk management verification
- Starts continuous monitoring
- Launches dashboard automatically

**Usage:**
```bash
./scripts/daily_startup.sh

# Available options:
./scripts/daily_startup.sh --skip-restart    # Skip service restart check
./scripts/daily_startup.sh --no-monitor      # Don't start monitoring
```

**When to Use:**
- Every morning before trading
- After system reboot
- After configuration changes

**Output:**
- `/tmp/startup_YYYYMMDD.log` - Detailed startup log
- Dashboard launched at http://localhost:8080
- Monitor running in background

---

### 2. `quick_check.sh` ⭐ RECOMMENDED
**Purpose:** Lightning-fast 10-second status check
**Duration:** 10 seconds
**Exit Codes:** 0=healthy, 1=degraded, 2=critical

**Features:**
- Service health (10 microservices)
- Trading status and positions
- Portfolio balance and P&L
- Risk metrics validation
- System alerts check

**Usage:**
```bash
./scripts/quick_check.sh

# Can be run as often as every 2-3 hours
```

**When to Use:**
- Throughout the trading day
- Before making trading decisions
- After any manual intervention
- As a cron job (*/30 * * * *)

**Output:**
- Color-coded status display
- Exit code for automation
- No log files (fast check)

---

### 3. `daily_shutdown.sh` ⭐ RECOMMENDED
**Purpose:** Safe evening shutdown with position checks
**Duration:** 3 minutes
**Exit Codes:** 0=clean shutdown, 1=warnings

**Features:**
- Stops auto-trading gracefully
- Checks for open positions (interactive close option)
- Generates daily performance report
- Stops monitoring processes
- Archives logs to `/tmp/crypto-bot-logs`
- Stops all Docker services cleanly

**Usage:**
```bash
./scripts/daily_shutdown.sh

# Force shutdown (skip position checks)
./scripts/daily_shutdown.sh --force
```

**When to Use:**
- Every evening after trading
- Before system maintenance
- Before configuration updates

**Output:**
- `/tmp/shutdown_YYYYMMDD.log` - Shutdown log with daily report
- Archived logs in `/tmp/crypto-bot-logs/`
- Daily P&L summary

---

## System Management Scripts

### 4. `startup.sh`
**Purpose:** Full system startup with build option
**Duration:** 10 minutes (with build), 3 minutes (skip build)
**Exit Codes:** 0=success, 1=failure

**Features:**
- Pre-flight checks (ports, Docker, network)
- Optional service rebuild
- Database initialization
- Health validation
- Service-by-service startup with logs

**Usage:**
```bash
./scripts/startup.sh                    # Full startup with build
./scripts/startup.sh --skip-build       # Fast restart (recommended)
./scripts/startup.sh --rebuild-all      # Nuclear rebuild
```

**When to Use:**
- First-time system setup
- After Docker issues
- After major code changes
- For production deployment

**Output:**
- `/tmp/startup_YYYYMMDD_HHMMSS.log`
- Service health status
- Initialization results

---

### 5. `health_check.sh`
**Purpose:** Comprehensive system health validation
**Duration:** 30 seconds
**Exit Codes:** 0=healthy, 1=warnings, 2=critical

**Features:**
- All 10 microservices health
- Infrastructure services (TimescaleDB, Redis, RabbitMQ)
- API endpoint validation
- Database connectivity
- Response time measurements
- Detailed vs summary modes

**Usage:**
```bash
./scripts/health_check.sh               # Summary mode
./scripts/health_check.sh --verbose     # Detailed mode
./scripts/health_check.sh --json        # JSON output for automation
```

**When to Use:**
- After system startup
- During troubleshooting
- Scheduled health checks
- Before critical operations

**Output:**
- Health status of all components
- Response times
- Exit code for automation
- Optional JSON output

---

### 6. `monitor.py`
**Purpose:** Continuous system monitoring with alerts
**Duration:** Runs continuously
**Exit Codes:** 0=clean exit, 1=error

**Features:**
- Configurable check intervals (default: 60s)
- Service health monitoring
- Trading status monitoring
- Portfolio balance tracking
- Risk metric validation
- Alert generation for critical issues
- Metrics export to JSON

**Usage:**
```bash
# Foreground (for testing)
python3 scripts/monitor.py --interval 60

# Background (production)
nohup python3 scripts/monitor.py --interval 60 > /tmp/monitor.log 2>&1 &

# Custom alerts
python3 scripts/monitor.py --interval 30 --alert-threshold 3
```

**When to Use:**
- Started automatically by `daily_startup.sh`
- During active trading
- For continuous system health

**Output:**
- `/tmp/monitor_YYYYMMDD.log` - Monitoring log
- `/tmp/crypto_bot_metrics.json` - Exported metrics
- Alerts for critical conditions

---

### 7. `validate_risk_limits.py`
**Purpose:** Risk management controls validation
**Duration:** 10 seconds
**Exit Codes:** 0=pass, 1=fail

**Features:**
- Validates all risk limits are enforced
- Position sizing checks (max 2% per trade)
- Daily loss limit verification (5%)
- Circuit breaker test (10% drawdown)
- Max positions enforcement (5 concurrent)
- Leverage restriction (1x only)
- Stop-loss configuration

**Usage:**
```bash
python3 scripts/validate_risk_limits.py --verbose

# Quick validation
python3 scripts/validate_risk_limits.py
```

**When to Use:**
- After configuration changes
- Before starting trading
- During compliance audits
- Part of `daily_startup.sh`

**Output:**
- Risk limit validation results
- Configuration verification
- Recommendations for improvements

---

## Maintenance Scripts

### 8. `backup.sh` ⭐ NEW
**Purpose:** Automated backup of database, logs, and configuration
**Duration:** 2-5 minutes
**Exit Codes:** 0=success, 1=errors

**Features:**
- TimescaleDB backup with compression
- Redis RDB backup
- Configuration files backup (.env, docker-compose.yml)
- Log files backup (optional with --full)
- ML model backups
- Backup verification
- Automatic old backup cleanup (30-day retention)
- Backup manifest creation

**Usage:**
```bash
# Quick backup (database + configs)
./scripts/backup.sh

# Full backup (includes logs)
./scripts/backup.sh --full

# Custom retention
./scripts/backup.sh --full --keep-days 60

# No compression
./scripts/backup.sh --no-compress
```

**When to Use:**
- Daily (recommended: end of day)
- Before major changes
- Before system updates
- After successful trading days

**Output:**
- `/mnt/d/Bimo_max/crypto-trading-bot/backups/db_YYYYMMDD_HHMMSS.sql.gz`
- `/mnt/d/Bimo_max/crypto-trading-bot/backups/configs_YYYYMMDD_HHMMSS.tar.gz`
- `/mnt/d/Bimo_max/crypto-trading-bot/backups/backup_manifest_YYYYMMDD_HHMMSS.txt`
- Restore commands in summary

**Restore Commands:**
```bash
# Database restore
gunzip -c backups/db_20251114_180000.sql.gz | docker exec -i crypto-trading-bot-timescaledb-1 psql -U crypto_user -d crypto_trading

# Config restore
tar -xzf backups/configs_20251114_180000.tar.gz

# ML models restore
tar -xzf backups/ml_models_20251114_180000.tar.gz
```

---

### 9. `cleanup_logs.sh` ⭐ NEW
**Purpose:** Log cleanup and rotation to manage disk space
**Duration:** 1-2 minutes
**Exit Codes:** 0=success, 1=errors

**Features:**
- Cleans monitor logs older than N days (default: 7)
- Cleans startup/shutdown logs
- Archives current logs
- Rotates Docker logs
- Runs docker system prune
- Cleans old archives
- Dry-run mode for safety
- Disk space reporting

**Usage:**
```bash
# Default cleanup (7 days)
./scripts/cleanup_logs.sh

# Custom retention
./scripts/cleanup_logs.sh --days 14

# Dry run (see what would be deleted)
./scripts/cleanup_logs.sh --dry-run --days 7

# Aggressive cleanup (3 days)
./scripts/cleanup_logs.sh --days 3
```

**When to Use:**
- Weekly (recommended)
- When disk space is low
- Before backups
- Part of maintenance routine

**Output:**
- Log cleanup summary
- Disk space reclaimed
- Archive location: `/tmp/crypto-bot-logs-archive/`
- Docker system prune results

---

### 10. `optimize_database.sh` ⭐ NEW
**Purpose:** TimescaleDB performance optimization
**Duration:** 5-30 minutes (depends on database size)
**Exit Codes:** 0=success, 1=errors

**Features:**
- VACUUM operation (reclaim storage)
- ANALYZE operation (update query statistics)
- REINDEX operation (rebuild indexes)
- TimescaleDB chunk compression
- Table size analysis
- Index usage statistics
- Slow query identification
- Before/after size comparison

**Usage:**
```bash
# Quick daily optimization
./scripts/optimize_database.sh --analyze

# Weekly maintenance
./scripts/optimize_database.sh --vacuum --analyze

# Full monthly optimization
./scripts/optimize_database.sh --all

# Individual operations
./scripts/optimize_database.sh --reindex
```

**When to Use:**
- Daily: `--analyze` (fast, updates statistics)
- Weekly: `--vacuum --analyze` (reclaim space)
- Monthly: `--all` (complete maintenance)
- After large data imports
- When queries are slow

**Output:**
- Database size before/after
- Top 10 tables by size
- Vacuum/analyze progress
- Slow query report
- Optimization recommendations

---

## Reporting Scripts

### 11. `generate_performance_report.sh` ⭐ NEW
**Purpose:** Generate comprehensive performance reports
**Duration:** 5-10 seconds
**Exit Codes:** 0=success, 1=errors

**Features:**
- Portfolio summary (balance, P&L, available funds)
- Trading statistics (total trades, win rate, trades today)
- Risk metrics (Sharpe ratio, max drawdown, VaR)
- Open positions detail
- Multiple output formats (TXT, JSON, HTML)
- Period selection (daily, weekly, monthly)
- Beautiful HTML reports

**Usage:**
```bash
# Daily text report
./scripts/generate_performance_report.sh --period daily --format txt

# Weekly JSON report
./scripts/generate_performance_report.sh --period weekly --format json

# Monthly HTML report (beautiful!)
./scripts/generate_performance_report.sh --period monthly --format html

# Custom output location
./scripts/generate_performance_report.sh --period daily --format html --output-dir ~/reports
```

**When to Use:**
- End of each trading day
- Weekly performance review
- Monthly analysis
- Investor reporting
- Performance tracking

**Output:**
- `/tmp/crypto-bot-reports/performance_daily_YYYYMMDD.txt` (text)
- `/tmp/crypto-bot-reports/performance_weekly_YYYYMMDD.json` (JSON)
- `/tmp/crypto-bot-reports/performance_monthly_YYYYMMDD.html` (HTML)

**HTML Report Features:**
- Responsive design
- Color-coded P&L
- Professional formatting
- Can be emailed to stakeholders

---

### 12. `system_status_report.sh` ⭐ NEW
**Purpose:** Comprehensive system status report
**Duration:** 10-15 seconds
**Exit Codes:** 0=success, 1=errors

**Features:**
- Overall system health status
- All 10 microservices health
- Docker container status
- Infrastructure health (DB, Redis, RabbitMQ)
- Trading status
- Portfolio summary
- System resource usage
- Recent error detection
- Email capability
- Save to file option

**Usage:**
```bash
# Display report
./scripts/system_status_report.sh

# Save to file
./scripts/system_status_report.sh --save /path/to/report.txt

# Email report
./scripts/system_status_report.sh --email admin@example.com

# Both
./scripts/system_status_report.sh --save ~/status.txt --email admin@example.com
```

**When to Use:**
- Daily system check
- Before critical operations
- Troubleshooting sessions
- Scheduled email reports
- Team status updates

**Output:**
- System status summary
- Service health breakdown
- Resource usage statistics
- Error summary (last hour)
- Overall status (HEALTHY/DEGRADED/CRITICAL)

**Email Setup:**
```bash
# Install mail utilities
sudo apt-get install mailutils

# Configure email then use:
./scripts/system_status_report.sh --email admin@example.com
```

---

## Infrastructure Scripts

### 13. `check_infrastructure.sh`
**Purpose:** Validate infrastructure services
**Features:** Database, Redis, RabbitMQ connectivity checks

### 14. `setup_database.sh`
**Purpose:** Initialize TimescaleDB with schema
**Features:** Creates tables, hypertables, indexes

### 15. `setup_notifications.sh`
**Purpose:** Configure Telegram notifications
**Features:** Bot setup, channel configuration, test messages

---

## Testing Scripts

### 16. `run_system_tests.sh` ⭐ NEW - COMPREHENSIVE TESTING
**Purpose:** Complete end-to-end system validation
**Duration:** 2-3 minutes
**Exit Codes:** 0=all tests passed, 1=some tests failed

**Features:**
- 84 comprehensive tests across 10 categories
- Docker services health validation
- API endpoint testing
- Database connectivity checks
- Message queue validation
- Operational scripts verification
- Configuration validation
- Documentation completeness
- Dashboard accessibility
- Performance benchmarking
- Emergency procedures validation

**Usage:**
```bash
# Run all tests (default mode)
./scripts/run_system_tests.sh

# Run with verbose output
./scripts/run_system_tests.sh --verbose

# Run with report generation
./scripts/run_system_tests.sh --report

# Run with both verbose and report
./scripts/run_system_tests.sh --verbose --report
```

**When to Use:**
- Before production deployment
- After configuration changes
- Weekly system health check
- CI/CD pipeline integration
- Post-update validation

**Test Categories:**
1. Docker Services Health (20 tests)
2. API Endpoints (10 tests)
3. Database Connectivity (4 tests)
4. Message Queue (3 tests)
5. Operational Scripts (20 tests)
6. Configuration Files (8 tests)
7. Documentation (9 tests)
8. Dashboard Accessibility (4 tests)
9. System Performance (3 tests)
10. Emergency Procedures (3 tests)

**Output:**
- Pass/fail status for each test
- Overall success rate percentage
- Test summary report
- Optional detailed report file

---

### 17. `run_phase3_tests.sh`
**Purpose:** Run Phase 3 integration tests
**Features:** ML service, sentiment analysis, risk metrics tests

### 18. Phase comparison scripts
**Purpose:** Compare trading strategy performance
**Features:** Backtest Phase 1 vs Phase 3 strategies

---

## Monitoring Scripts

### 18. `monitor_bot.sh`
**Purpose:** Monitor bot health with alerts
**Features:** Service checks, alert generation

### 19. `monitor_trading.sh`
**Purpose:** Monitor active trading
**Features:** Position tracking, P&L monitoring

### 20. `start-monitoring.sh`
**Purpose:** Start all monitoring services
**Features:** Dashboard, metrics collection, alerting

---

## Recommended Daily Workflow

### Morning Routine (9:00 AM) - 5 minutes
```bash
cd /mnt/d/Bimo_max/crypto-trading-bot
./scripts/daily_startup.sh

# Wait for completion, then verify:
open http://localhost:8080
```

### Intraday Checks (Every 2-3 hours) - 10 seconds
```bash
./scripts/quick_check.sh
```

### Evening Routine (6:00 PM) - 5 minutes
```bash
# Generate performance report first
./scripts/generate_performance_report.sh --period daily --format html

# Safe shutdown
./scripts/daily_shutdown.sh

# Review report
cat /tmp/shutdown_$(date +%Y%m%d).log | grep "Daily Performance"
```

### Weekly Maintenance (Sunday) - 30 minutes
```bash
# 1. Full backup
./scripts/backup.sh --full

# 2. Clean logs
./scripts/cleanup_logs.sh --days 7

# 3. Optimize database
./scripts/optimize_database.sh --vacuum --analyze

# 4. Generate weekly report
./scripts/generate_performance_report.sh --period weekly --format html

# 5. System status report
./scripts/system_status_report.sh --save ~/weekly_status.txt
```

### Monthly Maintenance (1st of month) - 60 minutes
```bash
# 1. Full system backup
./scripts/backup.sh --full --keep-days 90

# 2. Complete database optimization
./scripts/optimize_database.sh --all

# 3. Aggressive log cleanup
./scripts/cleanup_logs.sh --days 30

# 4. Monthly performance report
./scripts/generate_performance_report.sh --period monthly --format html

# 5. Email status report
./scripts/system_status_report.sh --email admin@example.com
```

---

## Script Dependencies

### Required Packages
```bash
# All scripts need:
sudo apt-get install -y curl jq bc docker-compose python3

# For email reports:
sudo apt-get install -y mailutils

# For database operations:
# (Already installed with Docker postgres image)

# Python packages:
pip install requests python-dotenv
```

### Required Services
- Docker and Docker Compose
- All 10 microservices running
- TimescaleDB container
- Redis container
- RabbitMQ container

---

## Troubleshooting

### Script Won't Execute
```bash
# Make executable
chmod +x scripts/script_name.sh

# Check shebang
head -1 scripts/script_name.sh
# Should be: #!/bin/bash
```

### Service Not Responding
```bash
# Check specific service
docker-compose logs service-name

# Restart service
docker-compose restart service-name

# Full restart
./scripts/startup.sh --skip-build
```

### Database Issues
```bash
# Check database health
docker exec crypto-trading-bot-timescaledb-1 pg_isready

# View logs
docker logs crypto-trading-bot-timescaledb-1

# Optimize
./scripts/optimize_database.sh --analyze
```

### Disk Space Issues
```bash
# Clean logs
./scripts/cleanup_logs.sh --days 3

# Docker cleanup
docker system prune -a

# Check space
df -h
```

---

## Exit Code Reference

All scripts use standard exit codes:

| Code | Meaning | Action Required |
|------|---------|-----------------|
| 0 | Success | None - all good |
| 1 | Warning | Review logs, may need attention |
| 2 | Critical | Immediate action required |

**Usage in automation:**
```bash
if ./scripts/quick_check.sh; then
    echo "System healthy"
else
    echo "System issues detected"
    # Send alert, page admin, etc.
fi
```

---

## Automation Examples

### Cron Jobs
```bash
# Edit crontab
crontab -e

# Morning startup (9:00 AM)
0 9 * * * cd /mnt/d/Bimo_max/crypto-trading-bot && ./scripts/daily_startup.sh

# Intraday checks (every 30 minutes during trading hours)
*/30 9-17 * * * cd /mnt/d/Bimo_max/crypto-trading-bot && ./scripts/quick_check.sh

# Evening shutdown (6:00 PM)
0 18 * * * cd /mnt/d/Bimo_max/crypto-trading-bot && ./scripts/daily_shutdown.sh

# Daily backup (11:00 PM)
0 23 * * * cd /mnt/d/Bimo_max/crypto-trading-bot && ./scripts/backup.sh --full

# Weekly maintenance (Sunday 2:00 AM)
0 2 * * 0 cd /mnt/d/Bimo_max/crypto-trading-bot && ./scripts/cleanup_logs.sh --days 7 && ./scripts/optimize_database.sh --vacuum --analyze

# Daily status report (8:00 AM)
0 8 * * * cd /mnt/d/Bimo_max/crypto-trading-bot && ./scripts/system_status_report.sh --email admin@example.com
```

### Systemd Service
```bash
# Create service file: /etc/systemd/system/crypto-bot-monitor.service
[Unit]
Description=Crypto Trading Bot Monitoring
After=docker.service

[Service]
Type=simple
User=your-user
WorkingDirectory=/mnt/d/Bimo_max/crypto-trading-bot
ExecStart=/usr/bin/python3 /mnt/d/Bimo_max/crypto-trading-bot/scripts/monitor.py --interval 60
Restart=always

[Install]
WantedBy=multi-user.target

# Enable and start
sudo systemctl enable crypto-bot-monitor
sudo systemctl start crypto-bot-monitor
```

---

## Quick Reference Table

| Need | Script | Duration |
|------|--------|----------|
| Start trading day | `daily_startup.sh` | 5 min |
| Quick health check | `quick_check.sh` | 10 sec |
| End trading day | `daily_shutdown.sh` | 3 min |
| Full system start | `startup.sh` | 10 min |
| Detailed health | `health_check.sh --verbose` | 30 sec |
| Continuous monitor | `monitor.py` | Ongoing |
| Risk validation | `validate_risk_limits.py` | 10 sec |
| Backup everything | `backup.sh --full` | 5 min |
| Clean old logs | `cleanup_logs.sh` | 2 min |
| Optimize database | `optimize_database.sh --all` | 30 min |
| Performance report | `generate_performance_report.sh` | 10 sec |
| System status | `system_status_report.sh` | 15 sec |

---

## Support

**Documentation:**
- Master guide: [SCRIPTS_OPERATIONAL_GUIDE.md](SCRIPTS_OPERATIONAL_GUIDE.md)
- Quick reference: [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
- This index: [SCRIPTS_INDEX.md](SCRIPTS_INDEX.md)

**Getting Help:**
```bash
# Most scripts have help
./scripts/script_name.sh --help

# View script source
cat scripts/script_name.sh

# Check logs
tail -f /tmp/monitor_$(date +%Y%m%d).log
```

---

**Last Updated:** 2025-11-14
**Version:** 1.0.0
**Total Scripts:** 30+
**Lines of Code:** 15,000+

**System Status:** ✅ Production-Ready (Paper Trading)
