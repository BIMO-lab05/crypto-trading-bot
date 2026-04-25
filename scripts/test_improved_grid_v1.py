#!/usr/bin/env python3
"""
Test Improved Grid Trading v1 Strategy
=======================================
Validates that adding ADX, RSI, and Volume filters improves win rate

Comparison:
- Original Grid Trading v1 (32.6% win rate baseline)
- Improved Grid Trading v1 (with ADX, RSI, Volume filters)

Target: Improve win rate from 32.6% toward 80% goal

Author: Grid Trading v1 Improvement Phase
Date: 2025-12-08
"""

import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services', 'trading-engine'))

from app.strategies.grid_trading_strategy import (
    GridTradingStrategy,
    # Configuration constants
    USE_ADX_FILTER,
    USE_RSI_FILTER,
    USE_VOLUME_FILTER,
)
from app.backtesting.backtest_engine import BacktestEngine
from app.backtesting.data_generator import (
    generate_ranging_market_data,
    get_cached_data_or_generate,
)


def run_grid_v1_backtest(
    symbol: str,
    use_filters: bool = True,
    days: int = 180
) -> Dict:
    """
    Run backtest for Grid Trading v1

    Args:
        symbol: Trading pair to test
        use_filters: Whether to use ADX/RSI/Volume filters
        days: Number of days of data to test

    Returns:
        Dict with backtest results
    """
    print(f"\n{'='*60}")
    print(f"🚀 Testing Grid Trading v1 ({'WITH' if use_filters else 'WITHOUT'} filters) on {symbol}")
    print(f"{'='*60}\n")

    # Get test data (cached or generate ranging market)
    print(f"📊 Loading {days} days of test data for {symbol}...")
    bars = get_cached_data_or_generate(
        symbol=symbol,
        days=days,
        market_type="ranging",  # Grid trading works best in ranging markets
    )
    print(f"✓ Loaded {len(bars)} bars")

    # Temporarily modify filter constants if needed
    if not use_filters:
        # Monkey-patch to disable filters for baseline test
        import app.strategies.grid_trading_strategy as grid_module
        original_adx = grid_module.USE_ADX_FILTER
        original_rsi = grid_module.USE_RSI_FILTER
        original_volume = grid_module.USE_VOLUME_FILTER

        grid_module.USE_ADX_FILTER = False
        grid_module.USE_RSI_FILTER = False
        grid_module.USE_VOLUME_FILTER = False

    # Create strategy
    strategy = GridTradingStrategy(
        symbol=symbol,
        grid_levels=10,
        grid_range_pct=0.10,
        use_atr_spacing=True,
        max_positions=5,
        position_size_pct=0.02,
    )

    # Create backtest engine
    engine = BacktestEngine(
        strategy=strategy,
        initial_capital=10000.0,
        commission=0.001,  # 0.1% commission
        slippage=0.0005,   # 0.05% slippage
    )

    # Run backtest
    print(f"⏳ Running backtest...")
    results = engine.run(bars)

    # Restore original filter settings
    if not use_filters:
        grid_module.USE_ADX_FILTER = original_adx
        grid_module.USE_RSI_FILTER = original_rsi
        grid_module.USE_VOLUME_FILTER = original_volume

    # Extract key metrics
    win_rate = (results['winning_trades'] / results['total_trades'] * 100) if results['total_trades'] > 0 else 0

    # Display results
    print(f"\n{'='*60}")
    print(f"📊 GRID TRADING V1 RESULTS ({'WITH' if use_filters else 'WITHOUT'} filters) - {symbol}")
    print(f"{'='*60}")
    print(f"Total Return:    {results['total_return']:>8.2f}%")

    # Check if win rate meets target
    target_met = "✓" if win_rate >= 80 else "✗"
    print(f"Win Rate:        {win_rate:>8.1f}% {target_met} (Target: 80%)")

    print(f"Sharpe Ratio:    {results['sharpe_ratio']:>8.2f}")
    print(f"Max Drawdown:    {results['max_drawdown']:>8.2f}%")
    print(f"Total Trades:    {results['total_trades']:>8}")
    print(f"Profit Factor:   {results['profit_factor']:>8.2f}")
    print(f"Avg Win:       $ {results['avg_win']:>8.2f}")
    print(f"Avg Loss:      $ {results['avg_loss']:>8.2f}")
    print(f"{'='*60}\n")

    return {
        'symbol': symbol,
        'with_filters': use_filters,
        'win_rate': win_rate,
        'total_return': results['total_return'],
        'sharpe_ratio': results['sharpe_ratio'],
        'total_trades': results['total_trades'],
        'profit_factor': results['profit_factor'],
    }


def compare_results(baseline: Dict, improved: Dict):
    """Compare baseline vs improved results"""
    print(f"\n{'='*80}")
    print("📈 COMPARISON: ORIGINAL V1 vs IMPROVED V1 (WITH FILTERS)")
    print(f"{'='*80}\n")

    # Calculate improvements
    win_rate_improvement = improved['win_rate'] - baseline['win_rate']
    return_improvement = improved['total_return'] - baseline['total_return']

    print(f"{'Metric':<20} {'Original v1':>15} {'Improved v1':>15} {'Change':>15}")
    print(f"{'-'*80}")
    print(f"{'Win Rate':<20} {baseline['win_rate']:>14.1f}% {improved['win_rate']:>14.1f}% {win_rate_improvement:>+14.1f}%")
    print(f"{'Total Return':<20} {baseline['total_return']:>14.2f}% {improved['total_return']:>14.2f}% {return_improvement:>+14.2f}%")
    print(f"{'Sharpe Ratio':<20} {baseline['sharpe_ratio']:>15.2f} {improved['sharpe_ratio']:>15.2f}")
    print(f"{'Total Trades':<20} {baseline['total_trades']:>15} {improved['total_trades']:>15}")
    print(f"{'Profit Factor':<20} {baseline['profit_factor']:>15.2f} {improved['profit_factor']:>15.2f}")
    print(f"{'='*80}\n")

    # Verdict
    print(f"🏆 VERDICT:")
    print(f"   Original v1 Win Rate: {baseline['win_rate']:.1f}%")
    print(f"   Improved v1 Win Rate: {improved['win_rate']:.1f}%")
    print(f"   Improvement:          {win_rate_improvement:+.1f}%")

    if improved['win_rate'] >= 80:
        print(f"   ✓ TARGET ACHIEVED! Win rate >= 80%")
    elif win_rate_improvement > 0:
        print(f"   ⚠ Improved but below 80% target (gap: {80 - improved['win_rate']:.1f}%)")
    else:
        print(f"   ✗ No improvement detected")

    print(f"\n💡 FILTER STATUS:")
    print(f"   ADX Filter:    {'ENABLED' if USE_ADX_FILTER else 'DISABLED'} (ADX < 35 for ranging markets)")
    print(f"   RSI Filter:    {'ENABLED' if USE_RSI_FILTER else 'DISABLED'} (RSI < 40 buys, > 60 sells)")
    print(f"   Volume Filter: {'ENABLED' if USE_VOLUME_FILTER else 'DISABLED'} (Volume > 0.8x average)")
    print(f"{'='*80}\n")


def main():
    """Main test execution"""
    print(f"{'='*60}")
    print("🧪 GRID TRADING V1 - IMPROVEMENT VALIDATION TEST")
    print(f"{'='*60}")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Goal: Validate that ADX, RSI, Volume filters improve win rate")
    print(f"Baseline: 32.6% win rate (original v1)")
    print(f"Target: >80% win rate")
    print(f"{'='*60}\n")

    # Test symbols
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

    all_baseline = []
    all_improved = []

    for symbol in symbols:
        # Test baseline (without filters)
        print(f"\n{'#'*60}")
        print(f"# TESTING {symbol} - BASELINE (WITHOUT FILTERS)")
        print(f"{'#'*60}")
        baseline_result = run_grid_v1_backtest(symbol, use_filters=False)
        all_baseline.append(baseline_result)

        # Test improved (with filters)
        print(f"\n{'#'*60}")
        print(f"# TESTING {symbol} - IMPROVED (WITH FILTERS)")
        print(f"{'#'*60}")
        improved_result = run_grid_v1_backtest(symbol, use_filters=True)
        all_improved.append(improved_result)

        # Compare for this symbol
        compare_results(baseline_result, improved_result)

    # Overall summary
    print(f"\n{'='*80}")
    print("📊 OVERALL SUMMARY - ALL SYMBOLS")
    print(f"{'='*80}\n")

    avg_baseline_win_rate = sum(r['win_rate'] for r in all_baseline) / len(all_baseline)
    avg_improved_win_rate = sum(r['win_rate'] for r in all_improved) / len(all_improved)
    overall_improvement = avg_improved_win_rate - avg_baseline_win_rate

    print(f"{'Symbol':<15} {'Baseline Win%':>15} {'Improved Win%':>15} {'Improvement':>15}")
    print(f"{'-'*80}")
    for baseline, improved in zip(all_baseline, all_improved):
        improvement = improved['win_rate'] - baseline['win_rate']
        status = "✓" if improved['win_rate'] >= 80 else "⚠" if improvement > 0 else "✗"
        print(f"{baseline['symbol']:<15} {baseline['win_rate']:>14.1f}% {improved['win_rate']:>14.1f}% {improvement:>+14.1f}% {status}")
    print(f"{'-'*80}")
    print(f"{'AVERAGE':<15} {avg_baseline_win_rate:>14.1f}% {avg_improved_win_rate:>14.1f}% {overall_improvement:>+14.1f}%")
    print(f"{'='*80}\n")

    # Final verdict
    print(f"🏆 FINAL VERDICT:")
    print(f"   Original v1: {avg_baseline_win_rate:.1f}% average win rate")
    print(f"   Improved v1: {avg_improved_win_rate:.1f}% average win rate")
    print(f"   Improvement: {overall_improvement:+.1f}%")
    print(f"   Gap to 80% target: {80 - avg_improved_win_rate:.1f}%")

    if avg_improved_win_rate >= 80:
        print(f"\n   ✅ SUCCESS! Achieved >80% win rate target!")
    elif overall_improvement > 10:
        print(f"\n   ⚠️  Significant improvement but below 80% target")
        print(f"      Next steps: Fine-tune filter thresholds")
    elif overall_improvement > 0:
        print(f"\n   ⚠️  Modest improvement detected")
        print(f"      Next steps: Adjust ADX/RSI thresholds or add more filters")
    else:
        print(f"\n   ❌ No improvement - filters may need adjustment")
        print(f"      Next steps: Review filter logic and thresholds")

    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    main()
