import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from el_shared import DAY, T0, assert_shift_invariant  # noqa: E402
from edge_lab.candidates.pairs_statarb import VARIANTS, generate_trades  # noqa: E402
from edge_lab.gate1 import run_gate1  # noqa: E402
from edge_lab.trades import gross_pnl, write_trades_csv  # noqa: E402

V_SECTOR = next(v for v in VARIANTS if v.name == "pairs_sector_30d")
V_VOLUME = next(v for v in VARIANTS if v.name == "pairs_volume_top10_60d")
V_ORTHO = next(v for v in VARIANTS if v.name == "pairs_orthogonal_30d")


def _df(ts_ms, close, volume=1000.0):
    close = np.asarray(close, dtype=float)
    open_ = np.concatenate([[close[0]], close[:-1]])
    return pd.DataFrame(
        {
            "ts_ms": ts_ms,
            "open": open_,
            "high": np.maximum(open_, close) * 1.001,
            "low": np.minimum(open_, close) * 0.999,
            "close": close,
            "volume": np.full(len(close), volume),
        }
    )


def make_cointegrated_pair(n_days=300, seed=7, half_life_days=2, noise_scale=3.0):
    """Common random-walk factor + a stationary AR(1) spread -> a textbook
    cointegrated pair: sym_a = factor, sym_b = factor + spread, where spread
    mean-reverts with the given half-life.

    Factor vol is deliberately small (0.004) relative to the spread's daily
    innovation (noise_scale=3.0): with the two on a comparable scale, the
    idiosyncratic mean-reverting part dominates day-to-day *returns* even
    though the *levels* still share the common trend. That keeps daily-return
    correlation under the pairs_orthogonal_30d variant's < 0.5 filter while
    the pair remains genuinely cointegrated in levels — a factor vol on the
    order of the noise scale (as an earlier version of this fixture used)
    pushes return correlation to ~0.8 and gets the positive control excluded
    by that filter before any calibration happens. half_life_days=2 keeps
    reversion commensurate with the 1-bar hold used by these variants (see
    pairs_statarb.py's max_holding_days deviation note).
    """
    rng = np.random.default_rng(seed)
    ts = [T0 + k * DAY for k in range(n_days)]

    factor_rets = rng.normal(0.0, 0.004, n_days)
    factor = 100.0 * np.cumprod(1 + factor_rets)

    phi = 0.5 ** (1.0 / half_life_days)
    spread = np.zeros(n_days)
    for k in range(1, n_days):
        spread[k] = phi * spread[k - 1] + rng.normal(0.0, noise_scale)

    sym_a_close = factor
    sym_b_close = factor + spread
    return {
        "PAIRAUSDT": _df(ts, sym_a_close),
        "PAIRBUSDT": _df(ts, sym_b_close),
    }


def make_independent_walks(n_days=300, seed=13):
    rng = np.random.default_rng(seed)
    ts = [T0 + k * DAY for k in range(n_days)]
    out = {}
    for i, sym in enumerate(["INDAUSDT", "INDBUSDT"]):
        rets = rng.normal(0.0, 0.02, n_days)
        close = 100.0 * np.cumprod(1 + rets)
        out[sym] = _df(ts, close)
    return out


def test_three_variants_declared():
    assert [v.name for v in VARIANTS] == [
        "pairs_sector_30d",
        "pairs_volume_top10_60d",
        "pairs_orthogonal_30d",
    ]
    assert all(v.candidate == "pairs_statarb" for v in VARIANTS)


def test_cointegrated_pair_emits_two_legs_per_position():
    data = make_cointegrated_pair()
    trades = generate_trades(data, V_SECTOR)
    assert trades, "cointegrated pair produced no trades"
    assert len(trades) % 2 == 0

    by_entry = {}
    for t in trades:
        by_entry.setdefault((t.entry_ts_ms, t.exit_ts_ms), []).append(t)

    for (entry_ts, exit_ts), pair_trades in by_entry.items():
        assert len(pair_trades) == 2, (
            f"expected 2 legs at {entry_ts}, got {len(pair_trades)}"
        )
        symbols = {t.symbol for t in pair_trades}
        assert symbols == {"PAIRAUSDT", "PAIRBUSDT"}
        sides = {t.symbol: t.side for t in pair_trades}
        assert sides["PAIRAUSDT"] != sides["PAIRBUSDT"]
        assert {sides["PAIRAUSDT"], sides["PAIRBUSDT"]} == {"LONG", "SHORT"}
        for t in pair_trades:
            assert t.entry_ts_ms == entry_ts
            assert t.exit_ts_ms == exit_ts


def test_shift_invariance_sector():
    data = make_cointegrated_pair()
    cut = T0 + 200 * DAY
    assert_shift_invariant(generate_trades, data, V_SECTOR, cut)


def test_shift_invariance_orthogonal():
    # seed=7 (the default) is used here rather than an alternate seed:
    # V_ORTHO's low_corr pair-selection filter plus the beta-persistence
    # screen is picky enough that many seeds produce zero trades over the
    # full 300-day run for this variant, which would make the check vacuous.
    # Verified empirically that seed=7 clears both filters and closes
    # trades well before this cut.
    data = make_cointegrated_pair(seed=7)
    cut = T0 + 200 * DAY
    assert_shift_invariant(generate_trades, data, V_ORTHO, cut)


def _position_gross_pnls(trades):
    """Sum both legs' gross_pnl per (entry_ts, exit_ts) position."""
    by_position = {}
    for t in trades:
        by_position.setdefault((t.entry_ts_ms, t.exit_ts_ms), []).append(t)
    return [
        sum(float(gross_pnl(t)) for t in leg_pair) for leg_pair in by_position.values()
    ]


def test_negative_control_independent_walks_have_no_pnl_edge():
    # Trade *count* cannot discriminate here: a z-score built off a trailing
    # spread crosses its entry threshold on any moderately volatile series,
    # coincidence-cointegrated or not, so a single admitted calibration
    # window can still emit a run of trades. What should differ, and does
    # empirically, is realized P&L: a genuinely mean-reverting spread
    # recovers value on each round trip, while a spread that only looked
    # mean-reverting in-sample is a forward martingale and averages out
    # near zero (or negative, net of the direction the noise chose).
    # Pooled over many independent-walk pairs so one unlucky/lucky draw
    # can't decide the assertion.
    for variant in (V_SECTOR, V_ORTHO):
        coint_pnls = _position_gross_pnls(
            generate_trades(make_cointegrated_pair(), variant)
        )
        assert coint_pnls, (
            f"{variant.name}: positive control produced no positions at all"
        )
        coint_mean = sum(coint_pnls) / len(coint_pnls)
        assert coint_mean > 0, (
            f"{variant.name}: cointegrated fixture has non-positive mean P&L"
        )

        indep_pnls = []
        for seed in range(1, 16):
            data = make_independent_walks(seed=seed * 17 + 3)
            indep_pnls.extend(_position_gross_pnls(generate_trades(data, variant)))

        if not indep_pnls:
            continue  # no trades at all is an even stronger negative-control pass
        indep_mean = sum(indep_pnls) / len(indep_pnls)
        assert indep_mean < coint_mean, (
            f"{variant.name}: independent-walk mean P&L ({indep_mean:.4f}) is not "
            f"below the cointegrated fixture's ({coint_mean:.4f}) — the screen is "
            "not detecting a real mechanism vs. noise"
        )


def test_negative_control_independent_walks_die_at_gate1(tmp_path):
    # The brief's literal criterion: "two independent random walks must
    # produce few or no trades, or produce trades that Gate 1 kills."
    # Pooled across seeds (same pool as the P&L assertion above) and run
    # through the real cost-hurdle screen, not a re-derived proxy.
    for variant in (V_SECTOR, V_ORTHO):
        pooled_trades = []
        for seed in range(1, 16):
            data = make_independent_walks(seed=seed * 17 + 3)
            pooled_trades.extend(generate_trades(data, variant))

        if not pooled_trades:
            continue  # no trades at all satisfies the brief's "or few/no trades" branch
        csv_path = write_trades_csv(pooled_trades, tmp_path / f"{variant.name}.csv")
        result = run_gate1(csv_path, tmp_path / "funding")
        assert result.verdict == "KILL", (
            f"{variant.name}: independent-walk trades cleared Gate 1 "
            f"(ratio_taker={result.ratio_taker}) — noise should not pass the cost hurdle"
        )


def test_volume_top10_filter_needs_enough_symbols():
    # fewer than 3 eligible symbols after excluding the top-2 by volume
    # leaves no pairs to trade
    data = make_cointegrated_pair()
    trades = generate_trades(data, V_VOLUME)
    assert trades == []


def _make_volume_universe():
    """Cointegrated PAIRA/PAIRB embedded in a wider volume-ranked universe:
    two very high-volume symbols to be excluded (BTC/ETH-analog), plus
    filler so the cointegrated pair lands inside the "next 10 by volume"
    eligible set for pairs_volume_top10_60d."""
    base = make_cointegrated_pair()
    rng = np.random.default_rng(99)
    ts = base["PAIRAUSDT"]["ts_ms"].tolist()
    extra = {}
    for name, vol in [("BIGAUSDT", 5_000.0), ("BIGBUSDT", 5_000.0)]:
        rets = rng.normal(0.0, 0.02, len(ts))
        close = 100.0 * np.cumprod(1 + rets)
        extra[name] = _df(ts, close, volume=vol)
    for i in range(9):
        rets = rng.normal(0.0, 0.02, len(ts))
        close = 100.0 * np.cumprod(1 + rets)
        extra[f"FILLER{i:02d}USDT"] = _df(ts, close, volume=800.0)

    data = dict(base)
    for sym, df in extra.items():
        data[sym] = df
    # give the cointegrated pair volume that lands it inside the top-10
    # (post BIGA/BIGB exclusion) alongside the fillers
    data["PAIRAUSDT"] = _df(ts, base["PAIRAUSDT"]["close"].tolist(), volume=900.0)
    data["PAIRBUSDT"] = _df(ts, base["PAIRBUSDT"]["close"].tolist(), volume=900.0)
    return data


def test_volume_top10_filter_trades_among_eligible_symbols():
    data = _make_volume_universe()
    trades = generate_trades(data, V_VOLUME)
    assert trades, "no trades among the eligible top-10-by-volume universe"
    symbols_traded = {t.symbol for t in trades}
    assert "BIGAUSDT" not in symbols_traded
    assert "BIGBUSDT" not in symbols_traded


def test_shift_invariance_volume():
    data = _make_volume_universe()
    cut = T0 + 200 * DAY
    assert_shift_invariant(generate_trades, data, V_VOLUME, cut)


def test_no_trade_closes_before_lookback_warmup():
    data = make_cointegrated_pair()
    lookback_days = dict(V_SECTOR.params)["lookback_days"]
    trades = generate_trades(data, V_SECTOR)
    earliest_entry = min(t.entry_ts_ms for t in trades)
    assert earliest_entry >= T0 + lookback_days * DAY
