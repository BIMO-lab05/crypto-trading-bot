# Phase 1 Daily Monitoring Checklist

## Quick Reference - Print This!

### Every Morning (5 minutes)

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot
python3 scripts/phase1_monitor.py --hours 24
```

**Check These Numbers**:
- [ ] Total Signals Analyzed: ____
- [ ] HOLD Rate: ____% (40-60% = normal, 70-100% = protecting capital)
- [ ] BUY/SELL Signals: ____
- [ ] GATEKEEPER Blocks: ____
- [ ] VALIDATOR Rejections: ____
- [ ] Any errors in output? Yes / No

**Interpretation**:
- ✅ High HOLD rate (70-100%) = Good! Protecting capital in poor conditions
- ✅ Moderate HOLD rate (40-60%) = Normal filtering
- ⚠️ Low HOLD rate (0-30%) = Watch win rate closely

### Every Evening (2 minutes)

```bash
tail -30 /tmp/trading-engine-phase1.log
```

**Look for**:
- [ ] New signals (🔍 Trend, ⚠️ Volume, 💰 ATR emojis)
- [ ] Any system errors
- [ ] Trading bot still running

### Every 7 Days (15 minutes)

```bash
python3 scripts/phase1_monitor.py --hours 168 --export /tmp/phase1_week$(date +%U).json
```

**Fill out weekly report** (template in PHASE1_MONITORING_GUIDE.md line 257)

### System Health Check

**Quick verify all services running**:
```bash
curl http://localhost:8005/health  # Trading Engine
curl http://localhost:8004/health  # Technical Analysis
curl http://localhost:8003/health  # Market Data
```

All should return: `{"status":"healthy"}`

### Warning Signs 🚨

**Stop and investigate if**:
- No signals for 48+ hours
- System errors in logs
- Win rate decreasing over time
- Trading during extreme volatility when shouldn't

### After 7-14 Days

**Evaluate Phase 1 Goals**:
1. Win rate improved by 10-15%? Yes / No
2. Drawdown reduced by 20-30%? Yes / No
3. Filtering 40-50% of signals? Yes / No

**If all 3 = Yes**: ✅ Proceed to Phase 2
**If 1-2 = Yes**: ⚠️ Tune parameters and re-test
**If 0 = Yes**: ❌ Need major changes

---

## Quick Commands

**Daily monitor**:
```bash
python3 scripts/phase1_monitor.py --hours 24
```

**Weekly export**:
```bash
python3 scripts/phase1_monitor.py --hours 168 --export /tmp/phase1_week1.json
```

**Watch live** (Ctrl+C to stop):
```bash
python3 scripts/phase1_monitor.py --hours 24 --watch
```

**View recent logs**:
```bash
tail -50 /tmp/trading-engine-phase1.log
```

**Check system status**:
```bash
ps aux | grep automated_trading_loop
```

---

**Monitoring Started**: November 4, 2025
**Target End Date**: November 11-18, 2025 (7-14 days)
**Current Status**: ✅ Phase 1 LIVE and filtering
