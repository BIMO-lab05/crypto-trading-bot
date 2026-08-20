"""Forward-paper-test run launcher.

CLI entry point (two modes):

**Run mode** (default — no positional subcommand):
    python -m scripts.forward_paper_test.run_isolation \\
        --flag <name> \\
        --duration-days N \\
        [--run-id <id>] \\
        [--paper-trade-log <path>] \\
        [--dry-run]

    The --dry-run flag short-circuits before any docker compose invocation and
    prints a JSON object describing the planned isolation run. Live launch
    requires PAPER_TRADING_MODE=true in the environment (or .env); it refuses
    and exits non-zero when TRADING_MODE=LIVE is set.

**Publish-evidence subcommand**:
    python -m scripts.forward_paper_test.run_isolation publish-evidence <dir> \\
        [--force]

    Validates that the evidence directory contains run.json + psr_ci.json with
    psr_ci_low > 0.0, then writes the PSR_CI_PUBLISHED marker file. Refuses
    without --force when CI brackets zero (psr_ci_low <= 0.0). With --force,
    writes PSR_CI_PUBLISHED AND force_override.txt (logged for CI visibility).

**Complete-run subcommand**:
    python -m scripts.forward_paper_test.run_isolation complete-run <dir> \\
        [--force-unverified]

    Reads meta.json for the run window (planned_start_utc), queries closed
    positions opened at/after that timestamp via the clean_epoch_positions
    view (docker exec into crypto-bot-postgres), and writes run.json with
    per-trade returns. Refuses (nonzero exit, no run.json written) when the
    window has zero closed positions — psr_ci.load_run_returns requires a
    non-empty returns array.

    Before writing run.json, also verifies the LIVE trading-engine
    container's env + StartedAt still match meta.json's recorded flag window
    (_verify_flag_window) — catching a mid-window `docker compose up -d` that
    silently reverted the flag under test. Refuses on violations unless
    --force-unverified is passed, in which case run.json is still written but
    with "flag_window_verified": false and the violation list recorded.

Safety invariants (CLAUDE.md load-bearing):
  - PAPER_TRADING_MODE must be "true" in env before launching.
  - TRADING_MODE must NOT be "LIVE" in env.
  - No autonomous loops — this is a single-shot CLI, not a daemon.
  - Never invokes git/gh — operator manages version control.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from scripts.forward_paper_test.profiles import TIER1_FLAG_PROFILES

_REPO = Path(__file__).resolve().parents[2]
_EVIDENCE_BASE = _REPO / ".planning" / "evidence" / "forward_paper_test"

TIER1_FLAG_NAMES = list(TIER1_FLAG_PROFILES.keys())

# Service name in docker-compose.unified.yml that carries the Tier-1 flags.
_COMPOSE_FILE = "docker-compose.unified.yml"
_TRADING_ENGINE_SERVICE = "trading-engine"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


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


def _check_paper_mode_precondition() -> None:
    """Enforce PAPER_TRADING_MODE=true precondition before any live launch.

    Raises SystemExit(1) with a clear message when:
      - TRADING_MODE=LIVE is set in the environment, or
      - PAPER_TRADING_MODE is explicitly set to anything other than "true".

    The forward-paper-test harness is paper-only. It must never fire real orders.
    """
    trading_mode = os.environ.get("TRADING_MODE", "").upper()
    paper_mode = os.environ.get("PAPER_TRADING_MODE", "true").lower()

    if trading_mode == "LIVE":
        print(
            "ERROR: TRADING_MODE=LIVE is set in the environment.\n"
            "The forward-paper-test harness is paper-only. Set TRADING_MODE=PAPER\n"
            "(or unset it) before running an isolation test.",
            file=sys.stderr,
        )
        sys.exit(1)

    if paper_mode != "true":
        print(
            f"ERROR: PAPER_TRADING_MODE={paper_mode!r} — must be 'true'.\n"
            "The forward-paper-test harness must run in paper-trading mode.\n"
            "Set PAPER_TRADING_MODE=true in the environment before continuing.",
            file=sys.stderr,
        )
        sys.exit(1)


def _build_docker_argv(flag: str) -> list[str]:
    """docker compose argv for an isolation run.

    Env overrides are NOT argv: `docker compose up` has no -e flag (the
    pre-2026-08-20 version emitted one and could never have launched). They
    ride the subprocess environment instead — compose interpolates
    ${VAR:-default} entries in the trading-engine block from it.
    """
    return ["docker", "compose", "-f", _COMPOSE_FILE, "up", "-d", _TRADING_ENGINE_SERVICE]


def _write_meta_json(
    ev_dir: Path,
    flag: str,
    run_id: str,
    duration_days: int,
    paper_trade_log: Optional[str],
    profile: dict,
) -> None:
    """Write meta.json to the evidence directory."""
    now = datetime.now(timezone.utc)
    planned_start = now.isoformat()
    planned_end = (now + timedelta(days=duration_days)).isoformat()
    meta = {
        "flag": flag,
        "run_id": run_id,
        "planned_start_utc": planned_start,
        "planned_end_utc": planned_end,
        "duration_days": duration_days,
        "git_sha": _get_git_sha(),
        "baseline_env_overrides": profile["baseline_env_overrides"],
        "flag_env_overrides": profile["env_overrides"],
        "paper_trade_log_path": paper_trade_log or "",
    }
    (ev_dir / "meta.json").write_text(json.dumps(meta, indent=2))


# ---------------------------------------------------------------------------
# Dry-run plan (no side effects)
# ---------------------------------------------------------------------------


def build_dry_run_plan(
    flag: str,
    duration_days: int,
    run_id: str,
    paper_trade_log: Optional[str],
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


# ---------------------------------------------------------------------------
# Live launch
# ---------------------------------------------------------------------------


def run_isolation(
    flag: str,
    duration_days: int,
    run_id: Optional[str] = None,
    paper_trade_log: Optional[str] = None,
    dry_run: bool = False,
    subprocess_runner: Optional[Callable] = None,
) -> None:
    """Launch an isolation run for the given flag.

    Parameters
    ----------
    flag:
        One of the three Tier-1 flag names.
    duration_days:
        Planned duration (informational — the operator stops the run manually).
    run_id:
        Optional stable ID; defaults to a UTC timestamp.
    paper_trade_log:
        Path where the paper-trade engine writes its trade log.
    dry_run:
        If True, print the planned overlay as JSON and return without touching
        the filesystem or launching docker.
    subprocess_runner:
        Callable with the same signature as ``subprocess.run``. Defaults to the
        real ``subprocess.run``. Override in tests to capture argv without
        executing docker.
    """
    if run_id is None:
        run_id = _make_run_id()

    if dry_run:
        plan = build_dry_run_plan(flag, duration_days, run_id, paper_trade_log)
        print(json.dumps(plan, indent=2))
        return

    # --- safety precondition ---
    _check_paper_mode_precondition()

    profile = TIER1_FLAG_PROFILES[flag]
    runner = subprocess_runner if subprocess_runner is not None else subprocess.run

    # Build the full env override dict: flag ON + other two explicitly OFF.
    # This is the isolation guarantee: these three flags are pinned
    # regardless of .env — never inherited. The rest of the operator
    # environment (PATH, credentials, service URLs, etc.) still rides along
    # via os.environ below, since docker compose needs a usable environment
    # to run at all.
    env_overrides = dict(profile["env_overrides"])

    # 1. Materialise evidence directory and write meta.json BEFORE docker call.
    ev_dir = _EVIDENCE_BASE / flag / run_id
    ev_dir.mkdir(parents=True, exist_ok=True)
    _write_meta_json(ev_dir, flag, run_id, duration_days, paper_trade_log, profile)

    # 2. Launch docker compose with explicit env overrides riding the
    # subprocess environment (docker compose up has no -e flag; compose
    # interpolates ${VAR:-default} entries in the trading-engine block from
    # the invoking process's environment).
    argv = _build_docker_argv(flag)
    run_env = {**os.environ, **env_overrides}
    result = runner(argv, cwd=str(_REPO), env=run_env)
    if hasattr(result, "returncode") and result.returncode != 0:
        print(
            f"ERROR: docker compose exited {result.returncode}. "
            "Check service logs: "
            f"docker compose -f {_COMPOSE_FILE} logs -f {_TRADING_ENGINE_SERVICE}",
            file=sys.stderr,
        )
        sys.exit(result.returncode)

    print(
        f"Isolation run started.\n"
        f"  Flag      : {flag}\n"
        f"  Run ID    : {run_id}\n"
        f"  Evidence  : {ev_dir}\n"
        f"  Duration  : {duration_days} days (operator stops manually)\n\n"
        f"When complete, compute PSR CI:\n"
        f"  python -m scripts.forward_paper_test.psr_ci "
        f"--evidence-dir {ev_dir}\n\n"
        f"Then publish evidence:\n"
        f"  python -m scripts.forward_paper_test.run_isolation "
        f"publish-evidence {ev_dir}"
    )


# ---------------------------------------------------------------------------
# Publish-evidence subcommand
# ---------------------------------------------------------------------------


def publish_evidence(evidence_dir: Path, force: bool = False) -> None:
    """Validate a completed evidence directory and write PSR_CI_PUBLISHED marker.

    Validation steps (T-05-01-01 threat mitigation):
      1. run.json must exist.
      2. psr_ci.json must exist.
      3. psr_ci.json.psr_ci_low must be > 0.0 (CI does not bracket zero).
         Without --force: refuse and exit non-zero.
         With --force: write marker + force_override.txt sidecar.

    Note: The meta.json.duration_days >= 7 check is a runtime advisory here
    (operator may run shorter for testing); enforcement is via the runbook.
    """
    ev_dir = Path(evidence_dir)

    run_json_path = ev_dir / "run.json"
    psr_ci_json_path = ev_dir / "psr_ci.json"
    marker_path = ev_dir / "PSR_CI_PUBLISHED"
    force_log_path = ev_dir / "force_override.txt"

    # 1. Check run.json
    if not run_json_path.exists():
        print(
            f"ERROR: run.json not found in {ev_dir}\n"
            "Complete the paper-trade run first:\n"
            "  python -m scripts.forward_paper_test.run_isolation complete-run "
            f"{ev_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    # 2. Check psr_ci.json
    if not psr_ci_json_path.exists():
        print(
            f"ERROR: psr_ci.json not found in {ev_dir}\n"
            "Compute PSR CI first:\n"
            "  python -m scripts.forward_paper_test.psr_ci "
            f"--evidence-dir {ev_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    # 3. Load and validate psr_ci.json
    psr_ci = json.loads(psr_ci_json_path.read_text())
    psr_ci_low = float(psr_ci.get("psr_ci_low", float("nan")))

    if psr_ci_low <= 0.0:
        if not force:
            print(
                f"ERROR: psr_ci_low = {psr_ci_low:.4f} <= 0.0.\n"
                "A confidence interval that brackets zero means there is no\n"
                "statistically meaningful edge. The gate refuses to mark this\n"
                "as published without explicit override.\n\n"
                "To override (operator acknowledges risk):\n"
                f"  python -m scripts.forward_paper_test.run_isolation "
                f"publish-evidence {ev_dir} --force",
                file=sys.stderr,
            )
            sys.exit(1)
        else:
            # Force override: write marker but also write force_override.txt
            timestamp = datetime.now(timezone.utc).isoformat()
            force_log_path.write_text(
                f"FORCE OVERRIDE at {timestamp}\n"
                f"psr_ci_low = {psr_ci_low:.6f} (CI brackets zero)\n"
                "Operator acknowledged risk and forced publication.\n"
            )
            print(
                f"WARNING: psr_ci_low = {psr_ci_low:.4f} <= 0.0 — CI brackets zero.\n"
                f"Force override recorded to {force_log_path}",
                file=sys.stderr,
            )

    marker_path.write_text(
        f"PSR_CI_PUBLISHED\n"
        f"flag     : {psr_ci.get('flag', ev_dir.parent.name)}\n"
        f"psr_ci_low: {psr_ci_low:.6f}\n"
        f"published: {datetime.now(timezone.utc).isoformat()}\n"
    )
    print(f"PSR_CI_PUBLISHED marker written to {marker_path}")


# ---------------------------------------------------------------------------
# Complete-run subcommand
# ---------------------------------------------------------------------------

_POSTGRES_CONTAINER = "crypto-bot-postgres"
_TRADING_ENGINE_CONTAINER = "crypto-bot-trading"

# How much later than planned_start_utc the container's StartedAt may be
# before it's treated as a mid-window recreate rather than the original
# launch. See _verify_flag_window docstring for the reasoning.
_FLAG_WINDOW_TOLERANCE_SECONDS = 300


def _verify_flag_window(meta: dict) -> list[str]:
    """Verify the running trading-engine container still matches meta's flag window.

    Returns a list of human-readable violation strings — empty means clean.

    Two independent checks, both against the LIVE container (docker-exec /
    docker-inspect style, mirroring _fetch_closed_positions):

    1. Env override match: for every key in meta["flag_env_overrides"], the
       container's actual env value (`docker exec <container> printenv <KEY>`)
       must equal the recorded value. A bare `docker compose up -d` run
       against trading-engine from a shell that never exported the override
       recreates the container with the compose file's `${VAR:-false}`
       default, silently reverting the flag mid-window — this is exactly the
       failure this check exists to catch.

    2. StartedAt timing (`docker inspect <container> --format
       '{{.State.StartedAt}}'`): compared against meta["planned_start_utc"].

       IMPORTANT — read before "fixing" the comparison direction:
       meta.json is written FIRST by the launcher, THEN `docker compose up -d`
       is invoked, which creates/recreates the container. So StartedAt a few
       seconds AFTER planned_start_utc is the EXPECTED, normal case for every
       run — it is NOT a violation. Flagging "StartedAt is after
       planned_start" as a violation would make every clean run fail.

       The actual violation this check catches is the opposite direction of
       magnitude: StartedAt LATER than planned_start_utc by MORE than
       _FLAG_WINDOW_TOLERANCE_SECONDS (5 minutes). A gap that large means the
       container was (re)created well after the window's launch moment — i.e.
       some *other*, later `docker compose up -d` recycled the container
       (mid-window), not the original launch sequencing. That is the mixed-
       flag-window scenario this whole helper exists to detect. A negative
       delta (StartedAt before planned_start_utc) is not flagged either way —
       it should not occur given the launcher's own write-meta-then-launch
       ordering, but this helper stays narrowly focused on the "too late"
       failure mode rather than asserting an ordering invariant that belongs
       to the launcher, not the verifier.

    Never raises on docker/subprocess failure — a failed docker call is
    itself recorded as a violation string so callers can refuse cleanly
    (fail-closed) instead of crashing complete_run with a traceback.
    """
    violations: list[str] = []

    inspect_result = subprocess.run(
        ["docker", "inspect", _TRADING_ENGINE_CONTAINER, "--format", "{{.State.StartedAt}}"],
        capture_output=True,
        text=True,
    )
    if inspect_result.returncode != 0:
        violations.append(
            f"docker inspect {_TRADING_ENGINE_CONTAINER} failed (rc="
            f"{inspect_result.returncode}): {inspect_result.stderr.strip()}"
        )
    else:
        started_at_raw = inspect_result.stdout.strip()
        try:
            started_at = datetime.fromisoformat(started_at_raw)
            planned_start = datetime.fromisoformat(meta["planned_start_utc"])
            delta_seconds = (started_at - planned_start).total_seconds()
            if delta_seconds > _FLAG_WINDOW_TOLERANCE_SECONDS:
                violations.append(
                    f"container StartedAt ({started_at_raw}) is {delta_seconds:.0f}s "
                    f"after planned_start_utc ({meta['planned_start_utc']}) — exceeds "
                    f"the {_FLAG_WINDOW_TOLERANCE_SECONDS:.0f}s tolerance. The "
                    "container was likely recreated mid-window (e.g. a bare "
                    "`docker compose up -d` run without the flag override exported), "
                    "so this window may mix flag-on and flag-off behaviour."
                )
        except ValueError as exc:
            violations.append(f"could not parse container StartedAt {started_at_raw!r}: {exc}")

    for key, expected in meta.get("flag_env_overrides", {}).items():
        env_result = subprocess.run(
            ["docker", "exec", _TRADING_ENGINE_CONTAINER, "printenv", key],
            capture_output=True,
            text=True,
        )
        if env_result.returncode != 0:
            violations.append(
                f"docker exec {_TRADING_ENGINE_CONTAINER} printenv {key} failed (rc="
                f"{env_result.returncode}): {env_result.stderr.strip()}"
            )
            continue
        actual = env_result.stdout.strip()
        if actual != expected:
            violations.append(
                f"container env {key}={actual!r} does not match "
                f"meta.flag_env_overrides[{key}]={expected!r} — the container was "
                "likely recreated mid-window without the override exported."
            )

    return violations


def _fetch_closed_positions(since_iso: str) -> list[tuple]:
    """Closed clean-epoch positions opened at/after since_iso, via docker-exec psql.

    Uses the public.clean_epoch_positions view (scripts/sql/create_clean_epoch_views.sql)
    so pre-epoch legacy rows can never leak into evidence — the view itself
    already restricts to opened_at >= the epoch cutover, and this query adds
    the run-window filter on top. Host-run: goes through the postgres
    container like scripts/check_collection_gaps.py does for TimescaleDB.
    Injection-safe: since_iso comes from our own meta.json, but is still
    passed through a strict ISO parse before interpolation — never skip this
    guard.

    Real schema (verified 2026-08-20 against the live DB, not the SQLAlchemy
    model — this repo has known schema drift): status is a plain varchar
    column with CHECK IN ('OPEN', 'CLOSED'); side is 'LONG'/'SHORT'. Column
    names (symbol, side, entry_price, quantity, realized_pnl, opened_at,
    closed_at, status) match the brief's SQL sketch exactly.
    """
    datetime.fromisoformat(since_iso)  # raises on garbage — never skip

    sql = (
        "SELECT symbol, side, entry_price, quantity, realized_pnl, "
        "opened_at, closed_at FROM public.clean_epoch_positions "
        f"WHERE status = 'CLOSED' AND opened_at >= '{since_iso}' "
        "ORDER BY opened_at"
    )
    out = subprocess.run(
        [
            "docker",
            "exec",
            _POSTGRES_CONTAINER,
            "psql",
            "-U",
            "cryptobot",
            "-d",
            "cryptobot",
            "-t",
            "-A",
            "-F",
            "|",
            "-c",
            sql,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return [tuple(line.split("|")) for line in out.stdout.strip().splitlines() if line]


def complete_run(evidence_dir, force_unverified: bool = False) -> int:
    """Write run.json: per-trade returns for the run's window. Returns exit code.

    Per-trade return = realized_pnl / (entry_price * quantity), computed via
    Decimal and only cast to float at the JSON-serialization boundary (money
    rule — CLAUDE.md). Refuses (nonzero exit, no run.json written) when the
    window has zero closed positions: psr_ci.load_run_returns requires a
    non-empty, NaN-free returns array, and an empty one would poison the
    downstream evidence loop silently.

    Flag-window verification (BEFORE run.json is written): once there are
    positions to harvest, _verify_flag_window(meta) checks the LIVE
    trading-engine container's env and StartedAt against meta.json — guarding
    against a mid-window `docker compose up -d` that silently reverted the
    flag under test (see _verify_flag_window docstring). On violations:
      - force_unverified=False (default): print each violation to stderr,
        refuse to write run.json, return nonzero. Evidence integrity over a
        best-effort guess.
      - force_unverified=True: print a loud WARNING for each violation to
        stderr, but proceed — run.json is written with
        "flag_window_verified": false and "flag_window_violations": [...],
        so the compromised window is recorded honestly rather than silently
        passed off as clean. Mirrors publish-evidence's --force pattern
        (which also writes an override marker instead of pretending nothing
        happened).
      On a clean pass, run.json records "flag_window_verified": true and
      "flag_window_violations": [] .
    """
    evidence_dir = Path(evidence_dir)
    meta_path = evidence_dir / "meta.json"
    if not meta_path.exists():
        print(f"ERROR: meta.json not found in {evidence_dir}", file=sys.stderr)
        return 1

    meta = json.loads(meta_path.read_text())
    since = meta["planned_start_utc"]  # real _write_meta_json key (not launched_at_utc)
    rows = _fetch_closed_positions(since)
    if not rows:
        print(
            f"ERROR: no closed positions opened since {since}; refusing to write "
            "an empty run.json (psr_ci requires a non-empty returns array).",
            file=sys.stderr,
        )
        return 1

    violations = _verify_flag_window(meta)
    if violations:
        if not force_unverified:
            print(
                "ERROR: flag-window verification failed — the running "
                "trading-engine container no longer matches this run's "
                "recorded flag window:",
                file=sys.stderr,
            )
            for v in violations:
                print(f"  - {v}", file=sys.stderr)
            print(
                "Refusing to write run.json (evidence would be unverifiable). "
                "Relaunch the window cleanly, or re-run with --force-unverified "
                "to record the violations honestly instead of blocking evidence "
                "entirely.",
                file=sys.stderr,
            )
            return 1
        print(
            "WARNING: flag-window verification failed but --force-unverified was "
            "passed. Recording flag_window_verified=false and the violations "
            "below in run.json instead of refusing:",
            file=sys.stderr,
        )
        for v in violations:
            print(f"  - {v}", file=sys.stderr)

    from decimal import Decimal

    returns = []
    for symbol, side, entry_price, quantity, realized_pnl, opened_at, closed_at in rows:
        notional = Decimal(entry_price) * Decimal(quantity)
        returns.append(float(Decimal(realized_pnl) / notional))

    payload = {
        "returns": returns,
        "run_id": meta["run_id"],
        "flag": meta["flag"],
        "window": {"since": since},
        "n_positions": len(rows),
        "source": "clean_epoch_positions view via complete-run",
        "flag_window_verified": not violations,
        "flag_window_violations": violations,
    }
    (evidence_dir / "run.json").write_text(json.dumps(payload, indent=2))
    print(f"run.json written: {len(returns)} returns -> {evidence_dir / 'run.json'}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    # Top-level parser: check for publish-evidence / complete-run first (first
    # positional arg). We use a two-phase parse: peek at sys.argv[1] before
    # delegating. This preserves backward compat: `--help`, `--flag`, etc. at
    # top level still work exactly as Task 1's tests expect.
    if len(sys.argv) >= 2 and sys.argv[1] == "publish-evidence":
        _main_publish_evidence()
        return

    if len(sys.argv) >= 2 and sys.argv[1] == "complete-run":
        _main_complete_run()
        return

    _main_run()


def _main_run() -> None:
    """Argparse for the default run mode."""
    parser = argparse.ArgumentParser(
        prog="run_isolation.py",
        description=(
            "Launch a forward-paper-test isolation run for one Tier-1 flag. "
            "Pass --dry-run to preview the plan without starting docker compose.\n\n"
            "Subcommands: publish-evidence <dir> [--force]"
        ),
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


def _main_publish_evidence() -> None:
    """Argparse for the publish-evidence subcommand."""
    # sys.argv[1] is already 'publish-evidence'; parse the rest.
    parser = argparse.ArgumentParser(
        prog="run_isolation.py publish-evidence",
        description=(
            "Validate a completed evidence directory and write the "
            "PSR_CI_PUBLISHED marker file. Refuses when psr_ci_low <= 0.0 "
            "unless --force is passed."
        ),
    )
    parser.add_argument(
        "evidence_dir",
        metavar="DIR",
        help="Path to the evidence directory (contains run.json, psr_ci.json).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Override the psr_ci_low > 0.0 guard. Writes force_override.txt "
            "alongside PSR_CI_PUBLISHED so the operator's acknowledgement is logged."
        ),
    )

    # Strip 'publish-evidence' from argv before parsing
    args = parser.parse_args(sys.argv[2:])
    publish_evidence(Path(args.evidence_dir), force=args.force)


def _main_complete_run() -> None:
    """Argparse for the complete-run subcommand."""
    # sys.argv[1] is already 'complete-run'; parse the rest.
    parser = argparse.ArgumentParser(
        prog="run_isolation.py complete-run",
        description=(
            "Derive per-trade returns from closed clean-epoch positions opened "
            "since the run's launch time (per meta.json) and write run.json — "
            "the input publish-evidence and psr_ci.load_run_returns consume."
        ),
    )
    parser.add_argument(
        "evidence_dir",
        metavar="DIR",
        help="Path to the evidence directory (contains meta.json).",
    )
    parser.add_argument(
        "--force-unverified",
        action="store_true",
        help=(
            "Downgrade a flag-window verification failure from a refusal to a "
            "loud warning. run.json is still written, but with "
            "flag_window_verified: false and the violation list recorded — "
            "honest evidence over blocked evidence."
        ),
    )

    # Strip 'complete-run' from argv before parsing
    args = parser.parse_args(sys.argv[2:])
    sys.exit(complete_run(Path(args.evidence_dir), force_unverified=args.force_unverified))


if __name__ == "__main__":
    main()
