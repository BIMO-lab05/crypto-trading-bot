#!/usr/bin/env python3
"""
Pre-LIVE Preflight CLI (PREFLIGHT-01 / Phase 8 plan 02).

Asserts the 6 LIVE preconditions and prints structured JSON (or human-readable
text) per check. Imports the shared check module at
``services/trading-engine/app/preflight`` so the CLI and HTTP endpoint share
a single source of truth (no logic duplication).

Exits:

* ``0`` if ``overall == "PASS"``
* ``1`` if ``overall == "FAIL"`` or ``"UNKNOWN"``
* ``2`` on bad CLI args (unknown ``--check`` name, missing ``--target`` for
  ``--dry-run``, ``git show`` failure on the requested ref)

Usage::

    python3 scripts/preflight_live.py                      # text output
    python3 scripts/preflight_live.py --json               # JSON output
    python3 scripts/preflight_live.py --check=cap          # single check
    python3 scripts/preflight_live.py --dry-run --target=HEAD --json

``--dry-run --target=<ref>`` reads ``.env.example`` from the given git ref via
``git show <ref>:.env.example`` (since ``.env`` is gitignored). The parsed
key=value pairs are *overlaid onto* ``os.environ`` and ``reload_settings()``
is called before ``run_all()``. This matters because three of the six checks
(``check_paper_mode``, ``check_ack``, ``check_dsr_evidence``) read
``os.environ`` directly (08-01 design — same source-of-truth as
``services/trading-engine/app/main.py:251``); constructing a fresh
``Settings(**parsed)`` alone would silently leave those three checks reading
process env. The env mutation is reverted in a try/finally before the
function returns. See SUMMARY deviation note for the full reasoning.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

# Add ``services/trading-engine`` to sys.path so ``from app.preflight import
# run_all`` resolves without docker. Mirror the pattern at
# ``services/trading-engine/tests/unit/test_config.py`` (08-PATTERNS.md
# lines 340-342).
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "services" / "trading-engine"))

from app.preflight import run_all  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Pre-LIVE Preflight CLI (PREFLIGHT-01). Asserts the 6 LIVE "
            "preconditions and prints PASS/FAIL/UNKNOWN per check."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of human-readable text.",
    )
    parser.add_argument(
        "--text",
        action="store_true",
        help=(
            "Emit human-readable text (default behavior; flag exists for "
            "symmetry with --json)."
        ),
    )
    parser.add_argument(
        "--check",
        default=None,
        help=(
            "Run only one check by name. Valid names: cap, paper_mode, "
            "trading_mode, ack, emergency_stop, dsr_evidence."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Read .env.example from --target git ref instead of process env. "
            "Used by Phase 8's CI workflow (.github/workflows/preflight-"
            "live-readiness.yml). Requires --target."
        ),
    )
    parser.add_argument(
        "--target",
        default=None,
        help=(
            "Git ref to read .env.example from (e.g. HEAD, origin/main). "
            "Required when --dry-run is set."
        ),
    )
    return parser


_VALID_CHECK_NAMES = frozenset(
    {"cap", "paper_mode", "trading_mode", "ack", "emergency_stop", "dsr_evidence"}
)

# Env keys the 6 preflight checks actually read. ``--dry-run`` only overlays
# these onto ``os.environ`` so unrelated config (e.g. comma-separated lists
# that pydantic-settings tries to JSON-decode) doesn't fail the snapshot
# Settings rebuild. Per Phase 8 plan 02 spec.
_PREFLIGHT_ENV_KEYS = frozenset(
    {
        "TRADING_MODE",
        "MAX_RISK_PER_TRADE",
        "PAPER_TRADING_MODE",
        "LIVE_TRADING_ACK",
        "ENABLE_ML_PREDICTIONS",
        "EMERGENCY_STOP_FILE",
    }
)


def _parse_dotenv(blob: str) -> dict[str, str]:
    """Parse a dotenv-style blob into a flat dict.

    Skips blank lines and comments. Trims whitespace and surrounding quotes
    around the value. Returns an empty dict for an empty blob.
    """
    out: dict[str, str] = {}
    for raw_line in blob.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip inline trailing comment ("KEY=val  # comment"). Only when the
        # value is NOT quoted — quoted values may legitimately contain '#'.
        if value and not (value.startswith('"') or value.startswith("'")):
            hash_idx = value.find("#")
            if hash_idx >= 0:
                value = value[:hash_idx].rstrip()
        # Strip matching surrounding quotes (common in .env.example).
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            out[key] = value
    return out


def _load_env_snapshot(target: str) -> dict[str, str]:
    """Read .env.example from ``target`` git ref via ``git show``.

    Returns the parsed dict on success; raises ``RuntimeError`` on git failure
    so ``main`` can convert to a clean exit-2 message.
    """
    try:
        result = subprocess.run(
            ["git", "show", f"{target}:.env.example"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"git show {target}:.env.example failed: "
            f"{(exc.stderr or '').strip() or 'unknown error'}"
        ) from exc
    parsed = _parse_dotenv(result.stdout)
    # Filter to the env keys that the 6 preflight checks actually read. The
    # snapshot may include comma-separated list fields (TRADING_SYMBOLS,
    # etc.) that pydantic-settings tries to JSON-decode when populated as
    # env vars, breaking ``reload_settings()``. Filtering both keeps the
    # snapshot focused and avoids that failure mode.
    return {k: v for k, v in parsed.items() if k in _PREFLIGHT_ENV_KEYS}


def _filter_report_to_check(report_dict: dict, check_name: str) -> dict:
    """Build a fresh report dict with only the named check.

    ``PreflightReport`` is frozen, so we return a new dict (not a mutation).
    Recomputes ``overall`` from the filtered single-check set: any FAIL ->
    FAIL, else any UNKNOWN -> UNKNOWN, else PASS.
    """
    checks = [c for c in report_dict["checks"] if c["check"] == check_name]
    statuses = {c["status"] for c in checks}
    if "FAIL" in statuses:
        overall = "FAIL"
    elif "UNKNOWN" in statuses:
        overall = "UNKNOWN"
    else:
        overall = "PASS"
    return {
        "schema_version": report_dict["schema_version"],
        "overall": overall,
        "evaluated_at": report_dict["evaluated_at"],
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    # --check name validation BEFORE running anything (cheaper failure).
    if args.check is not None and args.check not in _VALID_CHECK_NAMES:
        print(
            f"unknown check: {args.check!r}; valid names: "
            f"{', '.join(sorted(_VALID_CHECK_NAMES))}",
            file=sys.stderr,
        )
        return 2

    if args.dry_run and not args.target:
        print(
            "--dry-run requires --target=<git-ref> (e.g. HEAD)",
            file=sys.stderr,
        )
        return 2

    # --- Run the 6 checks (with optional dry-run env overlay) ------------
    if args.dry_run:
        try:
            snapshot = _load_env_snapshot(args.target)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

        # Overlay snapshot onto os.environ, reload settings, run, restore.
        # Three of six checks (paper_mode, ack, dsr_evidence) read os.environ
        # directly per 08-01 design — passing a fresh Settings(**parsed)
        # alone would not change what those three see. See module docstring.
        saved = dict(os.environ)
        try:
            os.environ.update(snapshot)
            from app.config import reload_settings  # noqa: E402

            reload_settings()
            report = run_all()
        finally:
            # Clear keys we added that weren't in saved; restore originals.
            for key in snapshot:
                if key in saved:
                    os.environ[key] = saved[key]
                else:
                    os.environ.pop(key, None)
            # Settings should be reloaded one more time to pick up the
            # restored env in case the caller invokes anything else.
            from app.config import reload_settings  # noqa: E402

            reload_settings()
    else:
        report = run_all()

    # --- Build serializable dict + optional --check filter ----------------
    report_dict = asdict(report)
    if args.check is not None:
        report_dict = _filter_report_to_check(report_dict, args.check)

    overall = report_dict["overall"]

    if args.json:
        print(json.dumps(report_dict, indent=2))
    else:
        for c in report_dict["checks"]:
            print(f"  {c['status']:8s}  {c['check']:18s}  {c['detail']}")
        print(f"\nOVERALL: {overall}")

    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
