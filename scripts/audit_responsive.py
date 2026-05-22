#!/usr/bin/env python3
"""MOBILE-01: Repo-wide audit of hardcoded-width sites in frontend/src/**/*.jsx.

Mirrors `scripts/audit_bybit_bypass.py` shape per
.planning/phases/14-mobile-responsive-dashboard/14-PATTERNS.md
(Pattern S1 + Pattern S3 — REPO_ROOT/PATTERNS/main/--out idiom +
mandatory-reason allowlist).

Detects:
    - Tailwind arbitrary widths:  w-[NNNpx], min-w-[NNNpx], max-w-[NNNpx]
    - Inline CSS widths:          width: NNNpx

Schema (each entry):
    {
        "file": str,         # repo-relative POSIX path
        "line": int,         # 1-based
        "rule": str,         # which PATTERNS key fired
        "snippet": str,      # source line stripped (clipped at 200 chars)
        "allowlisted": bool, # True iff "{file}:{line}" appears in allowlist
        "reason": str        # reason from allowlist; "" if not allowlisted
    }

Allowlist file:
    .planning/phases/14-mobile-responsive-dashboard/responsive-audit-allowlist.json
    Shape: [{"file": ..., "line": ..., "reason": "..."}, ...].
    Entries without a non-empty `reason` are silently dropped (Pattern S3).

Output:
    Default: REPO_ROOT / "responsive-audit.json" (per CONTEXT.md "Specifics"
    and ROADMAP SC#1). `--out` overrides.

Exit code (gate-friendly):
    0 if zero unallowlisted hits, 1 otherwise.

Usage:
    python3 scripts/audit_responsive.py                                  # writes responsive-audit.json
    python3 scripts/audit_responsive.py --out /tmp/audit.json            # custom output
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
ALLOWLIST = (
    REPO_ROOT
    / ".planning"
    / "phases"
    / "14-mobile-responsive-dashboard"
    / "responsive-audit-allowlist.json"
)
DEFAULT_OUT = REPO_ROOT / "responsive-audit.json"

# Hardcoded-width patterns per RESEARCH Example 3 (lines 543-548).
# Order is deterministic; iteration uses the dict's insertion order so
# multiple rules on the same line append in a stable sequence.
PATTERNS: dict[str, re.Pattern[str]] = {
    "no-hardcoded-width-tailwind": re.compile(r"\bw-\[(\d+)px\]"),
    "no-hardcoded-min-width-tailwind": re.compile(r"\bmin-w-\[(\d+)px\]"),
    "no-hardcoded-max-width-tailwind": re.compile(r"\bmax-w-\[(\d+)px\]"),
    "no-hardcoded-width-style": re.compile(r"\bwidth:\s*(\d+)px\b"),
}

# Self-exclusion guard: the audit script lives at scripts/audit_responsive.py;
# walking `frontend/src/**/*.jsx` can't hit it (different tree, different
# extension), but the acceptance gate greps for an explicit guard literal so
# we mirror `audit_bybit_bypass.py:121` verbatim.
_SELF_PATH = "scripts/audit_responsive.py"


def _load_allowlist() -> dict[str, str]:
    """Return {f"{file}:{line}": reason} for every well-formed allowlist entry.

    Pattern S3 — mandatory `reason` discipline. Entries without a non-empty
    `reason` are silently dropped so drive-by allowlisting cannot happen.
    Missing allowlist file is gracefully treated as empty allowlist.
    """
    if not ALLOWLIST.exists():
        return {}
    try:
        raw = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        # Phase 14 WR-02 fix — defense-in-depth: a typo in the allowlist
        # (trailing comma, missing brace) previously dropped every entry
        # silently, which made the audit gate fail with no diagnostic. Emit
        # a stderr WARN so the maintainer sees the parse error AND knows
        # the audit will now re-emit every formerly-allowlisted hit.
        print(
            f"audit_responsive: WARN failed to parse allowlist {ALLOWLIST}: {exc}; "
            "treating as empty (every formerly-allowlisted hit will now report)",
            file=sys.stderr,
        )
        return {}
    # Phase 14 WR-03 fix — guard against non-list root. If the allowlist is
    # accidentally written as a dict (e.g. `{"entries": [...]}`) the
    # subsequent `for entry in raw:` would yield keys (strings) and the
    # isinstance(entry, dict) guard below would catch each one, but the
    # surface error message would be misleading. Better to fail fast with a
    # diagnostic and treat the allowlist as empty.
    if not isinstance(raw, list):
        print(
            f"audit_responsive: WARN allowlist {ALLOWLIST} root is "
            f"{type(raw).__name__}, expected list; treating as empty",
            file=sys.stderr,
        )
        return {}
    out: dict[str, str] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        reason = entry.get("reason")
        file = entry.get("file")
        line = entry.get("line")
        if not reason or file is None or line is None:
            continue
        out[f"{file}:{line}"] = reason
    return out


def collect_hits(allowlist: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Walk frontend/src for *.jsx and emit one record per banned-pattern match.

    Output sorted by (file, line, rule) for deterministic, idempotent runs
    (the verify step asserts a committed artifact equals a fresh re-run).
    """
    if allowlist is None:
        allowlist = _load_allowlist()
    hits: list[dict[str, Any]] = []
    if not FRONTEND_SRC.exists():
        return hits
    for jsx in FRONTEND_SRC.rglob("*.jsx"):
        rel = jsx.relative_to(REPO_ROOT).as_posix()
        # Self-exclusion guard — mirror audit_bybit_bypass.py:121.
        # The walker is *.jsx-only and the script is .py, so this skip is
        # semantically a no-op; it satisfies the acceptance gate and matches
        # the established analog shape so future scope expansion stays safe.
        if (
            rel == _SELF_PATH
        ):  # scripts/audit_responsive.py -> continue (self-exclusion)
            continue
        try:
            text = jsx.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for rule, pattern in PATTERNS.items():
                if pattern.search(line):
                    key = f"{rel}:{lineno}"
                    hits.append(
                        {
                            "file": rel,
                            "line": lineno,
                            "rule": rule,
                            "snippet": line.strip()[:200],
                            "allowlisted": key in allowlist,
                            "reason": allowlist.get(key, ""),
                        }
                    )
    hits.sort(key=lambda h: (h["file"], h["line"], h["rule"]))
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "MOBILE-01: Audit hardcoded-width sites in frontend/src/**/*.jsx "
            "and emit JSON per the locked schema."
        )
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=f"Write JSON to this path (default: {DEFAULT_OUT.relative_to(REPO_ROOT)}).",
    )
    args = parser.parse_args(argv)

    allowlist = _load_allowlist()
    hits = collect_hits(allowlist)

    out_path = args.out if args.out is not None else DEFAULT_OUT
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(hits, indent=2) + "\n", encoding="utf-8")

    total = len(hits)
    unallowlisted = [h for h in hits if not h["allowlisted"]]
    n_un = len(unallowlisted)
    print(
        f"audit_responsive: {total} total hits, {n_un} unallowlisted "
        f"-> {out_path.relative_to(REPO_ROOT) if out_path.is_relative_to(REPO_ROOT) else out_path}"
    )
    if n_un:
        for h in unallowlisted[:10]:
            print(
                f"  unallowlisted: {h['file']}:{h['line']} ({h['rule']}) {h['snippet'][:80]}"
            )
        if n_un > 10:
            print(f"  ... and {n_un - 10} more")
    return 0 if not unallowlisted else 1


if __name__ == "__main__":
    sys.exit(main())
