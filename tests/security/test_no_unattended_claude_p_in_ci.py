"""Security invariant: no `claude -p` invocation in CI workflows or monitoring scripts.

T-05-03-07 (Tampering): future contributor re-introduces `claude -p` in CI/cron without
going through ADR review. This test gate prevents silent regression.

ALLOWLISTED PATHS (documentation only — these paths may reference `claude -p` as prose):
  - .planning/     DECISION.md and plan files document the pattern as historical context
  - docs/          ADR-011 references the pattern to describe what was deleted
  - wiki/          Concept pages and module docs may reference it educationally
  - .claude/       GSD tooling workflow templates (review.md etc.) — not executable CI code
  - .git/          Internal git objects
  - node_modules/  Third-party code, not part of this project
  - _archive_lstm/ Archived code, not in active execution path
  - __pycache__/   Compiled bytecode, not source

This gate enforces the rule on EXECUTABLE paths only:
  - .github/workflows/**/*.yml
  - scripts/monitoring/**/*
  - All other repo paths not in the allowlist above

Mirrors: services/tournament-harness/tests/integration/test_no_auto_merge.py (CD-10 pattern)
See also: docs/decisions/ADR-011-monitoring-disposition.md, .planning/phases/05-ml-cleanup-post-v0/05-03-DECISION.md
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo layout
# ---------------------------------------------------------------------------

REPO_ROOT = (
    Path(__file__).resolve().parents[2]
)  # tests/security/ -> tests/ -> repo root

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Shell form: `claude -p`, `claude  -p`, etc.
PATTERN_SHELL = r"claude\s+-p\b"

# Python list-arg form: ["claude", "-p", ...] or ("claude", "-p")
PATTERN_PYTHON_LIST = r'"claude"\s*,\s*"-p"'

# subprocess invocation: subprocess.run(["claude", "-p", ...]) etc.
PATTERN_SUBPROCESS = r"subprocess\.[a-z_]+\(\s*\[[^]]*\bclaude\b[^]]*-p\b"

# Combined pattern for single grep passes (shell + python-list forms)
PATTERN_GREP = r"claude\s+-p|" + PATTERN_PYTHON_LIST

# Self-identification for allowlisting grep output
_SELF_PATH_SUFFIX = "tests/security/test_no_unattended_claude_p_in_ci.py"
_SELF_FILE_BASENAME = Path(__file__).name

# ---------------------------------------------------------------------------
# Scan directories (post-disposition)
# ---------------------------------------------------------------------------

CI_WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
MONITORING_DIR = REPO_ROOT / "scripts" / "monitoring"

# Paths excluded from the broad scope scan (documentation/tooling — see module docstring)
_ALLOWLIST_DIRS = {
    ".planning",
    "docs",
    "wiki",
    ".claude",  # GSD tooling workflow templates — not executable CI code
    ".git",
    "node_modules",
    "_archive_lstm",
    "__pycache__",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GREP_LINE_RE = re.compile(r"^[^:]+:\d+:(.*)$")


def _is_comment_line(grep_line: str) -> bool:
    """True if the code portion of a grep hit is a shell or Python comment line."""
    m = _GREP_LINE_RE.match(grep_line)
    if not m:
        return False
    return m.group(1).lstrip().startswith("#")


def _filter_hits(raw_lines: list[str]) -> list[str]:
    """Remove self-references and comment lines from grep output."""
    return [
        ln
        for ln in raw_lines
        if _SELF_PATH_SUFFIX not in ln
        and _SELF_FILE_BASENAME not in ln
        and "/tests/" not in ln  # consistent with CD-10: skip all test files
        and not _is_comment_line(ln)
    ]


def _grep(pattern: str, *paths: Path) -> list[str]:
    """Run grep -rEn over the given paths and return filtered hit lines."""
    existing = [str(p) for p in paths if p.exists()]
    if not existing:
        return []
    result = subprocess.run(
        ["grep", "-rEn", pattern, *existing],
        capture_output=True,
        text=True,
    )
    return _filter_hits(result.stdout.splitlines())


def _grep_with_exclusions(
    pattern: str, root: Path, exclude_dirs: set[str]
) -> list[str]:
    """Run a single grep -rEn from root with --exclude-dir flags for each allowlisted dir.

    Faster than iterating top-level dirs individually (single process, kernel does the work).
    """
    cmd = ["grep", "-rEn", pattern, str(root)]
    for d in sorted(exclude_dirs):
        cmd += ["--exclude-dir", d]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return _filter_hits(result.stdout.splitlines())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_claude_p_in_ci_workflows():
    """T-05-03-07 (CI scope): no `claude -p` invocation in .github/workflows/**/*.yml."""
    hits = _grep(PATTERN_GREP, CI_WORKFLOWS_DIR)
    assert hits == [], (
        "Security gate T-05-03-07: `claude -p` found in CI workflows:\n  "
        + "\n  ".join(hits)
    )


def test_no_claude_p_in_monitoring():
    """T-05-03-07 (cron scope): no `claude -p` in scripts/monitoring/ after tier-2 deletion.

    If scripts/monitoring/ was deleted entirely (delete_all disposition), this test
    passes trivially — the directory is absent and the grep iterates over zero files.
    """
    hits = _grep(PATTERN_GREP, MONITORING_DIR)
    assert hits == [], (
        "Security gate T-05-03-07: `claude -p` found in scripts/monitoring/:\n  "
        + "\n  ".join(hits)
    )


def test_no_claude_p_broad_scope():
    """T-05-03-07 (broad scope): no `claude -p` in executable paths across the repo.

    Allowlisted paths (documentation/tooling only — see module docstring):
      .planning/, docs/, wiki/, .claude/, .git/, node_modules/, _archive_lstm/, __pycache__/

    Uses a single grep call with --exclude-dir flags (faster than per-dir iteration).
    This test enforces the rule on source code, scripts, and CI configs, not on
    documentation files or GSD tooling templates that reference the pattern as prose.
    """
    hits = _grep_with_exclusions(PATTERN_GREP, REPO_ROOT, _ALLOWLIST_DIRS)
    assert hits == [], (
        "Security gate T-05-03-07: `claude -p` found outside allowlisted doc paths:\n  "
        + "\n  ".join(hits)
    )


def test_pattern_pins_and_self_allowlist():
    """Regression guard: patterns are pinned and this file contains the guarded string.

    Verifies:
    1. The shell pattern matches the exact invariant.
    2. The Python list-arg pattern matches the exact invariant.
    3. This test file contains the literal pattern (so the filter is doing real work).
    4. This file's path ends with the self-exclusion suffix used in _filter_hits.
    """
    assert PATTERN_SHELL == r"claude\s+-p\b", (
        "Shell pattern must remain exact — change only via ADR review"
    )
    assert PATTERN_PYTHON_LIST == r'"claude"\s*,\s*"-p"', (
        "Python list-arg pattern must remain exact — change only via ADR review"
    )
    own = Path(__file__)
    assert _SELF_PATH_SUFFIX in own.as_posix(), (
        f"Self-exclusion suffix mismatch: {_SELF_PATH_SUFFIX!r} not in {own.as_posix()!r}"
    )
    # Sanity: this file must reference the literal strings being searched for; otherwise
    # _filter_hits would be filtering nothing meaningful and a removal would go undetected.
    text = own.read_text()
    assert "claude" in text and "-p" in text, (
        "Test file must reference the guarded pattern strings — do not remove them"
    )
