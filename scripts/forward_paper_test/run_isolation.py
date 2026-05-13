"""Forward-paper-test run launcher.

CLI entry point:
    python -m scripts.forward_paper_test.run_isolation \\
        --flag <name> \\
        --duration-days N \\
        [--run-id <id>] \\
        [--paper-trade-log <path>] \\
        [--dry-run]

The --dry-run flag short-circuits before any docker compose invocation and
prints a JSON object describing the planned isolation run. Live launch (non
dry-run) is stubbed for Task 2.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.forward_paper_test.profiles import TIER1_FLAG_PROFILES

_REPO = Path(__file__).resolve().parents[2]
_EVIDENCE_BASE = _REPO / ".planning" / "evidence" / "forward_paper_test"

TIER1_FLAG_NAMES = list(TIER1_FLAG_PROFILES.keys())


def _get_git_sha() -> str:
    """Return the current HEAD SHA (short), or 'unknown' if git is unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(_REPO),
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _make_run_id() -> str:
    """Generate a UTC-timestamp-based run ID."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_dry_run_plan(
    flag: str,
    duration_days: int,
    run_id: str,
    paper_trade_log: str | None,
) -> dict:
    """Build the dry-run plan dict without touching the filesystem."""
    profile = TIER1_FLAG_PROFILES[flag]
    now = datetime.now(timezone.utc)
    planned_start = now.isoformat()
    planned_end = (now + timedelta(days=duration_days)).isoformat()
    evidence_path = str(_EVIDENCE_BASE / flag / run_id)
    return {
        "flag": flag,
        "env_overrides": profile["env_overrides"],
        "baseline_env_overrides": profile["baseline_env_overrides"],
        "evidence_path": evidence_path,
        "planned_start": planned_start,
        "planned_end": planned_end,
        "duration_days": duration_days,
        "git_sha": _get_git_sha(),
        **({"paper_trade_log": paper_trade_log} if paper_trade_log else {}),
    }


def run_isolation(
    flag: str,
    duration_days: int,
    run_id: str | None = None,
    paper_trade_log: str | None = None,
    dry_run: bool = False,
) -> None:
    """Launch an isolation run for the given flag.

    In --dry-run mode, prints a JSON plan and exits. In live mode (Task 2),
    the NotImplementedError below is replaced with the actual docker compose
    invocation.
    """
    if run_id is None:
        run_id = _make_run_id()

    if dry_run:
        plan = build_dry_run_plan(flag, duration_days, run_id, paper_trade_log)
        print(json.dumps(plan, indent=2))
        return

    # Live launch is wired in Task 2.
    raise NotImplementedError("live launch wired in Task 2")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Launch a forward-paper-test isolation run for one Tier-1 flag. "
            "Pass --dry-run to preview the plan without starting docker compose."
        )
    )
    parser.add_argument(
        "--flag",
        required=True,
        choices=TIER1_FLAG_NAMES,
        help="Tier-1 feature flag to test in isolation.",
    )
    parser.add_argument(
        "--duration-days",
        type=int,
        default=7,
        metavar="N",
        help="How many days to run the isolation (default: 7).",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        metavar="ID",
        help="Optional run identifier (default: UTC timestamp).",
    )
    parser.add_argument(
        "--paper-trade-log",
        default=None,
        metavar="PATH",
        help="Path where the paper-trade engine writes its trade log.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned isolation overlay as JSON and exit without launching.",
    )

    args = parser.parse_args()
    run_isolation(
        flag=args.flag,
        duration_days=args.duration_days,
        run_id=args.run_id,
        paper_trade_log=args.paper_trade_log,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
