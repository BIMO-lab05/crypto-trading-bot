#!/usr/bin/env python3
"""
Backtesting Engine for Crypto Trading Bot
Tests trading strategies on historical data to validate effectiveness
"""

import os
import sys

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging

# ---------------------------------------------------------------------------
# Repo root on sys.path so `shared.account` resolves however this module is
# invoked. Mirrors the existing bootstrap in `backtesting/run_walk_forward.py`
# and `backtesting/simulators/monte_carlo.py` — not a new pattern.
#
# This file is HOST-RUN ONLY: repo-root `backtesting/` appears in no compose
# service and no Dockerfile copies it, so unlike code under `services/*/app/**`
# it MAY import the declaration of record directly. See `shared/account.py`.
#
# 2026-08-03: this engine defaulted to $10,000 and was MISSED by the capital
# audit, which caught `simulators/` but not the engine that actually produces
# the walk-forward evidence. Every result in `*_FINAL_RESULTS.log` (Dec 2025)
# was therefore computed on a 100x account.
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Used as the `initial_capital` default below. Do NOT let autoflake strip this —
# it has been removed once already (see the same failure mode in main.py, commit
# 6b48272). If it disappears, BacktestEngine raises NameError at import.
from shared.account import PAPER_INITIAL_BALANCE  # noqa: E402,F401

# Fee defaults come from the one cost model (services/trading-engine/app/
# costs.py) rather than hand-copied literals: the copies drifted — this file
# shipped `bybit_maker_fee = -0.0001` ("maker rebate"), but Bybit pays maker
# rebates only at MM/high-VIP tiers a $100 account cannot reach. Maker is a
# +2bp CHARGE. Top-level import first (killtests put backtesting/ on sys.path);
# package fallback for `from backtesting.backtest_engine import ...` callers.
try:
    from costs_loader import load_costs  # noqa: E402
except ImportError:  # imported as backtesting.backtest_engine from repo root
    from backtesting.costs_loader import load_costs  # noqa: E402

_BYBIT_PERP_FEES = load_costs().FeeSchedule.bybit_linear_perp()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OrderType(Enum):
    """Order types for backtesting"""

    BUY = "BUY"
    SELL = "SELL"


@dataclass
class Trade:
    """Represents a completed trade"""

    entry_time: datetime  # When the trade was opened
    exit_time: datetime  # When the trade was closed
    entry_price: float  # Entry price
    exit_price: float  # Exit price
    order_type: OrderType  # BUY or SELL
    position_size: float  # Position size (in base currency)
    profit_loss: float  # Profit/Loss in USD
    profit_loss_pct: float  # Profit/Loss percentage
    stop_loss: Optional[float] = None  # Stop loss price
    take_profit: Optional[float] = None  # Take profit price
    exit_reason: str = "signal"  # Why trade was closed (signal, stop_loss, take_profit)
    metadata: Dict = field(default_factory=dict)  # Additional trade data


@dataclass
class Position:
    """Represents an open position"""

    entry_time: datetime
    entry_price: float
    order_type: OrderType
    position_size: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    metadata: Dict = field(default_factory=dict)


@dataclass
class BacktestResult:
    """Results from a backtest run"""

    # Performance metrics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float

    # P&L metrics
    total_profit_loss: float
    total_profit_loss_pct: float
    avg_profit_per_trade: float
    avg_win: float
    avg_loss: float

    # Risk metrics
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    profit_factor: float  # Gross profit / Gross loss

    # Additional metrics
    avg_trade_duration_hours: float
    best_trade: float
    worst_trade: float

    # Trade history
    trades: List[Trade]
    equity_curve: List[float]

    # Strategy-specific
    strategy_name: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float


class BacktestEngine:
    """
    Backtesting engine that simulates trading strategies on historical data
    """

    def __init__(
        self,
        initial_capital: float = PAPER_INITIAL_BALANCE,
        position_size_pct: float = 0.02,  # 2% per trade
        commission: float = 0.001,  # 0.1% commission (LEGACY symmetric mode)
        slippage: float = 0.0005,  # 0.05% slippage (LEGACY fixed mode)
        # ===================== Realistic-sim knobs (ADR-013 phase B-4) =====================
        # All defaults are backward-compatible with the legacy single-rate
        # commission + fixed slippage model. Pass a non-default `fee_mode` /
        # `slippage_mode` / `funding_enabled` to engage the realistic models.
        fee_mode: str = "fixed",  # 'fixed' | 'bybit_perp'
        bybit_taker_fee: float = float(_BYBIT_PERP_FEES.taker),  # +0.055% taker
        bybit_maker_fee: float = float(
            _BYBIT_PERP_FEES.maker
        ),  # +0.020% maker — a CHARGE, not a rebate
        slippage_mode: str = "fixed",  # 'fixed' | 'atr_aware'
        atr_slippage_factor: float = 0.05,  # 5% of ATR/price as slippage in atr_aware mode
        atr_slippage_floor: float = 0.0005,  # never below 5 bps even in calm regime
        funding_enabled: bool = False,
        funding_rate_per_8h: float = 0.0001,  # 0.01% per 8h ≈ 0.03% per day baseline; user can pass historical
        funding_long_pays: bool = True,  # longs pay funding when positive (most common in bull)
        partial_fill_volume_pct: float = 0.0,  # 0 = disabled. Cap fill at this fraction of bar volume.
    ):
        """
        Initialize backtesting engine

        Args:
            initial_capital: Starting capital in USD
            position_size_pct: Percentage of capital to risk per trade
            commission: Legacy symmetric commission (used when fee_mode='fixed')
            slippage: Legacy fixed slippage (used when slippage_mode='fixed')
            fee_mode: 'fixed' (legacy) or 'bybit_perp' (asymmetric maker/taker)
            bybit_taker_fee, bybit_maker_fee: rates used in 'bybit_perp' mode
            slippage_mode: 'fixed' (legacy) or 'atr_aware' (scales with ATR/price)
            atr_slippage_factor: multiplier on ATR/price ratio
            atr_slippage_floor: minimum slippage even in calm regime
            funding_enabled: deduct funding cost every 8 hourly bars on open longs
            funding_rate_per_8h: positive rate => longs pay
            funding_long_pays: if True, longs pay when rate > 0 (default)
            partial_fill_volume_pct: cap fill at this fraction of bar volume (0 = disabled)
        """
        self.initial_capital = initial_capital
        self.position_size_pct = position_size_pct
        self.commission = commission
        self.slippage = slippage
        self.fee_mode = fee_mode
        self.bybit_taker_fee = bybit_taker_fee
        self.bybit_maker_fee = bybit_maker_fee
        self.slippage_mode = slippage_mode
        self.atr_slippage_factor = atr_slippage_factor
        self.atr_slippage_floor = atr_slippage_floor
        self.funding_enabled = funding_enabled
        self.funding_rate_per_8h = funding_rate_per_8h
        self.funding_long_pays = funding_long_pays
        self.partial_fill_volume_pct = partial_fill_volume_pct

        # State variables
        self.capital = initial_capital
        self.equity_curve = [initial_capital]
        self.trades: List[Trade] = []
        self.current_position: Optional[Position] = None
        self._bar_count = 0
        self._pending_signal: Optional[Dict] = None  # invariant A: fill at next open
        self._last_funding_time: Optional[datetime] = None

        logger.info(
            f"BacktestEngine initialized with ${initial_capital:,.2f} "
            f"(fee_mode={fee_mode}, slippage_mode={slippage_mode}, "
            f"funding_enabled={funding_enabled})"
        )

    def _effective_fee_rate(self, order_type_str: str = "MARKET") -> float:
        """
        Per-side fee rate. order_type_str hint lets the strategy pass
        'MARKET' (taker) or 'LIMIT' (maker — a smaller CHARGE, not a rebate;
        this account's tier earns none).
        """
        if self.fee_mode == "bybit_perp":
            if order_type_str.upper() == "LIMIT":
                return self.bybit_maker_fee
            return self.bybit_taker_fee
        return self.commission

    def _effective_slippage(self, atr_value: Optional[float], price: float) -> float:
        """ATR-aware slippage when enabled, else legacy fixed."""
        if self.slippage_mode == "atr_aware" and atr_value and price > 0:
            atr_pct = atr_value / price
            slip = self.atr_slippage_factor * atr_pct
            return max(slip, self.atr_slippage_floor)
        return self.slippage

    def _apply_funding(self, current_price: float, current_time: datetime) -> None:
        """Settle funding every 8 elapsed HOURS on any open position.

        Gap-audit fixes (audit/FINDINGS-GAP.md #2/#3): the old version
        charged longs only — shorts were simulated funding-free — and its
        cadence counted 8 *bars*, which is 8h only on hourly data. With a
        positive rate (funding_long_pays=True) longs pay and shorts RECEIVE;
        funding_long_pays=False inverts both. Cadence is wall-clock time
        since the last settlement, so 4h/daily data settles correctly.
        """
        if not self.funding_enabled or not self.current_position:
            return
        if self._last_funding_time is None:
            self._last_funding_time = current_time
            return
        if current_time - self._last_funding_time < timedelta(hours=8):
            return
        self._last_funding_time = current_time
        position_value = self.current_position.position_size * current_price
        funding_amount = position_value * self.funding_rate_per_8h
        is_long = self.current_position.order_type == OrderType.BUY
        pays = is_long == self.funding_long_pays
        self.capital += -funding_amount if pays else funding_amount
        logger.debug(
            f"funding {'paid' if pays else 'received'}: ${funding_amount:.4f} on "
            f"{'long' if is_long else 'short'} "
            f"(rate={self.funding_rate_per_8h * 100:.4f}%/8h, "
            f"value=${position_value:.2f}) at {current_time}"
        )

    def reset(self):
        """Reset backtest state"""
        self.capital = self.initial_capital
        self.equity_curve = [self.initial_capital]
        self.trades = []
        self.current_position = None
        self._bar_count = 0
        self._pending_signal = None
        self._last_funding_time = None

    def run_backtest(
        self, data: pd.DataFrame, strategy_func, strategy_name: str = "Unknown Strategy"
    ) -> BacktestResult:
        """
        Run backtest on historical data using a strategy function

        Args:
            data: DataFrame with columns: timestamp, open, high, low, close, volume
            strategy_func: Function that takes (row, position) and returns signal dict
            strategy_name: Name of the strategy

        Returns:
            BacktestResult with performance metrics
        """
        logger.info(f"Running backtest: {strategy_name}")
        # Handle both datetime index and timestamp column for logging
        if isinstance(data.index[0], (pd.Timestamp, datetime)):
            logger.info(f"Data range: {data.index[0]} to {data.index[-1]}")
        elif "timestamp" in data.columns:
            logger.info(
                f"Data range: {data.iloc[0]['timestamp']} to {data.iloc[-1]['timestamp']}"
            )
        logger.info(f"Total candles: {len(data)}")

        self.reset()

        # Iterate through historical data
        row_position = 0  # Integer position counter for strategy function
        for idx, row in data.iterrows():
            current_price = row["close"]
            # Handle both datetime index and timestamp column
            if isinstance(idx, (pd.Timestamp, datetime)):
                current_time = idx
            elif "timestamp" in row:
                current_time = pd.to_datetime(row["timestamp"])
            else:
                current_time = datetime.now()  # Fallback

            # Invariant A (gap audit 2026-08-19): a signal derived from bar
            # t's close fills no earlier than bar t+1's open. Execute the
            # previous bar's signal here, at this bar's open, before anything
            # else happens on this bar.
            if self._pending_signal is not None:
                fill_price = float(row["open"]) if "open" in row else current_price
                self._execute_signal(
                    self._pending_signal, fill_price, current_time, row
                )
                self._pending_signal = None

            # Apply funding before exit checks so a long that flipped past
            # an 8h boundary pays funding before stop-loss / take-profit
            # decides whether to close on this bar.
            self._apply_funding(current_price, current_time)

            # Check stop loss and take profit for open position
            if self.current_position:
                exit_reason = self._check_exit_conditions(row, current_time)
                if exit_reason:
                    self._close_position(current_price, current_time, exit_reason)

            # Get strategy signal - pass row_position (int) instead of idx (which may be Timestamp)
            signal = strategy_func(row, self.current_position, row_position, data)
            row_position += 1  # Increment position counter

            # Defer execution to the next bar's open (invariant A). A signal
            # on the final bar is dropped — it could never have been filled.
            if signal:
                self._pending_signal = signal

            # Update equity curve
            current_equity = self._calculate_equity(current_price)
            self.equity_curve.append(current_equity)
            self._bar_count += 1

        # Close any open position at the end
        if self.current_position:
            final_price = data.iloc[-1]["close"]
            # Handle both datetime index and timestamp column
            if isinstance(data.index[-1], (pd.Timestamp, datetime)):
                final_time = data.index[-1]
            elif "timestamp" in data.columns:
                final_time = pd.to_datetime(data.iloc[-1]["timestamp"])
            else:
                final_time = datetime.now()
            self._close_position(final_price, final_time, "end_of_data")

        # Calculate results
        result = self._calculate_results(strategy_name, data)

        logger.info(f"Backtest complete: {len(self.trades)} trades")
        logger.info(f"Win rate: {result.win_rate:.2f}%")
        logger.info(
            f"Total P&L: ${result.total_profit_loss:,.2f} ({result.total_profit_loss_pct:.2f}%)"
        )

        return result

    def _check_exit_conditions(
        self, row: pd.Series, current_time: datetime
    ) -> Optional[str]:
        """Check if stop loss or take profit is hit"""
        if not self.current_position:
            return None

        high = row["high"]
        low = row["low"]

        if self.current_position.order_type == OrderType.BUY:
            # Check stop loss (below entry)
            if (
                self.current_position.stop_loss
                and low <= self.current_position.stop_loss
            ):
                return "stop_loss"

            # Check take profit (above entry)
            if (
                self.current_position.take_profit
                and high >= self.current_position.take_profit
            ):
                return "take_profit"

        elif self.current_position.order_type == OrderType.SELL:
            # Check stop loss (above entry)
            if (
                self.current_position.stop_loss
                and high >= self.current_position.stop_loss
            ):
                return "stop_loss"

            # Check take profit (below entry)
            if (
                self.current_position.take_profit
                and low <= self.current_position.take_profit
            ):
                return "take_profit"

        return None

    def _execute_signal(
        self, signal: Dict, price: float, time: datetime, row: pd.Series
    ):
        """Execute a trading signal"""
        action = signal.get("action")

        if action == "BUY" and not self.current_position:
            self._open_position(OrderType.BUY, price, time, signal)

        elif action == "SELL" and not self.current_position:
            self._open_position(OrderType.SELL, price, time, signal)

        elif action == "HOLD" and self.current_position:
            # Close position on HOLD signal
            self._close_position(price, time, "signal")

    def _open_position(
        self, order_type: OrderType, price: float, time: datetime, signal: Dict
    ):
        """Open a new position"""
        # Calculate position size
        risk_amount = self.capital * self.position_size_pct
        position_size = risk_amount / price

        # Optional partial-fill cap (B-4): respect bar volume so the backtest
        # doesn't assume infinite liquidity at the close price.
        if self.partial_fill_volume_pct > 0:
            try:
                bar_volume = float(signal.get("_bar_volume") or 0.0)
            except (TypeError, ValueError):
                bar_volume = 0.0
            if bar_volume > 0:
                cap_qty = bar_volume * self.partial_fill_volume_pct
                if position_size > cap_qty:
                    logger.debug(
                        f"partial fill cap: requested {position_size:.6f} -> {cap_qty:.6f} "
                        f"(bar_volume={bar_volume:.2f}, pct={self.partial_fill_volume_pct})"
                    )
                    position_size = cap_qty

        # Apply slippage (ATR-aware when configured; legacy fixed otherwise)
        atr_value = signal.get("atr") if isinstance(signal, dict) else None
        slip = self._effective_slippage(atr_value, price)
        if order_type == OrderType.BUY:
            entry_price = price * (1 + slip)
        else:
            entry_price = price * (1 - slip)

        # Asymmetric fee model (B-4): MARKET => taker, LIMIT => maker (smaller
        # charge). Only a signal that declares a genuinely-resting limit entry
        # gets maker treatment.
        order_type_str = (
            signal.get("order_type") if isinstance(signal, dict) else None
        ) or "MARKET"
        fee_rate = self._effective_fee_rate(order_type_str)
        commission_cost = position_size * entry_price * fee_rate
        self.capital -= commission_cost

        # Get stop loss and take profit from signal
        stop_loss = signal.get("stop_loss")
        take_profit = signal.get("take_profit")

        self.current_position = Position(
            entry_time=time,
            entry_price=entry_price,
            order_type=order_type,
            position_size=position_size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            metadata=signal.get("metadata", {}),
        )

        logger.debug(
            f"Opened {order_type.value} position at ${entry_price:.2f}, size: {position_size:.4f}"
        )

    def _close_position(self, price: float, time: datetime, reason: str):
        """Close current position"""
        if not self.current_position:
            return

        # Determine exit price based on reason
        if reason == "stop_loss":
            exit_price = self.current_position.stop_loss
        elif reason == "take_profit":
            exit_price = self.current_position.take_profit
        else:
            # Apply slippage on time/signal-driven exits. Use ATR-aware mode
            # when configured; legacy fixed slippage otherwise. Stop/TP exits
            # use their pre-set price (no extra slippage applied beyond
            # whatever the strategy already baked into the level).
            atr_value = (self.current_position.metadata or {}).get("atr")
            slip = self._effective_slippage(atr_value, price)
            if self.current_position.order_type == OrderType.BUY:
                exit_price = price * (1 - slip)
            else:
                exit_price = price * (1 + slip)

        # Calculate P&L
        if self.current_position.order_type == OrderType.BUY:
            profit_loss = (
                exit_price - self.current_position.entry_price
            ) * self.current_position.position_size
        else:  # SELL
            profit_loss = (
                self.current_position.entry_price - exit_price
            ) * self.current_position.position_size

        # Every exit here is taker. Bybit conditional stop/TP orders are NOT
        # resting in the book — they trigger as market orders when the mark
        # price crosses — and signal-driven exits are market by construction.
        # (Until 2026-08-12 stop/TP exits were classified LIMIT against a
        # negative maker rate, so every stop-out CREDITED the account ~1bp.)
        # Legacy fee_mode='fixed' preserves the prior single-rate behavior.
        fee_rate = self._effective_fee_rate("MARKET")
        commission_cost = self.current_position.position_size * exit_price * fee_rate
        profit_loss -= commission_cost

        # Update capital
        self.capital += profit_loss

        # Calculate profit/loss percentage
        profit_loss_pct = (
            profit_loss
            / (self.current_position.entry_price * self.current_position.position_size)
        ) * 100

        # Create trade record
        trade = Trade(
            entry_time=self.current_position.entry_time,
            exit_time=time,
            entry_price=self.current_position.entry_price,
            exit_price=exit_price,
            order_type=self.current_position.order_type,
            position_size=self.current_position.position_size,
            profit_loss=profit_loss,
            profit_loss_pct=profit_loss_pct,
            stop_loss=self.current_position.stop_loss,
            take_profit=self.current_position.take_profit,
            exit_reason=reason,
            metadata=self.current_position.metadata,
        )

        self.trades.append(trade)
        self.current_position = None

        logger.debug(
            f"Closed position: P&L ${profit_loss:.2f} ({profit_loss_pct:.2f}%), reason: {reason}"
        )

    def _calculate_equity(self, current_price: float) -> float:
        """Calculate current equity including open position"""
        equity = self.capital

        if self.current_position:
            # Add unrealized P&L
            if self.current_position.order_type == OrderType.BUY:
                unrealized_pl = (
                    current_price - self.current_position.entry_price
                ) * self.current_position.position_size
            else:
                unrealized_pl = (
                    self.current_position.entry_price - current_price
                ) * self.current_position.position_size

            equity += unrealized_pl

        return equity

    def _calculate_results(
        self, strategy_name: str, data: pd.DataFrame
    ) -> BacktestResult:
        """Calculate backtest performance metrics"""
        if not self.trades:
            logger.warning("No trades executed during backtest")
            return BacktestResult(
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                total_profit_loss=0.0,
                total_profit_loss_pct=0.0,
                avg_profit_per_trade=0.0,
                avg_win=0.0,
                avg_loss=0.0,
                max_drawdown=0.0,
                max_drawdown_pct=0.0,
                sharpe_ratio=0.0,
                profit_factor=0.0,
                avg_trade_duration_hours=0.0,
                best_trade=0.0,
                worst_trade=0.0,
                trades=[],
                equity_curve=self.equity_curve,
                strategy_name=strategy_name,
                start_date=data.index[0]
                if isinstance(data.index[0], (pd.Timestamp, datetime))
                else pd.to_datetime(data.iloc[0]["timestamp"]),
                end_date=data.index[-1]
                if isinstance(data.index[-1], (pd.Timestamp, datetime))
                else pd.to_datetime(data.iloc[-1]["timestamp"]),
                initial_capital=self.initial_capital,
                final_capital=self.capital,
            )

        # Basic metrics
        winning_trades = [t for t in self.trades if t.profit_loss > 0]
        losing_trades = [t for t in self.trades if t.profit_loss <= 0]

        total_trades = len(self.trades)
        num_winning = len(winning_trades)
        num_losing = len(losing_trades)
        win_rate = (num_winning / total_trades) * 100 if total_trades > 0 else 0

        # P&L metrics
        total_pl = sum(t.profit_loss for t in self.trades)
        total_pl_pct = (
            (self.capital - self.initial_capital) / self.initial_capital
        ) * 100
        avg_profit = total_pl / total_trades if total_trades > 0 else 0

        avg_win = (
            sum(t.profit_loss for t in winning_trades) / num_winning
            if num_winning > 0
            else 0
        )
        avg_loss = (
            sum(t.profit_loss for t in losing_trades) / num_losing
            if num_losing > 0
            else 0
        )

        best_trade = max(t.profit_loss for t in self.trades) if self.trades else 0
        worst_trade = min(t.profit_loss for t in self.trades) if self.trades else 0

        # Risk metrics
        max_drawdown, max_drawdown_pct = self._calculate_max_drawdown()
        sharpe_ratio = self._calculate_sharpe_ratio()

        # Profit factor
        gross_profit = sum(t.profit_loss for t in winning_trades)
        gross_loss = abs(sum(t.profit_loss for t in losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        # Trade duration
        durations = [
            (t.exit_time - t.entry_time).total_seconds() / 3600 for t in self.trades
        ]
        avg_duration = sum(durations) / len(durations) if durations else 0

        return BacktestResult(
            total_trades=total_trades,
            winning_trades=num_winning,
            losing_trades=num_losing,
            win_rate=win_rate,
            total_profit_loss=total_pl,
            total_profit_loss_pct=total_pl_pct,
            avg_profit_per_trade=avg_profit,
            avg_win=avg_win,
            avg_loss=avg_loss,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=sharpe_ratio,
            profit_factor=profit_factor,
            avg_trade_duration_hours=avg_duration,
            best_trade=best_trade,
            worst_trade=worst_trade,
            trades=self.trades,
            equity_curve=self.equity_curve,
            strategy_name=strategy_name,
            start_date=data.index[0]
            if isinstance(data.index[0], (pd.Timestamp, datetime))
            else pd.to_datetime(data.iloc[0]["timestamp"]),
            end_date=data.index[-1]
            if isinstance(data.index[-1], (pd.Timestamp, datetime))
            else pd.to_datetime(data.iloc[-1]["timestamp"]),
            initial_capital=self.initial_capital,
            final_capital=self.capital,
        )

    def _calculate_max_drawdown(self) -> Tuple[float, float]:
        """Calculate maximum drawdown"""
        if not self.equity_curve:
            return 0.0, 0.0

        peak = self.equity_curve[0]
        max_dd = 0.0
        max_dd_pct = 0.0

        for equity in self.equity_curve:
            if equity > peak:
                peak = equity

            drawdown = peak - equity
            drawdown_pct = (drawdown / peak) * 100 if peak > 0 else 0

            if drawdown > max_dd:
                max_dd = drawdown
                max_dd_pct = drawdown_pct

        return max_dd, max_dd_pct

    def _calculate_sharpe_ratio(self, risk_free_rate: float = 0.02) -> float:
        """Calculate Sharpe ratio"""
        if len(self.equity_curve) < 2:
            return 0.0

        # Calculate returns
        returns = pd.Series(self.equity_curve).pct_change().dropna()

        if len(returns) == 0 or returns.std() == 0:
            return 0.0

        # Annualized Sharpe ratio (assuming daily returns)
        excess_returns = returns.mean() - (risk_free_rate / 365)
        sharpe = (excess_returns / returns.std()) * np.sqrt(365)

        return sharpe
