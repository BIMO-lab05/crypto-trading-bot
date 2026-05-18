#!/usr/bin/env python3
"""LIVECLOSE-03 PSR-evidence exporter.

Queries the ``leaderboard`` table (per migration 0002 authority — the
REQUIREMENTS.md wording ``tournament_results`` is incorrect; see
``services/tournament-harness/migrations/0002_mlgate_evidence_columns.sql``
lines 22-27) for ≥``ACCRUAL_WINDOW_DAYS`` consecutive UTC-calendar-day rows
with ``psr_ci_published=1`` in some natural-key group, then writes an
evidence JSON file under ``.planning/evidence/LIVECLOSE-03/``.

Single-source-of-truth contract: ``ACCRUAL_WINDOW_DAYS`` is imported from
``scripts.forward_paper_test.run_evidence_loop`` — NEVER redefined inline.
Drift between Phase 9 and Phase 11.1 would be silent and load-bearing for
the ML re-enablement gate; the import IS the contract.

Operator usage:

    python -m scripts.closure.liveclose_03_psr_evidence \\
        --db-path /data/tournament.db \\
        --target-path .planning/evidence/LIVECLOSE-03/psr-evidence.json

Exit codes:
    0 — AWAITING_HUMAN (technical PASS; operator still commits the JSON
        evidence file and flips the LIVECLOSE-03 row in
        ``.planning/state/carry_ins.json``)
    1 — INSUFFICIENT_DATA (fewer than ACCRUAL_WINDOW_DAYS consecutive-day
        rows in any natural-key group) OR paper-only refusal under
        TRADING_MODE=LIVE.

Plan: ``.planning/phases/11.1-carry-in-closure-harnesses-liveclose-01-05/11.1-04-PLAN.md``
Requirement: LIVECLOSE-03
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# Single source of truth — DO NOT redefine 7 inline. Drift between Phase 9
# and Phase 11.1 would be silent and load-bearing for the ML re-enablement
# gate. See plan 11.1-04 acceptance criterion grep gate.
from scripts.forward_paper_test.run_evidence_loop import ACCRUAL_WINDOW_DAYS  # noqa: E501

from scripts.closure._common import (
    STATUS_AWAITING_HUMAN,
    STATUS_INSUFFICIENT_DATA,
    write_evidence,
)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Mirrors scripts/forward_paper_test/run_evidence_loop.py:DEFAULT_TOURNAMENT_DB_PATH
DEFAULT_DB_PATH = "/data/tournament.db"

# Log line prefix — read by future digest tooling. Contract surface; do not
# rename without updating downstream consumers.
LOG_PREFIX = "LIVECLOSE_03"

# Path resolution: scripts/closure/liveclose_03_psr_evidence.py lives two
# directory levels below the repo root (parents[0]=scripts/closure/,
# parents[1]=scripts/, parents[2]=repo root).
_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_TARGET_DIR = _REPO / ".planning" / "evidence" / "LIVECLOSE-03"

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Safety precondition (paper-only)
# ---------------------------------------------------------------------------


def _check_paper_mode_precondition() -> None:
    """Refuse to run under TRADING_MODE=LIVE.

    Verbatim re-use of the guard from
    :func:`scripts.forward_paper_test.run_evidence_loop._check_paper_mode_precondition`
    — the PSR-evidence exporter is paper-only by the same trust posture: it
    must never publish evidence during LIVE trading because the resulting
    JSON file gates a future auto-flip of ``ENABLE_ML_PREDICTIONS``.
    """
    trading_mode = os.environ.get("TRADING_MODE", "").upper()
    if trading_mode == "LIVE":
        print(
            "ERROR: TRADING_MODE=LIVE is set in the environment.\n"
            "The LIVECLOSE-03 PSR-evidence exporter is paper-only. Set "
            "TRADING_MODE=PAPER (or unset it) before running.",
            file=sys.stderr,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Core query + payload helpers
# ---------------------------------------------------------------------------


def _longest_consecutive_streak(distinct_dates: list[date]) -> int:
    """Return the length of the longest run of consecutive UTC calendar dates.

    ``distinct_dates`` MUST be sorted ascending and contain no duplicates.
    A "consecutive run" is a maximal subsequence where each successive date
    differs from its predecessor by exactly one day (no gaps).
    """
    if not distinct_dates:
        return 0
    longest = current = 1
    for prev, curr in zip(distinct_dates, distinct_dates[1:]):
        if curr - prev == timedelta(days=1):
            current += 1
            longest = max(longest, current)
        else:
            current = 1
    return longest


def query_seven_day_window(
    conn: sqlite3.Connection,
    window_days: int = ACCRUAL_WINDOW_DAYS,
) -> list[dict]:
    """Return all leaderboard rows from natural-key groups whose longest
    consecutive UTC-calendar-day streak meets or exceeds ``window_days``.

    The query is read-only (SELECT) — the harness MUST NOT mutate the
    leaderboard (T-09-01-01 spirit from Phase 9; T-11.1-04-01 in this plan's
    threat register).

    Returns a list of plain dicts (NOT sqlite3.Row) so the payload is JSON-
    serialisable downstream.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT architecture, symbol, horizon, target_mode, hp_hash, run_id,"
        " run_date, dsr, psr, oos_sharpe, psr_ci_published"
        " FROM leaderboard"
        " WHERE psr_ci_published = 1"
        " ORDER BY architecture, symbol, horizon, target_mode, hp_hash,"
        "          run_date"
    )
    raw_rows = cur.fetchall()

    if not raw_rows:
        return []

    # Determine column names — works whether row_factory is set or not.
    col_names = [desc[0] for desc in cur.description]

    # Cast every row to dict so downstream JSON serialisation can't trip
    # on sqlite3.Row objects.
    all_rows = [dict(zip(col_names, row)) for row in raw_rows]

    # Group by natural key (architecture, symbol, horizon, target_mode, hp_hash).
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in all_rows:
        key = (
            row["architecture"],
            row["symbol"],
            row["horizon"],
            row["target_mode"],
            row["hp_hash"],
        )
        groups[key].append(row)

    # For each group, compute the longest consecutive streak of distinct
    # UTC calendar dates from run_date. Emit ALL rows of any group that
    # meets the window threshold.
    passing_rows: list[dict] = []
    for _, group_rows in groups.items():
        distinct_dates: set[date] = set()
        for row in group_rows:
            run_date_str = row["run_date"]
            if not run_date_str:
                continue
            try:
                # run_date is ISO-8601 UTC string ("YYYY-MM-DDTHH:MM:SSZ" or
                # "YYYY-MM-DD"). Take the calendar-date portion only.
                distinct_dates.add(date.fromisoformat(run_date_str[:10]))
            except (ValueError, TypeError):
                # Skip un-parseable rows; never raise from a read query.
                continue
        sorted_dates = sorted(distinct_dates)
        if _longest_consecutive_streak(sorted_dates) >= window_days:
            passing_rows.extend(group_rows)

    return passing_rows


def build_evidence_payload(
    passing_rows: list[dict],
    db_path: str,
) -> dict:
    """Build the ``extra=`` payload for the ``write_evidence`` call.

    DOES NOT include any required-field keys (``status``, ``schema_version``,
    ``timestamp``, ``evidence_paths``, ``human_needed``, ``liveclose_id``);
    those are passed through ``write_evidence``'s named parameters. The
    collision guard in ``scripts.closure._common.write_evidence`` would
    otherwise raise ``ValueError`` (caller misuse) before jsonschema validates.

    The returned dict ALSO carries a top-level ``"status"`` key reflecting
    the harness verdict — callers can read it for log lines and exit-code
    selection, but they MUST pop it before passing the dict as ``extra=``
    to :func:`scripts.closure._common.write_evidence` (this function leaves
    that pop to the caller — see :func:`main`).
    """
    # Collect distinct natural keys for the passing groups so the operator
    # can see at a glance which (architecture, symbol, horizon, target_mode,
    # hp_hash) tuples cleared the 7-day bar.
    natural_keys_passing = sorted(
        {
            (
                row["architecture"],
                row["symbol"],
                row["horizon"],
                row["target_mode"],
                row["hp_hash"],
            )
            for row in passing_rows
        }
    )

    # Re-compute the max consecutive streak across all passing groups for
    # the audit field (purely informational).
    max_streak = 0
    if passing_rows:
        groups: dict[tuple, set[date]] = defaultdict(set)
        for row in passing_rows:
            key = (
                row["architecture"],
                row["symbol"],
                row["horizon"],
                row["target_mode"],
                row["hp_hash"],
            )
            run_date_str = row["run_date"]
            if not run_date_str:
                continue
            try:
                groups[key].add(date.fromisoformat(run_date_str[:10]))
            except (ValueError, TypeError):
                continue
        for _, dates in groups.items():
            streak = _longest_consecutive_streak(sorted(dates))
            if streak > max_streak:
                max_streak = streak

    # Naming note: AWAITING_HUMAN on technical PASS because the operator
    # still commits the JSON evidence file and flips the LIVECLOSE-03 row
    # in .planning/state/carry_ins.json. COMPLETE is reserved for terminal
    # closures where no operator follow-up remains.
    verdict_status = STATUS_AWAITING_HUMAN if passing_rows else STATUS_INSUFFICIENT_DATA

    # The status field is included here as informational metadata for the
    # caller; main() MUST pop it before forwarding the dict as `extra=` to
    # write_evidence (which would otherwise raise ValueError on collision).
    return {
        "status": verdict_status,
        "row_count": len(passing_rows),
        "natural_keys_passing": [list(k) for k in natural_keys_passing],
        "consecutive_days_observed_max": max_streak,
        "db_path": db_path,
        "rows": passing_rows,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.closure.liveclose_03_psr_evidence",
        description=(
            "LIVECLOSE-03 PSR-evidence exporter. Queries leaderboard for "
            "≥{n}-day consecutive-day rows with psr_ci_published=1.".format(
                n=ACCRUAL_WINDOW_DAYS,
            )
        ),
    )
    parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help="Path to the tournament-harness sqlite DB (default: %(default)s).",
    )
    parser.add_argument(
        "--target-path",
        type=Path,
        default=None,
        help=(
            "Output path for the evidence JSON. Default: "
            ".planning/evidence/LIVECLOSE-03/psr-evidence-<ts>.json"
        ),
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=ACCRUAL_WINDOW_DAYS,
        help=(
            "Override the consecutive-day window for tests. "
            "Production usage should NOT pass this; ACCRUAL_WINDOW_DAYS is "
            "the single source of truth (default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Python logging level (default: %(default)s).",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entrypoint.

    Returns:
        0 — AWAITING_HUMAN (technical PASS).
        1 — INSUFFICIENT_DATA or paper-only refusal under TRADING_MODE=LIVE.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    # Paper-only refusal (sys.exit(1) raises SystemExit; main() returns
    # nothing in that path).
    _check_paper_mode_precondition()

    # Resolve default target path lazily so the timestamp is captured at
    # invocation time (matches scripts/closure/_common.py:write_evidence
    # behaviour when target_path is None).
    if args.target_path is None:
        ts = datetime.now(timezone.utc).isoformat().replace(":", "").replace("-", "")
        args.target_path = _DEFAULT_TARGET_DIR / f"psr-evidence-{ts}.json"

    # Open sqlite read-only. The harness only executes SELECT; no INSERT/
    # UPDATE/DELETE — T-11.1-04-01 mitigation.
    conn = sqlite3.connect(args.db_path)
    try:
        passing_rows = query_seven_day_window(
            conn,
            window_days=args.window_days,
        )
    finally:
        conn.close()

    payload = build_evidence_payload(passing_rows, db_path=args.db_path)
    # Pop status BEFORE forwarding payload as extra=. The status is also
    # passed via write_evidence's named `status=` argument; leaving it in
    # the `extra` dict would trip the required-field collision guard in
    # scripts.closure._common.write_evidence (caller-misuse ValueError).
    status = payload.pop("status")

    # The evidence file path goes into evidence_paths so the LIVECLOSE-INDEX
    # row points at the JSON itself. Repo-relative form for downstream tools.
    try:
        rel_target = args.target_path.resolve().relative_to(_REPO)
        evidence_paths = [str(rel_target)]
    except ValueError:
        # target_path lives outside the repo (e.g. pytest tmp_path); record
        # the absolute path verbatim.
        evidence_paths = [str(args.target_path)]

    out_path = write_evidence(
        liveclose_id="LIVECLOSE-03",
        status=status,
        evidence_paths=evidence_paths,
        human_needed=True,
        extra=payload,
        target_path=args.target_path,
    )

    logger.info(
        "%s status=%s row_count=%d target=%s",
        LOG_PREFIX,
        status,
        payload["row_count"],
        out_path,
    )

    return 0 if status == STATUS_AWAITING_HUMAN else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
