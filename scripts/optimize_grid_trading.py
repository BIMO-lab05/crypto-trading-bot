#!/usr/bin/env python3
"""
Grid Trading Parameter Optimization
Systematic parameter search to find optimal Grid Trading configuration.

Optimizes:
- Grid levels (5, 7, 10, 15, 20)
- Grid range % (5%, 10%, 15%, 20%)
- Position size % (1%, 1.5%, 2%, 2.5%)
- Max positions (3, 5, 7)
- ATR spacing (True/False)

Target metrics: Sharpe ratio, Total Return, Win Rate
"""

import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Tuple
from datetime import datetime
import pandas as pd
import numpy as np
from itertools import product

# Add trading-engine to path
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "trading-engine"))
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.account import ACCOUNT_EQUITY_USD  # noqa: E402

from app.backtesting.strategy_base import OHLCV
from app.backtesting.backtest_engine import BacktestEngine, BacktestConfig, BacktestResult
from app.strategies.grid_trading_strategy import GridTradingStrategy


# Configuration constants
DATA_DIR = Path(__file__).parent.parent / "data" / "historical"

# Focus on best-performing symbols from comprehensive backtest
OPTIMIZATION_SYMBOLS = ["SOLUSDT", "LTCUSDT", "BNBUSDT"]

# Parameter search space (reduced for faster optimization)
PARAM_GRID = {
    "grid_levels": [7, 10, 15],
    "grid_range_pct": [0.05, 0.10, 0.15],
    "position_size_pct": [0.015, 0.02, 0.025],
    "max_positions": [3, 5],
    "use_atr_spacing": [True, False],
}


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


def run_optimization_backtest(
    symbol: str,
    bars: List[OHLCV],
    params: Dict[str, Any],
    initial_equity: float = ACCOUNT_EQUITY_USD
) -> Tuple[BacktestResult, Dict[str, Any]]:
    """Run single backtest with given parameters"""

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
        initial_equity=initial_equity,
        commission_pct=0.1,  # 0.1% commission
        slippage_pct=0.05,   # 0.05% slippage
        max_positions=params["max_positions"],
    )

    # Run backtest
    engine = BacktestEngine(backtest_config)
    result = engine.run(strategy, bars)

    return result, params


def calculate_optimization_score(result: BacktestResult) -> float:
    """
    Calculate composite optimization score

    Weights:
    - Sharpe ratio: 40%
    - Total return: 30%
    - Win rate: 20%
    - Profit factor: 10%
    """
    metrics = result.metrics

    # Normalize metrics (0-100 scale)
    sharpe_score = min(max(metrics.sharpe_ratio * 20, 0), 100)  # -5 to +5 → 0 to 100
    return_score = min(max(metrics.total_return_pct, -50), 50) + 50  # -50% to +50% → 0 to 100
    winrate_score = metrics.win_rate  # Already 0-100
    pf_score = min(max((metrics.profit_factor - 0.5) * 33.33, 0), 100)  # 0.5 to 3.5 → 0 to 100

    # Weighted composite score
    score = (
        sharpe_score * 0.40 +
        return_score * 0.30 +
        winrate_score * 0.20 +
        pf_score * 0.10
    )

    return score


def optimize_grid_trading():
    """Run parameter optimization"""

    print("="*80)
    print("GRID TRADING PARAMETER OPTIMIZATION")
    print("="*80)
    print(f"\nOptimization symbols: {', '.join(OPTIMIZATION_SYMBOLS)}")
    print(f"Parameter space size: {np.prod([len(v) for v in PARAM_GRID.values()])} combinations")
    print(f"\nStarting optimization...\n")

    # Load data for all symbols
    symbol_data = {}
    for symbol in OPTIMIZATION_SYMBOLS:
        try:
            bars = load_csv_data(symbol)
            symbol_data[symbol] = bars
            print(f"✓ Loaded {len(bars)} bars for {symbol}")
        except Exception as e:
            print(f"✗ Error loading {symbol}: {e}")
            continue

    if not symbol_data:
        print("\n❌ No data loaded. Exiting.")
        return

    print(f"\n{'='*80}")
    print("TESTING PARAMETER COMBINATIONS")
    print(f"{'='*80}\n")

    # Generate all parameter combinations
    param_names = list(PARAM_GRID.keys())
    param_values = [PARAM_GRID[name] for name in param_names]
    all_combinations = list(product(*param_values))

    print(f"Total combinations to test: {len(all_combinations)}")
    print(f"Total backtests: {len(all_combinations) * len(symbol_data)}\n")

    # Store results
    all_results = []

    # Test each combination
    for combo_idx, combo in enumerate(all_combinations, 1):
        # Create parameter dict
        params = dict(zip(param_names, combo))

        # Compact parameter description
        param_desc = (
            f"L{params['grid_levels']} "
            f"R{params['grid_range_pct']*100:.0f}% "
            f"P{params['position_size_pct']*100:.1f}% "
            f"M{params['max_positions']} "
            f"{'ATR' if params['use_atr_spacing'] else 'FIX'}"
        )

        # Track aggregate metrics
        combo_scores = []
        combo_returns = []
        combo_sharpes = []
        combo_winrates = []

        # Test on each symbol
        for symbol, bars in symbol_data.items():
            try:
                result, used_params = run_optimization_backtest(symbol, bars, params)

                # Calculate optimization score
                score = calculate_optimization_score(result)

                combo_scores.append(score)
                combo_returns.append(result.metrics.total_return_pct)
                combo_sharpes.append(result.metrics.sharpe_ratio)
                combo_winrates.append(result.metrics.win_rate)

                # Store individual result
                all_results.append({
                    "combo_idx": combo_idx,
                    "symbol": symbol,
                    "params": params,
                    "param_desc": param_desc,
                    "score": score,
                    "total_return": result.metrics.total_return_pct,
                    "sharpe": result.metrics.sharpe_ratio,
                    "win_rate": result.metrics.win_rate,
                    "profit_factor": result.metrics.profit_factor,
                    "total_trades": result.metrics.total_trades,
                    "max_drawdown": result.metrics.max_drawdown_pct,
                })

            except Exception as e:
                print(f"  ✗ Error: {symbol} - {e}")
                continue

        # Print combo summary
        if combo_scores:
            avg_score = np.mean(combo_scores)
            avg_return = np.mean(combo_returns)
            avg_sharpe = np.mean(combo_sharpes)
            avg_winrate = np.mean(combo_winrates)

            print(f"[{combo_idx:3d}/{len(all_combinations)}] {param_desc:<25} | "
                  f"Score: {avg_score:5.1f} | Return: {avg_return:+6.2f}% | "
                  f"Sharpe: {avg_sharpe:+5.2f} | WinRate: {avg_winrate:5.1f}%")

    # Find best configurations
    print(f"\n{'='*80}")
    print("OPTIMIZATION RESULTS")
    print(f"{'='*80}\n")

    # Group by combination and calculate average scores
    combo_results = {}
    for result in all_results:
        combo_idx = result["combo_idx"]
        if combo_idx not in combo_results:
            combo_results[combo_idx] = {
                "param_desc": result["param_desc"],
                "params": result["params"],
                "scores": [],
                "returns": [],
                "sharpes": [],
                "winrates": [],
            }
        combo_results[combo_idx]["scores"].append(result["score"])
        combo_results[combo_idx]["returns"].append(result["total_return"])
        combo_results[combo_idx]["sharpes"].append(result["sharpe"])
        combo_results[combo_idx]["winrates"].append(result["win_rate"])

    # Calculate averages and sort by score
    ranked_combos = []
    for combo_idx, data in combo_results.items():
        ranked_combos.append({
            "combo_idx": combo_idx,
            "param_desc": data["param_desc"],
            "params": data["params"],
            "avg_score": np.mean(data["scores"]),
            "avg_return": np.mean(data["returns"]),
            "avg_sharpe": np.mean(data["sharpes"]),
            "avg_winrate": np.mean(data["winrates"]),
            "std_return": np.std(data["returns"]),
        })

    ranked_combos.sort(key=lambda x: x["avg_score"], reverse=True)

    # Print top 10
    print("TOP 10 CONFIGURATIONS (by composite score):\n")
    print(f"{'Rank':<6} {'Parameters':<30} {'Score':>8} {'Return':>10} {'Sharpe':>8} {'WinRate':>10}")
    print("-" * 80)

    for rank, combo in enumerate(ranked_combos[:10], 1):
        print(f"{rank:<6} {combo['param_desc']:<30} "
              f"{combo['avg_score']:>8.1f} "
              f"{combo['avg_return']:>+9.2f}% "
              f"{combo['avg_sharpe']:>+7.2f} "
              f"{combo['avg_winrate']:>9.1f}%")

    # Print best configuration details
    best_combo = ranked_combos[0]
    print(f"\n{'='*80}")
    print("BEST CONFIGURATION DETAILS")
    print(f"{'='*80}\n")
    print(f"Parameters: {best_combo['param_desc']}")
    print(f"  Grid Levels: {best_combo['params']['grid_levels']}")
    print(f"  Grid Range: {best_combo['params']['grid_range_pct']*100:.0f}%")
    print(f"  Position Size: {best_combo['params']['position_size_pct']*100:.1f}%")
    print(f"  Max Positions: {best_combo['params']['max_positions']}")
    print(f"  ATR Spacing: {best_combo['params']['use_atr_spacing']}")
    print(f"\nPerformance:")
    print(f"  Composite Score: {best_combo['avg_score']:.1f}/100")
    print(f"  Average Return: {best_combo['avg_return']:+.2f}%")
    print(f"  Average Sharpe: {best_combo['avg_sharpe']:+.2f}")
    print(f"  Average Win Rate: {best_combo['avg_winrate']:.1f}%")
    print(f"  Return Std Dev: {best_combo['std_return']:.2f}%")

    # Print per-symbol breakdown for best config
    print(f"\nPer-Symbol Performance (Best Configuration):\n")
    print(f"{'Symbol':<12} {'Return':>10} {'Sharpe':>8} {'WinRate':>10} {'Trades':>8}")
    print("-" * 55)

    best_idx = best_combo["combo_idx"]
    best_results = [r for r in all_results if r["combo_idx"] == best_idx]
    for result in best_results:
        print(f"{result['symbol']:<12} "
              f"{result['total_return']:>+9.2f}% "
              f"{result['sharpe']:>+7.2f} "
              f"{result['win_rate']:>9.1f}% "
              f"{result['total_trades']:>8d}")

    print(f"\n✅ Optimization complete!")
    print(f"   Tested {len(all_combinations)} parameter combinations")
    print(f"   Ran {len(all_results)} total backtests")
    print(f"   Best configuration: {best_combo['param_desc']}")


if __name__ == "__main__":
    optimize_grid_trading()
