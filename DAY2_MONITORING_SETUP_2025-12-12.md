# Day 2 Paper Trading Monitoring Setup Report
**Created:** 2025-12-12
**Purpose:** Comprehensive monitoring and validation tools for Day 2 of paper trading validation

---

## Section 1: Monitoring Tools Created

### 1.1 Day 2 Monitoring Dashboard
**File:** `/mnt/d/Bimo_max/crypto-trading-bot/scripts/day2_monitor.sh`

**Description:** Real-time monitoring dashboard for Day 2 paper trading with comprehensive system health, trading status, portfolio summary, and risk metrics.

**Features:**
- System health check (Docker containers + service endpoints)
- Trading engine status display
- Portfolio summary with P&L
- Today's performance metrics
- Open positions with unrealized P&L
- Risk status and budget utilization
- Signal activity tracking
- Recent trades display
- Day 1 vs Day 2 comparison
- Continuous refresh mode

**Usage:**
```bash
# Single run
./scripts/day2_monitor.sh

# Continuous monitoring (30-second refresh)
./scripts/day2_monitor.sh --continuous
./scripts/day2_monitor.sh -c
```

---

### 1.2 Daily Summary Generator
**File:** `/mnt/d/Bimo_max/crypto-trading-bot/scripts/generate_daily_summary.sh`

**Description:** Generates comprehensive daily trading summary reports with detailed statistics and performance breakdowns.

**Features:**
- Overall statistics (trades, wins/losses, P&L, win rate)
- Performance by symbol
- Performance by hour (UTC)
- Performance by side (LONG/SHORT)
- Trade duration analysis
- Complete trade list
- Portfolio and risk metrics
- Cumulative performance tracking

**Usage:**
```bash
# Generate summary for today
./scripts/generate_daily_summary.sh

# Generate summary for specific date
./scripts/generate_daily_summary.sh 2025-12-13

# Output saved to: /mnt/d/Bimo_max/crypto-trading-bot/reports/daily_summary_YYYY-MM-DD.txt
```

---

### 1.3 Alert Monitoring Script
**File:** `/mnt/d/Bimo_max/crypto-trading-bot/scripts/monitor_alerts.sh`

**Description:** Monitors and tests the alert system, displays channel status, and shows recent alerts.

**Features:**
- Notification service health check
- Alert channel status (Telegram, Email, Slack, Discord)
- Test mode for validating alert delivery
- Recent alerts display
- Critical alerts today
- Alert statistics (24h)
- Configured trigger list

**Usage:**
```bash
# View alert status
./scripts/monitor_alerts.sh

# Test all alert channels
./scripts/monitor_alerts.sh --test
./scripts/monitor_alerts.sh -t
```

---

### 1.4 Day Comparison Tool
**File:** `/mnt/d/Bimo_max/crypto-trading-bot/scripts/compare_days.sh`

**Description:** Compares trading performance between two days with detailed breakdown and improvement analysis.

**Features:**
- Side-by-side daily comparison
- Improvement analysis (P&L change, win rate change)
- Symbol performance comparison
- Hourly performance comparison
- Long vs Short comparison
- Summary assessment

**Usage:**
```bash
# Compare Day 1 vs Day 2 (defaults to yesterday vs today)
./scripts/compare_days.sh

# Compare specific dates
./scripts/compare_days.sh 2025-12-12 2025-12-13
```

---

### 1.5 Daily Loss Checker
**File:** `/mnt/d/Bimo_max/crypto-trading-bot/scripts/check_daily_loss.sh`

**Description:** Automated script to check daily loss against thresholds and trigger alerts/emergency stop if needed.

**Features:**
- Checks daily P&L against configurable thresholds
- Warning at 3% daily loss
- Critical alert at 4% daily loss
- Emergency stop trigger at 5% daily loss
- Sends alerts via notification service and Telegram
- Checks unrealized P&L as well
- Logs all checks to file

**Usage:**
```bash
# Manual run
./scripts/check_daily_loss.sh

# Add to cron for every 4 hours
# 0 */4 * * * /mnt/d/Bimo_max/crypto-trading-bot/scripts/check_daily_loss.sh
```

---

## Section 2: Validation Checklist

### Day 2 Validation Checklist
**File:** `/mnt/d/Bimo_max/crypto-trading-bot/DAY2_VALIDATION_CHECKLIST.md`

**Purpose:** Comprehensive checklist for Day 2 validation with morning, midday, and evening checks.

**Sections:**
1. Morning Checks (08:00-12:00 UTC)
   - System health verification
   - Trading activity checks
   - Performance review

2. Midday Checks (12:00-16:00 UTC)
   - Trading monitoring
   - Signal quality assessment
   - Alert system verification

3. Evening Checks (16:00-20:00 UTC)
   - End-of-day review
   - Risk assessment
   - System performance check

### Success Criteria
| Criteria | Target |
|----------|--------|
| Critical System Errors | 0 |
| Risk Limits Respected | 100% |
| Win Rate | >= 40% |
| Minimum Trades | >= 10 |
| Alert Channels Working | 100% |

### Issues to Watch For

**Critical (Stop Trading):**
- Emergency stop triggered
- Database connection lost
- Multiple services unhealthy (>2)
- Daily loss > 5%

**High Priority (Investigate Within 1 Hour):**
- Win rate < 35%
- Daily loss > 3%
- Signals stop for > 30 min
- Positions not closing properly

**Medium Priority (Monitor):**
- Single service restart
- ML predictions unavailable
- Alert delays
- Slow API responses (>500ms)

---

## Section 3: Automated Monitoring

### Cron Jobs (Optional)
Add to crontab (`crontab -e`):

```bash
# Daily summary at end of trading day (20:00 UTC)
0 20 * * * /mnt/d/Bimo_max/crypto-trading-bot/scripts/generate_daily_summary.sh >> /var/log/crypto-bot-daily.log 2>&1

# Check daily loss every 4 hours
0 */4 * * * /mnt/d/Bimo_max/crypto-trading-bot/scripts/check_daily_loss.sh >> /var/log/crypto-bot-loss-check.log 2>&1

# Health check every hour
0 * * * * /mnt/d/Bimo_max/crypto-trading-bot/health_check.sh >> /var/log/crypto-bot-health.log 2>&1
```

### Alert Thresholds

| Alert Type | Threshold | Action |
|------------|-----------|--------|
| Daily Loss Warning | 3% | Send INFO alert |
| Daily Loss Critical | 4% | Send WARNING alert |
| Daily Loss Emergency | 5% | Trigger emergency stop + CRITICAL alert |
| Service Unhealthy | 1 service | Send WARNING |
| Multiple Services Down | >2 services | Send CRITICAL |

### Notification Channels
- **Telegram:** Primary alert channel (real-time)
- **Email:** Secondary channel (batch)
- **Slack:** Team notifications (if configured)
- **Discord:** Webhook alerts (if configured)

---

## Section 4: Performance Metrics to Track

### Key Metrics

| Metric | Description | Calculation | Acceptable Range |
|--------|-------------|-------------|------------------|
| Win Rate | % of profitable trades | wins / total_trades * 100 | >= 40% |
| Daily P&L | Total profit/loss for day | SUM(trade_pnl) | > $0 (positive) |
| Avg Trade P&L | Average P&L per trade | daily_pnl / trades | > $0 |
| Max Drawdown | Largest peak-to-trough | MIN(running_pnl) | < 5% of capital |
| Sharpe Ratio | Risk-adjusted return | avg_return / std_dev | > 1.0 |
| Trade Count | Number of trades | COUNT(*) | 10-50 per day |
| Signal Conversion | % signals becoming trades | trades / signals * 100 | >= 30% |
| Risk Utilization | % of risk budget used | used_budget / total_budget | < 70% |

### How to Calculate Each Metric

**Win Rate:**
```sql
SELECT ROUND((SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)::numeric / COUNT(*) * 100), 2) as win_rate
FROM trades WHERE DATE(created_at) = CURRENT_DATE;
```

**Max Drawdown:**
```sql
SELECT ROUND(MIN(running_pnl)::numeric, 2) as max_drawdown
FROM (
    SELECT SUM(pnl) OVER (ORDER BY exit_time) as running_pnl
    FROM trades WHERE DATE(created_at) = CURRENT_DATE
) t;
```

**Risk Utilization:**
```bash
curl http://localhost:8009/api/v1/risk/current | jq '.utilization_pct'
```

---

## Section 5: Quick Reference Commands

### Most Useful Commands for Day 2

```bash
# === MONITORING ===
# Start Day 2 dashboard
./scripts/day2_monitor.sh --continuous

# Generate daily summary
./scripts/generate_daily_summary.sh

# Compare with Day 1
./scripts/compare_days.sh 2025-12-12 2025-12-13

# Check alert status
./scripts/monitor_alerts.sh

# === TRADING STATUS ===
# Check trading engine status
curl http://localhost:8005/api/v1/status | jq

# View open positions
curl http://localhost:8003/api/v1/positions | jq

# Check risk metrics
curl http://localhost:8009/api/v1/risk/current | jq

# View recent trades
curl http://localhost:8003/api/v1/trades?limit=10 | jq

# === TROUBLESHOOTING ===
# Check service health
docker ps --format "table {{.Names}}\t{{.Status}}"

# View trading engine logs
docker logs -f crypto-bot-trading --tail 100

# Check for errors
docker logs crypto-bot-trading --since "1h" 2>&1 | grep -i "error"

# Database query - today's stats
docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -c "
SELECT COUNT(*) as trades,
       ROUND(SUM(pnl)::numeric, 2) as pnl,
       ROUND(AVG(pnl)::numeric, 2) as avg_pnl
FROM trades
WHERE DATE(created_at) = CURRENT_DATE;"
```

### Emergency Procedures

**Stop All Trading:**
```bash
curl -X POST http://localhost:8005/api/v1/emergency-stop
```

**Restart Trading Engine:**
```bash
docker restart crypto-bot-trading
```

**Check All Services:**
```bash
for port in 8001 8002 8003 8004 8005 8006 8007 8008 8009; do
    echo -n "Port $port: "
    curl -s -o /dev/null -w "%{http_code}" http://localhost:$port/health || echo "DOWN"
    echo ""
done
```

**Close All Positions:**
```bash
curl -X POST http://localhost:8005/api/v1/positions/close-all
```

**Resume Trading (after emergency stop):**
```bash
curl -X POST http://localhost:8005/api/v1/trading/resume
```

---

## Files Created Summary

| File | Purpose | Location |
|------|---------|----------|
| day2_monitor.sh | Real-time monitoring dashboard | /scripts/ |
| generate_daily_summary.sh | Daily summary report generator | /scripts/ |
| monitor_alerts.sh | Alert system monitoring | /scripts/ |
| compare_days.sh | Day-over-day comparison | /scripts/ |
| check_daily_loss.sh | Automated loss threshold checker | /scripts/ |
| DAY2_VALIDATION_CHECKLIST.md | Day 2 validation checklist | / (root) |
| DAY2_MONITORING_SETUP_2025-12-12.md | This report | / (root) |

---

## Next Steps for Day 2

1. **Morning (08:00 UTC):**
   - Run `./scripts/day2_monitor.sh` to verify overnight status
   - Check for any overnight position changes
   - Review Day 1 summary for comparison baseline

2. **Throughout Day:**
   - Keep `./scripts/day2_monitor.sh --continuous` running
   - Check alerts regularly
   - Complete validation checklist items

3. **Evening (20:00 UTC):**
   - Run `./scripts/generate_daily_summary.sh`
   - Run `./scripts/compare_days.sh`
   - Update PAPER_TRADING_LOG.md
   - Complete Day 2 validation checklist

4. **Prepare for Day 3:**
   - Review issues identified
   - Plan any configuration changes
   - Update documentation

---

**Report Generated:** 2025-12-12 23:30 UTC
**Author:** Claude Code Backend Developer Agent
