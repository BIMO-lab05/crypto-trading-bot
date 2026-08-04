"""Phase 14 MOBILE-01 + MOBILE-02 -- file-content + anti-pattern gates.

Five gate tests covering MOBILE-01 + MOBILE-02 invariants:
  1. test_no_hidden_md_on_data_carrier: no mobile-hiding class on data-testid
     data-carrier elements (forbid `hidden md:block` family; PERMIT `md:hidden`
     which is the desktop-hide branch of dual-render)
  2. test_tailwind_screens_declared: tailwind.config.js declares theme.screens
     with 4 breakpoint tokens (sm/md/lg/xl)
  3. test_viewport_meta_present: frontend/index.html has viewport meta tag
  4. test_responsive_audit_shape: responsive-audit.json has required schema
  5. test_responsive_audit_count_zero: responsive-audit.json has zero
     unallowlisted hits AND is non-empty (proof script ran -- defense against
     silently-empty bug per RESEARCH Validation Architecture false-positive #5)

Anti-hidden gate scope discipline per RESEARCH Pitfall 2 verification table:
  - MUST require data-testid="(metric|tile|chip|row)-*" adjacency on SAME line
  - PERMITS md:hidden (the desktop-hide branch of dual-render for
    TournamentDashboard.jsx card-vs-table reflow)
  - PERMITS decorative `hidden sm:inline` / `hidden md:flex` on elements WITHOUT
    data-testid (10 verified-safe existing usages in App.jsx, CommandPalette.jsx,
    Dashboard.jsx, KeyMetricsStrip.jsx, StatusBar.jsx)

NO subprocess grep -r half -- per-line data-testid adjacency check can't be
expressed in plain grep without false negatives (per PATTERNS.md Pattern S2
documented constraint).

GREEN expectation (Wave-1 close):
  - test_no_hidden_md_on_data_carrier:  GREEN (Pitfall 2 verified baseline)
  - test_viewport_meta_present:         GREEN (meta already at index.html:17)
  - test_tailwind_screens_declared:     GREEN IFF Plan 14-01 Task 1 merged
  - test_responsive_audit_shape:        GREEN IFF Plan 14-01 Task 2 merged
  - test_responsive_audit_count_zero:   GREEN IFF Plan 14-01 Task 2 merged

14-01 and 14-02 are same-wave parallel; after merge all 5 should be GREEN.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Module-level constants -- SCOPE IS LOAD-BEARING (Pattern S1 + S4).
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
TAILWIND_CONFIG = REPO_ROOT / "frontend" / "tailwind.config.js"
INDEX_HTML = REPO_ROOT / "frontend" / "index.html"
AUDIT_OUTPUT = REPO_ROOT / "responsive-audit.json"
ALLOWLIST_PATH = (
    REPO_ROOT
    / ".planning"
    / "phases"
    / "14-mobile-responsive-dashboard"
    / "mobile-hidden-allowlist.json"
)

# Forbidden: `hidden md:block`, `hidden md:flex`, `hidden lg:grid`, etc.
# Permitted: `md:hidden`, `sm:hidden`, etc. (desktop-hide family --
# load-bearing for TournamentDashboard.jsx dual-render).
MOBILE_HIDE_PATTERN = re.compile(
    r"\bhidden\s+(?:sm|md|lg|xl):"
    r"(?:block|flex|grid|table|inline|inline-block|inline-flex)\b"
)
DATA_TESTID_DATA_CARRIER = re.compile(r'data-testid="(metric|tile|chip|row)-[^"]+"')

# responsive-audit.json schema (Plan 14-01 Task 2 deliverable).
REQUIRED_AUDIT_KEYS = {"file", "line", "rule", "snippet", "allowlisted", "reason"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_allowlist() -> set[str]:
    """Load mobile-hidden allowlist; returns set of allowlisted data-testid strings.

    Entries without a non-empty `reason` field are silently dropped (mirrors
    audit_bybit_bypass.py allowlist discipline; prevents drive-by allowlisting
    without explanation).

    Phase 14 WR-04 fix — previously this function crashed mid-collection on
    malformed JSON (JSONDecodeError) or entries missing `data_testid`
    (KeyError), inconsistent with scripts/audit_responsive.py:88-89's
    graceful-degrade pattern. Now mirrors that shape: empty allowlist on
    OSError / JSONDecodeError / non-list root, and a per-entry guard that
    requires `isinstance(e, dict)` + both `data_testid` and `reason` present.
    """
    if not ALLOWLIST_PATH.exists():
        return set()
    try:
        entries = json.loads(ALLOWLIST_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(entries, list):
        return set()
    return {
        e["data_testid"]
        for e in entries
        if isinstance(e, dict) and e.get("data_testid") and e.get("reason")
    }


# ---------------------------------------------------------------------------
# Gate 1: No mobile-hidden class on data-testid data-carrier elements
# ---------------------------------------------------------------------------


def test_no_hidden_md_on_data_carrier():
    """No mobile-hiding class on (metric|tile|chip|row)-* data-carrier elements.

    Walks frontend/src/**/*.jsx; per-line: both MOBILE_HIDE_PATTERN AND
    DATA_TESTID_DATA_CARRIER must match on the SAME line for a violation.
    Decorative usage (mobile-hide class without data-testid match) is PERMITTED.

    Per RESEARCH Pitfall 2 verification table (2026-05-22), zero preexisting
    violations exist -- this gate ships GREEN on first run. If it fails
    unexpectedly, investigate the failing file/line against the RESEARCH
    verification table (10 verified-safe entries) BEFORE allowlisting.
    """
    allowlist = _load_allowlist()
    violations = []
    for jsx_file in FRONTEND_SRC.rglob("*.jsx"):
        try:
            text = jsx_file.read_text(errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not MOBILE_HIDE_PATTERN.search(line):
                continue
            testid_match = DATA_TESTID_DATA_CARRIER.search(line)
            if not testid_match:
                # Decorative element without data-carrier testid -- PERMITTED
                continue
            testid = testid_match.group(0).split('"')[1]
            if testid in allowlist:
                continue
            violations.append(
                {
                    "file": str(jsx_file.relative_to(REPO_ROOT)),
                    "line": lineno,
                    "testid": testid,
                    "snippet": line.strip()[:120],
                }
            )
    assert violations == [], (
        f"{len(violations)} mobile-hidden-on-data violations:\n"
        + "\n".join(
            f"  {v['file']}:{v['line']} -- {v['testid']}: {v['snippet']}"
            for v in violations
        )
    )


# ---------------------------------------------------------------------------
# Gate 2: tailwind.config.js declares theme.screens with 4 breakpoint tokens
# ---------------------------------------------------------------------------


def test_tailwind_screens_declared():
    """tailwind.config.js declares theme.screens with all 4 breakpoint literals.

    Required block (Option A from UI-SPEC, or Option B if any `2xl:` usage
    appears in source):
        screens: {
          sm: '640px',
          md: '768px',
          lg: '1024px',
          xl: '1280px',
        }

    Depends on Plan 14-01 Task 1 landing. Same-wave parallel with 14-02; RED
    until 14-01 merges.
    """
    assert TAILWIND_CONFIG.exists(), (
        f"tailwind.config.js not found at {TAILWIND_CONFIG}"
    )
    text = TAILWIND_CONFIG.read_text()
    assert re.search(r"^\s+screens:\s*{", text, re.MULTILINE), (
        "tailwind.config.js missing theme.screens block (or theme.extend.screens "
        "if Option B). Expected `    screens: {` declaration."
    )
    for token in ("'640px'", "'768px'", "'1024px'", "'1280px'"):
        assert token in text, (
            f"tailwind.config.js missing breakpoint literal {token}. "
            "Required tokens: '640px', '768px', '1024px', '1280px'."
        )


# ---------------------------------------------------------------------------
# Gate 3: frontend/index.html has viewport meta tag
# ---------------------------------------------------------------------------


def test_viewport_meta_present():
    """frontend/index.html declares viewport meta with width=device-width.

    Meta already present at index.html:17 (verified 2026-05-22); ships GREEN
    on first run.
    """
    assert INDEX_HTML.exists(), f"frontend/index.html not found at {INDEX_HTML}"
    text = INDEX_HTML.read_text()
    pattern = re.compile(
        r'<meta\s+name=["\']viewport["\']\s+content=["\'][^"\']*width=device-width',
        re.IGNORECASE,
    )
    assert pattern.search(text), (
        "frontend/index.html missing viewport meta with width=device-width. "
        'Required: <meta name="viewport" content="width=device-width, '
        'initial-scale=1.0" />'
    )


# ---------------------------------------------------------------------------
# Gate 4: responsive-audit.json has required schema
# ---------------------------------------------------------------------------


def test_responsive_audit_shape():
    """responsive-audit.json at repo root is a list of entries with required keys.

    Each entry must have keys: {file, line, rule, snippet, allowlisted, reason}.
    Depends on Plan 14-01 Task 2 (scripts/audit_responsive.py + generated
    artifact). RED until 14-01 merges.
    """
    assert AUDIT_OUTPUT.exists(), (
        f"responsive-audit.json missing at repo root ({AUDIT_OUTPUT}). "
        "Plan 14-01 Task 2 (scripts/audit_responsive.py) must produce this "
        "artifact via `python3 scripts/audit_responsive.py --out "
        "responsive-audit.json`."
    )
    data = json.loads(AUDIT_OUTPUT.read_text())
    assert isinstance(data, list), (
        f"responsive-audit.json must be a JSON list, got {type(data).__name__}"
    )
    bad = [i for i, e in enumerate(data) if not REQUIRED_AUDIT_KEYS <= set(e.keys())]
    assert not bad, (
        f"responsive-audit.json entries at indices {bad[:5]} missing required "
        f"keys; required={sorted(REQUIRED_AUDIT_KEYS)}"
    )


# ---------------------------------------------------------------------------
# Gate 5: responsive-audit.json has zero unallowlisted hits and is non-empty
# ---------------------------------------------------------------------------


def test_responsive_audit_count_zero():
    """responsive-audit.json: zero unallowlisted hits AND non-empty.

    The non-empty check is defense-in-depth against RESEARCH Validation
    Architecture false-positive #5: a script that silently walks zero files
    would emit `[]` and trivially satisfy the count-zero gate. The
    `len(data) > 0` assertion forces the audit script to actually walk
    frontend/src/**/*.jsx and emit at least the (allowlisted) out-of-scope
    hits documented in RESEARCH Pitfall 1.

    Depends on Plan 14-01 Task 2; RED until 14-01 merges.
    """
    assert AUDIT_OUTPUT.exists(), (
        f"responsive-audit.json missing at repo root ({AUDIT_OUTPUT})"
    )
    data = json.loads(AUDIT_OUTPUT.read_text())
    unallow = [e for e in data if not e.get("allowlisted")]
    assert not unallow, (
        f"{len(unallow)} unallowlisted audit hits in responsive-audit.json:\n"
        + "\n".join(
            f"  {e['file']}:{e['line']} -- {e['snippet'][:100]}" for e in unallow[:5]
        )
    )
    # Proof-of-work: audit script must have walked SOMETHING.
    assert len(data) > 0, (
        "responsive-audit.json is empty -- did scripts/audit_responsive.py "
        "silently fail to walk frontend/src/**/*.jsx? Per RESEARCH Pitfall 1, "
        "the audit should find ~20+ out-of-phase-14-scope hits in "
        "frontend/src/components/performance/ and PerformanceDashboard/ "
        "directories that are pre-allowlisted with `out-of-phase-14-scope` "
        "reason. Empty output = script bug."
    )
