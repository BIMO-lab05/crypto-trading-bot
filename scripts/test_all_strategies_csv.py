#!/usr/bin/env python3
"""
Comprehensive Strategy Testing with CSV Historical Data
========================================================
Tests ALL available strategies on quality 180-day CSV data to find
strategies that actually work on real market data.

Context:
- Grid Trading v1 FAILED (0.1% win rate on real data vs 32.6% on synthetic)
- Need to find strategies with: win rate >45%, Sharpe >1.0, drawdown <15%

FIX: BacktestEngine doesn't notify strategy when positions close via SL/TP
     This version includes a patched engine that properly syncs position state.

Data Source: <repo>/data/historical/
File Format: {SYMBOL}_180days_20251208.csv

Author: Strategy Testing Framework
Date: 2025-12-08
"""

import sys
from pathlib import Path as _Path

_REPO_ROOT = _Path(__file__).resolve().parent.parent
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass
import pandas as pd
import numpy as np

# Add project root to path for imports
PROJECT_ROOT = str(_REPO_ROOT / "")
sys.path.insert(0, os.path.join(PROJECT_ROOT, "services", "trading-engine"))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# THIS script produced comprehensive/grid/sr/trend_FINAL_RESULTS.log (Dec 2025),
# not backtesting/backtest_engine.py. Its own PatchedBacktestEngine wraps the
# trading-engine service's backtester, and initial_equity was hardcoded 10000.0
# below -- a 100x account. Sourced from the declaration of record as of
# 2026-08-03. Do NOT let autoflake strip this import.
from shared.account import PAPER_INITIAL_BALANCE  # noqa: E402,F401

# Import backtesting framework
from app.backtesting.backtest_engine import (
    BacktestConfig,
    BacktestResult,
    Position,
    Trade,
)
from app.backtesting.strategy_base import StrategyBase, Signal, SignalType, OHLCV
from app.backtesting.performance_metrics import calculate_all_metrics

# Configure logging
logging.basicConfig(
    level=logging.WARNING, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Constants
DATA_DIR = os.path.join(PROJECT_ROOT, "data", "historical")
LOG_FILE = "/tmp/all_strategies_csv_test.log"

SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "ADAUSDT",
    "APTUSDT",
    "DOTUSDT",
    "LTCUSDT",
    "POLUSDT",
    "AVAXUSDT",
]

# Performance thresholds
MIN_WIN_RATE = 45.0
MIN_SHARPE = 1.0
MAX_DRAWDOWN = 15.0


# =============================================================================
# PATCHED BACKTEST ENGINE - Properly syncs position state with strategy
# =============================================================================


class PatchedBacktestEngine:
    """
    Patched BacktestEngine that properly notifies the strategy
    when positions are closed via stop loss or take profit.
    """

    def __init__(self, config: Optional[BacktestConfig] = None):
        self.config = config or BacktestConfig()
        self._equity = self.config.initial_equity
        self._cash = self.config.initial_equity
        self._position: Optional[Position] = None
        self._trades: List[Trade] = []
        self._equity_curve: List[float] = []
        self._equity_timestamps: List[datetime] = []
        self._signals_generated = 0
        self._signals_executed = 0
        self._trade_counter = 0
        self._strategy: Optional[StrategyBase] = None

    def reset(self) -> None:
        self._equity = self.config.initial_equity
        self._cash = self.config.initial_equity
        self._position = None
        self._trades = []
        self._equity_curve = []
        self._equity_timestamps = []
        self._signals_generated = 0
        self._signals_executed = 0
        self._trade_counter = 0

    def run(
        self,
        strategy: StrategyBase,
        data: List[OHLCV],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> BacktestResult:
        self.reset()
        self._strategy = strategy

        if not data:
            raise ValueError("No data provided for backtest")

        strategy.on_start(self.config.initial_equity)

        for i, bar in enumerate(data):
            strategy.add_bar(bar)

            # Check stop loss / take profit BEFORE getting new signal
            if self._position:
                self._check_exit_conditions(bar)

            # Get signal from strategy
            signal = strategy.on_bar(bar, self._equity)

            if signal:
                self._signals_generated += 1
                self._process_signal(signal, bar, strategy)

            # Record equity
            current_equity = self._calculate_equity(bar.close)
            self._equity_curve.append(current_equity)
            self._equity_timestamps.append(bar.timestamp)

            if progress_callback and i % 100 == 0:
                progress_callback(i, len(data))

        # Close any remaining position
        if self._position:
            self._close_position(data[-1], "backtest_end")

        strategy.on_end(self._equity)

        # Calculate metrics
        metrics = calculate_all_metrics(
            equity_curve=self._equity_curve,
            trades=[t.to_dict() for t in self._trades],
            initial_equity=self.config.initial_equity,
            start_date=data[0].timestamp,
            end_date=data[-1].timestamp,
        )

        return BacktestResult(
            strategy_name=strategy.get_name(),
            symbol=strategy.symbol,
            config=self.config,
            metrics=metrics,
            trades=self._trades,
            equity_curve=self._equity_curve,
            equity_timestamps=self._equity_timestamps,
            signals_generated=self._signals_generated,
            signals_executed=self._signals_executed,
        )

    def _process_signal(
        self, signal: Signal, bar: OHLCV, strategy: StrategyBase
    ) -> None:
        if signal.signal_type == SignalType.BUY:
            if not self._position:
                self._open_position(signal, bar, "long", strategy)
        elif signal.signal_type == SignalType.SELL:
            if not self._position:
                self._open_position(signal, bar, "short", strategy)
        elif signal.signal_type == SignalType.CLOSE_LONG:
            if self._position and self._position.side == "long":
                self._close_position(bar, signal.metadata.get("exit_reason", "signal"))
        elif signal.signal_type == SignalType.CLOSE_SHORT:
            if self._position and self._position.side == "short":
                self._close_position(bar, signal.metadata.get("exit_reason", "signal"))

    def _open_position(
        self, signal: Signal, bar: OHLCV, side: str, strategy: StrategyBase
    ) -> None:
        position_size_pct = (
            self.config.position_size_pct * signal.position_size_pct / 100
        )
        position_value = self._cash * (position_size_pct / 100)

        slippage_amount = bar.close * (self.config.slippage_pct / 100)
        if side == "long":
            entry_price = bar.close + slippage_amount
        else:
            entry_price = bar.close - slippage_amount

        quantity = position_value / entry_price
        commission = position_value * (self.config.commission_pct / 100)

        self._position = Position(
            symbol=signal.symbol,
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            entry_time=bar.timestamp,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
        )

        self._cash -= position_value + commission
        strategy.update_position(side, entry_price)
        self._signals_executed += 1

    def _close_position(self, bar: OHLCV, exit_reason: str) -> None:
        if not self._position:
            return

        slippage_amount = bar.close * (self.config.slippage_pct / 100)
        if self._position.side == "long":
            exit_price = bar.close - slippage_amount
        else:
            exit_price = bar.close + slippage_amount

        if self._position.side == "long":
            pnl = (exit_price - self._position.entry_price) * self._position.quantity
        else:
            pnl = (self._position.entry_price - exit_price) * self._position.quantity

        position_value = exit_price * self._position.quantity
        commission = position_value * (self.config.commission_pct / 100)
        net_pnl = pnl - commission

        entry_value = self._position.entry_price * self._position.quantity
        pnl_pct = (pnl / entry_value) * 100 if entry_value > 0 else 0

        self._trade_counter += 1
        trade = Trade(
            trade_id=f"T{self._trade_counter:05d}",
            symbol=self._position.symbol,
            side=self._position.side,
            entry_price=self._position.entry_price,
            exit_price=exit_price,
            quantity=self._position.quantity,
            entry_time=self._position.entry_time,
            exit_time=bar.timestamp,
            pnl=net_pnl,
            pnl_pct=pnl_pct,
            commission=commission * 2,
            slippage=slippage_amount * 2,
            exit_reason=exit_reason,
        )
        self._trades.append(trade)

        self._cash += position_value + net_pnl
        self._position = None

        # FIX: Notify strategy that position is closed
        if self._strategy:
            self._strategy.update_position(None, None)

    def _check_exit_conditions(self, bar: OHLCV) -> None:
        if not self._position:
            return

        if self._position.side == "long":
            if self.config.use_stop_loss and self._position.stop_loss:
                if bar.low <= self._position.stop_loss:
                    self._close_position(bar, "stop_loss")
                    return
            if self.config.use_take_profit and self._position.take_profit:
                if bar.high >= self._position.take_profit:
                    self._close_position(bar, "take_profit")
                    return
        else:
            if self.config.use_stop_loss and self._position.stop_loss:
                if bar.high >= self._position.stop_loss:
                    self._close_position(bar, "stop_loss")
                    return
            if self.config.use_take_profit and self._position.take_profit:
                if bar.low <= self._position.take_profit:
                    self._close_position(bar, "take_profit")
                    return

    def _calculate_equity(self, current_price: float) -> float:
        equity = self._cash
        if self._position:
            position_value = self._position.quantity * current_price
            equity += position_value
        return equity


# =============================================================================
# RESULT DATA CLASS
# =============================================================================


@dataclass
class StrategyTestResult:
    strategy_name: str
    symbol: str
    win_rate: float
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    profit_factor: float
    avg_win: float
    avg_loss: float
    error: Optional[str] = None

    def passes_criteria(self) -> bool:
        if self.error:
            return False
        return (
            self.win_rate >= MIN_WIN_RATE
            and self.sharpe_ratio >= MIN_SHARPE
            and self.max_drawdown <= MAX_DRAWDOWN
            and self.total_trades >= 10
        )


# =============================================================================
# DATA LOADING
# =============================================================================


def load_csv_data(symbol: str) -> Tuple[List[OHLCV], pd.DataFrame]:
    csv_file = os.path.join(DATA_DIR, f"{symbol}_180days_20251208.csv")
    if not os.path.exists(csv_file):
        raise FileNotFoundError(f"CSV file not found: {csv_file}")

    df = pd.read_csv(csv_file)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    bars = []
    for _, row in df.iterrows():
        bars.append(
            OHLCV(
                timestamp=row["timestamp"].to_pydatetime(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
        )

    return bars, df


# =============================================================================
# STRATEGY ADAPTERS
# =============================================================================


class RSIMomentumAdapter(StrategyBase):
    """RSI Momentum - Buy oversold, sell overbought"""

    def __init__(self, symbol: str):
        super().__init__(symbol)
        self._rsi_period = 14
        self._oversold = 30
        self._overbought = 70
        self._prev_rsi = None

    def get_name(self) -> str:
        return "RSIMomentum"

    def on_bar(self, bar: OHLCV, equity: float) -> Optional[Signal]:
        if len(self._prices) < self._rsi_period + 1:
            return None

        rsi = self.rsi(self._rsi_period)
        atr = self.atr(14)

        if rsi is None or atr is None:
            self._prev_rsi = rsi
            return None

        signal = None

        if not self.has_position() and self._prev_rsi is not None:
            if self._prev_rsi <= self._oversold and rsi > self._oversold:
                signal = Signal(
                    signal_type=SignalType.BUY,
                    symbol=self.symbol,
                    price=bar.close,
                    timestamp=bar.timestamp,
                    confidence=0.7,
                    stop_loss=bar.close - (atr * 2.0),
                    take_profit=bar.close + (atr * 3.0),
                    metadata={"rsi": rsi},
                )
            elif self._prev_rsi >= self._overbought and rsi < self._overbought:
                signal = Signal(
                    signal_type=SignalType.SELL,
                    symbol=self.symbol,
                    price=bar.close,
                    timestamp=bar.timestamp,
                    confidence=0.7,
                    stop_loss=bar.close + (atr * 2.0),
                    take_profit=bar.close - (atr * 3.0),
                    metadata={"rsi": rsi},
                )
        elif self.is_long() and rsi >= self._overbought:
            signal = Signal(
                signal_type=SignalType.CLOSE_LONG,
                symbol=self.symbol,
                price=bar.close,
                timestamp=bar.timestamp,
                confidence=0.7,
                metadata={"exit": "overbought"},
            )
        elif self.is_short() and rsi <= self._oversold:
            signal = Signal(
                signal_type=SignalType.CLOSE_SHORT,
                symbol=self.symbol,
                price=bar.close,
                timestamp=bar.timestamp,
                confidence=0.7,
                metadata={"exit": "oversold"},
            )

        self._prev_rsi = rsi
        return signal


class EMACrossoverAdapter(StrategyBase):
    """EMA Crossover - Fast crosses slow"""

    def __init__(self, symbol: str):
        super().__init__(symbol)
        self._fast = 9
        self._slow = 21
        self._prev_fast = None
        self._prev_slow = None

    def get_name(self) -> str:
        return "EMACrossover"

    def on_bar(self, bar: OHLCV, equity: float) -> Optional[Signal]:
        if len(self._prices) < self._slow + 1:
            return None

        fast = self.ema(self._fast)
        slow = self.ema(self._slow)
        atr = self.atr(14)

        if any(x is None for x in [fast, slow, atr]):
            self._prev_fast, self._prev_slow = fast, slow
            return None

        signal = None

        if self._prev_fast is not None and self._prev_slow is not None:
            # Bullish crossover
            if self._prev_fast <= self._prev_slow and fast > slow:
                if not self.has_position():
                    signal = Signal(
                        signal_type=SignalType.BUY,
                        symbol=self.symbol,
                        price=bar.close,
                        timestamp=bar.timestamp,
                        confidence=0.65,
                        stop_loss=bar.close - (atr * 2.0),
                        take_profit=bar.close + (atr * 3.0),
                        metadata={"fast": fast, "slow": slow},
                    )
                elif self.is_short():
                    signal = Signal(
                        signal_type=SignalType.CLOSE_SHORT,
                        symbol=self.symbol,
                        price=bar.close,
                        timestamp=bar.timestamp,
                        confidence=0.7,
                        metadata={"exit": "bullish_crossover"},
                    )
            # Bearish crossover
            elif self._prev_fast >= self._prev_slow and fast < slow:
                if not self.has_position():
                    signal = Signal(
                        signal_type=SignalType.SELL,
                        symbol=self.symbol,
                        price=bar.close,
                        timestamp=bar.timestamp,
                        confidence=0.65,
                        stop_loss=bar.close + (atr * 2.0),
                        take_profit=bar.close - (atr * 3.0),
                        metadata={"fast": fast, "slow": slow},
                    )
                elif self.is_long():
                    signal = Signal(
                        signal_type=SignalType.CLOSE_LONG,
                        symbol=self.symbol,
                        price=bar.close,
                        timestamp=bar.timestamp,
                        confidence=0.7,
                        metadata={"exit": "bearish_crossover"},
                    )

        self._prev_fast, self._prev_slow = fast, slow
        return signal


class BollingerMeanReversionAdapter(StrategyBase):
    """Bollinger Band Mean Reversion"""

    def __init__(self, symbol: str):
        super().__init__(symbol)
        self._period = 20
        self._std = 2.0

    def get_name(self) -> str:
        return "BollingerMeanReversion"

    def on_bar(self, bar: OHLCV, equity: float) -> Optional[Signal]:
        if len(self._prices) < self._period + 1:
            return None

        bb = self._calc_bb()
        atr = self.atr(14)

        if bb is None or atr is None:
            return None

        lower, middle, upper = bb
        signal = None

        if bar.close <= lower and not self.has_position():
            signal = Signal(
                signal_type=SignalType.BUY,
                symbol=self.symbol,
                price=bar.close,
                timestamp=bar.timestamp,
                confidence=0.65,
                stop_loss=bar.close - (atr * 1.5),
                take_profit=middle,
                metadata={"bb_lower": lower},
            )
        elif bar.close >= upper and not self.has_position():
            signal = Signal(
                signal_type=SignalType.SELL,
                symbol=self.symbol,
                price=bar.close,
                timestamp=bar.timestamp,
                confidence=0.65,
                stop_loss=bar.close + (atr * 1.5),
                take_profit=middle,
                metadata={"bb_upper": upper},
            )
        elif self.is_long() and bar.close >= middle:
            signal = Signal(
                signal_type=SignalType.CLOSE_LONG,
                symbol=self.symbol,
                price=bar.close,
                timestamp=bar.timestamp,
                confidence=0.7,
                metadata={"exit": "reached_middle"},
            )
        elif self.is_short() and bar.close <= middle:
            signal = Signal(
                signal_type=SignalType.CLOSE_SHORT,
                symbol=self.symbol,
                price=bar.close,
                timestamp=bar.timestamp,
                confidence=0.7,
                metadata={"exit": "reached_middle"},
            )

        return signal

    def _calc_bb(self):
        if len(self._prices) < self._period:
            return None
        p = self._prices[-self._period :]
        m = sum(p) / len(p)
        s = np.std(p)
        return (m - self._std * s, m, m + self._std * s)


class RSIBBComboAdapter(StrategyBase):
    """RSI + Bollinger Band Combo"""

    def __init__(self, symbol: str):
        super().__init__(symbol)
        self._rsi_period = 14
        self._bb_period = 20
        self._bb_std = 2.0
        self._oversold = 35
        self._overbought = 65

    def get_name(self) -> str:
        return "RSI_BB_Combo"

    def on_bar(self, bar: OHLCV, equity: float) -> Optional[Signal]:
        if len(self._prices) < 25:
            return None

        rsi = self.rsi(self._rsi_period)
        bb = self._calc_bb()
        atr = self.atr(14)

        if rsi is None or bb is None or atr is None:
            return None

        lower, middle, upper = bb
        signal = None

        if (
            rsi < self._oversold
            and bar.close <= lower * 1.01
            and not self.has_position()
        ):
            signal = Signal(
                signal_type=SignalType.BUY,
                symbol=self.symbol,
                price=bar.close,
                timestamp=bar.timestamp,
                confidence=0.75,
                stop_loss=bar.close - (atr * 2.0),
                take_profit=bar.close + (atr * 3.0),
                metadata={"rsi": rsi, "bb_lower": lower},
            )
        elif (
            rsi > self._overbought
            and bar.close >= upper * 0.99
            and not self.has_position()
        ):
            signal = Signal(
                signal_type=SignalType.SELL,
                symbol=self.symbol,
                price=bar.close,
                timestamp=bar.timestamp,
                confidence=0.75,
                stop_loss=bar.close + (atr * 2.0),
                take_profit=bar.close - (atr * 3.0),
                metadata={"rsi": rsi, "bb_upper": upper},
            )
        elif self.is_long() and (rsi > self._overbought or bar.close >= middle):
            signal = Signal(
                signal_type=SignalType.CLOSE_LONG,
                symbol=self.symbol,
                price=bar.close,
                timestamp=bar.timestamp,
                confidence=0.7,
                metadata={"exit": "target"},
            )
        elif self.is_short() and (rsi < self._oversold or bar.close <= middle):
            signal = Signal(
                signal_type=SignalType.CLOSE_SHORT,
                symbol=self.symbol,
                price=bar.close,
                timestamp=bar.timestamp,
                confidence=0.7,
                metadata={"exit": "target"},
            )

        return signal

    def _calc_bb(self):
        if len(self._prices) < self._bb_period:
            return None
        p = self._prices[-self._bb_period :]
        m = sum(p) / len(p)
        s = np.std(p)
        return (m - self._bb_std * s, m, m + self._bb_std * s)


class MACDHistogramAdapter(StrategyBase):
    """MACD Histogram crossover"""

    def __init__(self, symbol: str):
        super().__init__(symbol)
        self._fast = 12
        self._slow = 26
        self._signal = 9
        self._prev_hist = None

    def get_name(self) -> str:
        return "MACDHistogram"

    def on_bar(self, bar: OHLCV, equity: float) -> Optional[Signal]:
        if len(self._prices) < self._slow + self._signal + 1:
            return None

        macd, sig_line, hist = self._calc_macd()
        atr = self.atr(14)

        if any(x is None for x in [macd, hist, atr]):
            self._prev_hist = hist
            return None

        signal = None

        if self._prev_hist is not None:
            if self._prev_hist < 0 and hist > 0:
                if not self.has_position():
                    signal = Signal(
                        signal_type=SignalType.BUY,
                        symbol=self.symbol,
                        price=bar.close,
                        timestamp=bar.timestamp,
                        confidence=0.7,
                        stop_loss=bar.close - (atr * 2.0),
                        take_profit=bar.close + (atr * 3.0),
                        metadata={"histogram": hist},
                    )
                elif self.is_short():
                    signal = Signal(
                        signal_type=SignalType.CLOSE_SHORT,
                        symbol=self.symbol,
                        price=bar.close,
                        timestamp=bar.timestamp,
                        confidence=0.7,
                        metadata={"exit": "hist_flip"},
                    )
            elif self._prev_hist > 0 and hist < 0:
                if not self.has_position():
                    signal = Signal(
                        signal_type=SignalType.SELL,
                        symbol=self.symbol,
                        price=bar.close,
                        timestamp=bar.timestamp,
                        confidence=0.7,
                        stop_loss=bar.close + (atr * 2.0),
                        take_profit=bar.close - (atr * 3.0),
                        metadata={"histogram": hist},
                    )
                elif self.is_long():
                    signal = Signal(
                        signal_type=SignalType.CLOSE_LONG,
                        symbol=self.symbol,
                        price=bar.close,
                        timestamp=bar.timestamp,
                        confidence=0.7,
                        metadata={"exit": "hist_flip"},
                    )

        self._prev_hist = hist
        return signal

    def _calc_macd(self):
        if len(self._prices) < self._slow + self._signal:
            return None, None, None

        def ema_s(data, period):
            result = []
            mult = 2 / (period + 1)
            ema = sum(data[:period]) / period
            result.append(ema)
            for i in range(period, len(data)):
                ema = (data[i] * mult) + (ema * (1 - mult))
                result.append(ema)
            return result

        fast_ema = ema_s(self._prices, self._fast)
        slow_ema = ema_s(self._prices, self._slow)

        min_len = min(len(fast_ema), len(slow_ema))
        macd_line = [
            fast_ema[-(min_len - i)] - slow_ema[-(min_len - i)] for i in range(min_len)
        ]

        if len(macd_line) < self._signal:
            return None, None, None

        signal_ema = ema_s(macd_line, self._signal)
        return macd_line[-1], signal_ema[-1], macd_line[-1] - signal_ema[-1]


class TripleEMAAdapter(StrategyBase):
    """Triple EMA alignment strategy"""

    def __init__(self, symbol: str):
        super().__init__(symbol)
        self._ema1 = 9
        self._ema2 = 21
        self._ema3 = 55

    def get_name(self) -> str:
        return "TripleEMA"

    def on_bar(self, bar: OHLCV, equity: float) -> Optional[Signal]:
        if len(self._prices) < self._ema3 + 1:
            return None

        e1 = self.ema(self._ema1)
        e2 = self.ema(self._ema2)
        e3 = self.ema(self._ema3)
        atr = self.atr(14)

        if any(x is None for x in [e1, e2, e3, atr]):
            return None

        signal = None

        # Bullish: price > e1 > e2 > e3
        if bar.close > e1 > e2 > e3:
            if not self.has_position():
                signal = Signal(
                    signal_type=SignalType.BUY,
                    symbol=self.symbol,
                    price=bar.close,
                    timestamp=bar.timestamp,
                    confidence=0.7,
                    stop_loss=bar.close - (atr * 2.0),
                    take_profit=bar.close + (atr * 3.5),
                    metadata={"alignment": "bullish"},
                )
            elif self.is_short():
                signal = Signal(
                    signal_type=SignalType.CLOSE_SHORT,
                    symbol=self.symbol,
                    price=bar.close,
                    timestamp=bar.timestamp,
                    confidence=0.7,
                    metadata={"exit": "bullish_alignment"},
                )
        # Bearish: price < e1 < e2 < e3
        elif bar.close < e1 < e2 < e3:
            if not self.has_position():
                signal = Signal(
                    signal_type=SignalType.SELL,
                    symbol=self.symbol,
                    price=bar.close,
                    timestamp=bar.timestamp,
                    confidence=0.7,
                    stop_loss=bar.close + (atr * 2.0),
                    take_profit=bar.close - (atr * 3.5),
                    metadata={"alignment": "bearish"},
                )
            elif self.is_long():
                signal = Signal(
                    signal_type=SignalType.CLOSE_LONG,
                    symbol=self.symbol,
                    price=bar.close,
                    timestamp=bar.timestamp,
                    confidence=0.7,
                    metadata={"exit": "bearish_alignment"},
                )

        # Exit on middle EMA break
        if self.is_long() and bar.close < e2:
            signal = Signal(
                signal_type=SignalType.CLOSE_LONG,
                symbol=self.symbol,
                price=bar.close,
                timestamp=bar.timestamp,
                confidence=0.65,
                metadata={"exit": "ema2_break"},
            )
        elif self.is_short() and bar.close > e2:
            signal = Signal(
                signal_type=SignalType.CLOSE_SHORT,
                symbol=self.symbol,
                price=bar.close,
                timestamp=bar.timestamp,
                confidence=0.65,
                metadata={"exit": "ema2_break"},
            )

        return signal


class StochasticRSIAdapter(StrategyBase):
    """Stochastic RSI strategy"""

    def __init__(self, symbol: str):
        super().__init__(symbol)
        self._rsi_period = 14
        self._stoch_period = 14
        self._oversold = 20
        self._overbought = 80

    def get_name(self) -> str:
        return "StochasticRSI"

    def on_bar(self, bar: OHLCV, equity: float) -> Optional[Signal]:
        if len(self._prices) < self._rsi_period + self._stoch_period + 1:
            return None

        stoch_rsi = self._calc_stoch_rsi()
        atr = self.atr(14)

        if stoch_rsi is None or atr is None:
            return None

        signal = None

        if stoch_rsi < self._oversold and not self.has_position():
            signal = Signal(
                signal_type=SignalType.BUY,
                symbol=self.symbol,
                price=bar.close,
                timestamp=bar.timestamp,
                confidence=0.7,
                stop_loss=bar.close - (atr * 2.0),
                take_profit=bar.close + (atr * 3.0),
                metadata={"stoch_rsi": stoch_rsi},
            )
        elif stoch_rsi > self._overbought and not self.has_position():
            signal = Signal(
                signal_type=SignalType.SELL,
                symbol=self.symbol,
                price=bar.close,
                timestamp=bar.timestamp,
                confidence=0.7,
                stop_loss=bar.close + (atr * 2.0),
                take_profit=bar.close - (atr * 3.0),
                metadata={"stoch_rsi": stoch_rsi},
            )
        elif self.is_long() and stoch_rsi > self._overbought:
            signal = Signal(
                signal_type=SignalType.CLOSE_LONG,
                symbol=self.symbol,
                price=bar.close,
                timestamp=bar.timestamp,
                confidence=0.7,
                metadata={"exit": "overbought"},
            )
        elif self.is_short() and stoch_rsi < self._oversold:
            signal = Signal(
                signal_type=SignalType.CLOSE_SHORT,
                symbol=self.symbol,
                price=bar.close,
                timestamp=bar.timestamp,
                confidence=0.7,
                metadata={"exit": "oversold"},
            )

        return signal

    def _calc_stoch_rsi(self):
        if len(self._prices) < self._rsi_period + self._stoch_period:
            return None

        rsi_values = []
        for i in range(self._stoch_period):
            idx = len(self._prices) - self._stoch_period + i
            if idx < self._rsi_period:
                continue

            prices_slice = self._prices[: idx + 1]
            if len(prices_slice) < self._rsi_period + 1:
                continue

            deltas = [
                prices_slice[j] - prices_slice[j - 1]
                for j in range(1, len(prices_slice))
            ]
            gains = [d if d > 0 else 0 for d in deltas[-self._rsi_period :]]
            losses = [-d if d < 0 else 0 for d in deltas[-self._rsi_period :]]

            avg_gain = sum(gains) / self._rsi_period
            avg_loss = sum(losses) / self._rsi_period

            if avg_loss == 0:
                rsi = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))

            rsi_values.append(rsi)

        if len(rsi_values) < 2:
            return None

        rsi_min, rsi_max = min(rsi_values), max(rsi_values)
        if rsi_max == rsi_min:
            return 50.0

        return ((rsi_values[-1] - rsi_min) / (rsi_max - rsi_min)) * 100


# =============================================================================
# TESTING FUNCTIONS
# =============================================================================


def create_config() -> BacktestConfig:
    return BacktestConfig(
        initial_equity=PAPER_INITIAL_BALANCE,
        commission_pct=0.1,
        slippage_pct=0.05,
        position_size_pct=2.0,
        max_positions=5,
        use_stop_loss=True,
        use_take_profit=True,
    )


def run_test(
    strategy_class, symbol: str, bars: List[OHLCV], config: BacktestConfig
) -> StrategyTestResult:
    try:
        strategy = strategy_class(symbol)
        engine = PatchedBacktestEngine(config)
        result: BacktestResult = engine.run(strategy, bars)
        m = result.metrics

        return StrategyTestResult(
            strategy_name=strategy.get_name(),
            symbol=symbol,
            win_rate=m.win_rate,
            total_return=m.total_return_pct,
            sharpe_ratio=m.sharpe_ratio,
            max_drawdown=m.max_drawdown_pct,
            total_trades=m.total_trades,
            winning_trades=m.winning_trades,
            losing_trades=m.losing_trades,
            profit_factor=m.profit_factor,
            avg_win=m.avg_win,
            avg_loss=m.avg_loss,
        )
    except Exception as e:
        return StrategyTestResult(
            strategy_name=strategy_class.__name__.replace("Adapter", ""),
            symbol=symbol,
            win_rate=0,
            total_return=0,
            sharpe_ratio=0,
            max_drawdown=0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            profit_factor=0,
            avg_win=0,
            avg_loss=0,
            error=str(e),
        )


def test_all():
    strategies = {
        "RSIMomentum": RSIMomentumAdapter,
        "EMACrossover": EMACrossoverAdapter,
        "BollingerMeanReversion": BollingerMeanReversionAdapter,
        "RSI_BB_Combo": RSIBBComboAdapter,
        "MACDHistogram": MACDHistogramAdapter,
        "TripleEMA": TripleEMAAdapter,
        "StochasticRSI": StochasticRSIAdapter,
    }

    excluded = {
        "FundingRateArbitrage": "Requires funding rate data",
        "PairsTrading": "Requires two correlated symbols",
        "TriangularArbitrage": "Requires three symbols",
    }

    config = create_config()
    all_results: Dict[str, List[StrategyTestResult]] = {}

    print("=" * 80)
    print("COMPREHENSIVE STRATEGY TESTING - CSV DATA (PATCHED ENGINE)")
    print("=" * 80)
    print(
        f"\nTesting {len(strategies)} strategies on {len(SYMBOLS)} symbols (180 days)"
    )
    print(
        f"Criteria: Win Rate >{MIN_WIN_RATE}%, Sharpe >{MIN_SHARPE}, Drawdown <{MAX_DRAWDOWN}%"
    )
    print("\nExcluded:")
    for name, reason in excluded.items():
        print(f"  - {name}: {reason}")
    print()

    # Load data
    symbol_data: Dict[str, Tuple[List[OHLCV], pd.DataFrame]] = {}
    print("Loading CSV data...")
    for symbol in SYMBOLS:
        try:
            bars, df = load_csv_data(symbol)
            symbol_data[symbol] = (bars, df)
            print(f"  {symbol}: {len(bars)} bars")
        except Exception as e:
            print(f"  {symbol}: ERROR - {e}")
    print()

    # Test each strategy
    for strat_idx, (strat_name, strat_class) in enumerate(strategies.items(), 1):
        print(f"[{strat_idx}/{len(strategies)}] {strat_name}")
        print("-" * 60)

        all_results[strat_name] = []

        for symbol in SYMBOLS:
            if symbol not in symbol_data:
                continue

            bars, _ = symbol_data[symbol]
            result = run_test(strat_class, symbol, bars, config)
            all_results[strat_name].append(result)

            if result.error:
                print(f"  {symbol}: ERROR - {result.error[:40]}")
            else:
                status = "[OK]" if result.passes_criteria() else "[--]"
                print(
                    f"  {symbol}: {result.win_rate:5.1f}% WR, {result.total_return:+8.2f}% ret, "
                    f"{result.sharpe_ratio:5.2f} Sharpe, {result.max_drawdown:5.1f}% DD, "
                    f"{result.total_trades:4d} trades {status}"
                )

        valid = [r for r in all_results[strat_name] if not r.error]
        if valid:
            avg_wr = sum(r.win_rate for r in valid) / len(valid)
            avg_ret = sum(r.total_return for r in valid) / len(valid)
            avg_sharpe = sum(r.sharpe_ratio for r in valid) / len(valid)
            avg_dd = sum(r.max_drawdown for r in valid) / len(valid)
            total_t = sum(r.total_trades for r in valid)
            passes = sum(1 for r in valid if r.passes_criteria())
            status = "PASS" if passes >= len(valid) * 0.6 else "FAIL"
            print(
                f"  {'AVERAGE':<8}: {avg_wr:5.1f}% WR, {avg_ret:+8.2f}% ret, "
                f"{avg_sharpe:5.2f} Sharpe, {avg_dd:5.1f}% DD, {total_t:4d} total"
            )
            print(f"  Status: {status} ({passes}/{len(valid)} passed)")
        print()

    return all_results


def print_comparison(all_results: Dict[str, List[StrategyTestResult]]):
    print("=" * 100)
    print("STRATEGY COMPARISON")
    print("=" * 100)
    print()
    print(
        f"{'Strategy':<25} {'Win Rate':>10} {'Return':>12} {'Sharpe':>10} {'Drawdown':>10} {'Trades':>8} {'Status':>10}"
    )
    print("-" * 100)

    scores = []
    for name, results in all_results.items():
        valid = [r for r in results if not r.error]
        if not valid:
            print(
                f"{name:<25} {'N/A':>10} {'N/A':>12} {'N/A':>10} {'N/A':>10} {'N/A':>8} {'ERROR':>10}"
            )
            continue

        avg_wr = sum(r.win_rate for r in valid) / len(valid)
        avg_ret = sum(r.total_return for r in valid) / len(valid)
        avg_sharpe = sum(r.sharpe_ratio for r in valid) / len(valid)
        avg_dd = sum(r.max_drawdown for r in valid) / len(valid)
        total_t = sum(r.total_trades for r in valid)

        status = (
            "PASS"
            if (
                avg_wr >= MIN_WIN_RATE
                and avg_sharpe >= MIN_SHARPE
                and avg_dd <= MAX_DRAWDOWN
                and total_t >= 50
            )
            else "FAIL"
        )
        print(
            f"{name:<25} {avg_wr:>9.1f}% {avg_ret:>+11.2f}% {avg_sharpe:>10.2f} {avg_dd:>9.1f}% {total_t:>8} {status:>10}"
        )

        score = (
            (avg_wr / 100) * 0.3
            + avg_sharpe * 0.3
            + (avg_ret / 100) * 0.2
            + (1 - avg_dd / 100) * 0.2
        )
        scores.append((name, score, status, avg_wr, avg_sharpe, avg_ret, total_t))

    print("-" * 100)

    scores.sort(key=lambda x: x[1], reverse=True)
    print("\nTOP PERFORMERS:")
    for i, (name, score, status, wr, sharpe, ret, trades) in enumerate(scores[:5], 1):
        print(
            f"  {i}. {name}: score={score:.3f}, {wr:.1f}% WR, {sharpe:.2f} Sharpe, {ret:+.1f}% ret, {trades} trades ({status})"
        )

    viable = [s for s in scores if s[2] == "PASS"]
    print()
    if viable:
        print(f"FOUND {len(viable)} VIABLE STRATEGIES:")
        for name, _, _, wr, sharpe, ret, trades in viable:
            print(
                f"  - {name}: {wr:.1f}% win rate, {sharpe:.2f} Sharpe, {ret:+.1f}% return"
            )
    else:
        print("NO STRATEGIES MEET ALL CRITERIA")
        print("\nBest candidates for optimization:")
        for name, score, status, wr, sharpe, ret, trades in scores[:3]:
            issues = []
            if wr < MIN_WIN_RATE:
                issues.append(f"WR {wr:.1f}%<{MIN_WIN_RATE}%")
            if sharpe < MIN_SHARPE:
                issues.append(f"Sharpe {sharpe:.2f}<{MIN_SHARPE}")
            if trades < 50:
                issues.append(f"Trades {trades}<50")
            print(f"  - {name}: {', '.join(issues) if issues else 'Close'}")


def save_results(all_results: Dict[str, List[StrategyTestResult]]):
    with open(LOG_FILE, "w") as f:
        f.write("=" * 80 + "\n")
        f.write("COMPREHENSIVE STRATEGY TEST RESULTS\n")
        f.write(f"Generated: {datetime.now()}\n")
        f.write("=" * 80 + "\n\n")

        for name, results in all_results.items():
            f.write(f"\n{'=' * 60}\n{name}\n{'=' * 60}\n")
            for r in results:
                if r.error:
                    f.write(f"{r.symbol}: ERROR - {r.error}\n")
                else:
                    f.write(
                        f"{r.symbol}: WR={r.win_rate:.1f}%, Ret={r.total_return:+.2f}%, "
                        f"Sharpe={r.sharpe_ratio:.2f}, DD={r.max_drawdown:.1f}%, "
                        f"Trades={r.total_trades}, PF={r.profit_factor:.2f}\n"
                    )

    print(f"\nDetailed results saved to: {LOG_FILE}")


def main():
    print()
    print("=" * 80)
    print("COMPREHENSIVE STRATEGY TESTING - CSV DATA")
    print("=" * 80)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Goal: WR >{MIN_WIN_RATE}%, Sharpe >{MIN_SHARPE}, DD <{MAX_DRAWDOWN}%")
    print("Baseline: Grid Trading v1 = 0.1% win rate (FAILED)")
    print("FIX: Using patched engine with proper position sync")
    print("=" * 80)
    print()

    all_results = test_all()
    print()
    print_comparison(all_results)
    save_results(all_results)

    print()
    print("=" * 80)
    print("TESTING COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
