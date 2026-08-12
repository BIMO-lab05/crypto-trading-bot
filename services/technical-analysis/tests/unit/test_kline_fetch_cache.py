"""Kline fetch cache: TTL + single-flight (2026-08-12 DB stampede fix).

One signal cycle asks ~12 indicator endpoints for the same candle window.
Uncached, each ask is its own market-data -> TimescaleDB query; the
auto-trader resume drove the DB to 173% CPU and timeout bursts. These tests
pin the two properties that collapse that load: a window fetched once is
served from cache inside the TTL, and a concurrent burst costs exactly one
upstream call.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.fetcher import MarketDataFetcher


def _mk_response(rows):
    resp = AsyncMock()
    resp.status_code = 200
    resp.raise_for_status = lambda: None
    resp.json = lambda: {"success": True, "data": rows}
    return resp


def _rows(n=35):
    return [
        {
            "timestamp": 1_700_000_000_000 + i * 3_600_000,
            "open": 100.0 + i,
            "high": 101.0 + i,
            "low": 99.0 + i,
            "close": 100.5 + i,
            "volume": 10.0,
        }
        for i in range(n)
    ]


@pytest.fixture()
def fetcher():
    f = MarketDataFetcher.__new__(MarketDataFetcher)
    f.settings = type(
        "S",
        (),
        {"market_data_url": "http://md", "kline_cache_ttl_seconds": 30},
    )()
    f.base_url = "http://md"
    f.client = AsyncMock()
    f.client.get = AsyncMock(return_value=_mk_response(_rows()))
    f._kline_cache = {}
    f._kline_locks = {}
    return f


def test_second_call_within_ttl_hits_cache(fetcher):
    async def run():
        a = await fetcher.get_klines("BTCUSDT", "60", 200)
        b = await fetcher.get_klines("BTCUSDT", "60", 200)
        assert len(a) == len(b) == 35
        assert fetcher.client.get.await_count == 1

    asyncio.run(run())


def test_concurrent_burst_is_single_flight(fetcher):
    async def run():
        results = await asyncio.gather(
            *(fetcher.get_klines("BTCUSDT", "60", 200) for _ in range(12))
        )
        assert all(len(r) == 35 for r in results)
        assert fetcher.client.get.await_count == 1

    asyncio.run(run())


def test_distinct_windows_fetch_separately(fetcher):
    async def run():
        await fetcher.get_klines("BTCUSDT", "60", 200)
        await fetcher.get_klines("BTCUSDT", "15", 200)
        await fetcher.get_klines("ETHUSDT", "60", 200)
        await fetcher.get_klines("BTCUSDT", "60", 50)
        assert fetcher.client.get.await_count == 4

    asyncio.run(run())


def test_ttl_zero_disables_cache(fetcher):
    fetcher.settings.kline_cache_ttl_seconds = 0

    async def run():
        await fetcher.get_klines("BTCUSDT", "60", 200)
        await fetcher.get_klines("BTCUSDT", "60", 200)
        assert fetcher.client.get.await_count == 2

    asyncio.run(run())


def test_empty_window_is_not_cached(fetcher):
    fetcher.client.get = AsyncMock(
        side_effect=[_mk_response([]), _mk_response(_rows())]
    )

    async def run():
        first = await fetcher.get_klines("BTCUSDT", "60", 200)
        assert first == []
        second = await fetcher.get_klines("BTCUSDT", "60", 200)
        assert len(second) == 35
        assert fetcher.client.get.await_count == 2

    asyncio.run(run())


def test_cached_list_is_copy_not_alias(fetcher):
    async def run():
        a = await fetcher.get_klines("BTCUSDT", "60", 200)
        a.clear()
        b = await fetcher.get_klines("BTCUSDT", "60", 200)
        assert len(b) == 35

    asyncio.run(run())
