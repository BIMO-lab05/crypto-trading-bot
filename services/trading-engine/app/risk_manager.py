"""
Risk Manager
Purpose: Enforce risk management rules and position sizing
"""

import logging
from decimal import Decimal
from typing import Optional, Tuple
from app.config import get_settings
from app.models import Position, PositionSide, SignalAction

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Manages risk and position sizing

    Key responsibilities:
    1. Calculate safe position sizes
    2. Enforce maximum position limits
    3. Enforce maximum daily loss limits
    4. Calculate stop-loss and take-profit prices
    5. Monitor total exposure
    """

    def __init__(self):
        """Initialize risk manager"""
        self.settings = get_settings()
        self.daily_pnl = Decimal("0")  # Track daily P&L
        self.trading_halted = False
        logger.info("RiskManager initialized")
        logger.info(f"  Max position size: {self.settings.max_position_size_pct}%")
        logger.info(f"  Max daily loss: {self.settings.max_daily_loss_pct}%")
        logger.info(f"  Default stop loss: {self.settings.default_stop_loss_pct}%")
        logger.info(f"  Default take profit: {self.settings.default_take_profit_pct}%")

    def reset_daily_pnl(self):
        """Reset daily P&L (call at start of each trading day)"""
        logger.info(f"Resetting daily P&L (was: {self.daily_pnl})")
        self.daily_pnl = Decimal("0")
        self.trading_halted = False

    def update_daily_pnl(self, pnl: Decimal):
        """Update daily P&L"""
        self.daily_pnl += pnl
        logger.info(f"Daily P&L updated: {self.daily_pnl}")

        # Check if daily loss limit exceeded
        if self.should_halt_trading():
            self.halt_trading()

    def should_halt_trading(self) -> bool:
        """Check if trading should be halted"""
        if self.trading_halted:
            return True

        # Check daily loss limit
        max_loss = Decimal(str(self.settings.paper_initial_balance)) * Decimal(str(self.settings.max_daily_loss_pct / 100))
        if self.daily_pnl < -max_loss:
            return True

        return False

    def halt_trading(self):
        """Halt all trading"""
        if not self.trading_halted:
            logger.critical(f"🛑 TRADING HALTED! Daily loss limit exceeded: {self.daily_pnl}")
            self.trading_halted = True

    def resume_trading(self):
        """Resume trading (manual override)"""
        logger.warning("Trading resumed manually")
        self.trading_halted = False

    def calculate_position_size(
        self,
        account_balance: Decimal,
        entry_price: Decimal,
        stop_loss_price: Optional[Decimal] = None
    ) -> Decimal:
        """
        Calculate safe position size

        Uses:
        1. Maximum position size percentage of capital
        2. Risk-based sizing if stop-loss is provided

        Args:
            account_balance: Current account balance
            entry_price: Entry price for the position
            stop_loss_price: Optional stop loss price

        Returns:
            Safe position size in units
        """
        if account_balance <= 0 or entry_price <= 0:
            logger.warning("Invalid account balance or entry price")
            return Decimal("0")

        # Maximum position value based on percentage
        max_position_value = account_balance * Decimal(str(self.settings.max_position_size_pct / 100))

        # Calculate quantity
        quantity = max_position_value / entry_price

        # If stop-loss provided, use risk-based sizing
        if stop_loss_price and stop_loss_price > 0:
            risk_per_unit = abs(entry_price - stop_loss_price)
            if risk_per_unit > 0:
                max_risk = account_balance * Decimal(str(self.settings.max_position_size_pct / 100))
                risk_based_quantity = max_risk / risk_per_unit

                # Use the smaller quantity (more conservative)
                quantity = min(quantity, risk_based_quantity)

        logger.info(f"Position size calculated: {quantity} units (value: {quantity * entry_price})")
        return quantity

    def calculate_stop_loss(
        self,
        entry_price: Decimal,
        side: PositionSide,
        stop_loss_pct: Optional[float] = None
    ) -> Decimal:
        """
        Calculate stop-loss price

        Args:
            entry_price: Entry price
            side: Position side (LONG/SHORT)
            stop_loss_pct: Stop loss percentage (default from config)

        Returns:
            Stop loss price
        """
        if stop_loss_pct is None:
            stop_loss_pct = self.settings.default_stop_loss_pct

        stop_loss_factor = Decimal(str(stop_loss_pct / 100))

        if side == PositionSide.LONG:
            # For LONG: stop loss below entry
            stop_loss = entry_price * (Decimal("1") - stop_loss_factor)
        else:  # SHORT
            # For SHORT: stop loss above entry
            stop_loss = entry_price * (Decimal("1") + stop_loss_factor)

        logger.debug(f"Stop loss calculated: {stop_loss} ({stop_loss_pct}% from {entry_price})")
        return stop_loss

    def calculate_take_profit(
        self,
        entry_price: Decimal,
        side: PositionSide,
        take_profit_pct: Optional[float] = None
    ) -> Decimal:
        """
        Calculate take-profit price

        Args:
            entry_price: Entry price
            side: Position side (LONG/SHORT)
            take_profit_pct: Take profit percentage (default from config)

        Returns:
            Take profit price
        """
        if take_profit_pct is None:
            take_profit_pct = self.settings.default_take_profit_pct

        take_profit_factor = Decimal(str(take_profit_pct / 100))

        if side == PositionSide.LONG:
            # For LONG: take profit above entry
            take_profit = entry_price * (Decimal("1") + take_profit_factor)
        else:  # SHORT
            # For SHORT: take profit below entry
            take_profit = entry_price * (Decimal("1") - take_profit_factor)

        logger.debug(f"Take profit calculated: {take_profit} ({take_profit_pct}% from {entry_price})")
        return take_profit

    def check_position_limits(
        self,
        current_positions: list[Position],
        account_balance: Decimal
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if opening new position would exceed limits

        Args:
            current_positions: List of open positions
            account_balance: Current account balance

        Returns:
            Tuple of (allowed, reason if not allowed)
        """
        # Calculate current exposure
        total_exposure = sum(
            pos.entry_price * pos.quantity
            for pos in current_positions
            if pos.status.value == "OPEN"
        )

        exposure_pct = (total_exposure / account_balance * 100) if account_balance > 0 else 0

        # Check max exposure
        if exposure_pct >= self.settings.max_total_exposure_pct:
            reason = f"Total exposure ({exposure_pct:.1f}%) exceeds limit ({self.settings.max_total_exposure_pct}%)"
            logger.warning(f"Position limit check failed: {reason}")
            return False, reason

        # Check daily loss limit
        if self.should_halt_trading():
            reason = "Trading halted due to daily loss limit"
            logger.warning(f"Position limit check failed: {reason}")
            return False, reason

        return True, None

    def should_close_position(
        self,
        position: Position,
        current_price: Decimal
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if position should be closed

        Args:
            position: Position to check
            current_price: Current market price

        Returns:
            Tuple of (should_close, reason)
        """
        # Update position P&L
        position.update_pnl(current_price)

        # Check stop loss
        if position.check_stop_loss(current_price):
            reason = f"Stop loss hit at {current_price} (SL: {position.stop_loss})"
            logger.info(f"Position {position.id} should be closed: {reason}")
            return True, reason

        # Check take profit
        if position.check_take_profit(current_price):
            reason = f"Take profit hit at {current_price} (TP: {position.take_profit})"
            logger.info(f"Position {position.id} should be closed: {reason}")
            return True, reason

        return False, None

    def validate_signal(
        self,
        signal_action: SignalAction,
        signal_confidence: float
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate if signal meets trading criteria

        Args:
            signal_action: Signal action (BUY/SELL/HOLD)
            signal_confidence: Signal confidence (0-1)

        Returns:
            Tuple of (is_valid, reason if not valid)
        """
        # Check if trading is halted
        if self.should_halt_trading():
            return False, "Trading halted"

        # Check signal action
        if signal_action not in [SignalAction.BUY, SignalAction.SELL]:
            return False, f"Signal action is {signal_action.value}, not BUY/SELL"

        # Check confidence threshold
        if signal_confidence < self.settings.min_signal_confidence:
            return False, f"Signal confidence ({signal_confidence:.2f}) below threshold ({self.settings.min_signal_confidence})"

        return True, None


# Global risk manager instance
_risk_manager: Optional[RiskManager] = None


def get_risk_manager() -> RiskManager:
    """Get or create risk manager instance"""
    global _risk_manager
    if _risk_manager is None:
        _risk_manager = RiskManager()
    return _risk_manager
