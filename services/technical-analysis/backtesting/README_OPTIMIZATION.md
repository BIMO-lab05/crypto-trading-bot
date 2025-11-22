# Parameter Optimization System - README

## Quick Start

```bash
# Navigate to backtesting directory
cd /mnt/d/Bimo_max/crypto-trading-bot/services/technical-analysis/backtesting

# Run focused optimization (recommended first time)
python3 optimize_focused.py

# Monitor progress (in another terminal)
./monitor_optimization.sh

# View results (after completion)
cat PARAMETER_OPTIMIZATION_REPORT.md
```

## What This Does

Optimizes SQZMOM strategy parameters for maximum performance on three profitable symbols:
- **SOLUSDT** (currently +2,706% return)
- **DOGEUSDT** (currently +630% return)
- **BNBUSDT** (currently +330% return)

## Files Overview

### Optimization Scripts

| File | Purpose | Combinations | Time |
|------|---------|--------------|------|
| `optimize_focused.py` | Fast optimization | 216 per symbol | 15-30 min |
| `optimize_parameters.py` | Comprehensive | 1,600 per symbol | 90-180 min |

### Documentation

| File | Description |
|------|-------------|
| `OPTIMIZATION_GUIDE.md` | Complete user guide with examples |
| `OPTION_C_IMPLEMENTATION.md` | Technical implementation details |
| `README_OPTIMIZATION.md` | This quick reference |

### Utilities

| File | Purpose |
|------|---------|
| `monitor_optimization.sh` | Check optimization progress |

### Output Files (Generated)

| File | Description |
|------|-------------|
| `PARAMETER_OPTIMIZATION_REPORT.md` | Human-readable results report |
| `optimization_[SYMBOL]_focused.json` | Detailed results per symbol |
| `all_optimizations_focused.json` | Combined results |

## Parameter Grid

### Default Parameters (Current)

```python
{
    'bb_length': 20,
    'kc_length': 20,
    'min_momentum_threshold': 0.3,
    'stop_loss_pct': 1.5,
    'take_profit_pct': 3.0
}
```

### Focused Grid (216 combinations)

```python
{
    'bb_length': [18, 20, 22],
    'kc_length': [18, 20, 22],
    'min_momentum_threshold': [0.25, 0.3, 0.35, 0.4],
    'stop_loss_pct': [1.25, 1.5, 1.75],
    'take_profit_pct': [2.75, 3.0, 3.25]
}
```

### Comprehensive Grid (1,600 combinations)

```python
{
    'bb_length': [15, 20, 25, 30],
    'kc_length': [15, 20, 25, 30],
    'min_momentum_threshold': [0.2, 0.3, 0.4, 0.5],
    'stop_loss_pct': [1.0, 1.5, 2.0, 2.5, 3.0],
    'take_profit_pct': [2.5, 3.0, 3.5, 4.0, 5.0]
}
```

## Optimization Metrics

### Sharpe Ratio (Default - Recommended)
- **What:** Risk-adjusted return
- **Best for:** Live trading
- **Good value:** > 2.0

### Total Return %
- **What:** Absolute profit percentage
- **Best for:** Maximum profit
- **Good value:** > 100%

### Win Rate
- **What:** Percentage of winning trades
- **Best for:** Psychological comfort
- **Good value:** > 30%

## Usage Examples

### Example 1: Quick Test (2 minutes)

```bash
python3 -c "
import asyncio
from optimize_focused import quick_test_single_symbol
asyncio.run(quick_test_single_symbol())
"
```

### Example 2: Focused Optimization (15-30 minutes)

```bash
python3 optimize_focused.py
```

### Example 3: Comprehensive Optimization (90-180 minutes)

```bash
python3 optimize_parameters.py
```

### Example 4: Check Results

```bash
# View report
cat PARAMETER_OPTIMIZATION_REPORT.md

# Parse JSON
python3 -c "
import json
with open('optimization_SOLUSDT_focused.json') as f:
    data = json.load(f)
    print('Best Sharpe:', data['best_score'])
    print('Best Params:', json.dumps(data['best_params'], indent=2))
"
```

## Understanding Results

### Good Results Example

```
Symbol: SOLUSDT
Best Sharpe: 5.5
Best Return: +3000%
Win Rate: 35%
Trades: 50
Max Drawdown: 15%
```

**What this means:**
- ✅ Excellent risk-adjusted return (Sharpe > 3.0)
- ✅ High absolute returns
- ✅ Sufficient trades for statistical validity
- ✅ Acceptable drawdown (<20%)

### Concerning Results Example

```
Symbol: BNBUSDT
Best Sharpe: 0.5
Best Return: +50%
Win Rate: 15%
Trades: 5
Max Drawdown: 45%
```

**What this means:**
- ❌ Poor risk-adjusted return (Sharpe < 1.0)
- ❌ Few trades (not statistically significant)
- ❌ High drawdown (>30%)
- ❌ Low win rate

**Action needed:** Consider different parameters or different strategy for this symbol

## Applying Results

### Step 1: Read the Report

```bash
cat PARAMETER_OPTIMIZATION_REPORT.md
```

Look for the "Best Parameters" section for each symbol.

### Step 2: Update Your Configuration

```python
# In your strategy configuration file
OPTIMIZED_PARAMS = {
    'SOLUSDT': {
        'bb_length': 20,        # From optimization
        'kc_length': 22,        # From optimization
        'min_momentum_threshold': 0.3,  # From optimization
        'stop_loss_pct': 1.5,   # From optimization
        'take_profit_pct': 3.0  # From optimization
    },
    'DOGEUSDT': {
        # ... optimized parameters for DOGE
    },
    'BNBUSDT': {
        # ... optimized parameters for BNB
    }
}
```

### Step 3: Test with Backtest

```bash
# Run backtest with new parameters
python3 run_backtest.py

# Compare with old results
# Old: backtest_results.json
# New: backtest_results_optimized.json
```

### Step 4: Deploy to Paper Trading

Only after successful backtesting validation.

## Monitoring Optimization

While optimization is running:

```bash
# Check status
./monitor_optimization.sh

# Check process
ps aux | grep optimize

# Check output files
ls -lth optimization*.json

# Follow progress (if logging to file)
tail -f logs/optimization.log
```

## Common Issues

### Issue: Takes too long

**Solution:** Use focused optimization instead of comprehensive

```bash
python3 optimize_focused.py  # 15-30 min
# Instead of:
# python3 optimize_parameters.py  # 90-180 min
```

### Issue: No output files

**Possible causes:**
1. Still running (check with `ps aux | grep optimize`)
2. Error occurred (check terminal output)
3. Database connection failed

**Solutions:**
```bash
# Check if running
ps aux | grep optimize

# Test database
python3 test_db_connection.py

# Check for errors in output
grep -i error /tmp/optimize_output.log
```

### Issue: All results show 0 trades

**Cause:** Parameters too restrictive

**Solution:** Expand parameter ranges, especially `min_momentum_threshold`

```python
# In optimize script, change:
'min_momentum_threshold': [0.1, 0.2, 0.3, 0.4]  # Lower minimum
```

### Issue: Results not reproducible

**Cause:** Different data or time period

**Solution:** Use consistent date ranges:
```python
start_date='2025-10-20'
end_date='2025-11-19'
```

## Advanced Usage

### Custom Parameter Grid

Edit the script directly:

```python
# In optimize_focused.py or optimize_parameters.py
param_grid = {
    'bb_length': [15, 18, 20, 22, 25],      # Your values
    'kc_length': [20],                      # Fix this one
    'min_momentum_threshold': [0.2, 0.3, 0.4],
    'stop_loss_pct': [1.5, 2.0],
    'take_profit_pct': [3.0, 4.0, 5.0]
}
```

### Optimize for Different Metric

```python
# In optimize_symbol() call, change:
optimize_for='sharpe_ratio'      # Default (recommended)
# To:
optimize_for='total_return_pct'  # For max return
# Or:
optimize_for='win_rate'          # For max win rate
```

### Optimize Single Symbol

```python
# In main function, change:
symbols = ['SOLUSDT', 'DOGEUSDT', 'BNBUSDT']
# To:
symbols = ['SOLUSDT']  # Just one
```

## Best Practices

### 1. Start with Focused Optimization

```bash
# First run: Use focused (fast)
python3 optimize_focused.py

# If results look good, run comprehensive
python3 optimize_parameters.py
```

### 2. Validate Results

```bash
# Always backtest with optimized parameters before live trading
python3 run_backtest.py --params OPTIMIZED_PARAMS
```

### 3. Re-optimize Regularly

```bash
# Set up monthly re-optimization
crontab -e
# Add:
# 0 0 1 * * cd /path/to/backtesting && python3 optimize_focused.py
```

### 4. Monitor Live Performance

```python
# Track if optimized parameters continue to work
if live_sharpe < backtest_sharpe * 0.5:
    alert("Parameters degraded - re-optimize needed")
```

## Performance Expectations

### Focused Optimization

- **Time:** 15-30 minutes total
- **CPU:** 100% usage (normal)
- **Memory:** ~200 MB
- **Combinations:** 216 per symbol
- **Output files:** 4 files

### Comprehensive Optimization

- **Time:** 90-180 minutes total
- **CPU:** 100% usage (normal)
- **Memory:** ~300 MB
- **Combinations:** 1,600 per symbol
- **Output files:** 4 files

## Support and Troubleshooting

### Documentation

1. `OPTIMIZATION_GUIDE.md` - Complete guide
2. `OPTION_C_IMPLEMENTATION.md` - Technical details
3. This file - Quick reference

### Logs

Check these if issues occur:
- Terminal output
- `/tmp/optimize_output.log`
- System logs: `journalctl -f`

### Database

Verify database connection:
```bash
python3 test_db_connection.py
```

### Debug Mode

Run with verbose output:
```python
# In the script, set:
logging.basicConfig(level=logging.DEBUG)
```

## FAQ

**Q: How long does it take?**
A: Focused = 15-30 min, Comprehensive = 90-180 min

**Q: Can I stop and resume?**
A: No, but you can run focused first for quick results

**Q: Will it hurt my database?**
A: No, optimization only reads data (no writes)

**Q: What if I get different results?**
A: Ensure same date range and data. Minor variations are normal.

**Q: Should I use the absolute best parameters?**
A: Check top 5 results. If similar, use the most common values.

**Q: How often should I re-optimize?**
A: Monthly for active trading, quarterly for conservative

**Q: What's a good Sharpe ratio?**
A: >1.0 = good, >2.0 = very good, >3.0 = excellent

**Q: Can I optimize other symbols?**
A: Yes, add them to the symbols list in the script

**Q: What if all results are negative?**
A: Strategy may not work for that time period/symbol

**Q: How do I know if results are overfit?**
A: Test on different time period (out-of-sample validation)

## Next Steps

1. ✅ Run optimization: `python3 optimize_focused.py`
2. ⏳ Wait for completion (15-30 minutes)
3. 📊 Review report: `cat PARAMETER_OPTIMIZATION_REPORT.md`
4. 💾 Save best parameters to configuration
5. 🧪 Test with backtest: `python3 run_backtest.py`
6. 📝 Document changes in strategy config
7. 🚀 Deploy to paper trading
8. 📈 Monitor live performance
9. 🔄 Re-optimize monthly

## Current Status

**Implementation:** ✅ Complete
**Testing:** ⏳ In Progress (optimize_focused.py running)
**Documentation:** ✅ Complete
**Ready for Production:** ⏳ Awaiting results

---

*Last Updated: 2025-11-20*
*Version: 1.0*
*Status: Ready for use*
