"""Known-value + causality tests for edge_lab indicators."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from edge_lab import indicators as ind  # noqa: E402


def _df(n=300, seed=7):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + rng.uniform(0.1, 1.0, n)
    low = close - rng.uniform(0.1, 1.0, n)
    return pd.DataFrame({"open": close, "high": high, "low": low, "close": close})


def test_sma_known_values():
    s = pd.Series([1.0, 2.0, 3.0, 4.0])
    out = ind.sma(s, 2)
    assert np.isnan(out.iloc[0])
    assert out.iloc[1] == 1.5 and out.iloc[3] == 3.5


def test_bollinger_symmetry():
    df = _df()
    bb = ind.bollinger(df["close"], 20, 2.0)
    mid_dev_up = (bb["bb_upper"] - bb["bb_mid"]).dropna()
    mid_dev_dn = (bb["bb_mid"] - bb["bb_lower"]).dropna()
    assert np.allclose(mid_dev_up, mid_dev_dn)


def test_donchian_excludes_current_bar():
    # Current bar makes a new high; channel must NOT include it.
    df = pd.DataFrame(
        {
            "high": [10.0, 11.0, 12.0, 99.0],
            "low": [9.0, 10.0, 11.0, 98.0],
            "close": [9.5, 10.5, 11.5, 98.5],
        }
    )
    dc = ind.donchian(df, entry_n=3, exit_n=2)
    assert dc["dc_entry_high"].iloc[3] == 12.0  # max of bars 0..2, not 99


def test_squeeze_on_boolean_and_causal():
    df = _df()
    sq = ind.squeeze_on(df)
    assert sq.dtype == bool


def test_all_indicators_causal():
    """Value at row i must not change when future rows are removed."""
    df = _df(n=300)
    t = 250
    full = {
        "atr": ind.atr(df, 14),
        "bb": ind.bollinger(df["close"], 20, 2.0)["bb_upper"],
        "kc": ind.keltner(df, 20, 1.5)["kc_upper"],
        "dc": ind.donchian(df, 20, 10)["dc_entry_high"],
        "sq": ind.squeeze_on(df).astype(float),
    }
    trunc_df = df.iloc[: t + 1]
    trunc = {
        "atr": ind.atr(trunc_df, 14),
        "bb": ind.bollinger(trunc_df["close"], 20, 2.0)["bb_upper"],
        "kc": ind.keltner(trunc_df, 20, 1.5)["kc_upper"],
        "dc": ind.donchian(trunc_df, 20, 10)["dc_entry_high"],
        "sq": ind.squeeze_on(trunc_df).astype(float),
    }
    for k in full:
        a, b = full[k].iloc[t], trunc[k].iloc[t]
        assert (np.isnan(a) and np.isnan(b)) or a == b, f"{k} is not causal at row {t}"
