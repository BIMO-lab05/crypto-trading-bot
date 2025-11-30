"""
ATR-Based Stop Loss and Take Profit Calculator
Purpose: Dynamic stop loss and take profit levels based on market volatility
"""

import logging
from typing import Dict, Optional, Tuple
from decimal import Decimal
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk level classifications"""
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


@dataclass
class StopLevels:
    """Stop loss and take profit levels"""
    entry_price: Decimal
    stop_loss: Decimal
    take_profit_1: Decimal  # First target (1:1 R:R)
    take_profit_2: Decimal  # Second target (2:1 R:R)
    take_profit_3: Decimal  # Third target (3:1 R:R)
    trailing_stop: Decimal
    atr_value: float
    risk_amount: Decimal
    position_side: str  # "LONG" or "SHORT"

    def to_dict(self) -> Dict:
        return {
            "entry_price": float(self.entry_price),
            "stop_loss": float(self.stop_loss),
            "take_profit_1": float(self.take_profit_1),
            "take_profit_2": float(self.take_profit_2),
            "take_profit_3": float(self.take_profit_3),
            "trailing_stop": float(self.trailing_stop),
            "atr_value": self.atr_value,
            "risk_amount": float(self.risk_amount),
            "position_side": self.position_side,
            "risk_reward_ratios": {
                "tp1": 1.0,
                "tp2": 2.0,
                "tp3": 3.0
            }
        }


class ATRStopCalculator:
    """
    Calculate dynamic stop loss and take profit levels using ATR

    ATR (Average True Range) measures market volatility.
    Using ATR for stops ensures they adapt to current market conditions:
    - High volatility -> Wider stops to avoid noise
    - Low volatility -> Tighter stops for better risk control

    Default ATR Multipliers by Risk Level:
    - Conservative: 2.5x ATR stop, targets at 2.5x, 5x, 7.5x ATR
    - Moderate: 2.0x ATR stop, targets at 2x, 4x, 6x ATR
    - Aggressive: 1.5x ATR stop, targets at 1.5x, 3x, 4.5x ATR
    """

    # ATR multipliers for different risk levels
    RISK_MULTIPLIERS = {
        RiskLevel.CONSERVATIVE: {
            "stop": 2.5,
            "tp1": 2.5,
            "tp2": 5.0,
            "tp3": 7.5,
            "trailing": 2.0
        },
        RiskLevel.MODERATE: {
            "stop": 2.0,
            "tp1": 2.0,
            "tp2": 4.0,
            "tp3": 6.0,
            "trailing": 1.5
        },
        RiskLevel.AGGRESSIVE: {
            "stop": 1.5,
            "tp1": 1.5,
            "tp2": 3.0,
            "tp3": 4.5,
            "trailing": 1.0
        }
    }

    def __init__(
        self,
        risk_level: RiskLevel = RiskLevel.MODERATE,
        atr_period: int = 14,
        custom_multipliers: Optional[Dict[str, float]] = None
    ):
        """
        Initialize ATR stop calculator

        Args:
            risk_level: Risk tolerance level
            atr_period: Period for ATR calculation (default: 14)
            custom_multipliers: Optional custom multipliers override
        """
        self.risk_level = risk_level
        self.atr_period = atr_period

        # Use custom multipliers if provided, otherwise use defaults
        if custom_multipliers:
            self.multipliers = custom_multipliers
        else:
            self.multipliers = self.RISK_MULTIPLIERS[risk_level]

        logger.info(
            f"ATRStopCalculator initialized: "
            f"risk_level={risk_level.value}, "
            f"atr_period={atr_period}, "
            f"stop_mult={self.multipliers['stop']}x"
        )

    def calculate_atr(self, highs: list, lows: list, closes: list) -> float:
        """
        Calculate Average True Range (ATR)

        ATR = Average of True Range over N periods
        True Range = max(high-low, |high-prev_close|, |low-prev_close|)

        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of close prices

        Returns:
            ATR value
        """
        if len(highs) < self.atr_period + 1:
            logger.warning(f"Insufficient data for ATR: {len(highs)} < {self.atr_period + 1}")
            return 0.0

        true_ranges = []

        for i in range(1, len(highs)):
            high = highs[i]
            low = lows[i]
            prev_close = closes[i - 1]

            # True Range calculation
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)

        # Calculate ATR as simple moving average of true ranges
        if len(true_ranges) >= self.atr_period:
            atr = sum(true_ranges[-self.atr_period:]) / self.atr_period
        else:
            atr = sum(true_ranges) / len(true_ranges)

        return atr

    def calculate_stops(
        self,
        entry_price: float,
        atr_value: float,
        side: str,  # "LONG" or "SHORT"
        custom_stop_mult: Optional[float] = None,
        custom_tp_mult: Optional[float] = None
    ) -> StopLevels:
        """
        Calculate stop loss and take profit levels

        Args:
            entry_price: Entry price for the position
            atr_value: Current ATR value
            side: Position side ("LONG" or "SHORT")
            custom_stop_mult: Optional custom stop loss multiplier
            custom_tp_mult: Optional custom take profit multiplier

        Returns:
            StopLevels with all calculated levels
        """
        entry = Decimal(str(entry_price))
        atr = Decimal(str(atr_value))

        # Get multipliers
        stop_mult = Decimal(str(custom_stop_mult or self.multipliers["stop"]))
        tp1_mult = Decimal(str(custom_tp_mult or self.multipliers["tp1"]))
        tp2_mult = Decimal(str(self.multipliers["tp2"]))
        tp3_mult = Decimal(str(self.multipliers["tp3"]))
        trail_mult = Decimal(str(self.multipliers["trailing"]))

        # Calculate risk amount (distance to stop)
        risk_amount = atr * stop_mult

        if side.upper() == "LONG":
            # LONG position: Stop below entry, targets above
            stop_loss = entry - risk_amount
            take_profit_1 = entry + (atr * tp1_mult)
            take_profit_2 = entry + (atr * tp2_mult)
            take_profit_3 = entry + (atr * tp3_mult)
            trailing_stop = entry - (atr * trail_mult)
        else:
            # SHORT position: Stop above entry, targets below
            stop_loss = entry + risk_amount
            take_profit_1 = entry - (atr * tp1_mult)
            take_profit_2 = entry - (atr * tp2_mult)
            take_profit_3 = entry - (atr * tp3_mult)
            trailing_stop = entry + (atr * trail_mult)

        levels = StopLevels(
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            take_profit_3=take_profit_3,
            trailing_stop=trailing_stop,
            atr_value=atr_value,
            risk_amount=risk_amount,
            position_side=side.upper()
        )

        logger.info(
            f"Stop levels calculated for {side}: "
            f"entry={entry:.2f}, SL={stop_loss:.2f}, "
            f"TP1={take_profit_1:.2f}, TP2={take_profit_2:.2f}, TP3={take_profit_3:.2f}"
        )

        return levels

    def calculate_stops_from_data(
        self,
        entry_price: float,
        highs: list,
        lows: list,
        closes: list,
        side: str
    ) -> StopLevels:
        """
        Calculate stops directly from price data

        Args:
            entry_price: Entry price for position
            highs: List of high prices
            lows: List of low prices
            closes: List of close prices
            side: Position side ("LONG" or "SHORT")

        Returns:
            StopLevels with calculated levels
        """
        atr = self.calculate_atr(highs, lows, closes)
        return self.calculate_stops(entry_price, atr, side)

    def update_trailing_stop(
        self,
        current_price: float,
        current_trailing_stop: float,
        atr_value: float,
        side: str
    ) -> Tuple[float, bool]:
        """
        Update trailing stop based on price movement

        Args:
            current_price: Current market price
            current_trailing_stop: Current trailing stop level
            atr_value: Current ATR value
            side: Position side

        Returns:
            Tuple of (new_trailing_stop, was_updated)
        """
        trail_distance = atr_value * self.multipliers["trailing"]

        if side.upper() == "LONG":
            # For LONG: trail up (increase stop as price rises)
            new_stop = current_price - trail_distance
            if new_stop > current_trailing_stop:
                logger.info(
                    f"Trailing stop updated (LONG): "
                    f"{current_trailing_stop:.2f} -> {new_stop:.2f}"
                )
                return new_stop, True
        else:
            # For SHORT: trail down (decrease stop as price falls)
            new_stop = current_price + trail_distance
            if new_stop < current_trailing_stop:
                logger.info(
                    f"Trailing stop updated (SHORT): "
                    f"{current_trailing_stop:.2f} -> {new_stop:.2f}"
                )
                return new_stop, True

        return current_trailing_stop, False

    def check_stop_triggered(
        self,
        current_price: float,
        stop_loss: float,
        take_profits: list,
        side: str
    ) -> Dict[str, bool]:
        """
        Check if any stops have been triggered

        Args:
            current_price: Current market price
            stop_loss: Stop loss level
            take_profits: List of take profit levels [TP1, TP2, TP3]
            side: Position side

        Returns:
            Dict with triggered status for each level
        """
        result = {
            "stop_loss": False,
            "tp1": False,
            "tp2": False,
            "tp3": False
        }

        if side.upper() == "LONG":
            result["stop_loss"] = current_price <= stop_loss
            result["tp1"] = current_price >= take_profits[0] if len(take_profits) > 0 else False
            result["tp2"] = current_price >= take_profits[1] if len(take_profits) > 1 else False
            result["tp3"] = current_price >= take_profits[2] if len(take_profits) > 2 else False
        else:
            result["stop_loss"] = current_price >= stop_loss
            result["tp1"] = current_price <= take_profits[0] if len(take_profits) > 0 else False
            result["tp2"] = current_price <= take_profits[1] if len(take_profits) > 1 else False
            result["tp3"] = current_price <= take_profits[2] if len(take_profits) > 2 else False

        return result


# Global instance
_atr_calculator: Optional[ATRStopCalculator] = None


def get_atr_calculator(risk_level: RiskLevel = RiskLevel.MODERATE) -> ATRStopCalculator:
    """Get or create global ATR calculator instance"""
    global _atr_calculator
    if _atr_calculator is None:
        _atr_calculator = ATRStopCalculator(risk_level=risk_level)
    return _atr_calculator


def calculate_smart_stops(
    entry_price: float,
    atr_value: float,
    side: str,
    risk_level: RiskLevel = RiskLevel.MODERATE
) -> Dict:
    """
    Convenience function to calculate smart stops

    Args:
        entry_price: Entry price for position
        atr_value: Current ATR value
        side: Position side ("LONG" or "SHORT")
        risk_level: Risk tolerance level

    Returns:
        Dict with all stop levels
    """
    calculator = get_atr_calculator(risk_level)
    levels = calculator.calculate_stops(entry_price, atr_value, side)
    return levels.to_dict()
