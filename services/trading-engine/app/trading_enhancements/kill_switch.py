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
from datetime import datetime, date, timezone  # noqa: F401  (timezone used in daily roll)

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


# ---------------------------------------------------------------------------
# Derived defaults
# ---------------------------------------------------------------------------
# Mirrors `app.config.Settings` Field defaults. Used ONLY when `get_settings()`
# cannot be constructed (e.g. a host-run test session where `.env` is parsed by
# a different pydantic-settings version than the container pins). Keeping the
# fallback equal to the stock configuration means a settings failure degrades to
# the correct threshold rather than silently restoring the inert one.
_FALLBACK_PAPER_BALANCE_USD = 10000.0  # config.py paper_initial_balance (ADR-029)
_FALLBACK_TOTAL_EXPOSURE_PCT = 80.0  # config.py max_total_exposure_pct


def _default_max_position_value() -> float:
    """Per-position runaway tripwire, derived from account equity.

    FIX 2026-08-03 (capital audit). This was a flat `100000.0`, and
    `auto_trader.py` only ever overrode `max_daily_loss_pct`, so on the then
    $100 account no position could ever reach the threshold and this arm of the
    kill switch was PERMANENTLY DEAD.

    Derivation — `equity x max_total_exposure_pct`, i.e. $8,000 on the $10,000
    account (ADR-029):

      * NOT `equity x max_position_size_pct` ($1,000). `position_value` here is
        a SINGLE position's notional at open (`auto_trader.py:2102`), already
        clamped to `balance x max_risk_per_trade` = $1,000 by the per-trade cap
        gate. A $1,000 threshold would therefore trip on EVERY normal max-size
        trade and silently halt the bot.
      * The total-exposure ceiling is the right shape: a *single* position may
        never legitimately consume the account's entire exposure budget, so
        $8,000 is definitionally a runaway, while sitting 8x above a normal
        $1,000 trade.

    Resolved lazily at dataclass instantiation via `default_factory`, never at
    module import, so importing this module does not pull in settings.
    """
    try:
        from app.config import get_settings

        settings = get_settings()
        equity_usd = float(settings.paper_initial_balance)
        exposure_pct = float(settings.max_total_exposure_pct)
    except Exception as exc:  # settings must never make the kill switch unbuildable
        logger.error(
            "KillSwitch: could not read Settings for max_position_value (%s). "
            "Falling back to the declared defaults "
            "($%.2f x %.1f%%). Verify the service configuration.",
            exc,
            _FALLBACK_PAPER_BALANCE_USD,
            _FALLBACK_TOTAL_EXPOSURE_PCT,
        )
        equity_usd = _FALLBACK_PAPER_BALANCE_USD
        exposure_pct = _FALLBACK_TOTAL_EXPOSURE_PCT

    return equity_usd * (exposure_pct / 100.0)


@dataclass
class KillSwitchConfig:
    """
    Configuration for kill switch thresholds

    RESEARCH-BACKED DEFAULTS (2025-12-02):
    Based on: 3Commas, Bitsgap, Cryptohopper best practices

    Tiered Drawdown System:
    - 5%: Alert and review (reduce position sizes by 25%)
    - 10%: Reduce position sizes by 50%
    - 15%: Pause new trades, close underperformers
    - 20%: Full stop, require manual review

    - Daily loss: 5% (research standard)
    - Max drawdown: 15% (aggressive protection)
    - Consecutive losses: 5 (max 9 seen in history - stop at 5)
    """

    # Tiered thresholds (2025-12-02 research-backed)
    drawdown_alert_pct: float = 5.0  # Alert level - reduce size 25%
    drawdown_reduce_pct: float = 10.0  # Reduce position sizes by 50%
    drawdown_pause_pct: float = 15.0  # Pause new trades
    # ADR-028 (2026-08-03): was 5.0. At the ADR-010 per-trade cap of 10% ($10 on
    # a $100 balance) a 5% daily limit ($5) tripped on the FIRST full loss, so it
    # measured one trade rather than a day. Kept in sync with
    # `Settings.max_daily_loss_pct`, which `auto_trader.py:343` passes in — this
    # default only applies to bare `KillSwitchConfig()` construction.
    max_daily_loss_pct: float = 12.0  # Stop if daily loss exceeds 12%
    max_drawdown_pct: float = 20.0  # Hard stop at 20%
    # Stop if a SINGLE position's notional exceeds this. Derived from account
    # equity ($80 on the $100 account) — see `_default_max_position_value()`.
    # The default_factory is required, not cosmetic: `KillSwitch.__init__` does
    # `config or KillSwitchConfig()` and two test modules construct
    # `KillSwitchConfig()` with no arguments, so a fix applied only at the
    # `auto_trader.py` call site would leave those paths inert.
    max_position_value: float = field(default_factory=_default_max_position_value)
    max_consecutive_losses: int = 5  # Stop after 5 consecutive losses
    confirmation_delay_seconds: int = 5  # Delay before manual activation
    auto_reset_hours: int = 24  # Auto-reset after 24 hours (require review)
    require_multi_threshold: bool = False  # Single threshold can trigger (safer)


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

    # UTC date the current daily window belongs to. Without this,
    # `initial_balance` was set once at boot and never rolled, so
    # `current_daily_loss_pct` measured cumulative loss since process start
    # rather than loss within a day -- turning the 5% daily breaker into an
    # all-time breaker that halted the bot permanently. See the roll in
    # `_roll_daily_window_if_needed`.
    daily_window_date: Optional[date] = None


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
        # Anchor the daily window to the boot date, so the first roll happens
        # at the next UTC midnight rather than on the first update_metrics call.
        self.state.daily_window_date = datetime.now(timezone.utc).date()
        logger.info(f"KillSwitch balance initialized: ${balance:.2f}")

    def update_metrics(
        self,
        current_balance: float,
        trade_pnl: float = 0.0,
        was_loss: bool = False,
        position_value: float = 0.0,
        is_trade_close: bool = False,
    ) -> List[str]:
        """
        Update metrics and check thresholds

        FIX 2026-07-28:
        - `current_balance` should be EQUITY (cash + unrealized P&L). Feeding
          raw cash made opening a position (margin deduction) look like an
          instant "daily loss" >= the 5% threshold, false-triggering the switch.
        - Consecutive-loss streak only updates on trade CLOSES
          (`is_trade_close=True`). Previously every position OPEN (called with
          was_loss=False) reset the streak, so the 5-consecutive-losses
          breaker was structurally unreachable while the bot kept re-entering.

        Args:
            current_balance: Current account EQUITY (cash + unrealized P&L)
            trade_pnl: P&L from recent trade
            was_loss: Whether the trade was a loss
            position_value: Current position value
            is_trade_close: True when called after a position close (streak
                accounting only happens on closes)

        Returns:
            List of triggered threshold names (if any)
        """
        triggered = []

        # Roll the daily window BEFORE any threshold maths, so a new UTC day
        # is measured from that day's opening equity.
        self._roll_daily_window_if_needed(current_balance)

        # Update balance
        self.state.current_balance = current_balance
        if current_balance > self.state.peak_balance:
            self.state.peak_balance = current_balance

        # Calculate daily loss percentage
        if self.state.initial_balance > 0:
            daily_pnl = current_balance - self.state.initial_balance
            self.state.current_daily_loss_pct = (
                -(daily_pnl / self.state.initial_balance * 100) if daily_pnl < 0 else 0
            )

        # Calculate drawdown percentage
        if self.state.peak_balance > 0:
            drawdown = self.state.peak_balance - current_balance
            self.state.current_drawdown_pct = (
                (drawdown / self.state.peak_balance * 100) if drawdown > 0 else 0
            )

        # Update consecutive losses — ONLY on trade closes
        if is_trade_close:
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
                KillSwitchReason.DAILY_LOSS_LIMIT
                if "daily_loss_limit" in triggered
                else KillSwitchReason.MAX_DRAWDOWN
                if "max_drawdown" in triggered
                else KillSwitchReason.CONSECUTIVE_LOSSES
                if "consecutive_losses" in triggered
                else KillSwitchReason.MAX_POSITION_VALUE,
                {"triggered_thresholds": triggered},
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
                self._activate(KillSwitchReason.MANUAL_ACTIVATION, {"reason": reason})
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
            self._activate(KillSwitchReason.MANUAL_ACTIVATION, {"reason": "Manual confirmation"})
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
                f"Cannot deactivate: thresholds still triggered: {self.state.triggered_thresholds}"
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

    def _roll_daily_window_if_needed(self, current_balance: float) -> None:
        """
        Start a new daily window when the UTC date changes.

        FIX 2026-08-01. `initial_balance` was set once by `initialize_balance()`
        at boot and never rolled, so `current_daily_loss_pct` was really
        *cumulative loss since process start*. `AutoTrader.reset_daily_metrics()`
        existed to fix that and had zero callers -- nothing scheduled it. The
        result: the 5% DAILY breaker behaved as an all-time 5% breaker, and once
        crossed the bot halted permanently with no path back.

        Observed live before this fix: daily_loss_pct 8.42% against a
        peak_balance of 83.48 -- itself a figure fabricated by the restart
        rebase bug (audit DL-2) -- with trading halted and unable to recover.
        The tell was daily_loss_pct and drawdown_pct being exactly equal: two
        different formulas can only coincide when both their baselines are
        frozen.

        UTC deliberately, matching `RiskManager._roll_daily_window_if_needed`.
        """
        today = datetime.now(timezone.utc).date()

        if self.state.daily_window_date is None:
            self.state.daily_window_date = today
            return

        if self.state.daily_window_date == today:
            return

        previous = self.state.daily_window_date
        self.state.daily_window_date = today

        # ONLY the daily-scoped state is rebased.
        self.state.initial_balance = current_balance
        self.state.current_daily_loss_pct = 0.0

        # Deliberately NOT reset here, because neither is a daily metric and
        # resetting them would quietly delete the cumulative protections that
        # make a daily reset safe in the first place:
        #
        #   peak_balance -- the all-time high-water mark behind the 20%
        #       max-drawdown breaker. Rebasing it daily would measure drawdown
        #       from each morning's open, so an account bleeding 4% a day
        #       forever would never trip the drawdown breaker. That breaker is
        #       precisely the backstop for repeated daily-loss resets.
        #
        #   current_consecutive_losses -- a streak breaker for a broken
        #       strategy. Zeroing it each midnight means a bot losing four
        #       trades every day never reaches five in a row.
        #
        # Drop only the daily-loss entry from the triggered list; a drawdown or
        # consecutive-loss trigger is still live and must keep blocking.
        self.state.triggered_thresholds = [
            t for t in self.state.triggered_thresholds if t != "daily_loss_limit"
        ]

        logger.info(
            f"KillSwitch daily window rolled {previous} -> {today}; "
            f"daily baseline rebased to {current_balance:.2f} "
            f"(peak_balance {self.state.peak_balance:.2f} and loss streak "
            f"{self.state.current_consecutive_losses} carried over)"
        )

        # A daily-loss halt is scoped to its day, so release it -- but only if
        # nothing else still justifies the halt. force=False makes deactivate()
        # refuse while any other threshold remains in triggered_thresholds, so
        # an account that is also in max drawdown stays halted.
        #
        # A manual halt is never released: an operator stop must survive
        # midnight. (Audit T-27 records RiskManager getting this wrong; do not
        # reproduce it here.)
        if (
            self.state.is_active
            and not self.state.manual_override
            and self.state.activation_reason == KillSwitchReason.DAILY_LOSS_LIMIT
        ):
            if self.deactivate(force=False):
                logger.info("Released automatic daily-loss halt: new UTC day, baseline reset")
            else:
                logger.warning(
                    "Daily window rolled but halt retained: other thresholds "
                    f"still triggered: {self.state.triggered_thresholds}"
                )

    def reset_daily_metrics(self):
        """Reset daily metrics (call at start of trading day)"""
        self.state.initial_balance = self.state.current_balance
        self.state.current_daily_loss_pct = 0.0
        self.state.current_consecutive_losses = 0
        self.state.triggered_thresholds = []
        self.state.daily_window_date = datetime.now(timezone.utc).date()
        logger.info("KillSwitch daily metrics reset")

    def register_callback(self, callback: Callable):
        """Register callback for kill switch activation"""
        self._callbacks.append(callback)

    def get_status(self) -> Dict:
        """Get current kill switch status"""
        return {
            "is_active": self.state.is_active,
            "activation_time": self.state.activation_time.isoformat()
            if self.state.activation_time
            else None,
            "activation_reason": self.state.activation_reason.value
            if self.state.activation_reason
            else None,
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
