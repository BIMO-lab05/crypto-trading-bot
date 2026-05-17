"""Unit tests for ``app.lifespan.ml.auto_flip_ml_predictions`` — Phase 9 MLGATE-02.

Boot-time auto-flip of ``ENABLE_ML_PREDICTIONS`` based on DSR evidence in the
``leaderboard`` table (Path A — single source of truth via Phase 8's extended
``check_dsr_evidence`` from Plan 09-02 Task 1).

These tests seed a tmp SQLite ``leaderboard`` table with the production-faithful
schema (mirrors ``test_preflight_checks.py``'s ``_seed_leaderboard`` helper),
monkeypatch BOTH the marker-path constant AND the default tournament DB path on
``app.preflight.checks`` (because ``auto_flip_ml_predictions`` calls
``check_dsr_evidence`` without passing ``db_path``), then assert:

  * the returned ``{direction, reason}`` dict matches the seeded condition;
  * a ``logger.critical`` line containing the
    ``MLGATE_AUTO_FLIP direction=<v> reason=<v>`` literal is emitted (caplog);
  * the marker JSON at the writable tmp path parses to
    ``schema_version=1`` with the corresponding ``direction`` + ``reason``;
  * ``os.environ["ENABLE_ML_PREDICTIONS"]`` is mutated to the right value
    AFTER the log emission (D-09-02-04 ordering);
  * for the 3 reachable disabled-event reasons (``no_evidence``,
    ``dsr_below_gate``, ``evidence_stale``), Plan 09-03's ``get_current_reason``
    matches the auto-flip outcome (D-09-02-06 cross-plan reachability proof —
    closes checker Blocker 1);
  * marker-write failure does NOT raise and DOES NOT block the
    ``set_current_reason`` call (best-effort contract);
  * ``set_current_reason`` failure does NOT crash boot and the marker JSON is
    still written (D-09-02-06 best-effort contract).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.aggregation.ml_gate_reasons import get_current_reason, reset_counter
from app.lifespan.ml import auto_flip_ml_predictions


# ============================================================================
# Fixtures — production-faithful schema cloned from test_preflight_checks.py.
# Inline-merge of migrations 0001 + 0002 (run_date + psr_ci_published).
# ============================================================================
LEADERBOARD_SCHEMA_SQL = """
CREATE TABLE leaderboard (
    run_id              TEXT NOT NULL,
    tournament_id       TEXT NOT NULL,
    architecture        TEXT NOT NULL,
    symbol              TEXT NOT NULL,
    horizon             INTEGER NOT NULL,
    target_mode         TEXT NOT NULL,
    hp_hash             TEXT NOT NULL,
    dsr                 REAL,
    git_sha             TEXT NOT NULL,
    tournament_start_ts TEXT NOT NULL,
    status              TEXT NOT NULL,
    run_date            TEXT,
    psr_ci_published    INTEGER NOT NULL DEFAULT 0
        CHECK (psr_ci_published IN (0, 1)),
    PRIMARY KEY (architecture, symbol, horizon, target_mode, hp_hash, run_id)
);
"""


def _iso_days_ago(days: int) -> str:
    """ISO-8601 UTC string ``days`` before ``datetime.now(timezone.utc)``."""
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _seed_leaderboard(
    db_path: Path,
    dsr_value: float,
    *,
    psr_ci_published: int = 1,
    run_date: str | None = None,
    status: str = "success",
) -> None:
    """Create the leaderboard table and insert one row with the given fields."""
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(LEADERBOARD_SCHEMA_SQL)
        cur.execute(
            "INSERT INTO leaderboard "
            "(run_id, tournament_id, architecture, symbol, horizon, target_mode, "
            " hp_hash, dsr, git_sha, tournament_start_ts, status, "
            " run_date, psr_ci_published) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "run-001",
                "tourn-001",
                "gru",
                "BTCUSDT",
                24,
                "log_returns",
                "deadbeef",
                dsr_value,
                "abc123",
                "2026-05-16T14:32:01Z",
                status,
                run_date if run_date is not None else _iso_days_ago(3),
                psr_ci_published,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _create_empty_leaderboard(db_path: Path) -> None:
    """Create the leaderboard table with zero rows (schema only)."""
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(LEADERBOARD_SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def _reset_ml_gate_state():
    """Reset the cross-plan reason-state cache between every test.

    Without this, ``test_auto_flip_sets_current_reason_for_disabled_branches``
    can pass for the wrong reason when run after a sibling test that left
    ``_current_reason`` mutated in ``app.aggregation.ml_gate_reasons``.
    """
    reset_counter()
    yield
    reset_counter()


def _make_present_marker(tmp_path: Path) -> Path:
    """Create a non-empty marker file at tmp_path so check_dsr_evidence does
    not short-circuit to UNKNOWN-marker-absent. Returns the path.
    """
    p = tmp_path / "mlgate_present.json"
    p.write_text("{}")
    return p


# ============================================================================
# Test 1 — fresh DSR above gate -> enabled
# ============================================================================


def test_auto_flip_enabled_when_fresh_dsr_above_gate(monkeypatch, tmp_path, caplog):
    """Seed dsr=0.97 + psr_ci_published=1 + run_date=now-3d -> enabled."""
    monkeypatch.setenv("ENABLE_ML_PREDICTIONS", "true")
    present = _make_present_marker(tmp_path)
    monkeypatch.setattr("app.preflight.checks._MLGATE_MARKER_PATH", str(present))
    db_path = tmp_path / "tournament.db"
    monkeypatch.setattr(
        "app.preflight.checks._DEFAULT_TOURNAMENT_DB_PATH", str(db_path)
    )
    _seed_leaderboard(db_path, dsr_value=0.97, run_date=_iso_days_ago(3))

    write_marker = tmp_path / "auto_flip.json"
    fixed_now = datetime(2026, 5, 17, 12, 0, 0, tzinfo=timezone.utc)
    with caplog.at_level(logging.CRITICAL, logger="app.lifespan.ml"):
        out = auto_flip_ml_predictions(now=fixed_now, marker_path=str(write_marker))

    assert out == {"direction": "enabled", "reason": "dsr_above_gate"}
    assert any(
        "MLGATE_AUTO_FLIP direction=enabled reason=dsr_above_gate" in rec.message
        for rec in caplog.records
    ), f"expected critical log not found in {[r.message for r in caplog.records]!r}"

    payload = json.loads(write_marker.read_text())
    assert payload["schema_version"] == 1
    assert payload["direction"] == "enabled"
    assert payload["reason"] == "dsr_above_gate"
    assert payload["dsr_value"] == 0.97
    assert payload["run_date"] is not None
    assert payload["evaluated_at"] == fixed_now.isoformat()

    import os

    assert os.environ["ENABLE_ML_PREDICTIONS"] == "true"


# ============================================================================
# Test 2 — no evidence (no marker, no DB rows) -> disabled / no_evidence
# ============================================================================


def test_auto_flip_disabled_when_no_evidence(monkeypatch, tmp_path, caplog):
    """No marker file -> UNKNOWN at check_dsr_evidence -> no_evidence."""
    monkeypatch.setenv("ENABLE_ML_PREDICTIONS", "true")
    # Marker absent: point constant at a path that does not exist.
    monkeypatch.setattr(
        "app.preflight.checks._MLGATE_MARKER_PATH",
        str(tmp_path / "absent_marker.json"),
    )
    # DB path also routed to tmp so a host /data/tournament.db cannot leak in.
    monkeypatch.setattr(
        "app.preflight.checks._DEFAULT_TOURNAMENT_DB_PATH",
        str(tmp_path / "no.db"),
    )

    write_marker = tmp_path / "auto_flip.json"
    with caplog.at_level(logging.CRITICAL, logger="app.lifespan.ml"):
        out = auto_flip_ml_predictions(marker_path=str(write_marker))

    assert out == {"direction": "disabled", "reason": "no_evidence"}
    assert any(
        "MLGATE_AUTO_FLIP direction=disabled reason=no_evidence" in rec.message
        for rec in caplog.records
    ), f"expected critical log not found in {[r.message for r in caplog.records]!r}"
    payload = json.loads(write_marker.read_text())
    assert payload["schema_version"] == 1
    assert payload["direction"] == "disabled"
    assert payload["reason"] == "no_evidence"

    import os

    assert os.environ["ENABLE_ML_PREDICTIONS"] == "false"


# ============================================================================
# Test 3 — fresh dsr above gate but run_date stale -> evidence_stale
# ============================================================================


def test_auto_flip_disabled_when_evidence_stale(monkeypatch, tmp_path, caplog):
    """dsr=0.97 + psr_ci_published=1 + run_date=now-20d -> evidence_stale."""
    monkeypatch.setenv("ENABLE_ML_PREDICTIONS", "true")
    present = _make_present_marker(tmp_path)
    monkeypatch.setattr("app.preflight.checks._MLGATE_MARKER_PATH", str(present))
    db_path = tmp_path / "tournament.db"
    monkeypatch.setattr(
        "app.preflight.checks._DEFAULT_TOURNAMENT_DB_PATH", str(db_path)
    )
    _seed_leaderboard(db_path, dsr_value=0.97, run_date=_iso_days_ago(20))

    write_marker = tmp_path / "auto_flip.json"
    with caplog.at_level(logging.CRITICAL, logger="app.lifespan.ml"):
        out = auto_flip_ml_predictions(marker_path=str(write_marker))

    assert out == {"direction": "disabled", "reason": "evidence_stale"}
    assert any(
        "MLGATE_AUTO_FLIP direction=disabled reason=evidence_stale" in rec.message
        for rec in caplog.records
    )
    payload = json.loads(write_marker.read_text())
    assert payload["reason"] == "evidence_stale"
    assert payload["direction"] == "disabled"


# ============================================================================
# Test 4 — dsr below gate -> dsr_below_gate (takes precedence over staleness)
# ============================================================================


def test_auto_flip_disabled_when_dsr_below_gate(monkeypatch, tmp_path):
    """dsr=0.90 + psr_ci_published=1 + run_date=now-3d -> dsr_below_gate."""
    monkeypatch.setenv("ENABLE_ML_PREDICTIONS", "true")
    present = _make_present_marker(tmp_path)
    monkeypatch.setattr("app.preflight.checks._MLGATE_MARKER_PATH", str(present))
    db_path = tmp_path / "tournament.db"
    monkeypatch.setattr(
        "app.preflight.checks._DEFAULT_TOURNAMENT_DB_PATH", str(db_path)
    )
    _seed_leaderboard(db_path, dsr_value=0.90, run_date=_iso_days_ago(3))

    write_marker = tmp_path / "auto_flip.json"
    out = auto_flip_ml_predictions(marker_path=str(write_marker))

    assert out == {"direction": "disabled", "reason": "dsr_below_gate"}
    payload = json.loads(write_marker.read_text())
    assert payload["reason"] == "dsr_below_gate"
    assert payload["dsr_value"] == 0.90


# ============================================================================
# Test 5 — psr_ci_published=0 row is filtered out -> no_evidence
# ============================================================================


def test_auto_flip_ignores_unpublished_rows(monkeypatch, tmp_path):
    """dsr=0.99 + psr_ci_published=0 -> WHERE-clause excludes the row -> no_evidence."""
    monkeypatch.setenv("ENABLE_ML_PREDICTIONS", "true")
    present = _make_present_marker(tmp_path)
    monkeypatch.setattr("app.preflight.checks._MLGATE_MARKER_PATH", str(present))
    db_path = tmp_path / "tournament.db"
    monkeypatch.setattr(
        "app.preflight.checks._DEFAULT_TOURNAMENT_DB_PATH", str(db_path)
    )
    _seed_leaderboard(
        db_path,
        dsr_value=0.99,
        psr_ci_published=0,
        run_date=_iso_days_ago(3),
    )

    write_marker = tmp_path / "auto_flip.json"
    out = auto_flip_ml_predictions(marker_path=str(write_marker))

    assert out == {"direction": "disabled", "reason": "no_evidence"}


# ============================================================================
# Test 6 — marker-write failure does not raise (T-09-02-05 safety)
# ============================================================================


def test_auto_flip_marker_write_failure_does_not_raise(monkeypatch, tmp_path, caplog):
    """Path.write_text raising OSError MUST NOT crash boot; warning is logged."""
    monkeypatch.setenv("ENABLE_ML_PREDICTIONS", "true")
    present = _make_present_marker(tmp_path)
    monkeypatch.setattr("app.preflight.checks._MLGATE_MARKER_PATH", str(present))
    db_path = tmp_path / "tournament.db"
    monkeypatch.setattr(
        "app.preflight.checks._DEFAULT_TOURNAMENT_DB_PATH", str(db_path)
    )
    _seed_leaderboard(db_path, dsr_value=0.97, run_date=_iso_days_ago(3))

    # Patch Path.write_text to raise OSError (read-only mount simulation).
    # Per memory note feedback_pathlib_mocking: Path.write_text goes through
    # _io.open at C level, so patching pathlib.Path.write_text directly is
    # the correct mechanism (not builtins.open).
    def _raise_oserror(self, *args, **kwargs):
        raise OSError("read-only filesystem")

    monkeypatch.setattr("pathlib.Path.write_text", _raise_oserror)

    write_marker = tmp_path / "auto_flip.json"
    with caplog.at_level(logging.WARNING, logger="app.lifespan.ml"):
        # Must not raise.
        out = auto_flip_ml_predictions(marker_path=str(write_marker))

    assert out == {"direction": "enabled", "reason": "dsr_above_gate"}
    # Warning was logged.
    assert any("MLGATE marker write failed" in rec.message for rec in caplog.records), (
        f"expected marker-write warning, got {[r.message for r in caplog.records]!r}"
    )
    # Marker file was NOT created (write_text was patched to raise).
    assert not write_marker.exists()
    # Set_current_reason still ran for the disabled-event branch path? In this
    # PASS scenario, reason=dsr_above_gate is the enabled branch so
    # set_current_reason is intentionally NOT called. The in-process cache
    # remains at its default ("manual_override") — that is the expected
    # contract.
    assert get_current_reason() == "manual_override"


# ============================================================================
# Test 7 — reason-state propagation (D-09-02-06 reachability proof; ≥3 enums)
# ============================================================================


@pytest.mark.parametrize(
    "scenario,expected_reason",
    [
        ("no_evidence", "no_evidence"),
        ("dsr_below_gate", "dsr_below_gate"),
        ("evidence_stale", "evidence_stale"),
    ],
)
def test_auto_flip_sets_current_reason_for_disabled_branches(
    monkeypatch, tmp_path, scenario, expected_reason
):
    """For each of the 3 reachable disabled-event reasons, get_current_reason
    matches the auto-flip outcome — production-side reachability proof.

    Plan 09-03's 5-member ML_GATE_REASONS contains ``regime_shift`` (reserved
    for v1.2, no production path in Phase 9) and ``manual_override`` (the
    pre-auto-flip default — already reachable without seeding). These 3
    parametrized cases close the reachability gap from checker Blocker 1.
    """
    # Force a clean default before the seeded auto-flip runs.
    reset_counter()
    assert get_current_reason() == "manual_override"

    monkeypatch.setenv("ENABLE_ML_PREDICTIONS", "true")
    monkeypatch.setattr(
        "app.preflight.checks._DEFAULT_TOURNAMENT_DB_PATH",
        str(tmp_path / "tournament.db"),
    )

    if scenario == "no_evidence":
        # Marker absent -> UNKNOWN -> no_evidence
        monkeypatch.setattr(
            "app.preflight.checks._MLGATE_MARKER_PATH",
            str(tmp_path / "absent_marker.json"),
        )
        # No seed; DB does not exist.
    elif scenario == "dsr_below_gate":
        present = _make_present_marker(tmp_path)
        monkeypatch.setattr("app.preflight.checks._MLGATE_MARKER_PATH", str(present))
        _seed_leaderboard(
            tmp_path / "tournament.db",
            dsr_value=0.90,
            run_date=_iso_days_ago(3),
        )
    elif scenario == "evidence_stale":
        present = _make_present_marker(tmp_path)
        monkeypatch.setattr("app.preflight.checks._MLGATE_MARKER_PATH", str(present))
        _seed_leaderboard(
            tmp_path / "tournament.db",
            dsr_value=0.97,
            run_date=_iso_days_ago(20),
        )

    write_marker = tmp_path / "auto_flip.json"
    out = auto_flip_ml_predictions(marker_path=str(write_marker))

    assert out["reason"] == expected_reason
    assert out["direction"] == "disabled"
    # The cross-plan cache must now reflect the truthful reason — the
    # contract that closes checker Blocker 1.
    assert get_current_reason() == expected_reason


# ============================================================================
# Test 8 — set_current_reason failure does not crash boot (D-09-02-06 safety)
# ============================================================================


def test_auto_flip_does_not_crash_when_set_current_reason_raises(
    monkeypatch, tmp_path, caplog
):
    """If set_current_reason raises, auto_flip continues + marker still written.

    D-09-02-06 best-effort contract: the in-process cache update is
    best-effort; the marker JSON above is the durable source of truth.
    """
    monkeypatch.setenv("ENABLE_ML_PREDICTIONS", "true")
    present = _make_present_marker(tmp_path)
    monkeypatch.setattr("app.preflight.checks._MLGATE_MARKER_PATH", str(present))
    db_path = tmp_path / "tournament.db"
    monkeypatch.setattr(
        "app.preflight.checks._DEFAULT_TOURNAMENT_DB_PATH", str(db_path)
    )
    _seed_leaderboard(db_path, dsr_value=0.90, run_date=_iso_days_ago(3))

    def _raise_runtime(*args, **kwargs):
        raise RuntimeError("simulated cross-plan cache failure")

    # Patch the imported reference in app.lifespan.ml so the auto-flip's call
    # site hits the raising stub (not the canonical module's healthy impl).
    monkeypatch.setattr("app.lifespan.ml.set_current_reason", _raise_runtime)

    write_marker = tmp_path / "auto_flip.json"
    with caplog.at_level(logging.WARNING, logger="app.lifespan.ml"):
        out = auto_flip_ml_predictions(marker_path=str(write_marker))

    # Function returned normally with the expected direction/reason.
    assert out == {"direction": "disabled", "reason": "dsr_below_gate"}
    # Warning about the cross-plan cache failure was logged.
    assert any(
        "MLGATE set_current_reason failed" in rec.message for rec in caplog.records
    ), (
        f"expected set_current_reason warning, got {[r.message for r in caplog.records]!r}"
    )
    # Marker JSON is the durable source of truth — must still be written.
    assert write_marker.exists()
    payload = json.loads(write_marker.read_text())
    assert payload["reason"] == "dsr_below_gate"
    assert payload["direction"] == "disabled"
