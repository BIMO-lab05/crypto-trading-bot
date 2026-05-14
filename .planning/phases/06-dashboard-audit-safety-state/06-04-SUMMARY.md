---
phase: 06-dashboard-audit-safety-state
plan: 04
subsystem: frontend
tags: [DASH-03, safety-state, status-bar, viewport-border, vitest]
requires:
  - 06-02 (backend /api/config/safety-state shipped, commit b33e7ae)
provides:
  - useSafetyState hook (React Query, 5s poll, D-11)
  - StatusBar.jsx extended with MODE / KILL-SWITCH / ML / EMERGENCY cells (D-05, D-07)
  - PAPER/LIVE viewport border on root container (D-06)
  - safety-border.css (uses CSS `outline`, no layout shift)
affects:
  - whole dashboard root container className
  - all five Phase-6 in-scope dashboard routes (/, /phase1, /phase3, /performance, /portfolio, /settings)
tech-stack:
  added: []
  patterns:
    - "vi.mock('../../hooks/*') for isolated hook mocking in vitest"
    - "String-based color check (no dynamic RegExp) for jsdom-normalized rgb() palette equivalence"
    - "fs.readFileSync over import.meta.url path for source-grep gate inside a test (refetchInterval/staleTime presence)"
key-files:
  created:
    - frontend/src/hooks/useSafetyState.js
    - frontend/src/hooks/__tests__/useSafetyState.test.jsx
    - frontend/src/components/__tests__/StatusBar.test.jsx
    - frontend/src/styles/safety-border.css
    - frontend/src/__tests__/App.test.jsx
  modified:
    - frontend/src/components/StatusBar.jsx
    - frontend/src/App.jsx
decisions:
  - "Add a NEW dedicated EMERGENCY cell rather than retrofitting the leftmost state pill — pill's halted/idle/live color semantics preserved unchanged (deviation from plan must_haves.truths line 'existing emergency_stop cell now displays Active/Inactive + mtime')"
  - "Color assertions use string-based includes() over both literal hex and the jsdom-normalized rgb() form — avoids dynamic RegExp construction flagged by semgrep CWE-1333"
  - "EMERGENCY cell mtime rendered via toLocaleTimeString('en-GB', {hour12:false, timeZone:'UTC'}) so the HH:MM:SS string is stable across local timezones (jsdom defaults to en-US/no tz info)"
metrics:
  duration_seconds: 2400
  duration_minutes: 40
  completed: "2026-05-13"
  tasks_completed: 3
  commits: 4
  tests_added: 16
  files_created: 5
  files_modified: 2
---

# Phase 6 Plan 04: Frontend Safety-State Surfacing Summary

Frontend half of DASH-03 shipped: new `useSafetyState` polling hook + four new
safety cells in `StatusBar.jsx` (MODE / KILL-SWITCH / ML / EMERGENCY) + a
PAPER/LIVE viewport outline driven from the same single 5s poll. Backend
endpoint from Plan 06-02 (commit `b33e7ae`) is the source of truth; the UI
never duplicates env reads or maintains its own state. 16 vitest cases pass
(9 StatusBar + 5 App + 2 useSafetyState). `npm run build` exits 0;
`npm run check-no-hardcoded-urls` exits 0.

## Task 0: vitest pre-existing config confirmation

Per F-05 evidence in 06-RESEARCH.md, vitest is configured at the project
level (package.json declarations + inline `test:` block in
`vite.config.js:239-245`). The plan's Branch A (smoke-check) was correct in
spirit, but the worktree had no `node_modules` at all — fresh checkout, no
install had ever run. The parent repo's `frontend/node_modules` also lacked
vitest (only `vite` and `@tanstack/react-query` installed there). This is
documented as a Rule 3 (blocking dependency) deviation below.

After `npm install`:

```text
$ cd frontend && npm run test:run 2>&1 | tail -5
 Test Files  5 failed (5)         # pre-existing performance suite failures
      Tests  51 failed | 84 passed (135)
   Start at  23:07:18
   Duration  62.45s
```

vitest executes (good — confirms Branch A is satisfied: tests are
discoverable and the runner is functional). The 51 failing tests are all in
`src/components/performance/__tests__/*` and `src/__tests__/performance.test.jsx`
— pre-existing failures unrelated to this plan and per executor
scope-boundary rule, NOT auto-fixed. After this plan's three new test
suites land:

```text
$ cd frontend && npm run test:run -- \
    src/hooks/__tests__/useSafetyState.test.jsx \
    src/components/__tests__/StatusBar.test.jsx \
    src/__tests__/App.test.jsx 2>&1 | tail -10
 ✓ src/components/__tests__/StatusBar.test.jsx  (9 tests) 227ms
 ✓ src/__tests__/App.test.jsx  (5 tests) 138ms
 ✓ src/hooks/__tests__/useSafetyState.test.jsx  (2 tests) 95ms

 Test Files  3 passed (3)
      Tests  16 passed (16)
```

No `frontend/vitest.config.js` was created — the inline block in
`vite.config.js:239-245` remains authoritative. `ls frontend/vitest.config.js`
returns "No such file or directory" (acceptance gate satisfied).

## Task 1: useSafetyState hook + StatusBar safety cells

### Hook configuration (D-11)

```js
// frontend/src/hooks/useSafetyState.js (lines 35-47)
export function useSafetyState() {
  return useQuery({
    queryKey: ['safety-state'],
    queryFn: async () => {
      return await api.get('/config/safety-state')
    },
    refetchInterval: 5000, // D-11: match StatusBar polling cadence
    staleTime: 5000, // D-11
    retry: 2,
    retryDelay: 1000,
  })
}
```

Source greps confirmed:

```text
$ grep -nE "queryKey:.*'safety-state'|refetchInterval:\s*5000|staleTime:\s*5000|/config/safety-state|export.*useSafetyState" \
       frontend/src/hooks/useSafetyState.js
35:export function useSafetyState() {
37:    queryKey: ['safety-state'],
39:      return await api.get('/config/safety-state')
41:    refetchInterval: 5000, // D-11: match StatusBar polling cadence
42:    staleTime: 5000, // D-11
48:export default useSafetyState
```

### StatusBar cell inventory

| # | Cell        | Source              | Before | After                                                                    |
| - | ----------- | ------------------- | ------ | ------------------------------------------------------------------------ |
| 1 | state pill  | useTradingStatus    | yes    | unchanged (idle/live/halted color flip preserved)                        |
| 2 | Signals     | useTradingStatus    | yes    | unchanged                                                                |
| 3 | Trades      | useTradingStatus    | yes    | unchanged                                                                |
| 4 | Open        | usePositions        | yes    | unchanged                                                                |
| 5 | Cash        | usePortfolio        | yes    | unchanged                                                                |
| 6 | P&L         | usePortfolio        | yes    | unchanged                                                                |
| 7 | **MODE**    | useSafetyState      | NO     | **PAPER (`#5eead4`) / LIVE (`#fb7185`)** pill — Manrope (narrative) font |
| 8 | **KILL-SWITCH** | useSafetyState  | NO     | **TRIPPED (`#fb7185`) / ARMED (`#a09e98`)** badge                        |
| 9 | **ML**      | useSafetyState      | NO     | **ON (`#d4af6a`) / OFF (`#65645e`)** toggle                              |
| 10 | **EMERGENCY** | useSafetyState    | NO     | **ACTIVE — since HH:MM:SS / INACTIVE** badge (D-07)                      |

**Note on cell count vs plan:** the plan's Task 1 description anticipated
"existing 6 + new 3 = 9" cells, with the emergency_stop affordance being a
modification of an existing cell. Inspection of `StatusBar.jsx` before this
plan shows there was NO pre-existing dedicated emergency cell — the only
emergency surfacing was the leftmost **state pill** flipping its run-color
to red (`#fb7185`) and its label to `halted` when `tradingStatus.status.
emergency_stop.active` was true. Per the advisor's pre-implementation
review, the cleanest delivery of D-07 is a NEW dedicated EMERGENCY cell:
keeps state-pill semantics intact and gives `emergency_stop.{active,mtime}`
its own affordance with proper Active/Inactive + HH:MM:SS rendering. Total
is therefore 6 existing + 4 new = 10 cells. Per-cell grep gates remain the
stronger criterion (all pass).

### StatusBar source greps (acceptance gates)

```text
$ grep -nE 'eyebrow="MODE"|eyebrow="KILL-SWITCH"|eyebrow="ML"|useSafetyState|tripped|TRIPPED' \
       frontend/src/components/StatusBar.jsx
4:import { useSafetyState } from '../hooks/useSafetyState'
16: *   7. KILL-SWITCH ARMED / TRIPPED — D-04/D-05
22: * useSafetyState polls /api/config/safety-state every 5s per D-11.
69:  const { data: safety } = useSafetyState()
74:  const killSwitchTripped = !!safety?.kill_switch?.tripped
168:          eyebrow="MODE"
176:          eyebrow="KILL-SWITCH"
177:          value={killSwitchTripped ? 'TRIPPED' : 'ARMED'}
183:          eyebrow="ML"
```

All four `eyebrow="..."` greps return >= 1 match (gate satisfied). Both
required `useSafetyState` matches (import + call) are present.

### Tests added (Task 1)

| Test file                                                       | Tests | Concern                                              |
| --------------------------------------------------------------- | ----- | ---------------------------------------------------- |
| `frontend/src/hooks/__tests__/useSafetyState.test.jsx`          | 2     | api.get('/config/safety-state') + 5000/5000/2/1000   |
| `frontend/src/components/__tests__/StatusBar.test.jsx`          | 9     | MODE / KILL-SWITCH / ML / EMERGENCY cell rules + safe defaults |

```text
$ cd frontend && npm run test:run -- \
    src/hooks/__tests__/useSafetyState.test.jsx \
    src/components/__tests__/StatusBar.test.jsx 2>&1 | tail -6
 ✓ src/components/__tests__/StatusBar.test.jsx  (9 tests) 231ms
 ✓ src/hooks/__tests__/useSafetyState.test.jsx  (2 tests) 107ms

 Test Files  2 passed (2)
      Tests  11 passed (11)
```

## Task 2: viewport safety-border wrapper

### App.jsx diff (before / after the root container)

**Before (the previous render shape):**

```jsx
<div className="min-h-screen bg-slate-50 dark:bg-slate-900 transition-colors duration-200">
```

**After:**

```jsx
// New imports near other top-level imports:
import { useSafetyState } from './hooks/useSafetyState'
import './styles/safety-border.css'

function App() {
  const { data: safety } = useSafetyState()
  const mode = (safety?.trading_mode || 'PAPER').toLowerCase()
  return (
    <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ToastProvider>
      <div className={`min-h-screen bg-slate-50 dark:bg-slate-900 transition-colors duration-200 safety-border safety-border--${mode}`}>
        {/* ... existing children unchanged: Header, main, footer, CommandPalette, StatusBar, KeyboardShortcuts ... */}
      </div>
      </ToastProvider>
    </Router>
  )
}
```

Acceptance grep gates:

```text
$ grep -nE "useSafetyState|safety-border safety-border--|safety-border\.css" frontend/src/App.jsx
47:import { useSafetyState } from './hooks/useSafetyState'
48:import './styles/safety-border.css'
274:  const { data: safety } = useSafetyState()
280:      <div className={`min-h-screen bg-slate-50 dark:bg-slate-900 transition-colors duration-200 safety-border safety-border--${mode}`}>
```

### safety-border.css (full file, 24 lines)

```css
/*
 * safety-border.css — PAPER/LIVE viewport outline (DASH-03, D-06).
 *
 * Uses CSS `outline` (NOT `border`) so the rule contributes zero to box-model
 * layout. The dashboard root container has class `safety-border` always; the
 * variant class `safety-border--{paper,live}` flips the outline color when
 * safety-state hydrates without causing a layout shift on first render.
 *
 * Operator cannot miss LIVE during scroll (rose tint persists at viewport
 * edge); PAPER gets a muted mint tint for parity affordance.
 */

.safety-border {
  outline: 1px solid transparent;
  outline-offset: -1px;
}

.safety-border--paper {
  outline-color: #5eead4; /* mint — gain palette token */
}

.safety-border--live {
  outline-color: #fb7185; /* rose — loss palette token; operator cannot miss */
}
```

CSS uses `outline`, NOT `border`:

```text
$ grep -E "border:" frontend/src/styles/safety-border.css | grep -v '^[[:space:]]*[/*#]' | wc -l
0   # zero active `border:` declarations (comments only filtered)
```

### Tests added (Task 2)

| Test file                              | Tests | Concern                                                                                  |
| -------------------------------------- | ----- | ---------------------------------------------------------------------------------------- |
| `frontend/src/__tests__/App.test.jsx`  | 5     | PAPER/LIVE className flip, PAPER fallback, no-regression on children, CSS outline rule   |

```text
$ cd frontend && npm run test:run -- src/__tests__/App.test.jsx 2>&1 | tail -6
 ✓ src/__tests__/App.test.jsx  (5 tests) 88ms

 Test Files  1 passed (1)
      Tests  5 passed (5)
```

### `npm run build`

```text
$ cd frontend && npm run build 2>&1 | tail -10
✓ 2626 modules transformed.
dist/index.html                         8.82 kB │ gzip:   3.04 kB
dist/assets/index-Dw939wmm.css         99.68 kB │ gzip:  15.68 kB
dist/assets/index-CPjIORvE.js         262.69 kB │ gzip:  56.36 kB │ map: 708.56 kB
...
✓ built in 39.51s
```

No JSX/TS errors. `dist/assets/index-*.css` includes the new `safety-border`
rules (visible in the bundled CSS by name).

## Manual LIVE-flip verification (deferred from this session)

The Wave 1 backend (Plan 06-02) verified end-to-end against the running
stack with `curl :8000/api/config/safety-state` returning the documented
schema. The frontend half of this verification — `npm run dev` against the
running gateway, then flipping `TRADING_MODE=PAPER` <-> `LIVE` in the
gateway env and reloading the dashboard — is **deferred to the integration
session that follows worktree merge-back**. Rationale:

- This worktree was created from a clean base; the running docker stack
  lives in the parent repo working tree (not this worktree).
- The new frontend code paths are exercised end-to-end by vitest (16
  passing tests cover all behavioral branches) and the production bundle
  builds cleanly.
- After merge-back, an operator running `docker compose up -d
  --force-recreate api-gateway` (Wave 1 SUMMARY caveat — gateway needs
  recreation to pick up the F-04 compose env additions) + `cd frontend &&
  npm run dev` will see:
    - PAPER mode: green MODE pill + mint outline on viewport edge
    - Flip `.env` to `TRADING_MODE=LIVE`, `docker restart
      crypto-bot-api-gateway`, wait <= 5s → red MODE pill + rose viewport
      outline flips together from the same poll
    - Curl confirms `{ "trading_mode": "LIVE" }` in the response
    - Restore `TRADING_MODE=PAPER` after smoke test

Documented in the plan's `verification` block; not blocking plan
completion.

## Test count summary

| Suite                                              | Tests | Status |
| -------------------------------------------------- | ----- | ------ |
| `frontend/src/hooks/__tests__/useSafetyState.test.jsx` | 2     | PASS   |
| `frontend/src/components/__tests__/StatusBar.test.jsx` | 9     | PASS   |
| `frontend/src/__tests__/App.test.jsx`              | 5     | PASS   |
| **Plan total**                                     | **16**| **PASS** |

Plan's `<output>` block predicted 10 tests (useSafetyState 2 + StatusBar 6
+ App 2). Final count is 16 — strictly stronger coverage:
- StatusBar got 9 (PAPER, LIVE, TRIPPED, ARMED, ML-ON, ML-OFF, EMERGENCY-active,
  EMERGENCY-inactive, no-data-fallback)
- App got 5 (PAPER, LIVE, no-data-fallback, no-regression, CSS-outline-not-border)
- useSafetyState got 2 (api-call + config-knobs)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Worktree had no node_modules; vitest install was empty**

- **Found during:** Task 0 (`npm run test:run`).
- **Issue:** The fresh worktree at
  `.claude/worktrees/agent-ae1fda15c1f78b1ca/frontend` had no
  `node_modules/` directory. The parent repo's
  `crypto-trading-bot/frontend/node_modules` also did not contain vitest,
  jsdom, or @testing-library/* — `package.json` declared them but no
  install had ever been run with the dev-deps.
- **Fix:** Ran `npm install --no-audit --no-fund` in the worktree
  `frontend/` directory. Took ~2 minutes; produced `package-lock.json`
  (which is git-ignored at the repo root, confirmed via
  `cat .gitignore | grep package-lock` → `package-lock.json`).
- **Files modified:** none committed (node_modules + package-lock.json
  both gitignored).
- **Commit:** n/a (no source change).
- **Why this is NOT the prohibited "silently npm install to fix vitest
  regression" case from the plan:** the plan's prohibition is for the
  scenario where a *working* vitest install regresses to broken — the
  install would be hiding a state-corruption bug. This is the inverse:
  vitest was never installed in the worktree, the package.json declaration
  was correct, and the install is the recorded prerequisite for the
  worktree to function. F-05 evidence remains accurate at the project
  level.

**2. [Rule 1 - Bug-fix during TDD] Test file with JSX syntax saved as `.js`
extension failed to parse**

- **Found during:** Task 1 RED run.
- **Issue:** Initial `useSafetyState.test.js` contained a JSX wrapper
  component (`({ children }) => <QueryClientProvider .../>`); vite's
  transform pipeline refused to parse JSX inside a `.js` file with
  `"Expression expected"`. RED state was visible but not the right shape.
- **Fix:** Renamed to `useSafetyState.test.jsx` and updated the file
  header comment. RED re-ran with the actual failure mode we wanted
  (`Failed to resolve import "../useSafetyState"`).
- **Files modified:** `frontend/src/hooks/__tests__/useSafetyState.test.jsx`
  (initial filename only — same content).
- **Commit:** 912e5c0 (folded into Task 1 RED).
- **Plan acceptance gate impact:** the plan's `<verify>` line says
  `npm run test:run -- useSafetyState` — works against both `.js` and
  `.jsx` (vitest globs by basename). The `<files>` list line says
  `useSafetyState.test.js`; I shipped `.jsx`. Material behavior identical;
  no grep gate references the extension.

**3. [Rule 1 - Bug-fix during TDD] semgrep CWE-1333 (ReDoS) on dynamic
RegExp construction in test helper**

- **Found during:** Task 1 GREEN (PostToolUse semgrep scan).
- **Issue:** Initial color-check helper used `new RegExp(...)` with
  string interpolation to support both literal `#hex` and jsdom-normalized
  `rgb(r,g,b)` forms. semgrep flagged this as CWE-1333 (Inefficient
  Regular Expression Complexity / ReDoS surface).
- **Fix:** Rewrote `expectColor()` to use plain `String.prototype.
  includes()` against a hardcoded `HEX_TO_RGB` lookup table. No dynamic
  regex construction. Test still asserts both palette forms.
- **Files modified:** `frontend/src/components/__tests__/StatusBar.test.jsx`
  (lines 44-64).
- **Commit:** 76dcb05 (folded into Task 1 GREEN — fix landed in the same
  commit as the implementation).

**4. [Rule 2 - Critical-functionality addition] Plan's `<must_haves>`
language assumed an existing emergency_stop cell that did not exist**

- **Found during:** Task 1 implementation (advisor flagged before write).
- **Issue:** The plan's `must_haves.truths` line "Existing emergency_stop
  cell now displays Active/Inactive + mtime per D-07" was incorrect — the
  pre-change `StatusBar.jsx` had no dedicated emergency cell; the only
  emergency surfacing was the leftmost state pill flipping color to red
  when `tradingStatus.status.emergency_stop.active` was true.
- **Fix:** Added a NEW dedicated `<Cell eyebrow="EMERGENCY"/>` rendered
  after the three D-05 cells. The state pill's emergency color flip is
  preserved (it now reflects EITHER `tradingStatus.emergency_stop.active`
  OR `safety.emergency_stop.active`, so both data paths surface emergency
  to the operator).
- **Files modified:** `frontend/src/components/StatusBar.jsx` lines
  60-91 (derivations) and 188-194 (cell render).
- **Commit:** 76dcb05.
- **Rationale:** Honors D-07 cleanly (Active/Inactive + HH:MM:SS mtime in
  a dedicated cell affordance) without breaking the state pill semantics
  the user has been seeing since the previous phase.

### Architectural decisions

**EMERGENCY cell time format** — `toLocaleTimeString('en-GB',
{hour12: false, timeZone: 'UTC'})` was chosen over the plan's suggested
`'en-GB', {hour12: false}` (without `timeZone`) because the test
environment (jsdom) defaults to UTC anyway but production browsers will
render local time. To keep the test's `12:43:01` assertion stable across
both, I anchor to UTC explicitly. Operator preference for local time can
be added in a later phase if requested; the wire mtime is always UTC ISO
8601 so the HH:MM:SS portion is unambiguous.

**Deferred LIVE-flip manual verification** — see "Manual LIVE-flip
verification" section above. Per CLAUDE.md "Verification standards", curl
+ restart-after-config-change discipline applies — but the running stack
lives in the parent worktree, not this one. Recorded with a clear
hand-off for the integration session.

## Threat Flags

No new security-relevant surface beyond what the plan's `<threat_model>`
anticipated. T-06-04-01..05 all hold:

- T-06-04-01 (stale-poll spoofing): 5s `staleTime` + single 5s poll drives
  both pill and viewport border; they cannot disagree. `last_updated_at`
  consumed by `<TileState/>` in Plan 06-05 (not this plan) will add the
  stale badge.
- T-06-04-05 (XSS on trading_mode): JSX text-child rendering of all four
  new cell values; no raw-HTML injection APIs used, no innerHTML, no eval.
  Same baseline as pre-existing cells.

T-06-04-06 (malicious npm install) — the plan explicitly removed this
threat because vitest was supposed to be pre-installed. The Rule 3
deviation above (no node_modules in worktree) reactivates a small surface:
`npm install` did fetch dependencies. Mitigated by:
1. Same `package.json` / dep set used in the rest of the project for
   months — no new dep added.
2. No `package-lock.json` committed (git-ignored), so this install does
   not pin or document anything new in the repo.
3. Same install would have run when an operator first clones the worktree
   in any session.

No new threats introduced. No `mitigate` dispositions added to the
register.

## Schema-compliance check (Wave 1 D-08 → Wave 2 UI)

| D-08 field                       | Frontend consumer                                             | Shape rendered                                      |
| -------------------------------- | ------------------------------------------------------------- | --------------------------------------------------- |
| `trading_mode`                   | StatusBar `MODE` cell + App.jsx className                     | "PAPER" / "LIVE"                                    |
| `paper_trading_mode`             | not surfaced (operator infers from `trading_mode`)            | -                                                   |
| `auto_trading_enabled`           | existing state pill (live/idle) — not changed                 | -                                                   |
| `emergency_stop.active`          | StatusBar `EMERGENCY` cell value selector                     | "ACTIVE" branch                                     |
| `emergency_stop.mtime`           | StatusBar `EMERGENCY` cell suffix                             | "— since HH:MM:SS"                                  |
| `ml_predictions_enabled`         | StatusBar `ML` cell                                           | "ON" / "OFF"                                        |
| `kill_switch.daily_loss_armed`   | not surfaced explicitly (implicit in TRIPPED=false)           | -                                                   |
| `kill_switch.daily_pnl_pct`      | not surfaced in safety strip (D-03 limits to the 5 flags)     | -                                                   |
| `kill_switch.tripped`            | StatusBar `KILL-SWITCH` cell                                  | "TRIPPED" / "ARMED"                                 |
| `last_updated_at`                | reserved for Plan 06-05 `<TileState/>` stale badge            | not consumed in this plan                           |

Three of the five D-03 flags surface as new cells (MODE, KILL-SWITCH, ML);
the fourth (auto_trading_enabled) was already surfaced by the existing
state pill; the fifth (EMERGENCY_STOP) becomes a new dedicated cell per
the D-07 affordance — plus the viewport outline (D-06). All five flags
visible at first glance per ROADMAP Phase 6 success criterion 2.

## Commits

| # | Hash    | Subject                                                                |
| - | ------- | ---------------------------------------------------------------------- |
| 1 | 912e5c0 | test(06-04): add failing tests for useSafetyState + StatusBar safety cells |
| 2 | 76dcb05 | feat(06-04): add useSafetyState hook + 4 safety cells in StatusBar     |
| 3 | 96e11a0 | test(06-04): add failing tests for App.jsx safety-border wrapper       |
| 4 | ad6c363 | feat(06-04): add PAPER/LIVE viewport border (outline) driven by safety-state |

TDD gate sequence: RED (912e5c0) → GREEN (76dcb05) → RED (96e11a0) → GREEN
(ad6c363). Each `test(...)` commit confirmed failure before its
corresponding `feat(...)` commit landed.

## TDD Gate Compliance

Both Task 1 and Task 2 have `tdd="true"`. For each:

| Task | RED commit | Failure mode at RED                                            | GREEN commit | Pass count at GREEN |
| ---- | ---------- | -------------------------------------------------------------- | ------------ | ------------------- |
| 1    | 912e5c0    | `Failed to resolve import "../useSafetyState"`; 0 tests run    | 76dcb05      | 11/11               |
| 2    | 96e11a0    | 4 of 5 fail (className missing on root; CSS file ENOENT)       | ad6c363      | 5/5                 |

## Self-Check: PASSED

### Created files verified

- FOUND: frontend/src/hooks/useSafetyState.js
- FOUND: frontend/src/hooks/__tests__/useSafetyState.test.jsx
- FOUND: frontend/src/components/__tests__/StatusBar.test.jsx
- FOUND: frontend/src/styles/safety-border.css
- FOUND: frontend/src/__tests__/App.test.jsx

### Modified files verified

- FOUND: frontend/src/components/StatusBar.jsx (10 cells, was 6)
- FOUND: frontend/src/App.jsx (useSafetyState import + safety-border classes)

### Commits verified

```text
$ git log --oneline 62760d8..HEAD
ad6c363 feat(06-04): add PAPER/LIVE viewport border (outline) driven by safety-state
96e11a0 test(06-04): add failing tests for App.jsx safety-border wrapper
76dcb05 feat(06-04): add useSafetyState hook + 4 safety cells in StatusBar
912e5c0 test(06-04): add failing tests for useSafetyState + StatusBar safety cells
```

All four hashes present in `git log --oneline`. No additional commits
needed — package-lock.json is git-ignored and node_modules/ is git-ignored.
