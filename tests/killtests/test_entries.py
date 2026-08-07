import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from killtests.entries import DEFAULT_FIXTURE, load_entries  # noqa: E402


def test_fixture_loads_13_entries():
    entries = load_entries(DEFAULT_FIXTURE)
    assert len(entries) == 13
    ids = sorted(e.position_id for e in entries)
    assert len(set(ids)) == 13


def test_entry_fields_sane():
    for e in load_entries(DEFAULT_FIXTURE):
        assert e.side in ("LONG", "SHORT")
        assert e.symbol in {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"}
        assert e.entry_price > 0 and e.quantity > 0
        assert e.exit_ts_ms > e.entry_ts_ms
        # audit window: opened 2026-07-29 .. 2026-08-04; 1785974400000 = 2026-08-06 00:00 UTC (generous upper bound)
        assert 1785283200000 <= e.entry_ts_ms <= 1785974400000


def test_known_row_values():
    """Spot-check against the verified DB dump (position id 59)."""
    by_symbol_ts = {
        (e.symbol, e.side, round(e.entry_price, 2))
        for e in load_entries(DEFAULT_FIXTURE)
    }
    assert ("SOLUSDT", "LONG", 71.04) in by_symbol_ts
    assert ("BTCUSDT", "SHORT", 63556.10) in by_symbol_ts
