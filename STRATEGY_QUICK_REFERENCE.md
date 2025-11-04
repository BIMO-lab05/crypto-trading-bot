# Trading Strategy - Quick Reference Guide

## Strategy at a Glance
**Type:** Consensus-based multi-indicator momentum strategy  
**Indicators:** 5 (RSI, MACD, Bollinger Bands, SMA, EMA)  
**Trading Mode:** Paper trading (simulation only)  
**Position Side:** Long only (no shorting)

---

## Signal Generation Flow

```
Market Data (Price & Volume)
    ↓
┌─────────────────────────────────┐
│  Calculate 5 Indicators In      │
│  Parallel:                      │
│  - RSI (14)                     │
│  - MACD (12,26,9)               │
│  - Bollinger Bands (20,2.0)     │
│  - SMA (20)                     │
│  - EMA (20)                     │
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│  Generate Individual Signals    │
│  with Confidence Scores         │
│  (Each: BUY/SELL/HOLD + 0-1)    │
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│  Aggregate Signals:             │
│  - Convert to scores (+1/-1/0)  │
│  - Weight by confidence         │
│  - Average all 5 indicators     │
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│  Check Requirements:            │
│  ✓ Min confidence ≥ 0.6?        │
│  ✓ Min 3 indicators agree?      │
│  ✓ Trading not halted?          │
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│  Final Decision:                │
│  - BUY   (score ≥ 0.3)          │
│  - SELL  (score ≤ -0.3)         │
│  - HOLD  (otherwise)            │
└─────────────────────────────────┘
    ↓
Execute or Skip Trade
```

---

## Indicator Thresholds

| Indicator | Signal | Condition |
|-----------|--------|-----------|
| **RSI** | BUY | < 30 (oversold) |
| **RSI** | SELL | > 70 (overbought) |
| **MACD** | BUY | Histogram > 0 (bullish) |
| **MACD** | SELL | Histogram < 0 (bearish) |
| **BB** | BUY | Price near lower band |
| **BB** | SELL | Price near upper band |
| **SMA/EMA** | BUY | Price > moving average |
| **SMA/EMA** | SELL | Price < moving average |

---

## Entry & Exit Rules

### ENTRY (BUY)
```
✓ Aggregated score ≥ 0.3
✓ Confidence ≥ 0.6 (60%)
✓ At least 3 of 5 indicators signal BUY
✓ Position size = 2% of account
✓ Sufficient balance available
→ OPEN LONG POSITION
```

### EXIT (SELL)
```
AUTOMATIC (Hard Exits):
├─ Stop Loss: -3% from entry → Close
├─ Take Profit: +6% from entry → Close
└─ Daily loss > -5% → HALT all trading

SIGNAL-BASED:
└─ Aggregated score ≤ -0.3 → Close all positions
```

---

## Risk Management Summary

| Rule | Value | Impact |
|------|-------|--------|
| Position Size | 2% of capital | Max $200 per trade on $10k account |
| Stop Loss | 3% | Close if price drops 3% |
| Take Profit | 6% | Close if price rises 6% |
| Risk:Reward | 1:2 | Good ratio |
| Max Exposure | 20% | Can have multiple positions |
| Daily Loss Limit | 5% | HALT trading if -$500 on $10k |
| Commission | 0.1% | Simulated trading cost |

---

## Configuration Parameters

```yaml
# Signal Thresholds
min_signal_confidence: 0.6        # Only trade if 60%+ confident
min_consensus_indicators: 3       # Need 3+ of 5 indicators agreeing

# Risk Settings
max_position_size_pct: 2.0        # Max 2% per trade
max_daily_loss_pct: 5.0           # Stop if -5% daily loss
max_total_exposure_pct: 20.0      # Max 20% total exposure
default_stop_loss_pct: 3.0        # -3% hard stop
default_take_profit_pct: 6.0      # +6% profit target

# Paper Trading
paper_initial_balance: 10000.0    # Starting capital
paper_commission_pct: 0.1         # 0.1% fee per trade
```

---

## Example Trade Flow

### Scenario: BTCUSDT at $45,000

**1. Indicator Signals:**
```
RSI (22)        → BUY (oversold)           Conf: 0.73
MACD (positive) → BUY (bullish)            Conf: 0.65
BB (lower)      → BUY (lower band)         Conf: 0.80
SMA (above)     → BUY (price > 20 SMA)    Conf: 0.60
EMA (above)     → BUY (price > 20 EMA)    Conf: 0.55
────────────────────────────────────────────────────
Aggregated Score: (1×0.73 + 1×0.65 + 1×0.80 + 1×0.60 + 1×0.55) / 5
                = 3.33 / 5 = 0.67 (Strong BUY)

Consensus: 5/5 indicators agree (5 BUYs)
Confidence: 0.67 (67%)
```

**2. Risk Checks:**
```
✓ Score (0.67) > 0.3? YES
✓ Confidence (0.67) > 0.6? YES
✓ Consensus (5) ≥ 3? YES
✓ Trading halted? NO
✓ Balance sufficient? YES
→ PROCEED WITH TRADE
```

**3. Position Sizing:**
```
Account: $10,000
Max position: 2% = $200
Entry price: $45,000
Position size: $200 / $45,000 = 0.00444 BTC

Stop Loss: $45,000 × (1 - 0.03) = $43,650
Take Profit: $45,000 × (1 + 0.06) = $47,700
```

**4. Trade Execution:**
```
BUY 0.00444 BTC at $45,000
├─ Cost: 0.00444 × $45,000 = $200
├─ Commission: $200 × 0.1% = $0.20
├─ Total: $200.20
└─ Balance after: $10,000 - $200.20 = $9,799.80
```

**5. Monitoring:**
```
Price: $44,500 → Unrealized: -$222.20 (-1.1%)
Price: $47,700 → Take Profit Hit! → Close position
├─ Proceeds: 0.00444 × $47,700 = $211.77
├─ Commission: $211.77 × 0.1% = $0.21
├─ Net gain: $211.77 - $0.21 - $200.20 = $11.36 profit
└─ Balance: $9,799.80 + $211.56 = $10,011.36
```

---

## Key Strengths

✅ **Reduces false signals** - Requires consensus before trading  
✅ **Systematic risk management** - Hard stops, position sizing, daily limits  
✅ **Configurable** - All thresholds can be adjusted  
✅ **Modular design** - Easy to add/remove indicators  
✅ **Comprehensive logging** - Detailed trade analysis available  
✅ **Paper trading** - Safe testing before going live  

---

## Key Weaknesses

❌ **No trend filter** - May trade sideways markets (false signals)  
❌ **Fixed parameters** - Standard RSI(14), MACD(12,26,9) for all assets  
❌ **No optimization** - Parameters not tested/optimized  
❌ **No automation** - Manual API calls needed (not continuous)  
❌ **No persistence** - Trade history lost on restart  
❌ **No backtesting** - Can't validate on historical data  
❌ **Simple aggregation** - All indicators weighted equally  

---

## Next Steps

**Immediate:**
1. Validate on real market data (paper trading)
2. Track trade performance manually
3. Identify false signal patterns

**Short-term:**
1. Implement automated trading loop
2. Add database persistence
3. Create backtesting framework

**Medium-term:**
1. Add trend filter (no trades in sideways markets)
2. Optimize indicator parameters per asset
3. Implement dynamic position sizing

---

## File Locations

| Component | Location |
|-----------|----------|
| **RSI Indicator** | `/services/technical-analysis/app/indicators/rsi.py` |
| **MACD Indicator** | `/services/technical-analysis/app/indicators/macd.py` |
| **Bollinger Bands** | `/services/technical-analysis/app/indicators/bollinger_bands.py` |
| **Moving Averages** | `/services/technical-analysis/app/indicators/moving_averages.py` |
| **Signal Aggregator** | `/services/trading-engine/app/signal_aggregator.py` |
| **Risk Manager** | `/services/trading-engine/app/risk_manager.py` |
| **Position Manager** | `/services/trading-engine/app/position_manager.py` |
| **Paper Trading** | `/services/trading-engine/app/paper_trading.py` |
| **Config** | `/services/trading-engine/app/config.py` |

---

**Last Updated:** 2025-11-04
