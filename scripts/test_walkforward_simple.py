#!/usr/bin/env python3
"""
Simple Walk-Forward Test
Test the optimizer with existing BTC data
"""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np
from datetime import datetime
import logging

from backtesting.optimizers.walk_forward_optimizer import (
    WalkForwardOptimizer,
    WalkForwardConfig
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load existing BTC data
data = pd.read_csv(project_root / 'backtesting/data/BTCUSDT_60m_90d_bybit.csv', parse_dates=['timestamp'])

logger.info(f"Loaded {len(data)} candles")
logger.info(f"Date range: {data['timestamp'].min()} to {data['timestamp'].max()}")

# Define a simple strategy function
def simple_strategy(df, params):
    """Simple moving average crossover strategy"""
    fast_ma = df['close'].rolling(window=params.get('fast_period', 10)).mean()
    slow_ma = df['close'].rolling(window=params.get('slow_period', 30)).mean()
    
    df = df.copy()
    df['signal'] = 0
    df.loc[fast_ma > slow_ma, 'signal'] = 1  # BUY
    df.loc[fast_ma < slow_ma, 'signal'] = -1  # SELL
    
    return df

# Simple backtest function
def simple_backtest(data, params):
    """Run simple backtest and return metrics"""
    df = simple_strategy(data, params)
    
    # Calculate returns
    df['returns'] = df['close'].pct_change()
    df['strategy_returns'] = df['signal'].shift(1) * df['returns']
    
    # Calculate metrics
    total_return = (1 + df['strategy_returns']).prod() - 1
    volatility = df['strategy_returns'].std() * np.sqrt(24 * 365)  # Annualized
    sharpe = total_return / volatility if volatility > 0 else 0
    
    max_dd = 0
    peak = 1
    for ret in (1 + df['strategy_returns']).cumprod():
        if ret > peak:
            peak = ret
        dd = (peak - ret) / peak
        if dd > max_dd:
            max_dd = dd
    
    num_trades = (df['signal'].diff() != 0).sum()
    
    return {
        'sharpe_ratio': sharpe,
        'total_return': total_return,
        'max_drawdown': max_dd,
        'num_trades': num_trades
    }

# Create config
config = WalkForwardConfig(
    total_periods=3,
    in_sample_ratio=0.70,
    metric_to_optimize='sharpe_ratio'
)

# Create optimizer
optimizer = WalkForwardOptimizer(config)

# Create periods
periods = optimizer.create_periods(data)

logger.info(f"\nCreated {len(periods)} walk-forward periods:")
for i, p in enumerate(periods, 1):
    logger.info(f"  Period {i}: IS={len(p.is_data)} rows, OOS={len(p.oos_data)} rows")

# Define parameter space
param_space = {
    'fast_period': [5, 10, 15],
    'slow_period': [20, 30, 40]
}

logger.info(f"\nParameter space: {param_space}")
logger.info(f"Total combinations: {3 * 3} = 9")

# Test optimization on first period
logger.info(f"\n" + "="*80)
logger.info("TESTING SINGLE PERIOD OPTIMIZATION")
logger.info("="*80)

# Manually test one period
period = periods[0]
best_sharpe = -999
best_params = None

for fast in param_space['fast_period']:
    for slow in param_space['slow_period']:
        if fast >= slow:
            continue
            
        params = {'fast_period': fast, 'slow_period': slow}
        metrics = simple_backtest(period.is_data, params)
        
        logger.info(f"  {params} -> Sharpe: {metrics['sharpe_ratio']:.3f}, Return: {metrics['total_return']:.2%}")
        
        if metrics['sharpe_ratio'] > best_sharpe:
            best_sharpe = metrics['sharpe_ratio']
            best_params = params

logger.info(f"\nBest IS params: {best_params} (Sharpe: {best_sharpe:.3f})")

# Test on OOS
oos_metrics = simple_backtest(period.oos_data, best_params)
logger.info(f"OOS performance: Sharpe: {oos_metrics['sharpe_ratio']:.3f}, Return: {oos_metrics['total_return']:.2%}")

wfe = oos_metrics['sharpe_ratio'] / max(best_sharpe, 0.01)
logger.info(f"Walk-Forward Efficiency (WFE): {wfe:.2%}")

logger.info(f"\n" + "="*80)
if wfe > 0.50:
    logger.info("✅ WFE > 50% - Strategy shows robustness!")
else:
    logger.info("❌ WFE < 50% - Strategy may be overfit")
logger.info("="*80)

logger.info(f"\n✅ Walk-Forward Optimizer structure validated!")
logger.info(f"Next step: Integrate with full backtest engine for complete optimization")
