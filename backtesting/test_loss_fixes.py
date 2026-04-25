#!/usr/bin/env python3
"""
Backtest Loss Fixes - Test Proposed Configuration Changes
Purpose: Validate that disabling SHORT, tightening stop loss, and adding max hold time improves performance

Compares:
1. CURRENT CONFIG: LONG+SHORT, 3% SL, no max hold
2. PROPOSED FIX: LONG only, 2% SL, 48h max hold

Date: 2026-01-14
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import argparse
import asyncio

from backtesting.backtest_engine import BacktestEngine, OrderType, BacktestResult


class LossFixBacktest:
    """Specialized backtest to validate loss prevention fixes"""

    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.results = {}

    async def load_recent_data(self, symbol: str = "SOLUSDT", days: int = 30) -> pd.DataFrame:
        """Load last 30 days of data for SOLUSDT (our problem symbol)"""
        print(f"\n📊 Loading {days} days of {symbol} data for backtesting...")

        # Try to load from TimescaleDB directly
        try:
            import asyncpg

            conn = await asyncpg.connect(
                host='localhost',
                port=5433,
                user='cryptobot',
                password='cryptobot_secure_2024',
                database='market_data'
            )

            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=days)

            query = """
                SELECT
                    time_bucket('1 hour', timestamp) as timestamp,
                    symbol,
                    FIRST(open, timestamp) as open,
                    MAX(high) as high,
                    MIN(low) as low,
                    LAST(close, timestamp) as close,
                    SUM(volume) as volume
                FROM ohlcv_1m
                WHERE symbol = $1
                    AND timestamp >= $2
                    AND timestamp <= $3
                GROUP BY time_bucket('1 hour', timestamp), symbol
                ORDER BY timestamp ASC
            """

            rows = await conn.fetch(query, symbol, start_time, end_time)
            await conn.close()

            if not rows:
                print(f"❌ No data found for {symbol} in last {days} days")
                return pd.DataFrame()

            df = pd.DataFrame(rows, columns=['timestamp', 'symbol', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp').reset_index(drop=True)

            print(f"✅ Loaded {len(df)} hourly candles from {df['timestamp'].min()} to {df['timestamp'].max()}")
            return df

        except Exception as e:
            print(f"❌ Error loading data from database: {e}")
            return pd.DataFrame()

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators for strategy"""
        print("📈 Calculating technical indicators...")

        # RSI (14 period)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # EMA (20 period)
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()

        # EMA trend (50 and 200)
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()

        # ATR (14 period) for stop loss
        df['high_low'] = df['high'] - df['low']
        df['high_close'] = abs(df['high'] - df['close'].shift())
        df['low_close'] = abs(df['low'] - df['close'].shift())
        df['true_range'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
        df['atr'] = df['true_range'].rolling(window=14).mean()

        # MACD
        df['ema_12'] = df['close'].ewm(span=12, adjust=False).mean()
        df['ema_26'] = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = df['ema_12'] - df['ema_26']
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()

        return df

    def run_current_config_backtest(self, df: pd.DataFrame) -> BacktestResult:
        """Run backtest with CURRENT configuration (the one losing money)"""
        print("\n🔴 Running CURRENT CONFIG backtest (LONG+SHORT, 3% SL, no max hold)...")

        engine = BacktestEngine(
            initial_capital=self.initial_capital,
            commission=0.001,  # 0.1%
            slippage=0.0005    # 0.05%
        )

        def current_strategy(row, position, idx, data):
            """Current strategy: Allow both LONG and SHORT, 3% stop loss"""
            if pd.isna(row['rsi']) or pd.isna(row['ema_20']):
                return {'action': 'HOLD'}

            # If we have a position, check for exit (NO MAX HOLD TIME)
            if position:
                # No time-based exit in current config
                return {'action': 'HOLD'}

            # Entry signals (BOTH LONG AND SHORT allowed)
            if row['rsi'] < 35 and row['close'] > row['ema_20']:
                # LONG entry
                stop_loss = row['close'] * 0.97  # 3% stop loss
                take_profit = row['close'] * 1.09  # 9% take profit
                return {
                    'action': 'BUY',
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'metadata': {'signal': 'rsi_oversold_long'}
                }
            elif row['rsi'] > 65 and row['close'] < row['ema_20']:
                # SHORT entry (THIS IS THE PROBLEM!)
                stop_loss = row['close'] * 1.03  # 3% stop loss for SHORT
                take_profit = row['close'] * 0.91  # 9% take profit for SHORT
                return {
                    'action': 'SELL',
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'metadata': {'signal': 'rsi_overbought_short'}
                }

            return {'action': 'HOLD'}

        result = engine.run_backtest(df, current_strategy, "CURRENT_CONFIG")
        return result

    def run_proposed_fix_backtest(self, df: pd.DataFrame) -> BacktestResult:
        """Run backtest with PROPOSED FIX configuration"""
        print("\n🟢 Running PROPOSED FIX backtest (LONG only, 2% SL, 48h max hold)...")

        engine = BacktestEngine(
            initial_capital=self.initial_capital,
            commission=0.001,  # 0.1%
            slippage=0.0005    # 0.05%
        )

        MAX_HOLD_HOURS = 48

        def proposed_strategy(row, position, idx, data):
            """Proposed strategy: LONG only, 2% stop loss, 48h max hold"""
            if pd.isna(row['rsi']) or pd.isna(row['ema_20']):
                return {'action': 'HOLD'}

            # If we have a position, check for time-based exit
            if position:
                entry_time = position.entry_time
                current_time = row['timestamp']
                hours_held = (current_time - entry_time).total_seconds() / 3600

                # Force exit after 48 hours (MAX HOLD TIME)
                if hours_held >= MAX_HOLD_HOURS:
                    return {
                        'action': 'SELL' if position.order_type == OrderType.BUY else 'BUY',
                        'metadata': {'exit_reason': 'max_hold_time_48h'}
                    }

                return {'action': 'HOLD'}

            # Entry signals (LONG ONLY - NO SHORT!)
            if row['rsi'] < 35 and row['close'] > row['ema_20']:
                # LONG entry only
                stop_loss = row['close'] * 0.98  # 2% stop loss (TIGHTER!)
                take_profit = row['close'] * 1.06  # 6% take profit (adjusted for 3:1 R/R)
                return {
                    'action': 'BUY',
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'metadata': {'signal': 'rsi_oversold_long_only'}
                }

            # SHORT signals are DISABLED
            # No more SHORT trades!

            return {'action': 'HOLD'}

        result = engine.run_backtest(df, proposed_strategy, "PROPOSED_FIX")
        return result

    def print_comparison(self, current: BacktestResult, proposed: BacktestResult):
        """Print detailed comparison of both configs"""
        print("\n" + "="*100)
        print("                         BACKTEST COMPARISON: CURRENT vs PROPOSED FIX")
        print("="*100)

        print(f"\n📅 TEST PERIOD")
        print(f"  Start: {current.start_date.strftime('%Y-%m-%d %H:%M')}")
        print(f"  End:   {current.end_date.strftime('%Y-%m-%d %H:%M')}")
        print(f"  Duration: {(current.end_date - current.start_date).days} days")
        print(f"  Initial Capital: ${self.initial_capital:,.2f}")

        print(f"\n{'METRIC':<40} {'CURRENT':<20} {'PROPOSED':<20} {'CHANGE':<15}")
        print("-" * 95)

        # Trade statistics
        print(f"{'Total Trades':<40} {current.total_trades:<20} {proposed.total_trades:<20} {self._format_change(proposed.total_trades - current.total_trades):<15}")
        print(f"{'Winning Trades':<40} {current.winning_trades:<20} {proposed.winning_trades:<20} {self._format_change(proposed.winning_trades - current.winning_trades):<15}")
        print(f"{'Losing Trades':<40} {current.losing_trades:<20} {proposed.losing_trades:<20} {self._format_change(proposed.losing_trades - current.losing_trades):<15}")
        print(f"{'Win Rate':<40} {current.win_rate:.2f}%{'':<14} {proposed.win_rate:.2f}%{'':<14} {self._format_pct_change(proposed.win_rate - current.win_rate):<15}")

        print()

        # P&L metrics
        print(f"{'Total P&L':<40} ${current.total_profit_loss:,.2f}{'':<13} ${proposed.total_profit_loss:,.2f}{'':<13} {self._format_dollar_change(proposed.total_profit_loss - current.total_profit_loss):<15}")
        print(f"{'Total Return':<40} {current.total_profit_loss_pct:.2f}%{'':<14} {proposed.total_profit_loss_pct:.2f}%{'':<14} {self._format_pct_change(proposed.total_profit_loss_pct - current.total_profit_loss_pct):<15}")
        print(f"{'Final Capital':<40} ${current.final_capital:,.2f}{'':<13} ${proposed.final_capital:,.2f}{'':<13} {self._format_dollar_change(proposed.final_capital - current.final_capital):<15}")
        print(f"{'Avg Profit/Trade':<40} ${current.avg_profit_per_trade:,.2f}{'':<13} ${proposed.avg_profit_per_trade:,.2f}{'':<13} {self._format_dollar_change(proposed.avg_profit_per_trade - current.avg_profit_per_trade):<15}")
        print(f"{'Avg Win':<40} ${current.avg_win:,.2f}{'':<13} ${proposed.avg_win:,.2f}{'':<13} {self._format_dollar_change(proposed.avg_win - current.avg_win):<15}")
        print(f"{'Avg Loss':<40} ${current.avg_loss:,.2f}{'':<13} ${proposed.avg_loss:,.2f}{'':<13} {self._format_dollar_change(proposed.avg_loss - current.avg_loss):<15}")

        print()

        # Risk metrics
        print(f"{'Max Drawdown':<40} ${current.max_drawdown:,.2f}{'':<13} ${proposed.max_drawdown:,.2f}{'':<13} {self._format_dollar_change(proposed.max_drawdown - current.max_drawdown):<15}")
        print(f"{'Max Drawdown %':<40} {current.max_drawdown_pct:.2f}%{'':<14} {proposed.max_drawdown_pct:.2f}%{'':<14} {self._format_pct_change(proposed.max_drawdown_pct - current.max_drawdown_pct):<15}")
        print(f"{'Sharpe Ratio':<40} {current.sharpe_ratio:.2f}{'':<18} {proposed.sharpe_ratio:.2f}{'':<18} {self._format_ratio_change(proposed.sharpe_ratio - current.sharpe_ratio):<15}")
        print(f"{'Profit Factor':<40} {current.profit_factor:.2f}{'':<18} {proposed.profit_factor:.2f}{'':<18} {self._format_ratio_change(proposed.profit_factor - current.profit_factor):<15}")

        print()

        # Trade duration
        print(f"{'Avg Trade Duration (hours)':<40} {current.avg_trade_duration_hours:.1f}{'':<17} {proposed.avg_trade_duration_hours:.1f}{'':<17} {self._format_change(proposed.avg_trade_duration_hours - current.avg_trade_duration_hours):<15}")
        print(f"{'Best Trade':<40} ${current.best_trade:,.2f}{'':<13} ${proposed.best_trade:,.2f}{'':<13} {self._format_dollar_change(proposed.best_trade - current.best_trade):<15}")
        print(f"{'Worst Trade':<40} ${current.worst_trade:,.2f}{'':<13} ${proposed.worst_trade:,.2f}{'':<13} {self._format_dollar_change(proposed.worst_trade - current.worst_trade):<15}")

        print("\n" + "="*100)
        print("                                    ANALYSIS")
        print("="*100)

        # Determine if fixes improved performance
        improvements = []
        issues = []

        if proposed.win_rate > current.win_rate:
            improvements.append(f"✅ Win rate improved by {proposed.win_rate - current.win_rate:.1f}%")
        else:
            issues.append(f"⚠️ Win rate decreased by {current.win_rate - proposed.win_rate:.1f}%")

        if proposed.total_profit_loss > current.total_profit_loss:
            improvements.append(f"✅ Total P&L improved by ${proposed.total_profit_loss - current.total_profit_loss:,.2f}")
        else:
            issues.append(f"⚠️ Total P&L decreased by ${current.total_profit_loss - proposed.total_profit_loss:,.2f}")

        if abs(proposed.avg_loss) < abs(current.avg_loss):
            improvements.append(f"✅ Average loss reduced from ${current.avg_loss:,.2f} to ${proposed.avg_loss:,.2f}")
        else:
            issues.append(f"⚠️ Average loss increased from ${current.avg_loss:,.2f} to ${proposed.avg_loss:,.2f}")

        if proposed.max_drawdown < current.max_drawdown:
            improvements.append(f"✅ Max drawdown reduced by ${current.max_drawdown - proposed.max_drawdown:,.2f}")
        else:
            issues.append(f"⚠️ Max drawdown increased by ${proposed.max_drawdown - current.max_drawdown:,.2f}")

        if proposed.avg_trade_duration_hours < current.avg_trade_duration_hours:
            improvements.append(f"✅ Trade duration reduced from {current.avg_trade_duration_hours:.1f}h to {proposed.avg_trade_duration_hours:.1f}h")

        print("\n🟢 IMPROVEMENTS:")
        if improvements:
            for imp in improvements:
                print(f"  {imp}")
        else:
            print("  None")

        print("\n🔴 ISSUES:")
        if issues:
            for iss in issues:
                print(f"  {iss}")
        else:
            print("  None - All metrics improved!")

        print("\n📊 RECOMMENDATION:")
        if len(improvements) >= 3 and proposed.total_profit_loss > current.total_profit_loss:
            print("  ✅ APPLY THE FIXES - Proposed configuration shows clear improvement")
        elif len(improvements) > len(issues):
            print("  ⚠️ APPLY WITH CAUTION - Some improvements but also some tradeoffs")
        else:
            print("  ❌ DO NOT APPLY - Proposed fixes did not improve performance")

        print("\n" + "="*100)

    def _format_change(self, value: float) -> str:
        """Format numeric change with +/- sign"""
        if value > 0:
            return f"+{value:.1f}"
        elif value < 0:
            return f"{value:.1f}"
        else:
            return "0.0"

    def _format_dollar_change(self, value: float) -> str:
        """Format dollar change with emoji"""
        if value > 0:
            return f"✅ +${value:,.2f}"
        elif value < 0:
            return f"❌ ${value:,.2f}"
        else:
            return "$0.00"

    def _format_pct_change(self, value: float) -> str:
        """Format percentage change with emoji"""
        if value > 0:
            return f"✅ +{value:.2f}%"
        elif value < 0:
            return f"❌ {value:.2f}%"
        else:
            return "0.00%"

    def _format_ratio_change(self, value: float) -> str:
        """Format ratio change with emoji"""
        if value > 0:
            return f"✅ +{value:.2f}"
        elif value < 0:
            return f"❌ {value:.2f}"
        else:
            return "0.00"


async def main():
    parser = argparse.ArgumentParser(description="Backtest proposed loss prevention fixes")
    parser.add_argument('--symbol', default='SOLUSDT', help='Symbol to test (default: SOLUSDT)')
    parser.add_argument('--days', type=int, default=30, help='Days of historical data (default: 30)')
    parser.add_argument('--capital', type=float, default=10000.0, help='Initial capital (default: 10000)')
    args = parser.parse_args()

    print("\n" + "="*100)
    print("                        LOSS FIX BACKTEST - VALIDATION TEST")
    print("="*100)
    print(f"\nTesting Symbol: {args.symbol}")
    print(f"Test Period: Last {args.days} days")
    print(f"Initial Capital: ${args.capital:,.2f}")

    backtest = LossFixBacktest(initial_capital=args.capital)

    # Load data
    df = await backtest.load_recent_data(symbol=args.symbol, days=args.days)
    if df.empty:
        print("❌ Failed to load data. Exiting.")
        return

    # Calculate indicators
    df = backtest.calculate_indicators(df)

    # Run both backtests
    current_result = backtest.run_current_config_backtest(df)
    proposed_result = backtest.run_proposed_fix_backtest(df)

    # Print comparison
    backtest.print_comparison(current_result, proposed_result)

    print(f"\n✅ Backtest complete! Results saved in memory for analysis.")
    print(f"📄 Full analysis available in: TRADE_LOSS_ANALYSIS_2026-01-14.md")


if __name__ == "__main__":
    asyncio.run(main())
