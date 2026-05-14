"""Unit tests for LeaderboardDB.count_tournaments (D-09)."""

from __future__ import annotations

import json
from pathlib import Path


from app.leaderboard.db import LeaderboardDB, run_migrations
from app.leaderboard.result_schema import validate


MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _success_payload(*, tournament_id: str = "t1", run_id: str = "r1", **overrides):
    base = {
        "status": "success",
        "run_id": run_id,
        "tournament_id": tournament_id,
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


def _insert_run(db: LeaderboardDB, *, tournament_id: str, run_id: str) -> None:
    p = _success_payload(tournament_id=tournament_id, run_id=run_id)
    raw = json.dumps(p).encode()
    _, norm = validate(p, raw)
    db.insert_run(norm)


def test_count_zero_when_empty(tmp_path):
    db_path = tmp_path / "lb.db"
    run_migrations(db_path, MIGRATIONS_DIR)
    db = LeaderboardDB(db_path)
    try:
        assert db.count_tournaments() == 0
    finally:
        db.close()


def test_count_increases_with_distinct_tournaments(tmp_path):
    db_path = tmp_path / "lb.db"
    run_migrations(db_path, MIGRATIONS_DIR)
    db = LeaderboardDB(db_path)
    try:
        db.upsert_tournament("t1", "yaml: stub\n", "abc123", 42)
        db.upsert_tournament("t2", "yaml: stub\n", "abc123", 42)
        _insert_run(db, tournament_id="t1", run_id="r1")
        _insert_run(db, tournament_id="t1", run_id="r2")
        _insert_run(db, tournament_id="t2", run_id="r3")
        assert db.count_tournaments() == 2
    finally:
        db.close()


def test_count_distinct_only(tmp_path):
    db_path = tmp_path / "lb.db"
    run_migrations(db_path, MIGRATIONS_DIR)
    db = LeaderboardDB(db_path)
    try:
        db.upsert_tournament("t1", "yaml: stub\n", "abc123", 42)
        for i in range(5):
            _insert_run(db, tournament_id="t1", run_id=f"r{i}")
        assert db.count_tournaments() == 1
    finally:
        db.close()
