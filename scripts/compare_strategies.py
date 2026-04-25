#!/usr/bin/env python3
"""
Strategy Comparison Script
Compares Grid Trading against Statistical Arbitrage and Mean Reversion strategies.

Tests all strategies on same symbols and data for fair comparison.
Metrics: Return, Sharpe, Win Rate, Max DD, Profit Factor
"""

import sys
import os
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
import pandas as pd
import numpy as np

# Add trading-engine to path
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "trading-engine"))

from app.backtesting.strategy_base import OHLCV
from app.backtesting.backtest_engine import BacktestEngine, BacktestConfig, BacktestResult
from app.strategies.grid_trading_strategy import GridTradingStrategy
from app.strategies.statistical_arbitrage_strategy import StatisticalArbitrageStrategy
from app.strategies.mean_reversion_strategy import MeanReversionStrategy


# Configuration constants
DATA_DIR = Path(__file__).parent.parent / "data" / "historical"

# Test on best-performing symbols
COMPARISON_SYMBOLS = ["SOLUSDT", "LTCUSDT", "BNBUSDT"]

# Strategy configurations
GRID_TRADING_CONFIG = {
    "name": "Grid Trading (Optimized)",
    "grid_levels": 7,
    "grid_range_pct": 0.15,
    "use_atr_spacing": False,
    "max_positions": 3,
    "position_size_pct": 0.015,
}

STAT_ARB_CONFIG = {
    "name": "Statistical Arbitrage",
    "lookback_period": 20,
    "entry_threshold": 2.0,
    "exit_threshold": 0.5,
    "max_positions": 5,
    "position_size_pct": 0.02,
}

MEAN_REVERSION_CONFIG = {
    "name": "Mean Reversion",
    "lookback_period": 20,
    "entry_std": 2.0,
    "exit_std": 0.5,
    "max_positions": 5,
    "position_size_pct": 0.02,
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


def run_grid_trading(symbol: str, bars: List[OHLCV]) -> BacktestResult:
    """Run Grid Trading backtest"""
    strategy = GridTradingStrategy(
        symbol=symbol,
        grid_levels=GRID_TRADING_CONFIG["grid_levels"],
        grid_range_pct=GRID_TRADING_CONFIG["grid_range_pct"],
        use_atr_spacing=GRID_TRADING_CONFIG["use_atr_spacing"],
        max_positions=GRID_TRADING_CONFIG["max_positions"],
        position_size_pct=GRID_TRADING_CONFIG["position_size_pct"],
    )

    backtest_config = BacktestConfig(
        initial_equity=10000.0,
        commission_pct=0.1,
        slippage_pct=0.05,
        max_positions=GRID_TRADING_CONFIG["max_positions"],
    )

    engine = BacktestEngine(backtest_config)
    result = engine.run(strategy, bars)

    return result


def run_stat_arb(symbol: str, bars: List[OHLCV]) -> BacktestResult:
    """Run Statistical Arbitrage backtest"""
    strategy = StatisticalArbitrageStrategy(
        symbol=symbol,
        lookback_period=STAT_ARB_CONFIG["lookback_period"],
        entry_threshold=STAT_ARB_CONFIG["entry_threshold"],
        exit_threshold=STAT_ARB_CONFIG["exit_threshold"],
        max_positions=STAT_ARB_CONFIG["max_positions"],
        position_size_pct=STAT_ARB_CONFIG["position_size_pct"],
    )

    backtest_config = BacktestConfig(
        initial_equity=10000.0,
        commission_pct=0.1,
        slippage_pct=0.05,
        max_positions=STAT_ARB_CONFIG["max_positions"],
    )

    engine = BacktestEngine(backtest_config)
    result = engine.run(strategy, bars)

    return result


def run_mean_reversion(symbol: str, bars: List[OHLCV]) -> BacktestResult:
    """Run Mean Reversion backtest"""
    strategy = MeanReversionStrategy(
        symbol=symbol,
        lookback_period=MEAN_REVERSION_CONFIG["lookback_period"],
        entry_std=MEAN_REVERSION_CONFIG["entry_std"],
        exit_std=MEAN_REVERSION_CONFIG["exit_std"],
        max_positions=MEAN_REVERSION_CONFIG["max_positions"],
        position_size_pct=MEAN_REVERSION_CONFIG["position_size_pct"],
    )

    backtest_config = BacktestConfig(
        initial_equity=10000.0,
        commission_pct=0.1,
        slippage_pct=0.05,
        max_positions=MEAN_REVERSION_CONFIG["max_positions"],
    )

    engine = BacktestEngine(backtest_config)
    result = engine.run(strategy, bars)

    return result


def compare_strategies():
    """Run comprehensive strategy comparison"""

    print("="*80)
    print("STRATEGY COMPARISON - GRID TRADING VS ALTERNATIVES")
    print("="*80)
    print(f"\nSymbols: {', '.join(COMPARISON_SYMBOLS)}")
    print(f"Strategies: 3 (Grid Trading, Stat Arb, Mean Reversion)")
    print(f"\nStarting comparison...\n")

    # Store all results
    all_results = []

    # Test each symbol
    for symbol in COMPARISON_SYMBOLS:
        print(f"\n{'='*80}")
        print(f"Testing Symbol: {symbol}")
        print(f"{'='*80}\n")

        try:
            # Load data
            bars = load_csv_data(symbol)
            print(f"Loaded {len(bars)} bars from {bars[0].timestamp} to {bars[-1].timestamp}")

            # Test Grid Trading
            print(f"\nTesting Grid Trading...")
            grid_result = run_grid_trading(symbol, bars)
            all_results.append({
                "symbol": symbol,
                "strategy": "Grid Trading",
                "result": grid_result,
            })
            print(f"  Return: {grid_result.metrics.total_return_pct:+.2f}%")
            print(f"  Sharpe: {grid_result.metrics.sharpe_ratio:+.2f}")
            print(f"  Win Rate: {grid_result.metrics.win_rate:.1f}%")

            # Test Statistical Arbitrage
            print(f"\nTesting Statistical Arbitrage...")
            stat_arb_result = run_stat_arb(symbol, bars)
            all_results.append({
                "symbol": symbol,
                "strategy": "Stat Arb",
                "result": stat_arb_result,
            })
            print(f"  Return: {stat_arb_result.metrics.total_return_pct:+.2f}%")
            print(f"  Sharpe: {stat_arb_result.metrics.sharpe_ratio:+.2f}")
            print(f"  Win Rate: {stat_arb_result.metrics.win_rate:.1f}%")

            # Test Mean Reversion
            print(f"\nTesting Mean Reversion...")
            mean_rev_result = run_mean_reversion(symbol, bars)
            all_results.append({
                "symbol": symbol,
                "strategy": "Mean Reversion",
                "result": mean_rev_result,
            })
            print(f"  Return: {mean_rev_result.metrics.total_return_pct:+.2f}%")
            print(f"  Sharpe: {mean_rev_result.metrics.sharpe_ratio:+.2f}")
            print(f"  Win Rate: {mean_rev_result.metrics.win_rate:.1f}%")

        except Exception as e:
            print(f"  ❌ Error testing {symbol}: {e}")
            import traceback
            traceback.print_exc()
            continue

    # Comparative Summary
    print(f"\n\n{'='*80}")
    print("STRATEGY COMPARISON SUMMARY")
    print(f"{'='*80}\n")

    # Create comparison table
    strategies = ["Grid Trading", "Stat Arb", "Mean Reversion"]

    for strategy in strategies:
        strategy_results = [r for r in all_results if r["strategy"] == strategy]

        if not strategy_results:
            continue

        print(f"\n{strategy}:")
        print(f"  {'Symbol':<12} {'Return %':>10} {'Sharpe':>8} {'Win Rate':>10} {'Trades':>8} {'Max DD':>10}")
        print(f"  {'-'*70}")

        for res in strategy_results:
            metrics = res['result'].metrics

            print(f"  {res['symbol']:<12} "
                  f"{metrics.total_return_pct:>+9.2f}% "
                  f"{metrics.sharpe_ratio:>+7.2f} "
                  f"{metrics.win_rate:>9.1f}% "
                  f"{metrics.total_trades:>8d} "
                  f"{metrics.max_drawdown_pct:>9.2f}%")

        # Calculate averages
        avg_return = np.mean([r['result'].metrics.total_return_pct for r in strategy_results])
        avg_sharpe = np.mean([r['result'].metrics.sharpe_ratio for r in strategy_results])
        avg_winrate = np.mean([r['result'].metrics.win_rate for r in strategy_results])
        avg_trades = np.mean([r['result'].metrics.total_trades for r in strategy_results])
        avg_max_dd = np.mean([r['result'].metrics.max_drawdown_pct for r in strategy_results])

        print(f"  {'-'*70}")
        print(f"  {'AVERAGE':<12} "
              f"{avg_return:>+9.2f}% "
              f"{avg_sharpe:>+7.2f} "
              f"{avg_winrate:>9.1f}% "
              f"{avg_trades:>8.0f} "
              f"{avg_max_dd:>9.2f}%")

    # Head-to-Head Ranking
    print(f"\n\n{'='*80}")
    print("HEAD-TO-HEAD RANKING (by Average Return)")
    print(f"{'='*80}\n")

    # Calculate average metrics per strategy
    strategy_rankings = []
    for strategy in strategies:
        strategy_results = [r for r in all_results if r["strategy"] == strategy]

        if strategy_results:
            avg_return = np.mean([r['result'].metrics.total_return_pct for r in strategy_results])
            avg_sharpe = np.mean([r['result'].metrics.sharpe_ratio for r in strategy_results])
            avg_winrate = np.mean([r['result'].metrics.win_rate for r in strategy_results])

            strategy_rankings.append({
                "strategy": strategy,
                "avg_return": avg_return,
                "avg_sharpe": avg_sharpe,
                "avg_winrate": avg_winrate,
            })

    # Sort by return
    strategy_rankings.sort(key=lambda x: x["avg_return"], reverse=True)

    print(f"{'Rank':<6} {'Strategy':<25} {'Avg Return':>12} {'Avg Sharpe':>12} {'Avg WinRate':>12}")
    print("-" * 80)

    for rank, strat in enumerate(strategy_rankings, 1):
        print(f"{rank:<6} {strat['strategy']:<25} "
              f"{strat['avg_return']:>+11.2f}% "
              f"{strat['avg_sharpe']:>+11.2f} "
              f"{strat['avg_winrate']:>11.1f}%")

    # Winner announcement
    print(f"\n{'='*80}")
    print("WINNER")
    print(f"{'='*80}\n")

    winner = strategy_rankings[0]
    print(f"🏆 {winner['strategy']} wins with:")
    print(f"   Average Return: {winner['avg_return']:+.2f}%")
    print(f"   Average Sharpe: {winner['avg_sharpe']:+.2f}")
    print(f"   Average Win Rate: {winner['avg_winrate']:.1f}%")

    print(f"\n✅ Strategy comparison complete!")
    print(f"   Total tests run: {len(all_results)}")
    print(f"   Symbols tested: {len(COMPARISON_SYMBOLS)}")
    print(f"   Strategies compared: {len(strategies)}")


if __name__ == "__main__":
    compare_strategies()
