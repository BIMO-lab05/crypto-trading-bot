"""
Advanced Kelly Criterion Position Sizing Module
Purpose: Optimal position sizing based on edge and historical win rate for Statistical Arbitrage

Kelly Criterion Formula:
    f* = (b * p - q) / b

    Where:
    - f* = optimal fraction of capital to bet
    - b = odds (average_win / average_loss)
    - p = probability of winning (win_rate)
    - q = probability of losing (1 - p)

    Simplified:
    f* = p - q/b = p - (1-p)/b = (b*p - (1-p)) / b

Features:
- Full Kelly: Theoretical optimal (maximum growth rate)
- Fractional Kelly: Reduced variance (25-50% of full Kelly)
- Dynamic Kelly: Adjusts based on recent performance
- Rolling win rate tracking (last 50 trades)
- PostgreSQL persistence for metrics
- API endpoint integration

Risk Management:
- Never exceed 10% of capital per position
- Conservative default: 25% Kelly fraction
- Dynamic adjustment: 10% to 50% Kelly based on streak

Phase 3.2 - Statistical Arbitrage Position Sizing
Author: Trading Bot Development Team
Date: 2025-12-11
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple, Any
from collections import deque
import json

logger = logging.getLogger(__name__)


class KellyMode(str, Enum):
    """
    Kelly Criterion calculation modes

    FULL: Maximum growth rate (high variance)
    FRACTIONAL: Conservative (25% of full Kelly)
    DYNAMIC: Adjusts between 10-50% based on recent performance
    """
    FULL = "FULL"  # Full Kelly - theoretical optimal but high variance
    FRACTIONAL = "FRACTIONAL"  # Fractional Kelly (default 25%)
    DYNAMIC = "DYNAMIC"  # Dynamic Kelly - adjusts based on streak


@dataclass
class TradeRecord:
    """
    Record of a completed trade for performance tracking

    Attributes:
        trade_id: Unique trade identifier
        symbol: Trading symbol (e.g., 'BTCUSDT/ETHUSDT')
        entry_time: Trade entry timestamp
        exit_time: Trade exit timestamp
        entry_price: Entry price
        exit_price: Exit price
        pnl: Profit/Loss in base currency
        pnl_pct: Profit/Loss as percentage
        is_win: True if trade was profitable
        strategy: Strategy that generated the trade
        kelly_suggested: Kelly-suggested position size at entry
        actual_size: Actual position size used
    """
    trade_id: str
    symbol: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    is_win: bool
    strategy: str = "stat_arb"
    kelly_suggested: Optional[float] = None
    actual_size: Optional[float] = None


@dataclass
class KellyResult:
    """
    Result of Kelly Criterion position size calculation

    Attributes:
        position_size_pct: Recommended position size as % of capital
        position_value: Dollar value of recommended position
        quantity: Number of units to trade
        full_kelly_pct: Full Kelly percentage (before fraction applied)
        kelly_fraction_used: Fraction of Kelly used (e.g., 0.25)
        mode: Kelly mode used (FULL, FRACTIONAL, DYNAMIC)
        win_rate: Win rate used in calculation
        avg_win_pct: Average win percentage
        avg_loss_pct: Average loss percentage
        edge: Expected edge (positive = profitable)
        confidence_level: Confidence in the estimate (based on sample size)
        reasoning: Human-readable explanation
        metadata: Additional calculation details
    """
    position_size_pct: float
    position_value: Decimal
    quantity: Decimal
    full_kelly_pct: float
    kelly_fraction_used: float
    mode: KellyMode
    win_rate: float
    avg_win_pct: float
    avg_loss_pct: float
    edge: float
    confidence_level: float
    reasoning: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class KellyPositionSizer:
    """
    Advanced Kelly Criterion Position Sizing System

    Implements three Kelly variants:
    1. Full Kelly: f* = (bp - q) / b
       - Maximum geometric growth rate
       - High variance (not recommended for live trading)

    2. Fractional Kelly: fraction * full_kelly
       - Reduces variance while maintaining positive expectancy
       - Default: 25% Kelly (reduces variance by ~60%)

    3. Dynamic Kelly: Adjusts fraction based on recent performance
       - Increase after wins (up to 50% Kelly)
       - Decrease after losses (down to 10% Kelly)
       - Smoother equity curve

    Usage:
        sizer = KellyPositionSizer()

        # Record trades
        sizer.record_trade(TradeRecord(...))

        # Calculate position size
        result = sizer.calculate_position_size(
            capital=10000,
            current_price=50000,
            mode=KellyMode.DYNAMIC
        )
    """

    # Maximum position size (10% of capital) - safety cap
    MAX_POSITION_PCT: float = 10.0

    # Minimum position size (1% of capital) - ensure meaningful trades
    MIN_POSITION_PCT: float = 1.0

    # Minimum trades required for Kelly calculation
    MIN_TRADES_FOR_KELLY: int = 10

    # Rolling window size for win rate calculation
    ROLLING_WINDOW: int = 50

    def __init__(
        self,
        default_kelly_fraction: float = 0.25,
        max_kelly_fraction: float = 0.50,
        min_kelly_fraction: float = 0.10,
        fallback_position_pct: float = 3.0,
        streak_adjustment_factor: float = 0.05,
        db_session_factory: Optional[Any] = None,
    ):
        """
        Initialize Kelly Position Sizer

        Args:
            default_kelly_fraction: Default fraction of Kelly to use (0.25 = 25%)
            max_kelly_fraction: Maximum Kelly fraction for dynamic mode (0.50 = 50%)
            min_kelly_fraction: Minimum Kelly fraction for dynamic mode (0.10 = 10%)
            fallback_position_pct: Position size when insufficient data (3%)
            streak_adjustment_factor: How much to adjust per streak trade (0.05 = 5%)
            db_session_factory: Optional database session factory for persistence
        """
        # Configuration parameters
        self.default_kelly_fraction = default_kelly_fraction
        self.max_kelly_fraction = max_kelly_fraction
        self.min_kelly_fraction = min_kelly_fraction
        self.fallback_position_pct = fallback_position_pct
        self.streak_adjustment_factor = streak_adjustment_factor

        # Database connection (optional)
        self.db_session_factory = db_session_factory

        # Trade history (rolling window)
        self._trade_history: deque = deque(maxlen=self.ROLLING_WINDOW)

        # Performance tracking
        self._total_trades: int = 0
        self._winning_trades: int = 0
        self._losing_trades: int = 0
        self._total_wins_pct: float = 0.0
        self._total_losses_pct: float = 0.0

        # Streak tracking for dynamic Kelly
        self._current_streak: int = 0  # Positive = win streak, negative = lose streak
        self._current_kelly_fraction: float = default_kelly_fraction

        # Statistics cache
        self._stats_cache: Optional[Dict] = None
        self._stats_cache_time: Optional[datetime] = None

        logger.info(
            f"KellyPositionSizer initialized: "
            f"default_fraction={default_kelly_fraction}, "
            f"range=[{min_kelly_fraction}, {max_kelly_fraction}], "
            f"fallback={fallback_position_pct}%"
        )

    def record_trade(self, trade: TradeRecord) -> None:
        """
        Record a completed trade for performance tracking

        This updates:
        - Rolling win rate (last 50 trades)
        - Average win/loss percentages
        - Current streak
        - Dynamic Kelly fraction

        Args:
            trade: TradeRecord with trade details
        """
        # Add to rolling window
        self._trade_history.append(trade)

        # Update total counts
        self._total_trades += 1

        if trade.is_win:
            self._winning_trades += 1
            self._total_wins_pct += trade.pnl_pct

            # Update streak (positive for wins)
            if self._current_streak >= 0:
                self._current_streak += 1
            else:
                self._current_streak = 1
        else:
            self._losing_trades += 1
            self._total_losses_pct += abs(trade.pnl_pct)

            # Update streak (negative for losses)
            if self._current_streak <= 0:
                self._current_streak -= 1
            else:
                self._current_streak = -1

        # Update dynamic Kelly fraction
        self._update_dynamic_kelly_fraction()

        # Invalidate stats cache
        self._stats_cache = None

        logger.debug(
            f"Trade recorded: {trade.symbol} {'WIN' if trade.is_win else 'LOSS'} "
            f"({trade.pnl_pct:+.2f}%), streak={self._current_streak}, "
            f"kelly_fraction={self._current_kelly_fraction:.2%}"
        )

        # Persist to database if available
        if self.db_session_factory:
            self._persist_trade(trade)

    def _update_dynamic_kelly_fraction(self) -> None:
        """
        Update Kelly fraction based on recent performance streak

        Logic:
        - Win streak: Increase fraction (up to max_kelly_fraction)
        - Lose streak: Decrease fraction (down to min_kelly_fraction)
        - Each streak trade adjusts by streak_adjustment_factor
        """
        # Calculate new fraction based on streak
        # For performance-based scaling: +20% after 2+ wins, -30% after 2+ losses
        if self._current_streak >= 2:  # 2+ win streak
            # Apply +20% bonus to the default Kelly fraction
            new_fraction = self.default_kelly_fraction * 1.20
        elif self._current_streak <= -2:  # 2+ loss streak
            # Apply -30% penalty to the default Kelly fraction
            new_fraction = self.default_kelly_fraction * 0.70
        else:
            # No streak, use default
            new_fraction = self.default_kelly_fraction

        # Clamp to valid range
        self._current_kelly_fraction = max(
            self.min_kelly_fraction,
            min(self.max_kelly_fraction, new_fraction)
        )

    def calculate_position_size(
        self,
        capital: float,
        current_price: float,
        mode: KellyMode = KellyMode.FRACTIONAL,
        signal_confidence: Optional[float] = None,
        stop_loss_pct: Optional[float] = None,
        daily_pnl: Optional[Decimal] = None,
        total_capital: Optional[float] = None,
    ) -> KellyResult:
        """
        Calculate optimal position size using Kelly Criterion

        Args:
            capital: Available capital for trading
            current_price: Current asset price
            mode: Kelly calculation mode (FULL, FRACTIONAL, DYNAMIC)
            signal_confidence: Optional signal confidence (0-1) for adjustment
            stop_loss_pct: Optional stop loss percentage for risk limiting
            daily_pnl: Optional daily P&L for performance-based adjustment
            total_capital: Optional total capital for calculating daily P&L percentage

        Returns:
            KellyResult with recommended position size and details
        """
        # Get current performance stats
        stats = self.get_performance_stats()

        # Calculate Kelly fraction
        full_kelly_pct, edge = self._calculate_full_kelly(stats)

        # Determine Kelly fraction based on mode
        if mode == KellyMode.FULL:
            kelly_fraction = 1.0
        elif mode == KellyMode.DYNAMIC:
            kelly_fraction = self._current_kelly_fraction
        else:  # FRACTIONAL
            kelly_fraction = self.default_kelly_fraction

        # Apply Kelly fraction
        position_pct = full_kelly_pct * kelly_fraction

        # Adjust by signal confidence if provided
        confidence_adjustment = 1.0
        if signal_confidence is not None:
            # Scale position by confidence (0.5 to 1.5x)
            confidence_adjustment = 0.5 + signal_confidence
            position_pct *= confidence_adjustment

        # Apply risk limit if stop loss provided
        risk_limited = False
        if stop_loss_pct is not None and stop_loss_pct > 0:
            # Max position such that loss at stop = 2% of capital
            max_risk_pct = 2.0  # 2% max risk per trade
            max_position_by_risk = max_risk_pct / stop_loss_pct * 100
            if position_pct > max_position_by_risk:
                position_pct = max_position_by_risk
                risk_limited = True

        # Apply daily P&L adjustment if provided
        daily_pnl_adjustment = 1.0
        if daily_pnl is not None and total_capital is not None and total_capital > 0:
            daily_pnl_pct = float(daily_pnl) / total_capital * 100  # Convert to percentage

            # Performance-based scaling based on daily P&L
            if daily_pnl_pct > 0.5:  # Daily gain > 0.5%
                # Increase position size for positive performance
                daily_pnl_adjustment = 1.20  # +20% for good daily performance
            elif daily_pnl_pct < -0.5:  # Daily loss > 0.5%
                # Decrease position size for negative performance
                daily_pnl_adjustment = 0.70  # -30% for poor daily performance
            # If daily P&L is between -0.5% and 0.5%, no adjustment (daily_pnl_adjustment = 1.0)

            position_pct *= daily_pnl_adjustment

        # Apply min/max limits
        position_pct = max(self.MIN_POSITION_PCT, min(self.MAX_POSITION_PCT, position_pct))

        # Handle insufficient data
        if stats['total_trades'] < self.MIN_TRADES_FOR_KELLY:
            position_pct = self.fallback_position_pct
            reasoning = (
                f"Insufficient trade history ({stats['total_trades']}/{self.MIN_TRADES_FOR_KELLY}). "
                f"Using fallback position size of {self.fallback_position_pct}%"
            )
            confidence_level = 0.0
        else:
            reasoning = self._build_reasoning(
                full_kelly_pct, kelly_fraction, position_pct,
                stats, mode, signal_confidence, risk_limited, daily_pnl_adjustment
            )
            # Confidence based on sample size
            confidence_level = min(1.0, stats['total_trades'] / self.ROLLING_WINDOW)

        # Calculate position value and quantity (handle edge cases)
        position_value = Decimal(str(capital)) * Decimal(str(position_pct / 100))

        # Handle zero or invalid price
        if current_price <= 0:
            quantity = Decimal("0")
        else:
            try:
                quantity = position_value / Decimal(str(current_price))
            except (InvalidOperation, ZeroDivisionError):
                quantity = Decimal("0")

        return KellyResult(
            position_size_pct=position_pct,
            position_value=position_value,
            quantity=quantity,
            full_kelly_pct=full_kelly_pct,
            kelly_fraction_used=kelly_fraction,
            mode=mode,
            win_rate=stats['win_rate'],
            avg_win_pct=stats['avg_win_pct'],
            avg_loss_pct=stats['avg_loss_pct'],
            edge=edge,
            confidence_level=confidence_level,
            reasoning=reasoning,
            metadata={
                'streak': self._current_streak,
                'total_trades': stats['total_trades'],
                'rolling_trades': len(self._trade_history),
                'confidence_adjustment': confidence_adjustment,
                'risk_limited': risk_limited,
            }
        )

    def _calculate_full_kelly(self, stats: Dict) -> Tuple[float, float]:
        """
        Calculate full Kelly percentage

        Formula: f* = (b*p - q) / b
        Where:
        - b = odds = avg_win / avg_loss
        - p = win_rate
        - q = 1 - p

        Args:
            stats: Performance statistics dictionary

        Returns:
            Tuple of (full_kelly_pct, edge)
        """
        win_rate = stats['win_rate']
        avg_win = stats['avg_win_pct']
        avg_loss = stats['avg_loss_pct']

        # Validate inputs - win_rate must be strictly between 0 and 1
        if win_rate <= 0 or win_rate >= 1:
            logger.debug(f"Invalid win rate {win_rate}, returning 0")
            return 0.0, 0.0

        if avg_loss <= 0:
            logger.debug(f"Invalid avg_loss {avg_loss}, returning 0")
            return 0.0, 0.0

        # Calculate odds (b)
        odds = avg_win / avg_loss

        # Loss probability (q)
        loss_rate = 1 - win_rate

        # Kelly formula: f* = (b*p - q) / b
        kelly = (odds * win_rate - loss_rate) / odds

        # Edge = expected return per trade
        edge = (win_rate * avg_win) - (loss_rate * avg_loss)

        # Kelly can be negative (no edge) - cap at 0
        kelly = max(0.0, kelly)

        # Convert to percentage
        kelly_pct = kelly * 100

        logger.debug(
            f"Kelly calculation: win_rate={win_rate:.2%}, odds={odds:.2f}, "
            f"kelly={kelly:.4f} ({kelly_pct:.2f}%), edge={edge:.4f}"
        )

        return kelly_pct, edge

    def get_performance_stats(self, force_recalculate: bool = False) -> Dict:
        """
        Get current performance statistics

        Returns rolling statistics from last ROLLING_WINDOW trades.
        Results are cached for 60 seconds.

        Args:
            force_recalculate: Force recalculation ignoring cache

        Returns:
            Dictionary with:
            - win_rate: Probability of winning (0-1)
            - avg_win_pct: Average win percentage
            - avg_loss_pct: Average loss percentage (positive value)
            - total_trades: Number of trades in calculation
            - profit_factor: Total wins / Total losses
            - expectancy: Expected return per trade
        """
        # Check cache (60 second TTL)
        if (
            not force_recalculate
            and self._stats_cache is not None
            and self._stats_cache_time is not None
            and (datetime.now() - self._stats_cache_time).total_seconds() < 60
        ):
            return self._stats_cache

        # Calculate from rolling window
        if len(self._trade_history) == 0:
            stats = {
                'win_rate': 0.5,  # Neutral assumption
                'avg_win_pct': 2.0,  # Default 2%
                'avg_loss_pct': 1.5,  # Default 1.5%
                'total_trades': 0,
                'rolling_trades': 0,
                'profit_factor': 0.0,
                'expectancy': 0.0,
                'current_streak': self._current_streak,
                'current_kelly_fraction': self._current_kelly_fraction,
            }
            self._stats_cache = stats
            self._stats_cache_time = datetime.now()
            return stats

        # Calculate from rolling history
        trades = list(self._trade_history)

        wins = [t for t in trades if t.is_win]
        losses = [t for t in trades if not t.is_win]

        total = len(trades)
        win_count = len(wins)
        loss_count = len(losses)

        # Win rate
        win_rate = win_count / total if total > 0 else 0.5

        # Average win percentage
        avg_win_pct = (
            sum(t.pnl_pct for t in wins) / win_count
            if win_count > 0 else 2.0
        )

        # Average loss percentage (as positive value)
        avg_loss_pct = (
            sum(abs(t.pnl_pct) for t in losses) / loss_count
            if loss_count > 0 else 1.5
        )

        # Profit factor
        total_wins = sum(t.pnl_pct for t in wins) if wins else 0
        total_losses = sum(abs(t.pnl_pct) for t in losses) if losses else 0
        profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')

        # Expectancy (expected return per trade)
        expectancy = (win_rate * avg_win_pct) - ((1 - win_rate) * avg_loss_pct)

        stats = {
            'win_rate': win_rate,
            'avg_win_pct': avg_win_pct,
            'avg_loss_pct': avg_loss_pct,
            'total_trades': self._total_trades,
            'rolling_trades': total,
            'profit_factor': profit_factor,
            'expectancy': expectancy,
            'current_streak': self._current_streak,
            'current_kelly_fraction': self._current_kelly_fraction,
        }

        self._stats_cache = stats
        self._stats_cache_time = datetime.now()

        return stats

    def _build_reasoning(
        self,
        full_kelly_pct: float,
        kelly_fraction: float,
        final_pct: float,
        stats: Dict,
        mode: KellyMode,
        signal_confidence: Optional[float],
        risk_limited: bool,
        daily_pnl_adjustment: float = 1.0
    ) -> str:
        """
        Build human-readable reasoning for position size recommendation

        Args:
            full_kelly_pct: Full Kelly percentage
            kelly_fraction: Fraction of Kelly used
            final_pct: Final position percentage
            stats: Performance statistics
            mode: Kelly mode used
            signal_confidence: Signal confidence if provided
            risk_limited: Whether risk limit was applied

        Returns:
            Human-readable explanation string
        """
        parts = []

        # Base calculation
        parts.append(
            f"Kelly calculation: W={stats['win_rate']:.1%}, "
            f"Avg Win={stats['avg_win_pct']:.2f}%, "
            f"Avg Loss={stats['avg_loss_pct']:.2f}%"
        )

        # Full Kelly result
        parts.append(f"Full Kelly suggests {full_kelly_pct:.2f}%")

        # Mode-specific adjustment
        if mode == KellyMode.FULL:
            parts.append("Using full Kelly (maximum growth, high variance)")
        elif mode == KellyMode.FRACTIONAL:
            parts.append(f"Using {kelly_fraction:.0%} fractional Kelly for safety")
        else:  # DYNAMIC
            streak_desc = f"{'+' if self._current_streak > 0 else ''}{self._current_streak}"
            parts.append(
                f"Dynamic Kelly at {kelly_fraction:.0%} (streak: {streak_desc})"
            )

        # Confidence adjustment
        if signal_confidence is not None:
            parts.append(f"Confidence adjustment: {signal_confidence:.1%}")

        # Daily P&L adjustment
        if daily_pnl_adjustment != 1.0:
            adj_pct = (daily_pnl_adjustment - 1.0) * 100
            parts.append(f"Daily P&L adjustment: {adj_pct:+.1f}%")

        # Risk limit
        if risk_limited:
            parts.append("Risk-limited to 2% max loss at stop")

        # Final position
        parts.append(f"Final position size: {final_pct:.2f}%")

        # Edge assessment
        if stats['expectancy'] > 0:
            parts.append(f"Positive edge: +{stats['expectancy']:.2f}% per trade")
        else:
            parts.append(f"Warning: Negative edge ({stats['expectancy']:.2f}%)")

        return " | ".join(parts)

    def _persist_trade(self, trade: TradeRecord) -> None:
        """
        Persist the sizer's full state (aggregates + rolling window) to the
        kelly_state row. Called after each trade is recorded so the Kelly
        fraction and streak survive restarts.

        We persist the full state rather than each trade row because Kelly
        sizing only consumes aggregates plus the recent rolling window, and
        a single upsert on a single row is cheaper than per-trade inserts.
        """
        if self.db_session_factory is None:
            return

        try:
            from app.risk.kelly_persistence import save_state

            # db_session_factory is the sync sessionmaker from
            # database.connection.DatabaseManager — calling it returns a
            # Session that exposes connection() for Core operations.
            session = self.db_session_factory()
            try:
                save_state(session.connection(), self)
                session.commit()
            finally:
                session.close()
        except Exception as e:
            logger.error(f"Failed to persist Kelly state after trade {trade.trade_id}: {e}")

    def get_kelly_stats(self) -> Dict:
        """
        Get comprehensive Kelly statistics for API endpoint

        Returns:
            Dictionary with all Kelly-related statistics
        """
        stats = self.get_performance_stats()
        full_kelly, edge = self._calculate_full_kelly(stats)

        return {
            'kelly': {
                'full_kelly_pct': full_kelly,
                'current_fraction': self._current_kelly_fraction,
                'default_fraction': self.default_kelly_fraction,
                'edge': edge,
            },
            'performance': {
                'win_rate': stats['win_rate'],
                'avg_win_pct': stats['avg_win_pct'],
                'avg_loss_pct': stats['avg_loss_pct'],
                'profit_factor': stats['profit_factor'],
                'expectancy': stats['expectancy'],
            },
            'trades': {
                'total_trades': stats['total_trades'],
                'rolling_window': self.ROLLING_WINDOW,
                'trades_in_window': stats['rolling_trades'],
                'min_for_kelly': self.MIN_TRADES_FOR_KELLY,
                'has_sufficient_data': stats['total_trades'] >= self.MIN_TRADES_FOR_KELLY,
            },
            'streak': {
                'current_streak': self._current_streak,
                'streak_type': 'win' if self._current_streak > 0 else ('loss' if self._current_streak < 0 else 'none'),
            },
            'limits': {
                'max_position_pct': self.MAX_POSITION_PCT,
                'min_position_pct': self.MIN_POSITION_PCT,
                'fallback_pct': self.fallback_position_pct,
            },
            'timestamp': datetime.now().isoformat(),
        }

    def load_trades_from_db(self, limit: int = 50) -> int:
        """
        Restore the sizer state (aggregates + rolling window) from the
        kelly_state row. The `limit` argument is retained for API
        compatibility but is implicitly bounded by ROLLING_WINDOW since
        that's all we persist.

        Returns:
            Number of trades restored to the rolling window. 0 means either
            no row was found (fresh deploy) or no factory was configured.
        """
        if self.db_session_factory is None:
            logger.warning("No database session factory configured")
            return 0

        try:
            from app.risk.kelly_persistence import load_state

            session = self.db_session_factory()
            try:
                restored = load_state(session.connection(), self)
                session.commit()
            finally:
                session.close()

            logger.info(
                f"Loaded Kelly state: {self._total_trades} trades total, "
                f"{restored} in rolling window"
            )
            return restored

        except Exception as e:
            logger.error(f"Failed to load Kelly state from database: {e}")
            return 0

    def reset(self) -> None:
        """Reset all tracking data to initial state"""
        self._trade_history.clear()
        self._total_trades = 0
        self._winning_trades = 0
        self._losing_trades = 0
        self._total_wins_pct = 0.0
        self._total_losses_pct = 0.0
        self._current_streak = 0
        self._current_kelly_fraction = self.default_kelly_fraction
        self._stats_cache = None
        self._stats_cache_time = None

        logger.info("KellyPositionSizer reset to initial state")

    def simulate_kelly(
        self,
        win_rate: float,
        avg_win_pct: float,
        avg_loss_pct: float,
        capital: float = 10000,
        current_price: float = 50000,
        mode: KellyMode = KellyMode.FRACTIONAL
    ) -> KellyResult:
        """
        Simulate Kelly calculation with hypothetical parameters

        Useful for:
        - Testing different scenarios
        - Strategy optimization
        - What-if analysis

        Args:
            win_rate: Hypothetical win rate (0-1)
            avg_win_pct: Hypothetical average win percentage
            avg_loss_pct: Hypothetical average loss percentage
            capital: Capital for position calculation
            current_price: Price for quantity calculation
            mode: Kelly mode to use

        Returns:
            KellyResult with simulated position size
        """
        # Handle edge case: 100% win rate would cause division by zero
        # in profit_factor calculation, so cap it at 0.9999
        safe_win_rate = min(0.9999, max(0.0001, win_rate))

        # Safe loss rate (avoid division by zero)
        loss_rate = 1 - safe_win_rate

        # Create temporary stats dict
        temp_stats = {
            'win_rate': safe_win_rate,
            'avg_win_pct': avg_win_pct,
            'avg_loss_pct': avg_loss_pct,
            'total_trades': self.MIN_TRADES_FOR_KELLY,  # Bypass minimum check
            'rolling_trades': self.MIN_TRADES_FOR_KELLY,
            'profit_factor': (
                (safe_win_rate * avg_win_pct) / (loss_rate * avg_loss_pct)
                if avg_loss_pct > 0 and loss_rate > 0 else 0
            ),
            'expectancy': (safe_win_rate * avg_win_pct) - (loss_rate * avg_loss_pct),
            'current_streak': 0,
            'current_kelly_fraction': self.default_kelly_fraction,
        }

        # Calculate Kelly
        full_kelly_pct, edge = self._calculate_full_kelly(temp_stats)

        # Determine fraction
        if mode == KellyMode.FULL:
            kelly_fraction = 1.0
        elif mode == KellyMode.DYNAMIC:
            kelly_fraction = self.default_kelly_fraction
        else:
            kelly_fraction = self.default_kelly_fraction

        # Apply fraction
        position_pct = full_kelly_pct * kelly_fraction

        # Apply limits
        position_pct = max(self.MIN_POSITION_PCT, min(self.MAX_POSITION_PCT, position_pct))

        # Calculate values (handle edge cases)
        position_value = Decimal(str(capital)) * Decimal(str(position_pct / 100))

        if current_price <= 0:
            quantity = Decimal("0")
        else:
            try:
                quantity = position_value / Decimal(str(current_price))
            except (InvalidOperation, ZeroDivisionError):
                quantity = Decimal("0")

        return KellyResult(
            position_size_pct=position_pct,
            position_value=position_value,
            quantity=quantity,
            full_kelly_pct=full_kelly_pct,
            kelly_fraction_used=kelly_fraction,
            mode=mode,
            win_rate=safe_win_rate,
            avg_win_pct=avg_win_pct,
            avg_loss_pct=avg_loss_pct,
            edge=edge,
            confidence_level=1.0,  # Simulation has "perfect" data
            reasoning=f"SIMULATION: Win rate={safe_win_rate:.1%}, Avg Win={avg_win_pct:.2f}%, Avg Loss={avg_loss_pct:.2f}%",
            metadata={'simulated': True}
        )


# Global instance
_kelly_sizer: Optional[KellyPositionSizer] = None


def get_kelly_sizer() -> KellyPositionSizer:
    """
    Get or create global Kelly position sizer instance

    Returns:
        KellyPositionSizer singleton instance
    """
    global _kelly_sizer
    if _kelly_sizer is None:
        _kelly_sizer = KellyPositionSizer()
    return _kelly_sizer


def reset_kelly_sizer() -> None:
    """Reset global Kelly position sizer instance"""
    global _kelly_sizer
    if _kelly_sizer is not None:
        _kelly_sizer.reset()
    _kelly_sizer = None
