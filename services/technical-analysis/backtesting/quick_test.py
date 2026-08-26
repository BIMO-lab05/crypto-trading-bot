#!/usr/bin/env python3
"""Quick backtest to test the framework"""

import asyncio
import logging
from sqzmom_backtest import SQZMOMBacktester

# Host-run runner: resolve the declared account size (see shared/account.py).
import os as _os
import sys as _sys
_REPO_ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in _sys.path:
    _sys.path.insert(0, _REPO_ROOT)
from shared.account import PAPER_INITIAL_BALANCE  # noqa: E402


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    db_config = {
        'host': 'localhost',
        'port': 5433,
        'database': 'market_data',
        'user': 'cryptobot',
        'password': 'timescale_dev_password'
    }

    backtester = SQZMOMBacktester(
        db_config=db_config,
        initial_capital=PAPER_INITIAL_BALANCE,
        commission=0.001,
        risk_per_trade=0.02
    )

    await backtester.connect_db()

    print("\n" + "="*80)
    print("QUICK SQZMOM BACKTEST - TESTING FRAMEWORK")
    print("="*80 + "\n")

    # Test on BTCUSDT only
    result = await backtester.run_backtest('BTCUSDT', verbose=True)

    print("\n" + "="*80)
    print("RESULTS FOR BTCUSDT")
    print("="*80)
    print(f"Total Trades:      {result['total_trades']}")
    print(f"Win Rate:          {result['win_rate']:.2f}%")
    print(f"Total Return:      {result['total_return_pct']:.2f}%")
    print(f"Profit Factor:     {result['profit_factor']:.2f}")
    print(f"Sharpe Ratio:      {result['sharpe_ratio']:.2f}")
    print(f"Max Drawdown:      {result['max_drawdown']:.2f}%")
    print(f"Final Capital:     ${result['final_capital']:,.2f}")
    print(f"Long Trades:       {result['long_trades']} (Win Rate: {result['long_win_rate']:.2f}%)")
    print(f"Short Trades:      {result['short_trades']} (Win Rate: {result['short_win_rate']:.2f}%)")

    if result['total_trades'] > 0:
        print("\nFirst 5 Trades:")
        for i, trade in enumerate(result['trades'][:5], 1):
            print(f"  {i}. {trade['direction']:5} | Entry: ${trade['entry_price']:,} | "
                  f"Exit: ${trade['exit_price']:,} | P&L: ${trade['net_pnl']:.2f} ({trade['pnl_pct']:.2f}%)")

    await backtester.close()

if __name__ == "__main__":
    asyncio.run(main())
