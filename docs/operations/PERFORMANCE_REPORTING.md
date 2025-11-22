# Performance Reporting Guide

**Version:** 1.0.0
**Last Updated:** 2025-11-19
**Status:** Production Ready

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Manual Report Generation](#manual-report-generation)
4. [Automated Reports](#automated-reports)
5. [Report Metrics Explained](#report-metrics-explained)
6. [Configuration](#configuration)
7. [Troubleshooting](#troubleshooting)
8. [Sample Reports](#sample-reports)

---

## Overview

The Weekly Performance Report system provides comprehensive analysis of your trading bot's performance, including:

- **Trading Metrics:** Win rate, P&L, profit factor, trade quality
- **Risk Metrics:** Sharpe ratio, maximum drawdown, volatility
- **Performance Analysis:** By symbol, by strategy, over time
- **Visualizations:** Charts and graphs for easy interpretation
- **Multi-Format Output:** JSON, Markdown, HTML, CSV

### Key Features

- Automated weekly report generation
- Email delivery with charts
- Customizable metrics and thresholds
- Historical data analysis
- Performance trending
- Risk assessment

---

## Quick Start

### Prerequisites

```bash
# Install required Python packages
pip install pandas numpy matplotlib seaborn psycopg2-binary pyyaml

# Verify database connection
psql -h localhost -p 5432 -U cryptobot -d cryptobot -c "SELECT COUNT(*) FROM trades;"
```

### Generate Your First Report

```bash
# Navigate to project directory
cd /mnt/d/Bimo_max/crypto-trading-bot

# Generate report for last 7 days
python3 scripts/weekly_performance_report.py

# View the generated report
cd reports/$(date +%Y-%m-%d)
ls -la
# You'll see: performance_report.html, performance_report.md, etc.

# Open HTML report in browser
xdg-open performance_report.html  # Linux
open performance_report.html       # macOS
```

**That's it!** Your first performance report is generated.

---

## Manual Report Generation

### Basic Usage

```bash
# Default: Last 7 days, all formats
python3 scripts/weekly_performance_report.py

# Specific date range
python3 scripts/weekly_performance_report.py \
    --start 2025-11-01 \
    --end 2025-11-07

# Generate only HTML and PDF
python3 scripts/weekly_performance_report.py \
    --formats html csv

# Custom output directory
python3 scripts/weekly_performance_report.py \
    --output /path/to/custom/directory

# Verbose output for debugging
python3 scripts/weekly_performance_report.py --verbose
```

### Advanced Options

```bash
# Dry run (calculate metrics but don't generate files)
python3 scripts/weekly_performance_report.py --dry-run

# Send via email
python3 scripts/weekly_performance_report.py --email

# Use custom configuration file
python3 scripts/weekly_performance_report.py \
    --config /path/to/custom_config.yaml

# Generate report for last 30 days
python3 scripts/weekly_performance_report.py \
    --start $(date -d '30 days ago' +%Y-%m-%d) \
    --end $(date +%Y-%m-%d)
```

### Command-Line Reference

| Option | Description | Default |
|--------|-------------|---------|
| `--start` | Start date (YYYY-MM-DD) | 7 days ago |
| `--end` | End date (YYYY-MM-DD) | Today |
| `--config` | Config file path | `config/performance_report_config.yaml` |
| `--output` | Output directory | `reports/` |
| `--formats` | Report formats (json, markdown, html, csv) | All formats |
| `--email` | Send report via email | Disabled |
| `--dry-run` | Calculate metrics only | Disabled |
| `--verbose` | Enable debug logging | Disabled |

---

## Automated Reports

### Setup Automated Weekly Reports

```bash
# Install cron job for weekly reports (Monday at 9 AM)
cd /mnt/d/Bimo_max/crypto-trading-bot
./scripts/setup_weekly_report_cron.sh

# Custom schedule (Friday at 5 PM)
./scripts/setup_weekly_report_cron.sh --day Friday --time "17:00"

# Remove automated reports
./scripts/setup_weekly_report_cron.sh --remove
```

### Verify Cron Installation

```bash
# List all cron jobs
crontab -l

# You should see:
# ===================================================================
# Crypto Trading Bot - Weekly Performance Report
# Runs every Monday at 09:00
# ===================================================================
# 0 9 * * 1 cd /mnt/d/Bimo_max/crypto-trading-bot && /usr/bin/python3 ...
```

### Monitor Automated Reports

```bash
# View cron execution logs
tail -f /mnt/d/Bimo_max/crypto-trading-bot/logs/weekly_report_cron.log

# Check for errors
tail -f /mnt/d/Bimo_max/crypto-trading-bot/logs/weekly_report_error.log

# Test cron job manually
cd /mnt/d/Bimo_max/crypto-trading-bot
python3 scripts/weekly_performance_report.py --email
```

---

## Report Metrics Explained

### Trading Performance Metrics

#### Total Trades
- **Definition:** Total number of trade executions (buy and sell orders)
- **Interpretation:** Higher volume indicates more active trading
- **Typical Range:** 10-100+ per week depending on strategy

#### Win Rate
- **Definition:** Percentage of profitable trades: `(Winning Trades / Total Trades) × 100`
- **Interpretation:**
  - Below 40%: Review strategy, may need adjustment
  - 40-60%: Normal range for most strategies
  - Above 60%: Excellent performance
- **Note:** High win rate doesn't guarantee profitability if losses are larger than wins

#### Profit Factor
- **Definition:** Ratio of gross profit to gross loss: `Gross Profit / Gross Loss`
- **Interpretation:**
  - Less than 1.0: Losing strategy (more losses than gains)
  - 1.0-1.5: Marginal profitability
  - 1.5-2.0: Good performance
  - Above 2.0: Excellent performance
- **Example:** Profit Factor of 2.0 means you make $2 for every $1 lost

#### Average Win / Average Loss
- **Definition:** Mean profit per winning trade / Mean loss per losing trade
- **Interpretation:** Compare these to understand risk/reward ratio
- **Ideal:** Average Win should be at least 1.5× Average Loss

### Risk Metrics

#### Sharpe Ratio
- **Definition:** Risk-adjusted return metric: `(Return - Risk-Free Rate) / Standard Deviation`
- **Interpretation:**
  - Less than 0: Strategy losing money
  - 0-1: Subpar risk-adjusted returns
  - 1-2: Good risk-adjusted returns
  - 2-3: Very good risk-adjusted returns
  - Above 3: Excellent (rare)
- **Note:** Higher is better; measures return per unit of risk

#### Maximum Drawdown
- **Definition:** Largest peak-to-trough decline in portfolio value
- **Interpretation:**
  - Less than 5%: Conservative, low-risk strategy
  - 5-10%: Moderate risk
  - 10-20%: Aggressive strategy
  - Above 20%: High risk, review risk management
- **Example:** Max drawdown of 15% means at worst, portfolio was down 15% from peak

### Portfolio Metrics

#### ROI (Return on Investment)
- **Definition:** Total return as percentage: `(Final Value - Initial Value) / Initial Value × 100`
- **Interpretation:**
  - Negative: Losing money
  - 0-5% weekly: Conservative gains
  - 5-10% weekly: Good performance
  - Above 10% weekly: Excellent (but verify sustainability)

#### Total P&L (Profit & Loss)
- **Definition:** Sum of all realized profits and losses in USDT
- **Components:**
  - Realized P&L: Actual profits/losses from closed positions
  - Unrealized P&L: Paper profits/losses from open positions
  - Total P&L: Realized + Unrealized

### Performance Breakdowns

#### By Symbol
- Shows which trading pairs are most profitable
- Helps identify best-performing markets
- Use to allocate more capital to profitable symbols

#### By Strategy
- Compares performance of different trading strategies
- Identifies which strategies work best in current market
- Helps optimize strategy allocation

---

## Configuration

### Configuration File Location

```
/mnt/d/Bimo_max/crypto-trading-bot/config/performance_report_config.yaml
```

### Key Configuration Sections

#### 1. Database Connection

```yaml
database:
  host: localhost
  port: 5432
  user: cryptobot
  password: cryptobot_secure_2024
  database: cryptobot
```

#### 2. Email Settings

```yaml
email:
  server: smtp.gmail.com
  port: 587
  username: your-email@gmail.com
  password: your-app-password  # Use app-specific password!
  recipients:
    - trader@example.com
    - manager@example.com
```

**Gmail Setup:**
1. Enable 2-Factor Authentication
2. Generate App-Specific Password: https://myaccount.google.com/apppasswords
3. Use app password in configuration (not your regular password)

#### 3. Report Generation

```yaml
report:
  output_directory: /mnt/d/Bimo_max/crypto-trading-bot/reports
  formats:
    - markdown
    - html
    - json
    - csv
  include_charts: true
```

#### 4. Scheduling

```yaml
schedule:
  day: Monday
  time: "09:00"
  timezone: UTC
  period: weekly
```

#### 5. Alert Thresholds

```yaml
alerts:
  min_win_rate: 45.0          # Alert if win rate drops below 45%
  max_drawdown_threshold: 15.0 # Alert if drawdown exceeds 15%
  min_sharpe_ratio: 0.5       # Alert if Sharpe below 0.5
  send_alert_email: true
```

### Environment Variables

For production, use environment variables for sensitive data:

```bash
# In .env file or export
export POSTGRES_PASSWORD="your_secure_password"
export SMTP_PASSWORD="your_smtp_password"
```

Then reference in config:

```yaml
database:
  password: ${POSTGRES_PASSWORD}

email:
  password: ${SMTP_PASSWORD}
```

---

## Troubleshooting

### Common Issues

#### 1. "Database connection failed"

**Symptoms:**
```
ERROR - Failed to connect to database: connection refused
```

**Solutions:**
```bash
# Check if PostgreSQL is running
docker ps | grep postgres

# Check database credentials
psql -h localhost -p 5432 -U cryptobot -d cryptobot

# Verify database exists
psql -h localhost -p 5432 -U cryptobot -l

# Check firewall/network
telnet localhost 5432
```

#### 2. "No trades found in specified period"

**Symptoms:**
```
WARNING - No trades found in specified period
```

**Solutions:**
```bash
# Check if trades exist in database
psql -h localhost -p 5432 -U cryptobot -d cryptobot \
  -c "SELECT COUNT(*), MIN(executed_at), MAX(executed_at) FROM trades;"

# Adjust date range
python3 scripts/weekly_performance_report.py \
  --start 2025-10-01 \
  --end 2025-11-19

# Verify trading bot is running
docker ps | grep trading-engine
```

#### 3. "Email sending failed"

**Symptoms:**
```
ERROR - Failed to send email: Authentication failed
```

**Solutions:**
```bash
# For Gmail: Use app-specific password
# 1. Enable 2FA on Google Account
# 2. Generate app password at: https://myaccount.google.com/apppasswords
# 3. Update config with app password (not regular password)

# Test SMTP connection
telnet smtp.gmail.com 587

# Verify credentials in config
grep "password" config/performance_report_config.yaml

# Test email without actual sending (dry run)
python3 scripts/weekly_performance_report.py --dry-run
```

#### 4. "Chart generation failed"

**Symptoms:**
```
ERROR - Error generating charts: No module named 'matplotlib'
```

**Solutions:**
```bash
# Install missing dependencies
pip install matplotlib seaborn pandas numpy

# For headless servers (no display)
export MPLBACKEND=Agg
python3 scripts/weekly_performance_report.py

# Check chart output directory exists
ls -la reports/$(date +%Y-%m-%d)/charts/
```

#### 5. "Permission denied"

**Symptoms:**
```
ERROR - Permission denied: /mnt/d/Bimo_max/crypto-trading-bot/reports
```

**Solutions:**
```bash
# Fix directory permissions
mkdir -p /mnt/d/Bimo_max/crypto-trading-bot/reports
chmod 755 /mnt/d/Bimo_max/crypto-trading-bot/reports

# Fix script permissions
chmod +x /mnt/d/Bimo_max/crypto-trading-bot/scripts/weekly_performance_report.py

# Check file ownership
ls -la /mnt/d/Bimo_max/crypto-trading-bot/reports
```

### Debug Mode

Enable verbose logging for troubleshooting:

```bash
# Run with debug output
python3 scripts/weekly_performance_report.py --verbose

# Check log file
tail -f logs/performance_report.log

# Dry run to test without generating files
python3 scripts/weekly_performance_report.py --dry-run --verbose
```

### Getting Help

If issues persist:

1. Check logs: `tail -f logs/performance_report.log`
2. Run in dry-run mode: `python3 scripts/weekly_performance_report.py --dry-run --verbose`
3. Verify configuration: `cat config/performance_report_config.yaml`
4. Test database connection: `psql -h localhost -p 5432 -U cryptobot -d cryptobot`
5. Check dependencies: `pip list | grep -E "pandas|numpy|matplotlib|psycopg2"`

---

## Sample Reports

### Example Report Output

After running the script, you'll find these files in `reports/YYYY-MM-DD/`:

```
reports/2025-11-19/
├── performance_report.json      # Machine-readable data
├── performance_report.md        # Markdown for documentation
├── performance_report.html      # Web-viewable report
├── trading_performance.csv      # Excel-compatible data
└── charts/
    ├── pnl_over_time.png
    ├── portfolio_value.png
    ├── win_rate_trend.png
    ├── symbol_performance.png
    └── daily_volume.png
```

### Sample Metrics Output

```json
{
  "total_trades": 42,
  "total_positions": 21,
  "win_rate": 57.14,
  "total_pnl": 342.50,
  "roi_percentage": 3.43,
  "sharpe_ratio": 1.82,
  "max_drawdown": -4.23,
  "profit_factor": 2.15,
  "avg_trade_duration_hours": 18.5
}
```

### Sample Email Report

When email is enabled, recipients receive:

**Subject:** Weekly Performance Report - 2025-11-12 to 2025-11-19

**Body:** HTML-formatted report with:
- Executive summary dashboard
- Key metrics table
- Performance breakdowns
- Embedded charts
- Risk assessment

### Sample Markdown Report

```markdown
# Weekly Performance Report

**Period:** 2025-11-12 to 2025-11-19
**Generated:** 2025-11-19 09:00:00

## Executive Summary

| Metric | Value |
|--------|-------|
| **Total Trades** | 42 |
| **Win Rate** | 57.14% |
| **Total P&L** | $342.50 USDT |
| **ROI** | 3.43% |
| **Sharpe Ratio** | 1.8234 |

...
```

---

## Best Practices

### Report Review Workflow

**Weekly Routine:**
1. Receive automated report Monday morning
2. Review executive summary for red flags
3. Check win rate trend (should be stable)
4. Analyze worst trades for patterns
5. Verify risk metrics are within thresholds
6. Compare performance across symbols
7. Adjust strategy if needed

**Monthly Deep Dive:**
1. Generate 30-day report for longer trends
2. Compare month-over-month performance
3. Review all alert thresholds
4. Update strategy based on findings
5. Archive reports for compliance

### Metric Targets

Set realistic targets based on your strategy:

```yaml
# Conservative Strategy
win_rate: 55-65%
sharpe_ratio: 1.0-2.0
max_drawdown: -5% to -10%
weekly_roi: 1-3%

# Aggressive Strategy
win_rate: 45-55%
sharpe_ratio: 0.5-1.5
max_drawdown: -10% to -20%
weekly_roi: 3-7%
```

### Report Retention

```bash
# Keep reports for compliance/analysis
# Automatic cleanup after 90 days (configurable)

# Manual archive
tar -czf reports_archive_$(date +%Y%m).tar.gz reports/

# Restore from archive
tar -xzf reports_archive_202511.tar.gz
```

---

## Appendix

### Dependencies

Required Python packages:
```
pandas>=1.5.0
numpy>=1.23.0
matplotlib>=3.6.0
seaborn>=0.12.0
psycopg2-binary>=2.9.0
PyYAML>=6.0
```

Install with:
```bash
pip install -r requirements.txt
```

### File Structure

```
crypto-trading-bot/
├── config/
│   └── performance_report_config.yaml
├── scripts/
│   ├── weekly_performance_report.py
│   ├── setup_weekly_report_cron.sh
│   ├── cleanup_old_reports.sh
│   └── notify_report_error.sh
├── reports/
│   └── YYYY-MM-DD/
│       ├── performance_report.*
│       └── charts/
├── logs/
│   ├── performance_report.log
│   ├── weekly_report_cron.log
│   └── weekly_report_error.log
└── docs/
    └── operations/
        └── PERFORMANCE_REPORTING.md
```

### API Reference

For programmatic access:

```python
from scripts.weekly_performance_report import PerformanceReporter
from datetime import datetime, timedelta

# Initialize reporter
reporter = PerformanceReporter(
    db_config={
        'host': 'localhost',
        'port': 5432,
        'user': 'cryptobot',
        'password': 'password',
        'database': 'cryptobot'
    },
    start_date=datetime.now() - timedelta(days=7),
    end_date=datetime.now()
)

# Connect and fetch data
reporter.connect_database()
reporter.fetch_trading_data()
reporter.fetch_positions_data()
reporter.fetch_portfolio_snapshots()

# Calculate metrics
metrics = reporter.calculate_metrics()
print(metrics)

# Generate reports
report_files = reporter.save_reports(
    output_dir='./reports',
    formats=['json', 'html']
)

# Cleanup
reporter.close_database()
```

---

**Document Version:** 1.0.0
**Last Updated:** 2025-11-19
**Maintained By:** Crypto Trading Bot Team
**Next Review:** 2025-12-19
