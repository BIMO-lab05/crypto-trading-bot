"""Tests for orderbook snapshot collection (edge-search v2 phase A1)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.fetcher import BybitDataFetcher
from app.repository import OrderbookRepository

CONNECTOR_PAYLOAD = {
    "success": True,
    "data": {
        "s": "BTCUSDT",
        "ts": 1755600000000,
        "b": [["118000.5", "1.25"], ["118000.0", "0.5"]],
        "a": [["118001.0", "0.8"], ["118001.5", "2.0"]],
    },
}


@pytest.mark.asyncio
async def test_get_orderbook_normalizes_connector_payload():
    fetcher = BybitDataFetcher()
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = lambda: None
    mock_resp.json = lambda: CONNECTOR_PAYLOAD
    with patch.object(fetcher.client, "get", return_value=mock_resp) as g:
        ob = await fetcher.get_orderbook("BTCUSDT")
    await fetcher.close()
    assert g.call_args.kwargs["params"]["limit"] == 25
    assert ob["symbol"] == "BTCUSDT"
    assert ob["timestamp_ms"] == 1755600000000
    assert ob["bids"][0] == ["118000.5", "1.25"]
    assert len(ob["asks"]) == 2


@pytest.mark.asyncio
async def test_get_orderbook_returns_none_on_error():
    fetcher = BybitDataFetcher()
    with patch.object(fetcher.client, "get", side_effect=Exception("boom")):
        assert await fetcher.get_orderbook("BTCUSDT") is None
    await fetcher.close()


@pytest.mark.asyncio
@patch("app.repository.get_db_session")
@patch("app.repository.time")
async def test_save_snapshot_writes_row(mock_time, mock_get_db_session):
    """Follows the TickerRepository.save_ticker test convention in
    tests/test_repository.py: mock app.repository.get_db_session's async
    context manager and assert the ORM row reaches session.add."""
    mock_time.time.return_value = 1699000000.0

    mock_session = AsyncMock()
    mock_get_db_session.return_value.__aenter__.return_value = mock_session

    snap = {
        "symbol": "BTCUSDT",
        "timestamp_ms": 1755600000000,
        "bids": [["118000.5", "1.25"]],
        "asks": [["118001.0", "0.8"]],
    }
    ok = await OrderbookRepository.save_snapshot(snap)

    assert ok is True
    mock_session.add.assert_called_once()
    row = mock_session.add.call_args[0][0]
    assert row.symbol == "BTCUSDT"
    assert row.timestamp == 1755600000000
    assert '"bids"' in row.snapshot_data
    assert '"asks"' in row.snapshot_data


@pytest.mark.asyncio
async def test_collect_orderbook_data_fetches_and_saves_all_pairs():
    from app import scheduler as sched

    fake_ob = {"symbol": "X", "timestamp_ms": 1, "bids": [], "asks": []}
    with (
        patch.object(sched, "_trading_pairs", return_value=["BTCUSDT", "ETHUSDT"]),
        patch("app.scheduler.BybitDataFetcher") as F,
        patch("app.scheduler.OrderbookRepository") as R,
    ):
        F.return_value.get_orderbook = AsyncMock(return_value=fake_ob)
        F.return_value.close = AsyncMock()
        R.return_value.save_snapshot = AsyncMock(return_value=True)
        await sched.collect_orderbook_data()
    assert F.return_value.get_orderbook.await_count == 2
    assert R.return_value.save_snapshot.await_count == 2
    F.return_value.close.assert_awaited()  # pool leak guard, same as ticker job
