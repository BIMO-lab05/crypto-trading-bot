"""CD-10: no `gh pr merge` invocations anywhere in the harness or its workflows.

Auto-merge against trading code is unsafe even with significance gates (TOURN-06).
Humans always merge. Sibling to D-13 (test_no_legacy_r2_criterion.py).

Mirrors services/tournament-harness/tests/integration/test_tourn07_grep_gate.py.
"""

from __future__ import annotations
import re
import subprocess
from pathlib import Path


HARNESS_ROOT = Path(__file__).resolve().parents[2]  # services/tournament-harness/
REPO_ROOT = HARNESS_ROOT.parents[1]  # /<repo>/

PATTERN = r"gh\s+pr\s+merge"
SCAN_DIRS_ABS = [HARNESS_ROOT, REPO_ROOT / ".github" / "workflows"]

SELF_FILE_BASENAME = Path(__file__).name


def test_no_auto_merge_invocation():
    cmd = ["grep", "-rEn", PATTERN, *[str(d) for d in SCAN_DIRS_ABS if d.exists()]]
    result = subprocess.run(cmd, capture_output=True, text=True)
    hits = [
        ln
        for ln in result.stdout.splitlines()
        if "/tests/" not in ln  # skip all test files (Phase 3 convention)
        and SELF_FILE_BASENAME not in ln  # belt-and-suspenders self-allowlist
        and not _is_comment_line(ln)
    ]
    assert hits == [], (
        "CD-10 violation: `gh pr merge` invocation found:\n  " + "\n  ".join(hits)
    )


def test_no_auto_merge_in_python_files():
    compiled = re.compile(PATTERN)
    matches = []
    for py in (HARNESS_ROOT / "app").rglob("*.py"):
        text = py.read_text(errors="ignore")
        for ln_no, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            if compiled.search(line):
                matches.append((py, ln_no, line.strip()))
    assert matches == [], "CD-10 violation in app/:\n" + "\n".join(
        f"  {p}:{ln}: {snippet}" for p, ln, snippet in matches
    )


def test_pattern_is_pinned():
    assert PATTERN == r"gh\s+pr\s+merge", (
        "CD-10 pattern must remain exact (regression guard)"
    )


def test_self_allowlist_required():
    own = Path(__file__)
    assert "/tests/" in own.as_posix()
    # Sanity: this file mentions the literal pattern; if it didn't, the filter wouldn't be
    # doing real work and someone removed the pattern by accident.
    assert "gh pr merge" in own.read_text() or PATTERN in own.read_text()


_GREP_LINE_RE = re.compile(r"^[^:]+:\d+:(.*)$")


def _is_comment_line(grep_line: str) -> bool:
    """W3 fix — same regex extraction as test_no_legacy_r2_criterion.py."""
    m = _GREP_LINE_RE.match(grep_line)
    if not m:
        return False
    return m.group(1).lstrip().startswith("#")
