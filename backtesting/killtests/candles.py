"""Validated candle store over backfilled 11-col kline CSVs.

Hard-fail on any data-quality violation (spec §8): missing file, non-mainnet
rows, spacing gaps. As-of slicing serves only CLOSED bars (close <= now),
mirroring the live forming-candle drop in technical-analysis fetcher.py.
"""

import os

import pandas as pd

INTERVAL_MS = {"15": 900_000, "60": 3_600_000, "240": 14_400_000, "1440": 86_400_000}

_REQUIRED_COLS = {
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
}

_EPOCH = pd.Timestamp("1970-01-01")


class CandleValidationError(Exception):
    pass


class CandleStore:
    def __init__(self, data_dir: str, symbols: list, intervals: list):
        self._frames = {}
        for sym in symbols:
            for iv in intervals:
                path = os.path.join(data_dir, f"{sym}_{iv}m_365d_bybit.csv")
                if not os.path.exists(path):
                    raise CandleValidationError(f"missing candle file: {path}")
                self._frames[(sym, iv)] = self._load(path, sym, iv)

    @staticmethod
    def _load(path: str, sym: str, iv: str) -> pd.DataFrame:
        raw = pd.read_csv(path)
        missing = _REQUIRED_COLS - set(raw.columns)
        if missing:
            raise CandleValidationError(f"{path}: missing columns {sorted(missing)}")
        # HOW MUCH THIS GUARD IS WORTH — read before trusting it. The column
        # it checks is written by backtesting/bybit_data_fetcher.py, which
        # cannot observe which network it fetched from: bybit-connector picks
        # testnet vs mainnet from its own BYBIT_TESTNET env and exposes that
        # nowhere on its REST surface (only a startup log line,
        # bybit-connector/app/main.py:339,370). Until 2026-08-07 the fetcher
        # stamped True unconditionally, which made this check literally
        # unfalsifiable. It now refuses to write klines-schema CSVs unless the
        # operator passes --assert-mainnet, so a False row is at least
        # possible in principle — but the stamp is a human assertion, not a
        # proof. RESIDUAL GAP: an operator who asserts wrongly still poisons
        # the CSV and this guard still passes. Closing it needs the connector
        # to publish its testnet flag on /health.
        if not raw["is_mainnet"].astype(bool).all():
            raise CandleValidationError(f"{path}: contains is_mainnet=False rows")
        ts = pd.to_datetime(raw["timestamp"])
        if not ts.is_monotonic_increasing:
            raise CandleValidationError(f"{path}: timestamps not ascending")
        step_ms = INTERVAL_MS[iv]
        diffs = ts.diff().dropna().dt.total_seconds() * 1000
        bad = diffs[diffs != step_ms]
        if len(bad):
            first_bad = ts.iloc[bad.index[0]]
            raise CandleValidationError(
                f"{path}: {len(bad)} spacing gap(s)/duplicate(s); first at {first_bad}"
            )
        # pandas 3.x datetime64 columns are not guaranteed ns resolution (this
        # repo has seen [ms] and [us] depending on construction path), so
        # `.astype("int64")` returns whatever that resolution's raw integer
        # is -- NOT nanoseconds/microseconds/milliseconds consistently. Divide
        # by the resolution-independent Timedelta instead of assuming a unit.
        ts_ms = (ts - _EPOCH) // pd.Timedelta(milliseconds=1)
        out = pd.DataFrame(
            {
                "timestamp": ts,
                "ts_ms": ts_ms.astype("int64"),
                "open": raw["open"].astype(float),
                "high": raw["high"].astype(float),
                "low": raw["low"].astype(float),
                "close": raw["close"].astype(float),
                "volume": raw["volume"].astype(float),
            }
        )
        return out.reset_index(drop=True)

    def frame(self, symbol: str, interval: str) -> pd.DataFrame:
        return self._frames[(symbol, interval)]

    def as_of(self, symbol: str, interval: str, now_ms: int, limit: int) -> list:
        f = self._frames[(symbol, interval)]
        step = INTERVAL_MS[interval]
        closed = f[f["ts_ms"] + step <= now_ms].tail(limit)
        return [
            {
                "timestamp": int(r.ts_ms),
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
            }
            for r in closed.itertuples()
        ]

    def daily_window_before(self, symbol: str, date_ms: int, n: int) -> pd.DataFrame:
        f = self._frames[(symbol, "1440")]
        step = INTERVAL_MS["1440"]
        closed = f[f["ts_ms"] + step <= date_ms]
        if len(closed) < n:
            raise CandleValidationError(
                f"{symbol}: only {len(closed)} daily bars before "
                f"{pd.Timestamp(date_ms, unit='ms')}, need {n}"
            )
        return closed.tail(n).reset_index(drop=True)
