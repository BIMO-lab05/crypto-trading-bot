#!/usr/bin/env python3
"""BC-01: Repo-wide audit of Bybit-bypass sites.

Emits JSON array per .planning/REQUIREMENTS.md BC-01 schema. See
.planning/phases/13-bybit-connector-market-data-centralization/13-CONTEXT.md
D-01..D-09 for scope.

Schema (each entry):
    {
        "file": str,             # repo-relative POSIX path
        "line": int,             # 1-based
        "kind": str,             # pybit_import|mainnet_rest_url|testnet_rest_url|wss_stream_url
        "current_call": str,     # source line stripped
        "replacement_path": str  # bybit-connector REST path the refactor will target
    }

Output sorted by (file, line, kind) for deterministic / idempotent runs.

Usage:
    python scripts/audit_bybit_bypass.py                              # JSON to stdout
    python scripts/audit_bybit_bypass.py --out path/to/audit.json     # JSON to file
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

# Banned patterns per CONTEXT D-05.
BANNED_PATTERNS: dict[str, re.Pattern[str]] = {
    "pybit_import": re.compile(r"^\s*(from\s+pybit\b|import\s+pybit\b)", re.MULTILINE),
    "mainnet_rest_url": re.compile(r"https?://api\.bybit\.com"),
    "testnet_rest_url": re.compile(r"https?://api-testnet\.bybit\.com"),
    "wss_stream_url": re.compile(r"wss?://stream(?:-testnet)?\.bybit"),
}

# Directories outside the scope of the gate (D-05 + RESEARCH allowlist).
EXEMPT_DIRS: set[Path] = {
    REPO_ROOT / "services" / "bybit-connector",
    REPO_ROOT / "scripts" / "tape",
    REPO_ROOT / "_archive_exchanges",
    REPO_ROOT / "services" / "ml-prediction-service" / "models" / "_archive_lstm",
}

# Per-(file, kind) replacement endpoint overrides. Default fallback is
# `/api/v1/market/kline` (see _replacement_for below).
_REPLACEMENT_OVERRIDES: dict[tuple[str, str], str] = {
    # rotate_secrets: pybit auth ping → account/balance (D-07)
    (
        "infrastructure/scripts/rotate_secrets.py",
        "pybit_import",
    ): "/api/v1/account/balance",
    # health_check probe → bybit-connector /health (RESEARCH Endpoint Mapping)
    ("shared/health_check.py", "mainnet_rest_url"): "/health",
    ("shared/health_check.py", "testnet_rest_url"): "/health",
    ("shared/health_check.py", "wss_stream_url"): "/health",
    # ml-prediction orderbook consumer
    (
        "services/ml-prediction-service/app/handlers/orderbook.py",
        "mainnet_rest_url",
    ): "/api/v1/market/orderbook",
    (
        "services/ml-prediction-service/app/handlers/orderbook.py",
        "testnet_rest_url",
    ): "/api/v1/market/orderbook",
    (
        "services/ml-prediction-service/app/handlers/orderbook.py",
        "wss_stream_url",
    ): "/api/v1/market/orderbook",
}


def _is_under(path: Path, root: Path) -> bool:
    """Return True iff `path` is inside `root` (resolved). Mirrors PATTERNS Shared 4."""
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _replacement_for(rel_path: str, kind: str) -> str:
    """Look up the bybit-connector endpoint the refactor will route this site to."""
    override = _REPLACEMENT_OVERRIDES.get((rel_path, kind))
    if override is not None:
        return override
    # Default: every kline / ticker / generic Bybit consumer routes through kline.
    return "/api/v1/market/kline"


def collect_bypass_entries() -> list[dict[str, Any]]:
    """Walk the repo and emit one entry per banned-pattern match."""
    entries: list[dict[str, Any]] = []
    for py in REPO_ROOT.rglob("*.py"):
        if any(_is_under(py, exempt) for exempt in EXEMPT_DIRS):
            continue
        if "__pycache__" in py.parts:
            continue
        try:
            text = py.read_text(errors="ignore")
        except OSError:
            continue
        rel_path = py.relative_to(REPO_ROOT).as_posix()
        # Skip the audit script itself — the regex literals it contains would
        # otherwise self-match. The script lives at scripts/audit_bybit_bypass.py.
        if rel_path == "scripts/audit_bybit_bypass.py":
            continue
        for kind, pattern in BANNED_PATTERNS.items():
            for m in pattern.finditer(text):
                line_no = text[: m.start()].count("\n") + 1
                lines = text.splitlines()
                snippet = lines[line_no - 1].strip() if line_no - 1 < len(lines) else ""
                entries.append(
                    {
                        "file": rel_path,
                        "line": line_no,
                        "kind": kind,
                        "current_call": snippet,
                        "replacement_path": _replacement_for(rel_path, kind),
                    }
                )
    entries.sort(key=lambda e: (e["file"], e["line"], e["kind"]))
    return entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="BC-01: Audit every Bybit-bypass site in the repo "
        "and emit JSON per the locked schema."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write JSON to this path (default: stdout).",
    )
    args = parser.parse_args(argv)

    entries = collect_bypass_entries()

    if args.out is None:
        json.dump(entries, sys.stdout, indent=2, sort_keys=False)
        sys.stdout.write("\n")
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as fh:
            json.dump(entries, fh, indent=2, sort_keys=False)
            fh.write("\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
