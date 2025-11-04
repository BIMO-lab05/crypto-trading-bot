# Phase 1 API Reference Guide
# Technical Analysis Service - New Indicators
# Version: 1.0.0 | Last Updated: 2025-11-04

---

## Overview

This document provides complete API reference for the 4 new Phase 1 indicators implemented in the Technical Analysis Service.

**Base URL**: `http://localhost:8004`

**All endpoints return**:
- HTTP 200 OK on success
- Consistent JSON structure with `success`, `symbol`, `data` fields
- Proper error handling with meaningful messages

---

## Table of Contents

1. [Trend Filter API](#trend-filter-api)
2. [Volume Confirmation API](#volume-confirmation-api)
3. [ATR (Dynamic Stops) API](#atr-api)
4. [Stochastic Oscillator API](#stochastic-oscillator-api)
5. [Error Handling](#error-handling)
6. [Rate Limiting](#rate-limiting)
7. [Examples](#examples)

---

## Trend Filter API

### Endpoint

```
GET /api/v1/indicators/trend/{symbol}
```

### Description

Returns trend direction based on 50 and 200 period EMA comparison. Acts as GATEKEEPER to prevent counter-trend trading.

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | Yes | Trading pair symbol (e.g., "BTCUSDT") |

### Query Parameters

| Parameter | Type | Default | Min | Max | Description |
|-----------|------|---------|-----|-----|-------------|
| `interval` | string | "60" | - | - | Kline interval in minutes |
| `fast_period` | integer | 50 | 10 | 100 | Fast EMA period |
| `slow_period` | integer | 200 | 100 | 300 | Slow EMA period |
| `limit` | integer | 300 | 200 | 1000 | Number of klines to fetch |

### Response Format

```json
{
  "success": true,
  "symbol": "BTCUSDT",
  "data": {
    "trend": "BULLISH",           // BULLISH | BEARISH | NEUTRAL
    "fast_ema": 1766542.47,        // 50-period EMA value
    "slow_ema": 1384056.39,        // 200-period EMA value
    "spread_pct": 0.2763,          // Percentage spread between EMAs (27.63%)
    "confidence": 1.0,             // 0.0 to 1.0
    "signal": "BUY",               // BUY | SELL | HOLD
    "description": "BULLISH trend (27.64% spread)",
    "timestamp": 1762270351398
  },
  "parameters": {
    "fast_period": 50,
    "slow_period": 200
  }
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `trend` | string | Trend direction: BULLISH (fast > slow + 0.5%), BEARISH (fast < slow - 0.5%), NEUTRAL (within 0.5%) |
| `fast_ema` | float | Current value of fast EMA (default 50 period) |
| `slow_ema` | float | Current value of slow EMA (default 200 period) |
| `spread_pct` | float | Percentage spread: (fast_ema - slow_ema) / slow_ema |
| `confidence` | float | Confidence level (0.0-1.0) based on spread magnitude. Max at 5% spread. |
| `signal` | string | Trading signal: BUY (bullish), SELL (bearish), HOLD (neutral) |
| `description` | string | Human-readable trend description |
| `timestamp` | integer | Unix timestamp in milliseconds |

### Trend Logic

```python
if spread_pct > 0.005:     # > 0.5%
    trend = "BULLISH"
    signal = "BUY"
elif spread_pct < -0.005:  # < -0.5%
    trend = "BEARISH"
    signal = "SELL"
else:                       # Within ±0.5%
    trend = "NEUTRAL"
    signal = "HOLD"

confidence = min(abs(spread_pct) / 0.05, 1.0)  # 5% spread = 100% confidence
```

### Example Request

```bash
curl "http://localhost:8004/api/v1/indicators/trend/BTCUSDT?interval=60&fast_period=50&slow_period=200&limit=300"
```

### Use Cases

1. **Gatekeeper Filter**: Block trades against the major trend
2. **Trend Strength**: Assess trend strength via spread percentage
3. **Market Regime**: Identify trending vs choppy markets
4. **Confidence Weighting**: Weight signals based on trend strength

---

## Volume Confirmation API

### Endpoint

```
GET /api/v1/indicators/volume/{symbol}
```

### Description

Validates trading signals based on volume relative to 20-period average. Acts as VALIDATOR to filter low-volume false breakouts.

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | Yes | Trading pair symbol (e.g., "BTCUSDT") |

### Query Parameters

| Parameter | Type | Default | Min | Max | Description |
|-----------|------|---------|-----|-----|-------------|
| `interval` | string | "60" | - | - | Kline interval in minutes |
| `period` | integer | 20 | 5 | 50 | Periods for average volume |
| `signal_type` | string | "breakout" | - | - | "breakout" or "continuation" |
| `limit` | integer | 50 | 30 | 200 | Number of klines to fetch |

### Response Format

```json
{
  "success": true,
  "symbol": "BTCUSDT",
  "interval": "60",
  "signal_type": "breakout",
  "timestamp": 1762270351398,
  "data": {
    "confirmed": false,              // true if volume meets threshold
    "current_volume": 0.019,         // Current candle volume
    "avg_volume": 351468.87,         // 20-period average volume
    "volume_ratio": 5.4e-08,         // current / average
    "confidence": 0.1,               // 0.0 to 1.0
    "strength": "INSUFFICIENT",      // STRONG | MODERATE | WEAK | INSUFFICIENT
    "signal": "REJECT",              // CONFIRM | REJECT
    "description": "INSUFFICIENT volume (0.00x average)",
    "timestamp": 1762270351398
  },
  "parameters": {
    "period": 20
  }
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `confirmed` | boolean | True if volume meets the threshold for signal_type |
| `current_volume` | float | Volume of the most recent candle |
| `avg_volume` | float | Average volume over the specified period |
| `volume_ratio` | float | Ratio of current to average volume |
| `confidence` | float | Confidence level (0.0-1.0) based on volume strength |
| `strength` | string | Volume classification: STRONG (≥1.5x), MODERATE (1.2-1.5x), WEAK (1.0-1.2x), INSUFFICIENT (<1.0x) |
| `signal` | string | CONFIRM (pass filter) or REJECT (fail filter) |
| `description` | string | Human-readable volume assessment |

### Volume Logic

```python
volume_ratio = current_volume / avg_volume

if volume_ratio >= 1.5:
    strength = "STRONG"
    confidence = 1.0
    confirmed = True
elif volume_ratio >= 1.2:
    strength = "MODERATE"
    confidence = 0.7
    confirmed = True
elif volume_ratio >= 1.0:
    strength = "WEAK"
    confidence = 0.4
    confirmed = (signal_type == "continuation")  # Only for continuation
else:
    strength = "INSUFFICIENT"
    confidence = 0.1
    confirmed = False
```

### Signal Types

| Type | Threshold | Use Case |
|------|-----------|----------|
| `breakout` | 1.2x average | New support/resistance breaks - requires higher volume |
| `continuation` | 1.0x average | Existing trend continuation - more lenient |

### Example Requests

**Breakout Signal** (requires 1.2x volume):
```bash
curl "http://localhost:8004/api/v1/indicators/volume/BTCUSDT?interval=60&period=20&signal_type=breakout"
```

**Continuation Signal** (requires 1.0x volume):
```bash
curl "http://localhost:8004/api/v1/indicators/volume/BTCUSDT?interval=60&period=20&signal_type=continuation"
```

### Use Cases

1. **Breakout Validation**: Confirm breakouts with 1.2x+ volume
2. **Trend Continuation**: Accept trends with 1.0x+ volume
3. **False Signal Filter**: Reject signals on insufficient volume
4. **Confidence Adjustment**: Apply volume-based confidence penalties

---

## ATR API

### Endpoint

```
GET /api/v1/indicators/atr/{symbol}
```

### Description

Calculates Average True Range for dynamic stop-loss and take-profit levels. Provides volatility-adjusted risk management.

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | Yes | Trading pair symbol (e.g., "BTCUSDT") |

### Query Parameters

| Parameter | Type | Default | Min | Max | Description |
|-----------|------|---------|-----|-----|-------------|
| `interval` | string | "60" | - | - | Kline interval in minutes |
| `period` | integer | 14 | 7 | 30 | ATR calculation period |
| `current_price` | float | null | - | - | Entry price (defaults to last close) |
| `limit` | integer | 50 | 30 | 200 | Number of klines to fetch |

### Response Format

```json
{
  "success": true,
  "symbol": "BTCUSDT",
  "interval": "60",
  "current_price": 1999999.7,
  "timestamp": 1762270351398,
  "data": {
    "atr": 113057.98,              // Raw ATR value
    "atr_pct": 5.65,               // ATR as % of price
    "stop_loss_long": 1773883.74,  // Entry - (2 × ATR)
    "stop_loss_short": 2226115.66, // Entry + (2 × ATR)
    "take_profit_long": 2452231.63, // Entry + (4 × ATR)
    "take_profit_short": 1547767.77, // Entry - (4 × ATR)
    "volatility": "EXTREME",        // LOW | MEDIUM | HIGH | EXTREME
    "confidence": 0.4,              // 0.0 to 1.0
    "description": "EXTREME volatility (5.65% ATR)",
    "risk_reward_ratio": 2.0,       // Always 1:2 (TP = 2× SL)
    "timestamp": 1762270351398
  },
  "parameters": {
    "period": 14
  }
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `atr` | float | Raw ATR value in price units |
| `atr_pct` | float | ATR as percentage of current price |
| `stop_loss_long` | float | Stop-loss for long positions (entry - 2×ATR) |
| `stop_loss_short` | float | Stop-loss for short positions (entry + 2×ATR) |
| `take_profit_long` | float | Take-profit for long positions (entry + 4×ATR) |
| `take_profit_short` | float | Take-profit for short positions (entry - 4×ATR) |
| `volatility` | string | Market volatility classification |
| `confidence` | float | Confidence in volatility reading (lower for extreme volatility) |
| `risk_reward_ratio` | float | Always 2.0 (1:2 risk/reward) |

### Volatility Classification

| ATR % | Classification | Confidence | Trading Implications |
|-------|----------------|------------|----------------------|
| < 1.0% | LOW | 0.8 | Tight stops, smaller position sizes |
| 1.0-2.0% | MEDIUM | 1.0 | Normal trading conditions |
| 2.0-4.0% | HIGH | 0.7 | Wider stops, reduced position sizes |
| > 4.0% | EXTREME | 0.4 | Very wide stops, minimal positions |

### ATR Calculation

```python
# True Range = maximum of:
TR1 = high - low
TR2 = abs(high - prev_close)
TR3 = abs(low - prev_close)
TR = max(TR1, TR2, TR3)

# ATR = EMA of True Range
ATR = EMA(TR, period)

# Dynamic levels
stop_loss_long = entry - (2 × ATR)
take_profit_long = entry + (4 × ATR)
```

### Example Request

```bash
curl "http://localhost:8004/api/v1/indicators/atr/BTCUSDT?interval=60&period=14&current_price=2000000"
```

### Use Cases

1. **Dynamic Stop-Loss**: Replace fixed % stops with volatility-based stops
2. **Position Sizing**: Adjust position size based on ATR percentage
3. **Volatility Filter**: Avoid trading in extreme volatility
4. **Risk Management**: Maintain consistent 1:2 risk/reward ratio

---

## Stochastic Oscillator API

### Endpoint

```
GET /api/v1/indicators/stochastic/{symbol}
```

### Description

Calculates Stochastic Oscillator (%K and %D) for momentum-based entry timing. Detects overbought/oversold conditions and crossovers.

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | Yes | Trading pair symbol (e.g., "BTCUSDT") |

### Query Parameters

| Parameter | Type | Default | Min | Max | Description |
|-----------|------|---------|-----|-----|-------------|
| `interval` | string | "60" | - | - | Kline interval in minutes |
| `period` | integer | 14 | 5 | 30 | Stochastic period |
| `smooth_k` | integer | 3 | 1 | 10 | %K smoothing period |
| `smooth_d` | integer | 3 | 1 | 10 | %D smoothing period (SMA of %K) |
| `limit` | integer | 50 | 30 | 200 | Number of klines to fetch |

### Response Format

```json
{
  "success": true,
  "symbol": "BTCUSDT",
  "interval": "60",
  "timestamp": 1762270351398,
  "data": {
    "k": 100.0,                    // %K value (0-100)
    "d": 100.0,                    // %D value (0-100)
    "signal": "HOLD",              // BUY | SELL | HOLD
    "condition": "OVERBOUGHT",     // OVERBOUGHT | OVERSOLD | NEUTRAL
    "confidence": 0.3,             // 0.0 to 1.0
    "crossover": "NONE",           // BULLISH | BEARISH | NONE
    "description": "OVERBOUGHT (K=100.0, D=100.0)",
    "timestamp": 1762270351398
  },
  "parameters": {
    "period": 14,
    "smooth_k": 3,
    "smooth_d": 3
  }
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `k` | float | %K value (0-100), fast line |
| `d` | float | %D value (0-100), slow line (SMA of %K) |
| `signal` | string | Trading signal: BUY, SELL, or HOLD |
| `condition` | string | Market condition: OVERBOUGHT (>80), OVERSOLD (<20), or NEUTRAL |
| `confidence` | float | Signal confidence (0.0-1.0) |
| `crossover` | string | Crossover detection: BULLISH (%K crosses above %D), BEARISH (%K crosses below %D), or NONE |
| `description` | string | Human-readable description with %K and %D values |

### Stochastic Calculation

```python
# Raw %K
lowest_low = min(lows, period)
highest_high = max(highs, period)
k_raw = 100 × (close - lowest_low) / (highest_high - lowest_low)

# Smoothed %K
k = SMA(k_raw, smooth_k)

# %D (signal line)
d = SMA(k, smooth_d)
```

### Signal Logic

| Condition | Crossover | Signal | Confidence | Reasoning |
|-----------|-----------|--------|------------|-----------|
| OVERSOLD (<20) | BULLISH | BUY | 0.9 | Strong reversal signal |
| OVERBOUGHT (>80) | BEARISH | SELL | 0.9 | Strong reversal signal |
| Any | BULLISH | BUY | 0.6 | Moderate momentum signal |
| Any | BEARISH | SELL | 0.6 | Moderate momentum signal |
| OVERSOLD | None | BUY | 0.6 | %K > %D in oversold |
| OVERBOUGHT | None | SELL | 0.6 | %K < %D in overbought |
| NEUTRAL | None | HOLD | 0.3 | No clear signal |

### Crossover Detection

```python
# Bullish Crossover (buy signal)
k_prev <= d_prev AND k_current > d_current

# Bearish Crossover (sell signal)
k_prev >= d_prev AND k_current < d_current
```

### Example Request

```bash
curl "http://localhost:8004/api/v1/indicators/stochastic/BTCUSDT?interval=60&period=14&smooth_k=3&smooth_d=3"
```

### Use Cases

1. **Entry Timing**: Use crossovers for precise entry timing
2. **Overbought/Oversold**: Identify potential reversals
3. **Divergence Detection**: Spot divergences with price (not in API, but data available)
4. **Momentum Confirmation**: Confirm trend strength with %K position

---

## Error Handling

### Error Response Format

All endpoints return consistent error responses:

```json
{
  "success": false,
  "error": {
    "code": "INSUFFICIENT_DATA",
    "message": "Need at least 200 candles for trend filter",
    "details": {
      "symbol": "BTCUSDT",
      "available": 150,
      "required": 200
    }
  }
}
```

### Common Error Codes

| Code | HTTP Status | Description | Solution |
|------|-------------|-------------|----------|
| `INSUFFICIENT_DATA` | 200 | Not enough historical data | Increase `limit` parameter |
| `INVALID_SYMBOL` | 404 | Symbol not found or not supported | Check symbol format (e.g., "BTCUSDT") |
| `INVALID_INTERVAL` | 400 | Invalid interval parameter | Use valid intervals (1, 5, 15, 60, 240, 1440) |
| `CALCULATION_ERROR` | 200 | Error during calculation | Check logs, may return neutral/default response |
| `SERVICE_UNAVAILABLE` | 503 | Service temporarily unavailable | Retry after short delay |

### Neutral Response Fallback

If calculation fails, indicators return a neutral/default response instead of an error:

**Trend Filter**: Returns NEUTRAL trend with 0.0 confidence
**Volume Confirmation**: Returns REJECT with INSUFFICIENT strength
**ATR**: Returns 3% default stop-loss fallback
**Stochastic**: Returns K=50, D=50, HOLD signal

---

## Rate Limiting

**Current Limits**: None (to be implemented)

**Recommended Usage**:
- Maximum 10 requests/second per endpoint
- Use WebSocket for real-time updates (not yet implemented)
- Cache responses for at least 1 minute for same symbol/interval

**Future Implementation**:
- Rate limiting: 100 requests/minute per IP
- Burst allowance: 20 requests/second for 5 seconds
- Exceeded limits: HTTP 429 with Retry-After header

---

## Examples

### Complete Signal Generation Flow

```python
import requests

BASE_URL = "http://localhost:8004"
symbol = "BTCUSDT"
interval = "60"

# Step 1: Check trend
trend = requests.get(f"{BASE_URL}/api/v1/indicators/trend/{symbol}?interval={interval}").json()
print(f"Trend: {trend['data']['trend']} ({trend['data']['spread_pct']*100:.2f}% spread)")

# Step 2: Check volume
volume = requests.get(f"{BASE_URL}/api/v1/indicators/volume/{symbol}?interval={interval}&signal_type=breakout").json()
print(f"Volume: {volume['data']['strength']} (Confirmed: {volume['data']['confirmed']})")

# Step 3: Get ATR for stops
atr = requests.get(f"{BASE_URL}/api/v1/indicators/atr/{symbol}?interval={interval}").json()
print(f"ATR: {atr['data']['volatility']} ({atr['data']['atr_pct']:.2f}%)")
print(f"  Stop Loss: {atr['data']['stop_loss_long']:.2f}")
print(f"  Take Profit: {atr['data']['take_profit_long']:.2f}")

# Step 4: Check momentum
stoch = requests.get(f"{BASE_URL}/api/v1/indicators/stochastic/{symbol}?interval={interval}").json()
print(f"Stochastic: {stoch['data']['condition']} (K={stoch['data']['k']:.1f}, D={stoch['data']['d']:.1f})")
print(f"  Crossover: {stoch['data']['crossover']}")

# Decision logic
if (trend['data']['trend'] == 'BULLISH' and
    volume['data']['confirmed'] and
    stoch['data']['signal'] == 'BUY'):
    print("\n✅ STRONG BUY SIGNAL")
    print(f"  Entry: Current price")
    print(f"  Stop Loss: {atr['data']['stop_loss_long']:.2f}")
    print(f"  Take Profit: {atr['data']['take_profit_long']:.2f}")
else:
    print("\n⚠️  CONDITIONS NOT MET - HOLD")
```

### TypeScript/JavaScript Example

```typescript
interface TrendResponse {
  success: boolean;
  symbol: string;
  data: {
    trend: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
    fast_ema: number;
    slow_ema: number;
    spread_pct: number;
    confidence: number;
    signal: 'BUY' | 'SELL' | 'HOLD';
    description: string;
    timestamp: number;
  };
}

async function getTrendFilter(symbol: string, interval: string = '60'): Promise<TrendResponse> {
  const response = await fetch(
    `http://localhost:8004/api/v1/indicators/trend/${symbol}?interval=${interval}`
  );
  return response.json();
}

// Usage
const trend = await getTrendFilter('BTCUSDT', '60');
console.log(`Trend: ${trend.data.trend}`);
console.log(`Confidence: ${(trend.data.confidence * 100).toFixed(1)}%`);
```

---

## Integration with Signal Aggregation

The Trading Engine automatically fetches and integrates these indicators:

**fetch_all_indicators()** fetches 8 indicators in parallel:
1. RSI
2. MACD
3. Bollinger Bands
4. SMA (20-period)
5. EMA (20-period)
6. **Trend Filter** (Phase 1)
7. **Volume Confirmation** (Phase 1)
8. **Stochastic** (Phase 1)
9. **ATR** (Phase 1 - separate, not voting)

**aggregate_signals()** applies Phase 1 logic:
- **GATEKEEPER**: Trend Filter blocks counter-trend trades
- **VALIDATOR**: Volume Confirmation applies 70% confidence penalty if unconfirmed
- **VOTING**: 6 indicators vote (RSI, MACD, BB, SMA, EMA, Stochastic)
- **RISK MANAGEMENT**: ATR provides dynamic SL/TP levels
- **CONSENSUS**: Requires 4 out of 6 indicators in agreement

---

## Performance Notes

**Response Times** (observed):
- Trend Filter: ~80ms
- Volume Confirmation: ~50ms
- ATR: ~60ms
- Stochastic: ~70ms
- Full signal generation (8 indicators): ~150-200ms

**Optimization Tips**:
1. Use lower `limit` values when possible (minimum 200 for trend filter)
2. Cache responses for 60 seconds for same symbol/interval
3. Fetch multiple indicators in parallel
4. Use WebSocket connections for real-time updates (future feature)

---

## Changelog

### Version 1.0.0 (2025-11-04)
- Initial Phase 1 release
- Added Trend Filter API
- Added Volume Confirmation API
- Added ATR API
- Added Stochastic Oscillator API
- All 4 indicators fully tested and deployed

---

## Support & Documentation

**Main Documentation**: `/mnt/d/Bimo_max/crypto-trading-bot/PHASE1_IMPLEMENTATION_STATUS.md`
**Strategy Analysis**: `/mnt/d/Bimo_max/crypto-trading-bot/TRADING_STRATEGY_ANALYSIS.md`
**API Health**: `http://localhost:8004/health`
**API Root**: `http://localhost:8004/` (lists all endpoints)

**Service Status**: ✅ RUNNING
**Last Updated**: 2025-11-04 15:45 UTC

---

*This API reference is part of Phase 1 improvements to the Crypto Trading Bot strategy.*
