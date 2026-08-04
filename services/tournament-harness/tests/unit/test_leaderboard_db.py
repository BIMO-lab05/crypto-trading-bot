"""Unit tests for app.leaderboard.db."""

import json
import os
import sqlite3
from pathlib import Path

import pytest

from app.leaderboard.db import run_migrations, LeaderboardDB
from app.leaderboard.result_schema import validate


MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _success_payload(**overrides):
    base = {
        "status": "success",
        "run_id": "r1",
        "tournament_id": "t1",
        "architecture": "gru",
        "symbol": "SOLUSDT",
        "horizon": 5,
        "target_mode": "log_returns",
        "hp_hash": "deadbeef",
        "git_sha": "abc123",
        "tournament_start_ts": "2026-05-08T00:00:00",
        "train_window_includes_contaminated": 0,
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


def test_run_migrations_creates_tables(tmp_path):
    db_path = tmp_path / "lb.db"
    run_migrations(db_path, MIGRATIONS_DIR)
    conn = sqlite3.connect(str(db_path))
    tables = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    conn.close()
    assert {"leaderboard", "tournaments", "schema_version"} <= tables


def test_run_migrations_is_idempotent(tmp_path):
    db_path = tmp_path / "lb.db"
    run_migrations(db_path, MIGRATIONS_DIR)
    run_migrations(db_path, MIGRATIONS_DIR)  # second apply must not error
    db = LeaderboardDB(db_path)
    assert db.schema_version() >= 1
    db.close()


def test_run_migrations_sets_0600_on_fresh_create(tmp_path):
    db_path = tmp_path / "lb.db"
    run_migrations(db_path, MIGRATIONS_DIR)
    if os.name != "nt":
        mode = os.stat(db_path).st_mode & 0o777
        assert mode == 0o600


def test_insert_and_list_run(tmp_path):
    db_path = tmp_path / "lb.db"
    run_migrations(db_path, MIGRATIONS_DIR)
    db = LeaderboardDB(db_path)
    db.upsert_tournament("t1", "yaml: stub\n", "abc123", 42)
    p = _success_payload()
    raw = json.dumps(p).encode()
    _, norm = validate(p, raw)
    db.insert_run(norm)
    rows = db.list_runs(tournament_id="t1")
    assert len(rows) == 1
    assert rows[0]["architecture"] == "gru"
    assert rows[0]["status"] == "success"
    db.close()


def test_insert_failed_run(tmp_path):
    db_path = tmp_path / "lb.db"
    run_migrations(db_path, MIGRATIONS_DIR)
    db = LeaderboardDB(db_path)
    db.upsert_tournament("t1", "yaml\n", "abc", 42)
    p = _success_payload(status="failed", run_id="r2")
    p["reason"] = "nan_loss"
    raw = json.dumps(p).encode()
    _, norm = validate(p, raw)
    db.insert_run(norm)
    rows = db.list_runs(tournament_id="t1", status="failed")
    assert len(rows) == 1
    assert rows[0]["failure_reason"] == "nan_loss"
    db.close()


def test_list_runs_with_sql_injection_string(tmp_path):
    """T-03-08 — parameterised query refuses to interpret operator strings as SQL."""
    db_path = tmp_path / "lb.db"
    run_migrations(db_path, MIGRATIONS_DIR)
    db = LeaderboardDB(db_path)
    db.upsert_tournament("t1", "yaml\n", "abc", 42)
    p = _success_payload()
    raw = json.dumps(p).encode()
    _, norm = validate(p, raw)
    db.insert_run(norm)
    # Injection attempt — the ? placeholder treats the whole string as a literal symbol value.
    rows = db.list_runs(symbol="'; DROP TABLE leaderboard; --")
    assert rows == []
    # Verify the table still exists
    conn = sqlite3.connect(str(db_path))
    n = conn.execute("SELECT COUNT(*) FROM leaderboard").fetchone()[0]
    conn.close()
    assert n == 1


def test_check_constraint_rejects_bad_failure_reason(tmp_path):
    db_path = tmp_path / "lb.db"
    run_migrations(db_path, MIGRATIONS_DIR)
    db = LeaderboardDB(db_path)
    db.upsert_tournament("t1", "yaml\n", "abc", 42)
    # Bypass result_schema by hand-rolling a row with an invalid enum value
    # Don't go through validate() — we want to verify the SQL CHECK fires
    with pytest.raises(sqlite3.IntegrityError):
        db.conn.execute(
            "INSERT INTO leaderboard "
            "(run_id, tournament_id, architecture, symbol, horizon, target_mode, hp_hash, "
            " git_sha, tournament_start_ts, status, failure_reason) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                "r3",
                "t1",
                "gru",
                "SOLUSDT",
                5,
                "log_returns",
                "x",
                "g",
                "ts",
                "failed",
                "BOGUS_REASON",
            ),
        )
    db.close()


def test_schema_version_returns_max(tmp_path):
    db_path = tmp_path / "lb.db"
    run_migrations(db_path, MIGRATIONS_DIR)
    db = LeaderboardDB(db_path)
    # schema_version() returns MAX(version) — must equal the highest migration
    # file on disk (currently 0002_mlgate_evidence_columns.sql). Update this
    # alongside any new ####_*.sql added to services/tournament-harness/migrations/.
    expected = max(
        int(p.stem.split("_", 1)[0])
        for p in MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql")
    )
    assert db.schema_version() == expected
    db.close()
