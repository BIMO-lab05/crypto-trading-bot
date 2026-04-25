#!/usr/bin/env python3
"""
Comprehensive Strategy Comparison
Created: 2025-12-06
Purpose: Compare all implemented strategies on same dataset

Strategies Tested:
1. Simple RSI (baseline trend-following)
2. Multi-Indicator Strict (4 confirmations)
3. Multi-Indicator Moderate (2 confirmations)
4. Mean Reversion (BB bounces)
5. Mean Reversion Aggressive (no RSI confirmation)

This provides definitive answer on which approach works best for current market.
"""

import sys
import os
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np
from datetime import datetime
import logging

from backtesting.backtest_engine import BacktestEngine
from backtesting.strategies.multi_indicator_strategy import create_multi_indicator_strategy
from backtesting.strategies.mean_reversion_strategy import create_mean_reversion_strategy

logging.basicConfig(level=logging.WARNING, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def calculate_rsi_simple(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """Simple RSI for baseline strategy"""
    close = data['close']
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def create_simple_rsi_strategy(rsi_period: int = 14, oversold: int = 30, overbought: int = 70):
    """Simple RSI baseline strategy"""
    def strategy_func(row, position, idx, data):
        if idx < rsi_period:
            return None

        if isinstance(data.index, pd.DatetimeIndex):
            data_for_calc = data.reset_index(drop=True).iloc[:idx+1]
        else:
            data_for_calc = data.iloc[:idx+1]

        rsi_values = calculate_rsi_simple(data_for_calc, period=rsi_period)
        current_rsi = rsi_values.iloc[-1]

        if pd.isna(current_rsi):
            return None

        if position is None:
            if current_rsi < oversold:
                return {'action': 'BUY', 'stop_loss_pct': 2.0, 'take_profit_pct': 4.0}
            elif current_rsi > overbought:
                return {'action': 'SELL', 'stop_loss_pct': 2.0, 'take_profit_pct': 4.0}
        else:
            if position.order_type.value == 'BUY' and current_rsi > overbought:
                return {'action': 'HOLD'}
            elif position.order_type.value == 'SELL' and current_rsi < oversold:
                return {'action': 'HOLD'}

        return None

    return strategy_func


def main():
    """Run comprehensive strategy comparison"""
    print("\n" + "="*100)
    print("COMPREHENSIVE STRATEGY COMPARISON - PHASE 2 FINAL ANALYSIS")
    print("="*100)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*100 + "\n")

    # Load test data
    data_path = project_root / 'backtesting' / 'data' / 'BNBUSDT_60m_90d_bybit.csv'
    data = pd.read_csv(data_path)
    data['timestamp'] = pd.to_datetime(data['timestamp'])
    data = data.set_index('timestamp').sort_index()

    print(f"Testing on BNBUSDT:")
    print(f"  Period: {data.index[0]} to {data.index[-1]}")
    print(f"  Candles: {len(data):,}")
    print(f"  Price range: ${data['close'].min():.2f} - ${data['close'].max():.2f}")
    print()

    # Define all strategies to test
    strategies = [
        {
            'name': 'Simple RSI',
            'type': 'Trend Following',
            'func': create_simple_rsi_strategy(rsi_period=14, oversold=30, overbought=70),
            'description': 'Baseline: RSI(14) with 30/70 thresholds'
        },
        {
            'name': 'Multi-Indicator Strict',
            'type': 'Trend Following',
            'func': create_multi_indicator_strategy(require_all=True, min_confirmations=4),
            'description': 'RSI + MACD + BB + Volume (all 4 must agree)'
        },
        {
            'name': 'Multi-Indicator Moderate',
            'type': 'Trend Following',
            'func': create_multi_indicator_strategy(require_all=False, min_confirmations=2),
            'description': 'RSI + MACD + BB + Volume (2 of 4 must agree)'
        },
        {
            'name': 'Mean Reversion',
            'type': 'Mean Reversion',
            'func': create_mean_reversion_strategy(
                bb_period=20,
                bb_std=2.0,
                require_rsi=True,
                exit_at_mean=True,
                stop_loss_pct=1.5,
                take_profit_pct=2.0
            ),
            'description': 'BB(20,2) bounces with RSI confirmation, exit at mean'
        },
        {
            'name': 'Mean Reversion Aggressive',
            'type': 'Mean Reversion',
            'func': create_mean_reversion_strategy(
                bb_period=20,
                bb_std=2.0,
                require_rsi=False,
                exit_at_mean=True,
                stop_loss_pct=1.5,
                take_profit_pct=2.0
            ),
            'description': 'BB(20,2) bounces without RSI, exit at mean'
        },
        {
            'name': 'Mean Reversion Tight',
            'type': 'Mean Reversion',
            'func': create_mean_reversion_strategy(
                bb_period=15,
                bb_std=1.5,
                require_rsi=True,
                exit_at_mean=True,
                stop_loss_pct=1.0,
                take_profit_pct=1.5
            ),
            'description': 'Tighter BB(15,1.5), smaller targets'
        },
        {
            'name': 'Mean Reversion Wide',
            'type': 'Mean Reversion',
            'func': create_mean_reversion_strategy(
                bb_period=25,
                bb_std=2.5,
                require_rsi=True,
                exit_at_mean=True,
                stop_loss_pct=2.0,
                take_profit_pct=3.0
            ),
            'description': 'Wider BB(25,2.5), larger targets'
        },
    ]

    results = []

    for i, strategy in enumerate(strategies, 1):
        print(f"\n[{i}/{len(strategies)}] Testing: {strategy['name']}")
        print(f"    Type: {strategy['type']}")
        print(f"    Config: {strategy['description']}")

        engine = BacktestEngine(initial_capital=10000.0, commission=0.001, slippage=0.0005)
        result = engine.run_backtest(data, strategy['func'], strategy['name'])

        results.append({
            'name': strategy['name'],
            'type': strategy['type'],
            'description': strategy['description'],
            'result': result
        })

        # Show quick summary
        print(f"    ✓ Return: {result.total_profit_loss_pct:>7.2f}% | Sharpe: {result.sharpe_ratio:>6.2f} | "
              f"Trades: {result.total_trades:>3d} | Win Rate: {result.win_rate:>5.1f}%")

    # Detailed comparison table
    print("\n" + "="*100)
    print("DETAILED COMPARISON")
    print("="*100)
    print(f"{'Strategy':<30} {'Type':<18} {'Return':<10} {'Sharpe':<8} {'Trades':<8} {'Win %':<8} {'Profit Factor':<10}")
    print("-"*100)

    for r in results:
        res = r['result']
        print(f"{r['name']:<30} {r['type']:<18} "
              f"{res.total_profit_loss_pct:>8.2f}% "
              f"{res.sharpe_ratio:>7.2f} "
              f"{res.total_trades:>7d} "
              f"{res.win_rate:>7.1f} "
              f"{res.profit_factor:>9.2f}")

    # Category analysis
    print("\n" + "="*100)
    print("CATEGORY ANALYSIS")
    print("="*100)

    trend_strategies = [r for r in results if r['type'] == 'Trend Following']
    mean_rev_strategies = [r for r in results if r['type'] == 'Mean Reversion']

    if trend_strategies:
        print("\n📈 TREND FOLLOWING STRATEGIES:")
        best_trend = max(trend_strategies, key=lambda x: x['result'].sharpe_ratio)
        avg_return = np.mean([r['result'].total_profit_loss_pct for r in trend_strategies])
        avg_sharpe = np.mean([r['result'].sharpe_ratio for r in trend_strategies])

        print(f"  Average Return: {avg_return:.2f}%")
        print(f"  Average Sharpe: {avg_sharpe:.2f}")
        print(f"  Best: {best_trend['name']} (Sharpe: {best_trend['result'].sharpe_ratio:.2f})")

    if mean_rev_strategies:
        print("\n📉 MEAN REVERSION STRATEGIES:")
        best_mr = max(mean_rev_strategies, key=lambda x: x['result'].sharpe_ratio)
        avg_return = np.mean([r['result'].total_profit_loss_pct for r in mean_rev_strategies])
        avg_sharpe = np.mean([r['result'].sharpe_ratio for r in mean_rev_strategies])

        print(f"  Average Return: {avg_return:.2f}%")
        print(f"  Average Sharpe: {avg_sharpe:.2f}")
        print(f"  Best: {best_mr['name']} (Sharpe: {best_mr['result'].sharpe_ratio:.2f})")

    # Overall winner
    print("\n" + "="*100)
    best_overall = max(results, key=lambda x: x['result'].sharpe_ratio)
    best_return = max(results, key=lambda x: x['result'].total_profit_loss_pct)
    most_trades = max(results, key=lambda x: x['result'].total_trades)
    best_win_rate = max(results, key=lambda x: x['result'].win_rate)

    print("🏆 WINNERS BY METRIC:")
    print(f"  Best Sharpe Ratio: {best_overall['name']} ({best_overall['result'].sharpe_ratio:.2f})")
    print(f"  Best Return: {best_return['name']} ({best_return['result'].total_profit_loss_pct:.2f}%)")
    print(f"  Highest Win Rate: {best_win_rate['name']} ({best_win_rate['result'].win_rate:.1f}%)")
    print(f"  Most Active: {most_trades['name']} ({most_trades['result'].total_trades} trades)")

    print("\n" + "="*100)
    print("📊 KEY INSIGHTS:")
    print("="*100)

    # Check if any strategy is actually profitable
    profitable = [r for r in results if r['result'].total_profit_loss_pct > 0]
    positive_sharpe = [r for r in results if r['result'].sharpe_ratio > 0]

    print(f"\n1. Profitability: {len(profitable)}/{len(results)} strategies showed positive returns")

    if profitable:
        print("   Profitable strategies:")
        for r in profitable:
            print(f"     - {r['name']}: +{r['result'].total_profit_loss_pct:.2f}% (Sharpe: {r['result'].sharpe_ratio:.2f})")
    else:
        print("   ⚠️  NO strategies were profitable on this dataset")

    print(f"\n2. Risk-Adjusted: {len(positive_sharpe)}/{len(results)} strategies had positive Sharpe ratio")

    if not positive_sharpe:
        print("   ⚠️  ALL strategies had negative Sharpe ratios")
        print("   This suggests the market period was unfavorable for these approaches")

    print(f"\n3. Trade Frequency:")
    trades = [r['result'].total_trades for r in results]
    print(f"   Range: {min(trades)} - {max(trades)} trades")
    print(f"   Average: {np.mean(trades):.0f} trades")

    print(f"\n4. Win Rates:")
    win_rates = [r['result'].win_rate for r in results]
    print(f"   Range: {min(win_rates):.1f}% - {max(win_rates):.1f}%")
    print(f"   Average: {np.mean(win_rates):.1f}%")

    print("\n" + "="*100)
    print("✅ COMPARISON COMPLETE")
    print("="*100)

    return 0


if __name__ == "__main__":
    sys.exit(main())
