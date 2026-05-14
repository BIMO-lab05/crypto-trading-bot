"""D-13: CI grep gate enforcing the no-'>5% R²'-win-criterion rule.

Phase 4 explicitly drops the legacy 5%-R² win bar in favor of bootstrap p<0.05 vs persistence
(TOURN-05). This test catches any future PR that re-introduces the old criterion in code,
comments, strings, or workflow YAML.

Mirrors services/tournament-harness/tests/integration/test_tourn07_grep_gate.py.
"""

from __future__ import annotations
import re
import subprocess
from pathlib import Path

import pytest

# services/tournament-harness/
HARNESS_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = HARNESS_ROOT.parents[1]  # /<repo>/

PATTERNS = [
    r">\s*5\s*%",
    r"5\s*percent\s*R[²2]",
    r"r2[_\s]*returns?\s*>\s*0\.0?5",
    r"R[²2]\s*>\s*0?\.0?5",
]
LITERAL_STRINGS = ["5% R2", "5% R²", "five percent R"]
SCAN_DIRS_ABS = [
    HARNESS_ROOT / "app",
    REPO_ROOT / ".github" / "workflows",  # filter to tournament*.yml in scan
]

SELF_FILE_BASENAME = Path(__file__).name


def _scan_python(root: Path):
    """Yield (path, lineno, line_text, pattern) for every Python-side match in root."""
    if not root.exists():
        return
    compiled_re = [(re.compile(p), p) for p in PATTERNS]
    for py in root.rglob("*.py"):
        if "/tests/" in py.as_posix() or py.name == SELF_FILE_BASENAME:
            continue
        text = py.read_text(errors="ignore")
        for ln_no, line in enumerate(text.splitlines(), start=1):
            # Skip comment-only lines that contain the patterns *as documentation* — our gate
            # tolerates `# DO NOT add `>5% R²` here (D-13 forbids)` style notes.
            bare = line.lstrip()
            if bare.startswith("#"):
                continue
            for cre, pat in compiled_re:
                if cre.search(line):
                    yield (py, ln_no, line.strip(), pat)
            for lit in LITERAL_STRINGS:
                if lit in line:
                    yield (py, ln_no, line.strip(), f"literal:{lit}")


def test_no_legacy_r2_in_app():
    matches = list(_scan_python(HARNESS_ROOT / "app"))
    assert matches == [], (
        "D-13 violation: legacy '>5% R²' criterion found in services/tournament-harness/app/:\n"
        + "\n".join(
            f"  {p}:{ln}: {snippet}  (pattern={pat})" for p, ln, snippet, pat in matches
        )
    )


def test_no_legacy_r2_in_workflows():
    wf_dir = REPO_ROOT / ".github" / "workflows"
    if not wf_dir.exists():
        pytest.skip(".github/workflows not present in this checkout")
    matches = []
    compiled = [(re.compile(p), p) for p in PATTERNS]
    for yml in list(wf_dir.glob("tournament*.yml")) + list(
        wf_dir.glob("tournament*.yaml")
    ):
        for ln_no, line in enumerate(
            yml.read_text(errors="ignore").splitlines(), start=1
        ):
            for cre, pat in compiled:
                if cre.search(line):
                    matches.append((yml, ln_no, line.strip(), pat))
            for lit in LITERAL_STRINGS:
                if lit in line:
                    matches.append((yml, ln_no, line.strip(), f"literal:{lit}"))
    assert matches == [], "D-13 violation in workflow YAML:\n" + "\n".join(
        f"  {p}:{ln}: {snippet}  (pattern={pat})" for p, ln, snippet, pat in matches
    )


def test_grep_subprocess_returns_empty():
    """Shell-out grep — catches any code path the Python regex might miss."""
    cmd = [
        "grep",
        "-rEn",
        "|".join(PATTERNS),
        str(HARNESS_ROOT / "app"),
        str(HARNESS_ROOT / "tests"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    # W3 fix: drop the dead `output` variable that was never asserted; collect strict
    # app-side hits in a single pass with the comment-line filter applied via regex
    # (split(':', 2) misparses content lines containing additional colons — f-strings,
    # dict literals — so use a path:line:content regex instead).
    app_hits = [
        ln
        for ln in result.stdout.splitlines()
        if "/tests/" not in ln
        and SELF_FILE_BASENAME not in ln
        and not ln.split(":", 1)[0].endswith(".pyc")
        and not _is_comment_line(ln)
    ]
    assert app_hits == [], "D-13 grep gate violation:\n  " + "\n  ".join(app_hits)


_GREP_LINE_RE = re.compile(r"^[^:]+:\d+:(.*)$")


def _is_comment_line(grep_line: str) -> bool:
    """W3 fix: regex extraction of the content portion. The prior `split(':', 2)` form
    misparsed any content line containing additional colons (f-strings, dict literals,
    nested type hints). The regex anchors on `path:lineno:` and treats the remainder
    — colons and all — as content."""
    m = _GREP_LINE_RE.match(grep_line)
    if not m:
        return False
    return m.group(1).lstrip().startswith("#")


def test_pattern_constants_are_complete():
    """Defends against accidental deletion of patterns in future code review."""
    assert len(PATTERNS) == 4, "D-13 patterns must remain at 4 (regression guard)"
    assert len(LITERAL_STRINGS) == 3, (
        "D-13 literal strings must remain at 3 (regression guard)"
    )


def test_self_allowlist_works():
    """The patterns appear in this file; verify the /tests/ filter excludes us."""
    # This file's path contains "/tests/integration/" — assert at least one pattern matches
    # somewhere in the source so we know the filter is doing real work.
    own_text = Path(__file__).read_text()
    compiled = [re.compile(p) for p in PATTERNS]
    own_hits = sum(
        1 for line in own_text.splitlines() for c in compiled if c.search(line)
    )
    assert own_hits > 0, (
        "expected this test file to contain at least one D-13 pattern (sanity)"
    )
    # And we MUST be in /tests/ so the gate skips us.
    assert "/tests/" in Path(__file__).as_posix()
