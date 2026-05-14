"""B1: every klines read in services/tournament-harness/ carries an is_mainnet filter.

Phase 3 D-08 + CLAUDE.md gotcha: TimescaleDB `klines` carry mixed testnet/mainnet
history before 2026-04-25. Any unfiltered SELECT pollutes results. The canonical
reader `app.runner.data.load_klines_from_timescale` already enforces this in its
SQL; this test catches future copy-paste / new-loader regressions.

Mirrors services/tournament-harness/tests/integration/test_tourn07_grep_gate.py.
"""

from __future__ import annotations
import re
import subprocess
from pathlib import Path


HARNESS_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = HARNESS_ROOT.parents[1]
SELF_FILE_BASENAME = Path(__file__).name

# Patterns that look like a klines READ. Each regex is intentionally narrow.
KLINES_PATTERNS = [
    re.compile(r"\bFROM\s+klines\b", re.IGNORECASE),
    re.compile(r"\bSELECT[^;]*\bklines\b", re.IGNORECASE | re.DOTALL),
]
MAINNET_FILTER_PATTERN = re.compile(r"is_mainnet", re.IGNORECASE)
NEIGHBORHOOD_LINES = 5


def _scan_file(path: Path):
    """Yield (path, lineno, snippet) for any klines read missing is_mainnet within ±5 lines."""
    text = path.read_text(errors="ignore")
    lines = text.splitlines()
    violations = []
    for i, line in enumerate(lines, start=1):
        if line.lstrip().startswith("#"):
            continue
        for pat in KLINES_PATTERNS:
            if pat.search(line):
                lo = max(0, i - 1 - NEIGHBORHOOD_LINES)
                hi = min(len(lines), i + NEIGHBORHOOD_LINES)
                nbhd = "\n".join(lines[lo:hi])
                if not MAINNET_FILTER_PATTERN.search(nbhd):
                    violations.append((path, i, line.strip()))
                break
    return violations


def test_klines_reads_have_is_mainnet():
    app_root = HARNESS_ROOT / "app"
    all_violations = []
    for py in app_root.rglob("*.py"):
        if "/tests/" in py.as_posix() or py.name == SELF_FILE_BASENAME:
            continue
        all_violations.extend(_scan_file(py))
    assert all_violations == [], (
        "B1 violation: klines read without is_mainnet within ±5 lines:\n"
        + "\n".join(f"  {p}:{ln}: {snip}" for p, ln, snip in all_violations)
    )


def test_canonical_loader_carries_filter():
    loader = HARNESS_ROOT / "app" / "runner" / "data.py"
    assert loader.exists(), f"canonical klines reader missing: {loader}"
    text = loader.read_text()
    assert re.search(r"is_mainnet\s*=\s*TRUE", text, re.IGNORECASE), (
        "B1 regression: canonical loader app/runner/data.py SQL no longer enforces is_mainnet=TRUE"
    )


def test_subprocess_grep_klines_unfiltered_empty():
    cmd = ["grep", "-rEn", r"\bFROM\s+klines\b", str(HARNESS_ROOT / "app")]
    result = subprocess.run(cmd, capture_output=True, text=True)
    offending = []
    for ln in result.stdout.splitlines():
        if "/tests/" in ln or SELF_FILE_BASENAME in ln:
            continue
        # Extract path; re-scan its neighborhood for is_mainnet via the file scanner.
        try:
            path_str = ln.split(":", 1)[0]
        except IndexError:
            continue
        fp = Path(path_str)
        if not fp.exists():
            continue
        if _scan_file(fp):
            offending.append(ln)
    assert offending == [], "B1 violation (subprocess grep):\n  " + "\n  ".join(
        offending
    )


def test_self_allowlist_works():
    own = Path(__file__)
    assert "/tests/" in own.as_posix()
    # Sanity: this file mentions klines AND is_mainnet — proves the filter does real work.
    text = own.read_text()
    assert "klines" in text and "is_mainnet" in text


def test_pattern_constants_are_complete():
    assert len(KLINES_PATTERNS) == 2, "B1 KLINES_PATTERNS regression guard"
    assert MAINNET_FILTER_PATTERN is not None
    assert NEIGHBORHOOD_LINES == 5, "B1 NEIGHBORHOOD_LINES regression guard"
