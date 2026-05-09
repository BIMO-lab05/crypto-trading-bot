"""B2 strengthened: no underscore-prefixed metric reimplementations in pr/ or significance/.

Phase 3 already had a TOURN-07 grep gate over the whole harness (test_tourn07_grep_gate.py);
that pattern was `def\s+(sharpe|...)\w*\(` — without the optional underscore. The B2
blocker showed `_sharpe` and `_dir_acc_corrected_log_returns` slipped through. This sibling
gate strengthens the pattern with `_?` and scopes scanning to the two Phase 4 directories
where reimplementations would do the most damage.
"""

from __future__ import annotations
import re
import subprocess
from pathlib import Path


HARNESS_ROOT = Path(__file__).resolve().parents[2]
SELF_FILE_BASENAME = Path(__file__).name

# Both patterns scanned together — `def`-form catches named reimplementations,
# `lambda`-form catches disguised `lambda r: r.mean() / r.std(...)` Sharpe shapes
# (the kind that slipped past the def-only gate in checker iteration 1).
DEF_PATTERN = r"def\s+_?(sharpe|dir_acc|directional_accuracy|deflated|probabilistic_sharpe|compute_returns)\w*\s*\("
LAMBDA_PATTERN = r"lambda\s+\w+\s*:\s*[^,]*\.mean\(\)\s*/\s*\w+\.std"
PATTERNS = [DEF_PATTERN, LAMBDA_PATTERN]

SCAN_DIRS = [
    HARNESS_ROOT / "app" / "pr",
    HARNESS_ROOT / "app" / "significance",
]


def test_no_underscore_metric_reimplementations():
    compiled = [re.compile(p) for p in PATTERNS]
    violations = []
    for d in SCAN_DIRS:
        if not d.exists():
            continue
        for py in d.rglob("*.py"):
            if "/tests/" in py.as_posix() or py.name == SELF_FILE_BASENAME:
                continue
            for ln_no, line in enumerate(
                py.read_text(errors="ignore").splitlines(), start=1
            ):
                if line.lstrip().startswith("#"):
                    continue
                for cre in compiled:
                    if cre.search(line):
                        violations.append((py, ln_no, line.strip()))
                        break
    assert violations == [], (
        "B2 violation: parallel metric reimplementation found in pr/ or significance/:\n"
        + "\n".join(f"  {p}:{ln}: {snip}" for p, ln, snip in violations)
    )


def test_pattern_pinned():
    assert DEF_PATTERN == (
        r"def\s+_?(sharpe|dir_acc|directional_accuracy|deflated|probabilistic_sharpe|compute_returns)\w*\s*\("
    ), "B2 strengthened def-pattern pin: must include `_?` and the full alternation set"
    assert LAMBDA_PATTERN == (r"lambda\s+\w+\s*:\s*[^,]*\.mean\(\)\s*/\s*\w+\.std"), (
        "B2 strengthened lambda-pattern pin: catches `lambda r: r.mean() / r.std(...)` Sharpe shapes"
    )
    assert len(PATTERNS) == 2, (
        "B2 PATTERNS list must contain both def and lambda regexes"
    )


def test_self_allowlist_works():
    own = Path(__file__)
    assert "/tests/" in own.as_posix()
    text = own.read_text()
    # Sanity: file references the forbidden patterns so we know the filter does real work.
    assert "_sharpe" in text or "compute_returns" in text
    assert (
        "lambda" in text and ".mean()" in text
    )  # lambda-Sharpe pattern is also exercised


def test_subprocess_grep_returns_empty():
    # Combined alternation pattern — grep -E with `|` joins both regexes.
    # Guard: if neither pr/ nor significance/ exists yet (pre-Phase-4-app-code state),
    # skip cleanly rather than letting `grep -rEn PATTERN` (no path arg) fall back to
    # scanning the current working directory and matching unrelated docs.
    import pytest

    existing = [d for d in SCAN_DIRS if d.exists()]
    if not existing:
        pytest.skip(
            "Neither app/pr nor app/significance exists yet; gate scans nothing."
        )
    combined = "|".join(PATTERNS)
    cmd = ["grep", "-rEn", combined, *[str(d) for d in existing]]
    result = subprocess.run(cmd, capture_output=True, text=True)
    hits = [
        ln
        for ln in result.stdout.splitlines()
        if "/tests/" not in ln
        and SELF_FILE_BASENAME not in ln
        and not _is_comment_line(ln)
    ]
    assert hits == [], "B2 violation (subprocess grep):\n  " + "\n  ".join(hits)


_GREP_LINE_RE = re.compile(r"^[^:]+:\d+:(.*)$")


def _is_comment_line(grep_line: str) -> bool:
    m = _GREP_LINE_RE.match(grep_line)
    if not m:
        return False
    return m.group(1).lstrip().startswith("#")
