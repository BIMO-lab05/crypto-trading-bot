---
phase: 14-mobile-responsive-dashboard
reviewed: 2026-05-22T22:55:00Z
depth: deep
files_reviewed: 8
files_reviewed_list:
  - frontend/src/components/PathToLiveTile.jsx
  - frontend/src/components/TournamentFilterChips.jsx
  - frontend/src/pages/TournamentDashboard.jsx
  - frontend/tailwind.config.js
  - scripts/audit_responsive.py
  - tests/e2e/test_responsive_dashboard.py
  - tests/integration/test_no_mobile_hidden_data.py
  - .github/workflows/dashboard-smoke.yml
findings:
  critical: 3
  warning: 8
  info: 5
  total: 16
fix_iteration: 1
fixed_at: 2026-05-22T23:30:00Z
fixed_in_scope:
  critical: 3
  warning: 7
deferred:
  warning: 1   # WR-08 — bootstrap_stack carry-in, OP-04/INFRA-02 per-task scope
  info: 5      # IN-01..IN-05 — out of scope per task (severity: info)
status: clean
---

# Phase 14: Code Review Report

**Reviewed:** 2026-05-22T22:55:00Z
**Depth:** deep
**Files Reviewed:** 8
**Status:** issues_found

## Summary

Phase 14 ships a Tailwind breakpoint contract, a hardcoded-width audit script, a Playwright responsive matrix, a CI workflow extension, an anti-hidden grep gate, plus surgical reflows on `PathToLiveTile.jsx`, `TournamentFilterChips.jsx`, and `TournamentDashboard.jsx`. The reflow component edits themselves are correct in isolation, but the validation surface around them has structural defects that defeat the phase's stated proof-of-correctness:

1. **CI does not actually exercise Phase 14 source.** The workflow adds the responsive smoke step but never rebuilds the frontend bundle. The frontend Dockerfile is consumer-only (`COPY dist /usr/share/nginx/html`); `frontend/dist/` is gitignored. In a fresh CI checkout there is no `dist/` to copy, so `docker compose up --build` either fails on the COPY or, depending on BuildKit cache state, serves a stale or empty bundle. The 14-06 commit titled "harden Plan 14-06 — mandatory frontend rebuild before responsive tests" modified only `14-06-PLAN.md`; the workflow YAML still has zero `npm run build` step. Phase 14 SUMMARY itself documents the executor hitting "stale May-20 nginx image" — that footgun ships as-is.

2. **Plan 14-03 closed as verify-only with a self-documented test-vs-code conflict.** `KeyMetricsStrip.jsx` mtime is May 19; the file was untouched by 14-03. Its top-level `data-testid="key-metrics-strip"` wrapper carries `style={{ display: 'contents' }}`, which makes Chromium's `getBoundingClientRect()` return 0×0 by spec — that defeats `test_dashboard_single_column_mobile` (ratio = 0 < 0.90 ⇒ FAIL) and silently passes `test_key_metrics_2col` (falls back to one TileState child wrapper ⇒ "0 rows with >2 columns" ⇒ vacuously PASS). The SUMMARY admits both consequences and defers the fix to a future "phase-level reconciliation." Two Phase 14 tests landed RED-or-vacuous by design.

3. **Mirrored testid contract has a duplicate-DOM-id collision on null `run_id`.** Both branches of the dual-render coalesce to the literal string `'unknown'` when `row.run_id` is null. With ≥2 missing-run_id rows, the mobile branch emits multiple `<div data-testid="tournament-row-unknown">` siblings AND React duplicate-key warnings. Inherited from `TournamentLeaderboard.jsx:361`, mirrored intentionally — but Phase 14 is the place the bug widens from "1 desktop row" to "2 rows in DOM at once."

4. **Mobile card omits 5+ fields from the desktop leaderboard contract.** The phase's CONTEXT.md declares "Zero information loss (no `display: none` shortcuts)," but `TournamentLeaderboard.jsx` COLUMNS at lines 52-67 render 14 columns (including `target_mode`, `dir_acc_corrected`, `r2_returns`, `__significance`, `train_seconds`, `failure_reason`) while the mobile card at `TournamentDashboard.jsx:391-503` shows only 7 fields. Five-plus fields are functionally hidden on mobile via `md:hidden` (a `display:none` mechanism), contradicting the phase's stated invariant. The phase plan permitted "card content reordering" at Claude's Discretion — that's a permission to reorder, not a permission to drop.

The reflow JSX/Tailwind code itself reads clean. The defect cluster is in the validation glue: stale-bundle CI, vacuous-pass tests, deferred Phase-7-vs-Phase-14 reconciliation, mobile information loss, and a duplicate-testid trap.

---

## Critical Issues

### CR-01: CI workflow runs Phase 14 e2e tests against a stale (or empty) frontend bundle

**File:** `.github/workflows/dashboard-smoke.yml:73-83`, cross-ref `frontend/Dockerfile:11`, `.gitignore`
**Issue:** The new `Run smoke (Responsive)` step calls `pytest tests/e2e/test_responsive_dashboard.py` against `http://localhost:3000` after `bootstrap.sh`. `bootstrap.sh:62` runs `docker compose up -d --build`. The frontend Dockerfile is a single-stage nginx image that does `COPY dist /usr/share/nginx/html`. `frontend/dist/` is gitignored (root `.gitignore` lists `dist/`). A fresh CI checkout has no `dist/` directory, so the COPY either fails or — with buildx default behavior on a permissive cache — copies an empty directory or a stale layer. There is no `npm ci && npm run build` step anywhere in the workflow or in `bootstrap.sh`. The 14-06 SUMMARY explicitly records this exact trap ("Stale-build trap: docker compose --build alone reuses cache when only frontend/src changed (Dockerfile copies pre-built dist/). Must run `cd frontend && npm run build` first") and commit `9e1a8d5` is titled "harden Plan 14-06 — mandatory frontend rebuild before responsive tests" but modified only `14-06-PLAN.md`, not the workflow YAML. Net effect: every Phase 14 className/JSX change documented in the SUMMARYs is invisible to the CI matrix.
**Fix:** Add an explicit build step before bootstrap:
```yaml
      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json

      - name: Build frontend bundle
        run: |
          cd frontend
          npm ci
          npm run build

      - name: Boot stack via bootstrap.sh (paper mode, tape source)
        # ... existing block
```
Also harden `frontend/Dockerfile` to a multi-stage build (node:20-alpine → nginx:alpine) so a fresh checkout cannot serve an empty bundle: the build stage produces `dist/` inside the image, eliminating dependence on a host-side artifact.

---

### CR-02: `display: contents` on key-metrics-strip wrapper makes `test_dashboard_single_column_mobile` FAIL and `test_key_metrics_2col` vacuously PASS

**File:** `frontend/src/components/KeyMetricsStrip.jsx:202`, `tests/e2e/test_responsive_dashboard.py:250-280, 363-426`
**Issue:** `KeyMetricsStrip.jsx:202` is `<div data-testid="key-metrics-strip" style={{ display: 'contents' }}>`. Per CSS spec, an element with `display: contents` generates no layout box; `getBoundingClientRect()` returns `{x:0, y:0, width:0, height:0}` in Chromium. Two Phase 14 tests query this exact testid:

- `test_dashboard_single_column_mobile` (line 256) probes `'[data-testid="key-metrics-strip"]'` width vs `innerWidth`, requiring `rect.width / innerW >= 0.90`. With `display: contents`, `rect.width = 0`, ratio = 0, `too_narrow` is non-empty, assertion fails. This test cannot pass against the current KeyMetricsStrip.
- `test_key_metrics_2col` (line 368) queries the strip, then `strip.querySelectorAll('[data-testid^="metric-"]')`. No `Cell` in KeyMetricsStrip carries a `metric-*` testid — so `candidates.length === 0` and the test falls back to `Array.from(strip.children)`. The `display:contents` div has one child (the TileState wrapper), which has one rendered child (`<div>` at line 210). Right-edge dedup with 4px tolerance yields one column. The "rows with >2 columns" check is trivially empty. The test PASSES, but it tests nothing about whether the metric cells actually render in 2 columns at iPhone SE.

Plan 14-03 SUMMARY documents both consequences in its "Caveat documented for Plan 14-06" block and defers resolution. The defect ships in v1.2-polish-real-time.
**Fix:** Two options, pick one:
1. **Add testids to cells.** Add `data-testid={`metric-${slugify(eyebrow)}`}` (or similar) on each `Cell` in `KeyMetricsStrip.jsx:73-151`. The 2-col test then runs against actual metric cells. Update the single-column test to probe the inner grid container (`.max-w-7xl` div at line 217) instead of the `display: contents` wrapper.
2. **Remove `display: contents`.** Plan 14-03 explicitly forbids this on Phase-7 invariant grounds (15 sibling tiles share the pattern). If keeping it, the Playwright tests must not probe the `display: contents` element — refactor both tests to walk to the first descendant with `box-sizing` rendered.

Whichever path: stop landing tests that the SUMMARY itself flags as broken.

---

### CR-03: Mirrored `tournament-row-${runId ?? 'unknown'}` produces duplicate DOM testids and React keys on null run_id

**File:** `frontend/src/pages/TournamentDashboard.jsx:366,372-373`, mirror in `frontend/src/components/TournamentLeaderboard.jsx:361,365-366`
**Issue:** Both the mobile card branch (TournamentDashboard.jsx:366) and the desktop table branch (TournamentLeaderboard.jsx:361) coalesce missing `row.run_id` to the literal string `'unknown'`. When ≥2 rows in `sortedRows` have null `run_id`:

- **Mobile branch:** N sibling `<div key="unknown" data-testid="tournament-row-unknown">`. React emits "Encountered two children with the same key, `unknown`" warnings in dev; in prod, reconciliation may reuse the wrong DOM node, causing card content to ghost across rows on re-render.
- **Desktop branch (pre-existing, mirrored intentionally):** N sibling `<tr key="unknown">` — same problem inside the table.
- **Playwright contract:** `tests/e2e/test_responsive_dashboard.py:460` does `page.locator('[data-testid^="tournament-row-"]').first` — `.first` masks the collision in this specific test, but any future test relying on testid uniqueness (e.g. counting rows by testid) will misreport.

Phase 14 widens the bug from "1 stack of bad keys" to "2 stacks at once" (desktop + mobile rendered into the DOM, with `display: none` hiding one branch but not removing it). Comments at 359-365 advertise this as load-bearing but do not flag the null-run_id collision.
**Fix:** Use the array index as a tiebreaker on null:
```jsx
{sortedRows.map((row, idx) => {
  const runId = row?.run_id ?? `unknown-${idx}`
  ...
}
```
Apply the same fix at `TournamentLeaderboard.jsx:361` to preserve the mirroring contract. If a missing `run_id` is impossible by upstream schema invariant, instead of coercing to a string, drop the row or throw — silent coercion masks the data-integrity bug.

---

## Warnings

### WR-01: Mobile card drops 5+ leaderboard columns the desktop table renders — contradicts "zero information loss" invariant

**File:** `frontend/src/pages/TournamentDashboard.jsx:391-503`, cross-ref `frontend/src/components/TournamentLeaderboard.jsx:52-67`
**Issue:** Desktop renders 14 columns via `COLUMNS` array: `__marker`, `architecture`, `symbol`, `horizon`, `target_mode`, `dsr`, `oos_sharpe`, `psr`, `dir_acc_corrected`, `r2_returns`, `__significance`, `train_seconds`, `status`, `failure_reason`. Mobile card renders only: `symbol`, `horizon`, `dsr`, `oos_sharpe`, `psr`, `architecture`, `status` — 7 fields. Missing from mobile: `target_mode`, `dir_acc_corrected`, `r2_returns`, `__significance` (SignificanceBadge), `train_seconds`, `failure_reason`. CONTEXT.md (line 9) states "Zero information loss (no `display: none` shortcuts) … across `Dashboard.jsx`, `PathToLiveTile.jsx`, `KeyMetricsStrip`, and `pages/TournamentDashboard.jsx`." `md:hidden` IS a `display:none` mechanism (CSS class with `display: none` rule at the breakpoint), so the mobile branch silently drops 5+ fields that the desktop branch carries. The phase plan permits "Card content reordering inside `TournamentDashboard.jsx` mobile card view ... Claude's Discretion at implementation time" — reordering, not omission. Significance badges and failure reasons in particular are operationally load-bearing (failed-run diagnosis on mobile is impossible without `failure_reason`).
**Fix:** Add the missing fields to the mobile card. Options:
1. **Expand the meta-grid:** add rows for `Target Mode`, `Dir Acc`, `R² Returns`, `Train Sec`, `Significance` (render `<SignificanceBadge significance={perSymbolSignificance[row.symbol]} ... />` inline), and on failure render `failure_reason` in a colored block.
2. **Collapsible secondary fields:** render the 5 missing fields inside a `<details>` element that defaults closed; primary metrics stay above-the-fold while operators can drill in.
Either way, document in 14-05-SUMMARY why these fields are omitted (if intentional) or restore them.

### WR-02: `_load_allowlist()` in audit script silently swallows malformed allowlist JSON

**File:** `scripts/audit_responsive.py:84-100`
**Issue:** Lines 88-89: `except (OSError, json.JSONDecodeError): return {}`. A typo in the allowlist file (trailing comma, missing brace) silently drops every entry — the audit then re-emits every previously-allowlisted line as `allowlisted: false`, breaking the gate. No log, no stderr, no exit code. Compare `audit_bybit_bypass.py`-shape — that mirror also lacks the warning. Defense-in-depth missing.
**Fix:**
```python
try:
    raw = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    print(
        f"audit_responsive: WARN failed to parse allowlist {ALLOWLIST}: {exc}; "
        "treating as empty (every formerly-allowlisted hit will now report)",
        file=sys.stderr,
    )
    return {}
```

### WR-03: `_load_allowlist()` does not guard against non-list root or non-dict entries; iteration crashes on List[str]

**File:** `scripts/audit_responsive.py:91`
**Issue:** Line 91 does `for entry in raw:` with no `isinstance(raw, list)` check. If allowlist is a dict (e.g. `{"entries": [...]}`), the loop yields keys, the `isinstance(entry, dict)` guard at line 92 catches strings (good), but other JSON-valid containers would slip in unexpected ways. Mirror this guard against root shape.
**Fix:** Add `if not isinstance(raw, list): return {}` after line 89.

### WR-04: `test_no_mobile_hidden_data.py::_load_allowlist` crashes on malformed entries

**File:** `tests/integration/test_no_mobile_hidden_data.py:86-87`
**Issue:** Line 86 does `entries = json.loads(ALLOWLIST_PATH.read_text())` with no try/except, and line 87 does `{e["data_testid"] for e in entries if e.get("reason")}`. If the allowlist is malformed JSON or contains an entry without `data_testid`, the test crashes mid-collection (KeyError or JSONDecodeError) instead of failing the gate. Inconsistent with `scripts/audit_responsive.py:88-89`'s graceful degrade pattern.
**Fix:** Wrap in try/except mirroring `audit_responsive.py` shape, and guard the dict access:
```python
try:
    entries = json.loads(ALLOWLIST_PATH.read_text())
except (OSError, json.JSONDecodeError):
    return set()
if not isinstance(entries, list):
    return set()
return {
    e["data_testid"] for e in entries
    if isinstance(e, dict) and e.get("data_testid") and e.get("reason")
}
```

### WR-05: Touch-target allowlist substring match is too loose; permits cross-allowlisting

**File:** `tests/e2e/test_responsive_dashboard.py:170-181`
**Issue:** The allowlist match compares `entry["selector"]` against the rendered `hint` string via plain Python `in` substring check. A selector like `button[data-testid='emergency-stop']` legitimately matches the `hint` for the emergency-stop button. But the *converse* checks at lines 176 and 179 invert direction: `if f"data-testid='{f['testid']}'" in sel`. If a future allowlist entry contains the literal `data-testid='emergency-stop'` anywhere in its selector string (e.g. a CSS combinator like `[data-testid='emergency-stop'] + button`), every button on the page with `data-testid='emergency-stop'` matches — but also: if the allowlist selector happens to contain another testid's name as a substring (e.g. `tournament-refresh` would substring-match into a hypothetical `tournament-refresh-flyout`), unintended elements get allowlisted. Selector intent (CSS selector match) and string-in-string match are different operations.
**Fix:** Either parse selectors and use Playwright's selector engine to evaluate the allowlist (`page.locator(sel)` and compare to the failing element), or document that selectors must be exact-match strings (`{"selector_eq": "..."}`) and switch the comparison to equality. The current "substring in either direction" matcher is too permissive.

### WR-06: `audit_responsive.py` writes JSON without securing the output path against traversal

**File:** `scripts/audit_responsive.py:154-166`
**Issue:** `--out` accepts an arbitrary `Path` via argparse. A caller passing `--out /etc/passwd` (with sufficient permissions) or `--out ../../../../sensitive/path.json` would overwrite arbitrary files. The script is dev-tooling and not network-exposed, so this is low likelihood but trivial to harden. Also: line 165 does `out_path.parent.mkdir(parents=True, exist_ok=True)` — if `--out` is given a path under a restricted dir, this side-effect creates intermediate dirs the caller may not expect.
**Fix:** Validate that `--out` resolves to a path inside `REPO_ROOT`:
```python
out_path = (args.out if args.out is not None else DEFAULT_OUT).resolve()
if not out_path.is_relative_to(REPO_ROOT):
    parser.error(f"--out must resolve inside REPO_ROOT ({REPO_ROOT}); got {out_path}")
```

### WR-07: `audit_responsive.py` self-exclusion guard is dead code

**File:** `scripts/audit_responsive.py:70-74, 116-123`
**Issue:** Lines 74 and 121-123 declare and check `_SELF_PATH = "scripts/audit_responsive.py"`, but the walker on line 114 is `FRONTEND_SRC.rglob("*.jsx")` — `scripts/` is not under `frontend/src/` and the script is `.py`. The check is structurally unreachable. Comment at 116-119 explicitly states it is "semantically a no-op." Cargo-culted from `audit_bybit_bypass.py:121`.
**Fix:** Either delete the dead `_SELF_PATH` and its check entirely, or — if the acceptance gate truly literal-greps for the guard string — comment it out so future maintainers don't try to fix the "unused variable" warning by widening the walker scope and accidentally creating a real footgun. Cleaner: drop both `_SELF_PATH` and the `rel == _SELF_PATH` branch, document in the README that the walker is `.jsx`-only.

### WR-08: bootstrap_stack-coupled tests cannot run locally; CI signal is contingent on CR-01

**File:** `tests/e2e/test_responsive_dashboard.py:70,114,196,229,288,346,434` (all 7 tests)
**Issue:** Every test in the responsive matrix uses `@pytest.mark.usefixtures("bootstrap_stack")`. That session-scoped fixture clones the repo to `/tmp`, writes an empty `.env`, and shells out to `bootstrap.sh` (5-min boot). 14-06 SUMMARY records this as the test suite failing with "14 errors at setup" — bootstrap is operator-blocked locally (OP-04 / INFRA-02 carry-ins). The CI workflow runs the same fixture but, per CR-01, against a stale/empty bundle. There is therefore no environment — local or CI — in which the responsive matrix exercises the Phase 14 source against a real browser. Severity is WARNING (not BLOCKER) because the underlying fixture coupling is a pre-existing carry-in (OP-04/INFRA-02), not introduced by Phase 14. But: once CR-01 lands a frontend-rebuild step, this becomes the next bottleneck. Document the dependency chain explicitly.
**Fix:** Provide a lightweight fixture for pure-frontend matrices that does NOT require the full stack:
```python
@pytest.fixture(scope="session")
def vite_preview_server(request):
    """Boot `npm run build && npm run preview` on a free port; yield URL."""
    # Avoids the full bootstrap_stack/docker requirement for frontend-only e2e.
```
Then split tests by need: layout assertions (no-h-scroll, touch targets, single-column, dual-render) use `vite_preview_server`; behavior assertions that depend on backend data (banner state token, real PathToLive payload) keep `bootstrap_stack`. Also: document in the test module which CI lane each test belongs to so a failed `bootstrap_stack` doesn't take the layout tests down with it.

---

## Info

### IN-01: `test_responsive_audit_count_zero` proof-of-work assertion creates a brittle gate

**File:** `tests/integration/test_no_mobile_hidden_data.py:258-265`
**Issue:** The defense-in-depth assertion `len(data) > 0` ("script must walk something") becomes a failing gate if and when out-of-phase-14-scope hardcoded widths are *legitimately* cleaned up in a future phase. The test will fail for the right reason (cleanup happened) but with a misleading message ("script bug"). Anticipate this.
**Fix:** Comment-document the upper bound for "legitimate" empty: when allowlist length == 0 AND audit is also empty, that's the steady-state goal, not a script failure. Alternative: assert `audit_responsive: walked N files, found M hits` is printed to stderr and grep for the literal — proves the walker ran without coupling to non-empty output.

### IN-02: Cell components in `KeyMetricsStrip.jsx` have no per-card testid

**File:** `frontend/src/components/KeyMetricsStrip.jsx:73-151,284-328`
**Issue:** Each `Cell` would benefit from a stable testid (`metric-balance`, `metric-unrealized-pnl`, etc.) for the 2-col test to actually exercise the metric cells (per CR-02). Currently only the outer wrapper has a testid — every assertion below the wrapper level walks `children` arrays and tolerates structure changes silently.
**Fix:** Add `data-testid={`metric-${kebabCase(eyebrow)}`}` (or accept an explicit `testid` prop) on the Cell wrapper. Coordinate with Plan 7-03 testid contract — phase the change in 14-follow-up rather than now if Phase 7 invariants need re-stating.

### IN-03: `TournamentFilterChips.jsx` chips have no focus-visible style for keyboard users

**File:** `frontend/src/components/TournamentFilterChips.jsx:180-202, 211-233, 254-277, 280-303`
**Issue:** The Clear button (line 280) shows an `X` lucide icon plus the text "Clear filters". Screen readers will read "Clear filters" — acceptable. But the focus state has no visible focus ring (no `focus-visible` Tailwind utility, no inline `:focus-visible` style). Keyboard-only users will lose the active element. The chip and segment buttons have the same gap. Phase 14 added touch-target compliance (44px) but did not add focus-visible compliance, even though they're adjacent WCAG axes.
**Fix:** Add `focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-400` (or palette-matching color) to all interactive chip/segment classNames. Consider a sibling Phase for WCAG focus-visible audit if out of 14 scope.

### IN-04: Magic string `'unknown'` for missing run_id is not extracted to a constant

**File:** `frontend/src/pages/TournamentDashboard.jsx:366`, `frontend/src/components/TournamentLeaderboard.jsx:361`
**Issue:** The string `'unknown'` is hardcoded in two places (related to CR-03). Even after the duplicate-collision fix, the constant should be named (`MISSING_RUN_ID_PLACEHOLDER` or similar) and shared, so the dual-render contract that requires the two branches to agree is enforced by the type system rather than visual diff.
**Fix:** Extract to a shared constant in a module both files can import; alternatively, derive the testid via a helper `rowTestid(row, idx)` that both branches consume.

### IN-05: Plan 14-03 acknowledges Task 1 verify-block plan-author bug but did not patch it

**File:** N/A — process artifact in `14-03-SUMMARY.md` decisions §4
**Issue:** SUMMARY documents that the Task 1 `<verify>` shell chain short-circuits because `grep -c data-testid Dashboard.jsx` exits 1 (zero matches → exit 1 per grep semantics, even though "0" is the correct count). The fix was punted to "Phase 14 retrospective" rather than landed in this phase. This is process-debt, not source code, but it surfaces in code review because the same broken verify pattern may exist in other phases' plans and silently pass.
**Fix:** Audit `<verify>` blocks across all Phase 14 plans (and prior phases that use similar grep-chain verifies) for the same `grep -c | && ...` pattern; switch to explicit `[ "$(grep -c PATTERN FILE)" -ge N ]` comparisons that don't conflate "count = 0" with "command failed."

---

_Reviewed: 2026-05-22T22:55:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_

---

## Fix Log

**Fix iteration:** 1
**Fixed at:** 2026-05-22T23:30:00Z
**Fixer:** Claude (gsd-code-fixer, auto mode)
**Scope:** Critical + Warning per task; Info severity skipped per task scope.

### Fixed

| ID    | Severity | Commit    | Files changed                                                                                  | Rationale (one-line) |
|-------|----------|-----------|------------------------------------------------------------------------------------------------|----------------------|
| CR-01 | Critical | `a50c5a3` | `.github/workflows/dashboard-smoke.yml`, `frontend/Dockerfile`                                 | Add `npm ci && npm run build` step before `bootstrap.sh`; multi-stage Dockerfile (node:20-alpine -> nginx:alpine) eliminates host-side `dist/` dependency. |
| CR-02 | Critical | `be48ad9` | `frontend/src/components/KeyMetricsStrip.jsx`                                                  | Drop `display:contents` wrapper; move `data-testid="key-metrics-strip"` to the real layout box (inner div). Add per-Cell `data-testid={\`metric-${slug}\`}` so tests query real metric cells. |
| CR-03 | Critical | `3f6677c` | `frontend/src/pages/TournamentDashboard.jsx`, `frontend/src/components/TournamentLeaderboard.jsx` | Thread `idx` through `.map()`; coalesce missing `run_id` to `unknown-${idx}` instead of literal `'unknown'`. Both branches mirrored for dual-render parity. |
| WR-01 | Warning  | `33bb35b` | `frontend/src/pages/TournamentDashboard.jsx`                                                   | Mobile card now renders 14 fields (was 7) — `target_mode`, `dir_acc_corrected`, `r2_returns`, `__significance` (inline `<SignificanceBadge>`), `train_seconds`, and a colored `failure_reason` block. Restores CONTEXT.md "zero information loss" invariant. |
| WR-02 | Warning  | `b4552a2` | `scripts/audit_responsive.py`                                                                  | Emit `audit_responsive: WARN ...` to stderr when allowlist JSON fails to parse, instead of silently degrading to empty allowlist. |
| WR-03 | Warning  | `e2a9232` | `scripts/audit_responsive.py`                                                                  | Add `isinstance(raw, list)` root-type guard with stderr WARN when allowlist root is not a list. |
| WR-04 | Warning  | `4c889d9` | `tests/integration/test_no_mobile_hidden_data.py`                                              | Wrap `_load_allowlist` in try/except + `isinstance(entries, list)` + per-entry `isinstance(e, dict)`. Mirrors `audit_responsive.py`'s graceful-degrade shape. |
| WR-05 | Warning  | `3de2dc8` | `tests/e2e/test_responsive_dashboard.py`                                                       | Remove inverted-direction substring checks (`f"data-testid='...'" in sel`, `f"href='...'" in sel`); only forward `sel in hint` direction remains. Closes cross-allowlist surface. |
| WR-06 | Warning  | `772d5b0` | `scripts/audit_responsive.py`                                                                  | Validate `--out` resolves inside `REPO_ROOT` via `parser.error` to prevent path traversal / arbitrary-file overwrite. |
| WR-07 | Warning  | `5621109` | `scripts/audit_responsive.py`                                                                  | Delete dead `_SELF_PATH` constant + dead `if rel == _SELF_PATH: continue` branch (cargo-cult from `audit_bybit_bypass.py`; structurally unreachable in JSX-only walker). |

### Deferred

| ID    | Severity | Reason for deferral |
|-------|----------|---------------------|
| WR-08 | Warning  | Documented carry-in (OP-04 / INFRA-02 fixture coupling); explicitly skipped per task scope. Once a `vite_preview_server` fixture is introduced in a future phase, the layout-only subset of `test_responsive_dashboard.py` can be split off from `bootstrap_stack`. Net effect of CR-01 is that the existing `bootstrap_stack` lane DOES now exercise the real Phase 14 bundle, partially mitigating this warning. |
| IN-01 | Info     | Severity: info — out of scope per task. |
| IN-02 | Info     | Severity: info — but materially resolved as a side-effect of CR-02 (per-Cell `metric-*` testids now exist). |
| IN-03 | Info     | Severity: info — out of scope per task. Focus-visible WCAG axis is a sibling concern. |
| IN-04 | Info     | Severity: info — out of scope per task. Magic string `'unknown'` is now `unknown-${idx}` at both sites (CR-03); extraction-to-constant remains an open polish item. |
| IN-05 | Info     | Severity: info — process artifact in `14-03-SUMMARY.md`, not source code. |

### Out-of-scope side notes from this run

- **Semgrep CWE-250 on `frontend/Dockerfile`** — the post-write security scanner flagged that nginx runs as root in the new multi-stage Dockerfile. Pre-existing condition (the original single-stage Dockerfile also lacked `USER`); not part of CR-01's stale-bundle finding. Recommend a separate container-hardening pass (likely `nginxinc/nginx-unprivileged:alpine` + listen 8080 + compose port-mapping change).

_Fix iteration: 1_
_Status: clean (all in-scope Critical + Warning fixed; WR-08 documented-skip, all Info out-of-scope per task)_
