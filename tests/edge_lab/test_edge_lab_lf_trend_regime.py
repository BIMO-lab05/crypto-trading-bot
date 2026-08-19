import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from conftest import DAY, T0, assert_shift_invariant  # noqa: E402
from edge_lab.candidates.lf_trend import (  # noqa: E402
    _REGIME_VARIANTS,
    _regime_symbol_trades,
    VARIANTS,
    generate_trades,
)

REGIME_NAMES = ["trend_atr_high_20d", "trend_vol_spike_20d", "trend_vix_analog_10d"]


def _regime_variant(name):
    return next(v for v in VARIANTS if v.name == name)


def test_regime_variants_declared():
    names = [v.name for v in VARIANTS]
    for name in REGIME_NAMES:
        assert name in names


def _volatile_trending_universe():
    """Two symbols, 700 daily bars: one alternates quiet ranging with sharp
    volatility-and-trend bursts (regime metrics should clear the entry
    percentile mainly during the bursts), the other stays quiet throughout.
    700 bars comfortably covers every variant's longest lookback
    (trend_vol_spike_20d's 252-day entry percentile window) with room for
    several bursts afterward.
    """
    rng = np.random.default_rng(7)
    n = 700

    rets = rng.normal(0.0, 0.003, n)
    for start in (280, 350, 420, 490, 560, 630):
        rets[start : start + 15] = rng.normal(0.02, 0.01, 15)
    close_a = 100.0 * np.cumprod(1 + rets)
    open_a = np.concatenate([[100.0], close_a[:-1]])
    high_a = np.maximum(open_a, close_a) * (1 + np.abs(rets) * 2 + 0.001)
    low_a = np.minimum(open_a, close_a) * (1 - np.abs(rets) * 2 - 0.001)

    quiet = rng.normal(0.0, 0.002, n)
    close_b = 100.0 * np.cumprod(1 + quiet)
    open_b = np.concatenate([[100.0], close_b[:-1]])
    high_b = np.maximum(open_b, close_b) * 1.003
    low_b = np.minimum(open_b, close_b) * 0.997

    ts = [T0 + i * DAY for i in range(n)]

    def frame(open_, high, low, close):
        return pd.DataFrame(
            {
                "ts_ms": ts,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": np.full(n, 1000.0),
            }
        )

    return {
        "AUSDT": frame(open_a, high_a, low_a, close_a),
        "BUSDT": frame(open_b, high_b, low_b, close_b),
    }


def test_shift_invariance_all_regime_variants():
    data = _volatile_trending_universe()
    for name in REGIME_NAMES:
        variant = _regime_variant(name)
        assert_shift_invariant(generate_trades, data, variant, T0 + 660 * DAY)


def test_regime_filter_reduces_trade_count():
    """Compare each gated variant against its own ablation — the identical
    entry signal, exit rule, and metrics, but with the entry percentile
    gate forced open (entry_q=0.0, i.e. "clear the 0th percentile", which
    is true of every value in the trailing window except an exact tie with
    its min). Same dynamics everywhere except whether the regime gate can
    veto an entry, so the ablation's trade count is a valid "ungated"
    baseline for this variant's own exit logic — unlike comparing against
    dc_20_10, whose different exit rule (its own Donchian exit band) makes
    trade counts incomparable by construction.
    """
    data = _volatile_trending_universe()
    for name in REGIME_NAMES:
        cfg = _REGIME_VARIANTS[name]
        ablated_cfg = {**cfg, "entry_q": 0.0}

        gated_count = 0
        ablated_count = 0
        for symbol, df in data.items():
            gated_count += len(_regime_symbol_trades(symbol, df, cfg))
            ablated_count += len(_regime_symbol_trades(symbol, df, ablated_cfg))

        assert ablated_count > 0, (
            f"{name}: ablated (gate forced open) baseline produced no trades — "
            "fixture does not exercise this variant's breakout/exit signal"
        )
        assert gated_count < ablated_count, (
            f"{name} produced {gated_count} trades gated vs {ablated_count} with "
            "the entry gate forced open — a regime gate that does not cut trade "
            "count relative to its own ungated baseline is not filtering anything"
        )


def test_regime_variant_no_open_position_at_end():
    data = _volatile_trending_universe()
    for name in REGIME_NAMES:
        trades = generate_trades(data, _regime_variant(name))
        for sym, df in data.items():
            last_ts = df["ts_ms"].iloc[-1]
            for t in trades:
                if t.symbol == sym:
                    assert t.exit_ts_ms <= last_ts
