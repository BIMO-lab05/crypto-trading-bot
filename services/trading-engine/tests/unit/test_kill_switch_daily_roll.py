"""
Regression tests for the kill switch's daily window (2026-08-01).

`KillSwitchState.initial_balance` was set once at boot and never rolled, so
`current_daily_loss_pct` measured cumulative loss since process start rather
than loss within a day. `AutoTrader.reset_daily_metrics()` existed to fix that
and had zero callers. The 5% DAILY breaker therefore behaved as an all-time 5%
breaker: once crossed, the bot halted permanently.

Observed live: daily_loss_pct 8.42% with trading halted and no path back.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.trading_enhancements.kill_switch import (
    KillSwitch,
    KillSwitchConfig,
    KillSwitchReason,
)


def _switch(max_daily_loss_pct=5.0):
    ks = KillSwitch(KillSwitchConfig(max_daily_loss_pct=max_daily_loss_pct))
    ks.initialize_balance(100.0)
    return ks


def _on_date(d: date):
    """Patch the module's clock so the roll sees a chosen UTC date."""
    fake = datetime(d.year, d.month, d.day, 12, 0, tzinfo=timezone.utc)

    class _DT(datetime):
        @classmethod
        def now(cls, tz=None):
            return fake if tz else datetime(d.year, d.month, d.day, 12, 0)

    return patch("app.trading_enhancements.kill_switch.datetime", _DT)


class TestDailyWindowRoll:
    def test_no_roll_within_the_same_day(self):
        ks = _switch()
        baseline = ks.state.initial_balance

        ks.update_metrics(current_balance=97.0)

        assert ks.state.initial_balance == baseline
        assert ks.state.current_daily_loss_pct == pytest.approx(3.0)

    def test_rolls_and_rebases_on_new_utc_day(self):
        ks = _switch()
        today = ks.state.daily_window_date

        with _on_date(today + timedelta(days=1)):
            ks.update_metrics(current_balance=96.0)

        # Baseline rebased to the new day's opening equity, so a loss carried
        # over from yesterday is no longer counted against today.
        assert ks.state.initial_balance == 96.0
        assert ks.state.daily_window_date == today + timedelta(days=1)
        assert ks.state.current_daily_loss_pct == 0.0

    def test_cumulative_multiday_loss_does_not_read_as_one_day(self):
        """
        The reproduction. Losing 4% a day for three days must never present as
        a single 12% day and trip a 5% daily breaker.
        """
        ks = _switch()
        day0 = ks.state.daily_window_date

        balance = 100.0
        for offset in range(1, 4):
            balance *= 0.96
            with _on_date(day0 + timedelta(days=offset)):
                ks.update_metrics(current_balance=balance)

            assert ks.state.current_daily_loss_pct < 5.0
            assert ks.state.is_active is False

    def test_within_day_loss_still_trips(self):
        """The breaker must still do its job inside a single day."""
        ks = _switch()

        ks.update_metrics(current_balance=90.0)  # -10% in one day

        assert ks.state.current_daily_loss_pct == pytest.approx(10.0)
        assert ks.state.is_active is True


class TestHaltReleaseSemantics:
    def test_roll_releases_an_automatic_daily_loss_halt(self):
        ks = _switch()
        ks.update_metrics(current_balance=90.0)
        assert ks.state.is_active is True
        assert ks.state.activation_reason == KillSwitchReason.DAILY_LOSS_LIMIT

        with _on_date(ks.state.daily_window_date + timedelta(days=1)):
            ks.update_metrics(current_balance=90.0)

        assert ks.state.is_active is False, "a daily halt must not outlive its day"

    def test_roll_does_NOT_release_a_manual_halt(self):
        """
        An operator stop must survive midnight. Audit T-27 records RiskManager
        clearing manual halts on its day roll; this must not repeat that.
        """
        ks = _switch()
        ks.state.is_active = True
        ks.state.manual_override = True
        ks.state.activation_reason = KillSwitchReason.MANUAL_ACTIVATION

        with _on_date(ks.state.daily_window_date + timedelta(days=1)):
            ks.update_metrics(current_balance=99.0)

        assert ks.state.is_active is True
        assert ks.state.manual_override is True

    def test_roll_does_not_release_a_drawdown_halt(self):
        """Drawdown is not a daily metric; its halt is not the roll's to clear."""
        ks = _switch()
        ks.state.is_active = True
        ks.state.activation_reason = KillSwitchReason.MAX_DRAWDOWN

        with _on_date(ks.state.daily_window_date + timedelta(days=1)):
            ks.update_metrics(current_balance=99.0)

        assert ks.state.is_active is True


class TestWindowAnchoring:
    def test_initialize_balance_anchors_the_window(self):
        """Boot must not leave the window unset, or the first tick looks like a roll."""
        ks = _switch()
        assert ks.state.daily_window_date == datetime.now(timezone.utc).date()

    def test_reset_daily_metrics_also_anchors(self):
        ks = _switch()
        ks.state.daily_window_date = None

        ks.reset_daily_metrics()

        assert ks.state.daily_window_date == datetime.now(timezone.utc).date()
