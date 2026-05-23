---
phase: 14
plan: 02
subsystem: frontend-tests
tags: [tdd, wave-0, mobile, responsive, playwright, grep-gate]
dependency_graph:
  requires: []
  provides:
    - "tests/e2e/test_responsive_dashboard.py (RED Playwright matrix)"
    - "tests/integration/test_no_mobile_hidden_data.py (mostly-GREEN static gate)"
    - "mobile-hidden-allowlist.json (empty baseline)"
    - "touch-target-allowlist.json (pre-populated; 2 out-of-scope entries)"
  affects:
    - "Wave 2 plans (14-03/04/05): each plan drives a subset of the 7 e2e tests GREEN"
    - "Plan 14-01: file/artifact tests turn GREEN once 14-01 lands"
tech_stack:
  added: []
  patterns:
    - "Pattern S1: REPO_ROOT = Path(__file__).resolve().parents[N]"
    - "Pattern S2: pathlib-only scan (subprocess grep -r intentionally omitted)"
    - "Pattern S3: allowlist with mandatory `reason` field (silently drops missing)"
    - "Pattern S4: data-testid adjacency in anti-hidden regex (anti-collateral)"
    - "Pattern S6: browser_context_args parametrize matrix (NOT device descriptors)"
    - "Pattern S7: @pytest.mark.usefixtures('bootstrap_stack') per test body"
key_files:
  created:
    - tests/e2e/test_responsive_dashboard.py
    - tests/integration/test_no_mobile_hidden_data.py
    - .planning/phases/14-mobile-responsive-dashboard/mobile-hidden-allowlist.json
    - .planning/phases/14-mobile-responsive-dashboard/touch-target-allowlist.json
  modified: []
decisions:
  - "Pre-populated touch-target-allowlist.json (2 entries) rather than empty list, to satisfy must_haves.artifacts contains: '\"reason\":' check without requiring a live Playwright run in worktree"
  - "Used Playwright Page.evaluate() single-pass JS for all DOM probes (one round-trip per test, not N)"
  - "Test 4-6 (mobile-only assertions) wrapped with pytest.skip on ipad-portrait; matrix still parametrizes both viewports for consistent test-id reporting"
  - "Anti-`hidden` regex requires data-testid='(metric|tile|chip|row)-*' adjacency on SAME line per Pattern S4; permits md:hidden as the dual-render desktop-hide branch"
metrics:
  duration_minutes: 5
  completed_date: 2026-05-22
  tasks_completed: 2
  files_created: 4
  files_modified: 0
  commits: 2
  test_files_added: 2
  test_functions_added: 12
  playwright_matrix_items: 14
---

# Phase 14 Plan 02: Wave-0 RED Test Files Summary

**One-liner:** Two Wave-0 test files locked the MOBILE-02 + MOBILE-03 validation surface — 7 parametrized Playwright tests at 375×667 + 768×1024 (RED, Wave 2 drives them GREEN), 5 static gates with anti-hidden-on-data regex + tailwind/audit/viewport-meta file checks (2 GREEN immediately, 3 RED pending Plan 14-01 land).

## What Was Built

Two test files plus two allowlist JSON files committed as Wave-0 deliverables. Tests assert the contracts of MOBILE-02 (per-component mobile reflow) + MOBILE-03 (no-h-scroll, ≥44px touch targets, banner visibility) + MOBILE-01 file-content invariants. Wave-1 close state is by design: most assertions fail against the unreflowed dashboard so the test surface becomes a forcing function for Wave-2 reflow plans (14-03/04/05).

### `tests/e2e/test_responsive_dashboard.py` — 371 non-blank/non-comment lines, 7 test functions

| Test | Viewports | Wave-1 Expectation | Driven GREEN by |
|------|-----------|--------------------|-----------------|
| `test_no_horizontal_scroll` | iphone-se + ipad-portrait | RED | 14-03/04/05 reflow |
| `test_touch_targets_44px` | iphone-se + ipad-portrait | RED | 14-03/04/05 chip/button padding |
| `test_banner_visible_without_scroll` | iphone-se + ipad-portrait | RED | 14-04 PathToLiveTile reflow |
| `test_dashboard_single_column_mobile` | iphone-se only | RED | 14-03 Dashboard.jsx reflow |
| `test_path_to_live_rows_full_width` | iphone-se only | RED | 14-04 PathToLiveTile reflow |
| `test_key_metrics_2col` | iphone-se only | RED | 14-03 KeyMetricsStrip reflow |
| `test_tournament_dual_render` | iphone-se + ipad-portrait | RED (locked B2 testid contract) | 14-05 TournamentDashboard dual-render |

**Matrix mechanics:** `@pytest.mark.parametrize("browser_context_args", VIEWPORTS, indirect=True, ids=[...])` — raw viewport dicts, NOT the Playwright device-descriptor table (iPhone SE descriptor is 320×568 1st gen, not 375×667 2nd gen required by spec, per RESEARCH Pitfall 3). Pytest collection reports 14 items (7 tests × 2 viewports).

**Single-pass DOM probes:** every test uses `page.evaluate("""... JS ...""")` for one round-trip rather than N per-locator probes (RESEARCH "Don't Hand-Roll" guidance). Cuts test time and avoids per-locator race conditions.

**Touch-target test allowlist handling:** loads `touch-target-allowlist.json`; filters failures by substring-match of allowlist selectors against rendered hints (tag + testid + href). Pre-populated with 2 entries:
- `button[data-testid='emergency-stop']` — existing kill-switch button, defer to future a11y phase
- `a[href='/tournament']` — existing nav link, defer to future a11y phase

**Tournament dual-render test:** encodes the LOCKED B2 testid contract verbatim:
- `data-testid="tournament-mobile-card-list"` — mobile wrapper (`md:hidden`)
- `data-testid="tournament-desktop-table-wrapper"` — desktop wrapper (`hidden md:block`)
- `data-testid="tournament-row-${runId}"` — same string on both branches; only one branch is display-visible per viewport

### `tests/integration/test_no_mobile_hidden_data.py` — 195 non-blank/non-comment lines, 5 test functions

| Test | Wave-1 Expectation | Why |
|------|--------------------|-----|
| `test_no_hidden_md_on_data_carrier` | **GREEN** | RESEARCH Pitfall 2 verification table: zero preexisting violations on baseline. 10 existing `hidden (sm\|md\|lg):*` usages are decorative (no data-testid match). |
| `test_tailwind_screens_declared` | RED | Plan 14-01 Task 1 must add `theme.screens` block. |
| `test_viewport_meta_present` | **GREEN** | Meta already at `frontend/index.html:17`. |
| `test_responsive_audit_shape` | RED | Plan 14-01 Task 2 must generate `responsive-audit.json`. |
| `test_responsive_audit_count_zero` | RED | Same — depends on 14-01 Task 2 artifact. Includes proof-of-work `len(data) > 0` defense against silently-empty script (false-positive #5). |

**Anti-hidden regex (Pattern S4) — load-bearing:**
```python
MOBILE_HIDE_PATTERN = re.compile(
    r'\bhidden\s+(?:sm|md|lg|xl):(?:block|flex|grid|table|inline|inline-block|inline-flex)\b'
)
DATA_TESTID_DATA_CARRIER = re.compile(
    r'data-testid="(metric|tile|chip|row)-[^"]+"'
)
```
Per-line evaluation: both patterns must match the SAME line for a violation. Decorative usage (mobile-hide class without `data-testid="(metric|tile|chip|row)-*"` match) is PERMITTED.

**Allowlist file (mobile-hidden-allowlist.json):** empty list `[]` per RESEARCH Pitfall 2 verified safe baseline.

**No subprocess grep -r half:** documented in test docstring — per-line `data-testid` adjacency can't be expressed in plain `grep -r` without false negatives (Pattern S2 constraint).

## First-Run Pytest Results

Ran locally against the worktree (no docker stack — confirms file parses + assertions execute):

```
$ PYTHONPATH=. pytest tests/integration/test_no_mobile_hidden_data.py -v
============================== test session starts ==============================
tests/integration/test_no_mobile_hidden_data.py::test_no_hidden_md_on_data_carrier PASSED
tests/integration/test_no_mobile_hidden_data.py::test_tailwind_screens_declared FAILED
tests/integration/test_no_mobile_hidden_data.py::test_viewport_meta_present PASSED
tests/integration/test_no_mobile_hidden_data.py::test_responsive_audit_shape FAILED
tests/integration/test_no_mobile_hidden_data.py::test_responsive_audit_count_zero FAILED
========================= 3 failed, 2 passed in 1.24s ==========================
```

**Result:** Matches the GREEN expectation block in the plan verbatim. 2 GREEN immediately (Pitfall 2 baseline + already-present viewport meta), 3 RED until Plan 14-01 lands (`tailwind.config.js` screens block + `responsive-audit.json` artifact).

```
$ PYTHONPATH=. pytest tests/e2e/test_responsive_dashboard.py --collect-only -q
tests/e2e/test_responsive_dashboard.py: 14
```

**Result:** Pytest collection succeeds, 14 items (7 functions × 2 viewports). No docker stack booted in this worktree, so the test bodies are NOT executed — they will run RED against Wave-1 dashboard once CI matrix lands (Plan 14-06).

## Acceptance Criteria — All Met

### Task 1 (e2e test file)
- [x] File exists at `tests/e2e/test_responsive_dashboard.py`
- [x] ≥150 non-comment lines (actual: 371)
- [x] 7 required test functions present (verified via `ast.parse`)
- [x] `VIEWPORTS` constant with both 375×667 AND 768×1024 dicts
- [x] No use of Playwright device-descriptor table (`grep -q "playwright.devices"` returns no hits)
- [x] Uses `@pytest.mark.parametrize("browser_context_args", ..., indirect=True)` (Pattern S6)
- [x] Uses `bootstrap_stack` fixture (Pattern S7)
- [x] `test_tournament_dual_render` references all 3 LOCKED B2 testids: `tournament-mobile-card-list`, `tournament-desktop-table-wrapper`, `tournament-row-`
- [x] `touch-target-allowlist.json` exists as valid JSON list, pre-populated with 2 entries each carrying mandatory `reason` field
- [x] Pytest collection succeeds, 14 items reported

### Task 2 (integration test file)
- [x] File exists at `tests/integration/test_no_mobile_hidden_data.py`
- [x] ≥80 non-comment lines (actual: 195)
- [x] 5 required test functions present (verified via `ast.parse`)
- [x] Both `MOBILE_HIDE_PATTERN` AND `DATA_TESTID_DATA_CARRIER` regexes defined
- [x] Regex matches documented data-carrier set (`metric|tile|chip|row`)
- [x] Uses `REPO_ROOT = Path(__file__).resolve().parents[2]` (Pattern S1)
- [x] `mobile-hidden-allowlist.json` exists as valid JSON list (empty per Pitfall 2 baseline)
- [x] `test_no_hidden_md_on_data_carrier` passes locally (Pitfall 2 verified)
- [x] `test_viewport_meta_present` passes locally (meta already in index.html)

## Deviations from Plan

**None.** Plan executed exactly as written. The one judgment call recommended by the advisor was already encoded in the plan's must_haves block: `touch-target-allowlist.json` had to be pre-populated to satisfy `contains: '"reason":'`. Action step #1 documents the iterative-discovery procedure for an executor with a live stack but explicitly provides 2 concrete pre-populate entries; I used those verbatim since no docker stack was available in the worktree.

No authentication gates encountered (no external services touched).

No CLAUDE.md directive conflicts (Wave-0 test files are read-only static analysis + read-only browser DOM probes — no trust boundary changes).

## Threat Surface

Per the plan's threat model: N/A — no new attack surface. Pure read-only test files. No external inputs, no state mutation, no API routes, no auth changes, no data storage. The two test-screenshot information-disclosure and allowlist-tampering threats listed in the plan are inherited from the existing dashboard-smoke.yml infrastructure and remain `accept` / `mitigate` per the plan's disposition.

## Known Stubs

**None.** Both test files are fully wired; no placeholders, no TODO assertions, no mock data flowing to UI. The 3 RED tests (`test_tailwind_screens_declared`, `test_responsive_audit_shape`, `test_responsive_audit_count_zero`) are RED because their target artifacts don't exist yet (Plan 14-01 deliverable), not because of stubs in this plan.

## Commits

| Hash | Message |
|------|---------|
| `0eed59e` | `test(14-02): add RED responsive playwright matrix at 375x667 + 768x1024` |
| `81ea0a3` | `test(14-02): add mobile-hidden grep gate + MOBILE-01 file/artifact checks` |

## Self-Check: PASSED

Verified all SUMMARY claims before commit:
- [x] `tests/e2e/test_responsive_dashboard.py` exists (created in commit `0eed59e`)
- [x] `tests/integration/test_no_mobile_hidden_data.py` exists (created in commit `81ea0a3`)
- [x] `.planning/phases/14-mobile-responsive-dashboard/touch-target-allowlist.json` exists (commit `0eed59e`)
- [x] `.planning/phases/14-mobile-responsive-dashboard/mobile-hidden-allowlist.json` exists (commit `81ea0a3`)
- [x] Commit `0eed59e` in `git log`
- [x] Commit `81ea0a3` in `git log`
- [x] Both test files parse via `python3 -c "import ast; ast.parse(...)"` (verified twice)
- [x] Pytest collection of e2e file reports 14 items
- [x] Integration test 2 GREEN / 3 RED matches plan's GREEN expectation block verbatim
