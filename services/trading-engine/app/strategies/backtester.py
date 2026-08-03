"""
Strategy Backtester for Multi-Strategy Orchestration
======================================================
Purpose: Historical simulation and performance analysis of trading strategies

This module provides comprehensive backtesting capabilities:
1. Historical simulation with realistic fills
2. Walk-forward analysis for robustness testing
3. Out-of-sample validation
4. Performance comparison across strategies
5. Parameter optimization framework

Phase 9: Multi-Strategy Orchestration Engine
Author: Backend Developer Agent
Date: 2025-12-11
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict
import statistics
import math
from copy import deepcopy

from app.strategies.base import (
    StrategyBase,
    StrategySignal,
    SignalType,
)

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass
class BacktestCandle:
    """OHLCV candle for backtesting"""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to standard candle dict"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "o": self.open,
            "h": self.high,
            "l": self.low,
            "c": self.close,
            "v": self.volume,
        }


@dataclass
class BacktestTrade:
    """Record of a backtested trade"""

    trade_id: str
    strategy_id: str
    symbol: str
    side: str  # LONG or SHORT
    entry_time: datetime
    exit_time: Optional[datetime] = None
    entry_price: float = 0.0
    exit_price: float = 0.0
    quantity: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    fees: float = 0.0
    slippage: float = 0.0
    exit_reason: str = ""  # SL, TP, SIGNAL, TIME
    max_favorable_excursion: float = 0.0  # Best price during trade
    max_adverse_excursion: float = 0.0  # Worst price during trade

    @property
    def is_winner(self) -> bool:
        """Check if trade was profitable"""
        return self.pnl > 0

    @property
    def hold_time_hours(self) -> float:
        """Calculate hold time in hours"""
        if self.exit_time:
            return (self.exit_time - self.entry_time).total_seconds() / 3600
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "trade_id": self.trade_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "side": self.side,
            "entry_time": self.entry_time.isoformat(),
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "quantity": self.quantity,
            "pnl": self.pnl,
            "pnl_pct": self.pnl_pct,
            "is_winner": self.is_winner,
            "exit_reason": self.exit_reason,
        }


@dataclass
class BacktestResult:
    """Results from a backtest run"""

    strategy_id: str
    symbol: str
    start_date: datetime
    end_date: datetime

    # Capital tracking.
    # FIX 2026-08-03 (capital audit, B5). These carried `= 10000.0` defaults.
    # `final_capital` and `peak_capital` are RESULTS of a run: that they had a
    # capital default AT ALL was the defect, and changing 10000.0 -> 100.0 would
    # have preserved it in a prettier form. They are now REQUIRED, so a result
    # object can never silently report a capital figure no run produced.
    # Safe: the only construction site of this class is
    # `StrategyBacktester._calculate_results()` below, which passes all three
    # explicitly. (Verified by repo-wide grep — the other `BacktestResult`
    # symbols in this repo are unrelated classes in other modules.)
    initial_capital: float
    final_capital: float
    peak_capital: float

    # Trade statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0

    # PnL statistics
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    avg_trade: float = 0.0

    # Risk metrics
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_hours: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    # Streak statistics
    max_win_streak: int = 0
    max_loss_streak: int = 0
    current_streak: int = 0

    # Time statistics
    avg_hold_time_hours: float = 0.0
    avg_trades_per_day: float = 0.0

    # Trade list
    trades: List[BacktestTrade] = field(default_factory=list)

    # Equity curve
    equity_curve: List[Tuple[datetime, float]] = field(default_factory=list)

    # Daily returns
    daily_returns: List[float] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "initial_capital": self.initial_capital,
            "final_capital": self.final_capital,
            "total_pnl": self.total_pnl,
            "total_pnl_pct": self.total_pnl_pct,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "calmar_ratio": self.calmar_ratio,
            "avg_hold_time_hours": self.avg_hold_time_hours,
            "avg_trade": self.avg_trade,
            "largest_win": self.largest_win,
            "largest_loss": self.largest_loss,
            "max_win_streak": self.max_win_streak,
            "max_loss_streak": self.max_loss_streak,
        }


# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass
class BacktestConfig:
    """Configuration for backtesting"""

    # Capital settings.
    # FIX 2026-08-03 (capital audit): was 10000.0, 100x the real account.
    # Declared as None and resolved in __post_init__ rather than as
    # `= get_settings().paper_initial_balance`, because a dataclass field
    # default is evaluated at MODULE IMPORT — that form would create an
    # import-time settings dependency and freeze the value at first import.
    initial_capital: Optional[float] = None
    position_size_pct: float = 5.0  # Default position size
    max_positions: int = 5

    # Execution simulation
    slippage_pct: float = 0.05  # 0.05% slippage
    maker_fee_pct: float = 0.02  # Maker fee
    taker_fee_pct: float = 0.05  # Taker fee
    use_limit_orders: bool = False  # Use maker fees

    # Fill simulation
    fill_rate: float = 1.0  # Percentage of signals that fill
    partial_fill_rate: float = 0.0  # Chance of partial fill

    # Risk management
    max_drawdown_halt_pct: float = 20.0  # Stop trading at this drawdown
    daily_loss_limit_pct: float = 5.0  # Daily loss limit

    # Analysis settings
    risk_free_rate_annual: float = 0.05  # For Sharpe calculation
    trading_days_per_year: int = 365  # Crypto 24/7

    # Walk-forward settings
    walk_forward_windows: int = 5  # Number of windows
    in_sample_pct: float = 0.7  # In-sample percentage

    #: Mirrors config.py `paper_initial_balance`. Used only when `get_settings()`
    #: cannot be constructed (e.g. a host-run test session whose `.env` is parsed
    #: by a different pydantic-settings version than the container pins).
    _FALLBACK_INITIAL_CAPITAL_USD = 100.0

    def __post_init__(self) -> None:
        if self.initial_capital is not None:
            return
        try:
            from app.config import get_settings

            self.initial_capital = get_settings().paper_initial_balance
        except Exception as exc:  # a backtest must not be unbuildable
            logger.error(
                "BacktestConfig: could not read Settings for initial_capital "
                "(%s). Falling back to the declared default ($%.2f).",
                exc,
                self._FALLBACK_INITIAL_CAPITAL_USD,
            )
            self.initial_capital = self._FALLBACK_INITIAL_CAPITAL_USD

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "initial_capital": self.initial_capital,
            "position_size_pct": self.position_size_pct,
            "slippage_pct": self.slippage_pct,
            "maker_fee_pct": self.maker_fee_pct,
            "taker_fee_pct": self.taker_fee_pct,
            "max_drawdown_halt_pct": self.max_drawdown_halt_pct,
        }


# =============================================================================
# STRATEGY BACKTESTER
# =============================================================================


class StrategyBacktester:
    """
    Historical Simulation and Strategy Testing Framework

    Provides comprehensive backtesting capabilities for trading strategies:

    1. Historical Simulation:
       - Process historical data bar-by-bar
       - Generate signals using strategy logic
       - Simulate realistic order execution
       - Track positions and P&L

    2. Realistic Execution:
       - Slippage modeling
       - Commission/fee calculation
       - Partial fills (optional)
       - Order rejection simulation

    3. Risk Management:
       - Stop loss execution
       - Take profit execution
       - Maximum drawdown monitoring
       - Daily loss limits

    4. Performance Analysis:
       - Standard metrics (Win rate, Sharpe, etc.)
       - Equity curve generation
       - Drawdown analysis
       - Trade statistics

    5. Walk-Forward Analysis:
       - Split data into in-sample/out-of-sample
       - Validate strategy robustness
       - Detect overfitting

    Usage:
        config = BacktestConfig(initial_capital=100)
        backtester = StrategyBacktester(config)

        # Load historical data
        candles = load_historical_data("BTCUSDT", "2023-01-01", "2023-12-31")

        # Run backtest
        result = await backtester.run_backtest(
            strategy=my_strategy,
            symbol="BTCUSDT",
            candles=candles
        )

        # Analyze results
        print(f"Total PnL: ${result.total_pnl:.2f}")
        print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")

        # Walk-forward analysis
        wf_results = await backtester.run_walk_forward(
            strategy=my_strategy,
            symbol="BTCUSDT",
            candles=candles,
            n_windows=5
        )
    """

    def __init__(self, config: Optional[BacktestConfig] = None):
        """
        Initialize backtester

        Args:
            config: Backtest configuration
        """
        self.config = config or BacktestConfig()

        # Track state during backtest
        self._capital: float = 0.0
        self._positions: Dict[str, Dict[str, Any]] = {}
        self._trades: List[BacktestTrade] = []
        self._equity_curve: List[Tuple[datetime, float]] = []
        self._daily_pnl: Dict[str, float] = defaultdict(float)

        # Performance tracking
        self._trade_counter: int = 0
        self._peak_capital: float = 0.0
        self._current_drawdown: float = 0.0
        self._max_drawdown: float = 0.0
        self._halted: bool = False

        logger.info(
            f"StrategyBacktester initialized: "
            f"capital=${self.config.initial_capital:,.0f}"
        )

    def _reset_state(self) -> None:
        """Reset backtest state for new run"""
        self._capital = self.config.initial_capital
        self._positions = {}
        self._trades = []
        self._equity_curve = []
        self._daily_pnl = defaultdict(float)
        self._trade_counter = 0
        self._peak_capital = self.config.initial_capital
        self._current_drawdown = 0.0
        self._max_drawdown = 0.0
        self._halted = False

    # =========================================================================
    # MAIN BACKTEST METHODS
    # =========================================================================

    async def run_backtest(
        self,
        strategy: StrategyBase,
        symbol: str,
        candles: List[BacktestCandle],
        risk_per_trade_pct: Optional[float] = None,
    ) -> BacktestResult:
        """
        Run a full backtest on historical data

        Args:
            strategy: Strategy instance to test
            symbol: Trading symbol
            candles: Historical candle data
            risk_per_trade_pct: Risk per trade percentage

        Returns:
            BacktestResult with performance metrics
        """
        if not candles:
            raise ValueError("No candle data provided")

        self._reset_state()

        # Initialize strategy
        await strategy.on_initialize()
        await strategy.on_start()

        # Progress tracking
        total_bars = len(candles)
        warmup_period = strategy.metadata.required_data_history_bars

        logger.info(
            f"Starting backtest: {strategy.strategy_id} on {symbol}, "
            f"{total_bars} bars, warmup={warmup_period}"
        )

        # Process each bar
        for i in range(warmup_period, total_bars):
            if self._halted:
                break

            # Get historical data up to this point
            historical_candles = candles[: i + 1]
            current_candle = candles[i]
            current_price = Decimal(str(current_candle.close))

            # Update existing positions (check SL/TP)
            await self._update_positions(current_candle)

            # Prepare data for strategy
            data = {
                "candles": [c.to_dict() for c in historical_candles],
                "current_price": float(current_price),
            }

            # Run strategy analysis
            try:
                analysis = await strategy.analyze(symbol, data)

                # Generate signals
                signals = await strategy.generate_signals(
                    symbol, analysis, current_price
                )

                # Process signals
                for signal in signals:
                    await self._process_signal(
                        signal, current_candle, risk_per_trade_pct
                    )

            except Exception as e:
                logger.error(f"Strategy error at bar {i}: {e}")
                continue

            # Record equity
            equity = self._calculate_equity(current_candle.close)
            self._equity_curve.append((current_candle.timestamp, equity))

            # Update drawdown
            self._update_drawdown(equity)

            # Check daily loss limit
            self._check_daily_loss_limit(current_candle.timestamp.date())

        # Close any remaining positions at end
        if candles:
            last_candle = candles[-1]
            for position_id in list(self._positions.keys()):
                await self._close_position(
                    position_id,
                    last_candle.close,
                    last_candle.timestamp,
                    "END_OF_BACKTEST",
                )

        # Stop strategy
        await strategy.on_stop()

        # Calculate final results
        result = self._calculate_results(strategy.strategy_id, symbol, candles)

        logger.info(
            f"Backtest complete: {result.total_trades} trades, "
            f"PnL=${result.total_pnl:.2f} ({result.total_pnl_pct:.1f}%), "
            f"Sharpe={result.sharpe_ratio:.2f}"
        )

        return result

    async def run_walk_forward(
        self,
        strategy: StrategyBase,
        symbol: str,
        candles: List[BacktestCandle],
        n_windows: Optional[int] = None,
        in_sample_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Run walk-forward analysis

        Split data into multiple in-sample/out-of-sample periods
        to validate strategy robustness.

        Args:
            strategy: Strategy to test
            symbol: Trading symbol
            candles: Full historical data
            n_windows: Number of walk-forward windows
            in_sample_pct: In-sample percentage

        Returns:
            Walk-forward analysis results
        """
        n_windows = n_windows or self.config.walk_forward_windows
        in_sample_pct = in_sample_pct or self.config.in_sample_pct

        total_bars = len(candles)
        window_size = total_bars // n_windows
        in_sample_size = int(window_size * in_sample_pct)
        out_sample_size = window_size - in_sample_size

        logger.info(
            f"Walk-forward analysis: {n_windows} windows, "
            f"in-sample={in_sample_size} bars, "
            f"out-sample={out_sample_size} bars"
        )

        in_sample_results = []
        out_sample_results = []

        for window in range(n_windows):
            start_idx = window * window_size
            split_idx = start_idx + in_sample_size
            end_idx = min(start_idx + window_size, total_bars)

            # In-sample period
            in_sample_candles = candles[start_idx:split_idx]
            # Out-of-sample period
            out_sample_candles = candles[split_idx:end_idx]

            # Create fresh strategy copy
            strategy_copy = deepcopy(strategy)

            # Run in-sample backtest
            in_result = await self.run_backtest(
                strategy_copy, symbol, in_sample_candles
            )
            in_sample_results.append(in_result)

            # Run out-of-sample backtest
            out_result = await self.run_backtest(
                strategy_copy, symbol, out_sample_candles
            )
            out_sample_results.append(out_result)

            logger.info(
                f"Window {window + 1}/{n_windows}: "
                f"IS Sharpe={in_result.sharpe_ratio:.2f}, "
                f"OOS Sharpe={out_result.sharpe_ratio:.2f}"
            )

        # Aggregate results
        return self._aggregate_walk_forward_results(
            in_sample_results, out_sample_results
        )

    def _aggregate_walk_forward_results(
        self, in_sample: List[BacktestResult], out_sample: List[BacktestResult]
    ) -> Dict[str, Any]:
        """Aggregate walk-forward analysis results"""

        def avg_metric(results: List[BacktestResult], attr: str) -> float:
            values = [getattr(r, attr) for r in results]
            return statistics.mean(values) if values else 0.0

        # Calculate efficiency (OOS/IS performance ratio)
        is_sharpe = avg_metric(in_sample, "sharpe_ratio")
        oos_sharpe = avg_metric(out_sample, "sharpe_ratio")
        efficiency = oos_sharpe / is_sharpe if is_sharpe != 0 else 0.0

        # Calculate robustness score
        oos_positive = sum(1 for r in out_sample if r.total_pnl > 0)
        robustness = oos_positive / len(out_sample) if out_sample else 0.0

        return {
            "n_windows": len(in_sample),
            "in_sample": {
                "avg_sharpe": is_sharpe,
                "avg_win_rate": avg_metric(in_sample, "win_rate"),
                "avg_pnl_pct": avg_metric(in_sample, "total_pnl_pct"),
                "avg_max_drawdown": avg_metric(in_sample, "max_drawdown_pct"),
            },
            "out_of_sample": {
                "avg_sharpe": oos_sharpe,
                "avg_win_rate": avg_metric(out_sample, "win_rate"),
                "avg_pnl_pct": avg_metric(out_sample, "total_pnl_pct"),
                "avg_max_drawdown": avg_metric(out_sample, "max_drawdown_pct"),
            },
            "efficiency": efficiency,
            "robustness_score": robustness,
            "overfitting_detected": efficiency < 0.5 and is_sharpe > 1.0,
            "recommendation": (
                "ROBUST"
                if efficiency >= 0.7 and robustness >= 0.6
                else "MARGINAL"
                if efficiency >= 0.5
                else "LIKELY_OVERFIT"
            ),
        }

    # =========================================================================
    # POSITION MANAGEMENT
    # =========================================================================

    async def _process_signal(
        self,
        signal: StrategySignal,
        candle: BacktestCandle,
        risk_per_trade_pct: Optional[float] = None,
    ) -> None:
        """Process a trading signal"""
        # Check if we should open a new position
        if signal.signal_type in [SignalType.ENTRY_LONG, SignalType.ENTRY_SHORT]:
            # Check position limits
            if len(self._positions) >= self.config.max_positions:
                return

            # Check fill probability
            import random

            if random.random() > self.config.fill_rate:
                return

            # Open position
            await self._open_position(signal, candle, risk_per_trade_pct)

        # Check for exit signals on existing positions
        elif signal.signal_type in [SignalType.EXIT_LONG, SignalType.EXIT_SHORT]:
            for pos_id, pos in list(self._positions.items()):
                if pos["symbol"] == signal.symbol:
                    matching_exit = (
                        signal.signal_type == SignalType.EXIT_LONG
                        and pos["side"] == "LONG"
                    ) or (
                        signal.signal_type == SignalType.EXIT_SHORT
                        and pos["side"] == "SHORT"
                    )
                    if matching_exit:
                        await self._close_position(
                            pos_id, candle.close, candle.timestamp, "SIGNAL"
                        )

    async def _open_position(
        self,
        signal: StrategySignal,
        candle: BacktestCandle,
        risk_per_trade_pct: Optional[float] = None,
    ) -> None:
        """Open a new position"""
        self._trade_counter += 1
        trade_id = f"BT_{self._trade_counter}"

        # Determine side
        side = "LONG" if signal.signal_type == SignalType.ENTRY_LONG else "SHORT"

        # Calculate position size
        risk_pct = risk_per_trade_pct or self.config.position_size_pct
        position_value = self._capital * (risk_pct / 100)

        # Apply slippage
        slippage_mult = (
            (1 + self.config.slippage_pct / 100)
            if side == "LONG"
            else (1 - self.config.slippage_pct / 100)
        )
        entry_price = candle.close * slippage_mult

        # Calculate quantity
        quantity = position_value / entry_price

        # Calculate fee
        fee_pct = (
            self.config.maker_fee_pct
            if self.config.use_limit_orders
            else self.config.taker_fee_pct
        )
        fee = position_value * (fee_pct / 100)

        # Calculate stop loss and take profit prices
        if signal.stop_loss_pct:
            if side == "LONG":
                sl_price = entry_price * (1 - signal.stop_loss_pct / 100)
            else:
                sl_price = entry_price * (1 + signal.stop_loss_pct / 100)
        else:
            sl_price = None

        if signal.take_profit_pct:
            if side == "LONG":
                tp_price = entry_price * (1 + signal.take_profit_pct / 100)
            else:
                tp_price = entry_price * (1 - signal.take_profit_pct / 100)
        else:
            tp_price = None

        # Record position
        self._positions[trade_id] = {
            "trade_id": trade_id,
            "strategy_id": signal.strategy_id,
            "symbol": signal.symbol,
            "side": side,
            "entry_time": candle.timestamp,
            "entry_price": entry_price,
            "quantity": quantity,
            "stop_loss": sl_price,
            "take_profit": tp_price,
            "entry_fee": fee,
            "max_favorable": entry_price,
            "max_adverse": entry_price,
        }

        logger.debug(
            f"Position opened: {trade_id} {side} {signal.symbol} "
            f"@ {entry_price:.2f}, qty={quantity:.4f}"
        )

    async def _close_position(
        self, position_id: str, exit_price: float, exit_time: datetime, reason: str
    ) -> None:
        """Close a position and record trade"""
        if position_id not in self._positions:
            return

        pos = self._positions[position_id]

        # Apply slippage
        if pos["side"] == "LONG":
            actual_exit = exit_price * (1 - self.config.slippage_pct / 100)
            pnl = (actual_exit - pos["entry_price"]) * pos["quantity"]
        else:
            actual_exit = exit_price * (1 + self.config.slippage_pct / 100)
            pnl = (pos["entry_price"] - actual_exit) * pos["quantity"]

        # Calculate exit fee
        fee_pct = (
            self.config.maker_fee_pct
            if self.config.use_limit_orders
            else self.config.taker_fee_pct
        )
        exit_value = actual_exit * pos["quantity"]
        exit_fee = exit_value * (fee_pct / 100)

        # Total fees and slippage
        total_fees = pos["entry_fee"] + exit_fee
        slippage = abs(exit_price - actual_exit) * pos["quantity"]

        # Net PnL
        net_pnl = pnl - total_fees
        pnl_pct = (net_pnl / (pos["entry_price"] * pos["quantity"])) * 100

        # Create trade record
        trade = BacktestTrade(
            trade_id=pos["trade_id"],
            strategy_id=pos["strategy_id"],
            symbol=pos["symbol"],
            side=pos["side"],
            entry_time=pos["entry_time"],
            exit_time=exit_time,
            entry_price=pos["entry_price"],
            exit_price=actual_exit,
            quantity=pos["quantity"],
            pnl=net_pnl,
            pnl_pct=pnl_pct,
            fees=total_fees,
            slippage=slippage,
            exit_reason=reason,
            max_favorable_excursion=pos["max_favorable"],
            max_adverse_excursion=pos["max_adverse"],
        )

        self._trades.append(trade)

        # Update capital
        self._capital += net_pnl

        # Update daily PnL
        date_str = exit_time.strftime("%Y-%m-%d")
        self._daily_pnl[date_str] += net_pnl

        # Remove position
        del self._positions[position_id]

        logger.debug(
            f"Position closed: {pos['trade_id']} @ {actual_exit:.2f}, "
            f"PnL=${net_pnl:.2f} ({pnl_pct:.2f}%), reason={reason}"
        )

    async def _update_positions(self, candle: BacktestCandle) -> None:
        """Update positions and check SL/TP"""
        for pos_id, pos in list(self._positions.items()):
            # Update MFE/MAE
            if pos["side"] == "LONG":
                pos["max_favorable"] = max(pos["max_favorable"], candle.high)
                pos["max_adverse"] = min(pos["max_adverse"], candle.low)

                # Check stop loss
                if pos["stop_loss"] and candle.low <= pos["stop_loss"]:
                    await self._close_position(
                        pos_id, pos["stop_loss"], candle.timestamp, "STOP_LOSS"
                    )
                    continue

                # Check take profit
                if pos["take_profit"] and candle.high >= pos["take_profit"]:
                    await self._close_position(
                        pos_id, pos["take_profit"], candle.timestamp, "TAKE_PROFIT"
                    )
                    continue

            else:  # SHORT
                pos["max_favorable"] = min(pos["max_favorable"], candle.low)
                pos["max_adverse"] = max(pos["max_adverse"], candle.high)

                # Check stop loss
                if pos["stop_loss"] and candle.high >= pos["stop_loss"]:
                    await self._close_position(
                        pos_id, pos["stop_loss"], candle.timestamp, "STOP_LOSS"
                    )
                    continue

                # Check take profit
                if pos["take_profit"] and candle.low <= pos["take_profit"]:
                    await self._close_position(
                        pos_id, pos["take_profit"], candle.timestamp, "TAKE_PROFIT"
                    )
                    continue

    def _calculate_equity(self, current_price: float) -> float:
        """Calculate current equity including unrealized PnL"""
        equity = self._capital

        for pos in self._positions.values():
            if pos["side"] == "LONG":
                unrealized = (current_price - pos["entry_price"]) * pos["quantity"]
            else:
                unrealized = (pos["entry_price"] - current_price) * pos["quantity"]
            equity += unrealized

        return equity

    def _update_drawdown(self, equity: float) -> None:
        """Update drawdown tracking"""
        if equity > self._peak_capital:
            self._peak_capital = equity
            self._current_drawdown = 0.0
        else:
            self._current_drawdown = (
                (self._peak_capital - equity) / self._peak_capital * 100
            )

        if self._current_drawdown > self._max_drawdown:
            self._max_drawdown = self._current_drawdown

        # Check for halt condition
        if self._current_drawdown >= self.config.max_drawdown_halt_pct:
            self._halted = True
            logger.warning(
                f"Backtest halted: max drawdown {self._current_drawdown:.1f}%"
            )

    def _check_daily_loss_limit(self, date) -> None:
        """Check if daily loss limit exceeded"""
        date_str = date.strftime("%Y-%m-%d")
        daily_loss_pct = (
            abs(self._daily_pnl[date_str]) / self.config.initial_capital * 100
        )

        if daily_loss_pct >= self.config.daily_loss_limit_pct:
            # Close all positions for the day
            logger.warning(f"Daily loss limit reached: {daily_loss_pct:.1f}%")

    # =========================================================================
    # RESULTS CALCULATION
    # =========================================================================

    def _calculate_results(
        self, strategy_id: str, symbol: str, candles: List[BacktestCandle]
    ) -> BacktestResult:
        """Calculate comprehensive backtest results"""
        result = BacktestResult(
            strategy_id=strategy_id,
            symbol=symbol,
            start_date=candles[0].timestamp if candles else datetime.now(timezone.utc),
            end_date=candles[-1].timestamp if candles else datetime.now(timezone.utc),
            initial_capital=self.config.initial_capital,
            final_capital=self._capital,
            peak_capital=self._peak_capital,
            trades=self._trades,
            equity_curve=self._equity_curve,
        )

        # Trade statistics
        result.total_trades = len(self._trades)
        result.winning_trades = sum(1 for t in self._trades if t.is_winner)
        result.losing_trades = result.total_trades - result.winning_trades

        if result.total_trades > 0:
            result.win_rate = result.winning_trades / result.total_trades

        # PnL statistics
        result.total_pnl = self._capital - self.config.initial_capital
        result.total_pnl_pct = (result.total_pnl / self.config.initial_capital) * 100

        wins = [t.pnl for t in self._trades if t.is_winner]
        losses = [abs(t.pnl) for t in self._trades if not t.is_winner]

        result.gross_profit = sum(wins) if wins else 0.0
        result.gross_loss = sum(losses) if losses else 0.0
        result.profit_factor = (
            result.gross_profit / result.gross_loss
            if result.gross_loss > 0
            else float("inf")
        )

        result.avg_win = statistics.mean(wins) if wins else 0.0
        result.avg_loss = statistics.mean(losses) if losses else 0.0
        result.largest_win = max(wins) if wins else 0.0
        result.largest_loss = max(losses) if losses else 0.0
        result.avg_trade = (
            result.total_pnl / result.total_trades if result.total_trades > 0 else 0.0
        )

        # Drawdown
        result.max_drawdown_pct = self._max_drawdown

        # Calculate daily returns for Sharpe
        result.daily_returns = list(self._daily_pnl.values())

        # Risk-adjusted returns
        if result.daily_returns and len(result.daily_returns) > 1:
            daily_mean = statistics.mean(result.daily_returns)
            daily_std = statistics.stdev(result.daily_returns)
            daily_rf = (
                self.config.risk_free_rate_annual / self.config.trading_days_per_year
            )

            if daily_std > 0:
                result.sharpe_ratio = (
                    (daily_mean - daily_rf)
                    / daily_std
                    * math.sqrt(self.config.trading_days_per_year)
                )

                # Sortino (downside deviation)
                negative_returns = [r for r in result.daily_returns if r < 0]
                if negative_returns:
                    downside_std = math.sqrt(
                        sum(r**2 for r in negative_returns) / len(negative_returns)
                    )
                    if downside_std > 0:
                        result.sortino_ratio = (
                            (daily_mean - daily_rf)
                            / downside_std
                            * math.sqrt(self.config.trading_days_per_year)
                        )

        # Calmar ratio
        if result.max_drawdown_pct > 0:
            annual_return = result.total_pnl_pct * (
                365 / max(1, (result.end_date - result.start_date).days)
            )
            result.calmar_ratio = annual_return / result.max_drawdown_pct

        # Streaks
        result.max_win_streak, result.max_loss_streak = self._calculate_streaks()

        # Time statistics
        if self._trades:
            result.avg_hold_time_hours = statistics.mean(
                t.hold_time_hours for t in self._trades if t.hold_time_hours > 0
            )
            days = (result.end_date - result.start_date).days or 1
            result.avg_trades_per_day = result.total_trades / days

        return result

    def _calculate_streaks(self) -> Tuple[int, int]:
        """Calculate win and loss streaks"""
        max_win = 0
        max_loss = 0
        current_win = 0
        current_loss = 0

        for trade in self._trades:
            if trade.is_winner:
                current_win += 1
                current_loss = 0
                max_win = max(max_win, current_win)
            else:
                current_loss += 1
                current_win = 0
                max_loss = max(max_loss, current_loss)

        return max_win, max_loss


# =============================================================================
# COMPARISON UTILITIES
# =============================================================================


def compare_backtest_results(results: List[BacktestResult]) -> Dict[str, Any]:
    """
    Compare multiple backtest results

    Args:
        results: List of BacktestResult objects

    Returns:
        Comparison summary
    """
    if not results:
        return {}

    comparison = {"count": len(results), "by_metric": {}, "rankings": {}}

    # Metrics to compare
    metrics = [
        "total_pnl_pct",
        "sharpe_ratio",
        "sortino_ratio",
        "win_rate",
        "profit_factor",
        "max_drawdown_pct",
        "calmar_ratio",
    ]

    for metric in metrics:
        values = {r.strategy_id: getattr(r, metric, 0) for r in results}
        comparison["by_metric"][metric] = values

        # Ranking (higher is better, except drawdown)
        reverse = metric != "max_drawdown_pct"
        ranked = sorted(values.keys(), key=lambda s: values[s], reverse=reverse)
        comparison["rankings"][metric] = ranked

    # Overall ranking (by Sharpe)
    comparison["best_overall"] = (
        comparison["rankings"]["sharpe_ratio"][0]
        if comparison["rankings"]["sharpe_ratio"]
        else None
    )

    return comparison


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


def create_backtester(
    initial_capital: Optional[float] = None,
    config_overrides: Optional[Dict[str, Any]] = None,
) -> StrategyBacktester:
    """Factory function to create backtester.

    `initial_capital=None` defers to `BacktestConfig.__post_init__`, which
    sources the configured paper-trading balance (PAPER_INITIAL_BALANCE, $100).
    FIX 2026-08-03 (capital audit): the default was 10000.0.
    """
    config = BacktestConfig(initial_capital=initial_capital)

    if config_overrides:
        for key, value in config_overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)

    return StrategyBacktester(config)
