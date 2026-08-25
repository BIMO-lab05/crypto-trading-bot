#!/usr/bin/env python3
"""
Grid Trading Walk-Forward Validation
Tests strategy on unseen future data periods to validate robustness.

Method:
- Train/optimize on first 120 days (in-sample)
- Test on next 60 days (out-of-sample)
- Repeat for overlapping windows

Prevents overfitting by testing on data the strategy hasn't seen.
"""

import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# Add trading-engine to path
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "trading-engine"))

from app.backtesting.strategy_base import OHLCV
from app.backtesting.backtest_engine import BacktestEngine, BacktestConfig, BacktestResult
from app.strategies.grid_trading_strategy import GridTradingStrategy

# Declared account size (see shared/account.py).
import os as _os
import sys as _sys

_REPO_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))
if _REPO_ROOT not in _sys.path:
    _sys.path.insert(0, _REPO_ROOT)
from shared.account import ACCOUNT_EQUITY_USD  # noqa: E402



# Configuration constants
DATA_DIR = Path(__file__).parent.parent / "data" / "historical"

# Test on best-performing symbols
WALKFORWARD_SYMBOLS = ["SOLUSDT", "LTCUSDT", "BNBUSDT"]

# Window configuration
IN_SAMPLE_DAYS = 120  # Train/optimize on 120 days
OUT_SAMPLE_DAYS = 60  # Test on next 60 days
STEP_DAYS = 30        # Move window forward 30 days each time


def load_csv_data(symbol: str) -> List[OHLCV]:
    """Load historical data from CSV file"""
    csv_files = list(DATA_DIR.glob(f"{symbol}_180days_*.csv"))

    if not csv_files:
        raise FileNotFoundError(f"No CSV file found for {symbol} in {DATA_DIR}")

    csv_file = csv_files[0]
    df = pd.read_csv(csv_file)

    # Convert to OHLCV objects
    bars = []
    for _, row in df.iterrows():
        bar = OHLCV(
            timestamp=pd.to_datetime(row['timestamp']),
            open=float(row['open']),
            high=float(row['high']),
            low=float(row['low']),
            close=float(row['close']),
            volume=float(row['volume'])
        )
        bars.append(bar)

    return bars


def split_data_by_window(
    bars: List[OHLCV],
    in_sample_days: int,
    out_sample_days: int,
    step_days: int
) -> List[Dict[str, Any]]:
    """
    Split data into overlapping in-sample and out-of-sample windows

    Returns:
        List of {in_sample: bars, out_sample: bars, window_num: int} dicts
    """
    if not bars:
        return []

    # Calculate hours (assuming hourly data)
    in_sample_hours = in_sample_days * 24
    out_sample_hours = out_sample_days * 24
    step_hours = step_days * 24

    windows = []
    window_num = 0
    start_idx = 0

    while True:
        # In-sample period
        in_end_idx = start_idx + in_sample_hours
        if in_end_idx >= len(bars):
            break

        # Out-of-sample period
        out_end_idx = in_end_idx + out_sample_hours
        if out_end_idx > len(bars):
            break

        windows.append({
            "window_num": window_num,
            "in_sample": bars[start_idx:in_end_idx],
            "out_sample": bars[in_end_idx:out_end_idx],
            "in_start": bars[start_idx].timestamp,
            "in_end": bars[in_end_idx-1].timestamp,
            "out_start": bars[in_end_idx].timestamp,
            "out_end": bars[out_end_idx-1].timestamp,
        })

        window_num += 1
        start_idx += step_hours

    return windows


def optimize_on_window(
    symbol: str,
    in_sample_bars: List[OHLCV],
    param_grid: Dict[str, List[Any]]
) -> Dict[str, Any]:
    """
    Optimize parameters on in-sample data

    Returns best parameters based on Sharpe ratio
    """
    from itertools import product

    param_names = list(param_grid.keys())
    param_values = [param_grid[name] for name in param_names]
    all_combinations = list(product(*param_values))

    best_params = None
    best_sharpe = -999

    for combo in all_combinations:
        params = dict(zip(param_names, combo))

        try:
            # Create strategy
            strategy = GridTradingStrategy(
                symbol=symbol,
                grid_levels=params["grid_levels"],
                grid_range_pct=params["grid_range_pct"],
                use_atr_spacing=params["use_atr_spacing"],
                max_positions=params["max_positions"],
                position_size_pct=params["position_size_pct"],
            )

            # Create backtest config
            backtest_config = BacktestConfig(
                initial_equity=ACCOUNT_EQUITY_USD,
                commission_pct=0.1,
                slippage_pct=0.05,
                max_positions=params["max_positions"],
            )

            # Run backtest on in-sample data
            engine = BacktestEngine(backtest_config)
            result = engine.run(strategy, in_sample_bars)

            # Track best Sharpe ratio
            if result.metrics.sharpe_ratio > best_sharpe:
                best_sharpe = result.metrics.sharpe_ratio
                best_params = params

        except Exception as e:
            continue

    return best_params if best_params else param_grid


def test_on_window(
    symbol: str,
    out_sample_bars: List[OHLCV],
    params: Dict[str, Any]
) -> BacktestResult:
    """Test optimized parameters on out-of-sample data"""

    # Create strategy with optimized parameters
    strategy = GridTradingStrategy(
        symbol=symbol,
        grid_levels=params["grid_levels"],
        grid_range_pct=params["grid_range_pct"],
        use_atr_spacing=params["use_atr_spacing"],
        max_positions=params["max_positions"],
        position_size_pct=params["position_size_pct"],
    )

    # Create backtest config
    backtest_config = BacktestConfig(
        initial_equity=ACCOUNT_EQUITY_USD,
        commission_pct=0.1,
        slippage_pct=0.05,
        max_positions=params["max_positions"],
    )

    # Run backtest on out-of-sample data
    engine = BacktestEngine(backtest_config)
    result = engine.run(strategy, out_sample_bars)

    return result


def run_walkforward_validation():
    """Run walk-forward validation"""

    print("="*80)
    print("GRID TRADING WALK-FORWARD VALIDATION")
    print("="*80)
    print(f"\nConfiguration:")
    print(f"  In-sample period: {IN_SAMPLE_DAYS} days")
    print(f"  Out-of-sample period: {OUT_SAMPLE_DAYS} days")
    print(f"  Step size: {STEP_DAYS} days")
    print(f"  Symbols: {', '.join(WALKFORWARD_SYMBOLS)}")
    print(f"\nStarting validation...\n")

    # Simplified parameter grid for walk-forward
    param_grid = {
        "grid_levels": [7, 10, 15],
        "grid_range_pct": [0.05, 0.10, 0.15],
        "position_size_pct": [0.015, 0.02],
        "max_positions": [3, 5],
        "use_atr_spacing": [True, False],
    }

    # Store all results
    all_results = []

    # Test each symbol
    for symbol in WALKFORWARD_SYMBOLS:
        print(f"\n{'='*80}")
        print(f"Testing Symbol: {symbol}")
        print(f"{'='*80}\n")

        try:
            # Load data
            bars = load_csv_data(symbol)
            print(f"Loaded {len(bars)} bars from {bars[0].timestamp} to {bars[-1].timestamp}")

            # Split into windows
            windows = split_data_by_window(bars, IN_SAMPLE_DAYS, OUT_SAMPLE_DAYS, STEP_DAYS)
            print(f"Created {len(windows)} walk-forward windows\n")

            if not windows:
                print(f"  ⚠️  Insufficient data for walk-forward windows")
                continue

            # Process each window
            for window in windows:
                print(f"Window {window['window_num'] + 1}/{len(windows)}:")
                print(f"  In-sample:  {window['in_start']} to {window['in_end']} ({len(window['in_sample'])} bars)")
                print(f"  Out-sample: {window['out_start']} to {window['out_end']} ({len(window['out_sample'])} bars)")

                # Optimize on in-sample
                print(f"  Optimizing parameters on in-sample data...")
                best_params = optimize_on_window(symbol, window['in_sample'], param_grid)

                # Test on out-of-sample
                print(f"  Testing on out-of-sample data...")
                out_result = test_on_window(symbol, window['out_sample'], best_params)

                # Store result
                result_data = {
                    "symbol": symbol,
                    "window_num": window['window_num'],
                    "in_start": window['in_start'],
                    "in_end": window['in_end'],
                    "out_start": window['out_start'],
                    "out_end": window['out_end'],
                    "params": best_params,
                    "out_return": out_result.metrics.total_return_pct,
                    "out_sharpe": out_result.metrics.sharpe_ratio,
                    "out_winrate": out_result.metrics.win_rate,
                    "out_trades": out_result.metrics.total_trades,
                    "out_max_dd": out_result.metrics.max_drawdown_pct,
                }

                all_results.append(result_data)

                # Print window result
                print(f"  Out-of-sample performance:")
                print(f"    Return: {out_result.metrics.total_return_pct:+.2f}%")
                print(f"    Sharpe: {out_result.metrics.sharpe_ratio:+.2f}")
                print(f"    Win Rate: {out_result.metrics.win_rate:.1f}%")
                print(f"    Trades: {out_result.metrics.total_trades}")
                print()

        except Exception as e:
            print(f"  ❌ Error testing {symbol}: {e}")
            import traceback
            traceback.print_exc()
            continue

    # Summary
    print(f"\n{'='*80}")
    print("WALK-FORWARD VALIDATION SUMMARY")
    print(f"={'='*80}\n")

    if not all_results:
        print("❌ No results to summarize")
        return

    # Group by symbol
    for symbol in WALKFORWARD_SYMBOLS:
        symbol_results = [r for r in all_results if r["symbol"] == symbol]

        if not symbol_results:
            continue

        print(f"\n{symbol}:")
        print(f"  {'Window':<8} {'Out-Sample Period':<50} {'Return':>10} {'Sharpe':>8} {'WinRate':>10}")
        print(f"  {'-'*90}")

        for result in symbol_results:
            period_str = f"{result['out_start'].strftime('%Y-%m-%d')} to {result['out_end'].strftime('%Y-%m-%d')}"
            print(f"  {result['window_num']+1:<8} {period_str:<50} "
                  f"{result['out_return']:>+9.2f}% "
                  f"{result['out_sharpe']:>+7.2f} "
                  f"{result['out_winrate']:>9.1f}%")

        # Calculate average out-of-sample performance
        avg_return = np.mean([r['out_return'] for r in symbol_results])
        avg_sharpe = np.mean([r['out_sharpe'] for r in symbol_results])
        avg_winrate = np.mean([r['out_winrate'] for r in symbol_results])

        print(f"  {'-'*90}")
        print(f"  {'AVERAGE':<8} {'':<50} "
              f"{avg_return:>+9.2f}% "
              f"{avg_sharpe:>+7.2f} "
              f"{avg_winrate:>9.1f}%")

    # Overall statistics
    print(f"\n{'='*80}")
    print("OVERALL WALK-FORWARD STATISTICS")
    print(f"{'='*80}\n")

    all_returns = [r['out_return'] for r in all_results]
    all_sharpes = [r['out_sharpe'] for r in all_results]
    all_winrates = [r['out_winrate'] for r in all_results]

    print(f"Total windows tested: {len(all_results)}")
    print(f"\nOut-of-Sample Performance:")
    print(f"  Average Return: {np.mean(all_returns):+.2f}%")
    print(f"  Return Std Dev: {np.std(all_returns):.2f}%")
    print(f"  Average Sharpe: {np.mean(all_sharpes):+.2f}")
    print(f"  Average Win Rate: {np.mean(all_winrates):.1f}%")
    print(f"  Positive windows: {sum(1 for r in all_returns if r > 0)}/{len(all_returns)} ({100*sum(1 for r in all_returns if r > 0)/len(all_returns):.1f}%)")

    print(f"\n✅ Walk-forward validation complete!")


if __name__ == "__main__":
    run_walkforward_validation()
