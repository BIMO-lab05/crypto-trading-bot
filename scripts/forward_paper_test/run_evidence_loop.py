"""MLGATE-01 evidence-loop driver.

Idempotent orchestrator that walks un-published ``leaderboard`` rows and, when
the ≥7-day forward-paper-test accrual window has closed for a natural-key
group, computes PSR-CI via the canonical kernel and flips
``psr_ci_published = 1``.

The driver is a thin orchestrator over
:func:`scripts.forward_paper_test.psr_ci.compute_psr_with_bootstrap_ci` — it
does NOT re-implement bootstrap PSR/CI math (TOURN-07 spirit; the canonical
kernel is imported, never duplicated).

Idempotency contract (MLGATE-01 success criteria #1, verbatim):
    re-running ``python -m scripts.forward_paper_test.run_evidence_loop``
    produces the same final leaderboard row count and the same set of
    ``psr_ci_published = 1`` rows. Filtering happens at SELECT time
    (``WHERE psr_ci_published = 0``) — not post-filter — so already-published
    rows are never re-read.

Plan: ``.planning/phases/09-ml-re-enablement-gate/09-01-evidence-loop-driver-PLAN.md``
Requirement: MLGATE-01
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Canonical PSR-CI kernel — TOURN-07 spirit: imported, never re-implemented.
# Single-line import is contract surface: 09-01 acceptance grep gate looks for
# the exact `from scripts.forward_paper_test.psr_ci import compute_psr_with_bootstrap_ci`
# pattern; do not let a formatter wrap this across lines.
# fmt: off
from scripts.forward_paper_test.psr_ci import compute_psr_with_bootstrap_ci, load_run_returns  # noqa: E501
# fmt: on

# ---------------------------------------------------------------------------
# Module-level constants (test-overridable via monkeypatch.setattr)
# ---------------------------------------------------------------------------

# Single source of truth for the tournament-harness sqlite DB path — matches
# the literal in services/trading-engine/app/preflight/checks.py:49 so Phase 8
# and Phase 9 read the same DB by default.
DEFAULT_TOURNAMENT_DB_PATH = "/data/tournament.db"


def resolve_db_path() -> str:
    """CLI default for --db-path: TOURNAMENT_DB_PATH env, else the legacy literal."""
    return os.environ.get("TOURNAMENT_DB_PATH", DEFAULT_TOURNAMENT_DB_PATH)


# ≥7-day wall-clock accrual window before a row's natural-key group becomes
# eligible for PSR-CI publication (decision D-09-01-04).
ACCRUAL_WINDOW_DAYS = 7

# Log line prefix — read by Plan 09-03 digest. Contract surface; do not
# rename without updating downstream consumers.
LOG_PREFIX = "MLGATE_EVIDENCE_LOOP"

# Bootstrap seed for compute_psr_with_bootstrap_ci. Fixed across runs so
# re-running the driver on the same returns produces identical CI bounds.
_PSR_CI_SEED = 20260517

# Per-trade returns artefact convention — mirrors run_isolation.py:_EVIDENCE_BASE.
_REPO = Path(__file__).resolve().parents[2]
_EVIDENCE_BASE = _REPO / ".planning" / "evidence" / "forward_paper_test"

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Safety precondition (paper-only)
# ---------------------------------------------------------------------------


def _check_paper_mode_precondition() -> None:
    """Refuse to run under TRADING_MODE=LIVE.

    Mirrors :func:`scripts.forward_paper_test.run_isolation._check_paper_mode_precondition`
    — the evidence-loop driver is paper-only by the same trust posture: it
    must never run during LIVE trading because publishing a row gates a future
    auto-flip of ``ENABLE_ML_PREDICTIONS``.

    PAPER_TRADING_MODE is NOT required to be set (unlike run_isolation.py) —
    the driver only reads sqlite and updates a publication flag; it does not
    launch the trading engine. The TRADING_MODE=LIVE refusal is the load-
    bearing guard.
    """
    trading_mode = os.environ.get("TRADING_MODE", "").upper()
    if trading_mode == "LIVE":
        print(
            "ERROR: TRADING_MODE=LIVE is set in the environment.\n"
            "The MLGATE evidence-loop driver is paper-only. Set TRADING_MODE=PAPER\n"
            "(or unset it) before running.",
            file=sys.stderr,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Returns-source resolution
# ---------------------------------------------------------------------------


def _resolve_returns(
    *,
    run_id: str,
    returns_source: Optional[Path],
):
    """Resolve a per-trade log-returns array for ``run_id``.

    Source preference:
      1. If ``returns_source`` is provided (test convenience), load the
         single JSON file at that path via :func:`psr_ci.load_run_returns`
         (the parent directory must contain ``run.json``).
      2. Otherwise, resolve from
         ``.planning/evidence/forward_paper_test/<flag>/<run_id>/run.json``.
         The flag dimension is not present in the leaderboard schema; the
         driver enumerates flag subdirectories and picks the one whose run_id
         matches.

    Returns ``None`` if no source is resolvable — caller logs ``action=skip
    reason=returns_unavailable`` and continues (missing returns must not
    break the loop).
    """
    if returns_source is not None:
        # The argument may point at either the directory containing run.json
        # or directly at run.json itself. Normalise to the directory.
        rs = Path(returns_source)
        if rs.is_file() and rs.name == "run.json":
            rs = rs.parent
        if rs.is_dir() and (rs / "run.json").is_file():
            return load_run_returns(rs)
        return None

    # Production resolution: walk .planning/evidence/forward_paper_test/<flag>/<run_id>/
    if not _EVIDENCE_BASE.is_dir():
        return None
    for flag_dir in _EVIDENCE_BASE.iterdir():
        if not flag_dir.is_dir():
            continue
        candidate = flag_dir / run_id
        if (candidate / "run.json").is_file():
            return load_run_returns(candidate)
    return None


# ---------------------------------------------------------------------------
# Core loop
# ---------------------------------------------------------------------------


def run_evidence_loop(
    db_path: str = DEFAULT_TOURNAMENT_DB_PATH,
    *,
    dry_run: bool = False,
    returns_source: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> dict:
    """Walk un-published leaderboard rows; publish PSR-CI when the 7-day window has closed.

    Parameters
    ----------
    db_path:
        Path to the tournament-harness sqlite DB. Default matches the literal
        in ``services/trading-engine/app/preflight/checks.py``.
    dry_run:
        If True, enumerate eligible rows and log what WOULD happen, but
        perform no UPDATEs and skip the (expensive) bootstrap PSR-CI call.
    returns_source:
        Optional test override pointing at a JSON file (or its containing
        directory) with the ``{"returns": [...]}`` payload. When set, the
        same returns array is used for every eligible row — exclusively a
        test convenience. Production resolution walks
        ``.planning/evidence/forward_paper_test/<flag>/<run_id>/run.json``.
    now:
        Injectable clock for deterministic tests. Defaults to
        ``datetime.now(timezone.utc)``.

    Returns
    -------
    dict
        Keys: ``published`` (rows flipped to ``psr_ci_published=1``),
        ``skipped`` (eligible-but-window-open or returns-unavailable rows),
        ``errors`` (non-fatal exceptions caught per row).
    """
    if now is None:
        now = datetime.now(timezone.utc)

    counters = {"published": 0, "skipped": 0, "errors": 0}

    # Open DB (read+write). The driver only UPDATEs the psr_ci_published column;
    # it never INSERTs or DELETEs leaderboard rows (T-09-01-01 disposition).
    conn = sqlite3.connect(db_path, timeout=5.0)
    try:
        # SELECT eligible rows — idempotency filter is at SELECT time, NOT
        # post-filter. ORDER BY run_date ASC so the oldest accrual group is
        # surfaced first. Uses the idx_leaderboard_psr_published index from
        # migration 0002.
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT architecture, symbol, horizon, target_mode, hp_hash, run_id,"
                " run_date, dsr, oos_sharpe"
                " FROM leaderboard"
                " WHERE psr_ci_published = 0"
                "   AND status = 'success'"
                "   AND run_date IS NOT NULL"
                " ORDER BY run_date ASC"
            )
            rows = cur.fetchall()
        except sqlite3.Error as e:
            # Never leak full sqlite messages (may include filesystem paths)
            # — mirrors services/trading-engine/app/preflight/checks.py:246-251
            # disposition for T-09-01-03 (information disclosure).
            logger.error(
                "MLGATE_EVIDENCE_LOOP action=error reason=%s",
                type(e).__name__,
            )
            counters["errors"] += 1
            return counters

        if not rows:
            logger.info("MLGATE_EVIDENCE_LOOP action=skip reason=no_rows")
            return counters

        # Group by natural key (architecture, symbol, horizon, target_mode, hp_hash);
        # compute min(run_date) per group to apply the 7-day window check.
        groups: dict = defaultdict(list)
        for row in rows:
            key = row[:5]  # (architecture, symbol, horizon, target_mode, hp_hash)
            groups[key].append(row)

        for key, group_rows in groups.items():
            # Parse run_date strings (ISO-8601 UTC); skip any that can't be parsed.
            run_dates = []
            for r in group_rows:
                rd_str = r[6]
                try:
                    rd = datetime.fromisoformat(rd_str.replace("Z", "+00:00"))
                    if rd.tzinfo is None:
                        rd = rd.replace(tzinfo=timezone.utc)
                    run_dates.append(rd)
                except (ValueError, AttributeError) as e:
                    logger.warning(
                        "MLGATE_EVIDENCE_LOOP action=error reason=%s run_id=%s",
                        type(e).__name__,
                        r[5],
                    )
                    counters["errors"] += 1
            if not run_dates:
                continue

            min_run_date = min(run_dates)
            days_observed = (now - min_run_date).days

            if days_observed < ACCRUAL_WINDOW_DAYS:
                # Window still open: log and skip the whole group; do NOT flip.
                logger.info(
                    "MLGATE_EVIDENCE_LOOP action=skip reason=accrual_window_open days_observed=%d",
                    days_observed,
                )
                counters["skipped"] += len(group_rows)
                continue

            # Window closed — publish each row in the group.
            for r in group_rows:
                (
                    architecture,
                    symbol,
                    horizon,
                    target_mode,
                    hp_hash,
                    run_id,
                    _run_date,
                    _dsr,
                    _oos_sharpe,
                ) = r

                returns = _resolve_returns(
                    run_id=run_id,
                    returns_source=returns_source,
                )
                if returns is None:
                    logger.info(
                        "MLGATE_EVIDENCE_LOOP action=skip reason=returns_unavailable run_id=%s",
                        run_id,
                    )
                    counters["skipped"] += 1
                    continue

                if dry_run:
                    # Dry-run path: log what would happen, skip the (expensive)
                    # bootstrap PSR-CI call AND skip the UPDATE.
                    logger.info(
                        "MLGATE_EVIDENCE_LOOP action=publish run_id=%s psr_point=DRY_RUN psr_ci_low=DRY_RUN psr_ci_high=DRY_RUN",
                        run_id,
                    )
                    counters["published"] += 1
                    continue

                try:
                    psr = compute_psr_with_bootstrap_ci(returns, seed=_PSR_CI_SEED)
                except (ValueError, RuntimeError) as e:
                    logger.error(
                        "MLGATE_EVIDENCE_LOOP action=error reason=%s run_id=%s",
                        type(e).__name__,
                        run_id,
                    )
                    counters["errors"] += 1
                    continue

                # Single transaction: UPDATE psr_ci_published on the row matching
                # the full composite PK. All values are bound via ? placeholders
                # (T-03-08: no value interpolation; same style as
                # services/tournament-harness/app/leaderboard/db.py:_INSERT_LEADERBOARD_SQL).
                try:
                    conn.execute(
                        "UPDATE leaderboard SET psr_ci_published = 1"
                        " WHERE architecture = ?"
                        "   AND symbol = ?"
                        "   AND horizon = ?"
                        "   AND target_mode = ?"
                        "   AND hp_hash = ?"
                        "   AND run_id = ?",
                        (architecture, symbol, horizon, target_mode, hp_hash, run_id),
                    )
                    conn.commit()
                except sqlite3.Error as e:
                    logger.error(
                        "MLGATE_EVIDENCE_LOOP action=error reason=%s run_id=%s",
                        type(e).__name__,
                        run_id,
                    )
                    counters["errors"] += 1
                    continue

                logger.info(
                    "MLGATE_EVIDENCE_LOOP action=publish run_id=%s psr_point=%.4f psr_ci_low=%.4f psr_ci_high=%.4f",
                    run_id,
                    psr["psr_point"],
                    psr["psr_ci_low"],
                    psr["psr_ci_high"],
                )
                counters["published"] += 1

    finally:
        conn.close()

    return counters


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[list] = None) -> int:
    """Argparse + dispatch. Returns the process exit code.

    Exit codes:
      * ``0`` — ran to completion (zero errors)
      * ``1`` — argparse failure or paper-mode precondition violation
      * ``2`` — sqlite3 / runtime errors during the loop
    """
    # Configure root logger so the LOG_PREFIX lines surface on stdout for CLI
    # operators (tests use caplog and do not depend on this handler).
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        stream=sys.stdout,
    )

    parser = argparse.ArgumentParser(
        prog="run_evidence_loop.py",
        description=(
            "MLGATE-01 evidence-loop driver. Walks un-published leaderboard rows "
            "and publishes PSR-CI when the 7-day accrual window has closed for "
            "a natural-key group."
        ),
    )
    parser.add_argument(
        "--db-path",
        default=resolve_db_path(),
        metavar="PATH",
        help=(f"Path to the tournament-harness sqlite DB (default: {DEFAULT_TOURNAMENT_DB_PATH})."),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Enumerate eligible rows and log what would happen, but perform "
            "no UPDATEs and skip the bootstrap PSR-CI call."
        ),
    )
    parser.add_argument(
        "--returns-source",
        default=None,
        metavar="PATH",
        help=(
            "Optional test override: path to a JSON file (or its containing "
            'directory) with {"returns": [...]} — same returns array used '
            "for every eligible row. Production resolves from "
            ".planning/evidence/forward_paper_test/<flag>/<run_id>/run.json."
        ),
    )

    args = parser.parse_args(argv)

    # Safety: refuse to run under TRADING_MODE=LIVE. Sys.exit(1) on violation.
    _check_paper_mode_precondition()

    try:
        result = run_evidence_loop(
            db_path=args.db_path,
            dry_run=args.dry_run,
            returns_source=Path(args.returns_source) if args.returns_source else None,
        )
    except sqlite3.Error as e:
        # Never leak full sqlite messages (may include filesystem paths)
        # — mirrors services/trading-engine/app/preflight/checks.py:246-251
        # disposition for T-09-01-03.
        print(
            f"ERROR: sqlite error during evidence loop: {type(e).__name__}",
            file=sys.stderr,
        )
        return 2

    if result["errors"] > 0:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
