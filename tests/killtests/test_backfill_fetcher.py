"""Backfill fetcher upgrade: batch size 1000, 11-col klines schema, liveness guard."""

import asyncio
import sys
import time
from pathlib import Path

import httpx
import pandas as pd
import pytest
import respx

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

import bybit_data_fetcher as bdf  # noqa: E402


@respx.mock
def test_fetch_klines_unwraps_flat_connector_list():
    """Regression: bybit-connector wraps as {"success": true, "data": [...]} —
    already a flat V5 row list, since BybitRestClient.get_kline() unwraps
    Bybit's {"result": {"list": [...]}} server-side before the connector
    route re-wraps it. A prior double-unwrap
    (`data.get("data", {}).get("list", [])`) silently returned [] on every
    real HTTP call since 57b0d72 — only invisible because FakeFetcher above
    overrides fetch_klines and never exercises this parsing path. This test
    hits the real HTTP path via respx so it can't regress silently again.
    """
    rows = [["1700000000000", "100", "101", "99", "100.5", "10", "1000"]]
    respx.get("http://localhost:8001/health").mock(
        return_value=httpx.Response(200, json={"status": "healthy"})
    )
    respx.get("http://localhost:8001/api/v1/market/kline").mock(
        return_value=httpx.Response(200, json={"success": True, "data": rows})
    )

    async def _run():
        f = bdf.BybitDataFetcher(base_url="http://localhost:8001")
        try:
            return await f.fetch_klines("BTCUSDT", "60", limit=5)
        finally:
            await f.close()

    assert asyncio.run(_run()) == rows


KLINES_COLUMNS = [
    "timestamp",
    "symbol",
    "interval",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "turnover",
    "is_mainnet",
    "created_at",
]


def _mk_rows(n, start_ms, interval_min=60):
    """Bybit v5 rows, newest-first, [startTime, open, high, low, close, volume, turnover]."""
    step = interval_min * 60 * 1000
    rows = []
    for i in range(n):
        ts = start_ms + i * step
        rows.append([str(ts), "100", "101", "99", "100.5", "10", "1000"])
    rows.reverse()
    return rows


class FakeFetcher(bdf.BybitDataFetcher):
    """Bypass HTTP: serve canned batches; record requested limits."""

    def __init__(self, batches):
        # deliberately do NOT call super().__init__ — no httpx client needed
        self.rate_limit_delay = 0
        self._reachability_checked = True
        self._batches = list(batches)
        self.requested_limits = []

    async def fetch_klines(
        self, symbol, interval, start_time=None, end_time=None, limit=200
    ):
        self.requested_limits.append(limit)
        return self._batches.pop(0) if self._batches else []


def test_pagination_requests_limit_1000():
    now_ms = int(time.time() * 1000)
    f = FakeFetcher([_mk_rows(1000, now_ms - 1000 * 3600 * 1000), []])
    asyncio.run(f.download_historical_data("BTCUSDT", interval="60", days=50))
    assert f.requested_limits and all(l == 1000 for l in f.requested_limits)


def test_default_limits_are_1000():
    import inspect

    assert (
        inspect.signature(bdf.BybitDataFetcher.fetch_klines).parameters["limit"].default
        == 1000
    )
    assert (
        inspect.signature(bdf.BybitDataFetcher.get_klines).parameters["limit"].default
        == 1000
    )


def test_klines_schema_csv(tmp_path):
    now_ms = int(time.time() * 1000)
    f = FakeFetcher([_mk_rows(48, now_ms - 48 * 3600 * 1000), []])
    out = tmp_path / "BTCUSDT_60m_2d_bybit.csv"
    asyncio.run(
        f.download_historical_data(
            "BTCUSDT", interval="60", days=2, output_file=str(out), schema="klines"
        )
    )
    df = pd.read_csv(out)
    assert list(df.columns) == KLINES_COLUMNS
    assert df["is_mainnet"].all()
    assert (df["symbol"] == "BTCUSDT").all()
    assert (df["interval"].astype(str) == "60").all()


def test_klines_schema_drops_trailing_forming_bar(tmp_path):
    """Regression: Bybit V5 always reports the currently-forming bar as the
    newest row, even though its close time is still in the future. H3's
    replay driver walks the full frame and would otherwise exit on a
    still-forming close price. The klines schema must trim it; the legacy
    schema (test_legacy_schema_unchanged) is intentionally left untouched.
    """
    now_ms = int(time.time() * 1000)
    step_ms = 60 * 60 * 1000  # 60m interval
    closed_starts = [now_ms - (i + 1) * step_ms for i in range(5, 0, -1)]
    forming_start = now_ms - 5 * 60 * 1000  # opened 5 minutes ago, not yet closed
    starts = closed_starts + [forming_start]
    rows = [[str(ts), "100", "101", "99", "100.5", "10", "1000"] for ts in starts]
    rows.reverse()  # Bybit convention: newest first

    f = FakeFetcher([rows])
    out = tmp_path / "BTCUSDT_60m_1d_bybit.csv"
    asyncio.run(
        f.download_historical_data(
            "BTCUSDT", interval="60", days=1, output_file=str(out), schema="klines"
        )
    )
    df = pd.read_csv(out)
    # Resolution-independent: pandas infers a different datetime64 storage
    # resolution reading this back from CSV than it used in-memory, so a
    # raw int64 cast is not reliably milliseconds (see production code
    # comment in bybit_data_fetcher.py for the same issue).
    ts_ms = (
        (pd.to_datetime(df["timestamp"]) - pd.Timestamp("1970-01-01"))
        // pd.Timedelta(milliseconds=1)
    ).tolist()
    assert len(df) == 5
    assert forming_start not in ts_ms
    assert set(ts_ms) == set(closed_starts)


def test_legacy_schema_unchanged(tmp_path):
    now_ms = int(time.time() * 1000)
    f = FakeFetcher([_mk_rows(48, now_ms - 48 * 3600 * 1000), []])
    out = tmp_path / "legacy.csv"
    asyncio.run(
        f.download_historical_data(
            "BTCUSDT", interval="60", days=2, output_file=str(out)
        )
    )
    df = pd.read_csv(out)
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]


def test_assert_connector_live_rejects_stale():
    """Newest candle older than 3 intervals => tape mode / frozen data => RuntimeError."""
    stale_ms = int(time.time() * 1000) - 10 * 3600 * 1000
    f = FakeFetcher([_mk_rows(5, stale_ms)])
    with pytest.raises(RuntimeError, match="stale"):
        asyncio.run(bdf.assert_connector_live(f, symbol="BTCUSDT", interval="60"))


def test_assert_connector_live_accepts_fresh():
    fresh_ms = int(time.time() * 1000) - 2 * 3600 * 1000
    f = FakeFetcher([_mk_rows(5, fresh_ms)])
    asyncio.run(bdf.assert_connector_live(f, symbol="BTCUSDT", interval="60"))
