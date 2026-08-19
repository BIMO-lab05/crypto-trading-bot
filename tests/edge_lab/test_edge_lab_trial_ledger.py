"""Trial ledger: append-only record, distinct-variant counting, effective floor."""

import json

from edge_lab import trial_ledger


def _entry(candidate, variant, date="2026-08-18"):
    return {
        "candidate": candidate,
        "variant": variant,
        "params": [["k", "1"]],
        "date": date,
        "gate1_verdict": "PASS",
        "gate2_passed": False,
    }


def test_missing_ledger_file_yields_empty_list_and_static_floor(tmp_path, monkeypatch):
    missing = tmp_path / "does_not_exist.json"
    assert trial_ledger.load_entries(missing) == []
    assert trial_ledger.effective_trials_floor(0, path=missing, static_floor=16) == 16
    assert trial_ledger.effective_trials_floor(5, path=missing, static_floor=16) == 16


def test_append_entries_preserves_prior_rows_byte_for_byte_and_appends(tmp_path):
    path = tmp_path / "ledger.json"
    first = [_entry("boom", "v1")]
    trial_ledger.append_entries(first, path=path)
    prior_bytes = path.read_bytes()
    prior_entries = json.loads(prior_bytes)

    second = [_entry("quiet", "v1")]
    trial_ledger.append_entries(second, path=path)

    combined = json.loads(path.read_text())
    assert combined[: len(prior_entries)] == prior_entries
    assert combined == first + second


def test_append_entries_creates_file_when_missing(tmp_path):
    path = tmp_path / "nested" / "ledger.json"
    trial_ledger.append_entries([_entry("stub", "v1")], path=path)
    assert path.exists()
    assert json.loads(path.read_text()) == [_entry("stub", "v1")]


def test_distinct_variant_count_counts_rerun_once():
    entries = [
        _entry("funding_carry", "thresh_2x", date="2026-08-17"),
        _entry("funding_carry", "thresh_2x", date="2026-08-20"),
        _entry("lf_trend", "dc_20_10", date="2026-08-17"),
    ]
    assert trial_ledger.distinct_variant_count(entries) == 2


def test_effective_trials_floor_is_max_of_static_and_distinct_plus_new(tmp_path):
    path = tmp_path / "ledger.json"
    trial_ledger.append_entries(
        [_entry("boom", "v1"), _entry("boom", "v2"), _entry("quiet", "v1")],
        path=path,
    )
    # distinct_count = 3, static_floor = 2 -> 3 + new_variant_count dominates
    assert trial_ledger.effective_trials_floor(2, path=path, static_floor=2) == 5
    # static_floor dominates when it is larger
    assert trial_ledger.effective_trials_floor(0, path=path, static_floor=100) == 100


def test_ledger_path_default_resolves_at_call_time():
    assert trial_ledger.ledger_path().name == "trial_ledger.json"


def test_seed_ledger_has_at_least_the_8_battery_variants():
    entries = trial_ledger.load_entries()
    # Historical rows (seeded 2026-08-17/18, and 17 thin {candidate, variant}
    # rows appended before the writer was enriched) may lack "date" — those
    # stay as-is, append-only, and must not KeyError here. The writer in
    # run_battery.py now enriches every NEW row with date/params/
    # gate1_verdict/gate2_passed (finding 4, WS1-C final fix wave); this
    # test only asserts about the historical seed, not new rows.
    battery_pairs = {
        (e["candidate"], e["variant"]) for e in entries if e.get("date") == "2026-08-17"
    }
    expected = {
        ("xs_momentum", "lookback_7d"),
        ("xs_momentum", "lookback_30d"),
        ("xs_momentum", "lookback_90d"),
        ("funding_carry", "thresh_1.5x"),
        ("funding_carry", "thresh_2x"),
        ("lf_trend", "dc_20_10"),
        ("lf_trend", "dc_55_20"),
        ("vol_breakout", "sqz_default"),
    }
    assert expected <= battery_pairs
