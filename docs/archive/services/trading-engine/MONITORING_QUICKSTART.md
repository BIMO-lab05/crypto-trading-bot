# Monitoring Quick Start Guide

**Quick reference for monitoring trading signals and system health**

---

## 🚀 Quick Commands

### Monitor Signals (Single Check)
```bash
python3 monitor_signals.py --symbol BTCUSDT
```

### Continuous Monitoring (Real-time)
```bash
python3 monitor_signals.py --symbol BTCUSDT --continuous
```

### Analyze Historical Logs
```bash
python3 analyze_logs.py
```

### Check for Errors
```bash
python3 analyze_logs.py --errors-only
```

### Multi-Timeframe Analysis
```bash
python3 monitor_signals.py --symbol BTCUSDT --multi-timeframe
```

---

## 📊 Recent Activity (2025-10-30 to 2025-10-31)

### What We Found:
```
✅ System Status: Healthy (0 errors)
📈 Signals Analyzed: 3
🎯 All Decisions: HOLD (100%)
📊 Average Confidence: 47% (medium)
⚖️ Average Score: -0.47 (weak bearish bias)
```

### Why HOLD?
The system correctly identified **mixed signals**:
- **Bearish indicators**: MACD, SMA, EMA all signaled SELL
- **Bullish indicators**: Bollinger Bands signaled BUY
- **Neutral indicators**: RSI signaled HOLD

**Result:** No clear consensus → Smart HOLD decision ✓

This demonstrates the system is working correctly by **NOT** trading when signals conflict!

---

## 🎯 What Each Indicator Showed

| Indicator | Recent Signals | Confidence | Interpretation |
|-----------|----------------|------------|----------------|
| **MACD** | 🔴 SELL (3/3) | 100% | Strong bearish momentum |
| **SMA** | 🔴 SELL (3/3) | 100% | Price below moving average |
| **EMA** | 🔴 SELL (3/3) | 73% | Downward trend confirmed |
| **Bollinger Bands** | 🟢 BUY (3/3) | 40% | Oversold conditions |
| **RSI** | 🟡 HOLD (3/3) | 30% | Neutral zone (45-55) |

---

## 💡 Key Insights

### Good Signs ✅
1. **No conflicting timeframes** - System maintained consistency
2. **Proper HOLD usage** - Avoided trading in uncertainty
3. **Zero errors** - All systems operational
4. **Indicators working** - All 5 fetched successfully

### What to Watch 👀
1. **Confidence scores** - Currently at 47% (below 60% threshold)
2. **Weak consensus** - Only 3/5 indicators agreeing
3. **Mixed signals** - Bollinger Bands vs. trend indicators

### When to Trade 🎯
Wait for:
- ✅ Confidence ≥ 60%
- ✅ Consensus ≥ 4 indicators
- ✅ Score ≥ |0.3|
- ✅ Volume confirmation

---

## 🔍 Understanding the Output

### Signal Monitor Output
```
🎯 FINAL DECISION:
   Action:     🟡 HOLD         ← Trading action
   Confidence: 0.47 ~          ← Agreement level (~ = medium)
   Score:      -0.470          ← Weighted average (-1 to +1)
   Consensus:  3 indicators    ← How many agree
```

### Confidence Symbols
- 🔥 = High confidence (≥80%)
- ✓ = Good confidence (≥60%)
- ~ = Medium confidence (40-60%)
- ⚠️ = Low confidence (<40%)

### Signal Colors
- 🟢 BUY = Bullish
- 🔴 SELL = Bearish
- 🟡 HOLD = Neutral/Mixed

---

## 📋 Daily Monitoring Checklist

### Morning (Pre-Market)
- [ ] Run `python3 analyze_logs.py` - Review overnight activity
- [ ] Check for errors: `python3 analyze_logs.py --errors-only`
- [ ] Multi-timeframe check: `python3 monitor_signals.py --multi-timeframe`

### During Trading Hours
- [ ] Continuous monitoring: `python3 monitor_signals.py --continuous`
- [ ] Watch for confidence ≥ 60%
- [ ] Monitor consensus changes

### Evening (Post-Market)
- [ ] Run full analysis: `python3 analyze_logs.py`
- [ ] Review decision quality
- [ ] Check indicator performance

---

## 🚨 When to Take Action

### Start Monitoring More Closely
```
Confidence: 0.55 ~ → Approaching threshold
Consensus: 4/5    → Strong agreement building
```

### High-Confidence Signal Detected
```
🎯 FINAL DECISION:
   Action:     🟢 BUY
   Confidence: 0.85 🔥
   Score:      +0.72
   Consensus:  5 indicators agree
```
**→ This is tradeable!**

### System Issues
```
⚠️ Technical Analysis Service: Not Available
❌ Database connection failed
```
**→ Check service health immediately**

---

## 🛠️ Troubleshooting

### Monitor shows "TA Service not available"
```bash
# Check if technical-analysis service is running
curl http://localhost:8004/health

# If not running, start it
cd ../technical-analysis
python3 -m uvicorn app.main:app --reload --port 8004
```

### No signals in logs
```bash
# Verify trading engine is running
curl http://localhost:8001/health

# Check log file
tail -f logs/service.log
```

### Want to test manually?
```bash
# Get current signal via API
curl http://localhost:8001/api/v1/signals/BTCUSDT?interval=60

# Check position manager
curl http://localhost:8001/api/v1/positions?status=all
```

---

## 📚 More Information

- **Full Guide**: See `MONITORING_GUIDE.md` for complete documentation
- **Testing**: See `docs/development/TESTING.md`
- **Architecture**: See `docs/architecture/SYSTEM_OVERVIEW.md`

---

## 🎓 Pro Tips

1. **Use continuous monitoring during volatile periods**
   ```bash
   python3 monitor_signals.py --continuous --delay 30
   ```

2. **Compare multiple symbols**
   ```bash
   for sym in BTCUSDT ETHUSDT SOLUSDT; do
       echo "=== $sym ===" && python3 monitor_signals.py --symbol $sym
   done
   ```

3. **Save analysis to file**
   ```bash
   python3 analyze_logs.py > analysis_$(date +%Y%m%d).txt
   ```

4. **Real-time log filtering**
   ```bash
   tail -f logs/service.log | grep "Aggregated Signal"
   ```

---

**Last Updated:** 2025-11-09
