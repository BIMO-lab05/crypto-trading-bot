"""Tests for orderbook snapshot collection (edge-search v2 phase A1)."""

from decimal import Decimal
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
    # snapshot_data is a dict (JSONB column, final review H-3) -- not a JSON
    # string. Double-encoding via json.dumps() would store a string inside
    # the jsonb column and defeat every jsonb operator/GIN index.
    assert row.snapshot_data == {
        "bids": [["118000.5", "1.25"]],
        "asks": [["118001.0", "0.8"]],
    }
    # best_bid/best_ask built as Decimal(str(...)), never float()/round(_, 2)
    # (final review H-3; ADA precision incident, CLAUDE.md commit 487d1bd).
    assert row.best_bid == Decimal("118000.5")
    assert row.best_ask == Decimal("118001.0")
    assert isinstance(row.best_bid, Decimal)
    assert isinstance(row.best_ask, Decimal)


@pytest.mark.asyncio
@patch("app.repository.get_db_session")
@patch("app.repository.time")
async def test_save_snapshots_bulk_writes_all_rows_in_one_session(
    mock_time, mock_get_db_session
):
    """final review H-2/M-6: one session, one add_all, one commit for the
    whole tick instead of one session per symbol."""
    mock_time.time.return_value = 1699000000.0

    mock_session = AsyncMock()
    mock_get_db_session.return_value.__aenter__.return_value = mock_session

    snaps = [
        {
            "symbol": "BTCUSDT",
            "timestamp_ms": 1755600000000,
            "bids": [["118000.5", "1.25"]],
            "asks": [["118001.0", "0.8"]],
        },
        {
            "symbol": "ETHUSDT",
            "timestamp_ms": 1755600000000,
            "bids": [["3000.0", "2.0"]],
            "asks": [["3000.5", "1.5"]],
        },
    ]
    written = await OrderbookRepository.save_snapshots_bulk(snaps)

    assert written == 2
    mock_get_db_session.assert_called_once()  # one session for the whole batch
    mock_session.add_all.assert_called_once()
    rows = mock_session.add_all.call_args[0][0]
    assert len(rows) == 2
    assert {r.symbol for r in rows} == {"BTCUSDT", "ETHUSDT"}


@pytest.mark.asyncio
async def test_save_snapshots_bulk_empty_list_is_a_noop():
    assert await OrderbookRepository.save_snapshots_bulk([]) == 0


@pytest.mark.asyncio
async def test_collect_orderbook_data_fetches_concurrently_and_bulk_saves():
    """final review H-2/M-6: symbols fetch via asyncio.gather (not
    sequential await), and the tick's snapshots are written via ONE
    save_snapshots_bulk call, not one save_snapshot per symbol."""
    from app import scheduler as sched

    fake_ob = {"symbol": "X", "timestamp_ms": 1, "bids": [], "asks": []}
    fake_fetcher = AsyncMock()
    fake_fetcher.get_orderbook = AsyncMock(return_value=fake_ob)
    with (
        patch.object(sched, "_trading_pairs", return_value=["BTCUSDT", "ETHUSDT"]),
        patch.object(sched, "_get_orderbook_fetcher", return_value=fake_fetcher),
        patch("app.scheduler.OrderbookRepository") as R,
    ):
        R.return_value.save_snapshots_bulk = AsyncMock(return_value=2)
        await sched.collect_orderbook_data()
    assert fake_fetcher.get_orderbook.await_count == 2
    R.return_value.save_snapshots_bulk.assert_awaited_once()
    saved = R.return_value.save_snapshots_bulk.call_args[0][0]
    assert len(saved) == 2


@pytest.mark.asyncio
async def test_collect_orderbook_data_reuses_fetcher_across_calls():
    """final review H-2: the fetcher is a module-level singleton, not
    reconstructed (and its connection pool not torn down) every tick."""
    from app import scheduler as sched

    fake_ob = {"symbol": "X", "timestamp_ms": 1, "bids": [], "asks": []}
    fake_fetcher = AsyncMock()
    fake_fetcher.get_orderbook = AsyncMock(return_value=fake_ob)
    with (
        patch.object(sched, "_trading_pairs", return_value=["BTCUSDT"]),
        patch.object(sched, "_get_orderbook_fetcher", return_value=fake_fetcher),
        patch("app.scheduler.OrderbookRepository") as R,
    ):
        R.return_value.save_snapshots_bulk = AsyncMock(return_value=1)
        await sched.collect_orderbook_data()
        await sched.collect_orderbook_data()
    fake_fetcher.close.assert_not_called()
