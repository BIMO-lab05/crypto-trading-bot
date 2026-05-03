#!/usr/bin/env python3
"""
Test Trend-Following Strategy on CSV Data - OPTIMIZED VERSION v4
=================================================================
Since market is TRENDING 80% of time (not ranging),
test trend-following instead of mean reversion/grid.

OPTIMIZATION CHANGES (v4 - from v3):
- Cooldown: 4 -> 12 hours (major filter for quality trades)
- Momentum threshold: 0.5% -> 1.0% (stronger confirmation)
- ADX entry threshold: 20 -> 25 (only strong trends)
- ADX exit threshold: 15 -> 18 (exit sooner on weakening)
- ATR stop: 2.0x -> 2.5x (give trades more room)
- ATR target: 4.0x -> 5.0x (bigger winners)

v3 Results: 26.4% win rate, 307 trades/symbol, -0.41 Sharpe
v4 Goal: >35% win rate, 30-80 trades/symbol, >0 Sharpe
"""
import sys
from pathlib import Path as _Path
_REPO_ROOT = _Path(__file__).resolve().parent.parent
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services', 'trading-engine'))

from app.backtesting.backtest_engine import BacktestEngine, BacktestConfig, BacktestResult
from app.backtesting.strategy_base import OHLCV, StrategyBase, Signal, SignalType


class OptimizedTrendFollowingV4(StrategyBase):
    """
    Optimized Trend Following Strategy (v4)

    Key improvements over v3:
    - 12-hour cooldown (major reduction in trade frequency)
    - 1.0% momentum threshold (much stronger confirmation)
    - ADX > 25 for entries (only strong trends)
    - Wider stops (2.5x ATR) and larger targets (5x ATR)
    - Better risk/reward ratio (1:2)

    Entry conditions:
    - Long: Price > EMA(20) AND ADX > 25 AND momentum(5) > 1.0%
    - Short: Price < EMA(20) AND ADX > 25 AND momentum(5) < -1.0%
    - Must be at least 12 hours since last trade

    Exit conditions:
    - Trend reversal (price crosses EMA opposite direction)
    - Weakening trend (ADX < 18)
    - Stop loss (2.5x ATR) / Take profit (5x ATR)
    """

    def __init__(self, symbol: str):
        # OPTIMIZED PARAMETERS v4 - set before super().__init__
        self.ema_period = 20  # Keep stable EMA
        self.adx_period = 14  # Standard ADX period
        self.adx_entry_threshold = 25  # Was 20 in v3 - stricter
        self.adx_exit_threshold = 18  # Was 15 in v3 - exit sooner
        self.momentum_period = 5  # Keep fast momentum
        self.momentum_threshold_pct = 1.0  # Was 0.5% in v3 - stronger
        self.atr_stop_mult = 2.5  # Was 2.0 in v3 - more room
        self.atr_tp_mult = 5.0  # Was 4.0 in v3 - bigger wins
        self.cooldown_bars = 12  # Was 4 in v3 - much longer

        # Track last trade time
        self._last_trade_bar: Optional[int] = None
        self._current_bar_index = 0

        super().__init__(symbol, {
            "ema_period": self.ema_period,
            "adx_period": self.adx_period,
            "adx_entry_threshold": self.adx_entry_threshold,
            "adx_exit_threshold": self.adx_exit_threshold,
            "momentum_period": self.momentum_period,
            "momentum_threshold_pct": self.momentum_threshold_pct,
            "atr_stop_mult": self.atr_stop_mult,
            "atr_tp_mult": self.atr_tp_mult,
            "cooldown_bars": self.cooldown_bars
        })

    def get_name(self) -> str:
        """Return strategy name with parameters"""
        return f"TrendFollowing_v4_EMA{self.ema_period}_ADX{self.adx_entry_threshold}"

    def on_bar(self, bar: OHLCV, equity: float) -> Optional[Signal]:
        """Process each bar and generate trading signals"""
        self._current_bar_index += 1

        # Need enough data for calculations
        min_periods = max(self.ema_period, self.adx_period, self.momentum_period) + 1
        if len(self._prices) < min_periods:
            return None

        # Use the built-in EMA calculator from base class
        ema_value = self.ema(self.ema_period)
        if ema_value is None:
            return None

        # Calculate ADX
        adx = self._calculate_adx(self._highs, self._lows, self._prices, self.adx_period)

        # Calculate Momentum (rate of change over momentum period)
        momentum = self._prices[-1] - self._prices[-self.momentum_period]

        # Calculate momentum percentage
        momentum_pct = (momentum / self._prices[-self.momentum_period]) * 100

        # Use built-in ATR calculator
        atr_value = self.atr(14)
        if atr_value is None:
            return None

        current_price = bar.close

        # Calculate price distance from EMA (trend strength indicator)
        ema_distance_pct = ((current_price - ema_value) / ema_value) * 100

        # Generate signals based on trend following logic
        signal = None

        # Check cooldown
        in_cooldown = False
        if self._last_trade_bar is not None:
            bars_since_trade = self._current_bar_index - self._last_trade_bar
            in_cooldown = bars_since_trade < self.cooldown_bars

        # Entry signals - only if no position and not in cooldown
        if not self.has_position() and not in_cooldown:
            # LONG ENTRY: Price above EMA + strong ADX + strong positive momentum
            if (current_price > ema_value and
                adx > self.adx_entry_threshold and
                momentum_pct > self.momentum_threshold_pct):

                # Calculate stop loss and take profit
                stop_loss = current_price - (atr_value * self.atr_stop_mult)
                take_profit = current_price + (atr_value * self.atr_tp_mult)

                # Confidence based on ADX strength and momentum
                confidence = min(1.0, (adx / 50) * (1 + abs(momentum_pct) / 3))

                signal = Signal(
                    signal_type=SignalType.BUY,
                    symbol=self.symbol,
                    price=current_price,
                    timestamp=bar.timestamp,
                    confidence=confidence,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    metadata={
                        "ema": round(ema_value, 2),
                        "adx": round(adx, 2),
                        "momentum": round(momentum, 4),
                        "momentum_pct": round(momentum_pct, 2),
                        "atr": round(atr_value, 4),
                        "ema_distance_pct": round(ema_distance_pct, 2),
                        "entry_reason": "strong_uptrend"
                    }
                )
                self._last_trade_bar = self._current_bar_index

            # SHORT ENTRY: Price below EMA + strong ADX + strong negative momentum
            elif (current_price < ema_value and
                  adx > self.adx_entry_threshold and
                  momentum_pct < -self.momentum_threshold_pct):

                # Calculate stop loss and take profit
                stop_loss = current_price + (atr_value * self.atr_stop_mult)
                take_profit = current_price - (atr_value * self.atr_tp_mult)

                # Confidence based on ADX strength and momentum
                confidence = min(1.0, (adx / 50) * (1 + abs(momentum_pct) / 3))

                signal = Signal(
                    signal_type=SignalType.SELL,
                    symbol=self.symbol,
                    price=current_price,
                    timestamp=bar.timestamp,
                    confidence=confidence,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    metadata={
                        "ema": round(ema_value, 2),
                        "adx": round(adx, 2),
                        "momentum": round(momentum, 4),
                        "momentum_pct": round(momentum_pct, 2),
                        "atr": round(atr_value, 4),
                        "ema_distance_pct": round(ema_distance_pct, 2),
                        "entry_reason": "strong_downtrend"
                    }
                )
                self._last_trade_bar = self._current_bar_index

        # Exit signals - if we have a position
        elif self.is_long():
            # Exit long if: trend reverses OR trend weakens significantly
            exit_reason = None

            # Price crosses below EMA - clear trend reversal
            if current_price < ema_value:
                exit_reason = "trend_reversal_below_ema"
            # ADX drops - trend losing strength
            elif adx < self.adx_exit_threshold:
                exit_reason = "weak_trend_adx_low"

            if exit_reason:
                self._last_trade_bar = self._current_bar_index
                signal = Signal(
                    signal_type=SignalType.CLOSE_LONG,
                    symbol=self.symbol,
                    price=current_price,
                    timestamp=bar.timestamp,
                    confidence=0.8,
                    metadata={
                        "exit_reason": exit_reason,
                        "ema": round(ema_value, 2),
                        "adx": round(adx, 2),
                        "momentum_pct": round(momentum_pct, 2)
                    }
                )

        elif self.is_short():
            # Exit short if: trend reverses OR trend weakens significantly
            exit_reason = None

            # Price crosses above EMA - clear trend reversal
            if current_price > ema_value:
                exit_reason = "trend_reversal_above_ema"
            # ADX drops - trend losing strength
            elif adx < self.adx_exit_threshold:
                exit_reason = "weak_trend_adx_low"

            if exit_reason:
                self._last_trade_bar = self._current_bar_index
                signal = Signal(
                    signal_type=SignalType.CLOSE_SHORT,
                    symbol=self.symbol,
                    price=current_price,
                    timestamp=bar.timestamp,
                    confidence=0.8,
                    metadata={
                        "exit_reason": exit_reason,
                        "ema": round(ema_value, 2),
                        "adx": round(adx, 2),
                        "momentum_pct": round(momentum_pct, 2)
                    }
                )

        return signal

    def _calculate_adx(self, highs: List[float], lows: List[float],
                       closes: List[float], period: int) -> float:
        """
        Calculate Average Directional Index (ADX)

        ADX measures trend strength:
        - 0-20: Weak or no trend
        - 20-40: Moderate trend
        - 40-60: Strong trend
        - 60-100: Very strong trend
        """
        if len(closes) < period + 1:
            return 0

        # Calculate True Range
        tr_list = []
        for i in range(1, len(closes)):
            high_low = highs[i] - lows[i]
            high_close = abs(highs[i] - closes[i-1])
            low_close = abs(lows[i] - closes[i-1])
            tr = max(high_low, high_close, low_close)
            tr_list.append(tr)

        if not tr_list:
            return 0

        # Calculate directional movement
        plus_dm = []
        minus_dm = []
        for i in range(1, len(highs)):
            up_move = highs[i] - highs[i-1]
            down_move = lows[i-1] - lows[i]

            if up_move > down_move and up_move > 0:
                plus_dm.append(up_move)
                minus_dm.append(0)
            elif down_move > up_move and down_move > 0:
                plus_dm.append(0)
                minus_dm.append(down_move)
            else:
                plus_dm.append(0)
                minus_dm.append(0)

        # Smoothed averages
        if len(tr_list) < period or len(plus_dm) < period:
            return 0

        atr = sum(tr_list[-period:]) / period
        plus_di = (sum(plus_dm[-period:]) / period) / atr * 100 if atr > 0 else 0
        minus_di = (sum(minus_dm[-period:]) / period) / atr * 100 if atr > 0 else 0

        # ADX calculation
        dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0
        return dx


def load_csv_data(symbol: str) -> List[OHLCV]:
    """Load CSV data from historical data directory"""
    csv_file = fstr(_REPO_ROOT / 'data/historical/{symbol}_180days_20251208.csv')

    if not os.path.exists(csv_file):
        raise FileNotFoundError(f"CSV file not found: {csv_file}")

    df = pd.read_csv(csv_file)
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    bars = []
    for _, row in df.iterrows():
        bars.append(OHLCV(
            timestamp=row['timestamp'].to_pydatetime(),
            open=float(row['open']),
            high=float(row['high']),
            low=float(row['low']),
            close=float(row['close']),
            volume=float(row['volume'])
        ))
    return bars


def test_symbol(symbol: str) -> Dict:
    """Test trend following strategy on one symbol"""
    print(f"\n{'='*80}")
    print(f"Testing {symbol} - OPTIMIZED Trend Following v4")
    print(f"{'='*80}")

    # Load data
    bars = load_csv_data(symbol)
    print(f"Loaded {len(bars)} bars ({len(bars)/24:.0f} days)")

    # Create optimized strategy v4
    strategy = OptimizedTrendFollowingV4(symbol)
    print(f"Strategy: {strategy.get_name()}")
    print(f"Parameters: ADX>{strategy.adx_entry_threshold}, "
          f"EMA({strategy.ema_period}), "
          f"Momentum>{strategy.momentum_threshold_pct}%, "
          f"Cooldown={strategy.cooldown_bars}h")

    # Create config with reasonable position sizing
    config = BacktestConfig(
        initial_equity=10000.0,
        commission_pct=0.1,  # 0.1% commission (Bybit taker fee)
        slippage_pct=0.05,   # 0.05% slippage
        position_size_pct=2.0,  # 2% risk per trade
        max_positions=1
    )

    # Run backtest
    engine = BacktestEngine(config)
    result = engine.run(strategy, bars)

    metrics = result.metrics

    # Print detailed results
    print(f"\n--- Results ---")
    print(f"Win Rate: {metrics.win_rate:.1f}%")
    print(f"Total Return: {metrics.total_return_pct:.2f}%")
    print(f"Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
    print(f"Max Drawdown: {metrics.max_drawdown_pct:.2f}%")
    print(f"Total Trades: {metrics.total_trades}")
    print(f"Winning Trades: {metrics.winning_trades}")
    print(f"Losing Trades: {metrics.losing_trades}")

    # Calculate trades per 30 days
    if len(bars) > 0:
        days = len(bars) / 24  # Assuming hourly bars
        trades_per_30d = (metrics.total_trades / days) * 30
        print(f"Trades per 30 days: {trades_per_30d:.1f}")

    return {
        'symbol': symbol,
        'win_rate': metrics.win_rate,
        'total_return': metrics.total_return_pct,
        'sharpe_ratio': metrics.sharpe_ratio,
        'max_drawdown': metrics.max_drawdown_pct,
        'total_trades': metrics.total_trades,
        'winning_trades': metrics.winning_trades,
        'losing_trades': metrics.losing_trades
    }


if __name__ == "__main__":
    print("\n" + "="*80)
    print("TREND-FOLLOWING STRATEGY TEST - OPTIMIZED v4")
    print("="*80)
    print("Testing on TRENDING market (80% trend, 20% range)")
    print("Strategy: EMA + ADX + Momentum (OPTIMIZED PARAMETERS v4)")
    print("\nOptimization changes from v3:")
    print("  - ADX entry threshold: 20 -> 25 (only strong trends)")
    print("  - ADX exit threshold: 15 -> 18 (exit sooner)")
    print("  - Momentum threshold: 0.5% -> 1.0% (stronger confirmation)")
    print("  - Cooldown: 4 -> 12 hours (reduce frequency)")
    print("  - ATR stop: 2.0x -> 2.5x (more room)")
    print("  - ATR target: 4.0x -> 5.0x (bigger wins, 1:2 R:R)")
    print("\nv3 Results: 26.4% win rate, 307 trades/symbol, -0.41 Sharpe")
    print("v4 Goal: >35% win rate, 30-80 trades/symbol, >0 Sharpe")
    print("="*80 + "\n")

    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'ADAUSDT']

    results = []
    for symbol in symbols:
        try:
            result = test_symbol(symbol)
            results.append(result)
        except FileNotFoundError as e:
            print(f"Skipping {symbol}: {e}")
        except Exception as e:
            print(f"Error testing {symbol}: {e}")
            import traceback
            traceback.print_exc()

    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY - OPTIMIZED TREND FOLLOWING v4")
    print(f"{'='*80}")

    if results:
        # Calculate averages
        avg_win_rate = sum(r['win_rate'] for r in results) / len(results)
        avg_return = sum(r['total_return'] for r in results) / len(results)
        avg_sharpe = sum(r['sharpe_ratio'] for r in results) / len(results)
        avg_drawdown = sum(r['max_drawdown'] for r in results) / len(results)
        total_trades = sum(r['total_trades'] for r in results)
        total_wins = sum(r['winning_trades'] for r in results)
        total_losses = sum(r['losing_trades'] for r in results)

        print(f"\nPer-Symbol Results:")
        print(f"{'Symbol':<10} {'Win%':>8} {'Return%':>10} {'Sharpe':>8} {'Trades':>8} {'W/L':>8}")
        print("-" * 54)
        for r in results:
            wl = f"{r['winning_trades']}/{r['losing_trades']}"
            print(f"{r['symbol']:<10} {r['win_rate']:>7.1f}% {r['total_return']:>9.2f}% "
                  f"{r['sharpe_ratio']:>8.2f} {r['total_trades']:>8} {wl:>8}")

        print("-" * 54)
        print(f"\nAggregated Metrics:")
        print(f"  Average Win Rate: {avg_win_rate:.1f}%")
        print(f"  Average Return: {avg_return:.2f}%")
        print(f"  Average Sharpe: {avg_sharpe:.2f}")
        print(f"  Average Max Drawdown: {avg_drawdown:.2f}%")
        print(f"  Total Trades (all symbols): {total_trades}")
        print(f"  Total Wins/Losses: {total_wins}/{total_losses}")
        print(f"  Average trades/symbol: {total_trades/len(results):.1f}")

        # Validation against goals
        trades_per_symbol = total_trades / len(results)
        print(f"\n--- VALIDATION vs GOALS ---")
        print(f"Goal: Win rate > 35%  -> {'PASS' if avg_win_rate > 35 else 'FAIL'} ({avg_win_rate:.1f}%)")
        print(f"Goal: 30-80 trades/symbol -> {'PASS' if 30 <= trades_per_symbol <= 80 else 'FAIL'} ({trades_per_symbol:.1f})")
        print(f"Goal: Sharpe > 0 -> {'PASS' if avg_sharpe > 0 else 'FAIL'} ({avg_sharpe:.2f})")

        # Comparison with v3
        print(f"\n--- COMPARISON vs v3 ---")
        print(f"Win Rate: 26.4% -> {avg_win_rate:.1f}% ({'IMPROVED' if avg_win_rate > 26.4 else 'WORSE'})")
        print(f"Trades/symbol: 307 -> {trades_per_symbol:.1f} ({'IMPROVED' if trades_per_symbol < 307 else 'WORSE'})")
        print(f"Sharpe: -0.41 -> {avg_sharpe:.2f} ({'IMPROVED' if avg_sharpe > -0.41 else 'WORSE'})")

        # Historical comparison
        print(f"\n--- FULL OPTIMIZATION JOURNEY ---")
        print(f"v1 (original): 20% win rate, 5 trades total, N/A Sharpe (BUG)")
        print(f"v2 (bug fix):  23% win rate, 660 trades/symbol, -1.06 Sharpe")
        print(f"v3 (filtered): 26.4% win rate, 307 trades/symbol, -0.41 Sharpe")
        print(f"v4 (current):  {avg_win_rate:.1f}% win rate, {trades_per_symbol:.1f} trades/symbol, {avg_sharpe:.2f} Sharpe")

        if avg_win_rate > 40 and avg_sharpe > 0.5:
            print("\n[SUCCESS] OPTIMIZED TREND FOLLOWING v4 WORKS!")
            print("Strategy is ready for paper trading validation.")
        elif avg_win_rate > 35 or avg_sharpe > 0:
            print("\n[PARTIAL SUCCESS] Significant improvement!")
            print("Consider paper trading with current parameters.")
        elif avg_win_rate > 30:
            print("\n[PROGRESS] Steady improvement, getting closer to target")
        else:
            print("\n[NEEDS WORK] Consider different approach")
            print("Options: Try 4H timeframe, add RSI filter, or different strategy type")

    print(f"\n{'='*80}\n")
