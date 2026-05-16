"""
Preflight LIVE Readiness Checks (PREFLIGHT-01).

Pure functions — each returns a ``CheckResult``. No FastAPI dependency.
Imported by:

  - ``services/trading-engine/app/handlers/preflight.py`` (HTTP route, Phase 8 plan 02)
  - ``scripts/preflight_live.py`` (CLI entry point, Phase 8 plan 02)
  - ``services/trading-engine/app/main.py`` lifespan (Phase 8 plan 03 — grep gate
    asserts ``from app.preflight import`` survives autoflake).

CRITICAL: keep this module dependency-free beyond stdlib + ``app.config`` +
``sqlite3``, so the CLI can run on a developer laptop without docker.

NOTE on the boot-reject log literal: the ``main.py`` lifespan owns the
log line that announces a refused LIVE boot (Phase 8 plan 03 owns the
boot-path enforcement). It is NOT emitted here — these are pure check
functions that build a structured report. The Phase 8 grep gate
intentionally scopes to ``services/trading-engine/app/``; a stray copy
of that log literal in this file would still pass the gate but pollute
scope. Per 08-CONTEXT.md, that literal must not appear anywhere in this
file (including comments and docstrings).
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

from app.config import Settings, get_settings
from app.preflight.types import CheckResult, PreflightReport

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants (test-overridable via monkeypatch.setattr)
# ---------------------------------------------------------------------------

# Phase 9 (MLGATE-02) writes this marker on auto-flip. Phase 8 reads it as
# the "Phase 9 has landed" signal for the DSR evidence check. Tests override
# this constant rather than mass-patching ``pathlib.Path.is_file`` which
# would also affect ``check_emergency_stop`` and bleed cross-check.
_MLGATE_MARKER_PATH = "/run/mlgate_auto_flip.json"

# Default location of the tournament-harness sqlite DB. Overridable via
# ``check_dsr_evidence(db_path=...)`` for tests + non-default deploys.
_DEFAULT_TOURNAMENT_DB_PATH = "/data/tournament.db"

# LIVE-strict per-trade cap. Non-negotiable per CLAUDE.md + REQUIREMENTS.md
# PREFLIGHT-02. Paper mode is relaxed to 10% per ADR-010.
_LIVE_STRICT_CAP = 0.02

# DSR floor used by the v1.0 evaluation framework (returns_metrics + PSR/DSR).
# Mirrors REQUIREMENTS.md PREFLIGHT-01 wording.
_DSR_FLOOR = 0.95


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


def check_cap(settings: Settings | None = None) -> CheckResult:
    """Per-trade cap must be <= 0.02 (2%) in LIVE mode.

    PAPER skips the cap check by design (ADR-010 paper-relaxed 10%).
    """
    s = settings or get_settings()
    if s.trading_mode != "LIVE":
        return CheckResult(
            check="cap",
            status="PASS",
            detail=(
                f"non-LIVE mode ({s.trading_mode}); cap check skipped "
                "per ADR-010 paper-relaxed cap"
            ),
        )
    if s.max_risk_per_trade > _LIVE_STRICT_CAP:
        return CheckResult(
            check="cap",
            status="FAIL",
            detail=(
                f"max_risk_per_trade={s.max_risk_per_trade} > "
                f"{_LIVE_STRICT_CAP} (LIVE-strict per PREFLIGHT-02)"
            ),
        )
    return CheckResult(
        check="cap",
        status="PASS",
        detail=(f"max_risk_per_trade={s.max_risk_per_trade} <= {_LIVE_STRICT_CAP}"),
    )


def check_paper_mode(settings: Settings | None = None) -> CheckResult:
    """In LIVE mode, ``PAPER_TRADING_MODE`` env var must NOT be truthy.

    Reads from ``os.environ`` directly because there is no
    ``paper_trading_mode`` field on the Settings model — the var is consumed
    elsewhere in compose/bybit-connector wiring. Mirrors ``check_ack``'s
    direct-env pattern (same trust source as main.py:251).

    Non-LIVE modes skip this check.
    """
    s = settings or get_settings()
    if s.trading_mode != "LIVE":
        return CheckResult(
            check="paper_mode",
            status="PASS",
            detail=f"non-LIVE mode ({s.trading_mode}); paper_mode check skipped",
        )
    raw = os.environ.get("PAPER_TRADING_MODE", "false")
    if raw.lower() == "true":
        return CheckResult(
            check="paper_mode",
            status="FAIL",
            detail="PAPER_TRADING_MODE=true while TRADING_MODE=LIVE",
        )
    return CheckResult(
        check="paper_mode",
        status="PASS",
        detail=f"PAPER_TRADING_MODE={raw}",
    )


def check_trading_mode(settings: Settings | None = None) -> CheckResult:
    """``TRADING_MODE`` must equal ``LIVE`` for live trading."""
    s = settings or get_settings()
    if s.trading_mode == "LIVE":
        return CheckResult(
            check="trading_mode",
            status="PASS",
            detail="TRADING_MODE=LIVE",
        )
    return CheckResult(
        check="trading_mode",
        status="FAIL",
        detail=f"TRADING_MODE={s.trading_mode} (expected LIVE)",
    )


def check_ack(settings: Settings | None = None) -> CheckResult:
    """``LIVE_TRADING_ACK`` env var must equal ``I_UNDERSTAND_REAL_MONEY``.

    Skipped in non-LIVE modes — the check is pure under that condition and
    does not touch the env at all (matches the ``check_cap`` short-circuit
    pattern). Reads ``os.environ`` directly to mirror main.py:251 source-of-
    truth (the lifespan check uses the same env read, avoiding a config-
    reload race with stale Settings cache).
    """
    s = settings or get_settings()
    if s.trading_mode != "LIVE":
        return CheckResult(
            check="ack",
            status="PASS",
            detail=f"non-LIVE mode ({s.trading_mode}); ack check skipped",
        )
    ack = os.environ.get("LIVE_TRADING_ACK", "")
    if ack == "I_UNDERSTAND_REAL_MONEY":
        return CheckResult(
            check="ack",
            status="PASS",
            detail="LIVE_TRADING_ACK present",
        )
    return CheckResult(
        check="ack",
        status="FAIL",
        detail=(
            "LIVE_TRADING_ACK env var missing or wrong value "
            "(expected literal 'I_UNDERSTAND_REAL_MONEY')"
        ),
    )


def check_emergency_stop(settings: Settings | None = None) -> CheckResult:
    """EMERGENCY_STOP file must be absent.

    Uses ``.is_file()`` not ``.exists()`` to handle the WSL bind-mount edge
    case where Docker may create a *directory* at the mount point if the
    host file is absent (CLAUDE.md gotcha; see also main.py:282).
    """
    s = settings or get_settings()
    stop_file = Path(s.emergency_stop_file)
    if stop_file.is_file():
        return CheckResult(
            check="emergency_stop",
            status="FAIL",
            detail=f"file present at {stop_file}",
        )
    return CheckResult(
        check="emergency_stop",
        status="PASS",
        detail=f"no file at {stop_file}",
    )


def check_dsr_evidence(db_path: str | None = None) -> CheckResult:
    """DSR > 0.95 row in the ``leaderboard`` table — best-effort in Phase 8.

    Returns ``UNKNOWN`` if any of:
      - Phase 9 (MLGATE-02) auto-flip marker is absent (the 14-day staleness
        rule and the ``psr_ci_published`` column belong to Phase 9; Phase 8
        only surfaces the latest DSR value).
      - the sqlite DB is unreachable or the ``leaderboard`` table is empty.

    Returns ``PASS`` if ``ENABLE_ML_PREDICTIONS != true`` — ML is gated off
    by default per CLAUDE.md so no DSR evidence is required for boot.

    NOTE on table name: REQUIREMENTS.md wording says ``tournament_results``;
    the actual schema (services/tournament-harness/migrations/0001_initial.sql:9)
    defines the ``leaderboard`` table with the ``dsr REAL`` column. We read
    from ``leaderboard`` per 08-CONTEXT.md lines 95-101 decision. The
    REQUIREMENTS.md wording will be corrected in a follow-up docs commit;
    Phase 9 owns evidence-row schema additions.
    """
    if os.environ.get("ENABLE_ML_PREDICTIONS", "false").lower() != "true":
        return CheckResult(
            check="dsr_evidence",
            status="PASS",
            detail="ML disabled (ENABLE_ML_PREDICTIONS=false); DSR check skipped",
        )

    if not Path(_MLGATE_MARKER_PATH).is_file():
        return CheckResult(
            check="dsr_evidence",
            status="UNKNOWN",
            detail=(
                f"MLGATE-02 marker absent at {_MLGATE_MARKER_PATH} (Phase 9 not landed)"
            ),
        )

    path = db_path or _DEFAULT_TOURNAMENT_DB_PATH
    try:
        # uri-only connect-as-readonly would be safer, but the tournament-
        # harness module already initialises the DB read-write in another
        # process — we use a plain connect with a short timeout. The query
        # is parameter-free (column whitelisted in code, no user input).
        with sqlite3.connect(path, timeout=2.0) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT dsr FROM leaderboard ORDER BY tournament_start_ts DESC LIMIT 1"
            )
            row = cur.fetchone()
    except sqlite3.Error as e:
        # Never leak full sqlite messages (may include filesystem paths).
        return CheckResult(
            check="dsr_evidence",
            status="UNKNOWN",
            detail=(f"leaderboard query failed: {type(e).__name__} (db_path={path})"),
        )

    if row is None or row[0] is None:
        return CheckResult(
            check="dsr_evidence",
            status="UNKNOWN",
            detail=f"leaderboard empty or latest row has null dsr (db_path={path})",
        )

    dsr_value = float(row[0])
    if dsr_value > _DSR_FLOOR:
        return CheckResult(
            check="dsr_evidence",
            status="PASS",
            detail=f"latest leaderboard dsr={dsr_value} > {_DSR_FLOOR}",
        )
    return CheckResult(
        check="dsr_evidence",
        status="FAIL",
        detail=f"latest leaderboard dsr={dsr_value} <= {_DSR_FLOOR}",
    )


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


def run_all(settings: Settings | None = None) -> PreflightReport:
    """Run all 6 checks in the canonical order and aggregate to a report.

    Order: ``cap, paper_mode, trading_mode, ack, emergency_stop, dsr_evidence``.
    Dashboard tile (Phase 10) renders in this order; do not reshuffle.

    ``overall`` precedence:

    * any ``FAIL`` -> ``FAIL``
    * else any ``UNKNOWN`` -> ``UNKNOWN``
    * else ``PASS``

    ``UNKNOWN`` is a real terminal state. The dashboard treats ``UNKNOWN``
    as not-yet-PASS so READY can never light up while ``dsr_evidence`` is
    pending Phase 9.
    """
    s = settings or get_settings()
    checks = [
        check_cap(s),
        check_paper_mode(s),
        check_trading_mode(s),
        check_ack(s),
        check_emergency_stop(s),
        check_dsr_evidence(),
    ]
    if any(c.status == "FAIL" for c in checks):
        overall = "FAIL"
    elif any(c.status == "UNKNOWN" for c in checks):
        overall = "UNKNOWN"
    else:
        overall = "PASS"
    return PreflightReport(overall=overall, checks=checks)
