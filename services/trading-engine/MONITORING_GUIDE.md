# Trading Engine Monitoring Guide

**Purpose:** Monitor trading signals, confidence scores, and decision-making in real-time

**Last Updated:** 2025-11-09

---

## 📊 Current System Status (from logs)

### Recent Activity Analysis
Based on the latest log analysis:

```
✅ System Health: No errors detected
📈 Signals Analyzed: 3 trading decisions
🎯 Signal Distribution: 100% HOLD (no strong trends detected)
📊 Average Confidence: 47% (medium confidence)
⚖️ Average Score: -0.47 (weak bearish bias)
```

### Indicator Performance Summary

| Indicator | Samples | BUY | SELL | HOLD | Avg Confidence |
|-----------|---------|-----|------|------|----------------|
| MACD | 3 | 0 | 3 | 0 | 100% |
| SMA | 3 | 0 | 3 | 0 | 100% |
| EMA | 3 | 0 | 3 | 0 | 73% |
| Bollinger Bands | 3 | 3 | 0 | 0 | 40% |
| RSI | 3 | 0 | 0 | 3 | 30% |

**Key Observations:**
- MACD and SMA consistently bearish (SELL signals)
- Bollinger Bands showing oversold conditions (BUY signals)
- RSI neutral (HOLD signals)
- Mixed signals resulted in HOLD decisions (no consensus)

---

## 🛠️ Monitoring Tools

### 1. Real-Time Signal Monitor (`monitor_signals.py`)

**Purpose:** Watch trading signals as they happen with detailed breakdowns

#### Basic Usage

```bash
# Single symbol analysis
python3 monitor_signals.py --symbol BTCUSDT --interval 60

# Continuous monitoring (every 60 seconds)
python3 monitor_signals.py --symbol BTCUSDT --continuous

# Custom check interval
python3 monitor_signals.py --symbol ETHUSDT --continuous --delay 30

# Multi-timeframe analysis
python3 monitor_signals.py --symbol BTCUSDT --multi-timeframe
python3 monitor_signals.py --symbol BTCUSDT --multi-timeframe --timeframes 5 15 60 240
```

#### Example Output

```
================================================================================
📊 SIGNAL ANALYSIS: BTCUSDT (60m timeframe)
================================================================================
⏰ Timestamp: 2025-11-09 14:30:00 UTC

🎯 FINAL DECISION:
   Action:     🟡 HOLD
   Confidence: 0.47 ~
   Score:      -0.470
   Consensus:  3 indicators agree

📈 INDICATOR BREAKDOWN:
Indicator                 Signal   Confidence   Value           Role
--------------------------------------------------------------------------------
TREND_FILTER              🟢 BUY    0.85 ✓       5.20            🚪 GATEKEEPER
RSI                       🟡 HOLD   0.30 ⚠️      52.30           🗳️  VOTER
MACD                      🔴 SELL   1.00 🔥      -2.50           🗳️  VOTER
BOLLINGER_BANDS           🟢 BUY    0.40 ~       48000.00        🗳️  VOTER
SMA                       🔴 SELL   1.00 🔥      50100.00        🗳️  VOTER
EMA                       🔴 SELL   0.73 ✓       50050.00        🗳️  VOTER
VOLUME_CONFIRMATION       🟢 BUY    0.80 ✓       2.50            🔍 ✓ CONFIRMED

💡 DECISION RATIONALE:
   Vote Breakdown: BUY=1, SELL=3, HOLD=1
   Aggregated Score: -0.470 (threshold: ±0.3)
   ✓ Score 0.470 < 0.3 → HOLD (weak consensus)
   ⚠️  Low confidence 0.47 - signal may not be actionable
```

---

### 2. Historical Log Analyzer (`analyze_logs.py`)

**Purpose:** Review past trading activity and identify patterns

#### Basic Usage

```bash
# Full analysis
python3 analyze_logs.py

# Show only errors
python3 analyze_logs.py --errors-only

# Show last 20 signals
python3 analyze_logs.py --recent 20

# Analyze specific log file
python3 analyze_logs.py --log-file logs/service_2025-11-08.log
```

#### What It Analyzes

1. **Signal Distribution**: BUY/SELL/HOLD percentages
2. **Confidence Levels**: High/Medium/Low confidence breakdown
3. **Indicator Performance**: Which indicators trigger most often
4. **Decision Quality**: Consensus strength analysis
5. **Errors & Warnings**: System health issues
6. **API Patterns**: Technical Analysis service usage

---

### 3. Live Log Viewer (Manual)

Watch logs in real-time:

```bash
# Tail the log file
tail -f logs/service.log

# Follow with grep for signals only
tail -f logs/service.log | grep -E "(Aggregated Signal|✓)"

# Watch for errors
tail -f logs/service.log | grep -i error
```

---

## 🔍 Understanding Signal Decisions

### Signal Components

Every trading signal consists of:

1. **Individual Indicators** (7 total)
   - **Voters** (5): RSI, MACD, Bollinger Bands, SMA, EMA
   - **Gatekeeper** (1): Trend Filter
   - **Validator** (1): Volume Confirmation

2. **Aggregated Score**
   - Weighted average of all voting indicators
   - Range: -1.0 (strong SELL) to +1.0 (strong BUY)
   - Threshold: ±0.3

3. **Confidence Level**
   - Based on indicator agreement
   - Range: 0% to 100%
   - Minimum actionable: 60%

4. **Consensus Count**
   - Number of indicators agreeing on action
   - Minimum required: 3 out of 5

### Decision Logic

```
IF aggregated_score >= +0.3:
    → BUY signal
ELIF aggregated_score <= -0.3:
    → SELL signal
ELSE:
    → HOLD (weak consensus)

AND confidence must be >= 0.6 to be actionable
```

### Signal Interpretation Guide

| Score Range | Action | Confidence | Interpretation |
|-------------|--------|------------|----------------|
| +0.7 to +1.0 | BUY | 80-100% | Strong bullish trend |
| +0.3 to +0.7 | BUY | 60-80% | Moderate buy opportunity |
| -0.3 to +0.3 | HOLD | Any | Mixed signals, no consensus |
| -0.7 to -0.3 | SELL | 60-80% | Moderate sell pressure |
| -1.0 to -0.7 | SELL | 80-100% | Strong bearish trend |

---

## 📌 Key Metrics to Monitor

### 1. Confidence Score
- **High (≥70%)**: Strong agreement, actionable
- **Medium (40-70%)**: Moderate agreement, caution advised
- **Low (<40%)**: Weak agreement, avoid trading

### 2. Aggregated Score
- **Magnitude**: How strong is the signal?
- **Direction**: Is it bullish (+) or bearish (-)?

### 3. Consensus Count
- **4-5 indicators**: Strong consensus
- **3 indicators**: Weak consensus
- **<3 indicators**: No consensus, HOLD

### 4. Indicator Roles

**Gatekeepers** (Trend Filter):
- Acts as first filter
- Must confirm market direction
- If bearish during BUY signal → reduces confidence

**Validators** (Volume Confirmation):
- Confirms signal strength
- Checks volume support
- Can veto weak signals

**Voters** (RSI, MACD, BB, SMA, EMA):
- Cast votes for BUY/SELL/HOLD
- Weighted by confidence
- Majority determines preliminary action

---

## 🚨 Red Flags to Watch For

### In Real-Time Monitoring

1. **Low Confidence Signals**
   ```
   ⚠️  Low confidence 0.35 - signal may not be actionable
   ```
   **Action:** Don't trade, wait for stronger signal

2. **Mixed Timeframes**
   ```
   ⚠️  Mixed signals: Timeframes diverge
      15m: BUY, 60m: HOLD, 240m: SELL
   ```
   **Action:** Wait for timeframe alignment

3. **Weak Consensus**
   ```
   Vote Breakdown: BUY=2, SELL=2, HOLD=1
   ```
   **Action:** Market indecision, avoid trading

### In Log Analysis

1. **High Error Rate**
   ```
   Errors: 15 (↑ from previous period)
   ```
   **Action:** Check service health

2. **TA Service Unavailable**
   ```
   WARNING: Technical Analysis Service not available
   ```
   **Action:** Restart TA service

3. **Database Connection Issues**
   ```
   WARNING: Database connection failed - trades will not be persisted
   ```
   **Action:** Check database status

---

## 🎯 Best Practices

### Before Trading

1. ✅ Run multi-timeframe analysis
2. ✅ Check confidence ≥ 60%
3. ✅ Verify consensus ≥ 4 indicators
4. ✅ Confirm volume validation
5. ✅ Review recent error logs

### During Monitoring

1. ✅ Watch for confidence changes
2. ✅ Track consensus shifts
3. ✅ Monitor aggregated score trends
4. ✅ Note indicator disagreements

### After Trading

1. ✅ Analyze decision quality
2. ✅ Review indicator accuracy
3. ✅ Check error patterns
4. ✅ Document learnings

---

## 📊 Monitoring Schedule

### Recommended Frequency

- **Real-time monitoring**: During active trading hours
- **Log analysis**: Daily (end of day)
- **Multi-timeframe check**: Before entering positions
- **Error review**: Every 4 hours or if issues suspected

### Example Monitoring Session

```bash
# 1. Quick health check
python3 monitor_signals.py --symbol BTCUSDT

# 2. Review recent history
python3 analyze_logs.py --recent 10

# 3. Check for errors
python3 analyze_logs.py --errors-only

# 4. Multi-timeframe alignment
python3 monitor_signals.py --symbol BTCUSDT --multi-timeframe

# 5. If signals look good, start continuous monitoring
python3 monitor_signals.py --symbol BTCUSDT --continuous --delay 60
```

---

## 🐛 Troubleshooting

### "Technical Analysis Service not available"

```bash
# Check if TA service is running
curl http://localhost:8004/health

# Restart TA service
cd ../technical-analysis
python3 -m uvicorn app.main:app --reload --port 8004
```

### "Failed to fetch signal"

1. Verify TA service is running
2. Check network connectivity
3. Review TA service logs
4. Ensure correct symbol format (e.g., BTCUSDT not BTC-USDT)

### No signals in logs

1. Check if service is running
2. Verify log file permissions
3. Check log level (should be INFO or DEBUG)
4. Ensure API endpoints are being called

---

## 📈 Advanced Usage

### Custom Alert Script

Create a script to alert on high-confidence signals:

```bash
#!/bin/bash
# alert_on_signals.sh

while true; do
    python3 monitor_signals.py --symbol BTCUSDT | grep -E "BUY.*0\.[89]|SELL.*0\.[89]"
    if [ $? -eq 0 ]; then
        echo "🔔 High confidence signal detected!"
        # Add notification (email, Telegram, etc.)
    fi
    sleep 60
done
```

### Multiple Symbol Monitoring

```bash
# Monitor multiple symbols
for symbol in BTCUSDT ETHUSDT SOLUSDT; do
    echo "Analyzing $symbol..."
    python3 monitor_signals.py --symbol $symbol
    sleep 2
done
```

---

## 📝 Log File Locations

```
services/trading-engine/
├── logs/
│   └── service.log          # Main service log
├── monitor_signals.py        # Real-time monitor
├── analyze_logs.py          # Log analyzer
└── MONITORING_GUIDE.md      # This file
```

---

## 🔗 Related Documentation

- [Testing Guide](../../docs/development/TESTING.md)
- [Architecture Overview](../../docs/architecture/SYSTEM_OVERVIEW.md)
- [API Documentation](../../docs/api/openapi.yaml)

---

**Questions or Issues?** Check the troubleshooting section or review service logs for details.
