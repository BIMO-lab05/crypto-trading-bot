"""Battery #2 (battery_2026-08-18_manifest.md, Candidate Family #1) —
percentile-entry / fixed-holding-period funding_carry variants.

Daily bars are spaced at the funding cadence (8h), not the usual 1-day
spacing from `conftest.make_daily`, so that a settlement spike lands on an
exact, predictable bar index and the resulting entry/exit timestamps are
easy to assert against.
"""

import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from conftest import DAY, T0, assert_shift_invariant  # noqa: E402
from edge_lab.candidates.funding_carry import VARIANTS, generate_trades  # noqa: E402

EIGHT_H = 8 * 3_600_000
V_MAJOR_8H = next(v for v in VARIANTS if v.name == "fp_75pct_8h_major")
V_MAJOR_24H = next(v for v in VARIANTS if v.name == "fp_90pct_24h_major")
V_ALL_8H = next(v for v in VARIANTS if v.name == "fp_75pct_8h_all")

_N = 90
_SPIKE_IDX = 40  # first 40 settlements (i=0..39) are tiny; i=40 is the spike


def _funding(symbol, spike_rate, n=_N, spike_idx=_SPIKE_IDX, tiny="0.00001"):
    rates = [tiny] * n
    rates[spike_idx] = spike_rate
    return {
        symbol: pd.DataFrame(
            {
                "ts_ms": [T0 + i * EIGHT_H for i in range(n)],
                "funding_rate": rates,
            }
        )
    }


def _daily(symbol, n=_N):
    """Bars at the same 8h cadence as `_funding`, so bar index i lines up
    with settlement index i for deterministic entry/exit assertions.
    """
    opens = [100.0 + i * 0.01 for i in range(n)]
    return {
        symbol: pd.DataFrame(
            {
                "ts_ms": [T0 + i * EIGHT_H for i in range(n)],
                "open": opens,
            }
        )
    }


def test_spike_above_75pct_opens_short_and_exits_after_8h():
    daily = _daily("BTCUSDT")
    funding = _funding("BTCUSDT", "0.005")  # positive, huge vs. tiny history -> SHORT
    trades = generate_trades(daily, funding, V_MAJOR_8H)
    assert len(trades) == 1
    t = trades[0]
    assert t.side == "SHORT"
    assert t.entry_ts_ms == T0 + (_SPIKE_IDX + 1) * EIGHT_H
    assert t.exit_ts_ms == t.entry_ts_ms + EIGHT_H
    assert t.exit_ts_ms > t.entry_ts_ms
    assert t.entry_px > 0 and t.exit_px > 0


def test_spike_negative_opens_long():
    daily = _daily("BTCUSDT")
    funding = _funding("BTCUSDT", "-0.005")
    trades = generate_trades(daily, funding, V_MAJOR_8H)
    assert len(trades) == 1
    assert trades[0].side == "LONG"


def test_90pct_variant_holds_24h_not_8h():
    daily = _daily("BTCUSDT")
    funding = _funding("BTCUSDT", "0.005")
    trades = generate_trades(daily, funding, V_MAJOR_24H)
    assert len(trades) == 1
    t = trades[0]
    assert t.entry_ts_ms == T0 + (_SPIKE_IDX + 1) * EIGHT_H
    assert t.exit_ts_ms == t.entry_ts_ms + 3 * EIGHT_H  # 24h = 3 settlement epochs


def test_no_spike_never_enters():
    daily = _daily("BTCUSDT")
    funding = _funding(
        "BTCUSDT", "0.00001"
    )  # spike rate itself is tiny -> no rank edge
    trades = generate_trades(daily, funding, V_MAJOR_8H)
    assert trades == []


def test_insufficient_history_never_enters():
    """A spike before _MIN_PERCENTILE_SAMPLES settlements have accrued must
    not fire — there isn't enough history to rank it."""
    daily = _daily("BTCUSDT", n=40)
    funding = _funding("BTCUSDT", "0.005", n=40, spike_idx=5)
    trades = generate_trades(daily, funding, V_MAJOR_8H)
    assert trades == []


def test_symbol_filter_excludes_non_major():
    daily = _daily("DOGEUSDT")
    funding = _funding("DOGEUSDT", "0.005")
    trades = generate_trades(daily, funding, V_MAJOR_8H)
    assert trades == []


def test_all_symbols_variant_includes_non_major():
    daily = _daily("DOGEUSDT")
    funding = _funding("DOGEUSDT", "0.005")
    trades = generate_trades(daily, funding, V_ALL_8H)
    assert len(trades) == 1
    assert trades[0].symbol == "DOGEUSDT"


def test_no_funding_data_no_trades():
    daily = _daily("BTCUSDT")
    trades = generate_trades(daily, {}, V_MAJOR_8H)
    assert trades == []


def test_shift_invariance_percentile_variant():
    """Truncating price history after the cut must not change trades that
    already closed at or before the cut. Cut lands after the exit bar, so
    the one closed trade above is a non-vacuous check."""
    daily = _daily("BTCUSDT")
    funding = _funding("BTCUSDT", "0.005")
    entry_ts = T0 + (_SPIKE_IDX + 1) * EIGHT_H
    exit_ts = entry_ts + EIGHT_H
    cut = exit_ts + DAY  # comfortably past the exit bar

    def gen(d, v):
        return generate_trades(d, funding, v)

    assert_shift_invariant(gen, daily, V_MAJOR_8H, cut)
