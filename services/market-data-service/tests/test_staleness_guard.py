"""
Regression tests for the market-data staleness guard (audit DL-1 follow-up).

Ingest once stalled for 17 hours while every read returned the last stored row
as current, with HTTP 200 and a green /health. Repairing the scheduler (66779e2)
fixed that instance; these tests pin the behaviour that stops the class:

  - a stale stored row is treated as a MISS so the live re-fetch runs, meaning
    the outage self-heals on the first read rather than persisting;
  - if that re-fetch also fails, the stale row may still be served, but never
    without disclosing its age;
  - /ready reports not-ready when ingest has stalled.
"""

import time
from unittest.mock import AsyncMock, patch

import pytest

from app.handlers.query import assess_freshness, ticker_age_seconds, get_ticker
from app.config import get_settings


def _ticker(symbol="BTCUSDT", price="62848.40", age_seconds=0):
    ts = int((time.time() - age_seconds) * 1000)
    return {"symbol": symbol, "last_price": price, "timestamp": ts, "created_at": ts}


class TestFreshnessHelpers:
    def test_fresh_row_is_not_stale(self):
        age, stale = assess_freshness(_ticker(age_seconds=5))
        assert age < 10
        assert stale is False

    def test_row_beyond_budget_is_stale(self):
        budget = get_settings().market_data_staleness_seconds
        age, stale = assess_freshness(_ticker(age_seconds=budget + 60))
        assert age > budget
        assert stale is True

    def test_the_actual_outage_is_flagged(self):
        """The real DL-1 shape: a 17-hour-old row."""
        _, stale = assess_freshness(_ticker(age_seconds=17 * 3600))
        assert stale is True

    def test_missing_timestamp_is_treated_as_stale(self):
        """Cannot prove it is current -> must not be presented as fact."""
        age, stale = assess_freshness({"symbol": "BTCUSDT", "last_price": "1"})
        assert age is None
        assert stale is True

    def test_unparseable_timestamp_does_not_raise(self):
        assert ticker_age_seconds({"timestamp": "not-a-number"}) is None


class TestStaleRowTriggersLiveFetch:
    """
    The poison-pill fix. Previously the live-fetch fallback fired only when
    there was NO row, so any row -- however old -- short-circuited it.
    """

    @pytest.mark.asyncio
    async def test_stale_row_falls_through_to_live_fetch(self):
        stale = _ticker(price="60000.00", age_seconds=17 * 3600)
        fresh = _ticker(price="62848.40", age_seconds=0)

        fetcher = AsyncMock()
        fetcher.get_ticker = AsyncMock(return_value=fresh)

        with (
            patch("app.handlers.query.cache_get", AsyncMock(return_value=None)),
            patch("app.handlers.query.cache_set", AsyncMock()),
            patch("app.handlers.query.TickerRepository") as repo,
        ):
            repo.get_latest_ticker = AsyncMock(
                return_value=type("T", (), {"to_dict": lambda self: stale})()
            )
            repo.save_ticker = AsyncMock(return_value=True)

            result = await get_ticker("BTCUSDT", fetcher=fetcher)

        fetcher.get_ticker.assert_awaited_once()
        assert result["source"] == "live"
        assert result["data"]["last_price"] == "62848.40"
        assert result["is_stale"] is False

    @pytest.mark.asyncio
    async def test_fresh_row_is_served_without_refetch(self):
        """The guard must not turn every read into a Bybit call."""
        fresh = _ticker(age_seconds=30)
        fetcher = AsyncMock()
        fetcher.get_ticker = AsyncMock()

        with (
            patch("app.handlers.query.cache_get", AsyncMock(return_value=None)),
            patch("app.handlers.query.cache_set", AsyncMock()),
            patch("app.handlers.query.TickerRepository") as repo,
        ):
            repo.get_latest_ticker = AsyncMock(
                return_value=type("T", (), {"to_dict": lambda self: fresh})()
            )

            result = await get_ticker("BTCUSDT", fetcher=fetcher)

        fetcher.get_ticker.assert_not_awaited()
        assert result["source"] == "database"
        assert result["is_stale"] is False
        assert result["age_seconds"] < 60

    @pytest.mark.asyncio
    async def test_stale_row_served_when_refetch_fails_but_is_disclosed(self, caplog):
        """
        Degrading to a stale price beats a 500 -- but the caller is told the
        age and the operator gets an ERROR. Never silent.
        """
        stale = _ticker(age_seconds=17 * 3600)
        fetcher = AsyncMock()
        fetcher.get_ticker = AsyncMock(return_value=None)

        with (
            patch("app.handlers.query.cache_get", AsyncMock(return_value=None)),
            patch("app.handlers.query.cache_set", AsyncMock()),
            patch("app.handlers.query.TickerRepository") as repo,
        ):
            repo.get_latest_ticker = AsyncMock(
                return_value=type("T", (), {"to_dict": lambda self: stale})()
            )
            with caplog.at_level("ERROR"):
                result = await get_ticker("BTCUSDT", fetcher=fetcher)

        assert result["is_stale"] is True
        assert result["age_seconds"] > 60000
        assert any("STALE" in r.message for r in caplog.records)


class TestReadinessReportsFreshness:
    @pytest.mark.asyncio
    async def test_ready_503s_when_ingest_stalled(self):
        from fastapi import HTTPException
        from app.handlers.health import readiness_check

        fetcher = AsyncMock()
        fetcher.health_check = AsyncMock(return_value=True)

        with patch(
            "app.repository.TickerRepository.get_newest_row_age_seconds",
            AsyncMock(return_value=17 * 3600),
        ):
            with pytest.raises(HTTPException) as exc:
                await readiness_check(fetcher=fetcher)

        assert exc.value.status_code == 503
        assert "stale" in str(exc.value.detail).lower()

    @pytest.mark.asyncio
    async def test_ready_ok_when_ingest_current(self):
        from app.handlers.health import readiness_check

        fetcher = AsyncMock()
        fetcher.health_check = AsyncMock(return_value=True)

        with patch(
            "app.repository.TickerRepository.get_newest_row_age_seconds",
            AsyncMock(return_value=42.0),
        ):
            result = await readiness_check(fetcher=fetcher)

        assert result["status"] == "ready"
        assert result["data_freshness"]["ok"] is True

    @pytest.mark.asyncio
    async def test_empty_table_is_not_ready(self):
        from fastapi import HTTPException
        from app.handlers.health import readiness_check

        fetcher = AsyncMock()
        fetcher.health_check = AsyncMock(return_value=True)

        with patch(
            "app.repository.TickerRepository.get_newest_row_age_seconds",
            AsyncMock(return_value=None),
        ):
            with pytest.raises(HTTPException) as exc:
                await readiness_check(fetcher=fetcher)

        assert exc.value.status_code == 503
