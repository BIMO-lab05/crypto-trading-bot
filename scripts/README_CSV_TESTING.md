# Grid Trading v1 - CSV Historical Data Testing

## Overview
Script to test Grid Trading v1 strategy using real historical data from Bybit API instead of generated data.

## Script Location
```
/mnt/d/Bimo_max/crypto-trading-bot/scripts/test_grid_v1_with_csv.py
```

## How to Run
```bash
cd /mnt/d/Bimo_max/crypto-trading-bot
python3 scripts/test_grid_v1_with_csv.py
```

## Data Source
- **Location**: `/mnt/d/Bimo_max/crypto-trading-bot/data/historical/`
- **Format**: CSV files named `{SYMBOL}_180days_20251208.csv`
- **Columns**: timestamp, open, high, low, close, volume, turnover
- **Period**: 180 days (June 11 - December 7, 2025)
- **Timeframe**: Hourly (1H) bars
- **Total Bars**: ~4,320 per symbol

## Available Symbols (10 total)
1. BTCUSDT - Bitcoin
2. ETHUSDT - Ethereum
3. SOLUSDT - Solana
4. BNBUSDT - Binance Coin
5. ADAUSDT - Cardano
6. APTUSDT - Aptos
7. DOTUSDT - Polkadot
8. LTCUSDT - Litecoin
9. POLUSDT - Polygon
10. AVAXUSDT - Avalanche

## Test Results Summary (December 8, 2025)

### Performance Comparison
| Metric | Generated Data | Real CSV Data | Difference |
|--------|---------------|---------------|------------|
| Win Rate | 32.6% | 0.0% | -32.6% |
| Avg Return | N/A | -0.00% | N/A |
| Avg Sharpe | N/A | -0.33 | N/A |
| Total Trades | N/A | 661 | N/A |

### Per-Symbol Results
| Symbol | Win Rate | Return | Sharpe | Trades | Status |
|--------|----------|--------|--------|--------|--------|
| BTCUSDT | 0.0% | -0.00% | -0.74 | 59 | ❌ |
| ETHUSDT | 0.0% | -0.00% | -0.38 | 59 | ❌ |
| SOLUSDT | 0.0% | 0.00% | 0.15 | 78 | ❌ |
| BNBUSDT | 0.0% | -0.00% | -0.05 | 66 | ❌ |
| ADAUSDT | 0.0% | -0.00% | -0.41 | 66 | ❌ |
| APTUSDT | 0.0% | -0.00% | -0.46 | 69 | ❌ |
| DOTUSDT | 0.0% | -0.00% | -0.50 | 53 | ❌ |
| LTCUSDT | 0.0% | -0.00% | -0.05 | 66 | ❌ |
| POLUSDT | 0.0% | -0.00% | -0.35 | 71 | ❌ |
| AVAXUSDT | 0.0% | -0.00% | -0.49 | 74 | ❌ |

## Critical Findings

### 1. Strategy Overfitting
The Grid Trading v1 strategy shows **severe overfitting** to generated data:
- Generated data: 32.6% win rate
- Real market data: 0.0% win rate
- **32.6% performance degradation**

### 2. Trade Signal Generation
- Strategy generates signals (avg 66 trades per symbol)
- But trades are not profitable (0 winning trades)
- Suggests filters (ADX/RSI/Volume) are too restrictive or incorrect

### 3. Root Causes
Potential issues:
- **Generated data unrealistic**: Simulated ranging markets don't match real volatility
- **Filter parameters wrong**: ADX/RSI/Volume thresholds need calibration
- **Market conditions**: Real markets may not be ranging during test period
- **Grid parameters**: Grid levels/range may not suit real market dynamics

## Next Steps

### Immediate Actions
1. **Disable filters and re-test**: Test without ADX/RSI/Volume filters to see if they're the problem
2. **Analyze market conditions**: Check if test period had ranging vs trending markets
3. **Parameter optimization**: Use real data to optimize grid levels, range, ATR multiplier

### Script Modifications Needed
```python
# Test WITHOUT filters
result = run_grid_v1_backtest(symbol, use_filters=False)
```

### Long-term Improvements
1. Use real historical data for parameter optimization
2. Implement walk-forward testing
3. Add market regime detection
4. Calibrate filters using real market statistics
5. Consider reducing filter strictness

## Strategy Configuration

### Current Parameters
```python
GridTradingStrategy(
    symbol=symbol,
    grid_levels=10,           # 10 grid levels
    grid_range_pct=0.10,      # 10% range
    use_atr_spacing=True,     # ATR-based spacing
    max_positions=5,          # Max 5 concurrent positions
    position_size_pct=0.02,   # 2% per position
)
```

### Backtest Configuration
```python
BacktestConfig(
    initial_equity=10000.0,    # $10,000 capital
    commission_pct=0.1,        # 0.1% commission
    slippage_pct=0.05,         # 0.05% slippage
    position_size_pct=2.0,     # 2% per position
    max_positions=5,           # Max 5 positions
    use_stop_loss=True,
    use_take_profit=True,
)
```

## Technical Details

### CSV Data Loading
```python
def load_csv_data(symbol: str) -> List[OHLCV]:
    """Load CSV and convert to OHLCV format"""
    csv_file = f"{DATA_DIR}/{symbol}_180days_20251208.csv"
    df = pd.read_csv(csv_file)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    bars = [
        OHLCV(
            timestamp=row['timestamp'].to_pydatetime(),
            open=float(row['open']),
            high=float(row['high']),
            low=float(row['low']),
            close=float(row['close']),
            volume=float(row['volume']),
        )
        for _, row in df.iterrows()
    ]
    return bars
```

### Backtest Execution
```python
strategy = GridTradingStrategy(...)
config = BacktestConfig(...)
engine = BacktestEngine(config)
result: BacktestResult = engine.run(strategy, bars)

# Access metrics
metrics = result.metrics
win_rate = metrics.win_rate
total_return = metrics.total_return_pct
sharpe = metrics.sharpe_ratio
```

## Conclusion

**CRITICAL ISSUE DISCOVERED**: Grid Trading v1 is **NOT production-ready**. The strategy needs:

1. ❌ Re-calibration with real market data
2. ❌ Filter parameter optimization
3. ❌ Market regime detection
4. ❌ Extensive testing across different market conditions

The 32.6% win rate baseline was **artificially inflated** by testing on generated data that doesn't reflect real market dynamics.

**Recommendation**: Do NOT deploy this strategy to live trading. Requires complete re-validation with real data.

---

**Created**: December 8, 2025  
**Author**: Grid Trading v1 Testing Framework  
**Status**: ⚠️ Strategy FAILED real data validation
