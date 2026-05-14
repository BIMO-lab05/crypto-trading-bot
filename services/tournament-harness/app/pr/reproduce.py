"""run_reproduce — `tournament reproduce {tid} --git-sha {sha}` (04-04).

Phase 4 reproducibility verifier. Re-derives significance.json from a snapshot
at the recorded git_sha and asserts the result is bit-(near-)identical to the
operator's original within D-12 FP-noise tolerance.

Contract:
- Refuse on dirty git tree (D-12 — NO `--allow-dirty` opt-out here, unlike
  `tournament run` and `tournament open-pr`).
- Refuse on HEAD ≠ git_sha_expected (operator must `git checkout` first).
- Build temp leaderboard SQLite at data/leaderboard/reproduce_{tid}.db (CD-06)
  from the snapshot rows. Production tournaments.db is NEVER touched.
- Re-run the open-pr pipeline in --dry-run mode with output_suffix="dry-run"
  so the operator's original {tid}.{ensemble,significance,leaderboard} files
  are never overwritten (W2 — no atomic-rename choreography).
- Diff per-symbol significance keys (sharpe_lift, dir_acc_lift, sharpe_pvalue,
  dir_acc_pvalue) within tolerance: |Δsharpe|≤1e-6, |Δp|≤0.005.
- On match: clean up temp DB + scratch dry-run artifacts; exit 0.
- On mismatch: retain temp DB + scratch artifacts for forensic inspection;
  exit 4.

Exit codes:
  0  reproduced significance is identical within tolerance
  2  missing inputs (snapshot/baseline absent) OR temp-DB conflict without --force
  3  dirty git tree OR HEAD mismatch (D-12)
  4  reproducibility broken — diff exceeds D-12 tolerance
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

from app.leaderboard.db import LeaderboardDB, run_migrations
from app.orchestrator.launcher import _git_is_dirty, _git_sha


logger = logging.getLogger(__name__)

HARNESS_ROOT = Path(__file__).resolve().parents[2]  # services/tournament-harness/
MIGRATIONS_DIR = HARNESS_ROOT / "migrations"

# D-12 FP-noise tolerance (boundary inclusive).
SHARPE_TOLERANCE = 1e-6
PVALUE_TOLERANCE = 0.005

# Scratch artifact suffix written by the inner open-pr dry-run. Naming this as
# a constant keeps the cleanup loop and the artifact-path expectations in lock-step.
_DRYRUN_SUFFIX = "dry-run"
_ARTIFACT_EXTS = ("significance.json", "ensemble.json", "leaderboard.md")


def _validate_tid(tid: str) -> None:
    """T-04-20: reject path-traversal / NUL / whitespace characters in tournament_id."""
    if not tid or any(ch in tid for ch in ("/", "..", "\0", " ", "\\", "\n", "\t")):
        raise ValueError(f"invalid tournament_id: {tid!r}")


def _temp_db_path(tournament_id: str) -> Path:
    """CD-06 forensic temp DB path. NEVER overlaps with production tournaments.db."""
    _validate_tid(tournament_id)
    return HARNESS_ROOT / "data" / "leaderboard" / f"reproduce_{tournament_id}.db"


def _wrap_snapshot_row_for_insert(row: Dict[str, Any]) -> Dict[str, Any]:
    """Adapt a flat snapshot row → the nested shape `LeaderboardDB.insert_run` expects.

    Snapshot rows store leaderboard columns flat (sqlite Row dict). insert_run
    expects `metrics: {...}` nested + top-level identity fields. We re-pack
    here so the temp DB rebuild stays a one-liner per row at the call-site.
    """
    return {
        "run_id": row["run_id"],
        "tournament_id": row["tournament_id"],
        "architecture": row["architecture"],
        "symbol": row["symbol"],
        "horizon": row.get("horizon", 0),
        "target_mode": row.get("target_mode", "log_returns"),
        "hp_hash": row["hp_hash"],
        "git_sha": row.get("git_sha", "unknown"),
        "tournament_start_ts": row.get("tournament_start_ts", ""),
        "train_window_includes_contaminated": row.get(
            "train_window_includes_contaminated", 0
        ),
        "status": row.get("status", "success"),
        "failure_reason": row.get("failure_reason"),
        "failure_stderr_tail": row.get("failure_stderr_tail"),
        "metrics": {
            "r2_returns": row.get("r2_returns"),
            "dir_acc_corrected": row.get("dir_acc_corrected"),
            "oos_sharpe": row.get("oos_sharpe"),
            "psr": row.get("psr"),
            "dsr": row.get("dsr"),
            "cpcv_dsr": row.get("cpcv_dsr"),
            "train_seconds": row.get("train_seconds"),
        },
    }


def _diff_significance(
    original: Dict[str, Any], reproduced: Dict[str, Any]
) -> List[str]:
    """Return list of diff strings; empty list ⇔ within D-12 tolerance.

    Boundary-inclusive: a diff exactly at the tolerance value is treated as
    a pass (uses `>` not `>=`).
    """
    diffs: List[str] = []
    orig_per_sym = original.get("per_symbol", {}) or {}
    rep_per_sym = reproduced.get("per_symbol", {}) or {}
    keys_under_test = (
        ("sharpe_lift", SHARPE_TOLERANCE),
        ("dir_acc_lift", SHARPE_TOLERANCE),
        ("sharpe_pvalue", PVALUE_TOLERANCE),
        ("dir_acc_pvalue", PVALUE_TOLERANCE),
    )
    for sym, orig in orig_per_sym.items():
        rep = rep_per_sym.get(sym, {})
        for key, tol in keys_under_test:
            a = float(orig.get(key, 0.0) or 0.0)
            b = float(rep.get(key, 0.0) or 0.0)
            delta = abs(a - b)
            if delta > tol:
                diffs.append(f"{sym}.{key}: {a} vs {b} (delta={delta:.6g}, tol={tol})")
    return diffs


def _cleanup_dryrun_artifacts(snap_dir: Path, tournament_id: str) -> None:
    """Remove the {tid}.dry-run.* scratch artifacts. Idempotent."""
    for ext in _ARTIFACT_EXTS:
        (snap_dir / f"{tournament_id}.{_DRYRUN_SUFFIX}.{ext}").unlink(missing_ok=True)


def run_reproduce(
    tournament_id: str,
    *,
    git_sha_expected: str,
    force: bool = False,
) -> int:
    """Verify reproducibility of a recorded tournament's significance.json.

    See module docstring for the full contract + exit-code map.
    """
    _validate_tid(tournament_id)

    # 1. Refusal gates (D-12).
    if _git_is_dirty():
        sys.stderr.write(
            "git tree dirty - `reproduce` REFUSES (no --allow-dirty here; "
            "reproducibility is the whole point).\n"
        )
        raise SystemExit(3)
    head = _git_sha()
    if head != git_sha_expected:
        sys.stderr.write(
            f"HEAD ({head}) != requested git_sha ({git_sha_expected}). "
            f"Run: git checkout {git_sha_expected}\n"
        )
        raise SystemExit(3)

    # 2. Inputs must exist (snapshot + original significance.json).
    snap_dir = HARNESS_ROOT / "data" / "snapshots"
    snapshot_path = snap_dir / f"{tournament_id}.json"
    if not snapshot_path.exists():
        sys.stderr.write(f"snapshot not found: {snapshot_path}\n")
        raise SystemExit(2)
    with open(snapshot_path) as f:
        snapshot = json.load(f)
    original_sig_path = snap_dir / f"{tournament_id}.significance.json"
    if not original_sig_path.exists():
        sys.stderr.write(
            f"original significance not found at {original_sig_path}; "
            "run `tournament open-pr` first to record a baseline.\n"
        )
        raise SystemExit(2)
    with open(original_sig_path) as f:
        original_sig = json.load(f)

    # 3. Temp DB rebuild from snapshot rows (CD-06). NEVER touches tournaments.db.
    temp_db = _temp_db_path(tournament_id)
    if temp_db.exists():
        if not force:
            sys.stderr.write(
                f"temp DB exists at {temp_db}; pass --force to overwrite, "
                "or delete it manually for forensic inspection.\n"
            )
            raise SystemExit(2)
        temp_db.unlink()
    temp_db.parent.mkdir(parents=True, exist_ok=True)
    run_migrations(temp_db, MIGRATIONS_DIR)
    db = LeaderboardDB(temp_db)
    try:
        config = snapshot.get("config", {}) or {}
        db.upsert_tournament(
            snapshot["tournament_id"],
            config.get("config_yaml", ""),
            config.get("git_sha", "unknown"),
            int(config.get("seed", 0) or 0),
        )
        for row in snapshot.get("rows", []):
            db.insert_run(_wrap_snapshot_row_for_insert(row))
    finally:
        db.close()

    # 4. Re-run open-pr in --dry-run with the dry-run suffix so the operator's
    #    originals are NEVER overwritten (W2: no atomic-rename choreography).
    from app.pr.open_pr import run_open_pr  # lazy import (heavy)

    rc = run_open_pr(
        tournament_id,
        allow_dirty=False,
        dry_run=True,
        output_suffix=_DRYRUN_SUFFIX,
    )
    if rc != 0:
        sys.stderr.write(f"open-pr dry-run returned non-zero rc={rc}\n")
        raise SystemExit(rc)

    reproduced_sig_path = (
        snap_dir / f"{tournament_id}.{_DRYRUN_SUFFIX}.significance.json"
    )
    if not reproduced_sig_path.exists():
        sys.stderr.write(
            f"open-pr dry-run did not write expected artifact: {reproduced_sig_path}\n"
        )
        # CD-06 forensic: leave temp DB on disk for inspection.
        raise SystemExit(4)
    with open(reproduced_sig_path) as f:
        reproduced_sig = json.load(f)

    diffs = _diff_significance(original_sig, reproduced_sig)
    if diffs:
        sys.stderr.write(
            "reproducibility broken - diffs:\n  " + "\n  ".join(diffs) + "\n"
        )
        # CD-06: retain temp DB AND dry-run scratch artifacts for forensics.
        raise SystemExit(4)

    # Success: original artifacts untouched (mtime preserved); clean up scratch.
    temp_db.unlink(missing_ok=True)
    _cleanup_dryrun_artifacts(snap_dir, tournament_id)
    print(
        json.dumps(
            {
                "tournament_id": tournament_id,
                "git_sha": head,
                "diffs": [],
            },
            indent=2,
        )
    )
    return 0


__all__ = [
    "run_reproduce",
    "_diff_significance",
    "_validate_tid",
    "_temp_db_path",
    "SHARPE_TOLERANCE",
    "PVALUE_TOLERANCE",
]
