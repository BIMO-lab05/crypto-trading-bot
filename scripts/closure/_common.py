"""Shared evidence-write helper for LIVECLOSE carry-in closure harnesses.

Phase 11.1 Plan 01 (Wave 1 foundation). All five LIVECLOSE harnesses
(LIVECLOSE-01..05, Wave 2 plans 11.1-02..06) MUST import ``write_evidence``
from this module rather than re-implementing JSON serialisation. Bash
harnesses invoke the CLI subcommand ``python -m scripts.closure._common
write-evidence ...`` so JSON shape is enforced in one place.

This module is **closed for extension after Plan 11.1-01.** Wave 2 plans
consume read-only — they may import ``write_evidence`` / ``STATUS_*``,
but MUST NOT modify this file or ``.planning/evidence/_schema.json``.

Schema invariants enforced here:
  * ``schema_version`` is auto-injected from ``SCHEMA_VERSION`` (caller
    cannot override).
  * ``timestamp`` is auto-injected from ``datetime.now(timezone.utc)``
    (caller cannot override).
  * ``extra`` payload merges into the evidence dict but raises
    :class:`ValueError` when a key collides with a required schema field —
    the collision check fires **before** :func:`jsonschema.validate` so the
    error surfaces as ``ValueError`` (semantic intent: caller misuse), not
    ``ValidationError`` (data shape).

CLI surface (Wave-2 contract):
    python -m scripts.closure._common write-evidence \\
        --liveclose-id LIVECLOSE-0X \\
        --status COMPLETE|AWAITING_HUMAN|INSUFFICIENT_DATA|FAILED \\
        --evidence-path <repo-relative-path>  (repeatable) \\
        --human-needed | --no-human-needed \\
        --target-path <output.json> \\
        [--extra-json '{"ci_url":"..."}']

Exit code 0 on success, non-zero on validation failure.

Plan: .planning/phases/11.1-carry-in-closure-harnesses-liveclose-01-05/11.1-01-PLAN.md
Schema: .planning/evidence/_schema.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants — exported for downstream harnesses
# ---------------------------------------------------------------------------

# Status enum — MUST match .planning/evidence/_schema.json
# properties.status.enum exactly. Plan 11.1-01 acceptance test
# test_status_constants_match_schema_enum asserts this.
STATUS_COMPLETE = "COMPLETE"
STATUS_AWAITING_HUMAN = "AWAITING_HUMAN"
STATUS_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
STATUS_FAILED = "FAILED"

# Pinned schema version. Bump only on a breaking change to the required-field
# set or to the status enum (i.e. a change that would invalidate already-
# committed evidence files).
SCHEMA_VERSION = 1

# Path resolution: scripts/closure/_common.py is two directory levels below
# the repo root (parents[0]=scripts/closure/, parents[1]=scripts/,
# parents[2]=repo root). Mirrors scripts/forward_paper_test/run_isolation.py
# `_REPO = Path(__file__).resolve().parents[2]` idiom.
_REPO = Path(__file__).resolve().parents[2]
EVIDENCE_BASE = _REPO / ".planning" / "evidence"
SCHEMA_PATH = EVIDENCE_BASE / "_schema.json"

# Required-field set (kept as a frozenset for fast collision check). MUST
# stay in sync with the schema's `required` array; the test
# test_load_schema_returns_dict asserts the schema agrees.
_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "timestamp",
        "evidence_paths",
        "human_needed",
        "liveclose_id",
    }
)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def load_schema() -> dict[str, Any]:
    """Load and return the LIVECLOSE evidence JSON Schema.

    Raises:
        FileNotFoundError: when ``SCHEMA_PATH`` does not exist on disk.
    """
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(
            f"LIVECLOSE evidence schema not found at {SCHEMA_PATH}. "
            "Plan 11.1-01 Task 1 must run before any harness."
        )
    return json.loads(SCHEMA_PATH.read_text())


def write_evidence(
    liveclose_id: str,
    status: str,
    evidence_paths: list[str],
    human_needed: bool,
    extra: dict[str, Any] | None = None,
    target_path: Path | None = None,
) -> Path:
    """Build, validate, and write a LIVECLOSE evidence file.

    Args:
        liveclose_id: One of ``LIVECLOSE-01..05``. Enforced by schema enum.
        status: One of ``STATUS_COMPLETE``, ``STATUS_AWAITING_HUMAN``,
            ``STATUS_INSUFFICIENT_DATA``, ``STATUS_FAILED``.
        evidence_paths: Repo-relative paths to human-readable evidence
            artifacts. Empty list permitted for FAILED runs.
        human_needed: True when a wall-clock operator action is still
            required after the harness ran.
        extra: Optional payload extension (e.g. ``{"ci_url": "..."}``).
            Keys colliding with required schema fields raise ``ValueError``.
        target_path: Output path. Defaults to
            ``EVIDENCE_BASE / liveclose_id / "run-{timestamp}.json"``.
            Parent directories are created if missing.

    Returns:
        The path written.

    Raises:
        ValueError: When ``extra`` contains a key from the required-field
            set (caller misuse — fires *before* jsonschema validation).
        jsonschema.exceptions.ValidationError: When the resulting payload
            fails schema validation.
    """
    # Step 1 — collision check fires BEFORE validation so the test
    # contract distinguishes caller misuse (ValueError) from data-shape
    # errors (ValidationError).
    if extra:
        for required_key in _REQUIRED_FIELDS:
            if required_key in extra:
                raise ValueError(
                    f"extra key '{required_key}' collides with required field; "
                    "use the named write_evidence() parameter instead"
                )

    # Step 2 — build payload with auto-injected schema_version + timestamp.
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "evidence_paths": list(evidence_paths),
        "human_needed": bool(human_needed),
        "liveclose_id": liveclose_id,
    }
    if extra:
        payload.update(extra)

    # Step 3 — validate against schema. Raises jsonschema.ValidationError
    # on any drift (bad status enum, bad liveclose_id, wrong type, etc.).
    schema = load_schema()
    jsonschema.validate(payload, schema)

    # Step 4 — resolve target path and write.
    if target_path is None:
        ts = payload["timestamp"].replace(":", "").replace("-", "")
        target_path = EVIDENCE_BASE / liveclose_id / f"run-{ts}.json"
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    logger.info("evidence_written liveclose_id=%s target=%s", liveclose_id, target_path)
    return target_path


# ---------------------------------------------------------------------------
# CLI surface — Wave 2 bash harnesses (Plans 02 + 06) invoke this entrypoint
# instead of duplicating JSON writing.
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.closure._common",
        description="LIVECLOSE carry-in evidence helper (Phase 11.1).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    write = sub.add_parser(
        "write-evidence",
        help="Validate and write a LIVECLOSE evidence JSON file.",
    )
    write.add_argument(
        "--liveclose-id",
        required=True,
        choices=[f"LIVECLOSE-0{i}" for i in range(1, 6)],
        help="Carry-in identifier (LIVECLOSE-01..05).",
    )
    write.add_argument(
        "--status",
        required=True,
        # NB: do NOT pin choices here — the schema is the source of truth.
        # We want a BOGUS status to surface as a ValidationError so the
        # error message comes from jsonschema, not argparse.
        help="One of COMPLETE | AWAITING_HUMAN | INSUFFICIENT_DATA | FAILED.",
    )
    write.add_argument(
        "--evidence-path",
        action="append",
        default=[],
        dest="evidence_paths",
        help="Repo-relative path to an evidence artifact (repeatable).",
    )
    # BooleanOptionalAction (Python 3.9+) gives both --human-needed and
    # --no-human-needed from one declaration; required=True forces explicit
    # operator intent at the CLI surface.
    write.add_argument(
        "--human-needed",
        action=argparse.BooleanOptionalAction,
        required=True,
        help="True when a wall-clock operator action is still required.",
    )
    write.add_argument(
        "--target-path",
        type=Path,
        default=None,
        help="Output path. Default: .planning/evidence/<id>/run-<ts>.json.",
    )
    write.add_argument(
        "--extra-json",
        default=None,
        help='JSON object merged into payload (e.g. \'{"ci_url":"..."}\').',
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Returns 0 on success, 1 on validation failure (jsonschema or ValueError),
    2 on argparse failure (handled by argparse via SystemExit).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.cmd != "write-evidence":  # pragma: no cover - argparse rejects first
        parser.error(f"unknown subcommand: {args.cmd}")
        return 2

    extra: dict[str, Any] | None = None
    if args.extra_json:
        try:
            extra = json.loads(args.extra_json)
        except json.JSONDecodeError as exc:
            print(f"ERROR: --extra-json is not valid JSON: {exc}", file=sys.stderr)
            return 1
        if not isinstance(extra, dict):
            print("ERROR: --extra-json must decode to a JSON object", file=sys.stderr)
            return 1

    try:
        out = write_evidence(
            liveclose_id=args.liveclose_id,
            status=args.status,
            evidence_paths=args.evidence_paths,
            human_needed=args.human_needed,
            extra=extra,
            target_path=args.target_path,
        )
    except (jsonschema.exceptions.ValidationError, ValueError) as exc:
        print(f"ERROR: evidence validation failed: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(str(out))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
