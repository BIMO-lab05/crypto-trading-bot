# Day 2 Paper Trading Validation Checklist
**Date:** 2025-12-13
**Paper Trading Day:** 2 of 7

---

## Morning Checks (08:00-12:00 UTC)

### System Health
- [ ] Run `./scripts/day2_monitor.sh` - Verify all services healthy
- [ ] Check database connection - No connection errors
- [ ] Verify ML models loaded - 16/16 models available
- [ ] Check Prometheus targets - All targets UP

**Commands:**
```bash
# Quick health check
./scripts/day2_monitor.sh

# Docker status
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Check specific service health
curl http://localhost:8005/health | jq
curl http://localhost:8003/health | jq
curl http://localhost:8004/health | jq
```

### Trading Activity
- [ ] Verify SQZMOM strategy active
- [ ] Check signal generation (should be continuous)
- [ ] Review overnight positions (if any)
- [ ] Verify risk limits still enforced

**Commands:**
```bash
# Check trading engine status
curl http://localhost:8005/api/v1/status | jq

# Check active positions
curl http://localhost:8003/api/v1/positions | jq

# Check signals
docker logs crypto-bot-trading --since "1h" 2>&1 | grep -i "signal"
```

### Performance Review
- [ ] Generate daily summary: `./scripts/generate_daily_summary.sh`
- [ ] Compare Day 2 vs Day 1 metrics
- [ ] Review win rate trend
- [ ] Check P&L progression

**Commands:**
```bash
# Generate summary
./scripts/generate_daily_summary.sh

# Compare days
./scripts/compare_days.sh 2025-12-12 2025-12-13
```

---

## Midday Checks (12:00-16:00 UTC)

### Trading Monitoring
- [ ] Review new positions opened today
- [ ] Check for any positions near stop loss
- [ ] Verify take profit levels set correctly
- [ ] Monitor risk utilization (should be <70%)

**Commands:**
```bash
# Current positions with details
curl http://localhost:8003/api/v1/positions | python3 -c "
import sys, json
data = json.load(sys.stdin)
positions = data.get('positions', data) if isinstance(data, dict) else data
for p in positions:
    print(f\"{p.get('symbol')}: {p.get('side')} | Entry: \${p.get('entry_price', 0):.4f} | SL: \${p.get('stop_loss', 'N/A')} | TP: \${p.get('take_profit', 'N/A')} | PnL: \${p.get('unrealized_pnl', 0):.2f}\")
"

# Risk status
curl http://localhost:8009/api/v1/risk/current | jq
```

### Signal Quality
- [ ] Review signal-to-trade conversion rate
- [ ] Check signal rejection reasons
- [ ] Verify all 4 indicators working (RSI, MACD, BB, SQZMOM)
- [ ] ML predictions available for all symbols

**Commands:**
```bash
# Check TA service
curl http://localhost:8004/api/v1/indicators/status | jq

# Check ML predictions
curl http://localhost:8007/api/v1/prediction/BTCUSDT | jq

# Signal rejection reasons
docker logs crypto-bot-trading --since "4h" 2>&1 | grep -i "rejected\|skipped"
```

### Alert System
- [ ] Run `./scripts/monitor_alerts.sh`
- [ ] Verify Telegram alerts received
- [ ] Check for any critical alerts
- [ ] Test manual alert trigger

**Commands:**
```bash
# Monitor alerts
./scripts/monitor_alerts.sh

# Test alert
./scripts/monitor_alerts.sh --test

# Check notification logs
docker logs crypto-bot-notification --since "4h" 2>&1 | grep -i "sent\|alert"
```

---

## Evening Checks (16:00-20:00 UTC)

### End-of-Day Review
- [ ] Run final daily summary
- [ ] Review all closed trades
- [ ] Calculate actual vs expected performance
- [ ] Update PAPER_TRADING_LOG.md

**Commands:**
```bash
# Final summary
./scripts/generate_daily_summary.sh $(date +%Y-%m-%d)

# Query closed trades today
docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -c "
SELECT symbol, side, entry_price, exit_price, pnl, close_reason, entry_time, exit_time
FROM trades
WHERE DATE(created_at) = CURRENT_DATE
ORDER BY exit_time DESC;"
```

### Risk Assessment
- [ ] Check if any limits were exceeded
- [ ] Review maximum risk utilization for the day
- [ ] Verify no emergency stops triggered
- [ ] Calculate maximum drawdown today

**Commands:**
```bash
# Risk metrics summary
curl http://localhost:8009/api/v1/risk/summary | jq

# Check for emergency stops
docker logs crypto-bot-trading --since "24h" 2>&1 | grep -i "emergency\|stop"

# Max drawdown calculation
docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -c "
SELECT
    MAX(pnl) as best_trade,
    MIN(pnl) as worst_trade,
    ROUND(SUM(CASE WHEN pnl < 0 THEN pnl ELSE 0 END)::numeric, 2) as total_loss,
    ROUND(MIN(running_pnl)::numeric, 2) as max_drawdown
FROM (
    SELECT pnl, SUM(pnl) OVER (ORDER BY exit_time) as running_pnl
    FROM trades
    WHERE DATE(created_at) = CURRENT_DATE
) t;"
```

### System Performance
- [ ] Check container resource usage
- [ ] Review API response times
- [ ] Check for any errors in logs
- [ ] Verify database size growth

**Commands:**
```bash
# Container resources
docker stats --no-stream

# Check for errors
docker logs crypto-bot-trading --since "24h" 2>&1 | grep -i "error\|exception" | head -20

# Database size
docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -c "
SELECT pg_size_pretty(pg_database_size('cryptobot')) as db_size;"
```

---

## Issues to Watch For

### Critical (Stop Trading Immediately)
- [ ] Emergency stop triggered
- [ ] Database connection lost
- [ ] Multiple services unhealthy (>2)
- [ ] Risk limit exceeded (>5% daily loss)
- [ ] Trading engine unresponsive

**Emergency Commands:**
```bash
# Emergency stop
curl -X POST http://localhost:8005/api/v1/emergency-stop

# Check all services
docker ps --filter "health=unhealthy"

# Restart trading engine
docker restart crypto-bot-trading
```

### High Priority (Investigate Within 1 Hour)
- [ ] Win rate drops below 35%
- [ ] Daily loss exceeds 3%
- [ ] Signals stop generating for >30 min
- [ ] Positions not closing at stop loss/take profit
- [ ] Single service becomes unhealthy

### Medium Priority (Monitor Closely)
- [ ] Single service restart
- [ ] ML predictions unavailable
- [ ] Alert delivery delays
- [ ] Slow API responses (>500ms)
- [ ] Unusual trading patterns

---

## Day 2 Success Criteria

### Must Pass (All Required)
- [ ] **No critical system errors** - Zero unhandled exceptions
- [ ] **All risk limits respected** - No violations of 2% position / 5% daily limits
- [ ] **Win rate >= 40%** - Target minimum win rate
- [ ] **At least 10 trades executed** - Sufficient sample size
- [ ] **All alert channels functioning** - Notifications being delivered

### Target Metrics
| Metric | Target | Day 2 Actual | Status |
|--------|--------|--------------|--------|
| Total Trades | >= 10 | | |
| Win Rate | >= 40% | | |
| Daily P&L | > $0 | | |
| Max Drawdown | < 5% | | |
| Signal Conversion | >= 30% | | |
| Avg Trade P&L | > $0 | | |

---

## Notes Section

### Morning Notes
```
Time:
Observer:
Notes:


```

### Midday Notes
```
Time:
Observer:
Notes:


```

### Evening Notes
```
Time:
Observer:
Notes:


```

---

## End of Day Sign-Off

**Date:** 2025-12-13

**Day 2 Summary:**
- Total Trades: ____
- Win Rate: ____%
- Daily P&L: $____
- Critical Issues: ____
- Warnings: ____

**Assessment:**
- [ ] PASS - Day 2 objectives met
- [ ] PARTIAL - Some issues to address
- [ ] FAIL - Major issues found

**Issues Identified:**
1.
2.
3.

**Actions for Day 3:**
1.
2.
3.

**Signed:** _________________

**Time:** _________________
