# Phase 15: Planning-Tooling Hardening — Pattern Map

**Mapped:** 2026-05-22
**Files analyzed:** 9 (3 in-repo grep gates + 3 SDK verbs + 1 fixture + 1 pre-commit hook + 1 workflow extension)
**Analogs found:** 4 / 9 (3 exact + 1 partial; 5 with no analog — see "No Analog Found" section)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `tests/ci/test_no_placeholder_one_liners.py` | test (CI grep gate) | static scan + assert | `tests/ci/test_no_bybit_bypass.py` | **exact** |
| `tests/ci/test_roadmap_analyze_supersession_wired.py` | test (workflow-source grep gate) | single-file string presence | `tests/integration/test_no_mobile_hidden_data.py::test_viewport_meta_present` | **partial** (target file `~/.claude/get-shit-done/workflows/complete-milestone.md` is out of repo) |
| `tests/ci/test_audit_freshness_gate.py` | test (workflow-source grep gate) | single-file string presence | `tests/integration/test_no_mobile_hidden_data.py::test_viewport_meta_present` | **partial** (same out-of-repo workflow target) |
| `tests/fixtures/v11_13h_gap/audit.json` + `verification.md` (or .meta.json) | test fixture (static replay data) | static JSON read | `tests/fixtures/tournament/smoke-fixture.json` | **role-match** (static committed fixture; conftest staging not required) |
| `.planning/phases/15-.../mobile-hidden-allowlist.json` analog → `placeholder-allowlist.json` | data (allowlist JSON, likely empty per CONTEXT.md) | static JSON read | `.planning/phases/14-mobile-responsive-dashboard/mobile-hidden-allowlist.json` | **exact** (shape only — see Shared Patterns §Allowlist JSON) |
| `.github/workflows/planning-tooling-gate.yml` (new) OR extension of existing CI workflow | config (CI workflow) | event-driven CI | `.github/workflows/bybit-bypass-gate.yml` | **exact** |
| SDK verb `plan.validate` (out-of-repo: `~/.claude/get-shit-done/bin/lib/`) | service (SDK verb impl) | request-response (CLI) | — | **none** (see No Analog Found §1) |
| SDK verb `roadmap.analyze --apply` umbrella-supersession (out-of-repo) | service (SDK verb impl) | transform + diff-to-stdout | — | **none** (see No Analog Found §1) |
| `/gsd-complete-milestone` audit-freshness gate + `--accept-stale-audit` (out-of-repo: workflow MD + `milestone.cjs::cmdMilestoneComplete`) | controller (workflow gate) | request-response (CLI) | — | **none** (see No Analog Found §2) |
| `.git/hooks/pre-commit` extension (chain `plan.validate` for modified `*-PLAN.md`) | config (git hook) | event-driven (pre-commit) | — | **none** (only `.git/hooks/pre-commit.sample` exists; no real hook installed) |

---

## Pattern Assignments

### `tests/ci/test_no_placeholder_one_liners.py` (test, static scan + assert)

**Analog:** `tests/ci/test_no_bybit_bypass.py` (Phase 13 BC-03 grep gate)
**Match:** EXACT — same role (CI grep gate), same data flow (rglob a tree + regex + assert empty + dual-form parity).

**Imports + REPO_ROOT pattern** (lines 48-64):
```python
from __future__ import annotations

import re
import subprocess
from pathlib import Path

# REPO_ROOT — tests/ci/test_*.py -> parents[2] == repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
```

**Banned-pattern dict shape** (lines 151-156) — for TOOL-01 swap the 4 Bybit regexes for the 5 placeholder patterns from CONTEXT.md "Specifics" line 84:
```python
BANNED_PATTERNS: dict[str, re.Pattern[str]] = {
    "pybit_import": re.compile(r"^\s*(from\s+pybit\b|import\s+pybit\b)", re.MULTILINE),
    "mainnet_rest_url": re.compile(r"https?://api\.bybit\.com"),
    "testnet_rest_url": re.compile(r"https?://api-testnet\.bybit\.com"),
    "wss_stream_url": re.compile(r"wss?://stream(?:-testnet)?\.bybit"),
}
```

**For TOOL-01 the 5 patterns become** (derived from CONTEXT.md §Specifics + REQUIREMENTS.md TOOL-01):
```python
BANNED_PATTERNS: dict[str, re.Pattern[str]] = {
    "placeholder_rule_n": re.compile(r"^Rule\s+\d", re.MULTILINE),
    "placeholder_task_n": re.compile(r"^Task\s+\d", re.MULTILINE),
    "placeholder_one_liner_empty": re.compile(r"^one-liner:\s*$", re.MULTILINE),
    "placeholder_template_token": re.compile(r"<one-line summary>"),
    "placeholder_empty_string": re.compile(r"^one-liner:\s*\"\"\s*$", re.MULTILINE),
}
```

**Walk + scan helper** (lines 199-222) — for TOOL-01 change `REPO_ROOT.rglob("*.py")` to walk `.planning/phases/**/*-PLAN.md`:
```python
def _scan_py_files() -> list[tuple[str, int, str, str]]:
    """Walk REPO_ROOT for *.py files outside the exempt set."""
    violations: list[tuple[str, int, str, str]] = []
    for py in REPO_ROOT.rglob("*.py"):
        if _is_exempt(py):
            continue
        try:
            text = py.read_text(errors="ignore")
        except OSError:
            continue
        lines = text.splitlines()
        for kind, pattern in BANNED_PATTERNS.items():
            for m in pattern.finditer(text):
                line_no = text[: m.start()].count("\n") + 1
                snippet = (
                    lines[line_no - 1].strip() if 1 <= line_no <= len(lines) else ""
                )
                violations.append(
                    (str(py.relative_to(REPO_ROOT)), line_no, kind, snippet)
                )
    return sorted(violations)
```

**Core assertion** (lines 230-251):
```python
def test_no_bybit_bypass_in_python_code() -> None:
    violations = _scan_py_files()
    assert violations == [], (
        "BC-03 violation — direct-Bybit references found outside "
        "services/bybit-connector/:\n  "
        + "\n  ".join(f"{p}:{ln}: [{k}] {snippet}" for p, ln, k, snippet in violations)
    )
```

**Exempt-paths shape** (lines 89-122):
```python
EXEMPT_PATHS: set[Path] = {
    REPO_ROOT / "services" / "bybit-connector",
    REPO_ROOT / "scripts" / "tape",
    REPO_ROOT / "_archive_exchanges",
    REPO_ROOT / "services" / "ml-prediction-service" / "models" / "_archive_lstm",
}
EXEMPT_FILES: set[Path] = {
    REPO_ROOT / "tests" / "smoke" / "test_smoke.py",
    REPO_ROOT / "tests" / "integration" / "test_bybit_connector_tape_preserved.py",
}
```

For TOOL-01, EXEMPT_PATHS most likely empty (placeholder one-liners are always wrong in `*-PLAN.md`), and EXEMPT_FILES likely empty too — but the slot is established so the planner can drop in late-discovered exceptions via the allowlist JSON if needed.

**Dual-form parity test** (lines 253-323): grep-subprocess vs pytest scan must agree. Mirror this for TOOL-01 with grep over `.planning/phases/**/*-PLAN.md`. Critical defence-in-depth — without it, future GNU-grep `--exclude-dir` subtleties can drift the two scan sets silently.

**Exempt-paths existence test** (lines 326-344): every entry in EXEMPT_PATHS either exists today or is in a documented `known_future` set. Mirror this for TOOL-01 (likely trivial if EXEMPT_PATHS empty, but the test slot stays for hygiene).

---

### `tests/ci/test_roadmap_analyze_supersession_wired.py` (test, single-file string presence)

**Analog:** `tests/integration/test_no_mobile_hidden_data.py::test_viewport_meta_present` (Phase 14 Gate 3)
**Match:** PARTIAL — same role (single-file string-presence assertion), but the target file `~/.claude/get-shit-done/workflows/complete-milestone.md` lives **outside the repo** at the operator's home dir. The planner must decide between:
  - (a) grep the host path with `Path.home() / ".claude" / "get-shit-done" / "workflows" / "complete-milestone.md"` and `pytest.skip` if absent;
  - (b) vendor the workflow file into `.planning/sdk-proposals/` and grep the vendored copy;
  - (c) require operator to install vendored copy as part of phase deliverable.

**Imports + path-constant pattern** (lines 37-58):
```python
from __future__ import annotations

import json
import re
from pathlib import Path

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
```

**Single-file string presence test** (lines 197-213) — mirror exactly for the TOOL-02 wiring assertion (the workflow source must contain a `roadmap.analyze --apply` invocation string before the archive step):
```python
def test_viewport_meta_present():
    """frontend/index.html declares viewport meta with width=device-width."""
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
```

**For TOOL-02 the assertion pattern** (sketch — planner to refine):
```python
WORKFLOW_FILE = Path.home() / ".claude" / "get-shit-done" / "workflows" / "complete-milestone.md"
# OR vendored copy at .planning/sdk-proposals/complete-milestone.md

def test_roadmap_analyze_apply_wired_before_archive():
    """/gsd-complete-milestone MUST invoke roadmap.analyze --apply before archive step."""
    if not WORKFLOW_FILE.exists():
        pytest.skip(f"workflow source not present at {WORKFLOW_FILE}")
    text = WORKFLOW_FILE.read_text()
    # Must appear BEFORE archive_milestone / milestone.complete invocation
    apply_pos = text.find("roadmap.analyze --apply")
    archive_pos = text.find("milestone.complete")
    assert apply_pos > 0 and apply_pos < archive_pos, (
        "roadmap.analyze --apply must run before milestone.complete in workflow"
    )
```

---

### `tests/ci/test_audit_freshness_gate.py` (test, single-file string presence)

**Analog:** Same as above — `tests/integration/test_no_mobile_hidden_data.py::test_viewport_meta_present`
**Match:** PARTIAL — same shape (assert a string is present in a single source file), same out-of-repo workflow target.

**For TOOL-03 the assertion pattern** (sketch):
```python
def test_audit_freshness_check_unconditional():
    """/gsd-complete-milestone MUST compare audited_at vs VERIFICATION.md mtime
    unconditionally — no `if SKIP_AUDIT_FRESHNESS` / `--no-audit-check` escape hatches.
    --accept-stale-audit IS permitted (documented override flag), but the check
    itself must always run."""
    if not WORKFLOW_FILE.exists():
        pytest.skip(f"workflow source not present at {WORKFLOW_FILE}")
    text = WORKFLOW_FILE.read_text()
    assert "audited_at" in text and "VERIFICATION.md" in text, (
        "audit-freshness gate not wired in complete-milestone workflow"
    )
    # No silent-skip env vars
    forbidden = ["SKIP_AUDIT_FRESHNESS", "SKIP_AUDITED_AT_CHECK", "if FORCE_ARCHIVE"]
    for token in forbidden:
        assert token not in text, f"escape hatch {token!r} present in workflow"
```

---

### `tests/fixtures/v11_13h_gap/` (fixture, static replay data)

**Analog:** `tests/fixtures/tournament/smoke-fixture.json` (Phase 7 tournament replay; committed static JSON consumed by a function-scoped fixture in `conftest.py`)
**Match:** ROLE-MATCH — static committed JSON, not a fresh-clone bootstrap. **Do not mirror the `bootstrap_stack` / `tmp_fresh_clone` shape from `tests/integration/conftest.py`** (lines 64-89, 95-157) — that fixture boots the full docker stack and is the wrong scale for a unit-test replay.

**Canonical fixture data** (already in hand — drop these straight into the fixture):
- `audited_at` (from `.planning/milestones/v1.1-MILESTONE-AUDIT.md` frontmatter line 2): `2026-05-18T02:55:00Z`
- Most recent v1.1 VERIFICATION.md mtime (from `.planning/milestones/v1.1-phases/12-ci-recovery/12-VERIFICATION.md`): `2026-05-19 01:49:50 +0100` ≈ `2026-05-19T00:49:50Z`
- Gap: ~22h 55m — well above the 1h threshold; assertion target is "refuse to archive"

**Suggested fixture file shape** (`tests/fixtures/v11_13h_gap/scenario.json`):
```json
{
  "audit_path": ".planning/milestones/v1.1-MILESTONE-AUDIT.md",
  "audit_frontmatter_audited_at": "2026-05-18T02:55:00Z",
  "most_recent_verification_path": ".planning/milestones/v1.1-phases/12-ci-recovery/12-VERIFICATION.md",
  "most_recent_verification_mtime_utc": "2026-05-19T00:49:50Z",
  "gap_hours": 22.92,
  "threshold_hours": 1.0,
  "expected_outcome": "refuse_archive",
  "override_flag": "--accept-stale-audit",
  "override_expected_outcome": "archive_with_logged_warning"
}
```

**Static-fixture consumer pattern** (from `tests/integration/conftest.py` lines 316-346 — extract the JSON-stage idiom, drop the bind-mount staging):
```python
@pytest.fixture(scope="function")
def v11_13h_gap_scenario():
    """Static replay of v1.1 audit-vs-verification 13h-gap (actual gap ~23h)."""
    src = _repo_root() / "tests" / "fixtures" / "v11_13h_gap" / "scenario.json"
    return json.loads(src.read_text())
```

The fixture is read-only — no teardown needed.

---

### `tests/ci/test_no_placeholder_one_liners.py` allowlist JSON (likely empty)

**Analog:** `.planning/phases/14-mobile-responsive-dashboard/mobile-hidden-allowlist.json` (shape source for the JSON file format).
**Match:** EXACT for shape; content likely empty for TOOL-01 (placeholder one-liners shouldn't be retained anywhere).

**Allowlist JSON shape + mandatory-reason discipline** — see Shared Patterns §Allowlist JSON below.

---

### `.github/workflows/planning-tooling-gate.yml` (CI workflow)

**Analog:** `.github/workflows/bybit-bypass-gate.yml` (Phase 13 BC-03 standalone CI job)
**Match:** EXACT — same role (standalone CI job pinning a grep-gate test), same data flow (PR/push triggers, runs pytest on a single test file).

**Workflow imports + triggers** (lines 27-46):
```yaml
name: BC-03 Bybit-bypass grep gate

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

defaults:
  run:
    shell: bash

jobs:
  bc03-grep-gate:
    name: BC-03 grep gate (no Bybit bypass outside connector)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
```

**Install + run step** (lines 50-61):
```yaml
      - name: Install pytest
        run: |
          python -m pip install --upgrade pip
          pip install pytest==7.4.4

      - name: Run BC-03 grep gate
        # IMPORTANT: do NOT add `continue-on-error: true`. Failures must block
        # PR merge -- that is the entire point of the gate.
        run: pytest tests/ci/test_no_bybit_bypass.py -v
```

For Phase 15, the planner has two options:
- (a) one consolidated `planning-tooling-gate.yml` running all 3 new `tests/ci/test_*.py` files;
- (b) three separate workflows mirroring BC-03's "one contract per workflow" precedent.

Phase 13 chose (b) — readable per-contract PR check name. Recommend the same for Phase 15.

---

## Shared Patterns

### Allowlist JSON shape (cross-cutting — applies to all 3 grep gates if any false-positive comes up)

**Source:** `.planning/phases/14-mobile-responsive-dashboard/mobile-hidden-allowlist.json` (shape) + `tests/integration/test_no_mobile_hidden_data.py::_load_allowlist` (consumer pattern)
**Apply to:** TOOL-01 placeholder allowlist (likely empty); TOOL-02 / TOOL-03 wired-assertion allowlists (also likely empty).

**Consumer pattern** (`test_no_mobile_hidden_data.py` lines 77-103):
```python
def _load_allowlist() -> set[str]:
    """Entries without a non-empty `reason` field are silently dropped (mirrors
    audit_bybit_bypass.py allowlist discipline; prevents drive-by allowlisting
    without explanation)."""
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
```

**JSON entry shape** (per `audit_responsive.py` lines 79-125 — the canonical loader):
```json
[
  {"file": "path/relative/to/repo", "line": 42, "reason": "specific justification — no empty strings"}
]
```

Pattern S3 discipline (from Phase 14 PATTERNS): entries without a non-empty `reason` are silently dropped. Two-line audit-time WARN on JSON parse failure or non-list root (lines 91-114 of `audit_responsive.py`) — mirror for any new audit script that ships in this phase.

### REPO_ROOT resolution + perf discipline

**Source:** `tests/ci/test_no_bybit_bypass.py` lines 55-64 + lines 179-196 (`_is_exempt` with string-prefix check, NOT per-file `.resolve()`)
**Apply to:** All 3 new `tests/ci/test_*.py` files.
**Critical perf note (extracted from analog comments):** WSL2 filesystem stats are slow — calling `.resolve()` per file pushed the BC-03 gate from ~4s to ~60s+. Use string-prefix `startswith()` on pre-computed `_EXEMPT_PREFIXES`, not per-file `.resolve()`. Same applies for the `*-PLAN.md` scan.

```python
REPO_ROOT = Path(__file__).resolve().parents[2]  # resolved ONCE at module import

_EXEMPT_PREFIXES: tuple[str, ...] = tuple(sorted(str(p) + "/" for p in EXEMPT_PATHS))
_EXEMPT_FILE_STRS: frozenset[str] = frozenset(str(f) for f in EXEMPT_FILES)

SKIP_PARTS: frozenset[str] = frozenset(
    {"__pycache__", ".venv", "venv", "env", ".git", ".tox", "node_modules"}
)

def _is_exempt(path: Path) -> bool:
    if any(part in SKIP_PARTS for part in path.parts):
        return True
    spath = str(path)
    if spath in _EXEMPT_FILE_STRS:
        return True
    return spath.startswith(_EXEMPT_PREFIXES)
```

### Dual-form scan parity (pathlib + subprocess grep)

**Source:** `tests/ci/test_no_bybit_bypass.py::test_grep_command_matches_pytest_scan` lines 253-323
**Apply to:** TOOL-01 grep gate only (TOOL-02 and TOOL-03 are single-file string presence — no need for parity).

GNU grep's `--exclude-dir=PAT` matches the directory basename, not a path-segment glob. Post-filter grep stdout in Python with the same `_is_exempt` helper. Set-equality assertion (not "stdout is empty") so the check is correct in both RED and GREEN states.

### Audit script + CI gate two-file precedent

**Source:**
- Phase 13: `scripts/audit_bybit_bypass.py` (producer) + `tests/ci/test_no_bybit_bypass.py` (gate).
- Phase 14: `scripts/audit_responsive.py` (producer) + `tests/integration/test_no_mobile_hidden_data.py` (gate).

**Apply to TOOL-01:** the "audit script" role is filled by the **`plan.validate` SDK verb itself** (out-of-repo). The **repo-local CI gate** (`tests/ci/test_no_placeholder_one_liners.py`) is independent — it scans `*-PLAN.md` files directly, not the SDK output. Both layers shipped together is the established pattern: producer (verb) and gate (test) catch different drift modes.

---

## No Analog Found

Files / deliverables with no close in-repo match. Planner must use RESEARCH.md and external sources, and explicitly decide structural questions flagged below.

### §1 — SDK verb implementations (out-of-repo)

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| SDK verb `plan.validate` (location: `~/.claude/get-shit-done/bin/lib/`, host machine, OR `node_modules/@gsd-build/sdk/dist/` — absent in this repo) | service (CLI verb) | request-response | SDK source is not in this repo; `node_modules/@gsd-build/sdk/` not installed. Closest verb-shape analogs in `~/.claude/get-shit-done/bin/lib/` (e.g., `plan-scan.cjs`, `roadmap.cjs`) but reading-only — none of them validate plan content. **No `plan.validate` verb exists today** (grep confirmed). |
| SDK verb `roadmap.analyze --apply` umbrella-supersession (out-of-repo) | service (CLI verb) | transform + diff-to-stdout | `roadmap.analyze` exists today (consumed by `~/.claude/get-shit-done/workflows/complete-milestone.md` line 87) but is a readiness-report verb only. **No supersession-detection logic exists today** (grep confirmed in `roadmap.cjs` — 621 lines, no `supersed` / `umbrella` strings). |
| `/gsd-complete-milestone` audit-freshness gate + `--accept-stale-audit` (out-of-repo: workflow MD + `milestone.cjs::cmdMilestoneComplete`) | controller (workflow gate) | request-response | `cmdMilestoneComplete` in `~/.claude/get-shit-done/bin/lib/milestone.cjs` lines 91-271 archives unconditionally — no `audited_at` check, no override flag plumbing. The workflow MD at `~/.claude/get-shit-done/workflows/complete-milestone.md` has no pre-archive freshness step. |

**Critical structural call for the planner (do not soften):** SDK verb implementations have no repo analog because the SDK source lives outside the repo (at `~/.claude/get-shit-done/bin/lib/`, the operator's home dir). The planner must explicitly classify these deliverables as one of:
- **(a) Documentation-only contributions** shipped under `.planning/sdk-proposals/*.md` (planning artifacts describing what the verb should do; operator ports to SDK separately);
- **(b) SDK-fork PR pointer** — a stub file under `.planning/sdk-proposals/` linking to an upstream PR or fork that the operator must apply;
- **(c) Vendored copy under repo** — copy `~/.claude/get-shit-done/bin/lib/{plan-scan,roadmap,milestone}.cjs` into the repo (e.g. under `.gsd-sdk-overlays/`) and ship the diff there with a documented merge path back to the host SDK.

The downstream CI grep gates (`test_roadmap_analyze_supersession_wired.py`, `test_audit_freshness_gate.py`) depend on this decision — they need a stable file path to grep. **The planner must pick (a/b/c) before writing the PLANs**; without that decision the gates cannot land. (Recommend (a) — documentation under `.planning/sdk-proposals/` — for minimal cross-repo coupling; but surface all three to the operator.)

### §2 — Out-of-repo workflow source (target of TOOL-02 / TOOL-03 wiring assertions)

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `~/.claude/get-shit-done/workflows/complete-milestone.md` (consumer; grepped by TOOL-02 + TOOL-03 wiring tests) | config (workflow doc) | static read | The workflow file lives outside the repo. The TOOL-02/TOOL-03 grep gates need to assert that this file contains the right invocation strings before the archive step — but pytest needs a stable path to read. Same trifurcation as §1: grep host path with `pytest.skip` if absent; vendor a copy into `.planning/sdk-proposals/`; or require operator-installed vendored copy. |

### §3 — Git pre-commit hook chain

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `.git/hooks/pre-commit` extension (chain `plan.validate` for modified `*-PLAN.md`) | config (git hook) | event-driven (pre-commit) | Only `.git/hooks/pre-commit.sample` exists on this branch (verified). No real pre-commit hook installed, no `pre-commit` framework config (`.pre-commit-config.yaml`) at repo root, no `husky` config. **Genuinely novel for this repo.** Planner must decide: ship as self-installing script in `scripts/install-pre-commit.sh`, ship as `.pre-commit-config.yaml` (de facto Python toolchain standard), or ship as documentation-only with operator running the hook manually. Pre-commit hook activation is operator-side and CI-side both; the canonical fallback is the CI grep gate (`tests/ci/test_no_placeholder_one_liners.py`) — that fires PR-time even if no operator runs the hook locally. |

---

## Metadata

**Analog search scope:**
- `tests/ci/` (1 file: `test_no_bybit_bypass.py`)
- `tests/integration/` (`conftest.py`, `test_no_mobile_hidden_data.py`)
- `tests/fixtures/` (tournament + tape subdirs)
- `.github/workflows/` (20 workflows scanned; `bybit-bypass-gate.yml` selected as analog)
- `scripts/audit_*.py` (2 files — `audit_bybit_bypass.py` + `audit_responsive.py`)
- `~/.claude/get-shit-done/bin/lib/` (host SDK source, read-only — `plan-scan.cjs`, `roadmap.cjs`, `milestone.cjs`, `validate-command-router.cjs`, `commands.cjs` — confirmed no existing `plan.validate` / supersession / audit-freshness logic)
- `~/.claude/get-shit-done/workflows/` (`complete-milestone.md`, `plan-phase.md` — confirmed `roadmap.analyze` is used but as readiness verb only)
- `.git/hooks/` (confirmed `pre-commit.sample` only; no installed hook)

**Files scanned:** ~80 (in-repo) + ~20 (host SDK source for absence confirmation)

**Pattern extraction date:** 2026-05-22

**Key canonical-data extractions for fixture content:**
- `v1.1 audited_at = 2026-05-18T02:55:00Z` (from `.planning/milestones/v1.1-MILESTONE-AUDIT.md` line 2 frontmatter)
- `Phase 12 VERIFICATION.md mtime = 2026-05-19T00:49:50Z UTC` (from `stat -c %y` on `.planning/milestones/v1.1-phases/12-ci-recovery/12-VERIFICATION.md`)
- Actual gap ≈ 22.92h, well above the 1h threshold — fixture asserts `expected_outcome: refuse_archive`
