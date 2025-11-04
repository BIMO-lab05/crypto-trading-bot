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
- Ensure market-data-service is running on localhost:8003
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

## License

Part of the Crypto Trading Bot project.

## Support

For issues or questions:
- Check documentation in `/docs`
- Review Phase 1 implementation status: `PHASE1_IMPLEMENTATION_STATUS.md`
- Review Phase 1 API reference: `PHASE1_API_REFERENCE.md`
