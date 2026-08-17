"""Sync public Bybit v5 client + kline/funding fetchers with a file cache.

No auth — public market-data endpoints only (tickers, instruments-info,
kline, funding/history). Distinct from the async, auth-capable connector at
services/bybit-connector/app/bybit_rest_client.py; this one is host-run,
synchronous, and disposable per edge-lab run.

api.bybit.com IS mainnet by construction (no testnet toggle here), so
ensure_klines stamps is_mainnet=True on every row it writes — see
CLAUDE.md gotcha on the 2026-04-25 testnet/mainnet TimescaleDB split, which
does not apply to data fetched through this path.
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx
import pandas as pd

DAY = 86_400_000
MAX_INSTRUMENTS_PAGES = 10


class FetchError(RuntimeError):
    pass


def interval_ms(interval: str) -> int:
    return DAY if interval == "D" else int(interval) * 60_000


class BybitPublic:
    def __init__(
        self,
        base_url: str = "https://api.bybit.com",
        client: httpx.Client | None = None,
        sleep_s: float = 0.2,
    ):
        self._client = client or httpx.Client(base_url=base_url, timeout=30.0)
        self._sleep_s = sleep_s

    def get(self, path: str, params: dict) -> dict:
        last = None
        for attempt in range(3):
            try:
                resp = self._client.get(path, params=params)
                resp.raise_for_status()
                data = resp.json()
                if data.get("retCode") != 0:
                    raise FetchError(
                        f"{path} retCode={data.get('retCode')} "
                        f"retMsg={data.get('retMsg')}"
                    )
                return data.get("result", {})
            except (httpx.TimeoutException, httpx.TransportError, FetchError) as e:
                if isinstance(e, FetchError) and "retCode" in str(e):
                    raise  # API rejected the request: don't retry
                last = e
                time.sleep(2**attempt)  # 1, 2, 4
        raise FetchError(f"{path} failed after 3 attempts: {last}")

    def tickers(self) -> list[dict]:
        result = self.get("/v5/market/tickers", {"category": "linear"})
        return result.get("list", [])

    def instruments(self) -> list[dict]:
        """10-page cap, cursor loop — pattern verbatim from
        bybit_rest_client.py:712-750."""
        params = {"category": "linear", "limit": 1000}
        out: list[dict] = []
        cursor = None
        for _page in range(MAX_INSTRUMENTS_PAGES):
            # Fresh per-page copy: get() (and the mock transport in tests)
            # retains a reference to the dict it was handed, so mutating one
            # shared dict in place would corrupt the recorded first-page params.
            params_page = dict(params)
            if cursor:
                params_page["cursor"] = cursor
            result = self.get("/v5/market/instruments-info", params_page)
            out.extend(result.get("list") or [])
            cursor = result.get("nextPageCursor") or None
            if not cursor:
                break
        return out

    def fetch_klines(
        self, symbol: str, interval: str, days: int, now_ms: int
    ) -> pd.DataFrame:
        """Backward pagination from now_ms. l18-correct loop: break only on an
        empty batch or oldest_ts <= target_start — a short batch (e.g. 999
        rows, forming bar already dropped upstream) is NOT end-of-history."""
        iv_ms = interval_ms(interval)
        target_start = now_ms - days * DAY
        current_end = now_ms
        max_batches = days * DAY // (1000 * iv_ms) + 10
        rows: list[list] = []
        batch = 0
        while batch < max_batches:
            batch += 1
            params = {
                "category": "linear",
                "symbol": symbol,
                "interval": interval,
                "start": target_start,
                "end": current_end,
                "limit": 1000,
            }
            result = self.get("/v5/market/kline", params)
            page = result.get("list") or []
            if not page:
                break
            rows.extend(page)
            oldest = min(int(r[0]) for r in page)
            if oldest <= target_start:
                break
            current_end = oldest - 1
            time.sleep(self._sleep_s)

        cols = ["ts_ms", "open", "high", "low", "close", "volume", "turnover"]
        if not rows:
            return pd.DataFrame(columns=cols)

        dedup: dict[int, list] = {int(r[0]): r for r in rows}
        ts_sorted = sorted(dedup)
        df = pd.DataFrame(
            [
                {
                    "ts_ms": ts,
                    "open": float(dedup[ts][1]),
                    "high": float(dedup[ts][2]),
                    "low": float(dedup[ts][3]),
                    "close": float(dedup[ts][4]),
                    "volume": float(dedup[ts][5]),
                    "turnover": float(dedup[ts][6]),
                }
                for ts in ts_sorted
            ],
            columns=cols,
        )
        df["ts_ms"] = df["ts_ms"].astype("int64")
        # Drop the still-forming bar: its close time hasn't happened yet.
        df = df[df["ts_ms"] + iv_ms <= now_ms].reset_index(drop=True)
        return df

    def fetch_funding(self, symbol: str, days: int, now_ms: int) -> pd.DataFrame:
        """endTime walk backward, no cursor. Empty result for the whole
        window returns an empty DataFrame — never fabricate a rate."""
        target_start = now_ms - days * DAY
        current_end = now_ms
        # No a-priori funding interval to size max_batches off (varies by
        # symbol); bound generously assuming a 1h floor rather than the
        # 8h default, then let the empty-batch/window-covered breaks do
        # the real work.
        max_batches = days * DAY // (200 * 3_600_000) + 10
        rows: list[dict] = []
        batch = 0
        while batch < max_batches:
            batch += 1
            params = {
                "category": "linear",
                "symbol": symbol,
                "startTime": target_start,
                "endTime": current_end,
                "limit": 200,
            }
            result = self.get("/v5/market/funding/history", params)
            page = result.get("list") or []
            if not page:
                break
            rows.extend(page)
            oldest = min(int(r["fundingRateTimestamp"]) for r in page)
            if oldest <= target_start:
                break
            current_end = oldest - 1
            time.sleep(self._sleep_s)

        if not rows:
            return pd.DataFrame(columns=["ts_ms", "funding_rate"])

        dedup: dict[int, str] = {
            int(r["fundingRateTimestamp"]): r["fundingRate"] for r in rows
        }
        ts_sorted = sorted(dedup)
        df = pd.DataFrame(
            {"ts_ms": ts_sorted, "funding_rate": [dedup[t] for t in ts_sorted]}
        )
        df["ts_ms"] = df["ts_ms"].astype("int64")
        return df


def kline_csv_path(data_dir: Path, symbol: str, interval: str, days: int) -> Path:
    """Killtest naming convention: interval "D" maps to "1440"."""
    iv = "1440" if interval == "D" else interval
    return Path(data_dir) / f"{symbol}_{iv}m_{days}d_bybit.csv"


def funding_csv_path(data_dir: Path, symbol: str) -> Path:
    """What costs_loader.load_funding reads."""
    return Path(data_dir) / "funding" / f"{symbol}_funding.csv"


def ensure_klines(
    client: BybitPublic,
    data_dir: Path,
    symbol: str,
    interval: str,
    days: int,
    now_ms: int,
) -> Path:
    """Fetch + write once; resume-from-cache is file granularity."""
    path = kline_csv_path(data_dir, symbol, interval, days)
    if path.is_file():
        return path
    df = client.fetch_klines(symbol, interval, days, now_ms)
    out = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(df["ts_ms"], unit="ms"),
            "symbol": symbol,
            "interval": interval,
            "open": df["open"],
            "high": df["high"],
            "low": df["low"],
            "close": df["close"],
            "volume": df["volume"],
            "turnover": df["turnover"],
            "is_mainnet": True,  # api.bybit.com IS mainnet by construction
            "created_at": now_ms,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
    return path


def ensure_funding(
    client: BybitPublic, data_dir: Path, symbol: str, days: int, now_ms: int
) -> Path:
    """Fetch + write once; resume-from-cache is file granularity."""
    path = funding_csv_path(data_dir, symbol)
    if path.is_file():
        return path
    df = client.fetch_funding(symbol, days, now_ms)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path
