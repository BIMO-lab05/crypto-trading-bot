import sys
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from edge_lab.gate1 import run_gate1, slippage_table  # noqa: E402
from edge_lab.trades import Trade, write_trades_csv  # noqa: E402

T0, T1 = 1_700_000_000_000, 1_700_086_400_000


def test_slippage_table_has_majors_only():
    t = slippage_table()
    assert t["BTCUSDT"] == Decimal("5") and t["ADAUSDT"] == Decimal("10")
    assert "PEPEUSDT" not in t  # unknowns hit the fallback, by design


def test_big_edge_passes_small_edge_killed(tmp_path):
    # +5% per trade on an unknown symbol (31bps RT cost): ratio 500/31 = 16x -> PASS
    win = [
        Trade(
            "PEPEUSDT", "LONG", T0 + i * 200_000_000, T1 + i * 200_000_000, 100.0, 105.0
        )
        for i in range(5)
    ]
    r = run_gate1(write_trades_csv(win, tmp_path / "w.csv"), tmp_path / "funding")
    assert r.verdict == "PASS" and r.ratio_taker > Decimal("2")

    # +0.02% per trade: 2 bps gross vs 31 bps cost -> KILL
    lose = [
        Trade(
            "PEPEUSDT",
            "LONG",
            T0 + i * 200_000_000,
            T1 + i * 200_000_000,
            100.0,
            100.02,
        )
        for i in range(5)
    ]
    r2 = run_gate1(write_trades_csv(lose, tmp_path / "l.csv"), tmp_path / "funding")
    assert r2.verdict == "KILL"


def test_missing_funding_is_marked_not_zeroed(tmp_path):
    trades = [Trade("BTCUSDT", "LONG", T0, T1, 100.0, 105.0)]
    r = run_gate1(write_trades_csv(trades, tmp_path / "t.csv"), tmp_path / "funding")
    assert not r.funding_complete
    assert "BTCUSDT" in r.funding_symbols_missing
    assert "EXCLUDES funding" in r.render()


def test_funding_series_feeds_through(tmp_path):
    fdir = tmp_path / "funding"
    fdir.mkdir(parents=True)
    # settlement inside the holding window, LONG pays positive rate
    (fdir / "BTCUSDT_funding.csv").write_text(
        f"ts_ms,funding_rate\n{T0 + 3_600_000},0.0001\n"
    )
    trades = [Trade("BTCUSDT", "LONG", T0, T1, 100.0, 105.0)]
    r = run_gate1(write_trades_csv(trades, tmp_path / "t.csv"), fdir)
    assert r.funding_complete
    assert r.funding_total > 0  # positive = paid, per te_costs sign convention
