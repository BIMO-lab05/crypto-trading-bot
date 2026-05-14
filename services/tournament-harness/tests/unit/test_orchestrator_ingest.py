"""Unit tests for app.orchestrator.ingest."""

import json
from pathlib import Path


from app.leaderboard.db import run_migrations, LeaderboardDB
from app.orchestrator.ingest import (
    read_and_validate_result,
    ingest_run,
    _scrub,
    MAX_RESULT_BYTES,
)


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
        "hp_hash": "deadbeef",
        "git_sha": "abc",
        "tournament_start_ts": "2026-05-08T00:00:00",
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


def _spec(**overrides):
    base = {
        "run_id": "r1",
        "tournament_id": "t1",
        "architecture": "gru",
        "symbol": "SOL",
        "horizon": 5,
        "target_mode": "log_returns",
        "hp_hash": "deadbeef",
        "git_sha": "abc",
        "tournament_start_ts": "2026-05-08T00:00:00",
    }
    base.update(overrides)
    return base


def test_read_missing_returns_none(tmp_path):
    payload, err = read_and_validate_result(tmp_path / "no_such.json")
    assert payload is None and err is None


def test_read_oversized_aborts_before_load(tmp_path):
    p = tmp_path / "huge.json"
    p.write_bytes(b"x" * (MAX_RESULT_BYTES + 1))
    payload, err = read_and_validate_result(p)
    assert payload is None
    assert "oversized" in err


def test_read_invalid_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{ not json")
    payload, err = read_and_validate_result(p)
    assert payload is None
    assert "json parse" in err


def test_read_valid_success_payload(tmp_path):
    p = tmp_path / "ok.json"
    p.write_text(json.dumps(_success_payload()))
    payload, err = read_and_validate_result(p)
    assert err is None
    assert payload["status"] == "success"


def test_read_schema_invalid_payload(tmp_path):
    p = tmp_path / "bad_schema.json"
    bad = _success_payload(architecture="random_forest")
    p.write_text(json.dumps(bad))
    payload, err = read_and_validate_result(p)
    # payload is parseable JSON but invalid schema — payload returned + error
    assert payload is not None
    assert "invalid architecture" in err


def test_ingest_success_inserts_success_row(tmp_path):
    db_path = tmp_path / "lb.db"
    run_migrations(db_path, MIGRATIONS)
    db = LeaderboardDB(db_path)
    db.upsert_tournament("t1", "yaml\n", "abc", 42)

    rp = tmp_path / "result.json"
    rp.write_text(json.dumps(_success_payload()))

    container_state = {"ExitCode": 0, "OOMKilled": False, "TimedOut": False}
    reason = ingest_run(db, _spec(), container_state, rp)
    assert reason == ""

    rows = db.list_runs(tournament_id="t1")
    assert len(rows) == 1
    assert rows[0]["status"] == "success"
    db.close()


def test_ingest_oom_inserts_failed_row(tmp_path):
    db_path = tmp_path / "lb.db"
    run_migrations(db_path, MIGRATIONS)
    db = LeaderboardDB(db_path)
    db.upsert_tournament("t1", "yaml\n", "abc", 42)

    rp = tmp_path / "result.json"  # not created
    container_state = {"ExitCode": 137, "OOMKilled": True, "TimedOut": False}
    reason = ingest_run(db, _spec(), container_state, rp)
    assert reason == "oom_killed"

    rows = db.list_runs(tournament_id="t1", status="failed")
    assert len(rows) == 1
    assert rows[0]["failure_reason"] == "oom_killed"
    db.close()


def test_ingest_timeout_inserts_failed_row(tmp_path):
    db_path = tmp_path / "lb.db"
    run_migrations(db_path, MIGRATIONS)
    db = LeaderboardDB(db_path)
    db.upsert_tournament("t1", "yaml\n", "abc", 42)

    rp = tmp_path / "result.json"
    container_state = {"ExitCode": -1, "OOMKilled": False, "TimedOut": True}
    reason = ingest_run(db, _spec(), container_state, rp)
    assert reason == "timeout"
    db.close()


def test_ingest_runner_nan_loss(tmp_path):
    db_path = tmp_path / "lb.db"
    run_migrations(db_path, MIGRATIONS)
    db = LeaderboardDB(db_path)
    db.upsert_tournament("t1", "yaml\n", "abc", 42)

    rp = tmp_path / "result.json"
    rp.write_text(json.dumps(_success_payload(status="failed", reason="nan_loss")))
    container_state = {"ExitCode": 0, "OOMKilled": False, "TimedOut": False}
    reason = ingest_run(db, _spec(), container_state, rp)
    assert reason == "nan_loss"
    db.close()


def test_ingest_scrubs_passwords_in_stderr_tail(tmp_path):
    db_path = tmp_path / "lb.db"
    run_migrations(db_path, MIGRATIONS)
    db = LeaderboardDB(db_path)
    db.upsert_tournament("t1", "yaml\n", "abc", 42)

    rp = tmp_path / "result.json"
    container_state = {"ExitCode": 1, "OOMKilled": False, "TimedOut": False}
    tail = "ERROR: connecting with TIMESCALE_PASSWORD=hunter2 and host=timescaledb"
    ingest_run(db, _spec(), container_state, rp, stderr_tail=tail)

    rows = db.list_runs(tournament_id="t1", status="failed")
    persisted = rows[0]["failure_stderr_tail"]
    assert "hunter2" not in persisted
    assert "TIMESCALE_PASSWORD=***" in persisted
    db.close()


def test_scrub_pattern_handles_multiple_creds():
    s = "TIMESCALE_PASSWORD=hunter2 ... TOURNAMENT_READER_PASSWORD=letmein"
    out = _scrub(s)
    assert "hunter2" not in out and "letmein" not in out
    assert "TIMESCALE_PASSWORD=***" in out and "TOURNAMENT_READER_PASSWORD=***" in out


def test_scrub_none_returns_none():
    assert _scrub(None) is None
