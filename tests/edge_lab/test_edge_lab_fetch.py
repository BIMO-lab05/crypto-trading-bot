"""Fetcher pagination + cache tests against httpx.MockTransport. No network."""
import sys
from pathlib import Path

import httpx
import pandas as pd  # noqa: F401

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from edge_lab.fetch import (  # noqa: E402, F401
    BybitPublic, ensure_funding, ensure_klines, funding_csv_path,
    interval_ms, kline_csv_path,
)

DAY = 86_400_000
NOW = 1_800_000_000_000


def _kline_rows(start_ms, n, step_ms):
    # Bybit shape: newest-first [ts, o, h, l, c, vol, turnover] strings
    rows = [[str(start_ms + i * step_ms), "100", "101", "99", "100.5", "10", "1000"]
            for i in range(n)]
    return list(reversed(rows))


def _mock(handler):
    return BybitPublic(client=httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://api.bybit.com"),
        sleep_s=0.0)


def test_kline_pagination_stitches_multiple_pages():
    """3000 daily bars must come back complete across 3 pages."""
    total = 3000
    step = DAY
    t0 = NOW - total * step
    calls = []

    def handler(request):
        params = dict(request.url.params)
        calls.append(params)
        start, end = int(params["start"]), int(params["end"])
        rows = [[str(ts), "1", "1", "1", "1", "1", "1"]
                for ts in range(t0, NOW, step) if start <= ts <= end]
        rows = sorted(rows, key=lambda r: -int(r[0]))[:1000]
        return httpx.Response(200, json={"retCode": 0, "result": {"list": rows}})

    df = _mock(handler).fetch_klines("BTCUSDT", "D", days=total, now_ms=NOW)
    assert len(df) >= total - 1                    # forming-bar drop allowed
    assert df["ts_ms"].is_monotonic_increasing
    assert df["ts_ms"].duplicated().sum() == 0
    assert len(calls) >= 3


def test_short_batch_is_not_end_of_history():
    """999-row page (forming bar dropped upstream) must NOT stop the loop.
    Regression on the 260816-l18 gotcha."""
    step = DAY
    t0 = NOW - 1500 * step
    pages = []

    def handler(request):
        params = dict(request.url.params)
        start, end = int(params["start"]), int(params["end"])
        rows = [[str(ts), "1", "1", "1", "1", "1", "1"]
                for ts in range(t0, NOW, step) if start <= ts <= end]
        rows = sorted(rows, key=lambda r: -int(r[0]))[:999]   # always short
        pages.append(len(rows))
        return httpx.Response(200, json={"retCode": 0, "result": {"list": rows}})

    df = _mock(handler).fetch_klines("BTCUSDT", "D", days=1500, now_ms=NOW)
    assert len(df) >= 1499
    assert len(pages) >= 2                          # kept paginating past a short page


def test_funding_walks_end_time_backward():
    """700 settlements, 200/page, no cursor — endTime walk must fetch all."""
    step = 8 * 3_600_000
    n = 700
    t0 = NOW - n * step

    def handler(request):
        assert request.url.path == "/v5/market/funding/history"
        params = dict(request.url.params)
        start, end = int(params["startTime"]), int(params["endTime"])
        rows = [{"symbol": "BTCUSDT", "fundingRate": "0.0001",
                 "fundingRateTimestamp": str(ts)}
                for ts in range(t0, NOW, step) if start <= ts <= end]
        rows = sorted(rows, key=lambda r: -int(r["fundingRateTimestamp"]))[:200]
        return httpx.Response(200, json={"retCode": 0, "result": {"list": rows}})

    df = _mock(handler).fetch_funding("BTCUSDT", days=n * step // DAY + 1, now_ms=NOW)
    assert len(df) == n
    assert df["ts_ms"].is_monotonic_increasing


def test_retcode_error_raises():
    def handler(request):
        return httpx.Response(200, json={"retCode": 10001, "retMsg": "bad param"})
    try:
        _mock(handler).tickers()
        assert False, "should have raised"
    except Exception as e:
        assert "10001" in str(e)


def test_ensure_klines_skips_when_cached(tmp_path):
    hits = []

    def handler(request):
        hits.append(1)
        return httpx.Response(200, json={"retCode": 0, "result": {"list": [
            [str(NOW - 2 * DAY), "1", "1", "1", "1", "1", "1"]]}})

    c = _mock(handler)
    p1 = ensure_klines(c, tmp_path, "BTCUSDT", "D", 5, NOW)
    n_calls = len(hits)
    p2 = ensure_klines(c, tmp_path, "BTCUSDT", "D", 5, NOW)
    assert p1 == p2 and len(hits) == n_calls        # second call: zero fetches
    assert p1.name == "BTCUSDT_1440m_5d_bybit.csv"  # killtest naming, D->1440
    header = p1.read_text().splitlines()[0]
    assert header == ("timestamp,symbol,interval,open,high,low,close,"
                      "volume,turnover,is_mainnet,created_at")


def test_funding_csv_matches_costs_loader_contract(tmp_path):
    def handler(request):
        return httpx.Response(200, json={"retCode": 0, "result": {"list": [
            {"symbol": "BTCUSDT", "fundingRate": "0.0001",
             "fundingRateTimestamp": str(NOW - DAY)}]}})

    p = ensure_funding(_mock(handler), tmp_path, "BTCUSDT", 5, NOW)
    assert p == funding_csv_path(tmp_path, "BTCUSDT")
    from costs_loader import load_funding  # noqa: E402
    series = load_funding("BTCUSDT", str(tmp_path / "funding"))
    assert len(series) == 1 and series[0].ts_ms == NOW - DAY


def test_interval_ms():
    assert interval_ms("D") == DAY and interval_ms("240") == 4 * 3_600_000
