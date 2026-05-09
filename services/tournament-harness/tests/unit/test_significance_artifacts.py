"""Unit tests for app.significance.artifacts (Phase 4 plan 04-01 Task 1).

Verifies atomic-write discipline (D-14), config-by-reference contract (D-03),
and required schema fields per significance.json contract.
"""

from __future__ import annotations

import json

import pytest

from app.significance.artifacts import (
    SCHEMA_VERSION,
    write_ensemble,
    write_leaderboard_markdown,
    write_significance,
)


def test_write_ensemble_atomic_no_partial_files(tmp_path, synthetic_snapshot_dict):
    out = tmp_path / "t1.ensemble.json"
    snap = synthetic_snapshot_dict()
    ensembles = {
        "BTCUSDT": [
            {"run_id": "r1", "architecture": "gru", "hp_hash": "h1", "dsr": 0.9},
        ],
    }
    write_ensemble(snap, ensembles, git_sha="abc", output_path=out)
    assert out.exists(), "ensemble.json should exist after write"
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == [], f"no .tmp files should remain, got: {leftovers}"


def test_write_ensemble_required_keys(tmp_path, synthetic_snapshot_dict):
    out = tmp_path / "t1.ensemble.json"
    snap = synthetic_snapshot_dict()
    ensembles = {
        "BTCUSDT": [
            {"run_id": "r1", "architecture": "gru", "hp_hash": "h1", "dsr": 0.9}
        ]
    }
    payload = write_ensemble(snap, ensembles, git_sha="abc", output_path=out)
    on_disk = json.loads(out.read_text())
    for key in (
        "schema_version",
        "tournament_id",
        "git_sha",
        "created_at",
        "aggregation",
        "ensembles",
    ):
        assert key in on_disk, f"missing required key: {key}"
    assert on_disk["aggregation"] == "mean_log_returns"
    assert on_disk["schema_version"] == SCHEMA_VERSION
    assert on_disk == payload


def test_write_ensemble_no_weights_no_predictions(tmp_path, synthetic_snapshot_dict):
    """D-03: config-by-reference only. No weights/scalers/predictions/model in JSON."""
    out = tmp_path / "t1.ensemble.json"
    snap = synthetic_snapshot_dict()
    ensembles = {
        "BTCUSDT": [
            {"run_id": "r1", "architecture": "gru", "hp_hash": "h1", "dsr": 0.9}
        ]
    }
    write_ensemble(snap, ensembles, git_sha="abc", output_path=out)
    text_lower = out.read_text().lower()
    for forbidden in ("weights", "scaler", "predictions", '"model"'):
        assert forbidden not in text_lower, (
            f"forbidden token leaked into ensemble.json: {forbidden!r}"
        )


def test_write_significance_required_schema(tmp_path, synthetic_snapshot_dict):
    out = tmp_path / "t1.significance.json"
    snap = synthetic_snapshot_dict()
    per_symbol = {
        "BTCUSDT": {
            "sharpe_lift": 0.1,
            "sharpe_pvalue": 0.01,
            "dir_acc_lift": 0.05,
            "dir_acc_pvalue": 0.02,
            "n_oos_bars": 100,
            "block_size": 10,
            "n_resamples": 10000,
            "win_gate_passed": True,
            "n_members": 3,
            "bootstrap_seed": 12345,
        }
    }
    write_significance(
        snap,
        per_symbol,
        git_sha="abc",
        tournaments_evaluated_count=7,
        n_winning_symbols=1,
        output_path=out,
    )
    on_disk = json.loads(out.read_text())
    for key in (
        "per_symbol",
        "baseline",
        "aggregation",
        "git_sha",
        "evaluated_at",
        "tournaments_evaluated_count",
        "n_winning_symbols",
        "schema_version",
        "tournament_id",
    ):
        assert key in on_disk, f"significance.json missing: {key}"
    assert on_disk["baseline"] == "persistence"
    assert on_disk["aggregation"] == "mean_log_returns"
    assert isinstance(on_disk["tournaments_evaluated_count"], int)
    assert isinstance(on_disk["n_winning_symbols"], int)
    assert on_disk["per_symbol"]["BTCUSDT"]["bootstrap_seed"] == 12345


def test_write_leaderboard_markdown_returns_string(tmp_path):
    out = tmp_path / "t1.leaderboard.md"
    md = "# leaderboard\n\n| sym | dsr |\n|-----|-----|\n| BTC | 0.9 |\n"
    returned = write_leaderboard_markdown(md, out)
    assert returned == md
    assert out.read_text() == md
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []


def test_atomic_write_cleans_up_on_serialization_failure(
    tmp_path, monkeypatch, synthetic_snapshot_dict
):
    """If json.dumps blows up after tmp file open, no .tmp file should remain."""
    out = tmp_path / "t1.ensemble.json"
    snap = synthetic_snapshot_dict()
    ensembles = {
        "BTCUSDT": [
            {"run_id": "r1", "architecture": "gru", "hp_hash": "h1", "dsr": 0.9}
        ]
    }

    # Force the underlying json.dumps to raise — mimics serialization failure mid-write.
    import app.significance.artifacts as artifacts_module

    def boom(*_args, **_kwargs):
        raise RuntimeError("synthetic serialization failure")

    monkeypatch.setattr(artifacts_module.json, "dumps", boom)

    with pytest.raises(RuntimeError, match="synthetic"):
        write_ensemble(snap, ensembles, git_sha="abc", output_path=out)

    # No final file written, and no leftover .tmp.
    assert not out.exists()
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == [], f"leftover .tmp files after failure: {leftovers}"
