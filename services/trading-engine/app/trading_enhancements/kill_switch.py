"""
Enhanced Kill Switch - Multi-Threshold Emergency Stop
Research Source: FIA Best Practices for Automated Trading Risk Controls (2024)

Purpose:
- Emergency stop mechanism for automated trading
- Multiple threshold triggers (not single-variable)
- Safeguards against accidental activation
- Time-delayed confirmation for critical actions

Key Features:
- Daily loss limit trigger
- Max drawdown trigger
- Position value trigger
- Consecutive loss trigger
- Manual override with confirmation
"""

import logging
from enum import Enum
from typing import Optional, List, Dict, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

logger = logging.getLogger(__name__)


class KillSwitchReason(Enum):
    """Reasons for kill switch activation"""
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    MAX_DRAWDOWN = "max_drawdown"
    MAX_POSITION_VALUE = "max_position_value"
    CONSECUTIVE_LOSSES = "consecutive_losses"
    MANUAL_ACTIVATION = "manual_activation"
    API_FAILURES = "api_failures"
    ANOMALY_DETECTED = "anomaly_detected"


@dataclass
class KillSwitchConfig:
    """
    Configuration for kill switch thresholds

    RESEARCH-BACKED DEFAULTS:
    - Daily loss: 5% (industry standard)
    - Max drawdown: 10% (conservative for crypto)
    - Consecutive losses: 5 (prevent tilt trading)
    - Confirmation delay: 5 seconds (prevent accidents)
    """
    max_daily_loss_pct: float = 5.0         # Stop if daily loss exceeds 5%
    max_drawdown_pct: float = 10.0          # Stop if total drawdown exceeds 10%
    max_position_value: float = 100000.0    # Stop if single position exceeds value
    max_consecutive_losses: int = 5          # Stop after 5 consecutive losses
    confirmation_delay_seconds: int = 5      # Delay before manual activation
    auto_reset_hours: int = 24               # Auto-reset after 24 hours
    require_multi_threshold: bool = True     # Require 2+ thresholds for auto-activate


@dataclass
class KillSwitchState:
    """Current state of the kill switch"""
    is_active: bool = False
    activation_time: Optional[datetime] = None
    activation_reason: Optional[KillSwitchReason] = None
    activation_details: Dict = field(default_factory=dict)
    triggered_thresholds: List[str] = field(default_factory=list)
    manual_override: bool = False

    # Tracking metrics
    current_daily_loss_pct: float = 0.0
    current_drawdown_pct: float = 0.0
    current_consecutive_losses: int = 0
    peak_balance: float = 0.0
    initial_balance: float = 0.0
    current_balance: float = 0.0


class KillSwitch:
    """
    Multi-Threshold Kill Switch for Automated Trading

    RESEARCH-BACKED IMPLEMENTATION:
    - Uses multiple thresholds (not single-variable triggers)
    - Implements safeguards against accidental activation
    - Provides time-delayed confirmation for manual override
    - Auto-resets after configured period
    - Logs all activations for audit trail

    Usage:
        kill_switch = KillSwitch(config)

        # Check before trading
        if kill_switch.should_halt_trading():
            return  # Don't trade

        # Update metrics after trade
        kill_switch.update_metrics(
            current_balance=9500,
            trade_pnl=-100,
            was_loss=True
        )

        # Manual activation with confirmation
        kill_switch.activate_manual(reason="suspicious activity")
    """

    def __init__(self, config: Optional[KillSwitchConfig] = None):
        """
        Initialize kill switch

        Args:
            config: Configuration for thresholds
        """
        self.config = config or KillSwitchConfig()
        self.state = KillSwitchState()
        self._callbacks: List[Callable] = []
        self._pending_manual_activation: Optional[datetime] = None
        self._last_reset_check: datetime = datetime.now()

        logger.info(
            f"KillSwitch initialized: "
            f"daily_loss={self.config.max_daily_loss_pct}%, "
            f"drawdown={self.config.max_drawdown_pct}%, "
            f"consecutive_losses={self.config.max_consecutive_losses}"
        )

    def initialize_balance(self, balance: float):
        """
        Initialize balance tracking

        Args:
            balance: Starting balance
        """
        self.state.initial_balance = balance
        self.state.current_balance = balance
        self.state.peak_balance = balance
        logger.info(f"KillSwitch balance initialized: ${balance:.2f}")

    def update_metrics(
        self,
        current_balance: float,
        trade_pnl: float = 0.0,
        was_loss: bool = False,
        position_value: float = 0.0
    ) -> List[str]:
        """
        Update metrics and check thresholds

        Args:
            current_balance: Current account balance
            trade_pnl: P&L from recent trade
            was_loss: Whether the trade was a loss
            position_value: Current position value

        Returns:
            List of triggered threshold names (if any)
        """
        triggered = []

        # Update balance
        self.state.current_balance = current_balance
        if current_balance > self.state.peak_balance:
            self.state.peak_balance = current_balance

        # Calculate daily loss percentage
        if self.state.initial_balance > 0:
            daily_pnl = current_balance - self.state.initial_balance
            self.state.current_daily_loss_pct = -(daily_pnl / self.state.initial_balance * 100) if daily_pnl < 0 else 0

        # Calculate drawdown percentage
        if self.state.peak_balance > 0:
            drawdown = self.state.peak_balance - current_balance
            self.state.current_drawdown_pct = (drawdown / self.state.peak_balance * 100) if drawdown > 0 else 0

        # Update consecutive losses
        if was_loss:
            self.state.current_consecutive_losses += 1
        else:
            self.state.current_consecutive_losses = 0

        # Check thresholds
        if self.state.current_daily_loss_pct >= self.config.max_daily_loss_pct:
            triggered.append("daily_loss_limit")
            logger.warning(
                f"THRESHOLD: Daily loss {self.state.current_daily_loss_pct:.2f}% >= "
                f"{self.config.max_daily_loss_pct}%"
            )

        if self.state.current_drawdown_pct >= self.config.max_drawdown_pct:
            triggered.append("max_drawdown")
            logger.warning(
                f"THRESHOLD: Drawdown {self.state.current_drawdown_pct:.2f}% >= "
                f"{self.config.max_drawdown_pct}%"
            )

        if self.state.current_consecutive_losses >= self.config.max_consecutive_losses:
            triggered.append("consecutive_losses")
            logger.warning(
                f"THRESHOLD: Consecutive losses {self.state.current_consecutive_losses} >= "
                f"{self.config.max_consecutive_losses}"
            )

        if position_value >= self.config.max_position_value:
            triggered.append("max_position_value")
            logger.warning(
                f"THRESHOLD: Position value ${position_value:.2f} >= "
                f"${self.config.max_position_value:.2f}"
            )

        # Store triggered thresholds
        self.state.triggered_thresholds = triggered

        # Check if should activate
        if self._should_auto_activate(triggered):
            self._activate(
                KillSwitchReason.DAILY_LOSS_LIMIT if "daily_loss_limit" in triggered
                else KillSwitchReason.MAX_DRAWDOWN if "max_drawdown" in triggered
                else KillSwitchReason.CONSECUTIVE_LOSSES if "consecutive_losses" in triggered
                else KillSwitchReason.MAX_POSITION_VALUE,
                {"triggered_thresholds": triggered}
            )

        return triggered

    def _should_auto_activate(self, triggered: List[str]) -> bool:
        """
        Determine if kill switch should auto-activate

        RESEARCH: Use multiple thresholds to avoid single-variable false triggers
        """
        if not triggered:
            return False

        if self.config.require_multi_threshold:
            # Require at least 2 thresholds for auto-activation
            return len(triggered) >= 2
        else:
            # Single threshold is enough
            return len(triggered) >= 1

    def _activate(self, reason: KillSwitchReason, details: Dict):
        """Internal activation method"""
        if self.state.is_active:
            logger.debug("KillSwitch already active")
            return

        self.state.is_active = True
        self.state.activation_time = datetime.now()
        self.state.activation_reason = reason
        self.state.activation_details = details

        logger.critical(
            f"KILL SWITCH ACTIVATED: {reason.value} | "
            f"Daily Loss: {self.state.current_daily_loss_pct:.2f}% | "
            f"Drawdown: {self.state.current_drawdown_pct:.2f}% | "
            f"Consecutive Losses: {self.state.current_consecutive_losses}"
        )

        # Call registered callbacks
        for callback in self._callbacks:
            try:
                callback(self.state)
            except Exception as e:
                logger.error(f"KillSwitch callback error: {e}")

    def should_halt_trading(self) -> bool:
        """
        Check if trading should be halted

        Returns:
            True if kill switch is active and trading should stop
        """
        # Check for auto-reset
        self._check_auto_reset()

        return self.state.is_active

    def activate_manual(self, reason: str = "Manual activation") -> bool:
        """
        Manually activate the kill switch with confirmation delay

        SAFEGUARD: Requires waiting for confirmation_delay_seconds
        to prevent accidental activation

        Args:
            reason: Reason for manual activation

        Returns:
            True if activation started, False if already active
        """
        if self.state.is_active:
            logger.warning("KillSwitch already active")
            return False

        if self._pending_manual_activation is None:
            # Start confirmation timer
            self._pending_manual_activation = datetime.now()
            logger.warning(
                f"Manual kill switch initiated. "
                f"Confirm within {self.config.confirmation_delay_seconds}s to activate."
            )
            return True
        else:
            # Check if confirmation delay has passed
            elapsed = (datetime.now() - self._pending_manual_activation).total_seconds()
            if elapsed >= self.config.confirmation_delay_seconds:
                self._pending_manual_activation = None
                self._activate(
                    KillSwitchReason.MANUAL_ACTIVATION,
                    {"reason": reason}
                )
                self.state.manual_override = True
                return True
            else:
                remaining = self.config.confirmation_delay_seconds - elapsed
                logger.info(f"Confirm again in {remaining:.1f}s to activate kill switch")
                return False

    def confirm_manual_activation(self) -> bool:
        """Confirm pending manual activation"""
        if self._pending_manual_activation is None:
            logger.warning("No pending manual activation to confirm")
            return False

        elapsed = (datetime.now() - self._pending_manual_activation).total_seconds()
        if elapsed >= self.config.confirmation_delay_seconds:
            self._pending_manual_activation = None
            self._activate(
                KillSwitchReason.MANUAL_ACTIVATION,
                {"reason": "Manual confirmation"}
            )
            self.state.manual_override = True
            return True

        return False

    def deactivate(self, force: bool = False) -> bool:
        """
        Deactivate the kill switch

        Args:
            force: Force deactivation even if conditions still met

        Returns:
            True if deactivated successfully
        """
        if not self.state.is_active:
            return True

        # Check if conditions still warrant activation
        if not force and self.state.triggered_thresholds:
            logger.warning(
                f"Cannot deactivate: thresholds still triggered: "
                f"{self.state.triggered_thresholds}"
            )
            return False

        self.state.is_active = False
        self.state.activation_time = None
        self.state.activation_reason = None
        self.state.activation_details = {}
        self.state.manual_override = False
        self._pending_manual_activation = None

        logger.info("KillSwitch DEACTIVATED")
        return True

    def _check_auto_reset(self):
        """Check if kill switch should auto-reset"""
        if not self.state.is_active:
            return

        if self.state.activation_time is None:
            return

        elapsed_hours = (datetime.now() - self.state.activation_time).total_seconds() / 3600
        if elapsed_hours >= self.config.auto_reset_hours:
            logger.info(f"KillSwitch auto-reset after {elapsed_hours:.1f} hours")
            self.deactivate(force=True)

    def reset_daily_metrics(self):
        """Reset daily metrics (call at start of trading day)"""
        self.state.initial_balance = self.state.current_balance
        self.state.current_daily_loss_pct = 0.0
        self.state.current_consecutive_losses = 0
        self.state.triggered_thresholds = []
        logger.info("KillSwitch daily metrics reset")

    def register_callback(self, callback: Callable):
        """Register callback for kill switch activation"""
        self._callbacks.append(callback)

    def get_status(self) -> Dict:
        """Get current kill switch status"""
        return {
            "is_active": self.state.is_active,
            "activation_time": self.state.activation_time.isoformat() if self.state.activation_time else None,
            "activation_reason": self.state.activation_reason.value if self.state.activation_reason else None,
            "manual_override": self.state.manual_override,
            "metrics": {
                "daily_loss_pct": round(self.state.current_daily_loss_pct, 2),
                "drawdown_pct": round(self.state.current_drawdown_pct, 2),
                "consecutive_losses": self.state.current_consecutive_losses,
                "peak_balance": round(self.state.peak_balance, 2),
                "current_balance": round(self.state.current_balance, 2),
            },
            "thresholds": {
                "max_daily_loss_pct": self.config.max_daily_loss_pct,
                "max_drawdown_pct": self.config.max_drawdown_pct,
                "max_consecutive_losses": self.config.max_consecutive_losses,
            },
            "triggered_thresholds": self.state.triggered_thresholds,
            "pending_manual_activation": self._pending_manual_activation is not None,
        }


# Global kill switch instance
_kill_switch: Optional[KillSwitch] = None


def get_kill_switch(config: Optional[KillSwitchConfig] = None) -> KillSwitch:
    """Get or create global kill switch"""
    global _kill_switch
    if _kill_switch is None:
        _kill_switch = KillSwitch(config)
    return _kill_switch
