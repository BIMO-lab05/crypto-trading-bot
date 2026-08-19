"""Tests for open-interest collection (edge-search v2 phase A2)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.fetcher import BybitDataFetcher
from app.repository import OpenInterestRepository

CONNECTOR_PAYLOAD = {
    "success": True,
    "data": {
        "symbol": "BTCUSDT",
        "category": "linear",
        "list": [
            {"openInterest": "12345.5", "timestamp": "1755600000000"},
            {"openInterest": "12300.0", "timestamp": "1755599700000"},
        ],
    },
}


@pytest.mark.asyncio
async def test_get_open_interest_normalizes_connector_payload():
    fetcher = BybitDataFetcher()
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = lambda: None
    mock_resp.json = lambda: CONNECTOR_PAYLOAD
    with patch.object(fetcher.client, "get", return_value=mock_resp) as g:
        rows = await fetcher.get_open_interest("BTCUSDT")
    await fetcher.close()
    assert g.call_args.kwargs["params"]["symbol"] == "BTCUSDT"
    assert len(rows) == 2
    assert rows[0]["symbol"] == "BTCUSDT"
    assert rows[0]["timestamp_ms"] == 1755600000000
    assert isinstance(rows[0]["timestamp_ms"], int)
    assert rows[0]["open_interest"] == 12345.5
    assert isinstance(rows[0]["open_interest"], float)


@pytest.mark.asyncio
async def test_get_open_interest_returns_none_on_error():
    fetcher = BybitDataFetcher()
    with patch.object(fetcher.client, "get", side_effect=Exception("boom")):
        assert await fetcher.get_open_interest("BTCUSDT") is None
    await fetcher.close()


@pytest.mark.asyncio
async def test_get_open_interest_returns_none_on_empty_list():
    fetcher = BybitDataFetcher()
    empty_payload = {"success": True, "data": {"symbol": "BTCUSDT", "list": []}}
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = lambda: None
    mock_resp.json = lambda: empty_payload
    with patch.object(fetcher.client, "get", return_value=mock_resp):
        assert await fetcher.get_open_interest("BTCUSDT") is None
    await fetcher.close()


@pytest.mark.asyncio
@patch("app.repository.get_db_session")
@patch("app.repository.time")
async def test_bulk_upsert_writes_rows(mock_time, mock_get_db_session):
    """Follows KlineRepository.bulk_upsert's test convention: mock
    app.repository.get_db_session's async context manager and assert the
    upsert statement reaches session.execute."""
    mock_time.time.return_value = 1699000000.0

    mock_session = AsyncMock()
    mock_get_db_session.return_value.__aenter__.return_value = mock_session

    rows = [
        {"symbol": "BTCUSDT", "timestamp_ms": 1755600000000, "open_interest": 12345.5},
        {"symbol": "BTCUSDT", "timestamp_ms": 1755599700000, "open_interest": 12300.0},
    ]
    n = await OpenInterestRepository.bulk_upsert(rows)

    assert n == 2
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_bulk_upsert_empty_list_is_noop():
    assert await OpenInterestRepository.bulk_upsert([]) == 0


@pytest.mark.asyncio
async def test_collect_open_interest_data_fetches_and_upserts_all_pairs():
    from app import scheduler as sched

    fake_rows = [{"symbol": "X", "timestamp_ms": 1, "open_interest": 1.0}]
    with (
        patch.object(sched, "_trading_pairs", return_value=["BTCUSDT", "ETHUSDT"]),
        patch("app.scheduler.BybitDataFetcher") as F,
        patch("app.scheduler.OpenInterestRepository") as R,
    ):
        F.return_value.get_open_interest = AsyncMock(return_value=fake_rows)
        F.return_value.close = AsyncMock()
        R.return_value.bulk_upsert = AsyncMock(return_value=1)
        await sched.collect_open_interest_data()
    assert F.return_value.get_open_interest.await_count == 2
    assert R.return_value.bulk_upsert.await_count == 2
    F.return_value.close.assert_awaited()  # pool leak guard, same as orderbook job
