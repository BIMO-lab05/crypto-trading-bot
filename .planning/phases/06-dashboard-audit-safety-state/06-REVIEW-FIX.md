---
phase: 06-dashboard-audit-safety-state
fixed_at: 2026-05-14T01:55:00Z
review_path: .planning/phases/06-dashboard-audit-safety-state/06-REVIEW.md
iteration: 1
findings_in_scope: 8
fixed: 8
skipped: 0
status: all_fixed
---

# Phase 6: Code Review Fix Report

**Fixed at:** 2026-05-14T01:55:00Z
**Source review:** `.planning/phases/06-dashboard-audit-safety-state/06-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 8 (1 BLOCKER + 7 WARNING; 4 Info findings deliberately excluded)
- Fixed: 8
- Skipped: 0

**Verification cadence per fix:**
- JS/JSX: re-read modified region + `npx vitest run` (scoped); production `npm run build` and `npm run check-no-hardcoded-urls` re-run after WR-04 batch
- Python: `python3 -c 'import ast; ast.parse(...)'` syntax check + targeted `pytest` where a test file existed
- Shell: `bash -n` syntax check + scenario-based regression runs (5 cases for WR-07)

## Fixed Issues

### CR-01 [BLOCKER]: Operator-precedence bug renders alignment-score % wrong (off by 100x)

**Files modified:** `frontend/src/pages/Phase3Dashboard.jsx`
**Commit:** `7708d3e`
**Applied fix:** Parenthesized the `??` chain explicitly so `* 100` applies to whichever operand actually feeds `.toFixed(0)`:

```jsx
- ? `${(enhancedSignal.metadata?.multi_timeframe?.alignment_score ??
-      enhancedSignal.components?.mtf?.alignment_score * 100).toFixed(0)}%`
+ ? `${(((enhancedSignal.metadata?.multi_timeframe?.alignment_score ??
+        enhancedSignal.components?.mtf?.alignment_score)) * 100).toFixed(0)}%`
```

Pre-existing bug; not a Phase 6 regression but file was in review scope.

**Verification notes:** This is a pure rendering-math fix with no targeted unit test in the codebase. JS parsing rules (`*` binds tighter than `??`) confirm the new expression evaluates as intended: `(a ?? b)` resolves first, then `* 100`. Marked as **fixed: requires human verification** — operator should spot-check the Phase 3 dashboard alignment-score tile when the safety endpoint reports a non-null `metadata.multi_timeframe.alignment_score` to confirm the percent renders as e.g. `85%` rather than `1%`.

### WR-01: Unbounded `_alerts` list growth amplified by Phase 6 5s poll cadence

**Files modified:** `services/trading-engine/app/risk/dynamic_risk_budget.py`
**Commit:** `54a6492`
**Applied fix:** Two edits in the same file:

1. Convert `self._alerts: List[RiskBudgetAlert] = []` to `self._alerts: deque = deque(maxlen=500)`.
2. Wrap the slice site in `get_alerts()` at line ~1383 with `list(...)`: `for alert in list(self._alerts)[-limit:]` because deque does NOT support slice indexing (the advisor's catch — the reviewer's suggested fix had a runtime bug here).

`.append()` calls at lines ~1149, 1327, 1338, 1351 and `.clear()` at line ~1555 are deque-native and unchanged.

**Verification notes:** Confirmed deque semantics empirically:
- `deque(maxlen=500)` caps at 500 after 1000 appends.
- `list(d)[-N:]` returns the most-recent N items.
- Raw `d[-N:]` raises `TypeError` (which is exactly what the reviewer's naive suggestion would have triggered every time `/api/v1/risk/budget/alerts` was hit).

No existing pytest covers `get_alerts()` directly, so this slice-site verification is empirical rather than test-driven.

### WR-02: `asyncio.get_event_loop().run_until_complete()` deprecated on Python 3.12

**Files modified:** `services/trading-engine/tests/test_health_status.py`
**Commit:** `16184aa`
**Applied fix:** Replaced `asyncio.get_event_loop().run_until_complete(coro)` with `asyncio.run(coro)` in the `_run()` helper. The helper is called once per test from sync test bodies — no loop reuse to preserve.

**Verification notes:** Python syntax check passes. The deprecation warning was the only concern; behavior is equivalent for the one-coro-per-call usage pattern.

### WR-03: TileState `forceStale` ignores `isFetching` — refresh has no spinner affordance

**Files modified:** `frontend/src/components/TileState.jsx`
**Commit:** `0f4634d`
**Applied fix:** Gated `showStale` on `!query?.isFetching`:

```jsx
- const showStale =
-   Boolean(forceStale) ||
-   isStaleByTimestamp(lastUpdatedAt, effectiveStaleAfterMs)
+ const showStale =
+   !query?.isFetching &&
+   (
+     Boolean(forceStale) ||
+     isStaleByTimestamp(lastUpdatedAt, effectiveStaleAfterMs)
+   )
```

The stale badge now transiently disappears while a refetch is in flight and re-asserts after success if `forceStale` or the timestamp threshold still applies. Errors-loud precedence (F-05) preserved — branch 1 (`isError`) still fires before this code runs.

**Verification notes:** All 12 existing TileState tests still pass. The existing test fixtures use `makeQuery` with default `isFetching: false`, so this gate does not affect those scenarios.

### WR-04: Two components bypass the configured axios client

**Files modified:** `frontend/src/components/TradeHistory.jsx`, `frontend/src/components/PerformanceAnalyticsPanel.jsx`
**Commit:** `8abbcd8`
**Applied fix:** Two edits per file (per advisor's catch — the reviewer's snippet missed one):

1. Replace `axios.get('/api/trading/trades/history', ...)` with `api.get('/trading/trades/history', ...)`. Note path now omits the `/api/` prefix because the shared client carries `baseURL: '/api'`.
2. Drop the `.data` unwrap: the response interceptor in `services/api.js` already returns `response.data`, so the call expression IS the body.

**Verification notes:**
- Grep gate (`bash frontend/scripts/check-no-hardcoded-urls.sh`) — still passes.
- Production build (`npm run build`) — succeeds.
- All 12 TileState tests still pass.
- Pre-existing test failures in `performance.test.jsx` / `DailyPnLChart.test.jsx` / `RecentTrades.test.jsx` are unrelated (`ResizeObserver is not defined` jsdom limitation in `recharts` components) and reproduce on `HEAD~1` (verified by stashing the WR-04 changes and running the same tests).

### WR-05: TileState empty branch ignores `isLoading=true && data!=null` — stale data flashes to "No data yet"

**Files modified:** `frontend/src/components/TileState.jsx`
**Commit:** `db28493`
**Applied fix:** Gated the empty-branch predicate on `!query?.isFetching`:

```jsx
- if (query?.isSuccess && isEmptyFn(query.data)) {
+ if (query?.isSuccess && isEmptyFn(query.data) && !query?.isFetching) {
```

A real empty result from a settled query still shows "No data yet" — the gate only prevents the transient mid-refetch flash over cached non-empty data.

**Verification notes:** All 12 TileState tests still pass (default `isFetching: false` in test fixtures keeps existing-empty scenarios working).

### WR-06: `audit_tiles.py` writes ANSI escape codes unconditionally — corrupts non-TTY output

**Files modified:** `scripts/audit_tiles.py`
**Commit:** `52d53d7`
**Applied fix:** Gated ANSI color codes on `sys.stdout.isatty() and "NO_COLOR" not in os.environ`. The NO_COLOR opt-out follows the [no-color.org](https://no-color.org) convention.

**Verification notes:**
- All 6 `scripts/test_audit_tiles.py` tests still pass.
- `od -c` confirms no `\033` escape bytes in piped output.
- Real TTY behavior unchanged (codes still emitted when stdout is a terminal and `NO_COLOR` is unset).

### WR-07: `check-no-hardcoded-urls.sh` allowlist relies on substring grep — fragile to multi-line block-comment URLs

**Files modified:** `frontend/scripts/check-no-hardcoded-urls.sh`
**Commit:** `4575512`
**Applied fix:** Two changes (the second was a defect the reviewer did not flag but is exposed by attempting the first):

1. Added an `awk` pre-pass over `src/services/api.js` that records the set of line numbers inside `/* ... */` block-comment ranges. The api.js allowlist now consults that set in addition to the existing rules.
2. Tightened the single-line `//` allowlist regex from `grep -q '//'` (matches anywhere) to `grep -Eq '^[[:space:]]*//'` (must be at line-start, i.e. the line IS a comment). The old rule was a latent false-negative because `grep -q '//'` matched the `//` of `http://localhost:...` inside the URL itself, silently allowlisting any code line that contained the URL literal.

**Verification notes:** Five scenarios run end-to-end (Test1..Test4 + Baseline):

| Scenario | Old rule | New rule | Verdict |
|---|---|---|---|
| Plain code URL `const URL = "http://localhost:7777"` | PASS (silent false negative) | FAIL | regression caught (correct) |
| URL on a line of `/* ... */` block with no `*` prefix | FAIL (false positive — reviewer's flagged case) | PASS | bug fixed |
| URL on a `// comment` line | PASS | PASS | preserved |
| URL after inline trailing `// comment` on a code line | PASS | FAIL | stricter; no legitimate use in current api.js |
| Real api.js (unchanged tree) | PASS | PASS | no regression |

## Skipped Issues

None — all 8 in-scope findings (CR-01 + WR-01..WR-07) were fixed and committed.

## Cross-cutting verification

- `bash frontend/scripts/check-no-hardcoded-urls.sh` — exit 0 (grep gate intact)
- `npm run build` — succeeds (production bundle)
- `npx vitest run src/components/__tests__/TileState.test.jsx` — 12/12 passing (no regression from WR-03 or WR-05)
- `pytest scripts/test_audit_tiles.py` — 6/6 passing (no regression from WR-06)
- `python3 -c 'import ast; ast.parse(...)'` on each Python edit — clean

Pre-existing pytest failures in api-gateway tests (per CLAUDE.md "api-gateway test suite must run inside the container") were NOT exercised — the api-gateway codepath was not touched by these fixes. Pre-existing vitest failures in chart components (`recharts` ResizeObserver) were NOT addressed — they reproduce on `HEAD~1` and lie outside Phase 6 review scope.

## Out-of-scope (Info findings)

IN-01 (production `console.log`), IN-02 (raw `error.message` in inline panels), IN-03 (duplicate empty-state UX in PerformanceAnalyticsPanel), IN-04 (textual grep test for `useSafetyState`) were explicitly excluded by `severity_scope: critical+warning`. They remain documented in `06-REVIEW.md` for a future iteration.

---

_Fixed: 2026-05-14T01:55:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
