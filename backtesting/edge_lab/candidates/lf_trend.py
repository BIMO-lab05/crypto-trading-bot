"""Candidate 3 — low-frequency Donchian breakout trend.

Per symbol independently, a single-position (flat/long/short) breakout
system driven by Task 2's `donchian()` channel (already causal — the
channel value at bar t is computed from bars strictly before t). A
signal read off bar t's close only ever fills at bar t+1's open, so a
signal never fills on the bar that produced it.

LONG entry: close[t] > dc_entry_high[t]. LONG exit: close[t] < dc_exit_low[t].
SHORT is the mirror: enter on close[t] < dc_entry_low[t], exit on
close[t] > dc_exit_high[t]. One position per symbol. An exit signal for
the open side plus an opposite-side entry signal on the same bar
stop-and-reverse: the old leg closes and the new leg opens at the same
t+1 open. A position still open when the data ends is discarded — only
completed round trips are emitted.

Regime-gated variants (battery #2, Candidate Family #3 in
battery_2026-08-18_manifest.md) reuse the plain dc_20_10 breakout as the
"fixed underlying trend signal" and add a causal regime filter on entry:
a breakout only fires if a volatility/range metric at bar t exceeds a
percentile computed from the metric's own trailing history (bars
strictly before t, via `.shift(1).rolling(...)` — the same causal shape
`donchian()` already uses). Exit rules are variant-specific and either
close-vs-MA or opposite-breakout ("reversal"), each OR'd with the metric
dropping back below a lower percentile.

**Prior is deliberately low, and stated here rather than assumed away:**
lf_trend's Gate 1 pass (ratios 4.85 and 15.511) came from a handful of
outliers, not a distribution — pooled PF was about 1.0 at Gate 2. A
regime filter that merely removes losing periods in-sample is
overfitting; that is exactly what the DSR is for. These variants are
expected to fail Gate 2; running them is how we find that out cheaply,
not a bet that they will pass.
"""

from __future__ import annotations

import pandas as pd

from edge_lab.indicators import atr, donchian, sma
from edge_lab.trades import Trade, Variant

_CHANNELS = ((20, 10), (55, 20))

VARIANTS: list[Variant] = [
    Variant(
        candidate="lf_trend",
        name=f"dc_{entry_n}_{exit_n}",
        params=(("entry_n", entry_n), ("exit_n", exit_n)),
    )
    for entry_n, exit_n in _CHANNELS
]

# Underlying trend signal for the regime-gated variants: the dc_20_10
# breakout, the better of the two battery #1 performers (ratio 15.511).
# Only the entry side is reused — exits are variant-specific below.
_REGIME_ENTRY_N = 20

# Per-variant config, verbatim from the manifest's Candidate Family #3 table.
# `exit_kind`:
#   "ma_or_metric"      — exit on close crossing the `ma_n`-day MA, or the
#                          exit metric dropping below its exit percentile.
#   "reversal_or_metric" — exit on the opposite raw breakout signal
#                          ("reversal"), or the exit metric dropping below
#                          its exit percentile.
# Exit-side percentile windows/thresholds not spelled out verbatim in the
# manifest (trend_vol_spike_20d's exit metric switches to ATR per its own
# "Holding Period" cell; trend_vix_analog_10d's "range contracts" has no
# stated number) are filled in following the pattern set by the other two
# rows (entry pctile paired with a materially lower exit pctile over the
# same window) — a documented assumption, not a manifest quote.
_REGIME_VARIANTS = {
    "trend_atr_high_20d": dict(
        entry_metric="atr20",
        entry_window=100,
        entry_q=0.70,
        exit_kind="ma_or_metric",
        ma_n=50,
        exit_metric="atr20",
        exit_window=100,
        exit_q=0.30,
    ),
    "trend_vol_spike_20d": dict(
        entry_metric="vol20",
        entry_window=252,
        entry_q=0.75,
        exit_kind="reversal_or_metric",
        exit_metric="atr20",  # manifest: exit condition is stated in ATR, not vol
        exit_window=100,
        exit_q=0.20,
    ),
    "trend_vix_analog_10d": dict(
        entry_metric="range10",
        entry_window=60,
        entry_q=0.80,
        exit_kind="reversal_or_metric",
        exit_metric="range10",
        exit_window=60,
        exit_q=0.20,  # assumption: manifest gives no exit number for this row
    ),
}

VARIANTS.extend(
    Variant(
        candidate="lf_trend",
        name=name,
        params=tuple(sorted(cfg.items())),
    )
    for name, cfg in _REGIME_VARIANTS.items()
)


def _pctile_threshold(metric: pd.Series, window: int, q: float) -> pd.Series:
    """Percentile of the metric's trailing history, strictly before bar t."""
    return metric.shift(1).rolling(window, min_periods=window).quantile(q)


def _compute_metrics(df: pd.DataFrame) -> dict[str, pd.Series]:
    atr20 = atr(df, 20)
    vol20 = df["close"].pct_change().rolling(20, min_periods=20).std()
    range10 = (
        df["high"].rolling(10, min_periods=10).max()
        - df["low"].rolling(10, min_periods=10).min()
    ) / df["close"]
    return {"atr20": atr20, "vol20": vol20, "range10": range10}


def _symbol_trades(
    symbol: str, df: pd.DataFrame, entry_n: int, exit_n: int
) -> list[Trade]:
    ordered = df.sort_values("ts_ms").reset_index(drop=True)
    dc = donchian(ordered, entry_n, exit_n)

    ts = ordered["ts_ms"].tolist()
    open_ = ordered["open"].tolist()
    close = ordered["close"].tolist()
    entry_high = dc["dc_entry_high"].tolist()
    entry_low = dc["dc_entry_low"].tolist()
    exit_high = dc["dc_exit_high"].tolist()
    exit_low = dc["dc_exit_low"].tolist()

    trades: list[Trade] = []
    side: str | None = None  # None | "LONG" | "SHORT"
    entry_idx: int | None = None

    n = len(ordered)
    for t in range(n - 1):  # bar t+1 must exist to fill a signal from bar t
        c = close[t]
        long_entry = not pd.isna(entry_high[t]) and c > entry_high[t]
        long_exit = not pd.isna(exit_low[t]) and c < exit_low[t]
        short_entry = not pd.isna(entry_low[t]) and c < entry_low[t]
        short_exit = not pd.isna(exit_high[t]) and c > exit_high[t]

        fill_idx = t + 1

        if side is None:
            if long_entry:
                side, entry_idx = "LONG", fill_idx
            elif short_entry:
                side, entry_idx = "SHORT", fill_idx
        elif side == "LONG":
            if short_entry:  # exit + opposite entry same bar: stop-and-reverse
                trades.append(
                    Trade(
                        symbol=symbol,
                        side="LONG",
                        entry_ts_ms=ts[entry_idx],
                        exit_ts_ms=ts[fill_idx],
                        entry_px=open_[entry_idx],
                        exit_px=open_[fill_idx],
                    )
                )
                side, entry_idx = "SHORT", fill_idx
            elif long_exit:
                trades.append(
                    Trade(
                        symbol=symbol,
                        side="LONG",
                        entry_ts_ms=ts[entry_idx],
                        exit_ts_ms=ts[fill_idx],
                        entry_px=open_[entry_idx],
                        exit_px=open_[fill_idx],
                    )
                )
                side, entry_idx = None, None
        elif side == "SHORT":
            if long_entry:  # exit + opposite entry same bar: stop-and-reverse
                trades.append(
                    Trade(
                        symbol=symbol,
                        side="SHORT",
                        entry_ts_ms=ts[entry_idx],
                        exit_ts_ms=ts[fill_idx],
                        entry_px=open_[entry_idx],
                        exit_px=open_[fill_idx],
                    )
                )
                side, entry_idx = "LONG", fill_idx
            elif short_exit:
                trades.append(
                    Trade(
                        symbol=symbol,
                        side="SHORT",
                        entry_ts_ms=ts[entry_idx],
                        exit_ts_ms=ts[fill_idx],
                        entry_px=open_[entry_idx],
                        exit_px=open_[fill_idx],
                    )
                )
                side, entry_idx = None, None

    return trades


def _regime_symbol_trades(symbol: str, df: pd.DataFrame, cfg: dict) -> list[Trade]:
    ordered = df.sort_values("ts_ms").reset_index(drop=True)
    dc = donchian(ordered, _REGIME_ENTRY_N, _REGIME_ENTRY_N)
    metrics = _compute_metrics(ordered)

    entry_metric = metrics[cfg["entry_metric"]]
    entry_threshold = _pctile_threshold(
        entry_metric, cfg["entry_window"], cfg["entry_q"]
    )
    gate = (entry_metric > entry_threshold).fillna(False)

    exit_metric = metrics[cfg["exit_metric"]]
    exit_threshold = _pctile_threshold(exit_metric, cfg["exit_window"], cfg["exit_q"])
    metric_below_exit = (exit_metric < exit_threshold).fillna(False)

    if cfg["exit_kind"] == "ma_or_metric":
        ma = sma(ordered["close"], cfg["ma_n"])

    ts = ordered["ts_ms"].tolist()
    open_ = ordered["open"].tolist()
    close = ordered["close"].tolist()
    entry_high = dc["dc_entry_high"].tolist()
    entry_low = dc["dc_entry_low"].tolist()
    gate_l = gate.tolist()
    metric_below_exit_l = metric_below_exit.tolist()

    trades: list[Trade] = []
    side: str | None = None
    entry_idx: int | None = None

    n = len(ordered)
    for t in range(n - 1):  # bar t+1 must exist to fill a signal from bar t
        c = close[t]
        raw_long_entry = not pd.isna(entry_high[t]) and c > entry_high[t]
        raw_short_entry = not pd.isna(entry_low[t]) and c < entry_low[t]
        gated_long_entry = raw_long_entry and gate_l[t]
        gated_short_entry = raw_short_entry and gate_l[t]

        if cfg["exit_kind"] == "ma_or_metric":
            m = ma.iloc[t]
            long_exit = (not pd.isna(m) and c < m) or metric_below_exit_l[t]
            short_exit = (not pd.isna(m) and c > m) or metric_below_exit_l[t]
        else:  # reversal_or_metric
            long_exit = raw_short_entry or metric_below_exit_l[t]
            short_exit = raw_long_entry or metric_below_exit_l[t]

        fill_idx = t + 1

        if side is None:
            if gated_long_entry:
                side, entry_idx = "LONG", fill_idx
            elif gated_short_entry:
                side, entry_idx = "SHORT", fill_idx
        elif side == "LONG":
            if gated_short_entry:  # reversal that itself clears the regime gate
                trades.append(
                    Trade(
                        symbol=symbol,
                        side="LONG",
                        entry_ts_ms=ts[entry_idx],
                        exit_ts_ms=ts[fill_idx],
                        entry_px=open_[entry_idx],
                        exit_px=open_[fill_idx],
                    )
                )
                side, entry_idx = "SHORT", fill_idx
            elif long_exit:
                trades.append(
                    Trade(
                        symbol=symbol,
                        side="LONG",
                        entry_ts_ms=ts[entry_idx],
                        exit_ts_ms=ts[fill_idx],
                        entry_px=open_[entry_idx],
                        exit_px=open_[fill_idx],
                    )
                )
                side, entry_idx = None, None
        elif side == "SHORT":
            if gated_long_entry:  # reversal that itself clears the regime gate
                trades.append(
                    Trade(
                        symbol=symbol,
                        side="SHORT",
                        entry_ts_ms=ts[entry_idx],
                        exit_ts_ms=ts[fill_idx],
                        entry_px=open_[entry_idx],
                        exit_px=open_[fill_idx],
                    )
                )
                side, entry_idx = "LONG", fill_idx
            elif short_exit:
                trades.append(
                    Trade(
                        symbol=symbol,
                        side="SHORT",
                        entry_ts_ms=ts[entry_idx],
                        exit_ts_ms=ts[fill_idx],
                        entry_px=open_[entry_idx],
                        exit_px=open_[fill_idx],
                    )
                )
                side, entry_idx = None, None

    return trades


def generate_trades(daily: dict[str, pd.DataFrame], variant: Variant) -> list[Trade]:
    if variant.name in _REGIME_VARIANTS:
        cfg = _REGIME_VARIANTS[variant.name]
        trades: list[Trade] = []
        for symbol, df in daily.items():
            trades.extend(_regime_symbol_trades(symbol, df, cfg))
        return trades

    params = dict(variant.params)
    entry_n, exit_n = params["entry_n"], params["exit_n"]

    trades = []
    for symbol, df in daily.items():
        trades.extend(_symbol_trades(symbol, df, entry_n, exit_n))
    return trades
