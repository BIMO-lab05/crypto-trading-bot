#!/usr/bin/env python3
"""
Backtesting Engine for Crypto Trading Bot
Tests trading strategies on historical data to validate effectiveness
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging

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
    exit_time: datetime   # When the trade was closed
    entry_price: float    # Entry price
    exit_price: float     # Exit price
    order_type: OrderType # BUY or SELL
    position_size: float  # Position size (in base currency)
    profit_loss: float    # Profit/Loss in USD
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
        initial_capital: float = 10000.0,
        position_size_pct: float = 0.02,  # 2% per trade
        commission: float = 0.001,  # 0.1% commission
        slippage: float = 0.0005,  # 0.05% slippage
    ):
        """
        Initialize backtesting engine

        Args:
            initial_capital: Starting capital in USD
            position_size_pct: Percentage of capital to risk per trade
            commission: Trading commission percentage
            slippage: Slippage percentage
        """
        self.initial_capital = initial_capital
        self.position_size_pct = position_size_pct
        self.commission = commission
        self.slippage = slippage

        # State variables
        self.capital = initial_capital
        self.equity_curve = [initial_capital]
        self.trades: List[Trade] = []
        self.current_position: Optional[Position] = None

        logger.info(f"BacktestEngine initialized with ${initial_capital:,.2f}")

    def reset(self):
        """Reset backtest state"""
        self.capital = self.initial_capital
        self.equity_curve = [self.initial_capital]
        self.trades = []
        self.current_position = None

    def run_backtest(
        self,
        data: pd.DataFrame,
        strategy_func,
        strategy_name: str = "Unknown Strategy"
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
        elif 'timestamp' in data.columns:
            logger.info(f"Data range: {data.iloc[0]['timestamp']} to {data.iloc[-1]['timestamp']}")
        logger.info(f"Total candles: {len(data)}")

        self.reset()

        # Iterate through historical data
        row_position = 0  # Integer position counter for strategy function
        for idx, row in data.iterrows():
            current_price = row['close']
            # Handle both datetime index and timestamp column
            if isinstance(idx, (pd.Timestamp, datetime)):
                current_time = idx
            elif 'timestamp' in row:
                current_time = pd.to_datetime(row['timestamp'])
            else:
                current_time = datetime.now()  # Fallback

            # Check stop loss and take profit for open position
            if self.current_position:
                exit_reason = self._check_exit_conditions(row, current_time)
                if exit_reason:
                    self._close_position(current_price, current_time, exit_reason)

            # Get strategy signal - pass row_position (int) instead of idx (which may be Timestamp)
            signal = strategy_func(row, self.current_position, row_position, data)
            row_position += 1  # Increment position counter

            # Execute signal
            if signal:
                self._execute_signal(signal, current_price, current_time, row)

            # Update equity curve
            current_equity = self._calculate_equity(current_price)
            self.equity_curve.append(current_equity)

        # Close any open position at the end
        if self.current_position:
            final_price = data.iloc[-1]['close']
            # Handle both datetime index and timestamp column
            if isinstance(data.index[-1], (pd.Timestamp, datetime)):
                final_time = data.index[-1]
            elif 'timestamp' in data.columns:
                final_time = pd.to_datetime(data.iloc[-1]['timestamp'])
            else:
                final_time = datetime.now()
            self._close_position(final_price, final_time, "end_of_data")

        # Calculate results
        result = self._calculate_results(strategy_name, data)

        logger.info(f"Backtest complete: {len(self.trades)} trades")
        logger.info(f"Win rate: {result.win_rate:.2f}%")
        logger.info(f"Total P&L: ${result.total_profit_loss:,.2f} ({result.total_profit_loss_pct:.2f}%)")

        return result

    def _check_exit_conditions(self, row: pd.Series, current_time: datetime) -> Optional[str]:
        """Check if stop loss or take profit is hit"""
        if not self.current_position:
            return None

        high = row['high']
        low = row['low']

        if self.current_position.order_type == OrderType.BUY:
            # Check stop loss (below entry)
            if self.current_position.stop_loss and low <= self.current_position.stop_loss:
                return "stop_loss"

            # Check take profit (above entry)
            if self.current_position.take_profit and high >= self.current_position.take_profit:
                return "take_profit"

        elif self.current_position.order_type == OrderType.SELL:
            # Check stop loss (above entry)
            if self.current_position.stop_loss and high >= self.current_position.stop_loss:
                return "stop_loss"

            # Check take profit (below entry)
            if self.current_position.take_profit and low <= self.current_position.take_profit:
                return "take_profit"

        return None

    def _execute_signal(self, signal: Dict, price: float, time: datetime, row: pd.Series):
        """Execute a trading signal"""
        action = signal.get('action')

        if action == 'BUY' and not self.current_position:
            self._open_position(OrderType.BUY, price, time, signal)

        elif action == 'SELL' and not self.current_position:
            self._open_position(OrderType.SELL, price, time, signal)

        elif action == 'HOLD' and self.current_position:
            # Close position on HOLD signal
            self._close_position(price, time, "signal")

    def _open_position(self, order_type: OrderType, price: float, time: datetime, signal: Dict):
        """Open a new position"""
        # Calculate position size
        risk_amount = self.capital * self.position_size_pct
        position_size = risk_amount / price

        # Apply slippage
        if order_type == OrderType.BUY:
            entry_price = price * (1 + self.slippage)
        else:
            entry_price = price * (1 - self.slippage)

        # Deduct commission
        commission_cost = position_size * entry_price * self.commission
        self.capital -= commission_cost

        # Get stop loss and take profit from signal
        stop_loss = signal.get('stop_loss')
        take_profit = signal.get('take_profit')

        self.current_position = Position(
            entry_time=time,
            entry_price=entry_price,
            order_type=order_type,
            position_size=position_size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            metadata=signal.get('metadata', {})
        )

        logger.debug(f"Opened {order_type.value} position at ${entry_price:.2f}, size: {position_size:.4f}")

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
            # Apply slippage
            if self.current_position.order_type == OrderType.BUY:
                exit_price = price * (1 - self.slippage)
            else:
                exit_price = price * (1 + self.slippage)

        # Calculate P&L
        if self.current_position.order_type == OrderType.BUY:
            profit_loss = (exit_price - self.current_position.entry_price) * self.current_position.position_size
        else:  # SELL
            profit_loss = (self.current_position.entry_price - exit_price) * self.current_position.position_size

        # Deduct commission
        commission_cost = self.current_position.position_size * exit_price * self.commission
        profit_loss -= commission_cost

        # Update capital
        self.capital += profit_loss

        # Calculate profit/loss percentage
        profit_loss_pct = (profit_loss / (self.current_position.entry_price * self.current_position.position_size)) * 100

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
            metadata=self.current_position.metadata
        )

        self.trades.append(trade)
        self.current_position = None

        logger.debug(f"Closed position: P&L ${profit_loss:.2f} ({profit_loss_pct:.2f}%), reason: {reason}")

    def _calculate_equity(self, current_price: float) -> float:
        """Calculate current equity including open position"""
        equity = self.capital

        if self.current_position:
            # Add unrealized P&L
            if self.current_position.order_type == OrderType.BUY:
                unrealized_pl = (current_price - self.current_position.entry_price) * self.current_position.position_size
            else:
                unrealized_pl = (self.current_position.entry_price - current_price) * self.current_position.position_size

            equity += unrealized_pl

        return equity

    def _calculate_results(self, strategy_name: str, data: pd.DataFrame) -> BacktestResult:
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
                start_date=data.index[0] if isinstance(data.index[0], (pd.Timestamp, datetime)) else pd.to_datetime(data.iloc[0]['timestamp']),
                end_date=data.index[-1] if isinstance(data.index[-1], (pd.Timestamp, datetime)) else pd.to_datetime(data.iloc[-1]['timestamp']),
                initial_capital=self.initial_capital,
                final_capital=self.capital
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
        total_pl_pct = ((self.capital - self.initial_capital) / self.initial_capital) * 100
        avg_profit = total_pl / total_trades if total_trades > 0 else 0

        avg_win = sum(t.profit_loss for t in winning_trades) / num_winning if num_winning > 0 else 0
        avg_loss = sum(t.profit_loss for t in losing_trades) / num_losing if num_losing > 0 else 0

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
        durations = [(t.exit_time - t.entry_time).total_seconds() / 3600 for t in self.trades]
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
            start_date=data.index[0] if isinstance(data.index[0], (pd.Timestamp, datetime)) else pd.to_datetime(data.iloc[0]['timestamp']),
            end_date=data.index[-1] if isinstance(data.index[-1], (pd.Timestamp, datetime)) else pd.to_datetime(data.iloc[-1]['timestamp']),
            initial_capital=self.initial_capital,
            final_capital=self.capital
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
