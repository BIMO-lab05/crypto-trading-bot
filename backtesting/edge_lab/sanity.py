"""Gate 0 - data sanity checks over raw klines and funding history.

Screens candidate-input data before any strategy touches it: gap/duplicate/
monotonicity/price-validity checks on OHLC bars, and coverage checks on
funding settlements. Klines defects are battery-stoppers (ok=False); missing
funding is not — it surfaces via funding_ok/funding_n so screen.py's caller
can route the symbol to an EXCLUDES marker instead of silently dropping it.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from edge_lab.fetch import interval_ms

OHLC_COLS = ["open", "high", "low", "close"]
FUNDING_INTERVALS_PER_DAY = 3  # 8h cadence


@dataclass
class SanityReport:
    symbol: str
    interval: str
    ok: bool
    n_bars: int
    first_ts_ms: int
    last_ts_ms: int
    gaps: list[tuple[int, int]]
    defects: list[str]
    funding_ok: bool = False
    funding_n: int = 0


def check_klines(df: pd.DataFrame, symbol: str, interval: str) -> SanityReport:
    """Gate 0 kline check. Records every gap > 1 interval; flags a defect
    only for gaps > 2 intervals (a single missing bar is tolerated)."""
    iv_ms = interval_ms(interval)
    defects: list[str] = []

    n_bars = len(df)
    ts_vals = df["ts_ms"].to_numpy()
    first_ts_ms = int(ts_vals[0]) if n_bars else 0
    last_ts_ms = int(ts_vals[-1]) if n_bars else 0

    if n_bars == 0:
        defects.append("no bars")

    ts = df["ts_ms"]
    if not ts.is_monotonic_increasing:
        defects.append("ts_ms not monotonic")

    n_dup = int(ts.duplicated().sum())
    if n_dup:
        defects.append(f"{n_dup} duplicate ts_ms value(s)")

    ohlc = df[OHLC_COLS]
    if (ohlc <= 0).any().any():
        defects.append("non-positive OHLC value")
    if ohlc.isna().any().any():
        defects.append("NaN in OHLC")
    if (df["high"] < df["low"]).any():
        defects.append("high < low on at least one bar")

    gaps: list[tuple[int, int]] = []
    n_big_gaps = 0
    for i in range(1, len(ts_vals)):
        diff = ts_vals[i] - ts_vals[i - 1]
        if diff > iv_ms:
            gaps.append((int(ts_vals[i - 1]), int(ts_vals[i])))
            if diff > 2 * iv_ms:
                n_big_gaps += 1
    if n_big_gaps:
        defects.append(f"{n_big_gaps} gap(s) exceeding 2x interval")

    return SanityReport(
        symbol=symbol,
        interval=interval,
        ok=not defects,
        n_bars=n_bars,
        first_ts_ms=first_ts_ms,
        last_ts_ms=last_ts_ms,
        gaps=gaps,
        defects=defects,
    )


def check_funding(df: pd.DataFrame, days_expected: int) -> tuple[bool, int]:
    """funding_ok is False when the series is empty or covers < 50% of the
    settlements expected at 8h cadence over days_expected. Not a
    battery-stopper on its own - the caller routes it to an EXCLUDES marker."""
    expected = days_expected * FUNDING_INTERVALS_PER_DAY
    n = len(df)
    ok = n > 0 and n >= 0.5 * expected
    return ok, n


def render_sanity_table(reports: list[SanityReport]) -> str:
    """One line per report. Every dropped symbol and every defect string is
    named - no silent shrinkage."""
    lines = []
    for r in reports:
        status = "PASS" if r.ok else "FAIL"
        line = (
            f"{r.symbol} [{r.interval}] {status} n_bars={r.n_bars} "
            f"gaps={len(r.gaps)} funding_ok={r.funding_ok} funding_n={r.funding_n}"
        )
        if r.defects:
            line += " | defects: " + "; ".join(r.defects)
        lines.append(line)
    return "\n".join(lines)
