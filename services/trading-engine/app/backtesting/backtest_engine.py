"""
Backtest Engine - Core backtesting simulation engine
Event-driven backtesting with realistic execution modeling.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime, timedelta
from enum import Enum
import numpy as np

# Used inside default_factory lambdas below; the noqa keeps autoflake from
# stripping it (it cannot see lambda-body usage).
from app.config import get_settings  # noqa: F401

from app.backtesting.strategy_base import StrategyBase, Signal, SignalType, OHLCV
from app.backtesting.performance_metrics import (
    PerformanceMetrics,
    calculate_all_metrics,
)

logger = logging.getLogger(__name__)


class OrderType(Enum):
    """Order types"""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderSide(Enum):
    """Order side"""

    BUY = "buy"
    SELL = "sell"


@dataclass
class Position:
    """
    Open position tracking

    Tracks entry, current P&L, and position parameters.
    """

    symbol: str
    side: str  # "long" or "short"
    entry_price: float
    quantity: float
    entry_time: datetime
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    trailing_stop: Optional[float] = None
    trailing_stop_distance: Optional[float] = None

    def unrealized_pnl(self, current_price: float) -> float:
        """Calculate unrealized P&L"""
        if self.side == "long":
            return (current_price - self.entry_price) * self.quantity
        else:
            return (self.entry_price - current_price) * self.quantity

    def unrealized_pnl_pct(self, current_price: float) -> float:
        """Calculate unrealized P&L percentage"""
        if self.side == "long":
            return ((current_price / self.entry_price) - 1) * 100
        else:
            return ((self.entry_price / current_price) - 1) * 100


@dataclass
class Trade:
    """
    Completed trade record

    Stores all trade details for analysis.
    """

    trade_id: str
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    quantity: float
    entry_time: datetime
    exit_time: datetime
    pnl: float
    pnl_pct: float
    commission: float
    slippage: float
    exit_reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_hours(self) -> float:
        return (self.exit_time - self.entry_time).total_seconds() / 3600

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "quantity": self.quantity,
            "entry_time": self.entry_time.isoformat(),
            "exit_time": self.exit_time.isoformat(),
            "pnl": round(self.pnl, 2),
            "pnl_pct": round(self.pnl_pct, 2),
            "commission": round(self.commission, 4),
            "slippage": round(self.slippage, 4),
            "exit_reason": self.exit_reason,
            "duration_hours": round(self.duration_hours, 2),
            "metadata": self.metadata,
        }


@dataclass
class BacktestConfig:
    """
    Backtest configuration

    Attributes:
        initial_equity: Starting capital
        commission_pct: Commission per SIDE (percent, e.g. 0.055 = 0.055%)
        slippage_pct: Slippage per trade (percentage)
        position_size_pct: Default position size as % of equity
        max_positions: Maximum concurrent positions
        use_stop_loss: Enable stop loss execution
        use_take_profit: Enable take profit execution
        risk_per_trade_pct: Max risk per trade as % of equity
    """

    # Resolved from Settings at instantiation — never a hardcoded account size
    # (AUDIT 2.5; the account is $100, shared/account.py). default_factory, not
    # a plain default, so the value is read at construction time.
    initial_equity: float = field(
        default_factory=lambda: get_settings().paper_initial_balance
    )
    # Same Settings field the paper engine bills against, so screen verdicts and
    # paper P&L reconcile. Both are PERCENT per side (0.055 = Bybit linear-perp
    # taker), so the mapping is identity — do NOT scale by 100. Was a hardcoded
    # 0.1, i.e. 1.8x the venue.
    commission_pct: float = field(
        default_factory=lambda: get_settings().paper_commission_pct
    )
    slippage_pct: float = 0.05  # 0.05% slippage
    position_size_pct: float = 10.0  # 10% of equity per trade
    max_positions: int = 1
    use_stop_loss: bool = True
    use_take_profit: bool = True
    risk_per_trade_pct: float = 2.0  # 2% risk per trade


@dataclass
class BacktestResult:
    """
    Complete backtest result

    Contains all data from a backtest run.
    """

    strategy_name: str
    symbol: str
    config: BacktestConfig
    metrics: PerformanceMetrics
    trades: List[Trade]
    equity_curve: List[float]
    equity_timestamps: List[datetime]
    signals_generated: int
    signals_executed: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "config": {
                "initial_equity": self.config.initial_equity,
                "commission_pct": self.config.commission_pct,
                "slippage_pct": self.config.slippage_pct,
                "position_size_pct": self.config.position_size_pct,
            },
            "metrics": self.metrics.to_dict(),
            "trades_count": len(self.trades),
            "signals_generated": self.signals_generated,
            "signals_executed": self.signals_executed,
            "equity_curve_length": len(self.equity_curve),
        }


class BacktestEngine:
    """
    Event-Driven Backtesting Engine

    Simulates trading strategy execution on historical data with
    realistic order execution, slippage, and commission modeling.

    Features:
    - Event-driven bar-by-bar simulation
    - Realistic slippage and commission
    - Stop loss and take profit execution
    - Position sizing
    - Comprehensive performance metrics

    Usage:
        engine = BacktestEngine(config)
        result = engine.run(strategy, historical_data)
        print(result.metrics.summary())
    """

    def __init__(self, config: Optional[BacktestConfig] = None):
        """Initialize backtest engine"""
        self.config = config or BacktestConfig()

        # State tracking
        self._equity = self.config.initial_equity
        self._cash = self.config.initial_equity
        self._position: Optional[Position] = None
        self._trades: List[Trade] = []
        self._equity_curve: List[float] = []
        self._equity_timestamps: List[datetime] = []

        # Signal tracking
        self._signals_generated = 0
        self._signals_executed = 0
        self._trade_counter = 0

        # Strategy reference for position sync
        self._strategy: Optional[StrategyBase] = None

        logger.info(
            f"BacktestEngine initialized with equity: ${self.config.initial_equity:,.2f}"
        )

    def reset(self) -> None:
        """Reset engine state for new backtest"""
        self._equity = self.config.initial_equity
        self._cash = self.config.initial_equity
        self._position = None
        self._trades = []
        self._equity_curve = []
        self._equity_timestamps = []
        self._signals_generated = 0
        self._signals_executed = 0
        self._trade_counter = 0
        self._strategy = None

    def run(
        self,
        strategy: StrategyBase,
        data: List[OHLCV],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> BacktestResult:
        """
        Run backtest on historical data

        Args:
            strategy: Trading strategy to test
            data: List of OHLCV bars
            progress_callback: Optional callback(current_bar, total_bars)

        Returns:
            BacktestResult with all metrics and trades
        """
        self.reset()
        self._strategy = strategy  # Store reference for position sync

        if not data:
            raise ValueError("No data provided for backtest")

        logger.info(
            f"Starting backtest: {strategy.get_name()} on {strategy.symbol}, "
            f"{len(data)} bars"
        )

        # Call strategy start
        strategy.on_start(self.config.initial_equity)

        # Iterate through bars
        for i, bar in enumerate(data):
            # Add bar to strategy history
            strategy.add_bar(bar)

            # Check stop loss / take profit on existing position
            if self._position:
                self._check_exit_conditions(bar)

            # If still have position after exit check, update trailing stop
            if self._position and self._position.trailing_stop_distance:
                self._update_trailing_stop(bar)

            # Get signal from strategy
            signal = strategy.on_bar(bar, self._equity)

            if signal:
                self._signals_generated += 1
                self._process_signal(signal, bar, strategy)

            # Record equity
            current_equity = self._calculate_equity(bar.close)
            self._equity_curve.append(current_equity)
            self._equity_timestamps.append(bar.timestamp)

            # Progress callback
            if progress_callback and i % 100 == 0:
                progress_callback(i, len(data))

        # Close any remaining position at last bar price
        if self._position:
            self._close_position(data[-1], "backtest_end")

        # Call strategy end
        strategy.on_end(self._equity)

        # Calculate metrics
        metrics = calculate_all_metrics(
            equity_curve=self._equity_curve,
            trades=[t.to_dict() for t in self._trades],
            initial_equity=self.config.initial_equity,
            start_date=data[0].timestamp,
            end_date=data[-1].timestamp,
        )

        # Build result
        result = BacktestResult(
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

        logger.info(
            f"Backtest complete: {len(self._trades)} trades, "
            f"Return: {metrics.total_return_pct:.2f}%, "
            f"Sharpe: {metrics.sharpe_ratio:.2f}"
        )

        return result

    def _process_signal(
        self, signal: Signal, bar: OHLCV, strategy: StrategyBase
    ) -> None:
        """Process trading signal"""

        if signal.signal_type == SignalType.BUY:
            if not self._position and self._can_open_position():
                self._open_position(signal, bar, "long", strategy)

        elif signal.signal_type == SignalType.SELL:
            if not self._position and self._can_open_position():
                self._open_position(signal, bar, "short", strategy)

        elif signal.signal_type == SignalType.CLOSE_LONG:
            if self._position and self._position.side == "long":
                self._close_position(bar, signal.metadata.get("exit_reason", "signal"))

        elif signal.signal_type == SignalType.CLOSE_SHORT:
            if self._position and self._position.side == "short":
                self._close_position(bar, signal.metadata.get("exit_reason", "signal"))

    def _can_open_position(self) -> bool:
        """Check if we can open a new position"""
        return self._position is None

    def _open_position(
        self, signal: Signal, bar: OHLCV, side: str, strategy: StrategyBase
    ) -> None:
        """Open a new position"""

        # Calculate position size
        position_size_pct = (
            self.config.position_size_pct * signal.position_size_pct / 100
        )
        position_value = self._cash * (position_size_pct / 100)

        # Apply slippage to entry price
        slippage_amount = bar.close * (self.config.slippage_pct / 100)
        if side == "long":
            entry_price = bar.close + slippage_amount
        else:
            entry_price = bar.close - slippage_amount

        # Calculate quantity
        quantity = position_value / entry_price

        # Calculate commission
        commission = position_value * (self.config.commission_pct / 100)

        # Create position
        self._position = Position(
            symbol=signal.symbol,
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            entry_time=bar.timestamp,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
        )

        # Update cash (subtract position value and commission)
        self._cash -= position_value + commission

        # Update strategy position tracking
        strategy.update_position(side, entry_price)

        self._signals_executed += 1

        logger.debug(
            f"Opened {side} position: {quantity:.6f} @ ${entry_price:.2f}, "
            f"SL: {signal.stop_loss}, TP: {signal.take_profit}"
        )

    def _close_position(self, bar: OHLCV, exit_reason: str) -> None:
        """Close existing position"""
        if not self._position:
            return

        # Apply slippage to exit price
        slippage_amount = bar.close * (self.config.slippage_pct / 100)
        if self._position.side == "long":
            exit_price = bar.close - slippage_amount
        else:
            exit_price = bar.close + slippage_amount

        # Calculate P&L
        if self._position.side == "long":
            pnl = (exit_price - self._position.entry_price) * self._position.quantity
        else:
            pnl = (self._position.entry_price - exit_price) * self._position.quantity

        # Calculate commission
        position_value = exit_price * self._position.quantity
        commission = position_value * (self.config.commission_pct / 100)

        # Net P&L
        net_pnl = pnl - commission

        # Calculate P&L percentage
        entry_value = self._position.entry_price * self._position.quantity
        pnl_pct = (pnl / entry_value) * 100 if entry_value > 0 else 0

        # Create trade record
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
            commission=commission * 2,  # Entry + exit commission
            slippage=slippage_amount * 2,
            exit_reason=exit_reason,
        )
        self._trades.append(trade)

        # Return the ENTRY escrow (what _open_position debited) plus net P&L.
        # Crediting the exit notional here double-counted a long's P&L and
        # cancelled a short's; the round-trip delta must be
        # gross P&L - entry commission - exit commission for both sides.
        self._cash += entry_value + net_pnl

        logger.debug(
            f"Closed {self._position.side} position: "
            f"Entry ${self._position.entry_price:.2f} -> Exit ${exit_price:.2f}, "
            f"P&L: ${net_pnl:.2f} ({pnl_pct:.2f}%), Reason: {exit_reason}"
        )

        # Clear position in engine
        self._position = None

        # CRITICAL FIX: Update strategy position tracking to sync state
        # Without this, strategy.has_position() returns True even after close
        if self._strategy:
            self._strategy.update_position(None, None)

    def _check_exit_conditions(self, bar: OHLCV) -> None:
        """Check stop loss and take profit"""
        if not self._position:
            return

        if self._position.side == "long":
            # Check stop loss
            if self.config.use_stop_loss and self._position.stop_loss:
                if bar.low <= self._position.stop_loss:
                    self._close_position(bar, "stop_loss")
                    return

            # Check take profit
            if self.config.use_take_profit and self._position.take_profit:
                if bar.high >= self._position.take_profit:
                    self._close_position(bar, "take_profit")
                    return

        else:  # short position
            # Check stop loss
            if self.config.use_stop_loss and self._position.stop_loss:
                if bar.high >= self._position.stop_loss:
                    self._close_position(bar, "stop_loss")
                    return

            # Check take profit
            if self.config.use_take_profit and self._position.take_profit:
                if bar.low <= self._position.take_profit:
                    self._close_position(bar, "take_profit")
                    return

    def _update_trailing_stop(self, bar: OHLCV) -> None:
        """Update trailing stop if enabled"""
        if not self._position or not self._position.trailing_stop_distance:
            return

        if self._position.side == "long":
            new_stop = bar.high - self._position.trailing_stop_distance
            if (
                self._position.trailing_stop is None
                or new_stop > self._position.trailing_stop
            ):
                self._position.trailing_stop = new_stop
                self._position.stop_loss = new_stop
        else:
            new_stop = bar.low + self._position.trailing_stop_distance
            if (
                self._position.trailing_stop is None
                or new_stop < self._position.trailing_stop
            ):
                self._position.trailing_stop = new_stop
                self._position.stop_loss = new_stop

    def _calculate_equity(self, current_price: float) -> float:
        """Calculate current total equity"""
        equity = self._cash

        if self._position:
            # Entry-notional escrow convention, matching the cash ledger: cash
            # was debited the entry value, so the open leg is marked back at
            # entry value plus side-aware unrealized P&L. Marking it at
            # quantity * current_price inverted the sign for shorts.
            entry_value = self._position.entry_price * self._position.quantity
            equity += entry_value + self._position.unrealized_pnl(current_price)

        return equity


def run_backtest(
    strategy: StrategyBase,
    data: List[OHLCV],
    initial_equity: Optional[float] = None,
    commission_pct: Optional[float] = None,
    slippage_pct: float = 0.05,
) -> BacktestResult:
    """
    Convenience function to run a backtest

    Args:
        strategy: Strategy to test
        data: Historical OHLCV data
        initial_equity: Starting capital. None (default) resolves to
            Settings.paper_initial_balance — never a hardcoded account size
            (AUDIT 2.5).
        commission_pct: Commission percent per side. None (default) resolves to
            Settings.paper_commission_pct, the rate the paper engine bills.
        slippage_pct: Slippage percentage

    Returns:
        BacktestResult
    """
    settings = get_settings()
    if initial_equity is None:
        initial_equity = settings.paper_initial_balance
    if commission_pct is None:
        commission_pct = settings.paper_commission_pct
    config = BacktestConfig(
        initial_equity=initial_equity,
        commission_pct=commission_pct,
        slippage_pct=slippage_pct,
    )

    engine = BacktestEngine(config)
    return engine.run(strategy, data)


def generate_sample_data(
    symbol: str = "BTCUSDT",
    days: int = 365,
    start_price: float = 50000.0,
    volatility: float = 0.02,
) -> List[OHLCV]:
    """
    Generate sample OHLCV data for testing

    Args:
        symbol: Trading pair symbol
        days: Number of days of data
        start_price: Starting price
        volatility: Daily volatility (std dev of returns)

    Returns:
        List of OHLCV bars (hourly)
    """
    np.random.seed(42)

    bars = []
    price = start_price
    current_time = datetime(2024, 1, 1)

    hours = days * 24

    for _ in range(hours):
        # Generate random return with slight positive drift
        daily_return = np.random.normal(0.0001, volatility / np.sqrt(24))
        price = price * (1 + daily_return)

        # Generate OHLC
        open_price = price
        close_price = price * (1 + np.random.normal(0, volatility / 4))
        high_price = max(open_price, close_price) * (
            1 + abs(np.random.normal(0, volatility / 4))
        )
        low_price = min(open_price, close_price) * (
            1 - abs(np.random.normal(0, volatility / 4))
        )

        # Volume
        volume = np.random.uniform(100, 1000) * price / 10000

        bar = OHLCV(
            timestamp=current_time,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
        )
        bars.append(bar)

        price = close_price
        current_time += timedelta(hours=1)

    return bars
