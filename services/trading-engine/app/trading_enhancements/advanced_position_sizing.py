"""
Advanced Position Sizing Algorithms
Research Source: Kelly Criterion, Optimal F, ATR-Based Volatility Sizing

Purpose:
- Implement multiple position sizing methods
- Kelly Criterion with fractional variants
- Optimal F calculation
- ATR-based volatility-adjusted sizing
- Anti-Martingale pyramiding
- Risk parity allocation

RESEARCH: Position sizing can impact returns more than entry/exit timing.
Kelly Criterion maximizes long-term growth but full Kelly is too volatile.
Fractional Kelly (25-50%) provides better risk-adjusted returns.
"""

import logging
import numpy as np
from enum import Enum
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from collections import deque

logger = logging.getLogger(__name__)


class AdvancedSizingMethod(Enum):
    """Advanced position sizing methods"""
    FULL_KELLY = "full_kelly"           # Full Kelly Criterion
    HALF_KELLY = "half_kelly"           # 50% Kelly (recommended)
    QUARTER_KELLY = "quarter_kelly"     # 25% Kelly (conservative)
    OPTIMAL_F = "optimal_f"             # Ralph Vince's Optimal F
    ATR_VOLATILITY = "atr_volatility"   # ATR-based sizing
    ANTI_MARTINGALE = "anti_martingale" # Increase after wins
    RISK_PARITY = "risk_parity"         # Volatility-weighted
    FIXED_FRACTIONAL = "fixed_fractional"  # Simple fixed percentage


@dataclass
class PositionSizeResult:
    """Result of position sizing calculation"""
    method: AdvancedSizingMethod
    position_size_pct: float          # Percentage of capital to risk
    position_value: float             # Dollar value of position
    quantity: float                   # Number of units
    stop_distance: float              # Distance to stop loss
    risk_amount: float                # Dollar amount at risk
    kelly_fraction: float             # Kelly percentage used
    confidence_factor: float          # Signal confidence impact
    reasoning: str                    # Explanation of sizing


@dataclass
class AdvancedSizingConfig:
    """Configuration for advanced position sizing"""
    # Kelly parameters
    kelly_fraction: float = 0.25       # Use 25% of Kelly (conservative)
    min_kelly: float = 0.01            # Minimum 1% position
    max_kelly: float = 0.20            # Maximum 20% position
    min_win_rate: float = 0.35         # Min win rate for Kelly sizing
    min_profit_factor: float = 1.2     # Min profit factor for Kelly

    # ATR parameters
    atr_multiplier: float = 2.0        # ATR multiple for stop distance
    atr_risk_pct: float = 0.02         # Risk 2% per trade
    atr_risk_multiplier: float = 2.0   # ATR risk multiplier alias

    # Anti-Martingale parameters
    base_size_pct: float = 0.02        # Start with 2%
    size_multiplier: float = 1.5       # Increase by 50% after wins
    anti_martingale_factor: float = 1.5  # Anti-martingale multiplier alias
    max_pyramid_levels: int = 4        # Max 4 pyramid additions
    max_consecutive_increases: int = 3  # Max consecutive size increases
    reset_on_loss: bool = True         # Reset size after loss

    # Drawdown adjustment
    use_drawdown_adjustment: bool = True  # Reduce sizing during drawdown

    # Fixed fractional
    fixed_risk_pct: float = 0.02       # Fixed 2% risk per trade

    # General limits
    max_position_pct: float = 0.25     # Never more than 25% in one position
    min_position_pct: float = 0.01     # Never less than 1%


class AdvancedPositionSizer:
    """
    Advanced Position Sizing with Multiple Methods

    RESEARCH-BACKED IMPLEMENTATION:
    - Kelly Criterion for optimal growth
    - Fractional Kelly for reduced volatility
    - ATR-based for volatility adjustment
    - Anti-Martingale for trend following
    - Risk parity for portfolio allocation

    Usage:
        sizer = AdvancedPositionSizer(config)

        result = sizer.calculate_kelly(
            win_rate=0.55,
            reward_risk_ratio=2.0,
            capital=10000,
            price=50000
        )
    """

    def __init__(self, config: Optional[AdvancedSizingConfig] = None):
        """Initialize advanced position sizer"""
        self.config = config or AdvancedSizingConfig()
        self._trade_history: deque = deque(maxlen=100)
        self._consecutive_wins = 0
        self._consecutive_losses = 0
        self._pyramid_level = 0
        self._current_anti_martingale_size = self.config.base_size_pct

        logger.info(
            f"AdvancedPositionSizer initialized: "
            f"kelly_fraction={self.config.kelly_fraction}, "
            f"atr_multiplier={self.config.atr_multiplier}"
        )

    def calculate_kelly(
        self,
        win_rate: float,
        reward_risk_ratio: float,
        capital: float,
        price: float,
        confidence: float = 1.0
    ) -> PositionSizeResult:
        """
        Calculate position size using Kelly Criterion

        Formula: f* = W - [(1 - W) / R]
        Where:
            f* = Kelly fraction
            W = Win probability
            R = Reward/Risk ratio

        Args:
            win_rate: Historical win rate (0-1)
            reward_risk_ratio: Average win / Average loss
            capital: Available capital
            price: Current asset price
            confidence: Signal confidence multiplier

        Returns:
            PositionSizeResult with Kelly-optimized sizing
        """
        # Calculate full Kelly percentage
        if reward_risk_ratio <= 0:
            kelly_pct = 0.0
        else:
            kelly_pct = win_rate - ((1 - win_rate) / reward_risk_ratio)

        # Kelly can be negative (don't trade)
        kelly_pct = max(0, kelly_pct)

        # Apply fractional Kelly
        fractional_kelly = kelly_pct * self.config.kelly_fraction

        # Apply confidence factor
        adjusted_kelly = fractional_kelly * confidence

        # Apply limits
        final_pct = self._apply_limits(adjusted_kelly)

        # Calculate values
        position_value = capital * final_pct
        quantity = position_value / price if price > 0 else 0

        # Estimate risk (using default 2% stop)
        stop_distance = price * 0.02
        risk_amount = quantity * stop_distance

        return PositionSizeResult(
            method=AdvancedSizingMethod.HALF_KELLY if self.config.kelly_fraction == 0.5
                   else AdvancedSizingMethod.QUARTER_KELLY if self.config.kelly_fraction == 0.25
                   else AdvancedSizingMethod.FULL_KELLY,
            position_size_pct=final_pct,
            position_value=position_value,
            quantity=quantity,
            stop_distance=stop_distance,
            risk_amount=risk_amount,
            kelly_fraction=kelly_pct,
            confidence_factor=confidence,
            reasoning=f"Kelly={kelly_pct:.2%}, Fractional={fractional_kelly:.2%}, "
                     f"Final={final_pct:.2%} (WR={win_rate:.2%}, R:R={reward_risk_ratio:.2f})"
        )

    def calculate_optimal_f(
        self,
        trade_returns: List[float],
        capital: float,
        price: float
    ) -> PositionSizeResult:
        """
        Calculate position size using Optimal F (Ralph Vince)

        Optimal F maximizes Terminal Wealth Relative (TWR) through
        geometric optimization over historical trades.

        Args:
            trade_returns: List of past trade returns (as percentages)
            capital: Available capital
            price: Current asset price

        Returns:
            PositionSizeResult with Optimal F sizing
        """
        if not trade_returns or len(trade_returns) < 10:
            # Not enough data, use conservative default
            return PositionSizeResult(
                method=AdvancedSizingMethod.OPTIMAL_F,
                position_size_pct=self.config.min_position_pct,
                position_value=capital * self.config.min_position_pct,
                quantity=(capital * self.config.min_position_pct) / price,
                stop_distance=price * 0.02,
                risk_amount=0,
                kelly_fraction=0,
                confidence_factor=1.0,
                reasoning="Insufficient trade history for Optimal F, using minimum"
            )

        # Find the maximum loss
        max_loss = abs(min(trade_returns))
        if max_loss == 0:
            max_loss = 0.01  # Prevent division by zero

        # Test different f values to find optimal
        best_f = 0.01
        best_twr = 0

        for f in np.arange(0.01, 1.0, 0.01):
            twr = 1.0
            for trade_return in trade_returns:
                # HPR = 1 + f * (trade_return / max_loss)
                hpr = 1 + (f * trade_return / max_loss)
                if hpr <= 0:
                    twr = 0
                    break
                twr *= hpr

            if twr > best_twr:
                best_twr = twr
                best_f = f

        # Apply safety factor (use 50% of optimal f)
        safe_f = best_f * 0.5

        # Apply limits
        final_pct = self._apply_limits(safe_f)
        position_value = capital * final_pct
        quantity = position_value / price if price > 0 else 0

        return PositionSizeResult(
            method=AdvancedSizingMethod.OPTIMAL_F,
            position_size_pct=final_pct,
            position_value=position_value,
            quantity=quantity,
            stop_distance=price * max_loss,
            risk_amount=quantity * price * max_loss,
            kelly_fraction=best_f,
            confidence_factor=1.0,
            reasoning=f"Optimal F={best_f:.2%}, Safe F={safe_f:.2%}, TWR={best_twr:.4f}"
        )

    def calculate_atr_based(
        self,
        capital: float,
        price: float,
        atr_value: float,
        atr_multiplier: Optional[float] = None
    ) -> PositionSizeResult:
        """
        Calculate position size based on ATR volatility

        Formula: Position Size = (Risk Amount) / (ATR * Multiplier)

        This method adjusts position size inversely with volatility:
        - High volatility = smaller position
        - Low volatility = larger position

        Args:
            capital: Available capital
            price: Current asset price
            atr_value: Current ATR value
            atr_multiplier: Optional ATR multiple for stop

        Returns:
            PositionSizeResult with ATR-adjusted sizing
        """
        multiplier = atr_multiplier or self.config.atr_multiplier
        risk_pct = self.config.atr_risk_pct

        # Calculate risk amount
        risk_amount = capital * risk_pct

        # Calculate stop distance
        stop_distance = atr_value * multiplier

        # Calculate position size
        if stop_distance > 0:
            quantity = risk_amount / stop_distance
            position_value = quantity * price
            position_pct = position_value / capital if capital > 0 else 0
        else:
            quantity = 0
            position_value = 0
            position_pct = 0

        # Apply limits
        final_pct = self._apply_limits(position_pct)
        if final_pct != position_pct:
            position_value = capital * final_pct
            quantity = position_value / price if price > 0 else 0

        return PositionSizeResult(
            method=AdvancedSizingMethod.ATR_VOLATILITY,
            position_size_pct=final_pct,
            position_value=position_value,
            quantity=quantity,
            stop_distance=stop_distance,
            risk_amount=risk_amount,
            kelly_fraction=0,
            confidence_factor=1.0,
            reasoning=f"ATR={atr_value:.2f}, Stop={stop_distance:.2f}, "
                     f"Risk={risk_pct:.2%} of ${capital:.0f}"
        )

    def calculate_anti_martingale(
        self,
        capital: float,
        price: float,
        last_trade_won: bool
    ) -> PositionSizeResult:
        """
        Calculate position size using Anti-Martingale

        Anti-Martingale increases position after wins and decreases after losses.
        This is the opposite of traditional Martingale and is more suitable
        for trend-following strategies.

        Args:
            capital: Available capital
            price: Current asset price
            last_trade_won: Whether the last trade was a winner

        Returns:
            PositionSizeResult with Anti-Martingale sizing
        """
        # Update streak and position size
        if last_trade_won:
            self._consecutive_wins += 1
            self._consecutive_losses = 0

            if self._pyramid_level < self.config.max_pyramid_levels:
                self._pyramid_level += 1
                self._current_anti_martingale_size = min(
                    self.config.base_size_pct * (self.config.size_multiplier ** self._pyramid_level),
                    self.config.max_position_pct
                )
        else:
            self._consecutive_losses += 1
            self._consecutive_wins = 0

            if self.config.reset_on_loss:
                self._pyramid_level = 0
                self._current_anti_martingale_size = self.config.base_size_pct

        # Apply limits
        final_pct = self._apply_limits(self._current_anti_martingale_size)
        position_value = capital * final_pct
        quantity = position_value / price if price > 0 else 0

        return PositionSizeResult(
            method=AdvancedSizingMethod.ANTI_MARTINGALE,
            position_size_pct=final_pct,
            position_value=position_value,
            quantity=quantity,
            stop_distance=price * 0.02,
            risk_amount=position_value * 0.02,
            kelly_fraction=0,
            confidence_factor=1.0,
            reasoning=f"Pyramid Level={self._pyramid_level}, "
                     f"Consecutive Wins={self._consecutive_wins}, "
                     f"Size={final_pct:.2%}"
        )

    def calculate_risk_parity(
        self,
        capital: float,
        price: float,
        volatility: float,
        target_vol: float = 0.15,
        other_positions_vol: float = 0.0
    ) -> PositionSizeResult:
        """
        Calculate position size using Risk Parity

        Risk parity allocates capital inversely proportional to volatility,
        so each position contributes equally to portfolio risk.

        Args:
            capital: Available capital
            price: Current asset price
            volatility: Asset's annualized volatility
            target_vol: Target portfolio volatility
            other_positions_vol: Volatility contribution from existing positions

        Returns:
            PositionSizeResult with risk parity sizing
        """
        if volatility <= 0:
            volatility = 0.20  # Default 20% vol assumption

        # Available volatility budget
        available_vol = max(0, target_vol - other_positions_vol)

        # Weight based on inverse volatility
        inv_vol_weight = 1 / volatility

        # Scale to available volatility budget
        position_vol_contribution = available_vol * 0.5  # Max 50% of remaining budget
        position_pct = position_vol_contribution / volatility

        # Apply limits
        final_pct = self._apply_limits(position_pct)
        position_value = capital * final_pct
        quantity = position_value / price if price > 0 else 0

        return PositionSizeResult(
            method=AdvancedSizingMethod.RISK_PARITY,
            position_size_pct=final_pct,
            position_value=position_value,
            quantity=quantity,
            stop_distance=price * volatility / np.sqrt(252),  # Daily vol
            risk_amount=position_value * volatility / np.sqrt(252),
            kelly_fraction=0,
            confidence_factor=1.0,
            reasoning=f"Vol={volatility:.2%}, Target={target_vol:.2%}, "
                     f"Weight={final_pct:.2%}"
        )

    def calculate_fixed_fractional(
        self,
        capital: float,
        price: float,
        stop_loss_pct: float = 0.02
    ) -> PositionSizeResult:
        """
        Calculate position size using Fixed Fractional

        Simple method: Risk a fixed percentage of capital on each trade.

        Args:
            capital: Available capital
            price: Current asset price
            stop_loss_pct: Stop loss as percentage of entry

        Returns:
            PositionSizeResult with fixed fractional sizing
        """
        risk_pct = self.config.fixed_risk_pct
        risk_amount = capital * risk_pct

        # Calculate position size based on stop distance
        stop_distance = price * stop_loss_pct

        if stop_distance > 0:
            quantity = risk_amount / stop_distance
            position_value = quantity * price
            position_pct = position_value / capital if capital > 0 else 0
        else:
            quantity = 0
            position_value = 0
            position_pct = 0

        # Apply limits
        final_pct = self._apply_limits(position_pct)
        if final_pct != position_pct:
            position_value = capital * final_pct
            quantity = position_value / price if price > 0 else 0

        return PositionSizeResult(
            method=AdvancedSizingMethod.FIXED_FRACTIONAL,
            position_size_pct=final_pct,
            position_value=position_value,
            quantity=quantity,
            stop_distance=stop_distance,
            risk_amount=risk_amount,
            kelly_fraction=0,
            confidence_factor=1.0,
            reasoning=f"Fixed Risk={risk_pct:.2%}, Stop={stop_loss_pct:.2%}"
        )

    def get_recommended_size(
        self,
        capital: float,
        price: float,
        win_rate: float = 0.5,
        reward_risk: float = 2.0,
        atr_value: Optional[float] = None,
        volatility: Optional[float] = None,
        confidence: float = 1.0,
        last_trade_won: bool = True
    ) -> Dict[str, PositionSizeResult]:
        """
        Calculate position sizes using all methods and return recommendations

        Args:
            capital: Available capital
            price: Current asset price
            win_rate: Historical win rate
            reward_risk: Reward/Risk ratio
            atr_value: ATR value (optional)
            volatility: Asset volatility (optional)
            confidence: Signal confidence
            last_trade_won: Last trade result

        Returns:
            Dictionary of method -> PositionSizeResult
        """
        results = {}

        # Kelly-based
        results['kelly'] = self.calculate_kelly(
            win_rate, reward_risk, capital, price, confidence
        )

        # Fixed fractional
        results['fixed'] = self.calculate_fixed_fractional(
            capital, price
        )

        # ATR-based (if ATR available)
        if atr_value:
            results['atr'] = self.calculate_atr_based(
                capital, price, atr_value
            )

        # Risk parity (if volatility available)
        if volatility:
            results['risk_parity'] = self.calculate_risk_parity(
                capital, price, volatility
            )

        # Anti-martingale
        results['anti_martingale'] = self.calculate_anti_martingale(
            capital, price, last_trade_won
        )

        return results

    def record_trade(self, pnl_pct: float):
        """Record a trade result for Optimal F and Anti-Martingale"""
        self._trade_history.append(pnl_pct)

        if pnl_pct > 0:
            self._consecutive_wins += 1
            self._consecutive_losses = 0
        else:
            self._consecutive_losses += 1
            self._consecutive_wins = 0

    def _apply_limits(self, position_pct: float) -> float:
        """Apply position size limits"""
        return max(
            self.config.min_position_pct,
            min(self.config.max_position_pct, position_pct)
        )

    def get_status(self) -> Dict:
        """Get position sizer status"""
        return {
            "config": {
                "kelly_fraction": self.config.kelly_fraction,
                "atr_multiplier": self.config.atr_multiplier,
                "fixed_risk_pct": self.config.fixed_risk_pct,
                "max_position_pct": self.config.max_position_pct,
                "min_position_pct": self.config.min_position_pct
            },
            "state": {
                "trade_history_count": len(self._trade_history),
                "consecutive_wins": self._consecutive_wins,
                "consecutive_losses": self._consecutive_losses,
                "pyramid_level": self._pyramid_level,
                "current_anti_martingale_size": self._current_anti_martingale_size
            }
        }


# Global instance
_advanced_sizer: Optional[AdvancedPositionSizer] = None


def get_advanced_position_sizer(config: Optional[AdvancedSizingConfig] = None) -> AdvancedPositionSizer:
    """Get or create global advanced position sizer"""
    global _advanced_sizer
    if _advanced_sizer is None:
        _advanced_sizer = AdvancedPositionSizer(config)
    return _advanced_sizer
