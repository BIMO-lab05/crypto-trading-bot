# 24-Hour Monitoring Checklist
**Optimization Applied**: December 3, 2025
**Next Review**: December 4, 2025 (same time)

---

## ✅ Quick Status Check

Run this command for instant overview:
```bash
curl -s "http://localhost:8005/api/v1/phase1/metrics?hours=24" | python3 -m json.tool | grep -A 10 "signals"
```

---

## 📊 Key Metrics to Track

### 1. Trade Frequency (Target: 3-5 trades/day)
```bash
# Check trades in last 24 hours
docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot -c "
SELECT COUNT(*) as trades_24h
FROM positions
WHERE updated_at >= NOW() - INTERVAL '24 hours';
"
```

**Expected Result**: 3-5 trades (down from 10.4/day before)

---

### 2. Win Rate (Target: >50%)
```bash
# Check win rate of new trades
docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot -c "
SELECT
    COUNT(*) as total_trades,
    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
    ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1.0 ELSE 0.0 END) / COUNT(*) * 100, 1) as win_rate_pct,
    ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl
FROM positions
WHERE updated_at >= NOW() - INTERVAL '24 hours';
"
```

**Expected Result**: Win rate 55-60% (up from 41%)

---

### 3. Symbol Distribution (Should only see: SOL, BNB, BTC + quality alts)
```bash
# Check which symbols are trading
docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot -c "
SELECT symbol, COUNT(*) as trades
FROM positions
WHERE updated_at >= NOW() - INTERVAL '24 hours'
GROUP BY symbol
ORDER BY trades DESC;
"
```

**Expected Result**:
- ✅ SOLUSDT, BNBUSDT, BTCUSDT (should see these)
- ❌ XRPUSDT, ETHUSDT, DOGEUSDT (should NOT see these)

---

### 4. Portfolio P&L
```bash
# Check current portfolio status
docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot -c "
SELECT
    portfolio_id,
    ROUND(cash_balance::numeric, 2) as cash,
    ROUND(realized_pnl::numeric, 2) as realized_pnl,
    ROUND(unrealized_pnl::numeric, 2) as unrealized_pnl,
    ROUND((cash_balance + unrealized_pnl - 10000)::numeric, 2) as total_pnl,
    ROUND(((cash_balance + unrealized_pnl - 10000) / 10000 * 100)::numeric, 2) as roi_pct
FROM portfolios;
"
```

**Expected Result**: Total P&L trending positive (vs -$100 before)

---

### 5. Signal Filtering (Should see high HOLD rate)
```bash
# Check signal distribution
curl -s "http://localhost:8005/api/v1/phase1/metrics?hours=24" | python3 -m json.tool | head -30
```

**Expected Result**:
- HOLD: 95%+ (being selective)
- BUY/SELL: <5% (only high-quality signals)

---

## 🎯 Success Indicators

After 24 hours, you should see:

| Metric | Before Optimization | Target After | Status |
|--------|-------------------|--------------|---------|
| Trade Frequency | 10.4/day | 3-5/day | ⏳ Check tomorrow |
| Win Rate | 41% | 55-60% | ⏳ Check tomorrow |
| Net P&L | -$100/week | Positive | ⏳ Check tomorrow |
| Fees | -$87/week | -$30/week | ⏳ Check tomorrow |
| Bad Symbols | XRP, ETH, DOGE | None | ✅ Removed |

---

## 🔍 Detailed Analysis Commands

### View Recent Trades
```bash
docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot -c "
SELECT
    symbol,
    entry_price,
    exit_price,
    quantity,
    ROUND(realized_pnl::numeric, 2) as pnl,
    status,
    updated_at
FROM positions
WHERE updated_at >= NOW() - INTERVAL '24 hours'
ORDER BY updated_at DESC
LIMIT 10;
"
```

### Check System Health
```bash
curl -s "http://localhost:8005/api/v1/phase1/health" | python3 -m json.tool
```

### View Live Signal Processing
```bash
docker logs -f crypto-bot-trading | grep -E "Final Signal|Requirements MET"
```

---

## ⚠️ Warning Signs

If you see these, the optimization may need adjustment:

### 🔴 Too Conservative (No Trades)
**Symptom**: 0 trades after 48 hours
**Action**: Lower MIN_SIGNAL_CONFIDENCE from 0.50 to 0.45
```bash
# Edit: services/trading-engine/.env
MIN_SIGNAL_CONFIDENCE=0.45

# Restart
docker restart crypto-bot-trading
```

### 🔴 Still Too Many Trades
**Symptom**: >7 trades/day after 24 hours
**Action**: Increase MIN_SIGNAL_CONFIDENCE from 0.50 to 0.60
```bash
# Edit: services/trading-engine/.env
MIN_SIGNAL_CONFIDENCE=0.60

# Restart
docker restart crypto-bot-trading
```

### 🔴 Win Rate Still Low
**Symptom**: Win rate <50% after 20+ trades
**Action**: Increase MIN_CONSENSUS_INDICATORS from 3 to 4
```bash
# Edit: services/trading-engine/.env
MIN_CONSENSUS_INDICATORS=4

# Restart
docker restart crypto-bot-trading
```

---

## 📅 Review Schedule

### ✅ Now (Dec 3, 2025)
- [x] Optimization applied
- [x] Services restarted
- [x] System monitoring

### ⏳ Tomorrow (Dec 4, 2025)
- [ ] Run all metric checks above
- [ ] Verify trade frequency reduced
- [ ] Check win rate improvement
- [ ] Confirm no trades on removed symbols
- [ ] Review P&L trend

### ⏳ In 7 Days (Dec 10, 2025)
- [ ] Full week analysis
- [ ] Compare: 73 trades vs new count
- [ ] Compare: 41% WR vs new WR
- [ ] Compare: -$100 P&L vs new P&L
- [ ] Decide: Keep, adjust, or add symbols

---

## 🚀 Quick Reference

### Single Command Status Check
```bash
echo "=== OPTIMIZATION STATUS ===" && \
echo "Trade Frequency:" && \
docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot -c "SELECT COUNT(*) as trades_24h FROM positions WHERE updated_at >= NOW() - INTERVAL '24 hours';" && \
echo "" && \
echo "Win Rate:" && \
docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot -c "SELECT ROUND(SUM(CASE WHEN realized_pnl > 0 THEN 1.0 ELSE 0.0 END) / COUNT(*) * 100, 1) as win_rate_pct FROM positions WHERE updated_at >= NOW() - INTERVAL '24 hours';" && \
echo "" && \
echo "Signal Distribution:" && \
curl -s "http://localhost:8005/api/v1/phase1/metrics?hours=24" | python3 -m json.tool | grep -A 5 '"signals"'
```

---

**Created**: December 3, 2025
**Author**: Trading Strategy Optimization
**Status**: Active Monitoring Phase
