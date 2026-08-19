"""Shared fixtures: synthetic multi-symbol daily data + shift-invariance check."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

DAY = 86_400_000
# 2023-01-02 00:00 UTC — a Monday, so rebalance days align deterministically
T0 = 1_672_617_600_000


def make_daily(symbols, n_days=400, seed=11, drifts=None):
    rng = np.random.default_rng(seed)
    out = {}
    for i, sym in enumerate(symbols):
        drift = (drifts or {}).get(sym, 0.0)
        rets = rng.normal(drift, 0.02, n_days)
        close = 100.0 * np.cumprod(1 + rets)
        open_ = np.concatenate([[100.0], close[:-1]])
        out[sym] = pd.DataFrame(
            {
                "ts_ms": [T0 + k * DAY for k in range(n_days)],
                "open": open_,
                "high": np.maximum(open_, close) * 1.005,
                "low": np.minimum(open_, close) * 0.995,
                "close": close,
                "volume": np.full(n_days, 1000.0),
            }
        )
    return out


@pytest.fixture
def universe12():
    syms = [f"S{i:02d}USDT" for i in range(12)]
    drifts = {
        s: 0.004 if i < 3 else (-0.004 if i >= 9 else 0.0) for i, s in enumerate(syms)
    }
    return make_daily(syms, drifts=drifts)


def assert_shift_invariant(gen_fn, data, variant, cut_ts_ms, allow_empty=False):
    """Truncating history after `cut_ts_ms` must not change trades already closed.

    Guarded against passing vacuously: a generator that emits no trade closing
    at or before the cut compares an empty set to an empty set, which no
    look-ahead bug could ever fail. Callers that legitimately expect that must
    say so with `allow_empty=True` rather than get a silent green.
    """
    full = gen_fn(data, variant)
    trunc_data = {
        s: df[df["ts_ms"] <= cut_ts_ms].reset_index(drop=True) for s, df in data.items()
    }
    trunc = gen_fn(trunc_data, variant)
    key = lambda t: (
        t.symbol,
        t.side,
        t.entry_ts_ms,
        t.exit_ts_ms,
        round(t.entry_px, 10),
        round(t.exit_px, 10),
    )
    full_closed = {key(t) for t in full if t.exit_ts_ms <= cut_ts_ms}
    trunc_closed = {key(t) for t in trunc if t.exit_ts_ms <= cut_ts_ms}
    assert full_closed or allow_empty, (
        "vacuous shift-invariance check: the full-history run closed no trade "
        f"at or before cut_ts_ms={cut_ts_ms}, so this compares empty to empty "
        "and cannot fail. Move the cut, or pass allow_empty=True if that is "
        "genuinely the case under test."
    )
    assert full_closed == trunc_closed, (
        f"future data changed past trades: only-full={full_closed - trunc_closed} "
        f"only-trunc={trunc_closed - full_closed}"
    )
