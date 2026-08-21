"""
Honesty tests for the Phase 1 monitoring endpoints.

Locks in the 2026-08-20 fixes for live-measured defects:
1. `hours` query param actually filters every counter (payloads for
   different windows differ beyond the echoed period_hours).
2. Counts are true counts, not capped at the display deque's 1000-row
   fetch limit.
3. All counters in one response derive from one consistent windowed
   source (blocks+passed == signals.total, ATR bins sum to signals with
   ATR data, etc.).
4/5. /metrics and /health compute shared quantities with ONE formula
   from ONE source (validator rejection rate, trend distribution).
6. Timestamps are UTC-aware isoformat with an explicit +00:00 offset.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.handlers.phase1 import (
    get_latest_phase1_signal,
    get_phase1_health,
    get_phase1_metrics_endpoint,
)
from app.phase1_metrics import Phase1MetricsProvider


@pytest.fixture(autouse=True)
def reset_provider_state():
    """Isolate every test from class-level provider state."""
    Phase1MetricsProvider.reset_stats()
    Phase1MetricsProvider.set_active(True)
    yield
    Phase1MetricsProvider.reset_stats()
    Phase1MetricsProvider.set_active(True)


def _record(
    action="BUY",
    trend="BULLISH",
    blocked=False,
    validated=True,
    strength="STRONG",
    volatility="HIGH",
    recorded_at=None,
):
    Phase1MetricsProvider.record_signal(
        action=action,
        confidence=0.75,
        filters={
            "gatekeeper": not blocked,
            "trend": trend,
            "trend_blocked": blocked,
            "validator": validated,
            "volume_strength": strength,
        },
        metadata={"atr": {"volatility": volatility}},
        recorded_at=recorded_at,
    )


class TestHoursFilteringIsReal:
    """Defect 1: hours=1/6/24/168 returned byte-identical payloads."""

    def _seed_two_windows(self):
        old = datetime.now(timezone.utc) - timedelta(hours=3)
        _record(
            action="SELL",
            trend="BEARISH",
            blocked=True,
            validated=False,
            strength="WEAK",
            volatility="LOW",
            recorded_at=old,
        )
        _record(action="BUY", trend="BULLISH")

    def test_provider_counts_change_with_hours(self):
        self._seed_two_windows()
        provider = Phase1MetricsProvider()

        m1 = provider.get_metrics(hours=1)
        m6 = provider.get_metrics(hours=6)

        assert m1["signals"]["total"] == 1
        assert m6["signals"]["total"] == 2
        # Every counter family must move with the window, not just
        # signals.*
        assert m1["gatekeeper"]["blocks"] == 0
        assert m6["gatekeeper"]["blocks"] == 1
        assert m1["validator"]["rejected"] == 0
        assert m6["validator"]["rejected"] == 1
        assert m1["atr"]["low"] == 0
        assert m6["atr"]["low"] == 1
        assert m1["validator"]["strength_distribution"]["WEAK"] == 0
        assert m6["validator"]["strength_distribution"]["WEAK"] == 1

    async def test_handler_payloads_differ_beyond_period_hours(self):
        self._seed_two_windows()

        r1 = await get_phase1_metrics_endpoint(hours=1)
        r6 = await get_phase1_metrics_endpoint(hours=6)

        d1, d6 = r1["data"], r6["data"]
        assert d1["period_hours"] == 1
        assert d6["period_hours"] == 6
        # Strip the echoed field: the rest must still differ.
        d1.pop("period_hours")
        d6.pop("period_hours")
        assert d1 != d6

    def test_old_signals_leave_the_window(self):
        _record(recorded_at=datetime.now(timezone.utc) - timedelta(hours=30))
        provider = Phase1MetricsProvider()

        assert provider.get_metrics(hours=24)["signals"]["total"] == 0
        assert provider.get_metrics(hours=48)["signals"]["total"] == 1


class TestCountsNotCappedAtFetchLimit:
    """Defect 2: totals froze at exactly 1000 (LIMIT-1000 artifact)."""

    def test_counts_exceed_display_deque_cap(self):
        for _ in range(1005):
            _record()
        provider = Phase1MetricsProvider()

        metrics = provider.get_metrics(hours=1)
        health = provider.get_system_health()

        assert metrics["signals"]["total"] == 1005
        assert health["signals_last_hour"] == 1005
        assert health["total_signals_processed"] == 1005
        # Display history stays bounded; counters must not.
        assert len(Phase1MetricsProvider._signal_history) == 1000

    def test_lifetime_survives_signals_aging_out_of_windows(self):
        _record(recorded_at=datetime.now(timezone.utc) - timedelta(hours=30))
        _record()
        health = Phase1MetricsProvider().get_system_health()

        assert health["signals_last_hour"] == 1
        assert health["total_signals_processed"] == 2


class TestSingleConsistentSource:
    """Defect 3: total_processed=2524 vs signals.total=1000 vs
    ATR-sum=2517 in one response."""

    def test_counters_are_mutually_consistent(self):
        _record(action="BUY", trend="BULLISH")
        _record(
            action="SELL",
            trend="BEARISH",
            blocked=True,
            validated=False,
            strength="WEAK",
            volatility="LOW",
        )
        _record(action="HOLD", trend="NEUTRAL", strength="MODERATE", volatility="MEDIUM")
        m = Phase1MetricsProvider().get_metrics(hours=24)

        total = m["signals"]["total"]
        assert total == 3
        assert m["gatekeeper"]["blocks"] + m["gatekeeper"]["passed"] == total
        assert (
            m["gatekeeper"]["bullish_trends"]
            + m["gatekeeper"]["bearish_trends"]
            + m["gatekeeper"]["neutral_trends"]
        ) == total
        assert m["validator"]["confirmed"] + m["validator"]["rejected"] == total
        # Every seeded signal carried ATR data -> bins sum to total.
        assert sum(m["atr"].values()) == total
        assert (m["signals"]["buy"] + m["signals"]["sell"] + m["signals"]["hold"]) == total

    def test_block_rate_and_pass_counts_agree(self):
        _record(blocked=True)
        _record()
        _record()
        _record()
        m = Phase1MetricsProvider().get_metrics(hours=24)

        assert m["gatekeeper"]["blocks"] == 1
        assert m["gatekeeper"]["passed"] == 3
        assert m["filtering"]["gatekeeper_block_rate"] == pytest.approx(25.0)


class TestOneRateDefinitionAcrossEndpoints:
    """Defects 4+5: /metrics and /health disagreed on rejection rate
    (46.0 vs 40.016) and neutral trends (0 vs 6)."""

    def test_validator_rejection_rate_identical(self):
        for _ in range(3):
            _record(validated=True)
        for _ in range(2):
            _record(validated=False, strength="WEAK")
        provider = Phase1MetricsProvider()

        metrics = provider.get_metrics(hours=24)
        health = provider.get_system_health()

        assert health["filter_stats"]["window_hours"] == 24
        assert (
            metrics["filtering"]["validator_rejection_rate"]
            == health["filter_stats"]["validator"]["rejection_rate"]
            == pytest.approx(40.0)
        )

    def test_gatekeeper_block_rate_identical(self):
        _record(blocked=True)
        _record()
        provider = Phase1MetricsProvider()

        metrics = provider.get_metrics(hours=24)
        health = provider.get_system_health()

        assert (
            metrics["filtering"]["gatekeeper_block_rate"]
            == health["filter_stats"]["gatekeeper"]["block_rate"]
            == pytest.approx(50.0)
        )

    def test_trend_distribution_identical(self):
        for _ in range(6):
            _record(trend="NEUTRAL")
        _record(trend="BULLISH")
        provider = Phase1MetricsProvider()

        metrics = provider.get_metrics(hours=24)
        dist = provider.get_system_health()["filter_stats"]["trend_distribution"]

        assert metrics["gatekeeper"]["neutral_trends"] == 6
        assert dist["neutral"] == 6
        assert metrics["gatekeeper"]["bullish_trends"] == dist["bullish"] == 1
        assert metrics["gatekeeper"]["bearish_trends"] == dist["bearish"] == 0


class TestTimestampsAreUtcAware:
    """Defect 6: naive isoformat strings parse as LOCAL time in JS."""

    @staticmethod
    def _assert_utc_aware(value: str):
        parsed = datetime.fromisoformat(value)
        assert parsed.tzinfo is not None, f"naive timestamp emitted: {value}"
        assert parsed.utcoffset() == timedelta(0)
        assert value.endswith("+00:00") or value.endswith("Z")

    async def test_metrics_timeline_timestamps_are_aware(self):
        _record()
        result = await get_phase1_metrics_endpoint(hours=24)

        timeline = result["data"]["timeline"]
        assert timeline
        for entry in timeline:
            self._assert_utc_aware(entry["timestamp"])

    async def test_health_last_signal_time_is_aware(self):
        _record()
        result = await get_phase1_health()

        self._assert_utc_aware(result["data"]["last_signal_time"])

    async def test_latest_signal_timestamp_is_aware(self):
        _record()
        result = await get_latest_phase1_signal()

        assert result["data"] is not None
        self._assert_utc_aware(result["data"]["timestamp"])

    async def test_naive_legacy_history_treated_as_utc_not_shifted(self):
        """Pre-fix in-memory records were naive-UTC; serialization must
        attach +00:00 without shifting the value."""
        _record()
        # Simulate a legacy naive record already in history.
        naive = (datetime.now(timezone.utc) - timedelta(minutes=5)).replace(tzinfo=None)
        Phase1MetricsProvider._signal_history[-1]["timestamp"] = naive.isoformat()

        result = await get_phase1_metrics_endpoint(hours=24)
        emitted = result["data"]["timeline"][0]["timestamp"]

        self._assert_utc_aware(emitted)
        parsed = datetime.fromisoformat(emitted)
        # Same wall-clock value, just made explicit as UTC.
        assert parsed.replace(tzinfo=None) == naive
