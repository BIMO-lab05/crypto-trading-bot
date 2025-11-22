#!/usr/bin/env python3
"""
BTC/ETH Backtest with Real Data
Purpose: Test BTC and ETH with real Bybit data to determine profitability
"""

import asyncio
import json
from datetime import datetime
import logging

from sqzmom_backtest import SQZMOMBacktester

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Run BTC/ETH backtests with real data"""

    # Database configuration
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
        commission=0.001,  # 0.1% commission
        risk_per_trade=0.02  # 2% risk per trade
    )

    try:
        # Connect to database
        await backtester.connect_db()

        # Test only BTC and ETH (with real data)
        symbols = ['BTCUSDT', 'ETHUSDT']

        print("=" * 80)
        print("BTC/ETH BACKTEST WITH REAL BYBIT DATA")
        print("=" * 80)
        print(f"Initial Capital: $10,000 per symbol")
        print(f"Commission: 0.1% per trade")
        print(f"Risk per Trade: 2% of capital")
        print(f"Data Period: 90 days (Aug 22 - Nov 20, 2025)")
        print(f"Timeframe: 1 hour candles")
        print(f"Symbols: {', '.join(symbols)}")
        print("=" * 80)
        print()

        # Default strategy parameters
        default_params = {
            'bb_length': 20,
            'kc_length': 20,
            'min_momentum_threshold': 0.5,
            'stop_loss_pct': 2.0,
            'take_profit_pct': 4.0,
            'require_squeeze_release': False,
            'require_volume_confirmation': False
        }

        # Store results
        results = {}

        # Test each symbol
        for symbol in symbols:
            print(f"\n{'-' * 80}")
            print(f"Backtesting {symbol} with REAL DATA...")
            print(f"{'-' * 80}")

            result = await backtester.run_backtest(symbol, default_params, verbose=True)
            results[symbol] = result

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

        # Print comparison summary
        print("\n\n" + "=" * 80)
        print("COMPARISON: BTC vs ETH")
        print("=" * 80)
        print()

        print(f"{'Metric':<25} {'BTCUSDT':>15} {'ETHUSDT':>15}")
        print("-" * 60)
        print(f"{'Total Return':<25} {results['BTCUSDT']['total_return_pct']:>14.2f}% {results['ETHUSDT']['total_return_pct']:>14.2f}%")
        print(f"{'Final Capital':<25} ${results['BTCUSDT']['final_capital']:>13,.2f} ${results['ETHUSDT']['final_capital']:>13,.2f}")
        print(f"{'Win Rate':<25} {results['BTCUSDT']['win_rate']:>14.2f}% {results['ETHUSDT']['win_rate']:>14.2f}%")
        print(f"{'Total Trades':<25} {results['BTCUSDT']['total_trades']:>15} {results['ETHUSDT']['total_trades']:>15}")
        print(f"{'Sharpe Ratio':<25} {results['BTCUSDT']['sharpe_ratio']:>15.2f} {results['ETHUSDT']['sharpe_ratio']:>15.2f}")
        print(f"{'Max Drawdown':<25} {results['BTCUSDT']['max_drawdown']:>14.2f}% {results['ETHUSDT']['max_drawdown']:>14.2f}%")
        print(f"{'Profit Factor':<25} {results['BTCUSDT']['profit_factor']:>15.2f} {results['ETHUSDT']['profit_factor']:>15.2f}")

        # Recommendation
        print("\n" + "=" * 80)
        print("RECOMMENDATION")
        print("=" * 80)

        btc_profitable = results['BTCUSDT']['total_return_pct'] > 0
        eth_profitable = results['ETHUSDT']['total_return_pct'] > 0

        if btc_profitable and eth_profitable:
            print("✅ BOTH BTC AND ETH ARE PROFITABLE")
            print("   Recommendation: ADD both to trading symbols")
        elif btc_profitable:
            print("✅ BTC IS PROFITABLE, ❌ ETH IS NOT")
            print("   Recommendation: ADD BTC only")
        elif eth_profitable:
            print("❌ BTC IS NOT PROFITABLE, ✅ ETH IS")
            print("   Recommendation: ADD ETH only")
        else:
            print("❌ NEITHER BTC NOR ETH ARE PROFITABLE")
            print("   Recommendation: DO NOT ADD to trading symbols")
            print("   Consider strategy optimization or different timeframes")

        print()
        print("Notes:")
        print("- Results based on 90 days of real Bybit data")
        print("- Using SQZMOM strategy with default parameters")
        print("- Consider running parameter optimization for better results")
        print("=" * 80)

        # Save results
        output_file = '/mnt/d/Bimo_max/crypto-trading-bot/services/technical-analysis/backtesting/btc_eth_real_data_results.json'

        json_results = {
            'generated_at': datetime.now().isoformat(),
            'data_source': 'Real Bybit Data (90 days)',
            'date_range': '2025-08-22 to 2025-11-20',
            'test_config': {
                'initial_capital': backtester.initial_capital,
                'commission_rate': backtester.commission_rate,
                'risk_per_trade': backtester.risk_per_trade
            },
            'results': {
                symbol: {
                    k: v for k, v in metrics.items() if k != 'trades'
                }
                for symbol, metrics in results.items()
            },
            'recommendation': {
                'btc_profitable': btc_profitable,
                'eth_profitable': eth_profitable,
                'add_to_trading': {
                    'BTCUSDT': btc_profitable,
                    'ETHUSDT': eth_profitable
                }
            }
        }

        with open(output_file, 'w') as f:
            json.dump(json_results, f, indent=2)

        print(f"\n📄 Results saved to: {output_file}")

    except Exception as e:
        logger.error(f"Backtest failed: {e}", exc_info=True)
        raise

    finally:
        await backtester.close()


if __name__ == "__main__":
    asyncio.run(main())
