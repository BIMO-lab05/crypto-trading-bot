"""
Regression tests for kline interval validation in app/fetcher.py.

Bug 2026-08-18: a request like
GET /api/v1/indicators/atr/BTCUSDT?interval=invalid produced a 500 on
every advanced-indicator endpoint — market-data correctly returned
400, but the fetcher wrapped it into a generic computation failure.

Fix: MarketDataFetcher.get_klines rejects unknown intervals with a 422
HTTPException before any upstream call. Handlers re-raise
HTTPException, so the client error propagates untouched.
"""

import pytest
from fastapi import HTTPException

from app.fetcher import VALID_INTERVALS, MarketDataFetcher, normalize_interval


@pytest.mark.unit
class TestIntervalValidation:
    async def test_invalid_interval_raises_422(self):
        fetcher = MarketDataFetcher()
        with pytest.raises(HTTPException) as exc:
            await fetcher.get_klines("BTCUSDT", interval="invalid", limit=50)
        assert exc.value.status_code == 422
        assert "interval" in exc.value.detail.lower()

    async def test_minute_aliases_normalize_into_valid_set(self):
        # 1440/10080/43200 normalize to D/W/M and must not be rejected.
        for alias in ("1440", "10080", "43200"):
            assert normalize_interval(alias) in VALID_INTERVALS

    def test_valid_set_matches_market_data_service(self):
        # The set must mirror market-data's VALID_INTERVALS (query.py) —
        # drift would make TA reject intervals market-data serves.
        assert VALID_INTERVALS == frozenset(
            {"1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M"}
        )
