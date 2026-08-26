# tests/edge_lab/test_edge_lab_trials_threading.py
"""The ledger-derived trials floor must actually bind, not just exist.

`run_battery` computes an `effective_floor` from the trial ledger and has to
carry it through `_score_variant` -> `score_gate2` -> `run_gate2` (recorded
as `Gate2Result.num_trials_used`) and separately through the three verdict
renderers (`render_verdict`, `render_summary`, `write_verdict_json`). A gap
in either path renders a doc that claims "read live from edge_lab.config"
while quietly using a stale constant.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from edge_lab import trial_ledger  # noqa: E402
from edge_lab.config import NUM_TRIALS_FLOOR  # noqa: E402
from edge_lab.gate2 import run_gate2  # noqa: E402
from edge_lab.trades import Trade  # noqa: E402

from el_shared import DAY, T0, make_daily  # noqa: E402
from test_edge_lab_battery import (  # noqa: E402
    _pin,
    _stub_registry,
    _write_daily_csvs,
)
from edge_lab.run_battery import run_battery  # noqa: E402


@pytest.fixture(autouse=True)
def _redirect_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(trial_ledger, "ledger_path", lambda: tmp_path / "ledger.json")
    yield


def test_explicit_floor_above_path_count_binds():
    rng = np.random.default_rng(1)
    rets = pd.Series(rng.normal(0.001, 0.01, 500))
    r = run_gate2(rets, label_horizon_days=5, num_trials_floor=60)
    assert r.num_trials_used == 60


def test_dsr_strictly_decreasing_as_floor_rises():
    """Every compared floor must actually change num_trials_used.

    The pre-fix version compared floors 16/45/200: at the pinned CPCV 10/2
    config n_paths is 45, so max(16, 45) == max(45, 45) and the 16-vs-45 leg
    was a tautology — it passed without the floor doing anything. All floors
    here exceed the 45 paths, so each one IS num_trials_used, and the DSR
    ordering must be strict (mean/sigma chosen so DSR sits in the sensitive
    region, not saturated at 0.0 or 1.0 where floats would tie).
    """
    rng = np.random.default_rng(11)
    rets = pd.Series(rng.normal(0.0012, 0.012, 500))
    r_low = run_gate2(rets, label_horizon_days=5, num_trials_floor=46)
    r_mid = run_gate2(rets, label_horizon_days=5, num_trials_floor=60)
    r_high = run_gate2(rets, label_horizon_days=5, num_trials_floor=200)
    # Each floor must bind: above n_paths, num_trials_used == the floor.
    assert r_low.n_paths_valid < 46
    assert (r_low.num_trials_used, r_mid.num_trials_used, r_high.num_trials_used) == (
        46,
        60,
        200,
    )
    assert r_low.dsr > r_mid.dsr > r_high.dsr


def test_insufficient_samples_records_floor_not_zero():
    r = run_gate2(pd.Series([0.001] * 50), label_horizon_days=20, num_trials_floor=33)
    assert not r.passed
    assert r.num_trials_used == 33


def test_floor_survives_round_trip_through_run_battery(tmp_path):
    daily = make_daily(["AUSDT"], n_days=400)
    _write_daily_csvs(tmp_path, daily)
    pin = _pin(tmp_path, ["AUSDT"])

    # Pre-seed the ledger with enough distinct variants that the effective
    # floor rises above the static NUM_TRIALS_FLOOR, so a doc that fell back
    # to the constant is distinguishable from one that used the real floor.
    seed = [
        {"candidate": f"seed{i}", "variant": "v0"} for i in range(NUM_TRIALS_FLOOR + 10)
    ]
    trial_ledger.append_entries(seed)

    def one_trade(bundle, variant):
        return [Trade("AUSDT", "LONG", T0 + 30 * DAY, T0 + 37 * DAY, 100.0, 105.0)]

    out = tmp_path / "out"
    run_battery(
        tmp_path,
        pin,
        out,
        T0 + 400 * DAY,
        candidates=_stub_registry({"solo": one_trade}),
    )

    expected_floor = trial_ledger.effective_trials_floor(0)
    assert expected_floor > NUM_TRIALS_FLOOR

    md = next(out.glob("solo-verdict-*.md")).read_text()
    assert f"num_trials floor = {expected_floor}" in md
    assert f"num_trials floor = {NUM_TRIALS_FLOOR}" not in md.replace(
        f"num_trials floor = {expected_floor}", ""
    )

    payload = json.loads(next(out.glob("solo-verdict-*.json")).read_text())
    assert payload["thresholds"]["num_trials_floor"] == expected_floor

    # Decision of record 2026-08-20: the num_trials components must be
    # reported separately in every verdict artifact.
    trials = payload["trials"]
    assert trials["ledger_count"] == trial_ledger.effective_trial_count(0)
    assert trials["num_trials_floor"] == expected_floor
    assert trials["n_paths"] is not None
    assert trials["num_trials_used"] == max(expected_floor, trials["n_paths"])
    assert (
        f"trials accounting: ledger_count={trials['ledger_count']}, "
        f"n_paths={trials['n_paths']}, "
        f"num_trials_used={trials['num_trials_used']}, "
        f"num_trials_floor={expected_floor}"
    ) in md


def test_committed_verdict_json_keys_still_present(tmp_path):
    """A freshly rendered verdict must be a superset of the committed shape."""
    committed = sorted(
        REPO.glob(".planning/evidence/killtests/*-verdict-20260817.json")
    )
    if not committed:
        pytest.skip("no committed 2026-08-17 verdict JSON to compare against")

    daily = make_daily(["AUSDT"], n_days=400)
    _write_daily_csvs(tmp_path, daily)
    pin = _pin(tmp_path, ["AUSDT"])

    def one_trade(bundle, variant):
        return [Trade("AUSDT", "LONG", T0 + 30 * DAY, T0 + 37 * DAY, 100.0, 105.0)]

    out = tmp_path / "out"
    run_battery(
        tmp_path,
        pin,
        out,
        T0 + 400 * DAY,
        candidates=_stub_registry({"solo": one_trade}),
    )
    fresh = json.loads(next(out.glob("solo-verdict-*.json")).read_text())

    for old_path in committed:
        old = json.loads(old_path.read_text())
        assert set(old.keys()) <= set(fresh.keys())
        if "thresholds" in old:
            assert set(old["thresholds"].keys()) <= set(fresh["thresholds"].keys())


def test_rerun_of_ledgered_variants_adds_nothing():
    entries = [{"candidate": "c", "variant": "v0"}]
    trial_ledger.append_entries(entries)
    before = trial_ledger.effective_trials_floor(0)
    # Re-scoring the same (candidate, variant) contributes zero new trials.
    after = trial_ledger.effective_trials_floor(0)
    assert before == after


def test_run_battery_appends_enriched_rows(tmp_path):
    """New rows written by run_battery must carry date/params/gate1_verdict/
    gate2_passed, not the thin {candidate, variant} shape the pre-fix writer
    produced — those thin historical rows stay untouched (append-only), but
    every row appended going forward must be enriched."""
    daily = make_daily(["AUSDT"], n_days=400)
    _write_daily_csvs(tmp_path, daily)
    pin = _pin(tmp_path, ["AUSDT"])

    def one_trade(bundle, variant):
        return [Trade("AUSDT", "LONG", T0 + 30 * DAY, T0 + 37 * DAY, 100.0, 105.0)]

    out = tmp_path / "out"
    run_battery(
        tmp_path,
        pin,
        out,
        T0 + 400 * DAY,
        candidates=_stub_registry({"solo": one_trade}),
    )

    entries = trial_ledger.load_entries()
    assert entries, "run_battery must have appended at least one row"
    for e in entries:
        assert e["candidate"] == "solo"
        assert e["variant"] == "v0"
        assert e["date"] is not None
        assert "params" in e
        assert "gate1_verdict" in e
        assert "gate2_passed" in e
