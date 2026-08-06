import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from killtests.h4_information import h4_stats, load_num_trials, score_signals  # noqa: E402


def _series_and_store(n=1200, informative=False, seed=7):
    # n=1200 -> ~390 scored signals; CPCV needs n_samples >= n_groups*(label_horizon+embargo+1)
    # = 10*(24+4+1) = 290 — n=600 (190 signals) would make split() raise ValueError.
    """Synthetic 60m series + matching CandleStore-like frame provider."""
    rng = np.random.default_rng(seed)
    start = 1_700_000_000_000
    step = 3_600_000
    rets = rng.normal(0, 0.01, n)
    closes = 100 * np.exp(np.cumsum(rets))
    f = pd.DataFrame({"ts_ms": [start + i * step for i in range(n)], "close": closes})

    class FakeStore:
        def frame(self, symbol, interval):
            return f

    sig_rows = []
    for i in range(
        0, n, 3
    ):  # runs to the end so the last ~8 signals genuinely lack a 24-bar horizon
        if informative:
            fwd = np.log(closes[min(i + 24, n - 1)] / closes[i])
            act = "BUY" if fwd > 0 else "SELL"  # oracle: perfect foresight
        else:
            act = "BUY" if rng.random() < 0.5 else "SELL"
        sig_rows.append(
            {
                "symbol": "TESTUSDT",
                "ts_ms": start + i * step + step,
                "action": act,
                "confidence": 0.5,
                "aggregated_score": 0.2,
                "consensus_count": 3,
                "ens_action": act,
                "ens_confidence": 0.5,
                "ens_position_size_pct": 0.05,
                "close": closes[i],
            }
        )
    return pd.DataFrame(sig_rows), FakeStore()


def test_score_signals_shapes_and_horizon_drop():
    series, store = _series_and_store()
    scored = score_signals(series, store, horizon_bars=24)
    assert {"signed_ret", "hit", "fwd_ret"} <= set(scored.columns)
    # tail signals without a full 24-bar horizon are dropped
    assert len(scored) < len(series)


def test_unexpected_ens_action_raises():
    series, store = _series_and_store()
    series = series.copy()
    series.loc[series.index[0], "ens_action"] = "HOLD"
    with pytest.raises(ValueError, match="unexpected ens_action"):
        score_signals(series, store, horizon_bars=24)


def test_close_mismatch_raises():
    series, store = _series_and_store()
    series = series.copy()
    series.loc[series.index[0], "close"] = series["close"].iloc[0] * 2 + 1
    with pytest.raises(ValueError, match="ts_ms convention mismatch"):
        score_signals(series, store, horizon_bars=24)


def test_join_miss_raises_and_is_distinct_from_horizon_drop():
    # A signal ts_ms that doesn't land on the CandleStore's hourly grid must be
    # refused loudly, not silently folded into the (legitimate) tail-horizon
    # drop count -- see fix-round-1 reviewer repro: an entire symbol shifted off
    # the grid was previously discarded silently and the CLI still exited 0.
    series, store = _series_and_store()
    series = series.copy()
    series.loc[series.index[0], "ts_ms"] = series["ts_ms"].iloc[0] + 1_800_000
    with pytest.raises(ValueError, match="no matching bar"):
        score_signals(series, store, horizon_bars=24)


def test_h4_stats_reports_join_miss_and_horizon_drop_separately():
    series, store = _series_and_store(informative=True)
    scored = score_signals(series, store, horizon_bars=24)
    stats = h4_stats(scored, num_trials=8)
    assert stats["join_miss_signals"] == 0
    assert stats["horizon_drop_signals"] > 0


def test_empty_scored_raises_insufficient_signals():
    from killtests.h4_information import InsufficientSignalsError

    empty = pd.DataFrame(
        columns=["symbol", "ts_ms", "ens_action", "fwd_ret", "signed_ret", "hit"]
    )
    with pytest.raises(InsufficientSignalsError):
        h4_stats(empty, num_trials=8)


def test_oracle_signals_score_high():
    series, store = _series_and_store(informative=True)
    scored = score_signals(series, store, horizon_bars=24)
    stats = h4_stats(scored, num_trials=8)
    assert stats["directional_accuracy"] > 0.95
    assert stats["dsr"] > 0.95


def test_random_signals_fail_dsr():
    series, store = _series_and_store(informative=False)
    scored = score_signals(series, store, horizon_bars=24)
    stats = h4_stats(scored, num_trials=8)
    assert stats["dsr"] < 0.95


def test_num_trials_floor():
    doc = load_num_trials()
    assert doc["floor"] == 8
    assert len(doc["configurations"]) >= 8


def test_pf_is_pooled():
    # informative=True makes losses exactly 0.0 (oracle never scores a loser), so
    # both a correctly-pooled PF and a mean-of-folds PF would land on the same
    # inf -- vacuous. Use the random (informative=False) fixture instead, which
    # has non-zero wins AND losses and actually discriminates the two formulas.
    series, store = _series_and_store(informative=False)
    scored = score_signals(series, store, horizon_bars=24)
    stats = h4_stats(scored, num_trials=8)
    wins = scored.loc[scored["signed_ret"] > 0, "signed_ret"].sum()
    losses = abs(scored.loc[scored["signed_ret"] < 0, "signed_ret"].sum())
    assert losses > 0  # sanity: this fixture must not be vacuous either
    assert stats["pf_pooled"] == pytest.approx(wins / losses)


def test_gate_refuses_without_h3_verdict(tmp_path):
    from killtests.h4_information import _check_gates

    with pytest.raises(SystemExit, match="no H3 verdict"):
        _check_gates(
            force=False,
            evidence_dir=str(tmp_path),
            stamp_path=str(tmp_path / "stamp.json"),
        )


def test_gate_refuses_stale_stamp(tmp_path):
    from killtests.h4_information import _check_gates
    from killtests.report import write_verdict

    write_verdict("H3", "REJECT", "c", {}, [], {}, {}, out_dir=str(tmp_path))
    (tmp_path / "stamp.json").write_text(
        json.dumps({"date": "19700101", "passed": True})
    )
    with pytest.raises(SystemExit, match="parity stamp"):
        _check_gates(
            force=False,
            evidence_dir=str(tmp_path),
            stamp_path=str(tmp_path / "stamp.json"),
        )


def test_gate_force_returns_caveats(tmp_path):
    from killtests.h4_information import _check_gates

    caveats = _check_gates(
        force=True, evidence_dir=str(tmp_path), stamp_path=str(tmp_path / "stamp.json")
    )
    assert any("H3" in c for c in caveats) and any("stamp" in c for c in caveats)
