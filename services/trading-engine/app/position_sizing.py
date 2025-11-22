"""
Position Sizing with Kelly Criterion
Purpose: Calculate optimal position sizes based on edge, confidence, and performance data

Kelly Criterion: Optimal fraction to bet = W - [(1 - W) / R]
- W = Win rate (probability of winning)
- R = Win/Loss ratio (average win / average loss)

Features:
- Kelly Criterion calculation
- Fractional Kelly for conservative sizing
- Confidence-based adjustments
- Min/Max position limits
- Risk-per-trade limits
- Integration with performance tracker
"""

import logging
from decimal import Decimal
from typing import Optional, Dict, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class SizingMethod(str, Enum):
    """Position sizing methods"""
    FIXED = "FIXED"  # Fixed percentage of capital
    KELLY = "KELLY"  # Kelly Criterion
    FRACTIONAL_KELLY = "FRACTIONAL_KELLY"  # Conservative Kelly (0.25x to 0.5x)
    CONFIDENCE_ADJUSTED = "CONFIDENCE_ADJUSTED"  # Kelly + confidence modifier


@dataclass
class PositionSizeResult:
    """Position sizing calculation result"""
    position_size_pct: float  # % of capital to allocate
    position_value: Decimal  # Dollar value of position
    quantity: Decimal  # Number of units to buy
    method: SizingMethod
    kelly_fraction: Optional[float]  # Kelly % if applicable
    confidence_modifier: Optional[float]  # Confidence adjustment
    reasoning: str


class PositionSizer:
    """
    Calculate optimal position sizes using various methods

    Default: Fractional Kelly (25% Kelly) with confidence adjustments
    """

    def __init__(
        self,
        min_position_pct: float = 1.0,  # Minimum 1% of capital
        max_position_pct: float = 10.0,  # Maximum 10% of capital
        default_position_pct: float = 3.0,  # Default 3% for fixed sizing
        kelly_fraction: float = 0.25,  # Use 25% of full Kelly (conservative)
        confidence_scaling: bool = True,  # Scale size by signal confidence
        max_risk_per_trade_pct: float = 2.0,  # Max 2% risk per trade
    ):
        """
        Initialize position sizer

        Args:
            min_position_pct: Minimum position size (% of capital)
            max_position_pct: Maximum position size (% of capital)
            default_position_pct: Default position size for fixed method
            kelly_fraction: Fraction of Kelly to use (0.25 = Quarter Kelly)
            confidence_scaling: Enable confidence-based scaling
            max_risk_per_trade_pct: Maximum risk per trade (% of capital)
        """
        self.min_position_pct = min_position_pct
        self.max_position_pct = max_position_pct
        self.default_position_pct = default_position_pct
        self.kelly_fraction = kelly_fraction
        self.confidence_scaling = confidence_scaling
        self.max_risk_per_trade_pct = max_risk_per_trade_pct

        logger.info(
            f"PositionSizer initialized: "
            f"range={min_position_pct:.1f}%-{max_position_pct:.1f}%, "
            f"kelly_fraction={kelly_fraction:.2f}, "
            f"confidence_scaling={confidence_scaling}"
        )

    def calculate_position_size(
        self,
        method: SizingMethod,
        current_balance: Decimal,
        current_price: Decimal,
        signal_confidence: float,
        performance_stats: Optional[Dict] = None,
        stop_loss_pct: Optional[float] = None,
    ) -> PositionSizeResult:
        """
        Calculate position size using specified method

        Args:
            method: Sizing method to use
            current_balance: Available capital
            current_price: Current asset price
            signal_confidence: Signal confidence (0.0 to 1.0)
            performance_stats: Dict with 'win_rate', 'avg_win', 'avg_loss'
            stop_loss_pct: Stop loss distance as % (for risk calculation)

        Returns:
            PositionSizeResult with calculated size
        """
        # Calculate base position size
        if method == SizingMethod.FIXED:
            position_pct = self._calculate_fixed_size()
            kelly_frac = None
            conf_mod = None
            reasoning = f"Fixed sizing at {position_pct:.2f}%"

        elif method == SizingMethod.KELLY:
            position_pct, kelly_frac = self._calculate_kelly_size(performance_stats)
            conf_mod = None
            reasoning = f"Full Kelly: {kelly_frac:.2%} → {position_pct:.2f}%"

        elif method == SizingMethod.FRACTIONAL_KELLY:
            position_pct, kelly_frac = self._calculate_fractional_kelly_size(performance_stats)
            conf_mod = None
            reasoning = f"Fractional Kelly ({self.kelly_fraction}x): {kelly_frac:.2%} → {position_pct:.2f}%"

        elif method == SizingMethod.CONFIDENCE_ADJUSTED:
            position_pct, kelly_frac, conf_mod = self._calculate_confidence_adjusted_size(
                signal_confidence, performance_stats
            )
            reasoning = (
                f"Confidence-adjusted Kelly: "
                f"Kelly={kelly_frac:.2%}, Conf={signal_confidence:.2%}, "
                f"Modifier={conf_mod:.2f}x → {position_pct:.2f}%"
            )
        else:
            # Fallback to fixed
            position_pct = self.default_position_pct
            kelly_frac = None
            conf_mod = None
            reasoning = f"Unknown method, using fixed {position_pct:.2f}%"

        # Apply risk-per-trade limit if stop loss provided
        if stop_loss_pct is not None and stop_loss_pct > 0:
            max_position_by_risk = self.max_risk_per_trade_pct / stop_loss_pct
            if position_pct > max_position_by_risk:
                original_pct = position_pct
                position_pct = max_position_by_risk
                reasoning += f" | Risk-limited: {original_pct:.2f}% → {position_pct:.2f}%"

        # Apply min/max limits
        position_pct = max(self.min_position_pct, min(position_pct, self.max_position_pct))

        # Calculate position value and quantity
        position_value = current_balance * Decimal(str(position_pct / 100))
        quantity = position_value / current_price

        return PositionSizeResult(
            position_size_pct=position_pct,
            position_value=position_value,
            quantity=quantity,
            method=method,
            kelly_fraction=kelly_frac,
            confidence_modifier=conf_mod,
            reasoning=reasoning
        )

    def _calculate_fixed_size(self) -> float:
        """Calculate fixed position size"""
        return self.default_position_pct

    def _calculate_kelly_size(
        self,
        performance_stats: Optional[Dict] = None
    ) -> Tuple[float, float]:
        """
        Calculate full Kelly Criterion position size

        Kelly = W - [(1 - W) / R]
        W = Win rate
        R = Win/Loss ratio

        Returns:
            (position_pct, kelly_fraction)
        """
        if not performance_stats:
            logger.warning("No performance stats, using default sizing")
            return self.default_position_pct, 0.0

        win_rate = performance_stats.get('win_rate', 0.5)
        avg_win = performance_stats.get('avg_win', 0.0)
        avg_loss = abs(performance_stats.get('avg_loss', 0.0))

        # Validate inputs
        if win_rate <= 0 or win_rate >= 1:
            logger.warning(f"Invalid win rate {win_rate}, using default")
            return self.default_position_pct, 0.0

        if avg_loss == 0:
            logger.warning("Average loss is 0, cannot calculate Kelly")
            return self.default_position_pct, 0.0

        # Calculate win/loss ratio
        win_loss_ratio = avg_win / avg_loss

        if win_loss_ratio <= 0:
            logger.warning(f"Invalid win/loss ratio {win_loss_ratio}, using default")
            return self.default_position_pct, 0.0

        # Kelly Criterion
        kelly = win_rate - ((1 - win_rate) / win_loss_ratio)

        # Kelly can be negative (no edge), cap at 0
        kelly = max(0, kelly)

        # Convert to percentage
        kelly_pct = kelly * 100

        logger.info(
            f"Kelly calculation: W={win_rate:.2%}, R={win_loss_ratio:.2f}, "
            f"Kelly={kelly:.4f} ({kelly_pct:.2f}%)"
        )

        return kelly_pct, kelly

    def _calculate_fractional_kelly_size(
        self,
        performance_stats: Optional[Dict] = None
    ) -> Tuple[float, float]:
        """
        Calculate fractional Kelly (conservative)

        Returns:
            (position_pct, kelly_fraction)
        """
        full_kelly_pct, kelly = self._calculate_kelly_size(performance_stats)

        # Apply fraction
        fractional_kelly_pct = full_kelly_pct * self.kelly_fraction

        return fractional_kelly_pct, kelly

    def _calculate_confidence_adjusted_size(
        self,
        signal_confidence: float,
        performance_stats: Optional[Dict] = None
    ) -> Tuple[float, float, float]:
        """
        Calculate position size with confidence adjustments

        Base: Fractional Kelly
        Adjustment: Scale by signal confidence

        Returns:
            (position_pct, kelly_fraction, confidence_modifier)
        """
        # Start with fractional Kelly
        base_pct, kelly = self._calculate_fractional_kelly_size(performance_stats)

        if not self.confidence_scaling:
            return base_pct, kelly, 1.0

        # Calculate confidence modifier
        # High confidence (>0.8): 1.2x - 1.5x
        # Medium confidence (0.6-0.8): 1.0x
        # Low confidence (<0.6): 0.5x - 1.0x

        if signal_confidence >= 0.8:
            # High confidence: boost 20-50%
            conf_modifier = 1.2 + (signal_confidence - 0.8) * 1.5
        elif signal_confidence >= 0.6:
            # Medium confidence: no adjustment
            conf_modifier = 1.0
        else:
            # Low confidence: reduce 50-100%
            conf_modifier = 0.5 + (signal_confidence - 0.5) * 1.0
            conf_modifier = max(0.5, conf_modifier)

        # Apply confidence modifier
        adjusted_pct = base_pct * conf_modifier

        logger.debug(
            f"Confidence adjustment: base={base_pct:.2f}%, "
            f"confidence={signal_confidence:.2%}, modifier={conf_modifier:.2f}x, "
            f"adjusted={adjusted_pct:.2f}%"
        )

        return adjusted_pct, kelly, conf_modifier

    def calculate_stop_loss_distance(
        self,
        position_size_pct: float,
        max_risk_pct: Optional[float] = None
    ) -> float:
        """
        Calculate stop loss distance based on position size and max risk

        Stop Loss % = Max Risk % / Position Size %

        Args:
            position_size_pct: Position size as % of capital
            max_risk_pct: Maximum risk per trade (default: self.max_risk_per_trade_pct)

        Returns:
            Stop loss distance as percentage
        """
        if max_risk_pct is None:
            max_risk_pct = self.max_risk_per_trade_pct

        # Calculate stop loss distance
        stop_loss_pct = max_risk_pct / position_size_pct

        logger.debug(
            f"Stop loss calculation: position_size={position_size_pct:.2f}%, "
            f"max_risk={max_risk_pct:.2f}%, stop_loss={stop_loss_pct:.2%}"
        )

        return stop_loss_pct

    def get_performance_stats_from_tracker(
        self,
        performance_tracker
    ) -> Dict:
        """
        Extract performance stats from PerformanceTracker

        Args:
            performance_tracker: PerformanceTracker instance

        Returns:
            Dict with 'win_rate', 'avg_win', 'avg_loss'
        """
        try:
            metrics = performance_tracker.calculate_metrics()

            # Extract winning and losing trades
            winning_trades = [t for t in performance_tracker.trades if t.pnl > 0]
            losing_trades = [t for t in performance_tracker.trades if t.pnl < 0]

            # Calculate averages
            avg_win = (
                sum([float(t.pnl_pct) for t in winning_trades]) / len(winning_trades)
                if winning_trades else 0.0
            )
            avg_loss = (
                sum([float(t.pnl_pct) for t in losing_trades]) / len(losing_trades)
                if losing_trades else 0.0
            )

            return {
                'win_rate': metrics.win_rate,
                'avg_win': avg_win / 100,  # Convert to decimal (5% → 0.05)
                'avg_loss': avg_loss / 100,
                'total_trades': metrics.total_trades
            }

        except Exception as e:
            logger.error(f"Error extracting performance stats: {e}")
            return {
                'win_rate': 0.5,
                'avg_win': 0.02,
                'avg_loss': -0.01,
                'total_trades': 0
            }


# Global instance
_position_sizer: Optional[PositionSizer] = None


def get_position_sizer() -> PositionSizer:
    """Get or create global position sizer instance"""
    global _position_sizer
    if _position_sizer is None:
        _position_sizer = PositionSizer()
    return _position_sizer


def reset_position_sizer():
    """Reset global instance (for testing)"""
    global _position_sizer
    _position_sizer = None
