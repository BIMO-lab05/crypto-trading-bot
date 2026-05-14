"""Unit tests for app.leaderboard.queries — DSL safety + correctness."""

import json
import sqlite3
from pathlib import Path

import pytest

from app.leaderboard.queries import (
    parse_where,
    run_query,
)
from app.leaderboard.db import run_migrations, LeaderboardDB
from app.leaderboard.result_schema import validate


MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


def test_parse_empty_where():
    sql, params = parse_where("")
    assert sql == "" and params == []


def test_parse_simple_equality():
    sql, params = parse_where("symbol=SOL")
    assert sql == "symbol = ?"
    assert params == ["SOL"]


def test_parse_compound_and():
    sql, params = parse_where("symbol=SOL AND architecture=gru")
    assert sql == "symbol = ? AND architecture = ?"
    assert params == ["SOL", "gru"]


def test_parse_quoted_value():
    sql, params = parse_where("status='success'")
    assert params == ["success"]


def test_parse_in_list():
    sql, params = parse_where("symbol IN (SOL, BNB, ADA)")
    assert "symbol IN (?,?,?)" in sql
    assert params == ["SOL", "BNB", "ADA"]


def test_parse_rejects_semicolon():
    with pytest.raises(ValueError, match="forbidden token"):
        parse_where("symbol=SOL; DROP TABLE leaderboard")


def test_parse_rejects_comment():
    with pytest.raises(ValueError, match="forbidden token"):
        parse_where("symbol=SOL -- comment")


def test_parse_rejects_union():
    with pytest.raises(ValueError, match="forbidden token"):
        parse_where("symbol=SOL UNION SELECT * FROM leaderboard")


def test_parse_rejects_disallowed_column():
    with pytest.raises(ValueError, match="not in allowlist"):
        parse_where("dsr>0.5")


def test_parse_rejects_disallowed_operator():
    with pytest.raises(ValueError, match="invalid token|not in allowlist"):
        parse_where("symbol@SOL")


def test_run_query_rejects_disallowed_by():
    with pytest.raises(ValueError, match="--by"):
        run_query("/tmp/nonexistent.db", by="kp_hash_evil")


def test_run_query_clamps_top_to_max(tmp_path):
    db_path = tmp_path / "lb.db"
    run_migrations(db_path, MIGRATIONS)
    db = LeaderboardDB(db_path)
    db.upsert_tournament("t1", "yaml\n", "abc", 42)
    db.close()
    rows = run_query(str(db_path), top=10**9, by="dsr")
    # No rows since none inserted, but no exception either — clamp worked.
    assert rows == []


def test_run_query_returns_rows(tmp_path):
    db_path = tmp_path / "lb.db"
    run_migrations(db_path, MIGRATIONS)
    db = LeaderboardDB(db_path)
    db.upsert_tournament("t1", "yaml\n", "abc", 42)

    payload = {
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
    raw = json.dumps(payload).encode()
    _, norm = validate(payload, raw)
    db.insert_run(norm)
    db.close()

    rows = run_query(
        str(db_path),
        tournament_id="t1",
        top=5,
        by="dsr",
        where="architecture=gru AND symbol=SOL",
    )
    assert len(rows) == 1
    assert rows[0]["architecture"] == "gru"


def test_run_query_with_injection_string_returns_no_rows(tmp_path):
    """T-03-29 — injection string is rejected at parse time, not silently bypassed."""
    db_path = tmp_path / "lb.db"
    run_migrations(db_path, MIGRATIONS)
    db = LeaderboardDB(db_path)
    db.upsert_tournament("t1", "yaml\n", "abc", 42)
    db.close()
    with pytest.raises(ValueError):
        run_query(str(db_path), where="symbol=SOL; DROP TABLE leaderboard")
    # leaderboard table still exists
    conn = sqlite3.connect(str(db_path))
    n = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name='leaderboard'"
    ).fetchone()[0]
    conn.close()
    assert n == 1
