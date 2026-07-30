# Weekly Performance Report - Quick Start Guide

**5-Minute Setup Guide**

---

## Step 1: Install Dependencies (1 minute)

```bash
# Install required Python packages
pip install pandas numpy matplotlib seaborn psycopg2-binary pyyaml
```

---

## Step 2: Configure Settings (2 minutes)

```bash
# Edit configuration file
nano config/performance_report_config.yaml

# Update these three sections:

# 1. DATABASE (lines 9-15)
database:
  host: localhost          # Your PostgreSQL host
  port: 5432
  user: cryptobot          # Your database user
  password: your_password  # Your database password
  database: cryptobot

# 2. EMAIL (lines 20-28)
email:
  server: smtp.gmail.com
  port: 587
  username: your-email@gmail.com
  password: your-app-password  # Gmail app-specific password
  recipients:
    - trader@example.com

# 3. REPORT (lines 34-37)
report:
  output_directory: /mnt/d/Bimo_max/crypto-trading-bot/reports

# Save and exit (Ctrl+X, Y, Enter)
```

**Gmail Users:** Generate app-specific password at: https://myaccount.google.com/apppasswords

---

## Step 3: Test Report Generation (1 minute)

```bash
# Navigate to project directory
cd /mnt/d/Bimo_max/crypto-trading-bot

# Generate test report (last 7 days)
python3 scripts/weekly_performance_report.py --verbose

# View generated files
ls -lh reports/$(date +%Y-%m-%d)/
```

**Expected output:**
```
performance_report.json
performance_report.md
performance_report.html
trading_performance.csv
charts/
  ├── pnl_over_time.png
  ├── portfolio_value.png
  ├── win_rate_trend.png
  ├── symbol_performance.png
  └── daily_volume.png
```

---

## Step 4: View Report (30 seconds)

```bash
# Open HTML report in browser
cd reports/$(date +%Y-%m-%d)

# Linux
xdg-open performance_report.html

# macOS
open performance_report.html

# Windows (WSL)
explorer.exe performance_report.html
```

---

## Step 5: Setup Automated Weekly Reports (30 seconds)

```bash
# Install cron job (runs every Monday at 9 AM)
cd /mnt/d/Bimo_max/crypto-trading-bot
./scripts/setup_weekly_report_cron.sh

# Verify installation
crontab -l | grep weekly_performance

# Monitor future executions
tail -f logs/weekly_report_cron.log
```

---

## Done! 🎉

Your weekly performance reports are now automated!

**What happens next:**
- Every Monday at 9 AM, a new report is generated
- Report is emailed to configured recipients
- Reports are saved to `reports/YYYY-MM-DD/`
- Old reports are cleaned up after 90 days

---

## Common Commands

```bash
# Generate report for custom date range
python3 scripts/weekly_performance_report.py \
  --start 2025-11-01 \
  --end 2025-11-07

# Generate and email immediately
python3 scripts/weekly_performance_report.py --email

# Generate only specific formats
python3 scripts/weekly_performance_report.py --formats html csv

# Dry run (test without creating files)
python3 scripts/weekly_performance_report.py --dry-run

# Custom schedule (Friday at 5 PM)
./scripts/setup_weekly_report_cron.sh --day Friday --time "17:00"

# Remove automated reports
./scripts/setup_weekly_report_cron.sh --remove
```

---

## Troubleshooting

**Problem:** "Database connection failed"
```bash
# Check PostgreSQL is running
docker ps | grep postgres

# Test connection
psql -h localhost -p 5432 -U cryptobot -d cryptobot
```

**Problem:** "Email sending failed"
```bash
# For Gmail: Use app-specific password, not account password
# Generate at: https://myaccount.google.com/apppasswords
```

**Problem:** "No trades found"
```bash
# Check if trades exist
psql -h localhost -p 5432 -U cryptobot -d cryptobot \
  -c "SELECT COUNT(*) FROM trades;"

# Adjust date range
python3 scripts/weekly_performance_report.py \
  --start 2025-10-01 --end 2025-11-19
```

---

## Need More Help?

- **Full Documentation:** `docs/operations/PERFORMANCE_REPORTING.md`
- **Configuration Guide:** `config/performance_report_config.yaml` (see comments)
- **Implementation Details:** `WEEKLY_PERFORMANCE_REPORT_IMPLEMENTATION.md`
- **Run Tests:** `python3 tests/unit/test_performance_reporter.py`

---

**Version:** 1.0.0
**Last Updated:** 2025-11-19
