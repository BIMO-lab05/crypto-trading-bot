# tests/edge_lab/test_edge_lab_gate2.py
import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

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
