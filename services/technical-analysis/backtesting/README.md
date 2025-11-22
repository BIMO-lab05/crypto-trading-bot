# SQZMOM Strategy Backtesting Module

Comprehensive backtesting framework for the Squeeze Momentum (SQZMOM) trading strategy using real historical cryptocurrency data from TimescaleDB.

## Quick Start

### 1. Test Database Connection
```bash
python3 test_db_connection.py
```

Expected output:
```
✓ Successfully connected to TimescaleDB!
Available Historical Data:
Total Symbols: 7
Total Candles: 5,040
```

### 2. Run Quick Single-Symbol Test
```bash
python3 quick_test.py
```

This runs a backtest on BTCUSDT and displays results in ~5 seconds.

### 3. Run Comprehensive Backtest Suite
```bash
python3 run_backtest.py
```

This performs:
- Individual backtests on all 7 symbols
- Multi-symbol portfolio backtest
- Parameter optimization
- Generates comprehensive reports

## Module Files

| File | Purpose | Lines |
|------|---------|-------|
| `sqzmom_backtest.py` | Core backtesting engine | 792 |
| `run_backtest.py` | Comprehensive test suite | 437 |
| `quick_test.py` | Quick single-symbol test | 50 |
| `test_db_connection.py` | Database verification | 100 |

## Features

### Backtesting Capabilities
- ✅ Single symbol backtesting
- ✅ Multi-symbol portfolio testing
- ✅ Parameter grid search optimization
- ✅ Real-time database integration
- ✅ Commission accounting (0.1% default)
- ✅ Risk-based position sizing (2% per trade)
- ✅ Bar-by-bar historical replay

### Performance Metrics
- **Profitability**: Total Return %, P&L, Profit Factor
- **Win Rate**: Wins/Losses, Win/Loss Ratio, Average Win/Loss
- **Risk Metrics**: Sharpe Ratio, Maximum Drawdown, Sortino Ratio
- **Trade Statistics**: Duration, Frequency, Long/Short breakdown
- **Equity Curve**: Continuous capital tracking

### Risk Management
- Position sizing based on stop loss distance
- Maximum 2% risk per trade
- Capital preservation (95% max position size)
- Commission impact on every trade
- Drawdown tracking

## Usage Examples

### Example 1: Simple Backtest
```python
import asyncio
from sqzmom_backtest import SQZMOMBacktester

async def main():
    # Configure database
    db_config = {
        'host': 'localhost',
        'port': 5433,
        'database': 'market_data',
        'user': 'cryptobot',
        'password': 'timescale_dev_password'
    }

    # Initialize backtester
    backtester = SQZMOMBacktester(
        db_config=db_config,
        initial_capital=10000.0,
        commission=0.001,
        risk_per_trade=0.02
    )

    await backtester.connect_db()

    # Run backtest
    result = await backtester.run_backtest('BTCUSDT')

    # Print results
    print(f"Total Trades: {result['total_trades']}")
    print(f"Win Rate: {result['win_rate']:.2f}%")
    print(f"Total Return: {result['total_return_pct']:.2f}%")
    print(f"Sharpe Ratio: {result['sharpe_ratio']:.2f}")

    await backtester.close()

asyncio.run(main())
```

### Example 2: Custom Parameters
```python
# Custom strategy parameters
params = {
    'bb_length': 25,
    'kc_length': 25,
    'min_momentum_threshold': 0.7,
    'stop_loss_pct': 1.5,
    'take_profit_pct': 5.0,
    'require_squeeze_release': True,
    'require_volume_confirmation': False
}

result = await backtester.run_backtest('ETHUSDT', strategy_params=params)
```

### Example 3: Multi-Symbol Portfolio
```python
symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT']

portfolio_result = await backtester.run_multi_symbol_backtest(
    symbols,
    strategy_params=params
)

print(f"Combined Return: {portfolio_result['combined_metrics']['total_return_pct']:.2f}%")
print(f"Total Trades: {portfolio_result['combined_metrics']['total_trades']}")
```

### Example 4: Parameter Optimization
```python
# Define parameter ranges to test
param_ranges = {
    'min_momentum_threshold': [0.3, 0.5, 0.7],
    'stop_loss_pct': [1.5, 2.0, 2.5],
    'take_profit_pct': [3.0, 4.0, 5.0]
}

# Run optimization (tests 27 combinations)
opt_result = await backtester.optimize_parameters('BTCUSDT', param_ranges)

print(f"Best Parameters: {opt_result['best_params']}")
print(f"Best Return: {opt_result['best_return']:.2f}%")
print(f"Tested {opt_result['total_combinations_tested']} combinations")

# Top 5 parameter sets
for i, result in enumerate(opt_result['all_results'][:5], 1):
    print(f"{i}. Return: {result['return_pct']:.2f}%, "
          f"Win Rate: {result['win_rate']:.2f}%, "
          f"Sharpe: {result['sharpe_ratio']:.2f}")
```

## Strategy Configuration

### Default Parameters
```python
{
    'bb_length': 20,                      # Bollinger Bands period
    'bb_mult': 2.0,                       # BB standard deviation multiplier
    'kc_length': 20,                      # Keltner Channels period
    'kc_mult': 1.5,                       # KC ATR multiplier
    'min_momentum_threshold': 0.5,        # Minimum momentum for entry
    'stop_loss_pct': 2.0,                 # Stop loss percentage
    'take_profit_pct': 4.0,               # Take profit percentage
    'require_squeeze_release': False,     # Only trade on squeeze release
    'require_volume_confirmation': False  # Require above-average volume
}
```

### Entry Rules (LONG)
1. Momentum > min_momentum_threshold
2. Color is bullish ('lime' or 'green')
3. Either:
   - Squeeze released (squeeze_off = True), OR
   - Squeeze active with accelerating momentum (color = 'lime')

### Entry Rules (SHORT)
1. Momentum < -min_momentum_threshold
2. Color is bearish ('red' or 'maroon')
3. Either:
   - Squeeze released (squeeze_off = True), OR
   - Squeeze active with accelerating negative momentum (color = 'red')

### Exit Rules
1. **Stop Loss**: Price moves against position by stop_loss_pct
2. **Take Profit**: Price moves in favor by take_profit_pct
3. **Momentum Reversal**: Color changes (bullish to bearish or vice versa)
4. **Momentum Exhaustion**: Momentum declining for 3+ consecutive bars

## Output Files

After running `run_backtest.py`, the following files are generated:

### SQZMOM_BACKTEST_REPORT.md
Comprehensive markdown report with:
- Executive summary
- Individual symbol performance
- Portfolio performance
- Parameter optimization results
- Key findings and recommendations

### backtest_results.json
JSON file containing:
```json
{
  "generated_at": "2025-11-20T10:00:00",
  "test_config": {...},
  "individual_results": {
    "BTCUSDT": {...},
    "ETHUSDT": {...}
  },
  "portfolio_results": {...},
  "optimization_results": {...}
}
```

### trade_logs.json
Detailed trade-by-trade logs:
```json
{
  "BTCUSDT": [
    {
      "direction": "LONG",
      "entry_time": "2025-10-20T19:00:00",
      "entry_price": 67500.00,
      "exit_time": "2025-10-21T15:00:00",
      "exit_price": 69200.00,
      "pnl": 425.50,
      "pnl_pct": 2.52,
      "duration_hours": 20.0
    }
  ]
}
```

## Performance Metrics Explained

### Profitability Metrics
- **Total Return %**: (Final Capital - Initial Capital) / Initial Capital * 100
- **Total P&L**: Final Capital - Initial Capital (in USD)
- **Profit Factor**: Gross Profit / Gross Loss (>1 is profitable)

### Risk-Adjusted Metrics
- **Sharpe Ratio**: (Mean Return / Std Dev of Returns) × √(365×24) for hourly data
  - < 0: Negative returns
  - 0-1: Poor risk-adjusted returns
  - 1-2: Good risk-adjusted returns
  - \> 2: Excellent risk-adjusted returns
- **Maximum Drawdown**: Largest peak-to-trough decline in equity

### Win Rate Metrics
- **Win Rate %**: (Winning Trades / Total Trades) × 100
- **Average Win**: Mean P&L of winning trades
- **Average Loss**: Mean P&L of losing trades
- **Win/Loss Ratio**: Average Win / |Average Loss|

## Database Requirements

### TimescaleDB Connection
```
Host:     localhost
Port:     5433
Database: market_data
User:     cryptobot
Password: timescale_dev_password
```

### Required Table Structure
```sql
CREATE TABLE market_data.candles (
    time        TIMESTAMPTZ NOT NULL,
    symbol      TEXT NOT NULL,
    interval    TEXT NOT NULL,
    open        DECIMAL NOT NULL,
    high        DECIMAL NOT NULL,
    low         DECIMAL NOT NULL,
    close       DECIMAL NOT NULL,
    volume      DECIMAL NOT NULL
);
```

### Available Data
- **Symbols**: BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT, ADAUSDT, DOGEUSDT
- **Period**: 2025-10-20 to 2025-11-19 (30 days)
- **Interval**: 1 hour (60 minutes)
- **Total Candles**: 720 per symbol (5,040 total)

## Dependencies

```
asyncpg >= 0.27.0
pandas >= 2.0.0
numpy >= 1.24.0
scipy >= 1.10.0
```

Install with:
```bash
pip install asyncpg pandas numpy scipy
```

## Performance

### Execution Times
- Single symbol backtest (720 candles): ~2-5 seconds
- Multi-symbol (4 symbols): ~10-20 seconds
- Parameter optimization (27 combinations): ~1-2 minutes

### Memory Usage
- Typical memory footprint: < 200 MB
- Scales linearly with number of candles
- Efficient pandas operations

## Error Handling

The framework includes comprehensive error handling:

- Database connection errors
- Missing/corrupt data
- Invalid parameters
- Calculation errors
- Type conversion issues

All errors are logged with full stack traces.

## Logging

Logging is configured at INFO level by default:

```python
import logging
logging.basicConfig(level=logging.INFO)
```

To enable debug logging:
```python
logging.basicConfig(level=logging.DEBUG)
```

Log format:
```
2025-11-20 10:15:03,422 - sqzmom_backtest - INFO - Starting backtest for BTCUSDT...
```

## Troubleshooting

### Database Connection Failed
```
✗ Connection failed: could not connect to server
```
**Solution**: Ensure TimescaleDB docker container is running:
```bash
docker ps | grep timescaledb
```

### No Data Found
```
⚠ No data found for BTCUSDT
```
**Solution**: Check if data exists in database:
```sql
SELECT COUNT(*) FROM market_data.candles WHERE symbol = 'BTCUSDT';
```

### Decimal Type Errors
```
TypeError: unsupported operand type(s) for -: 'decimal.Decimal' and 'float'
```
**Solution**: Already handled in current version. Data is converted from Decimal to float automatically.

## Best Practices

### 1. Start with Quick Test
Always run `quick_test.py` first to verify setup before running full backtests.

### 2. Validate Data Quality
Check that price data is realistic before interpreting results.

### 3. Use Parameter Optimization Carefully
- Start with small parameter ranges
- Beware of overfitting
- Validate optimized parameters on out-of-sample data

### 4. Monitor Memory with Large Datasets
For datasets > 10,000 candles, consider batch processing.

### 5. Save Results
Always save results to JSON for later analysis:
```python
import json
with open('my_backtest_results.json', 'w') as f:
    json.dump(result, f, indent=2)
```

## License

Part of the Crypto Trading Bot project.

## Support

For issues or questions, see the main project documentation.

---

**Version**: 1.0.0
**Last Updated**: 2025-11-20
**Status**: Production Ready
