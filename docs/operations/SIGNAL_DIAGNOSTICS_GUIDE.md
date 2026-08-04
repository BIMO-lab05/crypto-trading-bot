# Signal Diagnostics Guide

## Overview
Enhanced logging system that shows detailed breakdown of why trades are or aren't executing.

## Quick Test

Run the diagnostic test to see current signal analysis:

```bash
python3 scripts/test_signal_diagnostics.py
```

## What You'll See

### 1. **Signal Overview**
```
📊 SIGNAL ANALYSIS FOR BTCUSDT
Action: HOLD
Confidence: 14.0%
Aggregated Score: -0.137
Consensus: 4 indicators
```

### 2. **Individual Indicators**
Each indicator shows:
- Signal direction (BUY/SELL/HOLD)
- Confidence level (0-100%)
- Visual emoji indicator

```
📈 INDIVIDUAL INDICATORS:
  🟢 RSI                 : BUY  (conf: 29.0%)
  🔴 MACD                : SELL (conf: 10.0%)
  🟢 BOLLINGER_BANDS     : BUY  (conf: 55.0%)
  🔴 SMA                 : SELL (conf: 25.0%)
  🔴 EMA                 : SELL (conf: 21.0%)
  🔴 TREND_FILTER        : SELL (conf: 19.8%)
  🟢 VOLUME_CONFIRMATION : BUY  (conf: 100.0%)
  ⚪ STOCHASTIC          : HOLD (conf: 30.0%)
  🔴 ICHIMOKU            : SELL (conf: 100.0%)
```

### 3. **Vote Summary**
Quick count of indicator consensus:
```
📊 VOTE SUMMARY: 🟢 BUY: 3 | 🔴 SELL: 5 | ⚪ HOLD: 1
```

### 4. **Requirement Checks**
Shows which trading requirements are met:
```
✅ REQUIREMENT CHECKS:
  ✗ Confidence: 14.0% < 65.0%
  ✓ Consensus: 4 ≥ 3
  ✗ Overall: Requirements NOT MET
```

### 5. **Reasons Not Trading**
Specific reasons why a trade won't execute:
```
⚠️  REASONS NOT TRADING:
  • Low confidence: 14.0% < 65.0% (need 51.0% more)
  • Volume penalty: 95% (Unknown volume strength)
  • Trend filter blocked: SELL aligned with BEARISH trend
```

### 6. **Final Decision**
```
🛑 DECISION: HOLD - Not trading (requirements not met)
```
OR
```
✅ DECISION: BUY - All requirements met! Trade would execute.
```

## Interpreting Results

### Why No Trades?

**Most Common Reasons:**

1. **Low Confidence** (Most Common)
   - System needs 65% confidence by default
   - Current market shows mixed signals
   - Indicators are conflicting

2. **Insufficient Consensus**
   - Need at least 3 indicators agreeing
   - Currently: indicators are split

3. **Trend Filter Block**
   - Strong trend in opposite direction
   - Prevents counter-trend trades

4. **Low Volume**
   - Insufficient trading volume
   - Reduces signal reliability

### What Indicates a Trade Would Execute?

All must be true:
- ✅ Confidence ≥ 65%
- ✅ Consensus ≥ 3 indicators
- ✅ No trend blocks
- ✅ Sufficient volume

## Running with Automated Trading Loop

The enhanced diagnostics are automatically included when running the trading loop:

```bash
python3 scripts/automated_trading_loop_with_notifications.py
```

Watch the logs in real-time:
```bash
tail -f logs/trading_loop.log
```

## Example: Understanding Current Market (Jan 20, 2026)

Based on the test output:

**BTCUSDT Analysis:**
- Price: $90,713
- Signal: HOLD
- Confidence: Only 14% (needs 65%)

**Why HOLD?**
- Mixed signals: 3 BUY vs 5 SELL
- Overall bearish bias (MACD, EMA, SMA, Trend Filter all bearish)
- Strong individual signals: Ichimoku (100% SELL), Volume Confirmation (100% BUY)
- Result: System correctly stays out due to conflicting signals

**This is GOOD trading behavior!** The system is protecting capital by not trading in unclear conditions.

## Adjusting Sensitivity

If you want to see more trading activity (for testing):

### Option 1: Lower Confidence Threshold
Edit `scripts/automated_trading_loop_with_notifications.py`:
```python
min_confidence: float = 0.50  # Lower from 0.65 to 0.50
```

### Option 2: Reduce Consensus Required
Edit the trading engine configuration (not recommended):
```python
min_consensus_required: int = 2  # Lower from 3 to 2
```

⚠️ **Warning:** Lowering these values increases risk significantly!

## Monitoring Live

### Watch Signal Changes
```bash
# Run diagnostics every 60 seconds
watch -n 60 python3 scripts/test_signal_diagnostics.py
```

### Check Multiple Symbols
Edit `test_signal_diagnostics.py` to test different symbols:
```python
symbol = "ETHUSDT"  # or "BNBUSDT", "SOLUSDT", etc.
```

## Troubleshooting

### No Signal Data
```
⚠️  BTCUSDT: No signal data received
```
**Solution:** Check if trading-engine service is running:
```bash
docker-compose ps trading-engine
docker-compose logs trading-engine
```

### API Connection Errors
```
❌ Error: Connection refused
```
**Solution:** Ensure all services are running:
```bash
docker-compose up -d
```

## Advanced: Understanding Aggregated Score

The aggregated score combines all indicators:
- **Positive score**: Bullish bias
- **Negative score**: Bearish bias
- **Near zero**: Conflicting signals

Example:
```
Aggregated Score: -0.137  ← Slight bearish bias
```

This weighted score considers:
- Individual indicator confidence
- Indicator weights (Ichimoku has 1.3x weight)
- Volume confirmation
- Trend alignment

## Best Practices

1. **Don't Force Trades**
   - If signals are weak, HOLD is the right decision
   - Patience preserves capital

2. **Watch for Pattern Changes**
   - Run diagnostics periodically
   - Look for confidence increasing over time

3. **Understand Your Risk**
   - Current settings (65% confidence) are conservative
   - This is appropriate for live trading

4. **Use Paper Trading First**
   - Test with lower thresholds in paper mode
   - Understand system behavior before going live

## Summary

The enhanced diagnostics provide full transparency into:
- ✅ Why trades execute
- ✅ Why trades don't execute
- ✅ What would need to change for a trade
- ✅ Current market conditions
- ✅ Individual indicator performance

This helps you trust the system and understand its decisions!
