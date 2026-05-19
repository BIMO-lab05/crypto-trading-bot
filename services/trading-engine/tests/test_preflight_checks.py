"""
Unit tests for ``app.preflight.checks`` — Phase 8 PREFLIGHT-01.

Each check is exercised against every terminal state (PASS / FAIL / UNKNOWN)
plus the WSL bind-mount edge case for ``check_emergency_stop`` and the
ML-gated branch for ``check_dsr_evidence``.

Uses Pydantic v2's keyword-arg constructor on ``Settings`` directly — no
env-var roundtrip, no ``reload_settings()`` (avoids global side effects).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


from app.config import Settings
from app.preflight.checks import (
    check_ack,
    check_cap,
    check_dsr_evidence,
    check_emergency_stop,
    check_paper_mode,
    check_trading_mode,
    run_all,
)


# ============================================================================
# Production-schema-faithful fixture for the DSR check.
# Column types MUST match services/tournament-harness/migrations/0001_initial.sql:9-38
# AND migration 0002_mlgate_evidence_columns.sql (run_date TEXT, psr_ci_published
# INTEGER NOT NULL DEFAULT 0 — added by Phase 9 Plan 09-01).
# In particular, tournament_start_ts is TEXT NOT NULL (ISO-8601 string),
# NOT INTEGER. ORDER BY on ISO-8601 strings is chronological because the
# format is fixed-width — but switching the fixture to INTEGER would
# silently diverge from production type semantics and any future
# datetime-aware refactor would pass against the fixture but fail in
# production. The meta-test
# ``test_dsr_fixture_schema_matches_production`` below guards this.
#
# Inline-merge rationale (Phase 9 Plan 09-02 Task 1, advisor note 3):
# rather than apply migration 0002.sql against the inline CREATE (which has
# no schema_version table for run_migrations to gate on), we merge the
# columns directly into the inline CREATE here. This satisfies the Plan
# 09-02 acceptance criterion's "OR the inline ALTER TABLE columns appear in
# the fixture build" branch.
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
    -- Phase 9 Plan 09-01 migration 0002 columns (mlgate_evidence_columns):
    run_date            TEXT,
    psr_ci_published    INTEGER NOT NULL DEFAULT 0
        CHECK (psr_ci_published IN (0, 1)),
    PRIMARY KEY (architecture, symbol, horizon, target_mode, hp_hash, run_id)
);
"""


def _fresh_run_date(days_ago: int = 3) -> str:
    """ISO-8601 UTC string ``run_date`` value `days_ago` before now.

    Within Phase 9 MLGATE-02's 14-day staleness window for any
    ``days_ago < 14``; outside for any ``days_ago >= 14``.
    """
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _seed_leaderboard(
    db_path: Path,
    dsr_value: float,
    *,
    psr_ci_published: int = 1,
    run_date: str | None = None,
) -> None:
    """Create the leaderboard table and insert a single row.

    Uses an ISO-8601 string ``tournament_start_ts`` to match production schema.
    The two Phase 9 columns default to "qualifying" values
    (``psr_ci_published=1``, ``run_date=now-3d``) so the existing Phase 8
    tests can call the helper unchanged for the freshness-and-published case.
    Callers that need an unpublished or stale row pass the kwargs explicitly.
    """
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
                "success",
                run_date if run_date is not None else _fresh_run_date(3),
                psr_ci_published,
            ),
        )
        conn.commit()
    finally:
        conn.close()


# ============================================================================
# check_cap
# ============================================================================


def test_check_cap_paper_allows_10pct():
    """PAPER mode skips the cap check per ADR-010 (10% allowed)."""
    settings = Settings(trading_mode="PAPER", max_risk_per_trade=0.10)
    result = check_cap(settings)
    assert result.status == "PASS"
    assert "non-LIVE" in result.detail or "skipped" in result.detail


def test_check_cap_live_rejects_3pct():
    """LIVE mode with cap > 2% MUST fail — PREFLIGHT-02 contract.

    Both the failing cap value AND the strict limit must appear in detail
    so an operator reading dashboard/CLI output understands what to fix.
    """
    settings = Settings(trading_mode="LIVE", max_risk_per_trade=0.03)
    result = check_cap(settings)
    assert result.status == "FAIL"
    assert "0.03" in result.detail
    assert "0.02" in result.detail


def test_check_cap_live_accepts_2pct():
    """LIVE mode with cap == 2% must PASS."""
    settings = Settings(trading_mode="LIVE", max_risk_per_trade=0.02)
    result = check_cap(settings)
    assert result.status == "PASS"


# ============================================================================
# check_paper_mode
# ============================================================================


def test_check_paper_mode_non_live_skips(monkeypatch):
    """PAPER mode: paper_mode check is short-circuited to PASS regardless of env."""
    monkeypatch.setenv("PAPER_TRADING_MODE", "true")
    settings = Settings(trading_mode="PAPER")
    result = check_paper_mode(settings)
    assert result.status == "PASS"


def test_check_paper_mode_live_with_true_fails(monkeypatch):
    """LIVE + PAPER_TRADING_MODE=true is a configuration error -> FAIL."""
    monkeypatch.setenv("PAPER_TRADING_MODE", "true")
    settings = Settings(trading_mode="LIVE")
    result = check_paper_mode(settings)
    assert result.status == "FAIL"
    assert "PAPER_TRADING_MODE" in result.detail


def test_check_paper_mode_live_with_false_passes(monkeypatch):
    """LIVE + PAPER_TRADING_MODE=false (or unset) -> PASS."""
    monkeypatch.setenv("PAPER_TRADING_MODE", "false")
    settings = Settings(trading_mode="LIVE")
    result = check_paper_mode(settings)
    assert result.status == "PASS"


# ============================================================================
# check_trading_mode
# ============================================================================


def test_check_trading_mode_live_passes():
    settings = Settings(trading_mode="LIVE")
    result = check_trading_mode(settings)
    assert result.status == "PASS"
    assert "LIVE" in result.detail


def test_check_trading_mode_paper_fails():
    """The trading_mode check from the LIVE-readiness perspective:
    if the mode is NOT LIVE, the system is not LIVE-ready, so the check FAILs."""
    settings = Settings(trading_mode="PAPER")
    result = check_trading_mode(settings)
    assert result.status == "FAIL"
    assert "PAPER" in result.detail


# ============================================================================
# check_ack
# ============================================================================


def test_check_ack_present(monkeypatch):
    """LIVE_TRADING_ACK with correct sentinel must PASS in LIVE mode."""
    monkeypatch.setenv("LIVE_TRADING_ACK", "I_UNDERSTAND_REAL_MONEY")
    settings = Settings(trading_mode="LIVE")
    result = check_ack(settings)
    assert result.status == "PASS"


def test_check_ack_missing_in_live(monkeypatch):
    """Missing LIVE_TRADING_ACK in LIVE mode must FAIL."""
    monkeypatch.delenv("LIVE_TRADING_ACK", raising=False)
    settings = Settings(trading_mode="LIVE")
    result = check_ack(settings)
    assert result.status == "FAIL"


def test_check_ack_skipped_in_paper(monkeypatch):
    """Non-LIVE mode short-circuits to PASS without reading env."""
    # Even if ack is missing, PAPER mode short-circuits.
    monkeypatch.delenv("LIVE_TRADING_ACK", raising=False)
    settings = Settings(trading_mode="PAPER")
    result = check_ack(settings)
    assert result.status == "PASS"


# ============================================================================
# check_emergency_stop
# ============================================================================


def test_check_emergency_stop_file_present(tmp_path):
    """EMERGENCY_STOP file must trigger FAIL."""
    stop_file = tmp_path / "EMERGENCY_STOP"
    stop_file.write_text("")
    settings = Settings(emergency_stop_file=str(stop_file))
    result = check_emergency_stop(settings)
    assert result.status == "FAIL"


def test_check_emergency_stop_directory_at_path_is_not_file(tmp_path):
    """WSL bind-mount edge case: a *directory* at the path must NOT FAIL.

    ``Path.is_file()`` returns False for directories; ``.exists()`` would
    falsely trip. This is the CLAUDE.md gotcha mirrored from main.py:282.
    """
    (tmp_path / "EMERGENCY_STOP").mkdir()
    settings = Settings(emergency_stop_file=str(tmp_path / "EMERGENCY_STOP"))
    result = check_emergency_stop(settings)
    assert result.status == "PASS"


def test_check_emergency_stop_absent(tmp_path):
    """No file at path -> PASS."""
    settings = Settings(emergency_stop_file=str(tmp_path / "EMERGENCY_STOP"))
    result = check_emergency_stop(settings)
    assert result.status == "PASS"


# ============================================================================
# check_dsr_evidence
# ============================================================================


def test_check_dsr_evidence_ml_disabled_passes(monkeypatch):
    """ENABLE_ML_PREDICTIONS=false short-circuits to PASS."""
    monkeypatch.setenv("ENABLE_ML_PREDICTIONS", "false")
    result = check_dsr_evidence()
    assert result.status == "PASS"
    assert "ML disabled" in result.detail


def test_check_dsr_evidence_ml_enabled_no_marker_is_unknown(monkeypatch, tmp_path):
    """ML on but Phase 9 marker absent -> UNKNOWN per CONTEXT.md decision."""
    monkeypatch.setenv("ENABLE_ML_PREDICTIONS", "true")
    # Point the marker to a non-existent path inside tmp so the test does
    # not depend on whatever happens to be at /run on the host.
    monkeypatch.setattr(
        "app.preflight.checks._MLGATE_MARKER_PATH",
        str(tmp_path / "no-such-marker.json"),
    )
    result = check_dsr_evidence()
    assert result.status == "UNKNOWN"
    assert "Phase 9" in result.detail or "marker" in result.detail


def test_check_dsr_evidence_ml_enabled_with_row_above_gate_passes(
    monkeypatch, tmp_path
):
    """ML on + marker present + leaderboard row with dsr=0.97 -> PASS.

    Seeds the leaderboard table using the production-faithful schema
    (tournament_start_ts TEXT NOT NULL, ISO-8601 string timestamp). Per
    Phase 9 Plan 09-02 Task 1 step 8, the row MUST include
    ``psr_ci_published=1`` AND a fresh ``run_date`` (within the 14-day
    staleness window) so the new MLGATE-02 filters pass.
    """
    monkeypatch.setenv("ENABLE_ML_PREDICTIONS", "true")
    # Create the marker file at an in-tmp path and point the constant at it.
    marker = tmp_path / "mlgate_marker.json"
    marker.write_text("{}")
    monkeypatch.setattr("app.preflight.checks._MLGATE_MARKER_PATH", str(marker))
    # Seed a leaderboard row well above the 0.95 floor with the Phase 9
    # columns set to "qualifying": psr_ci_published=1 + fresh run_date.
    db_path = tmp_path / "tournament.db"
    _seed_leaderboard(
        db_path,
        dsr_value=0.97,
        psr_ci_published=1,
        run_date=_fresh_run_date(days_ago=3),
    )

    result = check_dsr_evidence(db_path=str(db_path))
    assert result.status == "PASS"
    assert "0.97" in result.detail


def test_check_dsr_evidence_ml_enabled_with_row_at_or_below_gate_fails(
    monkeypatch, tmp_path
):
    """ML on + marker present + leaderboard row with dsr<=0.95 -> FAIL.

    The row carries ``psr_ci_published=1`` + fresh ``run_date`` so the
    failure reason is the dsr-below-gate path, not the staleness path
    (Phase 9 MLGATE-02 branch ordering).
    """
    monkeypatch.setenv("ENABLE_ML_PREDICTIONS", "true")
    marker = tmp_path / "mlgate_marker.json"
    marker.write_text("{}")
    monkeypatch.setattr("app.preflight.checks._MLGATE_MARKER_PATH", str(marker))
    db_path = tmp_path / "tournament.db"
    _seed_leaderboard(
        db_path,
        dsr_value=0.90,
        psr_ci_published=1,
        run_date=_fresh_run_date(days_ago=3),
    )

    result = check_dsr_evidence(db_path=str(db_path))
    assert result.status == "FAIL"
    assert "0.9" in result.detail
    # The detail must name the below-gate cause (not "stale"). The new
    # check_dsr_evidence branch-orders dsr_below_gate above evidence_stale
    # so the operator sees the root cause.
    assert "stale" not in result.detail.lower()


# ============================================================================
# run_all
# ============================================================================


def test_run_all_returns_six_checks_in_order(monkeypatch):
    """run_all returns 6 checks in the canonical order: cap, paper_mode,
    trading_mode, ack, emergency_stop, dsr_evidence."""
    monkeypatch.setenv("ENABLE_ML_PREDICTIONS", "false")
    settings = Settings(trading_mode="PAPER", max_risk_per_trade=0.10)
    report = run_all(settings)
    assert len(report.checks) == 6
    names = [c.check for c in report.checks]
    assert names == [
        "cap",
        "paper_mode",
        "trading_mode",
        "ack",
        "emergency_stop",
        "dsr_evidence",
    ]


def test_run_all_overall_fail_when_any_check_fails(monkeypatch, tmp_path):
    """Any FAIL -> overall=FAIL (highest precedence)."""
    monkeypatch.setenv("ENABLE_ML_PREDICTIONS", "false")
    # PAPER mode + cap=0.10 PASSes the cap check but trading_mode=PAPER
    # fails (we're checking LIVE-readiness, not paper validity).
    settings = Settings(
        trading_mode="PAPER",
        max_risk_per_trade=0.10,
        emergency_stop_file=str(tmp_path / "stop"),
    )
    report = run_all(settings)
    assert report.overall == "FAIL"


def test_run_all_overall_unknown_when_no_fail_but_unknown(monkeypatch, tmp_path):
    """No FAIL + at least one UNKNOWN -> overall=UNKNOWN.

    Setup: LIVE mode + all preconditions met, but ML enabled with marker
    absent so dsr_evidence is the only UNKNOWN.
    """
    monkeypatch.setenv("ENABLE_ML_PREDICTIONS", "true")
    monkeypatch.setenv("LIVE_TRADING_ACK", "I_UNDERSTAND_REAL_MONEY")
    monkeypatch.setenv("PAPER_TRADING_MODE", "false")
    monkeypatch.setattr(
        "app.preflight.checks._MLGATE_MARKER_PATH",
        str(tmp_path / "no-marker.json"),
    )
    settings = Settings(
        trading_mode="LIVE",
        max_risk_per_trade=0.02,
        emergency_stop_file=str(tmp_path / "no-stop-file"),
    )
    report = run_all(settings)
    assert report.overall == "UNKNOWN"
    statuses = {c.check: c.status for c in report.checks}
    assert statuses["dsr_evidence"] == "UNKNOWN"
    # No FAIL anywhere.
    assert not any(c.status == "FAIL" for c in report.checks)


def test_run_all_overall_pass_when_all_pass(monkeypatch, tmp_path):
    """All PASS -> overall=PASS."""
    monkeypatch.setenv("ENABLE_ML_PREDICTIONS", "false")
    monkeypatch.setenv("LIVE_TRADING_ACK", "I_UNDERSTAND_REAL_MONEY")
    monkeypatch.setenv("PAPER_TRADING_MODE", "false")
    settings = Settings(
        trading_mode="LIVE",
        max_risk_per_trade=0.02,
        emergency_stop_file=str(tmp_path / "no-stop-file"),
    )
    report = run_all(settings)
    assert report.overall == "PASS"


# ============================================================================
# Meta-test — fixture schema MUST match production
# ============================================================================


def test_dsr_fixture_schema_matches_production():
    """Source-inspection guard: the CREATE TABLE in *this file* must declare
    the start-ts column as TEXT NOT NULL (matches
    services/tournament-harness/migrations/0001_initial.sql:28), and MUST NOT
    declare it as the INTEGER form.

    This is the regression detector for a future copy-paste that "fixes"
    the fixture back to integer timestamps — that would pass other tests
    today but silently diverge from production type semantics.

    The forbidden literal is built at runtime so it does not appear in
    this file's source text and trigger the very check it implements.
    """
    source = Path(__file__).read_text()
    column = "tournament_start_ts"
    required_form = f"{column} TEXT NOT NULL"
    # Build forbidden form via concatenation so the literal does not
    # appear in this file's source.
    forbidden_form = column + " " + "INT" + "EGER"
    assert required_form in source, (
        f"fixture must declare {required_form} "
        "(matches production schema 0001_initial.sql:28)"
    )
    assert forbidden_form not in source, (
        f"fixture must NOT declare {column} as the integer form — "
        "production schema is TEXT NOT NULL"
    )
