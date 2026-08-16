"""
Market Data Service - get_historical_klines pagination tests

Regression coverage for the "backfill stops after one batch" defect:
``get_kline`` drops the still-forming candle by time filter, so a full page
comes back as ``MAX_CANDLES_PER_REQUEST - 1`` rows. The pagination loop used
to read that short batch as "history exhausted" and break, storing ~999 bars
instead of the requested range.

Deliberately a standalone module: ``test_fetcher.py`` and
``test_fetcher_enhanced.py`` both carry a module-level
``pytestmark = pytest.mark.skip(...)`` from the PR #86 fix-up, so anything
added there would silently skip. This file must never grow a module-level
skip.

``pytest.ini`` sets ``asyncio_mode = auto`` — plain ``async def test_*`` runs.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

from app.fetcher import MAX_CANDLES_PER_REQUEST, BybitDataFetcher

ONE_MINUTE_MS = 60_000


def _row(ts: int) -> Dict[str, Any]:
    """Minimal kline dict — only ``timestamp`` is load-bearing for the loop."""
    return {
        "timestamp": ts,
        "open": "50000.0",
        "high": "50100.0",
        "low": "49900.0",
        "close": "50050.0",
        "volume": "1.5",
        "turnover": "75000.0",
    }


def _descending_batch(
    newest_ts: int, count: int, step_ms: int = ONE_MINUTE_MS
) -> List[Dict[str, Any]]:
    """``count`` rows walking backwards from ``newest_ts`` (newest first)."""
    return [_row(newest_ts - i * step_ms) for i in range(count)]


async def test_short_batch_does_not_stop_pagination():
    """A batch of limit-1 rows must NOT terminate the loop.

    The still-forming candle is dropped by ``get_kline``'s time filter, so a
    *full* page arrives as 999 rows when the limit is 1000. Treating that as
    "no more data" truncated every backfill to a single batch.
    """
    # Same expression get_historical_klines uses (fetcher.py:316). time.time()
    # would drift: datetime.utcnow() is naive and .timestamp() reads it as
    # local time, pushing the fake rows outside the final window filter.
    end_time = datetime.utcnow()
    end_ms = int(end_time.timestamp() * 1000)
    target_start_ms = int((end_time - timedelta(days=5)).timestamp() * 1000)

    short = MAX_CANDLES_PER_REQUEST - 1  # 999 — the dropped forming candle

    # Batch 1 oldest is ~999 minutes back, far newer than the 7200-minute
    # target start, so the `oldest_ts <= target_start_ms` break cannot fire
    # here — the test would otherwise pass against unfixed code.
    batch_1 = _descending_batch(end_ms - ONE_MINUTE_MS, short)
    batch_1_oldest = min(k["timestamp"] for k in batch_1)
    assert batch_1_oldest > target_start_ms

    batch_2 = _descending_batch(batch_1_oldest - ONE_MINUTE_MS, short)
    batch_2_oldest = min(k["timestamp"] for k in batch_2)
    assert batch_2_oldest > target_start_ms

    fetcher = BybitDataFetcher(base_url="http://test-connector:8001")
    try:
        # Patch the method, not the HTTP layer: bypasses both
        # bybit_connector_retry and the closed-candle filter.
        with patch.object(
            fetcher,
            "get_kline",
            new=AsyncMock(side_effect=[batch_1, batch_2, []]),
        ):
            result = await fetcher.get_historical_klines(
                symbol="BTCUSDT",
                interval="1",
                days=5,
                end_time=end_time,
                rate_limit_delay=0,
            )

            assert fetcher.get_kline.await_count >= 2, (
                "pagination stopped after the first short batch"
            )

        assert len(result) == short * 2
        assert batch_2_oldest in [k["timestamp"] for k in result]
    finally:
        await fetcher.close()


async def test_reaching_target_start_still_breaks():
    """Deleting the short-batch break must not cause runaway pagination.

    Termination on ``oldest_ts <= target_start_ms`` is one of the three
    surviving exit conditions.
    """
    end_time = datetime.utcnow()
    end_ms = int(end_time.timestamp() * 1000)
    target_start_ms = int((end_time - timedelta(days=5)).timestamp() * 1000)

    batch_1 = [
        _row(end_ms - ONE_MINUTE_MS),
        _row(end_ms - 2 * ONE_MINUTE_MS),
        _row(target_start_ms + ONE_MINUTE_MS),
        _row(target_start_ms),
        _row(target_start_ms - ONE_MINUTE_MS),  # oldest <= target -> break
    ]

    fetcher = BybitDataFetcher(base_url="http://test-connector:8001")
    try:
        with patch.object(
            fetcher, "get_kline", new=AsyncMock(side_effect=[batch_1, []])
        ):
            result = await fetcher.get_historical_klines(
                symbol="BTCUSDT",
                interval="1",
                days=5,
                end_time=end_time,
                rate_limit_delay=0,
            )

            assert fetcher.get_kline.await_count == 1

        # The row older than the requested window is filtered out.
        assert len(result) == 4
    finally:
        await fetcher.close()


async def test_empty_first_batch_returns_empty():
    """Empty-batch break is the second surviving exit condition."""
    end_time = datetime.utcnow()

    fetcher = BybitDataFetcher(base_url="http://test-connector:8001")
    try:
        with patch.object(fetcher, "get_kline", new=AsyncMock(side_effect=[[]])):
            result = await fetcher.get_historical_klines(
                symbol="BTCUSDT",
                interval="1",
                days=5,
                end_time=end_time,
                rate_limit_delay=0,
            )

            assert fetcher.get_kline.await_count == 1

        assert result == []
    finally:
        await fetcher.close()
