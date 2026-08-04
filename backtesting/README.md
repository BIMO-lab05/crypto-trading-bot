# Backtesting Framework - Phase 1 Validation

This backtesting framework validates the effectiveness of Phase 1 trading strategy improvements by comparing performance against a baseline strategy using historical data.

## Overview

**Purpose**: Prove that Phase 1 filters (GATEKEEPER, VALIDATOR, ATR) improve trading performance before deploying to live trading.

**Phase 1 Goals**:
1. Increase win rate by 10-15%
2. Reduce maximum drawdown by 20-30%
3. Reduce false signals by 40-50%

## Files

### 1. `backtest_engine.py` (600+ lines)
Complete backtesting engine with realistic trading simulation.

**Features**:
- Position management (long/short)
- Stop loss and take profit execution
- Commission and slippage modeling
- Comprehensive performance metrics:
  - Win rate, profit/loss, Sharpe ratio
  - Maximum drawdown, profit factor
  - Trade statistics and equity curve

### 2. `data_downloader.py` (200+ lines)
Downloads historical OHLCV data from the market data service.

**Features**:
- Automatic batching with rate limiting
- Multiple symbol support
- CSV export functionality
- Configurable timeframes and periods

### 3. `run_phase1_backtest.py` (600+ lines)
Complete Phase 1 comparison runner.

**Features**:
- Baseline strategy (RSI + EMA, no filters)
- Phase 1 strategy (baseline + GATEKEEPER + VALIDATOR + ATR)
- Inline technical indicator calculations
- Side-by-side performance comparison
- Goal achievement analysis

## Quick Start

### Basic Usage

Run a 90-day backtest on BTCUSDT:

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot
python3 backtesting/run_phase1_backtest.py --days 90
```

### Custom Parameters

```bash
# 30-day test with $50,000 capital
python3 backtesting/run_phase1_backtest.py --days 30 --capital 50000

# Different symbol
python3 backtesting/run_phase1_backtest.py --symbol ETHUSDT --days 90

# 15-minute candles
python3 backtesting/run_phase1_backtest.py --interval 15 --days 30

# Use pre-downloaded data (faster)
python3 backtesting/run_phase1_backtest.py \
  --data-file backtesting/data/BTCUSDT_60m_90d.csv
```

## Strategy Comparison

### Baseline Strategy (WITHOUT Phase 1)

**Entry Signals**:
- BUY: RSI < 30 (oversold) AND price > EMA(20)
- SELL: RSI > 70 (overbought) AND price < EMA(20)

**Risk Management**:
- Fixed 3% stop loss
- Fixed 6% take profit

**No Filtering**: Takes all signals regardless of trend or volume

### Phase 1 Strategy (WITH Phase 1)

**Same Entry Signals** as baseline, but with additional filters:

**GATEKEEPER (Trend Filter)**:
- Blocks BUY signals in BEARISH trend (50 EMA < 200 EMA)
- Blocks SELL signals in BULLISH trend (50 EMA > 200 EMA)
- Prevents counter-trend trading

**VALIDATOR (Volume Confirmation)**:
- Requires volume > 1.2x average for breakout signals
- Requires volume > 1.0x average for continuation signals
- Filters out low-volume false breakouts

**ATR-Based Risk Management**:
- Dynamic stop loss: 2x ATR from entry
- Dynamic take profit: 4x ATR from entry
- Adapts to market volatility

## Output Report

The backtest generates a comprehensive comparison report:

```
================================================================================
                    PHASE 1 BACKTEST COMPARISON
================================================================================

📅 TEST PERIOD
  Start: 2024-08-04
  End:   2024-11-04
  Initial Capital: $10,000.00

METRIC                               BASELINE        PHASE 1         IMPROVEMENT
--------------------------------------------------------------------------------
Total Trades                         150             75              -50.0%
Win Rate                             45.00%          58.00%          ✅ +13.00%
Total P&L                            $-500.00        $1,200.00       ✅ +340.0%
Total Return                         -5.00%          +12.00%         ✅ +17.00%
Max Drawdown                         18.50%          11.20%          ✅ -39.5%
Sharpe Ratio                         -0.35           1.25            ✅ +457.1%
Profit Factor                        0.85            1.65            ✅ +94.1%

🎯 PHASE 1 GOALS vs RESULTS
--------------------------------------------------------------------------------
  Goal 1: Increase Win Rate by 10-15%
    ✅ ACHIEVED: +13.00% improvement

  Goal 2: Reduce Drawdown by 20-30%
    ✅ ACHIEVED: 39.5% reduction

  Goal 3: Reduce False Signals by 40-50%
    ✅ ACHIEVED: 50.0% fewer trades (filtered out)
```

## Performance Metrics Explained

- **Win Rate**: Percentage of profitable trades
- **Total P&L**: Total profit or loss in USD
- **Total Return**: ROI as percentage of initial capital
- **Avg Profit/Trade**: Average profit per trade
- **Max Drawdown**: Largest peak-to-trough equity decline
- **Sharpe Ratio**: Risk-adjusted return (higher is better)
- **Profit Factor**: Gross profit / Gross loss (>1 is profitable)

## Advanced Usage

### Download Data Only

```bash
cd backtesting
python3 data_downloader.py --symbol BTCUSDT --days 90 --interval 60
```

### Test Different Parameters

Edit `run_phase1_backtest.py` to modify:
- RSI thresholds (default: 30/70)
- EMA period (default: 20)
- Trend filter periods (default: 50/200)
- Volume thresholds (default: 1.2x/1.5x)
- ATR multipliers (default: 2x stop, 4x target)

### Batch Testing Multiple Symbols

```python
from data_downloader import HistoricalDataDownloader
import asyncio

async def main():
    downloader = HistoricalDataDownloader()
    await downloader.download_multiple_symbols(
        symbols=['BTCUSDT', 'ETHUSDT', 'BNBUSDT'],
        interval='60',
        days=90
    )
    await downloader.close()

asyncio.run(main())
```

## Interpreting Results

### Phase 1 is Working If:
✅ Win rate improves by at least 10%
✅ Drawdown reduces by at least 20%
✅ Total return is positive or improved
✅ Sharpe ratio increases (better risk-adjusted returns)
✅ Profit factor > 1.0 and improved vs baseline

### Phase 1 Needs Tuning If:
⚠️ Win rate improves but total return decreases (filtering too aggressively)
⚠️ Drawdown increases (ATR stops too wide)
⚠️ Very few trades executed (filters too strict)

### Phase 1 is Not Working If:
❌ Win rate decreases or stays the same
❌ Drawdown increases significantly
❌ Total return is negative and worse than baseline

## Next Steps

### If Phase 1 Goals Are Achieved:
1. Continue to Phase 2 (Multiple Timeframe Analysis)
2. Add frontend visualization
3. Write unit tests

### If Phase 1 Goals Are Not Met:
1. Adjust trend filter thresholds
2. Modify volume confirmation ratios
3. Tune ATR multipliers
4. Re-run backtest with optimized parameters

### Monitor Live Performance:
1. Compare backtest results vs live trading
2. Use `scripts/phase1_monitor.py` to track effectiveness
3. Collect 24-48 hours of data for validation

## Technical Details

### Backtesting Engine Features

- **Realistic Simulation**: Models slippage (0.05%) and commissions (0.1%)
- **Position Management**: One position at a time, proper entry/exit logic
- **Stop Loss Execution**: Checks high/low of each candle for SL/TP hits
- **Equity Curve**: Tracks portfolio value over time
- **Trade Journal**: Records every trade with metadata

### Data Requirements

- Minimum 200 candles for indicator calculation
- Recommended 2000+ candles for statistical significance
- 1-hour candles recommended (good balance of data points)

### Performance Considerations

- Downloading 90 days of data: ~30 seconds
- Running baseline backtest: ~5 seconds
- Running Phase 1 backtest: ~10 seconds (more indicators)
- Total runtime: ~1 minute for complete comparison

## Troubleshooting

**"No data downloaded"**
- Ensure market-data-service is running on localhost:8002
  > **Corrected 2026-07-30:** this doc previously said port 8003 — that is portfolio-manager. market-data-service serves on **:8002**.
- Check service logs: `tail /tmp/market-data.log`

**"Not enough candles"**
- Increase `--days` parameter (minimum 30 days for 1h candles)
- Or use shorter interval (e.g., `--interval 15`)

**"All signals filtered"**
- Market conditions may not match strategy
- Try different time period
- Adjust Phase 1 filter thresholds

**Performance issues**
- Use `--data-file` to skip download on repeated runs
- Reduce `--days` for faster testing
- Use larger `--interval` (fewer candles to process)

## Files Created During Execution

```
backtesting/
├── backtest_engine.py          # Engine
├── data_downloader.py           # Downloader
├── run_phase1_backtest.py       # Runner
├── README.md                    # This file
├── data/                        # Downloaded data
│   └── BTCUSDT_60m_90d.csv     # Historical OHLCV
└── results/                     # Future: detailed reports
```

## Contributing

To add new strategies:
1. Create strategy function in `run_phase1_backtest.py`
2. Follow signature: `def strategy(row, position, idx, data) -> dict`
3. Return `{'action': 'BUY'/'SELL', 'stop_loss': price, 'take_profit': price}`
4. Add to comparison runner

---

# Phase1-vs-Phase3 comparison framework

> Merged from `backtesting/README_COMPARISON.md` on 2026-07-30.

> **Status note (2026-07-30):** several claims below describe the Phase 3 "AI-enhanced" leg as if ML and sentiment were live. As of the current stack: `ENABLE_ML_PREDICTIONS=false` (GRU models scored chance-level after the look-ahead-leakage fix), sentiment analysis is removed from the signal pipeline (`ENABLE_SENTIMENT_ANALYSIS=false`), and the **walk-forward harness currently tests `phase1_strategy_prod`, not the deployed ensemble**. Treat the Phase 3 comparison results as framework documentation, not as evidence about the deployed strategy.

## Overview

This comprehensive backtesting framework compares two trading strategies:

- **Phase 1:** Technical Analysis Only (RSI, MACD, Bollinger Bands, EMA, Volume)
- **Phase 3:** AI-Enhanced (Phase 1 + ML Predictions + Sentiment Analysis)

## Quick Start

### Basic Usage

```bash
# Run comparison with default settings (BTC, ETH, BNB - 90 days)
python backtesting/run_phase_comparison.py

# Custom symbol
python backtesting/run_phase_comparison.py --symbols BTCUSDT

# Multiple symbols
python backtesting/run_phase_comparison.py --symbols BTCUSDT ETHUSDT SOLUSDT

# Custom timeframe
python backtesting/run_phase_comparison.py --interval 240 --days 180

# Custom capital
python backtesting/run_phase_comparison.py --capital 50000
```

### Full Options

```bash
python backtesting/run_phase_comparison.py \
    --symbols BTCUSDT ETHUSDT BNBUSDT \
    --interval 60 \
    --days 90 \
    --capital 10000
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--symbols` | BTCUSDT ETHUSDT BNBUSDT | Trading pairs to test (space-separated) |
| `--interval` | 60 | Candle interval in minutes (15, 60, 240, 1440) |
| `--days` | 90 | Historical data lookback period |
| `--capital` | 10000.0 | Initial trading capital in USD |

## Strategy Comparison

### Phase 1 Strategy (Technical Analysis)

**Indicators:**
- RSI (14 period) - Oversold/Overbought detection
- MACD (12/26/9) - Trend momentum
- Bollinger Bands (20/2) - Volatility and price extremes
- EMA (20/50/200) - Trend direction

**Filters:**
- **GATEKEEPER:** 50/200 EMA trend filter (blocks counter-trend trades)
- **VALIDATOR:** Volume confirmation (requires 1.2x average volume)

**Risk Management:**
- ATR-based dynamic stop-loss (2x ATR)
- ATR-based take-profit (4x ATR)
- 2% position sizing per trade

### Phase 3 Strategy (AI-Enhanced)

**Everything from Phase 1 PLUS:**

**ML Enhancements:**
- Price direction prediction (BULLISH/BEARISH/NEUTRAL)
- Confidence scoring (0-1 scale)
- Volatility-adjusted position sizing
- Trend strength analysis

**Sentiment Analysis:**
- Market sentiment scoring (-1 to 1)
- Bullish/Bearish signal counting
- Volume-weighted sentiment
- Confidence thresholds

**Multi-timeframe:**
- Higher timeframe confirmation
- Cross-timeframe trend alignment
- Volatility regime detection

**Signal Weighting:**
```python
Technical Indicators: 50%
ML Predictions:       30%
Sentiment Analysis:   20%
```

## Output Reports

### Individual Symbol Reports

Location: `backtesting/results/BACKTEST_COMPARISON_{SYMBOL}_{INTERVAL}m_{DAYS}d_{TIMESTAMP}.md`

**Includes:**
- Executive summary
- Performance metrics table
- Risk-adjusted returns (Sharpe, Sortino, Calmar)
- Statistical significance testing (t-test)
- Trade quality analysis
- Signal quality metrics
- Detailed trade logs
- Recommendations

### Master Summary Report

Location: `backtesting/results/BACKTEST_COMPARISON_SUMMARY_{TIMESTAMP}.md`

**Includes:**
- All symbols tested
- Comparative performance table
- Links to detailed reports

## Metrics Explained

### Profitability Metrics

- **Total P/L:** Absolute profit/loss in USD
- **Total Return:** Percentage return on initial capital
- **Avg Profit/Trade:** Mean profit per executed trade
- **Profit Factor:** Gross profit / Gross loss (>1.0 is profitable)

### Win Rate Metrics

- **Win Rate:** Percentage of profitable trades
- **Winning Trades:** Count of trades with profit > 0
- **Losing Trades:** Count of trades with profit <= 0

### Risk Metrics

- **Max Drawdown:** Maximum peak-to-trough decline in capital
- **Sharpe Ratio:** Risk-adjusted returns (>1.0 is good, >2.0 is excellent)
- **Sortino Ratio:** Like Sharpe but only penalizes downside volatility
- **Calmar Ratio:** Annual return / Max drawdown

### Trade Quality Metrics

- **Avg Duration:** Mean time position is held (hours)
- **Profit/Hour:** Efficiency of capital deployment
- **Win Streak:** Maximum consecutive winning trades
- **Loss Streak:** Maximum consecutive losing trades
- **Trade Expectancy:** Expected value per trade

### Statistical Significance

- **T-Test:** Determines if Phase 3 improvement is statistically significant
- **P-Value:** Probability improvement is due to chance (<0.05 is significant)
- **Interpretation:** Plain English explanation of results

## Example Output

```
QUICK SUMMARY - BTCUSDT
======================================
Phase 1 (TA Only):
  Trades: 45 | Win Rate: 55.56% | Return: 12.34%
  Final Capital: $11,234.00 | Max DD: 8.45%

Phase 3 (AI Enhanced):
  Trades: 38 | Win Rate: 63.16% | Return: 18.72%
  Final Capital: $11,872.00 | Max DD: 6.23%

Improvement: +51.75%
```

## Interpreting Results

### Good Phase 3 Performance Indicators

1. **Higher Win Rate:** Phase 3 > Phase 1 (typically 5-10% improvement)
2. **Lower Drawdown:** Phase 3 max drawdown < Phase 1
3. **Better Sharpe Ratio:** Phase 3 Sharpe > 1.5
4. **Statistical Significance:** P-value < 0.05
5. **Fewer Trades, Higher Quality:** Phase 3 filters out false signals

### Red Flags

1. **No Statistical Significance:** P-value > 0.10
2. **Higher Drawdown:** Risk management issues
3. **Lower Win Rate:** ML predictions not adding value
4. **Similar Performance:** AI not providing edge

## Data Requirements

### Minimum Data

- **Candles:** 200+ for indicator warm-up
- **Days:** 30+ for meaningful statistical analysis
- **Recommended:** 90+ days for robust testing

### Optimal Settings

| Interval | Days | Use Case |
|----------|------|----------|
| 15m | 30 | Scalping/day trading |
| 60m | 90 | Swing trading (default) |
| 240m | 180 | Position trading |
| 1440m | 365 | Long-term strategies |

## Troubleshooting (comparison runs)

### No Trades Generated

**Issue:** Backtest completes but 0 trades executed

**Solutions:**
- Reduce lookback period (try 60 days instead of 90)
- Check if filters are too strict
- Verify data quality (check for gaps)
- Try more volatile asset (e.g., altcoins)

### Low Win Rate (<45%)

**Issue:** Both strategies showing poor performance

**Solutions:**
- Check market conditions (bear market affects all strategies)
- Verify indicator calculations
- Adjust RSI thresholds (try 25/75 instead of 30/70)
- Review stop-loss placement (may be too tight)

### Phase 3 Worse Than Phase 1

**Issue:** AI-enhanced strategy underperforms

**Solutions:**
- ML predictions may need real training data (currently simulated)
- Sentiment weights may be too high (reduce from 20% to 10%)
- Check if test period includes unusual market events
- Consider hybrid approach (use Phase 1 for entry, Phase 3 for exit)

### Memory Issues

**Issue:** Script crashes with large datasets

**Solutions:**
```bash
# Reduce data size
python backtesting/run_phase_comparison.py --days 30

# Test one symbol at a time
python backtesting/run_phase_comparison.py --symbols BTCUSDT
```

## Advanced Usage (comparison runs)

### Custom Strategy Testing

Edit `run_phase_comparison.py` to modify strategies:

```python
# Adjust RSI thresholds
if rsi < 25:  # More oversold
    # BUY signal

# Change ATR multipliers
'stop_loss': current_price - (atr * 1.5)  # Tighter stop
'take_profit': current_price + (atr * 5.0)  # Higher target
```

### Export Trade Data

```python
# Save trades to CSV
import pandas as pd

trades_df = pd.DataFrame([{
    'entry_time': t.entry_time,
    'exit_time': t.exit_time,
    'entry_price': t.entry_price,
    'exit_price': t.exit_price,
    'profit_loss': t.profit_loss,
    'exit_reason': t.exit_reason
} for t in phase1_result.trades])

trades_df.to_csv('phase1_trades.csv', index=False)
```

### Batch Testing

```bash
# Test multiple timeframes
for interval in 60 240 1440; do
    python backtesting/run_phase_comparison.py \
        --interval $interval \
        --symbols BTCUSDT
done
```

## Integration with Live Trading

### From Backtest to Production

1. **Validate Results:**
   - Win rate > 55%
   - Sharpe ratio > 1.5
   - Max drawdown < 15%
   - P-value < 0.05

2. **Paper Trading:**
   - Run live paper trading for 2 weeks
   - Verify similar performance to backtest
   - Monitor slippage and commission impact

3. **Live Deployment:**
   - Start with minimal capital (10% of total)
   - Gradually increase after consistent results
   - Monitor real-time metrics vs backtest

### Recommended Signal Weights (Production)

Based on typical backtest results:

```python
PRODUCTION_WEIGHTS = {
    # Core Technical Analysis (Phase 1)
    "rsi": 0.20,
    "macd": 0.15,
    "bollinger_bands": 0.15,
    "trend_filter": 0.20,
    "volume_confirmation": 0.10,

    # AI Enhancements (Phase 3)
    "ml_prediction": 0.15,  # If trained model available
    "sentiment_analysis": 0.05,  # If real APIs connected
}
```

## Performance Benchmarks

### Expected Results (90-day BTC backtest)

**Phase 1 (TA Only):**
- Win Rate: 50-60%
- Return: 8-15%
- Sharpe: 1.0-1.8
- Max DD: 8-12%

**Phase 3 (AI Enhanced):**
- Win Rate: 58-68%
- Return: 12-22%
- Sharpe: 1.5-2.5
- Max DD: 6-10%

**Improvement Range:**
- Win Rate: +5-10%
- Return: +30-50%
- Sharpe: +40-60%
- Drawdown: -20-30% reduction

> **Note (2026-07-30):** these benchmark ranges predate the GRU look-ahead-leakage fix; do not treat them as current expectations for the AI-enhanced leg.

## Support (comparison runs)

For issues or questions:
1. Check `backtesting/results/` for error logs
2. Review generated reports for diagnostic info
3. Verify data quality with `data_downloader.py`
4. Test with single symbol first to isolate issues

> **Stale links (2026-07-30):** the old `README_COMPARISON.md` "Further Reading" pointed to `../PHASE1_IMPLEMENTATION_STATUS.md`, `../PHASE3_COMPLETE.md`, and `../TRADING_STRATEGY_ANALYSIS.md`, which no longer exist in the repo (removed in the 2026-07-30 docs restructure). Current strategy evidence lives under `docs/strategy/` (e.g. `docs/strategy/evidence/`).

---

**Note:** Past performance does not guarantee future results. Always start with paper trading before deploying real capital.

## License

Part of the Crypto Trading Bot project.

## Support

For issues or questions:
- Check documentation in `/docs`
