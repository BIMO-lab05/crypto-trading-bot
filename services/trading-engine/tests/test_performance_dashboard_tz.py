"""
Regression tests for the timezone-coercion helper in
app/handlers/performance_dashboard.py.

Bug 2026-05-19: every period-filtered endpoint in this module
(/statistics, /performance, /equity-curve, /drawdown,
/returns-distribution) returned HTTP 500 with
"can't compare offset-naive and offset-aware datetimes". The
positions table stores opened_at/closed_at as
`timestamp without time zone`, so SQLAlchemy reads them back as
tz-naive even though they are written via
datetime.now(timezone.utc). The cutoff_date the route computed was
tz-aware (datetime.now(timezone.utc) - delta). Comparing a naive
ORM-returned closed_at to an aware cutoff_date raised the error and
no route in this module could complete.

Fix: a module-level helper coerces a possibly-naive datetime to
tz-aware UTC before the comparison. These tests pin the helper's
behaviour so future "let me just compare datetime objects" patches
do not silently reintroduce the same 500.

The integration test for this dashboard
(tests/integration/test_dashboard_integration.py) is file-level
skipped pending PR #86 follow-up, so a focused unit test is the
durable regression net.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.handlers.performance_dashboard import _ensure_utc


@pytest.mark.unit
class TestEnsureUtc:
    def test_naive_datetime_is_coerced_to_utc(self):
        """
        A tz-naive datetime is treated as UTC by convention because
        the positions table is `timestamp without time zone` written
        through datetime.now(timezone.utc).
        """
        naive = datetime(2026, 5, 19, 12, 0, 0)
        result = _ensure_utc(naive)
        assert result is not None
        assert result.tzinfo is timezone.utc
        # The clock fields are unchanged — only the tz label is attached.
        assert result.year == 2026
        assert result.month == 5
        assert result.day == 19
        assert result.hour == 12

    def test_aware_datetime_is_passed_through_unchanged(self):
        """An already-aware datetime is returned as-is — same identity ok."""
        aware = datetime(2026, 5, 19, 12, 0, 0, tzinfo=timezone.utc)
        result = _ensure_utc(aware)
        assert result is aware
        assert result.tzinfo is timezone.utc

    def test_aware_non_utc_datetime_is_left_alone(self):
        """
        A datetime already tagged with a non-UTC tz must NOT be
        rewritten — that would silently change the wall-clock value.
        The helper only fills in tz=UTC when none is present.
        """
        plus_two = timezone(timedelta(hours=2))
        aware = datetime(2026, 5, 19, 14, 0, 0, tzinfo=plus_two)
        result = _ensure_utc(aware)
        assert result is aware
        assert result.utcoffset() == timedelta(hours=2)

    def test_none_is_passed_through(self):
        """Optional[datetime] in, Optional[datetime] out — None survives."""
        assert _ensure_utc(None) is None

    def test_naive_comparison_to_aware_cutoff_does_not_raise(self):
        """
        Anchor the actual failure mode: comparing a naive ORM value
        to a tz-aware cutoff must succeed once the helper is in the
        path. If this raises, the route fix is not effective.
        """
        naive_closed_at = datetime(2026, 5, 19, 12, 0, 0)
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        # Without _ensure_utc, this comparison raises
        # "can't compare offset-naive and offset-aware datetimes".
        assert _ensure_utc(naive_closed_at) >= cutoff
