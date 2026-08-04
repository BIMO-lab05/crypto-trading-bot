# Weekly Performance Report System - File Index

Quick navigation to all files related to the weekly performance reporting system.

---

## Core Files

### 1. Main Script
**File:** `scripts/weekly_performance_report.py`
**Lines:** 1,317
**Purpose:** Main reporting engine with database queries, metrics calculation, and report generation

**Key Functions:**
- `PerformanceReporter` - Main class
- `fetch_trading_data()` - Query trades from database
- `calculate_metrics()` - Compute all performance metrics
- `generate_charts()` - Create visualizations
- `create_html_report()` - Generate HTML report
- `send_email()` - Email delivery

**Usage:**
```bash
python3 scripts/weekly_performance_report.py
python3 scripts/weekly_performance_report.py --start 2025-11-01 --end 2025-11-07
python3 scripts/weekly_performance_report.py --email --verbose
```

---

### 2. Configuration File
**File:** `config/performance_report_config.yaml`
**Lines:** 294
**Purpose:** All configuration settings for report generation

**Sections:**
- Database connection settings
- Email/SMTP configuration
- Report output settings
- Scheduling configuration
- Alert thresholds
- Advanced options

**Usage:**
```bash
nano config/performance_report_config.yaml
# Edit database, email, and report settings
```

---

### 3. Cron Setup Script
**File:** `scripts/setup_weekly_report_cron.sh`
**Lines:** 407
**Purpose:** Install and manage automated weekly reports

**Features:**
- Install cron job for weekly execution
- Configure schedule (day/time)
- Setup log rotation
- Create cleanup scripts

**Usage:**
```bash
./scripts/setup_weekly_report_cron.sh                    # Install (Monday 9 AM)
./scripts/setup_weekly_report_cron.sh --day Friday --time "17:00"
./scripts/setup_weekly_report_cron.sh --remove           # Uninstall
```

---

## Documentation

### 4. Full Documentation
**File:** `docs/operations/PERFORMANCE_REPORTING.md`
**Lines:** 713
**Purpose:** Comprehensive user guide and reference

**Sections:**
- Quick Start (5 minutes)
- Manual report generation
- Automated reports setup
- Metrics explained (Sharpe ratio, drawdown, etc.)
- Configuration reference
- Troubleshooting guide
- Sample reports
- Best practices

**Read Online:**
```bash
cat docs/operations/PERFORMANCE_REPORTING.md
# or open in editor/browser
```

---

### 5. Quick Start Guide
**File:** `WEEKLY_REPORT_QUICK_START.md`
**Lines:** ~100
**Purpose:** 5-minute setup guide

**Steps:**
1. Install dependencies
2. Configure settings
3. Test report generation
4. View report
5. Setup automation

---

### 6. Implementation Summary
**File:** `WEEKLY_PERFORMANCE_REPORT_IMPLEMENTATION.md`
**Lines:** ~600
**Purpose:** Complete implementation details and technical reference

**Contents:**
- All files created
- Features implemented
- Example outputs
- Installation instructions
- Configuration options
- Troubleshooting
- Performance metrics
- Security considerations

---

## Testing

### 7. Unit Tests
**File:** `tests/unit/test_performance_reporter.py`
**Lines:** 668
**Purpose:** Comprehensive test suite

**Test Coverage:**
- Database operations
- Data fetching
- Metrics calculation
- Report generation (all formats)
- Chart creation
- Email sending
- Error handling
- Edge cases

**Run Tests:**
```bash
python3 tests/unit/test_performance_reporter.py
pytest tests/unit/test_performance_reporter.py --cov=scripts
```

---

## Generated Files (Examples)

### 8. Report Output Directory
**Location:** `reports/YYYY-MM-DD/`
**Structure:**
```
reports/2025-11-19/
├── performance_report.json      # Machine-readable metrics
├── performance_report.md        # Markdown documentation
├── performance_report.html      # Web-viewable report
├── trading_performance.csv      # Excel-compatible data
└── charts/
    ├── pnl_over_time.png
    ├── portfolio_value.png
    ├── win_rate_trend.png
    ├── symbol_performance.png
    └── daily_volume.png
```

---

## Logs

### 9. Log Files
**Locations:**
- `logs/performance_report.log` - Main script execution log
- `logs/weekly_report_cron.log` - Automated cron execution log
- `logs/weekly_report_error.log` - Error log for troubleshooting

**View Logs:**
```bash
tail -f logs/performance_report.log
tail -f logs/weekly_report_cron.log
grep ERROR logs/performance_report.log
```

---

## Quick Commands

### Generate Report
```bash
# Default (last 7 days)
python3 scripts/weekly_performance_report.py

# Custom date range
python3 scripts/weekly_performance_report.py \
  --start 2025-11-01 --end 2025-11-07

# With email
python3 scripts/weekly_performance_report.py --email

# Dry run (test only)
python3 scripts/weekly_performance_report.py --dry-run --verbose
```

### Setup Automation
```bash
# Install
./scripts/setup_weekly_report_cron.sh

# Custom schedule
./scripts/setup_weekly_report_cron.sh --day Friday --time "17:00"

# Remove
./scripts/setup_weekly_report_cron.sh --remove
```

### View Reports
```bash
# List all reports
ls -lt reports/

# View latest HTML report
cd reports/$(ls -t reports/ | head -1)
xdg-open performance_report.html
```

### Check Status
```bash
# Verify cron job installed
crontab -l | grep weekly_performance

# Check recent executions
tail -20 logs/weekly_report_cron.log

# Test database connection
psql -h localhost -p 5432 -U cryptobot -d cryptobot
```

---

## File Tree

```
crypto-trading-bot/
├── scripts/
│   ├── weekly_performance_report.py          # Main script
│   └── setup_weekly_report_cron.sh            # Automation setup
├── config/
│   └── performance_report_config.yaml         # Configuration
├── docs/
│   └── operations/
│       └── PERFORMANCE_REPORTING.md           # Full documentation
├── tests/
│   └── unit/
│       └── test_performance_reporter.py       # Unit tests
├── reports/                                    # Generated reports
│   └── YYYY-MM-DD/
│       ├── performance_report.json
│       ├── performance_report.md
│       ├── performance_report.html
│       ├── trading_performance.csv
│       └── charts/
│           ├── pnl_over_time.png
│           └── ...
├── logs/                                       # Log files
│   ├── performance_report.log
│   ├── weekly_report_cron.log
│   └── weekly_report_error.log
├── WEEKLY_REPORT_QUICK_START.md               # Quick setup
├── WEEKLY_PERFORMANCE_REPORT_IMPLEMENTATION.md # Implementation details
└── WEEKLY_REPORT_INDEX.md                     # This file
```

---

## Dependencies

Required Python packages (install with pip):
```
pandas>=1.5.0
numpy>=1.23.0
matplotlib>=3.6.0
seaborn>=0.12.0
psycopg2-binary>=2.9.0
PyYAML>=6.0
```

---

## Next Steps

1. **First Time Setup:**
   - Read: `WEEKLY_REPORT_QUICK_START.md`
   - Configure: `config/performance_report_config.yaml`
   - Run: `python3 scripts/weekly_performance_report.py --verbose`

2. **Automation:**
   - Setup: `./scripts/setup_weekly_report_cron.sh`
   - Verify: `crontab -l`

3. **Troubleshooting:**
   - Read: `docs/operations/PERFORMANCE_REPORTING.md` (Section 7)
   - Check logs: `logs/performance_report.log`

4. **Testing:**
   - Run: `python3 tests/unit/test_performance_reporter.py`

---

**Last Updated:** 2025-11-19
**Status:** Production Ready
**Version:** 1.0.0
