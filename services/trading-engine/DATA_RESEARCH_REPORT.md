# Historical Market Data Research Report

**Date:** 2025-12-11
**Researcher:** Data Researcher Agent
**Purpose:** Investigate historical market data availability and collection for crypto trading bot validation

---

## Executive Summary

The strategy validation failures are primarily caused by **insufficient historical data collection** and **Bybit API limitations**. The Support/Resistance strategy only received 200 candles (8.3 days) because:

1. **Bybit API default limit is 200 candles per request**
2. **No pagination/batch fetching was implemented for the S/R strategy data**
3. **The market-data-service fetcher has a broken batch collection loop**

This report identifies the root causes and provides actionable recommendations.

---

## 1. Data Sources Analysis

### 1.1 Bybit API Limitations

Based on research of the [Bybit API Documentation](https://bybit-exchange.github.io/docs/v5/market/kline):

| Parameter | Value | Notes |
|-----------|-------|-------|
| Default limit | 200 candles | Per API request |
| Maximum limit | 1000 candles | Per V5 API (newer limit) |
| Endpoint | `/v5/market/kline` | For OHLCV data |
| Coverage | Spot, USDT/USDC/Inverse contracts | All markets |

**Key Finding:** To get 180 days of hourly data (4,320 candles), you need **at least 5 API calls** with proper pagination.

### 1.2 Current Data Collection System

**File:** `/mnt/d/Bimo_max/crypto-trading-bot/services/market-data-service/app/fetcher.py`

The `BybitDataFetcher` class has a critical bug in `get_historical_klines()`:

```python
# Lines 192-247: Current implementation
while current_time < end_time:
    klines = await self.get_kline(
        symbol=symbol,
        interval=interval,
        limit=1000  # Requests 1000, but API may return 200
    )

    # BUG: This updates current_time based on oldest timestamp
    # But without start_time parameter, API always returns LATEST 200 bars
    if klines:
        oldest_ts = min(k["timestamp"] for k in klines)
        current_time = datetime.fromtimestamp(oldest_ts / 1000)
```

**Problem:** The `get_kline()` method does not pass `start_time` or `end_time` parameters to the API, so Bybit always returns the **latest 200 bars regardless of the loop iteration**.

### 1.3 Bybit Connector Service

**File:** `/mnt/d/Bimo_max/crypto-trading-bot/services/market-data-service/app/fetcher.py`

The `get_kline()` method (lines 68-145) shows:
- Only sends `category`, `symbol`, `interval`, `limit` parameters
- **Does NOT send `start` or `end` timestamps**
- This causes the pagination loop to fetch the same 200 bars repeatedly

---

## 2. Data Quality Assessment

### 2.1 What Grid Trading and Trend-Following Had (4,320 bars)

These strategies likely used the **sample data generator** (`generate_sample_data()`) which creates synthetic data:

```python
# From backtest_engine.py lines 543-596
def generate_sample_data(
    symbol: str = "BTCUSDT",
    days: int = 365,
    start_price: float = 50000.0,
    volatility: float = 0.02
) -> List[OHLCV]:
    # Generates random walk data
    hours = days * 24  # 180 days = 4,320 bars
```

**Implication:** Grid Trading and Trend-Following validation used **synthetic data**, not real market data.

### 2.2 What Support/Resistance Strategy Had (200 bars)

The S/R strategy uses `SR_LOOKBACK_PERIODS = 100` candles for level detection:

```python
# From support_resistance_strategy.py
SR_LOOKBACK_PERIODS = 100  # Number of candles to analyze for S/R levels
```

With only 200 candles available (8.3 days of hourly data):
- Only 100 candles available for S/R detection
- Only 100 candles for actual trading signals
- **Insufficient for meaningful validation**

---

## 3. Data Collection Infrastructure

### 3.1 Available Scripts and Tools

| Component | Location | Status |
|-----------|----------|--------|
| Market Data Service | `/services/market-data-service/` | ACTIVE |
| Data Fetcher | `app/fetcher.py` | BUG - no pagination |
| Collection Handler | `app/handlers/collection.py` | Working |
| Backtest Data Provider | `app/backtesting/data_provider.py` | Working |
| Scheduler | `app/scheduler.py` | Collecting daily |

### 3.2 Data Storage

Data is stored in:
1. **TimescaleDB** - Time-series optimized PostgreSQL
2. **Redis** - Caching layer

### 3.3 Historical Data Files

The context mentioned CSV files at `/mnt/d/Bimo_max/crypto-trading-bot/data/historical/` but this directory structure could not be verified. The system primarily uses database storage rather than CSV files.

---

## 4. Root Cause Analysis

### 4.1 Why S/R Strategy Got Only 200 Candles

1. **Bybit API default:** Returns 200 candles without explicit time range
2. **Missing parameters:** `get_kline()` doesn't pass `start_time`/`end_time`
3. **Broken pagination:** The batch loop re-fetches same data
4. **No validation:** No check for data completeness before running backtest

### 4.2 Why Grid/Trend-Following Had 4,320 Bars

They used `use_sample_data=True` in the backtest request:

```python
# From backtest.py handler
if request.use_sample_data:
    data = generate_sample_data(
        symbol=request.symbol,
        days=request.days,  # 180 days = 4,320 bars
        start_price=50000.0,
        volatility=0.02
    )
```

---

## 5. Recommendations

### 5.1 Immediate Fixes (Priority: HIGH)

#### Fix 1: Add Time Range Parameters to Bybit Connector

Update `/services/market-data-service/app/fetcher.py`:

```python
@bybit_connector_retry
async def get_kline(
    self,
    symbol: str,
    interval: str,
    limit: int = 200,
    start_time: Optional[int] = None,  # ADD THIS
    end_time: Optional[int] = None     # ADD THIS
) -> List[Dict[str, Any]]:
    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": interval,
        "limit": min(limit, 1000)
    }

    # ADD THESE CONDITIONS
    if start_time:
        params["start"] = start_time
    if end_time:
        params["end"] = end_time
```

#### Fix 2: Create Data Collection Script

Create `/mnt/d/Bimo_max/crypto-trading-bot/scripts/collect_180_days_data.py`:

```python
#!/usr/bin/env python3
"""
Collect 180 days of historical data for strategy validation
Handles Bybit API pagination properly
"""

import asyncio
import httpx
from datetime import datetime, timedelta
import csv
import os

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT",
    "ADAUSDT", "XRPUSDT", "LTCUSDT", "AVAXUSDT", "DOTUSDT"
]

BYBIT_API_URL = "https://api.bybit.com"
OUTPUT_DIR = "/mnt/d/Bimo_max/crypto-trading-bot/data/historical"

async def fetch_klines_batch(
    client: httpx.AsyncClient,
    symbol: str,
    interval: str,
    start_time: int,
    end_time: int,
    limit: int = 1000
):
    """Fetch a single batch of klines"""
    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": interval,
        "start": start_time,
        "end": end_time,
        "limit": limit
    }

    response = await client.get(
        f"{BYBIT_API_URL}/v5/market/kline",
        params=params
    )

    if response.status_code == 200:
        data = response.json()
        if data.get("retCode") == 0:
            return data.get("result", {}).get("list", [])
    return []


async def collect_symbol_data(symbol: str, days: int = 180):
    """Collect historical data for a single symbol"""
    print(f"Collecting {days} days of {symbol} data...")

    all_klines = []
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=days)

    current_end = int(end_time.timestamp() * 1000)
    target_start = int(start_time.timestamp() * 1000)

    async with httpx.AsyncClient(timeout=30.0) as client:
        while current_end > target_start:
            batch = await fetch_klines_batch(
                client, symbol, "60",
                target_start, current_end, 1000
            )

            if not batch:
                break

            all_klines.extend(batch)

            # Update end time for next batch (oldest candle - 1)
            oldest_ts = min(int(k[0]) for k in batch)
            current_end = oldest_ts - 1

            print(f"  Fetched {len(batch)} candles, total: {len(all_klines)}")

            await asyncio.sleep(0.1)  # Rate limiting

    # Save to CSV
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filename = f"{OUTPUT_DIR}/{symbol}_180days_{datetime.now().strftime('%Y%m%d')}.csv"

    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])

        for k in sorted(all_klines, key=lambda x: int(x[0])):
            writer.writerow(k)

    print(f"Saved {len(all_klines)} candles to {filename}")
    return len(all_klines)


async def main():
    """Collect data for all symbols"""
    for symbol in SYMBOLS:
        try:
            count = await collect_symbol_data(symbol, 180)
            print(f"SUCCESS: {symbol} - {count} candles")
        except Exception as e:
            print(f"ERROR: {symbol} - {e}")

        await asyncio.sleep(1.0)  # Rate limiting between symbols


if __name__ == "__main__":
    asyncio.run(main())
```

### 5.2 Data Validation Before Backtest

Add minimum data check to validation:

```python
# Add to strategy validators
MIN_BARS_FOR_VALIDATION = {
    "support_resistance": 1000,  # ~42 days hourly
    "grid_trading": 2000,        # ~83 days hourly
    "trend_following": 2000,     # ~83 days hourly
}

def validate_data_sufficiency(data: List[OHLCV], strategy: str) -> bool:
    min_required = MIN_BARS_FOR_VALIDATION.get(strategy, 1000)
    if len(data) < min_required:
        raise ValueError(
            f"Insufficient data: {len(data)} bars provided, "
            f"{min_required} required for {strategy}"
        )
    return True
```

### 5.3 Use Bybit Historical Data Download

Bybit provides bulk historical data download at:
[https://www.bybit.com/derivatives/en/history-data](https://www.bybit.com/derivatives/en/history-data)

This can provide years of data without API rate limits.

---

## 6. Data Requirements by Strategy

| Strategy | Minimum Data | Recommended | Rationale |
|----------|--------------|-------------|-----------|
| Support/Resistance | 1,000 bars (42 days) | 2,160 bars (90 days) | S/R levels need history to form |
| Grid Trading | 2,000 bars (83 days) | 4,320 bars (180 days) | Range detection needs volatility cycles |
| Trend Following | 2,000 bars (83 days) | 4,320 bars (180 days) | Trends span weeks/months |
| RSI Momentum | 500 bars (21 days) | 2,160 bars (90 days) | RSI reacts to recent price action |
| Regime Adaptive | 1,000 bars (42 days) | 4,320 bars (180 days) | Hurst exponent needs long history |

---

## 7. Action Items

### Immediate (This Week)
1. [ ] Fix `get_kline()` to accept `start_time`/`end_time` parameters
2. [ ] Create and run `collect_180_days_data.py` script
3. [ ] Collect real data for top 10 trading symbols
4. [ ] Re-run S/R strategy validation with proper data

### Short-term (This Month)
5. [ ] Download bulk historical data from Bybit portal
6. [ ] Create data validation layer before backtests
7. [ ] Document minimum data requirements per strategy
8. [ ] Set up automated daily data collection job

### Long-term
9. [ ] Implement incremental data updates (append new candles)
10. [ ] Create data quality monitoring dashboard
11. [ ] Add data integrity checks (gaps, duplicates, outliers)

---

## 8. Sources

- [Bybit API Kline Documentation](https://bybit-exchange.github.io/docs/v5/market/kline)
- [Bybit Historical Data Download](https://www.bybit.com/derivatives/en/history-data)
- [Crypto Data from Bybit: OHLC & Live Prices](https://www.codearmo.com/python-tutorial/getting-crypto-data-bybit)
- [Getting Historical Bars from ByBit API with Python](https://quantnomad.com/getting-historical-bars-from-bybit-api-with-python/)

---

## Appendix A: Current System Architecture

```
                    +------------------+
                    |   Bybit API      |
                    | (200 bars/call)  |
                    +--------+---------+
                             |
                             v
                    +--------+---------+
                    | Bybit Connector  |
                    |   Service :8001  |
                    +--------+---------+
                             |
                             v
                    +--------+---------+
                    | Market Data Svc  |
                    |      :8002       |
                    +--------+---------+
                             |
              +--------------+--------------+
              |                             |
              v                             v
     +--------+--------+           +--------+--------+
     |   TimescaleDB   |           |     Redis       |
     | (Historical DB) |           |   (Cache)       |
     +-----------------+           +-----------------+
              |
              v
     +--------+--------+
     | Trading Engine  |
     | Backtest Module |
     +-----------------+
```

---

**Report Generated:** 2025-12-11
**Status:** Analysis Complete - Action Required
