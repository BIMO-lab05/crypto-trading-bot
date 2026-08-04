#!/usr/bin/env python3
"""
Tile Audit Runtime Probe (Phase 6, DASH-01).

Reads the machine-readable tile inventory at
``.planning/phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.json``,
hits every documented backing endpoint for tiles whose verdict is
``FIXED``, asserts the response shape matches the recorded one, and
prints PASS/FAIL per tile. Exits:

* ``0`` if every FIXED tile passes
* ``1`` if any FIXED tile fails (non-200 or shape mismatch)
* ``2`` on bad CLI args (missing ``--against``, missing inventory file)

LABELED_STALE, REMOVED, and PENDING-OPERATOR rows are NOT probed per
D-02 (they are inert by design for the regression gate).

Per D-09 security mitigation (T-06-01-01 Tampering): ``--against`` is
required. The script fail-closes (exit 2) if neither the flag nor the
``AUDIT_TILES_AGAINST`` environment variable is supplied, so a localhost
default is never silently written to disk.

Usage::

    python3 scripts/audit_tiles.py --against http://localhost:8000
    AUDIT_TILES_AGAINST=http://localhost:8000 python3 scripts/audit_tiles.py
    python3 scripts/audit_tiles.py --against http://localhost:8000 \\
        --inventory /path/to/06-TILE-AUDIT.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

_REPO_ROOT = Path(__file__).resolve().parent.parent
# Phase 6 (DASH-01) shipped in v1.0 and was archived under
# .planning/milestones/v1.0-phases/ at v1.1 cutover (commit d1daa1a).
# AUDIT-01 (Phase 16, 2026-05-23) restored the file to the archive path
# and updated this reference. The artifact is frozen — its verdicts pin the
# v1.0 regression gate and are not re-edited.
_AUDIT_JSON = (
    _REPO_ROOT
    / ".planning"
    / "milestones"
    / "v1.0-phases"
    / "06-dashboard-audit-safety-state"
    / "06-TILE-AUDIT.json"
)

# ANSI color codes (same palette as scripts/monitor.py).
#
# WR-06: emit ANSI codes only when stdout is a real TTY AND the operator
# has not opted out via NO_COLOR (https://no-color.org). When the script
# is invoked from CI, piped to a file, or captured by `docker logs`, the
# escape sequences would otherwise be written as literal bytes (e.g.
# "[0;32mPASS[0m") and corrupt the regression-gate output. The five
# scripts/test_audit_tiles.py tests only assert "PASS"/"FAIL" substring
# presence so they pass either way — the regression here is operator
# legibility, not test correctness.
_use_color = sys.stdout.isatty() and "NO_COLOR" not in os.environ
GREEN = "\033[0;32m" if _use_color else ""
RED = "\033[0;31m" if _use_color else ""
YELLOW = "\033[1;33m" if _use_color else ""
NC = "\033[0m" if _use_color else ""

_PROBE_TIMEOUT_SEC = 10


# ---------------------------------------------------------------------------
# Inventory loading
# ---------------------------------------------------------------------------


def load_inventory(path: Path) -> list[dict]:
    """Load tile inventory JSON and filter to probeable verdict == "FIXED" rows.

    Only ``FIXED`` rows are probed; ``LABELED_STALE``, ``REMOVED``, and
    ``PENDING-OPERATOR`` rows are inert per D-02 (the audit table itself
    handles those; the regression gate only cares about endpoints we
    expect to keep working).

    Page-level composition rows (whose ``endpoint`` begins with ``n/a``)
    are also skipped even when verdict is ``FIXED`` -- they have no
    single backing endpoint to probe; their child tiles carry the real
    endpoint verdicts.

    Raises ``FileNotFoundError`` if ``path`` does not exist; ``main()``
    converts that to a clean exit-2 message (no Python traceback).
    """
    if not path.exists():
        raise FileNotFoundError(f"inventory file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    tiles = payload.get("tiles", [])
    if not isinstance(tiles, list):
        raise ValueError(
            f"inventory 'tiles' must be a list, got {type(tiles).__name__}"
        )
    out = []
    for row in tiles:
        if row.get("verdict") != "FIXED":
            continue
        endpoint = (row.get("endpoint") or "").strip()
        if not endpoint or endpoint.lower().startswith("n/a"):
            # Page-level composition row -- no single endpoint to probe.
            continue
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# Shape matching
# ---------------------------------------------------------------------------


def _shape_matches(got: Any, expected: Any) -> bool:
    """Shallow shape match between ``got`` (response JSON) and ``expected``.

    The ``expected`` value uses a tiny DSL:

    * ``"number"``  -> int | float (bools are NOT numbers here)
    * ``"string"``  -> str
    * ``"bool"``    -> bool
    * ``"object"``  -> dict
    * ``"list"``    -> list (any element type)
    * ``"list[<X>]"`` -> list (length-0 accepted; element-0 type is
      checked recursively if list is non-empty)
    * ``dict``      -> recursive match: every key in ``expected`` must be
      present in ``got`` with a compatible inner type.

    Length is NOT checked. Empty lists satisfy ``list[*]`` per Test 4.
    """
    # Recursive dict case
    if isinstance(expected, dict):
        if not isinstance(got, dict):
            return False
        for key, sub_expected in expected.items():
            if key not in got:
                return False
            if not _shape_matches(got[key], sub_expected):
                return False
        return True

    # Primitive-tag case
    if isinstance(expected, str):
        tag = expected.strip()
        if tag == "number":
            return isinstance(got, (int, float)) and not isinstance(got, bool)
        if tag == "string":
            return isinstance(got, str)
        if tag == "bool":
            return isinstance(got, bool)
        if tag == "object":
            return isinstance(got, dict)
        if tag == "list":
            return isinstance(got, list)
        if tag.startswith("list[") and tag.endswith("]"):
            if not isinstance(got, list):
                return False
            # Empty list is accepted per Test 4
            if not got:
                return True
            inner = tag[len("list[") : -1].strip()
            return _shape_matches(got[0], inner)
        # Unknown tag: be permissive (don't fail the gate on doc typos)
        return True

    # Unknown expected shape descriptor -> permissive
    return True


# ---------------------------------------------------------------------------
# Per-tile probe
# ---------------------------------------------------------------------------


def probe(base_url: str, row: dict) -> dict:
    """Probe one endpoint and return a result dict.

    Returns ``{tile, endpoint, status_code, ok, elapsed_ms, error}``.
    ``ok`` is True iff HTTP 200 AND response JSON matches ``row['expected_shape']``.
    Network errors are caught and reported via ``error`` with ``ok=False``.
    """
    endpoint = row["endpoint"]
    url = f"{base_url.rstrip('/')}{endpoint}"
    expected_shape = row.get("expected_shape", {})
    t0 = datetime.now(timezone.utc)
    try:
        resp = requests.get(url, timeout=_PROBE_TIMEOUT_SEC)
    except Exception as exc:  # noqa: BLE001 — surface any transport failure
        elapsed_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
        return {
            "tile": row.get("tile"),
            "endpoint": endpoint,
            "status_code": None,
            "ok": False,
            "elapsed_ms": elapsed_ms,
            "error": str(exc),
        }
    elapsed_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
    status_code = resp.status_code
    shape_ok = False
    if status_code == 200:
        try:
            body = resp.json()
            shape_ok = _shape_matches(body, expected_shape)
        except Exception as exc:  # noqa: BLE001
            return {
                "tile": row.get("tile"),
                "endpoint": endpoint,
                "status_code": status_code,
                "ok": False,
                "elapsed_ms": elapsed_ms,
                "error": f"json decode: {exc}",
            }
    return {
        "tile": row.get("tile"),
        "endpoint": endpoint,
        "status_code": status_code,
        "ok": status_code == 200 and shape_ok,
        "elapsed_ms": elapsed_ms,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Tile audit runtime probe (Phase 6, DASH-01). Hits every FIXED-verdict "
            "endpoint in the inventory and prints PASS/FAIL per tile."
        ),
    )
    parser.add_argument(
        "--against",
        default=None,
        help=(
            "Base URL of the running stack (e.g. http://localhost:8000). "
            "REQUIRED -- fail-closed per D-09 (T-06-01-01 Tampering mitigation). "
            "Alternatively set the AUDIT_TILES_AGAINST environment variable."
        ),
    )
    parser.add_argument(
        "--inventory",
        default=str(_AUDIT_JSON),
        help="Path to 06-TILE-AUDIT.json inventory sidecar.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    against = args.against or os.environ.get("AUDIT_TILES_AGAINST")
    if not against:
        # D-09 fail-closed: no localhost default written to disk.
        print(
            "ERROR: --against is required (no default; D-09 fail-closed). "
            "Pass --against <url> or set AUDIT_TILES_AGAINST in the environment.",
            file=sys.stderr,
        )
        sys.exit(2)

    inventory_path = Path(args.inventory)
    try:
        rows = load_inventory(inventory_path)
    except FileNotFoundError as exc:
        print(f"ERROR: inventory not found: {inventory_path}", file=sys.stderr)
        print(f"       {exc}", file=sys.stderr)
        sys.exit(2)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: invalid inventory at {inventory_path}: {exc}", file=sys.stderr)
        sys.exit(2)

    if not rows:
        print(f"{YELLOW}No FIXED-verdict tiles in inventory; nothing to probe.{NC}")
        sys.exit(0)

    fails = 0
    for row in rows:
        result = probe(against, row)
        mark = f"{GREEN}PASS{NC}" if result["ok"] else f"{RED}FAIL{NC}"
        tile_name = (result["tile"] or "?")[:30]
        endpoint = (result["endpoint"] or "?")[:50]
        http_code = result["status_code"] if result["status_code"] is not None else "—"
        elapsed = result["elapsed_ms"] if result["elapsed_ms"] is not None else "—"
        print(
            f"  {mark}  {tile_name:30s}  {endpoint:50s}  http={http_code}  {elapsed}ms"
        )
        if not result["ok"]:
            fails += 1
            if result["error"]:
                print(f"        error: {result['error']}")

    print()
    summary_color = GREEN if fails == 0 else RED
    print(f"{summary_color}{len(rows) - fails}/{len(rows)} tiles PASS{NC}")
    sys.exit(0 if fails == 0 else 1)


if __name__ == "__main__":
    main()
