# Parameter Optimization Guide - SQZMOM Strategy

## Overview

This guide explains how to optimize the Squeeze Momentum (SQZMOM) trading strategy parameters for maximum performance.

## Current Performance (Default Parameters)

Using default parameters:
```python
{
    'bb_length': 20,
    'kc_length': 20,
    'min_momentum_threshold': 0.3,
    'stop_loss_pct': 1.5,
    'take_profit_pct': 3.0
}
```

Results over 30 days (2025-10-20 to 2025-11-19):
- **SOLUSDT**: +2,706% return (22% win rate, 4.76 Sharpe ratio)
- **DOGEUSDT**: +630% return (28% win rate, 5.41 Sharpe ratio)
- **BNBUSDT**: +330% return (31% win rate, -3.21 Sharpe ratio)

## Optimization Scripts

### 1. optimize_parameters.py (Comprehensive)

**Purpose:** Full grid search optimization

**Features:**
- Tests 1,600 parameter combinations per symbol
- Comprehensive search across parameter space
- Best for finding global optimum
- Takes 30-60 minutes per symbol

**Parameter Grid:**
```python
{
    'bb_length': [15, 20, 25, 30],           # 4 values
    'kc_length': [15, 20, 25, 30],           # 4 values
    'min_momentum_threshold': [0.2, 0.3, 0.4, 0.5],  # 4 values
    'stop_loss_pct': [1.0, 1.5, 2.0, 2.5, 3.0],      # 5 values
    'take_profit_pct': [2.5, 3.0, 3.5, 4.0, 5.0]     # 5 values
}
# Total: 4 × 4 × 4 × 5 × 5 = 1,600 combinations
```

**Usage:**
```bash
cd /mnt/d/Bimo_max/crypto-trading-bot/services/technical-analysis/backtesting
python3 optimize_parameters.py
```

**Expected Time:** 90-180 minutes for all 3 symbols

### 2. optimize_focused.py (Fast)

**Purpose:** Quick optimization with focused ranges

**Features:**
- Tests 216 parameter combinations per symbol
- Focused around current best values
- Best for refinement and quick testing
- Takes 5-10 minutes per symbol

**Parameter Grid:**
```python
{
    'bb_length': [18, 20, 22],              # 3 values
    'kc_length': [18, 20, 22],              # 3 values
    'min_momentum_threshold': [0.25, 0.3, 0.35, 0.4],  # 4 values
    'stop_loss_pct': [1.25, 1.5, 1.75],     # 3 values
    'take_profit_pct': [2.75, 3.0, 3.25]    # 3 values
}
# Total: 3 × 3 × 4 × 3 × 3 = 216 combinations
```

**Usage:**
```bash
cd /mnt/d/Bimo_max/crypto-trading-bot/services/technical-analysis/backtesting
python3 optimize_focused.py
```

**Expected Time:** 15-30 minutes for all 3 symbols

### 3. Quick Test (Development)

For rapid testing during development, use the quick test function:

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot/services/technical-analysis/backtesting
python3 -c "import asyncio; from optimize_focused import quick_test_single_symbol; asyncio.run(quick_test_single_symbol())"
```

This tests only 27 combinations on SOLUSDT (takes ~2 minutes).

## Understanding Optimization Metrics

The optimizer can optimize for different metrics:

### 1. Sharpe Ratio (Recommended - Default)

**What it is:** Risk-adjusted return metric

**Formula:** `(Average Return - Risk-Free Rate) / Standard Deviation of Returns`

**Why use it:**
- Accounts for both return AND risk
- Penalizes volatile strategies
- Better for live trading (reduces stress)
- Industry standard for strategy evaluation

**When to use:** Always for production strategies

### 2. Total Return Percentage

**What it is:** Absolute profit/loss percentage

**Formula:** `(Final Capital - Initial Capital) / Initial Capital × 100`

**Why use it:**
- Simple and intuitive
- Maximizes profit without regard to risk
- Good for comparing absolute performance

**When to use:** When you want maximum profit regardless of volatility

### 3. Win Rate

**What it is:** Percentage of winning trades

**Formula:** `Winning Trades / Total Trades × 100`

**Why use it:**
- Psychological comfort (more wins)
- Good for strategies with small consistent gains
- May sacrifice total return

**When to use:** When you prefer many small wins over fewer large wins

## Optimization Process

### Step 1: Choose Optimization Type

```python
# In optimize_parameters.py or optimize_focused.py, line ~250
optimize_for='sharpe_ratio'  # or 'total_return_pct' or 'win_rate'
```

### Step 2: Run Optimization

```bash
# Focused (recommended first)
python3 optimize_focused.py

# Or comprehensive (for final optimization)
python3 optimize_parameters.py
```

### Step 3: Review Results

The optimizer generates three types of output files:

1. **PARAMETER_OPTIMIZATION_REPORT.md**
   - Human-readable markdown report
   - Summary of best parameters
   - Performance comparison table
   - Recommendations

2. **optimization_[SYMBOL].json** (per symbol)
   - Complete optimization results
   - All parameter combinations tested
   - Top 10 best parameter sets
   - Detailed metrics for each combination

3. **all_optimizations.json**
   - Combined results for all symbols
   - Cross-symbol comparison data
   - Overall statistics

### Step 4: Analyze Results

Look for:

1. **Best Sharpe Ratio:** Higher is better (>1.0 is good, >2.0 is excellent)
2. **Consistency:** Check if top 5 parameter sets are similar
3. **Trade Count:** Ensure sufficient trades (>20 for statistical significance)
4. **Max Drawdown:** Lower is better (<20% is acceptable)
5. **Win Rate:** Higher is better, but not at expense of Sharpe ratio

### Step 5: Apply Best Parameters

Copy the best parameters from the report into your production configuration:

```python
# Example from optimization results
SOLUSDT_OPTIMIZED_PARAMS = {
    'bb_length': 20,
    'kc_length': 22,
    'min_momentum_threshold': 0.3,
    'stop_loss_pct': 1.5,
    'take_profit_pct': 3.0,
    'require_squeeze_release': False,
    'require_volume_confirmation': False
}
```

## Advanced Usage

### Custom Parameter Grid

Edit the `param_grid` dictionary in either script:

```python
# Test different ranges
param_grid = {
    'bb_length': [15, 18, 20, 22, 25],      # More granular
    'kc_length': [20],                      # Fix this parameter
    'min_momentum_threshold': [0.2, 0.3, 0.4, 0.5, 0.6],  # Wider range
    'stop_loss_pct': [1.0, 1.5, 2.0],
    'take_profit_pct': [2.0, 3.0, 4.0, 5.0]
}
```

### Optimize Single Symbol

```python
# In optimize_focused.py or optimize_parameters.py
symbols = ['SOLUSDT']  # Instead of ['SOLUSDT', 'DOGEUSDT', 'BNBUSDT']
```

### Change Optimization Metric

```python
# In optimize_symbol() call
optimize_for='total_return_pct'  # For maximum return
optimize_for='win_rate'          # For maximum win rate
optimize_for='sharpe_ratio'      # For best risk-adjusted return (default)
```

### Parameter Sensitivity Analysis

After optimization, check which parameters matter most:

```python
from optimize_parameters import ParameterOptimizer
import json

# Load results
with open('optimization_SOLUSDT.json', 'r') as f:
    results = json.load(f)

# Analyze sensitivity (automatically done by optimizer)
# Look for "sensitivity_score" in output
# Higher score = parameter has bigger impact on performance
```

## Interpreting Results

### Good Optimization Results

```
Symbol: SOLUSDT
Best Sharpe: 5.5
Best Return: +3000%
Win Rate: 35%
Trades: 50
Max DD: 15%
```

**Why good:**
- High Sharpe ratio (>3.0)
- Consistent performance across top parameter sets
- Sufficient trades for statistical validity
- Acceptable drawdown (<20%)

### Concerning Results

```
Symbol: BNBUSDT
Best Sharpe: 0.5
Best Return: +50%
Win Rate: 15%
Trades: 5
Max DD: 45%
```

**Why concerning:**
- Low Sharpe ratio (<1.0)
- Few trades (not statistically significant)
- High drawdown (>30%)
- Low win rate (<20%)

**Action:** Strategy may not be suitable for this symbol

## Best Practices

### 1. Always Test on Historical Data First

Never deploy optimized parameters without backtesting on out-of-sample data.

### 2. Avoid Overfitting

**Signs of overfitting:**
- Perfect performance in backtest (>95% win rate)
- Very specific parameter values (e.g., 20.37 instead of 20)
- Poor performance on different time periods
- Huge difference between top and second-best parameters

**Prevention:**
- Use rounded parameter values
- Test on multiple time periods
- Require consistency across top parameter sets
- Use walk-forward optimization

### 3. Re-optimize Periodically

Market conditions change. Re-run optimization:
- Monthly for active trading
- Quarterly for conservative strategies
- After major market events

### 4. Monitor Live Performance

Track if optimized parameters continue to perform:
```python
# Compare backtest expectations vs live results
backtest_sharpe = 4.76
live_sharpe = calculate_live_sharpe()

if live_sharpe < backtest_sharpe * 0.5:
    print("WARNING: Performance degraded significantly")
    print("Consider re-optimization")
```

### 5. Use Symbol-Specific Parameters

Different symbols may require different parameters:
```python
OPTIMIZED_PARAMS = {
    'SOLUSDT': {...},
    'DOGEUSDT': {...},
    'BNBUSDT': {...}
}

# Use appropriate params for each symbol
params = OPTIMIZED_PARAMS[symbol]
```

## Troubleshooting

### Issue: Optimization Takes Too Long

**Solution:** Use focused optimization or reduce parameter grid

```python
# Smaller grid
param_grid = {
    'bb_length': [20],              # Fix at current value
    'kc_length': [20],              # Fix at current value
    'min_momentum_threshold': [0.2, 0.3, 0.4],  # Focus on key params
    'stop_loss_pct': [1.5, 2.0],
    'take_profit_pct': [3.0, 4.0]
}
# Total: 1 × 1 × 3 × 2 × 2 = 12 combinations (very fast)
```

### Issue: All Results Show Negative Returns

**Possible causes:**
1. Strategy not suitable for time period
2. Commission too high
3. Parameter ranges too restrictive

**Solutions:**
1. Try different time period or symbols
2. Check commission rate (should be 0.001 or 0.1%)
3. Expand parameter ranges

### Issue: Results Not Reproducible

**Cause:** Database data changed or different time period

**Solution:** Ensure consistent data and time ranges

### Issue: "No data available" Error

**Cause:** Database not connected or no data for symbol

**Solutions:**
```bash
# Check database connection
python3 test_db_connection.py

# Verify data exists
psql -h localhost -p 5433 -U cryptobot -d market_data \
  -c "SELECT symbol, COUNT(*) FROM market_data.candles GROUP BY symbol;"
```

## Output Files Reference

### PARAMETER_OPTIMIZATION_REPORT.md

Markdown report with:
- Executive summary
- Best parameters per symbol
- Performance metrics
- Comparison tables
- Recommendations

### optimization_[SYMBOL].json

JSON file with complete results:
```json
{
  "symbol": "SOLUSDT",
  "optimize_for": "sharpe_ratio",
  "best_params": {...},
  "best_score": 5.5,
  "top_10_results": [...],
  "all_results": [...]
}
```

### all_optimizations.json

Combined results for all symbols:
```json
{
  "SOLUSDT": {...},
  "DOGEUSDT": {...},
  "BNBUSDT": {...}
}
```

## Next Steps

After optimization:

1. **Review** PARAMETER_OPTIMIZATION_REPORT.md
2. **Validate** results make sense (no overfitting)
3. **Test** best parameters on different time period
4. **Document** parameter choices in strategy configuration
5. **Deploy** to paper trading first
6. **Monitor** live performance vs backtest expectations
7. **Re-optimize** monthly or when performance degrades

## FAQ

**Q: Should I optimize on all available data?**
A: No. Use 70% for optimization, 30% for validation (out-of-sample testing).

**Q: What if different symbols need vastly different parameters?**
A: This is normal. Use symbol-specific configurations.

**Q: How often should I re-optimize?**
A: Monthly for active strategies, quarterly for conservative ones.

**Q: What's a good Sharpe ratio?**
A: >1.0 is good, >2.0 is excellent, >3.0 is exceptional.

**Q: Should I use the absolute best parameters or average of top 5?**
A: For conservative approach, use parameters that appear in multiple top results.

**Q: What if optimization shows 0 trades?**
A: Parameters are too restrictive. Expand parameter ranges, especially `min_momentum_threshold`.

## Resources

- **Backtest Results:** `SQZMOM_BACKTEST_REPORT.md`
- **Test Database Connection:** `test_db_connection.py`
- **Quick Backtest:** `quick_test.py`
- **Main Backtester:** `sqzmom_backtest.py`
- **Full Backtest Suite:** `run_backtest.py`

---

*Last Updated: 2025-11-20*
*Version: 1.0*
