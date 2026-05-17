"""Unit tests for ``scripts.forward_paper_test.run_evidence_loop`` (MLGATE-01).

Covers the 8 behaviours from Plan 09-01 Task 3 (idempotency, accrual window
skip, resume, dry-run, paper-only refusal). All tests are host-runnable:

  pytest scripts/forward_paper_test/tests/test_run_evidence_loop.py -xvs

Fixtures build a fresh SQLite leaderboard per-test via the canonical migration
runner ``services/tournament-harness/app/leaderboard/db.py::run_migrations``
(idempotent — applying twice does NOT error). The runner is the project's
single source of truth for schema application; this test exercises both
migration 0001 and 0002 via the runner so the test surface matches production
boot semantics.

The logged literal ``MLGATE_EVIDENCE_LOOP action=<value> reason=<reason>`` is a
contract surface (Plan 09-03 digest will read it). Most tests assert on the
literal via ``caplog``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np

# Path-import shim: make ``services/tournament-harness`` importable as ``app.*``
# so the canonical migration runner can be reached without an editable install.
_REPO = Path(__file__).resolve().parents[3]
_TOURNAMENT_HARNESS_ROOT = _REPO / "services" / "tournament-harness"
if str(_TOURNAMENT_HARNESS_ROOT) not in sys.path:
    sys.path.insert(0, str(_TOURNAMENT_HARNESS_ROOT))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_MIGRATIONS_DIR = _REPO / "services" / "tournament-harness" / "migrations"


def _build_leaderboard_db(tmp_path: Path) -> Path:
    """Create an empty leaderboard DB with migrations 0001 + 0002 applied.

    Uses the canonical runner ``run_migrations`` (idempotent — skips
    already-applied versions via schema_version). Returns the DB path.
    """
    from app.leaderboard.db import run_migrations  # type: ignore

    db_path = tmp_path / "leaderboard.db"
    run_migrations(db_path, _MIGRATIONS_DIR)
    return db_path


def _insert_row(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    run_date_iso: Optional[str],
    psr_ci_published: int = 0,
    dsr: float = 0.97,
    architecture: str = "gru",
    symbol: str = "BTCUSDT",
    horizon: int = 5,
    target_mode: str = "log_returns",
    hp_hash: str = "deadbeef",
    status: str = "success",
) -> None:
    """Insert a single leaderboard row satisfying all 0001 NOT NULL constraints.

    Variable fields are exposed via kwargs so tests can build groups that
    share a natural key (architecture, symbol, horizon, target_mode, hp_hash)
    but differ on run_id / run_date — that shape drives the per-group 7-day
    accrual rule.
    """
    conn.execute(
        "INSERT INTO leaderboard ("
        " run_id, tournament_id, architecture, symbol, horizon, target_mode,"
        " hp_hash, dsr, git_sha, tournament_start_ts, status,"
        " run_date, psr_ci_published"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            run_id,
            "t-test",
            architecture,
            symbol,
            horizon,
            target_mode,
            hp_hash,
            dsr,
            "abc1234",
            "2026-05-09T00:00:00Z",
            status,
            run_date_iso,
            psr_ci_published,
        ),
    )
    conn.commit()


def _returns_json(tmp_path: Path, *, n: int = 40, seed: int = 11) -> Path:
    """Write a deterministic ``{"returns": [...]}`` JSON; return the directory path.

    The directory is returned (not the file path) so callers can pass it
    straight to ``--returns-source`` or the function arg. ``tmp_path`` may
    be a sub-path that does not yet exist — created here.
    """
    tmp_path = Path(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    returns = rng.normal(loc=0.001, scale=0.02, size=n)
    run_json = {
        "run_id": "rid-fixture",
        "flag": "enable_vol_targeting",
        "returns": returns.tolist(),
    }
    (tmp_path / "run.json").write_text(json.dumps(run_json))
    return tmp_path


# Reference clock used by every deterministic test — keeps window math stable
# across re-runs. Anchored well after the 7-day accrual window of the
# 2026-05-09 tournament_start_ts in _insert_row.
_NOW = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Test 1: empty DB skips cleanly
# ---------------------------------------------------------------------------


def test_evidence_loop_empty_db_skips_cleanly(tmp_path, caplog):
    """Empty leaderboard: returns {published:0, skipped:0, errors:0}, exits 0."""
    from scripts.forward_paper_test.run_evidence_loop import run_evidence_loop

    db_path = _build_leaderboard_db(tmp_path)

    caplog.set_level("INFO")
    result = run_evidence_loop(db_path=str(db_path), now=_NOW)

    assert result == {"published": 0, "skipped": 0, "errors": 0}
    assert any(
        "MLGATE_EVIDENCE_LOOP action=skip reason=no_rows" in rec.message
        for rec in caplog.records
    ), f"expected no_rows skip log; got {[r.message for r in caplog.records]}"


# ---------------------------------------------------------------------------
# Test 2: window-open skip (no publish)
# ---------------------------------------------------------------------------


def test_evidence_loop_window_open_skips_without_publish(tmp_path, caplog):
    """1 row with run_date = now-3d: returns {published:0, skipped:1}; no UPDATE."""
    from scripts.forward_paper_test.run_evidence_loop import run_evidence_loop

    db_path = _build_leaderboard_db(tmp_path)
    run_date = (_NOW - timedelta(days=3)).isoformat()
    conn = sqlite3.connect(str(db_path))
    try:
        _insert_row(conn, run_id="rid-1", run_date_iso=run_date)
    finally:
        conn.close()

    caplog.set_level("INFO")
    result = run_evidence_loop(db_path=str(db_path), now=_NOW)

    assert result["published"] == 0
    assert result["skipped"] == 1
    assert result["errors"] == 0

    # The row's psr_ci_published flag is still 0 (no UPDATE happened).
    conn = sqlite3.connect(str(db_path))
    try:
        published = conn.execute(
            "SELECT psr_ci_published FROM leaderboard WHERE run_id=?", ("rid-1",)
        ).fetchone()[0]
    finally:
        conn.close()
    assert published == 0, "row was published despite window being open"

    assert any(
        "MLGATE_EVIDENCE_LOOP action=skip reason=accrual_window_open" in rec.message
        for rec in caplog.records
    ), f"expected accrual_window_open log; got {[r.message for r in caplog.records]}"


# ---------------------------------------------------------------------------
# Test 3: window-closed publishes
# ---------------------------------------------------------------------------


def test_evidence_loop_window_closed_publishes(tmp_path, caplog):
    """1 row with run_date = now-8d + returns array: row flips to psr_ci_published=1."""
    from scripts.forward_paper_test.run_evidence_loop import run_evidence_loop

    db_path = _build_leaderboard_db(tmp_path)
    run_date = (_NOW - timedelta(days=8)).isoformat()
    conn = sqlite3.connect(str(db_path))
    try:
        _insert_row(conn, run_id="rid-eligible", run_date_iso=run_date)
    finally:
        conn.close()

    returns_dir = _returns_json(tmp_path / "ret1")

    caplog.set_level("INFO")
    result = run_evidence_loop(
        db_path=str(db_path), returns_source=returns_dir, now=_NOW
    )

    assert result["published"] == 1
    assert result["skipped"] == 0
    assert result["errors"] == 0

    conn = sqlite3.connect(str(db_path))
    try:
        published = conn.execute(
            "SELECT psr_ci_published FROM leaderboard WHERE run_id=?",
            ("rid-eligible",),
        ).fetchone()[0]
    finally:
        conn.close()
    assert published == 1, "row not flipped to psr_ci_published=1"

    assert any(
        "MLGATE_EVIDENCE_LOOP action=publish run_id=rid-eligible" in rec.message
        for rec in caplog.records
    )


# ---------------------------------------------------------------------------
# Test 4: idempotent two runs (same row counts; no re-publish)
# ---------------------------------------------------------------------------


def test_evidence_loop_idempotent_two_runs(tmp_path, caplog):
    """Seed 3 eligible rows + 1 already-published row; run twice, results identical."""
    from scripts.forward_paper_test.run_evidence_loop import run_evidence_loop

    db_path = _build_leaderboard_db(tmp_path)
    run_date = (_NOW - timedelta(days=8)).isoformat()
    conn = sqlite3.connect(str(db_path))
    try:
        # 3 eligible rows in distinct natural-key groups (different hp_hash) so
        # the per-group 7-day window applies to each independently.
        for i in range(3):
            _insert_row(
                conn,
                run_id=f"rid-elig-{i}",
                run_date_iso=run_date,
                hp_hash=f"hp{i}",
            )
        # 1 already-published row.
        _insert_row(
            conn,
            run_id="rid-already",
            run_date_iso=run_date,
            psr_ci_published=1,
            hp_hash="hp-already",
        )
    finally:
        conn.close()

    returns_dir = _returns_json(tmp_path / "ret2")

    caplog.set_level("INFO")
    result1 = run_evidence_loop(
        db_path=str(db_path), returns_source=returns_dir, now=_NOW
    )

    # All 3 eligible rows published; the already-published row was never read.
    assert result1["published"] == 3
    assert result1["skipped"] == 0

    # Snapshot the published-row set after run 1.
    conn = sqlite3.connect(str(db_path))
    try:
        published_after_1 = {
            row[0]
            for row in conn.execute(
                "SELECT run_id FROM leaderboard WHERE psr_ci_published=1"
            )
        }
    finally:
        conn.close()
    assert published_after_1 == {
        "rid-elig-0",
        "rid-elig-1",
        "rid-elig-2",
        "rid-already",
    }

    # Run 2: same DB, no eligible rows remain → published=0.
    caplog.clear()
    result2 = run_evidence_loop(
        db_path=str(db_path), returns_source=returns_dir, now=_NOW
    )
    assert result2["published"] == 0, (
        "idempotency violated — already-published rows re-flipped"
    )
    assert result2["skipped"] == 0

    # The published-set is identical across runs.
    conn = sqlite3.connect(str(db_path))
    try:
        published_after_2 = {
            row[0]
            for row in conn.execute(
                "SELECT run_id FROM leaderboard WHERE psr_ci_published=1"
            )
        }
    finally:
        conn.close()
    assert published_after_2 == published_after_1

    # Run 2 sees no eligible rows — emits no_rows skip log.
    assert any(
        "MLGATE_EVIDENCE_LOOP action=skip reason=no_rows" in rec.message
        for rec in caplog.records
    )


# ---------------------------------------------------------------------------
# Test 5: two runs same row count (driver never INSERTs/DELETEs)
# ---------------------------------------------------------------------------


def test_evidence_loop_two_runs_same_row_count(tmp_path):
    """COUNT(*) after run-1 == COUNT(*) after run-2 — driver never INSERTs/DELETEs."""
    from scripts.forward_paper_test.run_evidence_loop import run_evidence_loop

    db_path = _build_leaderboard_db(tmp_path)
    run_date = (_NOW - timedelta(days=8)).isoformat()
    conn = sqlite3.connect(str(db_path))
    try:
        for i in range(5):
            _insert_row(
                conn,
                run_id=f"rid-count-{i}",
                run_date_iso=run_date,
                hp_hash=f"hp-c{i}",
            )
    finally:
        conn.close()

    returns_dir = _returns_json(tmp_path / "ret3")

    def _count() -> int:
        c = sqlite3.connect(str(db_path))
        try:
            return c.execute("SELECT COUNT(*) FROM leaderboard").fetchone()[0]
        finally:
            c.close()

    n_before = _count()
    assert n_before == 5

    run_evidence_loop(db_path=str(db_path), returns_source=returns_dir, now=_NOW)
    n_after_1 = _count()
    run_evidence_loop(db_path=str(db_path), returns_source=returns_dir, now=_NOW)
    n_after_2 = _count()

    assert n_before == n_after_1 == n_after_2 == 5, (
        f"row count changed across runs: before={n_before}, after_1={n_after_1}, "
        f"after_2={n_after_2}"
    )


# ---------------------------------------------------------------------------
# Test 6: resume from partial state (3 published, N-3 to process)
# ---------------------------------------------------------------------------


def test_evidence_loop_resume_from_partial_state(tmp_path, caplog):
    """Seed N rows, mark first 3 already published; driver processes only the rest."""
    from scripts.forward_paper_test.run_evidence_loop import run_evidence_loop

    db_path = _build_leaderboard_db(tmp_path)
    run_date_old = (_NOW - timedelta(days=8)).isoformat()
    conn = sqlite3.connect(str(db_path))
    try:
        # First 3: already published.
        for i in range(3):
            _insert_row(
                conn,
                run_id=f"rid-done-{i}",
                run_date_iso=run_date_old,
                psr_ci_published=1,
                hp_hash=f"hp-done-{i}",
            )
        # Next 4: not yet published, window closed.
        for i in range(4):
            _insert_row(
                conn,
                run_id=f"rid-todo-{i}",
                run_date_iso=run_date_old,
                psr_ci_published=0,
                hp_hash=f"hp-todo-{i}",
            )
    finally:
        conn.close()

    returns_dir = _returns_json(tmp_path / "ret4")

    caplog.set_level("INFO")
    result = run_evidence_loop(
        db_path=str(db_path), returns_source=returns_dir, now=_NOW
    )

    # Only the 4 unpublished rows were processed; the 3 done rows were never re-read.
    assert result["published"] == 4
    assert result["skipped"] == 0

    publish_logs = [
        rec.message
        for rec in caplog.records
        if "MLGATE_EVIDENCE_LOOP action=publish" in rec.message
    ]
    assert len(publish_logs) == 4, (
        f"expected 4 publish logs (only the todo rows); got {len(publish_logs)}: {publish_logs}"
    )
    # No publish log mentions a done row.
    for msg in publish_logs:
        for i in range(3):
            assert f"rid-done-{i}" not in msg, (
                f"already-published row re-published: {msg}"
            )


# ---------------------------------------------------------------------------
# Test 7: dry-run does not mutate
# ---------------------------------------------------------------------------


def test_evidence_loop_dry_run_does_not_mutate(tmp_path, caplog):
    """dry_run=True on a fully-eligible fixture: no UPDATEs; publish logs emitted."""
    from scripts.forward_paper_test.run_evidence_loop import run_evidence_loop

    db_path = _build_leaderboard_db(tmp_path)
    run_date = (_NOW - timedelta(days=8)).isoformat()
    conn = sqlite3.connect(str(db_path))
    try:
        for i in range(2):
            _insert_row(
                conn,
                run_id=f"rid-dry-{i}",
                run_date_iso=run_date,
                hp_hash=f"hp-dry-{i}",
            )
    finally:
        conn.close()

    returns_dir = _returns_json(tmp_path / "ret5")

    caplog.set_level("INFO")
    result = run_evidence_loop(
        db_path=str(db_path),
        dry_run=True,
        returns_source=returns_dir,
        now=_NOW,
    )

    # Counter reflects what WOULD have been published.
    assert result["published"] == 2
    assert result["errors"] == 0

    # But the rows on disk are untouched.
    conn = sqlite3.connect(str(db_path))
    try:
        flags = [
            row[0]
            for row in conn.execute(
                "SELECT psr_ci_published FROM leaderboard ORDER BY run_id"
            )
        ]
    finally:
        conn.close()
    assert flags == [0, 0], f"dry-run mutated the DB: psr_ci_published={flags}"

    # Publish logs still emitted (operator sees what would happen).
    publish_logs = [
        rec.message
        for rec in caplog.records
        if "MLGATE_EVIDENCE_LOOP action=publish" in rec.message
    ]
    assert len(publish_logs) == 2
    # Dry-run markers in the log line.
    for msg in publish_logs:
        assert "DRY_RUN" in msg, f"dry-run publish log missing DRY_RUN marker: {msg}"


# ---------------------------------------------------------------------------
# Test 8: refuses LIVE mode
# ---------------------------------------------------------------------------


def test_evidence_loop_refuses_live_mode(tmp_path, monkeypatch):
    """TRADING_MODE=LIVE → SystemExit(1) with 'TRADING_MODE=LIVE' / 'paper-only' in stderr."""
    # Subprocess invocation is the most faithful test: the precondition is a
    # sys.exit(1), and pytest's monkeypatch leaves Python state across tests
    # — invoking the module fresh isolates the exit-code check completely.
    env = {**os.environ, "TRADING_MODE": "LIVE"}
    db_path = tmp_path / "never-touched.db"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.forward_paper_test.run_evidence_loop",
            "--db-path",
            str(db_path),
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        cwd=str(_REPO),
        env=env,
    )
    assert result.returncode == 1, (
        f"expected exit 1 for TRADING_MODE=LIVE; got {result.returncode}\n"
        f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
    )
    combined = (result.stdout + result.stderr).lower()
    assert "trading_mode=live" in combined or "paper-only" in combined, (
        f"stderr should mention TRADING_MODE=LIVE or paper-only; got: {result.stderr!r}"
    )
    # The DB was never opened (no rows could have leaked out).
    assert not db_path.exists(), "DB was created despite the precondition refusing"
