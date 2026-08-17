# tests/edge_lab/test_edge_lab_gate2.py
import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from edge_lab.gate2 import daily_returns_from_trades, run_gate2  # noqa: E402
from edge_lab.trades import Trade  # noqa: E402

DAY = 86_400_000
T0 = 1_700_000_000_000


def _daily_closes(symbol="BTCUSDT", n=400, drift=0.001):
    ts = [T0 + i * DAY for i in range(n)]
    px = 100.0 * np.cumprod([1 + drift] * n)
    return {symbol: pd.DataFrame({"ts_ms": ts, "open": px, "close": px})}


def test_flat_days_are_zero():
    closes = _daily_closes()
    trades = [Trade("BTCUSDT", "LONG", T0 + 10 * DAY, T0 + 12 * DAY, 101.0, 102.0)]
    rets = daily_returns_from_trades(
        trades, closes, T0, T0 + 20 * DAY, {"BTCUSDT": Decimal("21")}, {}
    )
    assert len(rets) == 21
    assert rets.iloc[0] == 0.0 and rets.iloc[-1] == 0.0
    assert (rets.iloc[10:13] != 0).any()


def test_costs_deducted_at_entry_and_exit():
    closes = _daily_closes(drift=0.0)  # flat prices: only costs remain
    trades = [Trade("BTCUSDT", "LONG", T0 + 5 * DAY, T0 + 7 * DAY, 100.0, 100.0)]
    rets = daily_returns_from_trades(
        trades, closes, T0, T0 + 10 * DAY, {"BTCUSDT": Decimal("20")}, {}
    )
    # 10 bps at entry day, 10 bps at exit day
    assert abs(rets.iloc[5] + 0.001) < 1e-9
    assert abs(rets.iloc[7] + 0.001) < 1e-9


def test_short_side_sign():
    closes = _daily_closes(drift=0.01)  # rising market
    trades = [Trade("BTCUSDT", "SHORT", T0 + 5 * DAY, T0 + 10 * DAY, 105.0, 110.0)]
    rets = daily_returns_from_trades(
        trades, closes, T0, T0 + 15 * DAY, {"BTCUSDT": Decimal("0")}, {}
    )
    assert rets.iloc[6] < 0  # short loses in a rising market


def test_gate2_strong_signal_passes():
    rng = np.random.default_rng(3)
    rets = pd.Series(rng.normal(0.004, 0.005, 500))  # absurdly strong daily edge
    r = run_gate2(rets, label_horizon_days=5)
    assert r.passed and r.dsr >= 0.95 and r.pooled_pf > 1.0


def test_gate2_noise_fails():
    rng = np.random.default_rng(4)
    rets = pd.Series(rng.normal(0.0, 0.01, 500))
    r = run_gate2(rets, label_horizon_days=5)
    assert not r.passed and len(r.reasons) >= 1


def test_gate2_insufficient_samples_is_reported_not_raised():
    r = run_gate2(pd.Series([0.001] * 50), label_horizon_days=20)
    assert not r.passed
    assert any("insufficient" in reason for reason in r.reasons)


def test_pooled_pf_not_dragged_by_zero_loss_folds():
    """All-positive returns: pooled PF must be inf, not a fold-mean near 1."""
    rets = pd.Series([0.001] * 400)
    r = run_gate2(rets, label_horizon_days=2)
    assert r.pooled_pf == float("inf")


def _closes_missing(missing_days, symbol="BTCUSDT", n=400, drift=0.001):
    """`_daily_closes` with the given day offsets deleted — a data hole."""
    frame = _daily_closes(symbol, n, drift)[symbol]
    holes = [T0 + d * DAY for d in missing_days]
    return {symbol: frame[~frame["ts_ms"].isin(holes)].reset_index(drop=True)}


def test_single_bar_hole_is_carried_not_raised():
    """Gate 0 tolerates one missing bar, so Gate 2 must not ERROR on it.

    The gap day contributes exactly 0.0 (carried close over itself) and the
    day AFTER it is measured against that carried close, so the two-day
    price move is booked whole rather than lost.
    """
    px = 100.0 * np.cumprod([1.001] * 400)
    closes = _closes_missing([7])
    trades = [Trade("BTCUSDT", "LONG", T0 + 5 * DAY, T0 + 9 * DAY, 100.0, 110.0)]

    rets = daily_returns_from_trades(
        trades, closes, T0, T0 + 20 * DAY, {"BTCUSDT": Decimal("0")}, {}
    )

    assert rets.iloc[7] == 0.0
    # day 8 spans the hole: close[8] / close[6] - 1, not close[8] / close[7]
    assert rets.iloc[8] == pytest.approx(px[8] / px[6] - 1.0, abs=1e-12)
    # unaffected neighbours still price day-over-day
    assert rets.iloc[6] == pytest.approx(px[6] / px[5] - 1.0, abs=1e-12)


def test_multi_bar_hole_still_raises():
    """3 consecutive missing bars is Gate 0 defect territory — stay loud."""
    closes = _closes_missing([7, 8, 9])
    trades = [Trade("BTCUSDT", "LONG", T0 + 5 * DAY, T0 + 12 * DAY, 100.0, 110.0)]

    with pytest.raises(KeyError, match="two or more consecutive missing bars"):
        daily_returns_from_trades(
            trades, closes, T0, T0 + 20 * DAY, {"BTCUSDT": Decimal("0")}, {}
        )


def test_same_day_trade_exact_net_return():
    """+1% move, 20bps round trip -> that day's return is exactly 0.008.

    Both cost halves land on the one day a same-day trade touches, so the
    full round trip is charged there — not half of it.
    """
    closes = _daily_closes(drift=0.0)
    trades = [
        Trade("BTCUSDT", "LONG", T0 + 5 * DAY, T0 + 5 * DAY + 3_600_000, 100.0, 101.0)
    ]

    rets = daily_returns_from_trades(
        trades, closes, T0, T0 + 10 * DAY, {"BTCUSDT": Decimal("20")}, {}
    )

    assert rets.iloc[5] == pytest.approx(0.008, abs=1e-12)


def test_concurrent_trades_equal_weighted_against_solo_control():
    """Two identical overlapping trades must score as the single-trade control.

    Equal weighting divides each day's summed contribution by n_open, so the
    duo's 2x sum over n_open=2 lands back on the solo value. The control
    assertion is the load-bearing one: solo must be the FULL return, not a
    halved one — without it this passes just as happily if both sides are
    wrongly divided.
    """
    closes = _daily_closes(drift=0.0)
    one = Trade("BTCUSDT", "LONG", T0 + 5 * DAY, T0 + 5 * DAY + 3_600_000, 100.0, 101.0)
    args = (closes, T0, T0 + 10 * DAY, {"BTCUSDT": Decimal("20")}, {})

    solo = daily_returns_from_trades([one], *args)
    duo = daily_returns_from_trades([one, one], *args)

    assert duo.iloc[5] == pytest.approx(solo.iloc[5], abs=1e-12)
    assert solo.iloc[5] == pytest.approx(0.008, abs=1e-12)  # NOT 0.004
    np.testing.assert_allclose(duo.to_numpy(), solo.to_numpy(), atol=1e-12)

    # A multi-day overlap weights the same way, every day of the hold.
    px = 100.0 * np.cumprod([1.001] * 400)
    rising = _daily_closes(drift=0.001)
    held = Trade("BTCUSDT", "LONG", T0 + 5 * DAY, T0 + 8 * DAY, 100.0, 110.0)
    held_args = (rising, T0, T0 + 12 * DAY, {"BTCUSDT": Decimal("0")}, {})

    solo_held = daily_returns_from_trades([held], *held_args)
    duo_held = daily_returns_from_trades([held, held], *held_args)

    np.testing.assert_allclose(duo_held.to_numpy(), solo_held.to_numpy(), atol=1e-12)
    assert solo_held.iloc[6] == pytest.approx(px[6] / px[5] - 1.0, abs=1e-12)
