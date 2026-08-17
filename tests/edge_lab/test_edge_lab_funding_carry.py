import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from conftest import DAY, T0, make_daily  # noqa: E402
from edge_lab.candidates.funding_carry import VARIANTS, generate_trades  # noqa: E402

V15 = next(v for v in VARIANTS if v.name == "thresh_1.5x")
EIGHT_H = 8 * 3_600_000


def _funding(symbol, rate, n=90, start=T0):
    return {
        symbol: pd.DataFrame(
            {
                "ts_ms": [start + i * EIGHT_H for i in range(n)],
                "funding_rate": [rate] * n,
            }
        )
    }


def test_two_variants_declared():
    assert [v.name for v in VARIANTS] == ["thresh_1.5x", "thresh_2x"]


def test_high_positive_funding_opens_short():
    daily = make_daily(["AUSDT"], n_days=60, seed=1)
    # 0.3%/settlement, wildly above any threshold; positive -> longs pay -> we SHORT
    trades = generate_trades(daily, _funding("AUSDT", "0.003"), V15)
    assert trades and all(t.side == "SHORT" for t in trades)


def test_negative_funding_opens_long():
    daily = make_daily(["AUSDT"], n_days=60, seed=1)
    trades = generate_trades(daily, _funding("AUSDT", "-0.003"), V15)
    assert trades and all(t.side == "LONG" for t in trades)


def test_tiny_funding_never_enters():
    daily = make_daily(["AUSDT"], n_days=60, seed=1)
    # 0.1 bp/settlement * 9 = 0.9 bp per hold vs threshold 1.5 * 31bp — no entry
    trades = generate_trades(daily, _funding("AUSDT", "0.00001"), V15)
    assert trades == []


def test_sign_flip_exits():
    daily = make_daily(["AUSDT"], n_days=60, seed=1)
    n = 90
    rates = ["0.003"] * 45 + ["-0.003"] * 45  # flips mid-window
    f = {
        "AUSDT": pd.DataFrame(
            {"ts_ms": [T0 + i * EIGHT_H for i in range(n)], "funding_rate": rates}
        )
    }
    trades = generate_trades(daily, f, V15)
    assert trades
    first = trades[0]
    flip_ms = T0 + 45 * EIGHT_H
    assert first.exit_ts_ms <= flip_ms + 3 * DAY  # exits shortly after the flip


def test_no_funding_data_no_trades():
    daily = make_daily(["AUSDT"], n_days=60, seed=1)
    assert generate_trades(daily, {}, V15) == []


def test_shift_invariance_manual():
    """Truncating both price and funding history must not change past trades."""
    from conftest import assert_shift_invariant

    daily = make_daily(["AUSDT"], n_days=120, seed=2)
    f = _funding("AUSDT", "0.003", n=360)
    cut = T0 + 60 * DAY
    gen = lambda d, v: generate_trades(
        d,
        {
            "AUSDT": f["AUSDT"][f["AUSDT"]["ts_ms"] <= cut]
            if d["AUSDT"]["ts_ms"].max() <= cut
            else f["AUSDT"]
        },
        v,
    )
    assert_shift_invariant(gen, daily, V15, cut)
