"""Unit tests for app.leaderboard.snapshot.export_snapshot."""

import json
from pathlib import Path

import pytest

from app.leaderboard.db import run_migrations, LeaderboardDB
from app.leaderboard.snapshot import export_snapshot
from app.leaderboard.result_schema import validate


MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


def _success_payload(**overrides):
    base = {
        "status": "success",
        "run_id": "r1",
        "tournament_id": "t1",
        "architecture": "gru",
        "symbol": "SOL",
        "horizon": 5,
        "target_mode": "log_returns",
        "hp_hash": "h1",
        "git_sha": "abc",
        "tournament_start_ts": "ts",
        "metrics": {
            "r2_returns": 0.05,
            "dir_acc_corrected": 0.55,
            "oos_sharpe": 0.8,
            "psr": 0.7,
            "dsr": 0.55,
            "cpcv_dsr": 0.5,
            "train_seconds": 120.0,
        },
    }
    base.update(overrides)
    return base


def test_export_snapshot_round_trip(tmp_path):
    db_path = tmp_path / "lb.db"
    run_migrations(db_path, MIGRATIONS)
    db = LeaderboardDB(db_path)
    db.upsert_tournament("t1", "tournament_id: t1\n", "abc", 42)
    payload = _success_payload()
    _, norm = validate(payload, json.dumps(payload).encode())
    db.insert_run(norm)
    db.close()

    out = tmp_path / "snap.json"
    snap = export_snapshot(db_path, "t1", out)
    assert out.exists()
    loaded = json.loads(out.read_text())
    assert loaded["tournament_id"] == "t1"
    assert loaded["summary"]["n_rows"] == 1
    assert loaded["summary"]["n_success"] == 1


def test_export_snapshot_unknown_tournament_raises(tmp_path):
    db_path = tmp_path / "lb.db"
    run_migrations(db_path, MIGRATIONS)
    out = tmp_path / "snap.json"
    with pytest.raises(ValueError, match="not found"):
        export_snapshot(db_path, "no_such_tournament", out)


def test_export_snapshot_writes_atomically(tmp_path):
    db_path = tmp_path / "lb.db"
    run_migrations(db_path, MIGRATIONS)
    db = LeaderboardDB(db_path)
    db.upsert_tournament("t1", "config\n", "abc", 42)
    db.close()
    out = tmp_path / "snap.json"
    export_snapshot(db_path, "t1", out)
    # No leftover .tmp files
    leftovers = list(tmp_path.glob("snapshot.*.json.tmp"))
    assert leftovers == []


def test_export_snapshot_includes_failed_rows(tmp_path):
    db_path = tmp_path / "lb.db"
    run_migrations(db_path, MIGRATIONS)
    db = LeaderboardDB(db_path)
    db.upsert_tournament("t1", "config\n", "abc", 42)
    payload = _success_payload(status="failed")
    payload["reason"] = "nan_loss"
    _, norm = validate(payload, json.dumps(payload).encode())
    db.insert_run(norm)
    db.close()
    out = tmp_path / "snap.json"
    snap = export_snapshot(db_path, "t1", out)
    assert snap["summary"]["n_failed"] == 1


def test_export_snapshot_handles_no_rows(tmp_path):
    db_path = tmp_path / "lb.db"
    run_migrations(db_path, MIGRATIONS)
    db = LeaderboardDB(db_path)
    db.upsert_tournament("t1", "config\n", "abc", 42)
    db.close()
    out = tmp_path / "snap.json"
    snap = export_snapshot(db_path, "t1", out)
    assert snap["summary"]["n_rows"] == 0
    assert snap["rows"] == []
