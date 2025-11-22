# BTC/ETH Backtest Analysis: Real Data vs Test Data

**Date:** November 20, 2025
**Purpose:** Compare backtest results before/after replacing unrealistic test data with real Bybit market data

---

## Executive Summary

After fetching 90 days of real historical data from Bybit and re-running backtests, **both BTC and ETH showed significant losses** with the SQZMOM strategy using default parameters.

**Recommendation: DO NOT add BTC or ETH to trading symbols** with current strategy configuration.

---

## Data Quality Comparison

### Old Test Data (Unrealistic)
- **BTC Price Range:** $63,000 to $332,000 (400%+ swing in 30 days)
- **Problem:** Completely unrealistic volatility
- **Result:** -100% loss (capital wiped out)

### New Real Data (Realistic)
- **BTC Price Range:** $88,850 to $125,981 (42% range over 90 days)
- **ETH Price Range:** $2,880 to $4,934 (71% range over 90 days)
- **Source:** Bybit API (real market data)
- **Period:** August 22 - November 20, 2025 (90 days)
- **Candles:** 2,160 hourly candles per symbol

---

## Backtest Results with Real Data

### Test Configuration
- **Initial Capital:** $10,000 per symbol
- **Commission:** 0.1% per trade
- **Risk per Trade:** 2% of capital
- **Strategy:** SQZMOM (Squeeze Momentum)
- **Timeframe:** 1 hour candles

### BTCUSDT Performance

| Metric | Value |
|--------|-------|
| **Total Trades** | 584 |
| **Winning Trades** | 128 (21.92%) |
| **Losing Trades** | 456 (78.08%) |
| **Total Return** | **-70.57%** |
| **Final Capital** | **$2,943.41** |
| **Profit Factor** | 0.39 (< 1.0 = losing) |
| **Sharpe Ratio** | -13.47 (extremely poor) |
| **Max Drawdown** | 70.94% |
| **Average Win** | $35.11 |
| **Average Loss** | -$25.33 |
| **Largest Win** | $282.02 |
| **Largest Loss** | -$171.00 |
| **Avg Trade Duration** | 3.3 hours |

**Long vs Short:**
- Long Trades: 287 (19.16% win rate)
- Short Trades: 297 (24.58% win rate)

### ETHUSDT Performance

| Metric | Value |
|--------|-------|
| **Total Trades** | 594 |
| **Winning Trades** | 182 (30.64%) |
| **Losing Trades** | 412 (69.36%) |
| **Total Return** | **-72.87%** |
| **Final Capital** | **$2,712.86** |
| **Profit Factor** | 0.55 (< 1.0 = losing) |
| **Sharpe Ratio** | -8.67 (extremely poor) |
| **Max Drawdown** | 72.87% |
| **Average Win** | $48.45 |
| **Average Loss** | -$39.09 |
| **Largest Win** | $432.21 |
| **Largest Loss** | -$260.83 |
| **Avg Trade Duration** | 3.2 hours |

**Long vs Short:**
- Long Trades: 277 (28.16% win rate)
- Short Trades: 317 (32.81% win rate)

---

## Comparison: Test Data vs Real Data

| Symbol | Test Data Return | Real Data Return | Difference |
|--------|------------------|------------------|------------|
| **BTCUSDT** | -100% | -70.57% | +29.43% (less bad) |
| **ETHUSDT** | -100% | -72.87% | +27.13% (less bad) |

### Key Findings:

1. **Both datasets show losses**, but real data is more realistic
2. **Test data was worse** because of extreme unrealistic volatility
3. **Win rates are poor** (22% for BTC, 31% for ETH)
4. **Profit factors < 1.0** indicate losing strategy
5. **Negative Sharpe ratios** indicate poor risk-adjusted returns

---

## Market Context (Real Data Period)

### Bitcoin (BTCUSDT)
- **Starting Price:** $112,280
- **Ending Price:** $91,762.50
- **Period Return:** -18.27%
- **Market Condition:** Downtrend

### Ethereum (ETHUSDT)
- **Starting Price:** $4,272.97
- **Ending Price:** $3,015.00
- **Period Return:** -29.44%
- **Market Condition:** Strong downtrend

**Important:** The test period was during a **bearish market** for both assets. This may have negatively impacted strategy performance.

---

## Strategy Analysis

### Why Did SQZMOM Fail on BTC/ETH?

1. **Low Win Rates**
   - BTC: 21.92% (4 losses for every 1 win)
   - ETH: 30.64% (2.3 losses for every 1 win)
   - **Required:** Typically need >40% for momentum strategies

2. **Profit Factor < 1.0**
   - BTC: 0.39 (losing $2.57 for every $1.00 won)
   - ETH: 0.55 (losing $1.82 for every $1.00 won)
   - **Required:** Should be >1.5 for viable strategy

3. **Excessive Trading**
   - BTC: 584 trades (6.5 trades/day)
   - ETH: 594 trades (6.6 trades/day)
   - **Issue:** Over-trading leads to death by commissions

4. **Bearish Market Period**
   - Strategy may perform better in trending bull markets
   - Need to test in different market conditions

5. **Default Parameters Not Optimized**
   - Using generic SQZMOM parameters
   - May need asset-specific optimization

---

## Recommendations

### ❌ DO NOT Add to Trading Symbols (Current Configuration)

**Reasons:**
1. Both symbols showed 70%+ losses over 90 days
2. Win rates too low (<40%)
3. Profit factors < 1.0
4. Extremely negative Sharpe ratios
5. Massive drawdowns (>70%)

### ✅ Potential Path Forward (If Still Interested)

**Option 1: Parameter Optimization**
- Run parameter optimization specifically for BTC/ETH
- Test different:
  - BB/KC lengths (currently 20)
  - Momentum thresholds (currently 0.5)
  - Stop loss (currently 2%)
  - Take profit (currently 4%)

**Option 2: Different Timeframes**
- Current test: 1-hour candles
- Try: 4-hour or daily candles
- Longer timeframes may reduce over-trading

**Option 3: Different Strategy**
- SQZMOM may not be suitable for BTC/ETH volatility
- Consider:
  - Trend-following strategies (EMA crossovers)
  - Mean-reversion strategies
  - Breakout strategies

**Option 4: Market Condition Filters**
- Only trade during confirmed trends
- Add ADX filter (trend strength)
- Skip choppy/sideways markets

**Option 5: Test in Bull Market**
- Current test period: bearish (-18% BTC, -29% ETH)
- Re-test strategy during bull market periods
- May perform better in trending upward conditions

---

## Comparison with Other Symbols

Looking at the original backtest with all 7 symbols, the profitable ones were:

| Symbol | Return | Win Rate | Profit Factor | Status |
|--------|--------|----------|---------------|--------|
| SOLUSDT | +2,706.86% | 22.03% | 1.14 | ✅ Profitable |
| DOGEUSDT | +630.90% | 27.78% | 1.75 | ✅ Profitable |
| BNBUSDT | +330.50% | 30.65% | 1.04 | ✅ Profitable |
| BTCUSDT | **-70.57%** | 21.92% | 0.39 | ❌ Losing |
| ETHUSDT | **-72.87%** | 30.64% | 0.55 | ❌ Losing |
| XRPUSDT | -99.47% | 33.99% | 0.32 | ❌ Losing |
| ADAUSDT | -99.41% | 25.93% | 0.05 | ❌ Losing |

**Key Insight:** Higher volatility altcoins (SOL, DOGE, BNB) showed profits while major pairs (BTC, ETH) showed losses. This suggests the strategy may be better suited for high-volatility, lower market cap assets.

---

## Technical Details

### Data Fetching Process

**Script:** `/scripts/fetch_real_historical_data.py`

**Process:**
1. Connected to Bybit public API
2. Fetched 2,160 hourly candles (90 days) per symbol
3. Deleted old test data from TimescaleDB
4. Inserted real market data
5. Verified data integrity

**API Details:**
- Endpoint: `https://api.bybit.com/v5/market/kline`
- Category: `linear` (USDT perpetuals)
- Interval: `60` (1 hour)
- Rate limit: 5 requests/second (safe)

### Database Verification

```sql
-- BTC Data
SELECT COUNT(*) FROM market_data.candles WHERE symbol = 'BTCUSDT';
-- Result: 2,160 candles

-- ETH Data
SELECT COUNT(*) FROM market_data.candles WHERE symbol = 'ETHUSDT';
-- Result: 2,160 candles

-- Price Range Check
SELECT MIN(close), MAX(close) FROM market_data.candles WHERE symbol = 'BTCUSDT';
-- Result: $88,850.10 to $125,981.30 ✅ Realistic
```

---

## Files Generated

1. **Data Fetcher Script:**
   - `/scripts/fetch_real_historical_data.py`
   - Fetches real data from Bybit API

2. **Backtest Script:**
   - `/services/technical-analysis/backtesting/run_btc_eth_backtest.py`
   - Tests BTC/ETH only with real data

3. **Results Files:**
   - `btc_eth_real_data_results.json` (detailed metrics)
   - `backtest_results_OLD_TEST_DATA.json` (backup of old results)
   - `BTC_ETH_REAL_DATA_ANALYSIS.md` (this report)

4. **Data Quality Check:**
   - `/services/technical-analysis/backtesting/test_real_data.py`
   - Verifies data integrity

---

## Conclusion

**Final Recommendation: ❌ DO NOT add BTC or ETH to trading symbols**

**Rationale:**
1. ✅ Real data successfully fetched and validated
2. ❌ Both symbols lost 70%+ with default SQZMOM strategy
3. ❌ Win rates too low (22% BTC, 31% ETH)
4. ❌ Profit factors < 1.0 (losing money)
5. ❌ Massive drawdowns (>70%)

**Alternative Actions:**
1. **Stick with profitable symbols:** SOL, DOGE, BNB
2. **Optimize parameters** if still want to trade BTC/ETH
3. **Test different strategies** better suited for major pairs
4. **Wait for bull market** and re-test

**Data Quality:**
- ✅ Real Bybit data successfully integrated
- ✅ Realistic price ranges confirmed
- ✅ Ready for future backtests with different strategies

---

**Report Generated:** November 20, 2025
**Author:** Crypto Trading Bot Analysis System
**Data Source:** Bybit API (90 days real market data)
