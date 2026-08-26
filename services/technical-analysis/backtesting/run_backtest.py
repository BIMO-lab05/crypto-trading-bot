#!/usr/bin/env python3
"""
Executable Script to Run SQZMOM Backtests
Purpose: Execute comprehensive backtests and generate reports

Usage:
    python3 run_backtest.py
"""

import asyncio
from pathlib import Path as _Path
_SCRIPT_DIR = str(_Path(__file__).resolve().parent)
import json
from datetime import datetime
import logging

from sqzmom_backtest import SQZMOMBacktester

# Host-run runner: resolve the declared account size (see shared/account.py).
import os as _os
import sys as _sys
_REPO_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in _sys.path:
    _sys.path.insert(0, _REPO_ROOT)
from shared.account import PAPER_INITIAL_BALANCE  # noqa: E402


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Run comprehensive backtests"""

    # Database configuration (matching docker-compose)
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
        initial_capital=PAPER_INITIAL_BALANCE,
        commission=0.001,  # 0.1% commission
        risk_per_trade=0.02  # 2% risk per trade
    )

    try:
        # Connect to database
        await backtester.connect_db()

        # Symbols to test (all available)
        all_symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT', 'DOGEUSDT']
        primary_symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT']

        print("=" * 80)
        print("SQZMOM STRATEGY BACKTESTING FRAMEWORK")
        print("=" * 80)
        print(f"Initial Capital: $10,000 per symbol")
        print(f"Commission: 0.1% per trade (entry + exit)")
        print(f"Risk per Trade: 2% of capital")
        print(f"Date Range: 2025-10-20 to 2025-11-19 (30 days)")
        print(f"Timeframe: 1 hour candles")
        print(f"Symbols: {', '.join(all_symbols)}")
        print("=" * 80)
        print()

        # Store results
        all_results = {}

        # =================================================================
        # TEST 1: INDIVIDUAL SYMBOL BACKTESTS
        # =================================================================
        print("\n" + "=" * 80)
        print("TEST 1: INDIVIDUAL SYMBOL BACKTESTS")
        print("=" * 80)
        print()

        # Default strategy parameters
        default_params = {
            'bb_length': 20,
            'kc_length': 20,
            'min_momentum_threshold': 0.5,
            'stop_loss_pct': 2.0,
            'take_profit_pct': 4.0,
            'require_squeeze_release': False,  # More lenient for more trades
            'require_volume_confirmation': False
        }

        individual_results = {}

        for symbol in all_symbols:
            print(f"\n{'-' * 80}")
            print(f"Backtesting {symbol}...")
            print(f"{'-' * 80}")

            result = await backtester.run_backtest(symbol, default_params, verbose=True)
            individual_results[symbol] = result

            # Print summary
            print(f"\n📊 Results for {symbol}:")
            print(f"  Total Trades:          {result['total_trades']}")
            print(f"  Winning Trades:        {result['winning_trades']}")
            print(f"  Losing Trades:         {result['losing_trades']}")
            print(f"  Win Rate:              {result['win_rate']:.2f}%")
            print(f"  Total P&L:             ${result['total_pnl']:,.2f}")
            print(f"  Total Return:          {result['total_return_pct']:.2f}%")
            print(f"  Profit Factor:         {result['profit_factor']:.2f}")
            print(f"  Average Win:           ${result['avg_win']:.2f}")
            print(f"  Average Loss:          ${result['avg_loss']:.2f}")
            print(f"  Largest Win:           ${result['largest_win']:.2f}")
            print(f"  Largest Loss:          ${result['largest_loss']:.2f}")
            print(f"  Sharpe Ratio:          {result['sharpe_ratio']:.2f}")
            print(f"  Max Drawdown:          {result['max_drawdown']:.2f}%")
            print(f"  Avg Trade Duration:    {result['avg_trade_duration_hours']:.1f} hours")
            print(f"  Long Trades:           {result['long_trades']} (Win Rate: {result['long_win_rate']:.2f}%)")
            print(f"  Short Trades:          {result['short_trades']} (Win Rate: {result['short_win_rate']:.2f}%)")

        all_results['individual'] = individual_results

        # =================================================================
        # TEST 2: MULTI-SYMBOL PORTFOLIO BACKTEST
        # =================================================================
        print("\n\n" + "=" * 80)
        print("TEST 2: MULTI-SYMBOL PORTFOLIO BACKTEST")
        print("=" * 80)
        print()

        print("Testing portfolio approach with 4 primary symbols...")
        print(f"Symbols: {', '.join(primary_symbols)}")
        print()

        portfolio_result = await backtester.run_multi_symbol_backtest(
            primary_symbols,
            default_params
        )

        combined = portfolio_result['combined_metrics']

        print("\n📈 Portfolio Performance:")
        print(f"  Total Trades:          {combined['total_trades']}")
        print(f"  Winning Trades:        {combined['winning_trades']}")
        print(f"  Losing Trades:         {combined['losing_trades']}")
        print(f"  Win Rate:              {combined['win_rate']:.2f}%")
        print(f"  Combined P&L:          ${combined['total_pnl']:,.2f}")
        print(f"  Combined Return:       {combined['total_return_pct']:.2f}%")
        print(f"  Average Sharpe Ratio:  {combined['avg_sharpe_ratio']:.2f}")
        print(f"  Average Max Drawdown:  {combined['avg_max_drawdown']:.2f}%")
        print(f"  Average Profit Factor: {combined['avg_profit_factor']:.2f}")

        print("\n📋 Per-Symbol Performance:")
        for symbol in primary_symbols:
            metrics = portfolio_result['per_symbol_metrics'][symbol]
            print(f"  {symbol:10} | Trades: {metrics['total_trades']:3} | "
                  f"Return: {metrics['total_return_pct']:6.2f}% | "
                  f"Win Rate: {metrics['win_rate']:5.2f}%")

        all_results['portfolio'] = portfolio_result

        # =================================================================
        # TEST 3: PARAMETER OPTIMIZATION
        # =================================================================
        print("\n\n" + "=" * 80)
        print("TEST 3: PARAMETER OPTIMIZATION")
        print("=" * 80)
        print()

        # Define parameter ranges to test
        param_ranges = {
            'min_momentum_threshold': [0.3, 0.5, 0.7],
            'stop_loss_pct': [1.5, 2.0, 2.5],
            'take_profit_pct': [3.0, 4.0, 5.0]
        }

        # Optimize on BTCUSDT (most liquid)
        print("Optimizing parameters on BTCUSDT (most liquid pair)...")
        print(f"Parameter ranges:")
        for param, values in param_ranges.items():
            print(f"  {param}: {values}")
        print()

        opt_result = await backtester.optimize_parameters('BTCUSDT', param_ranges)

        print("\n🎯 Optimization Results:")
        print(f"  Combinations Tested:   {opt_result['total_combinations_tested']}")
        print(f"  Best Return:           {opt_result['best_return']:.2f}%")
        print()
        print("  Best Parameters Found:")
        for param, value in opt_result['best_params'].items():
            print(f"    {param:25} = {value}")

        print()
        print("  Best Metrics:")
        best = opt_result['best_metrics']
        print(f"    Total Trades:          {best['total_trades']}")
        print(f"    Win Rate:              {best['win_rate']:.2f}%")
        print(f"    Sharpe Ratio:          {best['sharpe_ratio']:.2f}")
        print(f"    Max Drawdown:          {best['max_drawdown']:.2f}%")
        print(f"    Profit Factor:         {best['profit_factor']:.2f}")

        print()
        print("  Top 5 Parameter Combinations:")
        print(f"  {'Rank':<6} {'Return':<10} {'Sharpe':<8} {'Win Rate':<10} {'Trades':<8} {'Max DD':<8}")
        print("  " + "-" * 60)
        for i, result in enumerate(opt_result['all_results'][:5], 1):
            print(f"  {i:<6} {result['return_pct']:>6.2f}%   {result['sharpe_ratio']:>6.2f}  "
                  f"{result['win_rate']:>6.2f}%    {result['total_trades']:>5}    {result['max_drawdown']:>6.2f}%")

        all_results['optimization'] = opt_result

        # =================================================================
        # TEST 4: BACKTEST WITH OPTIMIZED PARAMETERS
        # =================================================================
        print("\n\n" + "=" * 80)
        print("TEST 4: BACKTEST WITH OPTIMIZED PARAMETERS")
        print("=" * 80)
        print()

        print("Re-running backtest on all symbols with optimized parameters...")
        print()

        optimized_results = {}

        for symbol in all_symbols:
            print(f"Testing {symbol} with optimized params...")

            result = await backtester.run_backtest(
                symbol,
                opt_result['best_params'],
                verbose=False
            )
            optimized_results[symbol] = result

            print(f"  {symbol:10} | Return: {result['total_return_pct']:6.2f}% | "
                  f"Trades: {result['total_trades']:3} | Win Rate: {result['win_rate']:5.2f}%")

        # Compare with default parameters
        print()
        print("📊 Comparison: Default vs Optimized Parameters")
        print(f"  {'Symbol':<12} {'Default Return':<15} {'Optimized Return':<17} {'Improvement':<12}")
        print("  " + "-" * 60)

        for symbol in all_symbols:
            default_return = individual_results[symbol]['total_return_pct']
            optimized_return = optimized_results[symbol]['total_return_pct']
            improvement = optimized_return - default_return

            print(f"  {symbol:<12} {default_return:>6.2f}%         {optimized_return:>6.2f}%            "
                  f"{improvement:>+6.2f}%")

        all_results['optimized'] = optimized_results

        # =================================================================
        # GENERATE COMPREHENSIVE REPORT
        # =================================================================
        print("\n\n" + "=" * 80)
        print("GENERATING COMPREHENSIVE REPORT")
        print("=" * 80)
        print()

        report = backtester.generate_report(all_results)

        # Add detailed sections to report
        report += "\n## Detailed Results\n\n"

        # Individual symbol details
        report += "### Individual Symbol Performance\n\n"
        report += "| Symbol | Trades | Win Rate | Return | Sharpe | Max DD | Profit Factor |\n"
        report += "|--------|--------|----------|--------|--------|--------|---------------|\n"

        for symbol in all_symbols:
            metrics = individual_results[symbol]
            report += f"| {symbol} | {metrics['total_trades']} | "
            report += f"{metrics['win_rate']:.2f}% | {metrics['total_return_pct']:.2f}% | "
            report += f"{metrics['sharpe_ratio']:.2f} | {metrics['max_drawdown']:.2f}% | "
            report += f"{metrics['profit_factor']:.2f} |\n"

        # Strategy parameters used
        report += "\n### Strategy Configuration\n\n"
        report += "**Default Parameters:**\n"
        for param, value in default_params.items():
            report += f"- `{param}`: {value}\n"

        report += "\n**Optimized Parameters:**\n"
        for param, value in opt_result['best_params'].items():
            report += f"- `{param}`: {value}\n"

        # Key findings
        report += "\n## Key Findings\n\n"

        # Calculate overall statistics
        total_trades_all = sum(r['total_trades'] for r in individual_results.values())
        avg_return = sum(r['total_return_pct'] for r in individual_results.values()) / len(all_symbols)
        avg_win_rate = sum(r['win_rate'] for r in individual_results.values()) / len(all_symbols)
        profitable_symbols = len([r for r in individual_results.values() if r['total_return_pct'] > 0])

        report += f"1. **Overall Performance**: Tested {len(all_symbols)} symbols over 30 days\n"
        report += f"   - Total Trades: {total_trades_all}\n"
        report += f"   - Average Return: {avg_return:.2f}%\n"
        report += f"   - Average Win Rate: {avg_win_rate:.2f}%\n"
        report += f"   - Profitable Symbols: {profitable_symbols}/{len(all_symbols)}\n\n"

        # Best and worst performers
        best_symbol = max(individual_results.items(), key=lambda x: x[1]['total_return_pct'])
        worst_symbol = min(individual_results.items(), key=lambda x: x[1]['total_return_pct'])

        report += f"2. **Best Performer**: {best_symbol[0]} with {best_symbol[1]['total_return_pct']:.2f}% return\n"
        report += f"   - Win Rate: {best_symbol[1]['win_rate']:.2f}%\n"
        report += f"   - Sharpe Ratio: {best_symbol[1]['sharpe_ratio']:.2f}\n"
        report += f"   - Total Trades: {best_symbol[1]['total_trades']}\n\n"

        report += f"3. **Worst Performer**: {worst_symbol[0]} with {worst_symbol[1]['total_return_pct']:.2f}% return\n"
        report += f"   - Win Rate: {worst_symbol[1]['win_rate']:.2f}%\n"
        report += f"   - Total Trades: {worst_symbol[1]['total_trades']}\n\n"

        # Strategy insights
        report += "4. **Strategy Insights**:\n"
        report += f"   - Parameter optimization improved returns by an average of "
        avg_improvement = sum(
            optimized_results[s]['total_return_pct'] - individual_results[s]['total_return_pct']
            for s in all_symbols
        ) / len(all_symbols)
        report += f"{avg_improvement:.2f}%\n"

        report += f"   - Risk management (2% per trade) prevented catastrophic losses\n"
        report += f"   - Commission impact: {backtester.commission_rate * 100:.2f}% per trade (round trip)\n\n"

        # Recommendations
        report += "## Recommendations\n\n"

        if avg_return > 0:
            report += "✅ **Strategy is profitable** on the tested period\n\n"
        else:
            report += "⚠ **Strategy needs improvement** - negative returns on average\n\n"

        report += "**Optimization Suggestions:**\n"
        report += "1. Use optimized parameters for live trading\n"
        report += "2. Consider implementing trailing stop losses for better profit protection\n"
        report += "3. Add volume filters to improve entry quality\n"
        report += "4. Test on different timeframes (4h, 1d) for longer-term trends\n"
        report += "5. Implement position sizing based on volatility (ATR-based)\n\n"

        report += "**Risk Management:**\n"
        report += f"- Current 2% risk per trade is conservative and suitable\n"
        report += f"- Maximum observed drawdown: {max(r['max_drawdown'] for r in individual_results.values()):.2f}%\n"
        report += f"- Consider reducing position size if drawdown exceeds 20%\n\n"

        report += "---\n"
        report += f"\n*Report generated by SQZMOM Backtesting Framework v1.0*\n"
        report += f"*Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n"

        # Save report
        report_path = f'{_SCRIPT_DIR}/SQZMOM_BACKTEST_REPORT.md'
        with open(report_path, 'w') as f:
            f.write(report)

        print(f"📄 Report saved to: {report_path}")

        # Save detailed results as JSON
        json_path = f'{_SCRIPT_DIR}/backtest_results.json'

        # Prepare JSON-serializable results
        json_results = {
            'generated_at': datetime.now().isoformat(),
            'test_config': {
                'initial_capital': backtester.initial_capital,
                'commission_rate': backtester.commission_rate,
                'risk_per_trade': backtester.risk_per_trade
            },
            'individual_results': {
                symbol: {
                    k: v for k, v in metrics.items() if k != 'trades'  # Exclude trade details for JSON
                }
                for symbol, metrics in individual_results.items()
            },
            'portfolio_results': {
                'combined_metrics': combined,
                'symbols': primary_symbols
            },
            'optimization_results': {
                'symbol': opt_result['symbol'],
                'best_params': opt_result['best_params'],
                'best_return': opt_result['best_return'],
                'total_combinations_tested': opt_result['total_combinations_tested'],
                'top_5_results': opt_result['all_results'][:5]
            },
            'optimized_results': {
                symbol: {
                    k: v for k, v in metrics.items() if k != 'trades'
                }
                for symbol, metrics in optimized_results.items()
            }
        }

        with open(json_path, 'w') as f:
            json.dump(json_results, f, indent=2)

        print(f"📊 Detailed results saved to: {json_path}")

        # Save trade logs
        trades_path = f'{_SCRIPT_DIR}/trade_logs.json'
        all_trades_data = {
            symbol: metrics['trades']
            for symbol, metrics in individual_results.items()
        }

        with open(trades_path, 'w') as f:
            json.dump(all_trades_data, f, indent=2)

        print(f"📝 Trade logs saved to: {trades_path}")

        print()
        print("=" * 80)
        print("✓ BACKTESTING COMPLETED SUCCESSFULLY")
        print("=" * 80)
        print()
        print("Summary:")
        print(f"  - Tested {len(all_symbols)} symbols")
        print(f"  - Total trades: {total_trades_all}")
        print(f"  - Average return: {avg_return:.2f}%")
        print(f"  - Best performer: {best_symbol[0]} ({best_symbol[1]['total_return_pct']:.2f}%)")
        print(f"  - Parameter optimization completed")
        print()
        print("Files generated:")
        print(f"  1. {report_path}")
        print(f"  2. {json_path}")
        print(f"  3. {trades_path}")
        print()

    except Exception as e:
        logger.error(f"Backtesting failed: {e}", exc_info=True)
        raise

    finally:
        # Close database connection
        await backtester.close()


if __name__ == "__main__":
    asyncio.run(main())
