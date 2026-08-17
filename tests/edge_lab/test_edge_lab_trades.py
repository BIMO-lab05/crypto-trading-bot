"""Trade record + CSV contract against screen.py's parser."""

import sys
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from edge_lab.trades import Trade, gross_pnl, notionals, write_trades_csv  # noqa: E402
from edge_lab.config import NOTIONAL_PER_TRADE  # noqa: E402
from screen import _rows_from_csv, screen_trades  # noqa: E402
from costs_loader import load_costs  # noqa: E402


def _mk(side, entry_px, exit_px):
    return Trade(
        symbol="BTCUSDT",
        side=side,
        entry_ts_ms=1_700_000_000_000,
        exit_ts_ms=1_700_086_400_000,
        entry_px=entry_px,
        exit_px=exit_px,
    )


def test_long_pnl_sign():
    # LONG, +1%: pnl = notional * 0.01
    t = _mk("LONG", 100.0, 101.0)
    assert gross_pnl(t) == (NOTIONAL_PER_TRADE * Decimal("0.01")).quantize(
        Decimal("0.00000001")
    )


def test_short_pnl_sign():
    # SHORT, price +1%: loss
    t = _mk("SHORT", 100.0, 101.0)
    assert gross_pnl(t) < 0


def test_notional_out_scales_with_price():
    t = _mk("LONG", 100.0, 110.0)
    n_in, n_out = notionals(t)
    assert n_in == NOTIONAL_PER_TRADE
    assert n_out == (NOTIONAL_PER_TRADE * Decimal("1.1")).quantize(
        Decimal("0.00000001")
    )


def test_csv_round_trips_through_screen(tmp_path):
    trades = [_mk("LONG", 100.0, 101.0), _mk("SHORT", 200.0, 199.0)]
    path = write_trades_csv(trades, tmp_path / "t.csv")
    rows, provenance = _rows_from_csv(str(path), modelled_fee_rate=Decimal("0.001"))
    assert len(rows) == 2
    assert provenance == "notional_in / notional_out, as supplied"
    costs = load_costs()
    result = screen_trades(
        rows,
        schedule=costs.FeeSchedule.bybit_linear_perp(),
        slippage_table={"BTCUSDT": Decimal("5")},
        slippage_fallback=Decimal("10"),
    )
    assert result.n_trades == 2
    assert result.verdict in ("PASS", "KILL")
