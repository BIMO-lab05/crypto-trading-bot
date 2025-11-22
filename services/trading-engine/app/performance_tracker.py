"""
Performance Tracker Module
Purpose: Track and analyze trading performance metrics
Features:
- Win rate, profit factor, Sharpe ratio
- Per-symbol and per-strategy analysis
- Equity curve generation
- Maximum drawdown calculation
- Trade statistics and distributions
"""

import logging
from typing import List, Dict, Optional, Tuple
from decimal import Decimal
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import numpy as np

from app.models import Position, PositionStatus, PositionSide

logger = logging.getLogger(__name__)


@dataclass
class TradeMetrics:
    """Metrics for a single trade"""
    symbol: str
    strategy: str
    side: PositionSide
    entry_price: Decimal
    exit_price: Optional[Decimal]
    quantity: Decimal
    pnl: Decimal
    pnl_pct: float
    duration_seconds: int
    entry_time: datetime
    exit_time: Optional[datetime]
    is_winner: bool


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics"""
    # Basic stats
    total_trades: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int

    # Win rate
    win_rate: float
    loss_rate: float

    # P&L metrics
    total_pnl: Decimal
    total_pnl_pct: float
    gross_profit: Decimal
    gross_loss: Decimal
    profit_factor: float

    # Average metrics
    avg_win: Decimal
    avg_loss: Decimal
    avg_win_pct: float
    avg_loss_pct: float

    # Risk metrics
    max_consecutive_wins: int
    max_consecutive_losses: int
    max_drawdown: Decimal
    max_drawdown_pct: float

    # Risk-adjusted returns
    sharpe_ratio: float
    sortino_ratio: float

    # Trade duration
    avg_duration_seconds: int
    max_duration_seconds: int
    min_duration_seconds: int

    # Time period
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    days_active: int


@dataclass
class SymbolPerformance:
    """Performance metrics for a specific symbol"""
    symbol: str
    metrics: PerformanceMetrics
    trades: List[TradeMetrics]


@dataclass
class StrategyPerformance:
    """Performance metrics for a specific strategy"""
    strategy: str
    metrics: PerformanceMetrics
    trades: List[TradeMetrics]


@dataclass
class EquityPoint:
    """Point in equity curve"""
    timestamp: datetime
    balance: Decimal
    equity: Decimal  # balance + unrealized P&L
    total_pnl: Decimal
    drawdown: Decimal
    drawdown_pct: float


class PerformanceTracker:
    """
    Tracks and analyzes trading performance

    Features:
    - Real-time metrics calculation
    - Historical performance analysis
    - Per-symbol breakdown
    - Per-strategy breakdown
    - Equity curve generation
    - Sharpe ratio calculation
    """

    def __init__(self, initial_balance: Decimal = Decimal("10000")):
        """
        Initialize performance tracker

        Args:
            initial_balance: Starting capital
        """
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.peak_balance = initial_balance

        # Trade history
        self.trades: List[TradeMetrics] = []
        self.equity_curve: List[EquityPoint] = []

        # Cache for metrics
        self._metrics_cache: Optional[PerformanceMetrics] = None
        self._cache_valid = False

        logger.info(f"PerformanceTracker initialized with ${initial_balance:,.2f}")

    def add_trade(
        self,
        position: Position,
        exit_price: Decimal,
        exit_time: datetime
    ) -> TradeMetrics:
        """
        Add a completed trade to performance tracking

        Args:
            position: Closed position
            exit_price: Exit price
            exit_time: Exit timestamp

        Returns:
            TradeMetrics for the trade
        """
        # Calculate P&L
        if position.side == PositionSide.LONG:
            pnl = (exit_price - position.entry_price) * position.quantity
        else:  # SHORT
            pnl = (position.entry_price - exit_price) * position.quantity

        pnl_pct = float((pnl / (position.entry_price * position.quantity)) * 100)

        # Calculate duration
        duration = (exit_time - position.opened_at).total_seconds()

        # Create trade metrics
        trade = TradeMetrics(
            symbol=position.symbol,
            strategy=position.strategy or "unknown",
            side=position.side,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
            pnl=pnl,
            pnl_pct=pnl_pct,
            duration_seconds=int(duration),
            entry_time=position.opened_at,
            exit_time=exit_time,
            is_winner=pnl > 0
        )

        self.trades.append(trade)
        self._cache_valid = False  # Invalidate cache

        # Update balance
        self.current_balance += pnl
        self.peak_balance = max(self.peak_balance, self.current_balance)

        # Add equity point
        self._add_equity_point(exit_time)

        logger.info(f"Trade recorded: {position.symbol} {position.side.value} "
                   f"P&L: ${pnl:+,.2f} ({pnl_pct:+.2f}%)")

        return trade

    def _add_equity_point(self, timestamp: datetime):
        """Add a point to the equity curve"""
        total_pnl = self.current_balance - self.initial_balance
        drawdown = self.peak_balance - self.current_balance
        drawdown_pct = float((drawdown / self.peak_balance) * 100) if self.peak_balance > 0 else 0.0

        point = EquityPoint(
            timestamp=timestamp,
            balance=self.current_balance,
            equity=self.current_balance,  # For now, no unrealized P&L
            total_pnl=total_pnl,
            drawdown=drawdown,
            drawdown_pct=drawdown_pct
        )

        self.equity_curve.append(point)

    def calculate_metrics(self) -> PerformanceMetrics:
        """
        Calculate comprehensive performance metrics

        Returns:
            PerformanceMetrics object
        """
        # Use cache if valid
        if self._cache_valid and self._metrics_cache:
            return self._metrics_cache

        if not self.trades:
            return self._empty_metrics()

        # Basic counts
        total_trades = len(self.trades)
        winning_trades = sum(1 for t in self.trades if t.is_winner)
        losing_trades = sum(1 for t in self.trades if not t.is_winner and t.pnl < 0)
        breakeven_trades = sum(1 for t in self.trades if t.pnl == 0)

        # Win/loss rates (as decimals, not percentages, for Kelly Criterion)
        win_rate = (winning_trades / total_trades) if total_trades > 0 else 0.0
        loss_rate = (losing_trades / total_trades) if total_trades > 0 else 0.0

        # P&L calculations
        total_pnl = sum(t.pnl for t in self.trades)
        gross_profit = sum(t.pnl for t in self.trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in self.trades if t.pnl < 0))

        profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else float('inf')

        total_pnl_pct = float((total_pnl / self.initial_balance) * 100)

        # Average wins/losses
        wins = [t for t in self.trades if t.is_winner]
        losses = [t for t in self.trades if not t.is_winner and t.pnl < 0]

        avg_win = (sum(t.pnl for t in wins) / len(wins)) if wins else Decimal("0")
        avg_loss = (sum(t.pnl for t in losses) / len(losses)) if losses else Decimal("0")
        avg_win_pct = (sum(t.pnl_pct for t in wins) / len(wins)) if wins else 0.0
        avg_loss_pct = (sum(t.pnl_pct for t in losses) / len(losses)) if losses else 0.0

        # Consecutive wins/losses
        max_consecutive_wins = self._calculate_max_consecutive(True)
        max_consecutive_losses = self._calculate_max_consecutive(False)

        # Drawdown
        max_drawdown, max_drawdown_pct = self._calculate_max_drawdown()

        # Risk-adjusted returns
        sharpe_ratio = self._calculate_sharpe_ratio()
        sortino_ratio = self._calculate_sortino_ratio()

        # Duration stats
        durations = [t.duration_seconds for t in self.trades]
        avg_duration = int(np.mean(durations)) if durations else 0
        max_duration = max(durations) if durations else 0
        min_duration = min(durations) if durations else 0

        # Time period
        start_date = min(t.entry_time for t in self.trades) if self.trades else None
        end_date = max(t.exit_time for t in self.trades if t.exit_time) if self.trades else None
        days_active = (end_date - start_date).days if (start_date and end_date) else 0

        metrics = PerformanceMetrics(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            breakeven_trades=breakeven_trades,
            win_rate=win_rate,
            loss_rate=loss_rate,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            avg_win_pct=avg_win_pct,
            avg_loss_pct=avg_loss_pct,
            max_consecutive_wins=max_consecutive_wins,
            max_consecutive_losses=max_consecutive_losses,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            avg_duration_seconds=avg_duration,
            max_duration_seconds=max_duration,
            min_duration_seconds=min_duration,
            start_date=start_date,
            end_date=end_date,
            days_active=days_active
        )

        # Cache the result
        self._metrics_cache = metrics
        self._cache_valid = True

        return metrics

    def _empty_metrics(self) -> PerformanceMetrics:
        """Return empty metrics when no trades exist"""
        return PerformanceMetrics(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            breakeven_trades=0,
            win_rate=0.0,
            loss_rate=0.0,
            total_pnl=Decimal("0"),
            total_pnl_pct=0.0,
            gross_profit=Decimal("0"),
            gross_loss=Decimal("0"),
            profit_factor=0.0,
            avg_win=Decimal("0"),
            avg_loss=Decimal("0"),
            avg_win_pct=0.0,
            avg_loss_pct=0.0,
            max_consecutive_wins=0,
            max_consecutive_losses=0,
            max_drawdown=Decimal("0"),
            max_drawdown_pct=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            avg_duration_seconds=0,
            max_duration_seconds=0,
            min_duration_seconds=0,
            start_date=None,
            end_date=None,
            days_active=0
        )

    def _calculate_max_consecutive(self, winners: bool) -> int:
        """Calculate maximum consecutive wins or losses"""
        if not self.trades:
            return 0

        max_consecutive = 0
        current_consecutive = 0

        for trade in self.trades:
            if trade.is_winner == winners:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0

        return max_consecutive

    def _calculate_max_drawdown(self) -> Tuple[Decimal, float]:
        """Calculate maximum drawdown in absolute and percentage terms"""
        if not self.equity_curve:
            return Decimal("0"), 0.0

        max_dd = max(point.drawdown for point in self.equity_curve)
        max_dd_pct = max(point.drawdown_pct for point in self.equity_curve)

        return max_dd, max_dd_pct

    def _calculate_sharpe_ratio(self, risk_free_rate: float = 0.02) -> float:
        """
        Calculate Sharpe ratio (risk-adjusted return)

        Formula: (Mean Return - Risk Free Rate) / Std Dev of Returns

        Args:
            risk_free_rate: Annual risk-free rate (default: 2%)

        Returns:
            Sharpe ratio
        """
        if len(self.trades) < 2:
            return 0.0

        # Calculate returns
        returns = np.array([float(t.pnl_pct) for t in self.trades])

        # Calculate mean and std dev
        mean_return = np.mean(returns)
        std_return = np.std(returns)

        if std_return == 0:
            return 0.0

        # Convert annual risk-free rate to per-trade
        # Assuming ~100 trades per year
        risk_free_per_trade = risk_free_rate / 100

        sharpe = (mean_return - risk_free_per_trade) / std_return

        return float(sharpe)

    def _calculate_sortino_ratio(self, risk_free_rate: float = 0.02) -> float:
        """
        Calculate Sortino ratio (downside risk-adjusted return)

        Similar to Sharpe but only considers downside volatility

        Args:
            risk_free_rate: Annual risk-free rate (default: 2%)

        Returns:
            Sortino ratio
        """
        if len(self.trades) < 2:
            return 0.0

        # Calculate returns
        returns = np.array([float(t.pnl_pct) for t in self.trades])

        # Calculate mean
        mean_return = np.mean(returns)

        # Calculate downside deviation (only negative returns)
        downside_returns = returns[returns < 0]

        if len(downside_returns) == 0:
            return float('inf')  # No losses

        downside_std = np.std(downside_returns)

        if downside_std == 0:
            return 0.0

        # Convert annual risk-free rate to per-trade
        risk_free_per_trade = risk_free_rate / 100

        sortino = (mean_return - risk_free_per_trade) / downside_std

        return float(sortino)

    def get_symbol_performance(self, symbol: str) -> SymbolPerformance:
        """Get performance metrics for a specific symbol"""
        symbol_trades = [t for t in self.trades if t.symbol == symbol]

        if not symbol_trades:
            return SymbolPerformance(
                symbol=symbol,
                metrics=self._empty_metrics(),
                trades=[]
            )

        # Create temporary tracker for symbol
        temp_tracker = PerformanceTracker(self.initial_balance)
        temp_tracker.trades = symbol_trades

        return SymbolPerformance(
            symbol=symbol,
            metrics=temp_tracker.calculate_metrics(),
            trades=symbol_trades
        )

    def get_strategy_performance(self, strategy: str) -> StrategyPerformance:
        """Get performance metrics for a specific strategy"""
        strategy_trades = [t for t in self.trades if t.strategy == strategy]

        if not strategy_trades:
            return StrategyPerformance(
                strategy=strategy,
                metrics=self._empty_metrics(),
                trades=[]
            )

        # Create temporary tracker for strategy
        temp_tracker = PerformanceTracker(self.initial_balance)
        temp_tracker.trades = strategy_trades

        return StrategyPerformance(
            strategy=strategy,
            metrics=temp_tracker.calculate_metrics(),
            trades=strategy_trades
        )

    def get_all_symbols(self) -> List[str]:
        """Get list of all symbols traded"""
        return list(set(t.symbol for t in self.trades))

    def get_all_strategies(self) -> List[str]:
        """Get list of all strategies used"""
        return list(set(t.strategy for t in self.trades))

    def log_performance_report(self):
        """Log comprehensive performance report"""
        metrics = self.calculate_metrics()

        logger.info("=" * 80)
        logger.info("📊 PERFORMANCE REPORT")
        logger.info("=" * 80)

        # Overall stats
        logger.info(f"\n📈 Overall Performance:")
        logger.info(f"   Total Trades: {metrics.total_trades}")
        logger.info(f"   Win Rate: {metrics.win_rate:.2f}%")
        logger.info(f"   Total P&L: ${metrics.total_pnl:+,.2f} ({metrics.total_pnl_pct:+.2f}%)")
        logger.info(f"   Current Balance: ${self.current_balance:,.2f}")

        # Win/Loss breakdown
        logger.info(f"\n✅ Wins vs ❌ Losses:")
        logger.info(f"   Winning Trades: {metrics.winning_trades} ({metrics.win_rate:.1f}%)")
        logger.info(f"   Losing Trades: {metrics.losing_trades} ({metrics.loss_rate:.1f}%)")
        logger.info(f"   Avg Win: ${metrics.avg_win:,.2f} ({metrics.avg_win_pct:+.2f}%)")
        logger.info(f"   Avg Loss: ${metrics.avg_loss:,.2f} ({metrics.avg_loss_pct:.2f}%)")

        # Risk metrics
        logger.info(f"\n⚠️  Risk Metrics:")
        logger.info(f"   Profit Factor: {metrics.profit_factor:.2f}")
        logger.info(f"   Max Drawdown: ${metrics.max_drawdown:,.2f} ({metrics.max_drawdown_pct:.2f}%)")
        logger.info(f"   Max Consecutive Wins: {metrics.max_consecutive_wins}")
        logger.info(f"   Max Consecutive Losses: {metrics.max_consecutive_losses}")

        # Risk-adjusted returns
        logger.info(f"\n📊 Risk-Adjusted Returns:")
        logger.info(f"   Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
        logger.info(f"   Sortino Ratio: {metrics.sortino_ratio:.2f}")

        # Per-symbol breakdown
        symbols = self.get_all_symbols()
        if symbols:
            logger.info(f"\n🔍 Per-Symbol Performance:")
            for symbol in sorted(symbols):
                perf = self.get_symbol_performance(symbol)
                logger.info(f"   {symbol}: {perf.metrics.total_trades} trades, "
                           f"Win Rate: {perf.metrics.win_rate:.1f}%, "
                           f"P&L: ${perf.metrics.total_pnl:+,.2f}")

        logger.info("=" * 80)


# Global instance
_performance_tracker: Optional[PerformanceTracker] = None


def get_performance_tracker(initial_balance: Optional[Decimal] = None) -> PerformanceTracker:
    """Get or create performance tracker instance"""
    global _performance_tracker
    if _performance_tracker is None:
        balance = initial_balance or Decimal("10000")
        _performance_tracker = PerformanceTracker(initial_balance=balance)
    return _performance_tracker


def reset_performance_tracker():
    """Reset performance tracker (for testing)"""
    global _performance_tracker
    _performance_tracker = None
