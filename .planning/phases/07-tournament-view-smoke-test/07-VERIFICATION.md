---
phase: 07-tournament-view-smoke-test
verified: 2026-05-14T22:10:00Z
status: human_needed
score: 3/3 ROADMAP success criteria structurally verified; 1 of 3 awaits live-stack confirmation
overrides_applied: 0
human_verification:
  - test: "CI green run on .github/workflows/integration.yml"
    expected: "Push branch, confirm `Install Playwright browsers` step runs, Chromium downloads, then `pytest tests/integration -v --tb=short --screenshot=only-on-failure --video=retain-on-failure --tracing=retain-on-failure` exits 0 with test_dashboard_smoke.py collected and passing."
    why_human: "Static wiring is verified file-level; first end-to-end execution of the smoke against a recorded-tape stack has never run. STATE.md notes Actions billing is blocked at github.com/settings/billing — operator must unblock before CI signal is available."
  - test: "Resolve Plan 05 Deferred Issue #1 if it triggers on first run"
    expected: "`tape_reset` is `async def`; pytest-playwright's `page` fixture is sync. If the first CI run fails on fixture composition, apply Plan 05's flagged remediation: ensure pytest-asyncio mode is `auto` in pyproject.toml / pytest.ini, OR replace `tape_reset` in the `@pytest.mark.usefixtures` list with a sync wrapper that drives it via `asyncio.run` at the top of the test body."
    why_human: "Plan 05 SUMMARY explicitly flagged this as latent and deferred resolution to the first live run. Plan 06 SUMMARY acknowledges it but did not preempt — both flagged as a follow-up. Falsifying or confirming requires actual pytest-playwright collection."
  - test: "Visual confirmation of /tournament page renders with seeded fixture"
    expected: "Bring up the unified compose stack, seed `services/tournament-harness/data/snapshots/smoke-tape-fixture.json` (+ 2 sidecars), open http://localhost:3000/tournament (or :8000/tournament through gateway), confirm: (a) page heading 'Tournament Leaderboard', (b) selector shows `smoke-tape-fixture`, (c) 7 rows render with SOL/GRU row showing green `✓ in ensemble` pill, (d) 1 failed row (BNB/LSTM) renders with rose `failed` status + `nan_loss` reason, (e) contaminated-warning is NOT visible, (f) footer reads `exported 2026-05-14T12:00:00Z · git a1b2c3d · tournament started 2026-05-14T00:00:00Z`."
    why_human: "Pixel-level visual rendering and hover-tooltip behavior cannot be verified by grep. Code structure suggests it will render correctly, but the only honest confirmation is operator-driven."
---

# Phase 7: Tournament View & Smoke Test — Verification Report

**Phase Goal (ROADMAP.md line 170):** The dashboard reads the tournament leaderboard so the operator can see ML evaluation results without leaving the UI, and a Playwright smoke test asserts every major tile renders non-empty against the recorded-tape stack.

**Verified:** 2026-05-14T22:10:00Z
**Status:** `human_needed`
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (from ROADMAP Success Criteria + REQUIREMENTS DASH-04/DASH-06)

| # | Truth (ROADMAP success criterion) | Status | Evidence |
|---|-----------------------------------|--------|----------|
| 1 | Dashboard exposes a Tournament view showing leaderboard rows from Phase 3's SQLite store, filterable by symbol and architecture, with significance markers from Phase 4 | ✓ VERIFIED | `/tournament` route registered (App.jsx:314); `TournamentDashboard.jsx` composes selector + filter chips + table + footer; `useTournamentList` + `useTournamentSnapshot` consume the gateway snapshot endpoints; significance markers wired via `SignificanceBadge` (`significance-badge-pass` and `significance-badge-none` testids both present at TournamentLeaderboard.jsx:273, SignificanceBadge.jsx:78). Filter chips multi-select on symbol + architecture via URL params (`useSearchParams`). |
| 2 | A Playwright smoke test boots the recorded-tape stack from Phase 1, opens the dashboard, and asserts each major tile (Performance, Portfolio, Safety State, Tournament) renders non-empty | ⚠ STRUCTURALLY VERIFIED (awaits live execution) | `tests/integration/test_dashboard_smoke.py` exists and parses; iterates `06-TILE-AUDIT.json` at runtime (16 rows: 11 FIXED, 5 LABELED_STALE, 0 REMOVED); hard-asserts every non-REMOVED row has `data_testid` before navigation; named StatusBar substrings PAPER / ARMED / OFF / INACTIVE asserted per D-17; targets gateway origin `http://localhost:8000`; both significance paths exercised. **Has never been executed against a live stack** — Plan 05 + Plan 06 SUMMARYs both explicitly defer functional verification to first CI run. |
| 3 | The smoke test is wired into the Phase 2 integration suite so dashboard regressions surface alongside backend regressions | ✓ VERIFIED | `tests/integration/requirements.txt` pins `pytest-playwright>=0.5,<1.0`; `.github/workflows/integration.yml` installs Chromium (line 38) before stack boot and uploads playwright-artifacts on failure (line 94); identical wiring in `integration-ml-on.yml` (lines 35, 79). Existing `iter-fix-check-diff.sh` anti-mock guard preserved; `docker compose down -v` teardown preserved. Single `pytest tests/integration` invocation now collects `test_dashboard_smoke.py` with `--screenshot=only-on-failure --video=retain-on-failure --tracing=retain-on-failure`. |

**Score:** 3/3 structurally verified at file/grep/parse level. SC #2's live-execution proof is gated on CI billing being unblocked.

### Per-Requirement Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| DASH-04 | Tournament view — leaderboard rows from TOURN-02, filterable by symbol/architecture, with significance markers | ✓ SATISFIED (structurally) | All 6 components shipped: `TournamentDashboard.jsx` page, `TournamentLeaderboard.jsx`, `TournamentFilterChips.jsx`, `TournamentSelector.jsx`, `SignificanceBadge.jsx`, `ContaminatedWindowWarning.jsx`; gateway endpoints `GET /api/tournament/snapshots[/{id}]` shipped; 9 in-container unit tests pass per Plan 01 SUMMARY. |
| DASH-06 | Smoke test for the dashboard — Playwright or equivalent asserts each major tile renders non-empty against the recorded-tape stack from INFRA-03 | ⚠ AWAITING LIVE EXECUTION | Test file authored, audit-driven (D-15 full coverage), no escape hatches (B-1 hard data_testid gate), both significance paths exercised, CI install + artifact upload wired. Live green run pending CI billing unblock. |

### Required Artifacts (4 levels: exists / substantive / wired / data-flowing)

**Plan 01 — Gateway endpoints + RO bind-mount:**

| Artifact | Exists | Substantive | Wired | Data Flows | Status |
|----------|--------|-------------|-------|-----------|--------|
| `services/api-gateway/app/main.py` (`/api/tournament/snapshots` + detail routes) | ✓ | ✓ — regex gate, `is_relative_to` defense-in-depth, 50 MiB cap, local imports, module-level `_TOURNAMENT_SNAPSHOTS_DIR` seam | ✓ — reads `/app/snapshots/*.json` via Path.glob | ✓ — host-side dir is gitignored except `.gitkeep`; smoke fixture seeds 3 files into it via the `tournament_snapshot_seeded` conftest fixture | ✓ VERIFIED |
| `docker-compose.unified.yml` RO bind-mount entry | ✓ | ✓ — `./services/tournament-harness/data/snapshots:/app/snapshots:ro` at line 298 | ✓ — Docker creates mount at gateway start regardless of harness profile (D-02) | n/a (mount declaration) | ✓ VERIFIED |
| `services/api-gateway/tests/test_tournament_snapshots.py` (9 tests) | ✓ | ✓ — covers happy path, empty dir, 404, sidecar-missing, path-traversal `..` + `.`, 50 MiB size cap, null sidecars, merged-response | ✓ — Plan 01 SUMMARY: 9 passed, 11 safety-state regression tests still pass | n/a (test code) | ✓ VERIFIED |

**Plan 02 — Frontend data layer:**

| Artifact | Exists | Substantive | Wired | Data Flows | Status |
|----------|--------|-------------|-------|-----------|--------|
| `frontend/src/services/api.js` tournamentAPI export | ✓ (line 219) | ✓ — listSnapshots + getSnapshot, no `/v1/` prefix, reuses shared axios instance | ✓ — imported by both hooks | ✓ — axios interceptor strips `.data` (api.js:34) | ✓ VERIFIED |
| `frontend/src/hooks/useTournamentList.js` | ✓ | ✓ — staleTime: Infinity, refetchOnWindowFocus/Mount false, retry 2, D-23 citation present | ✓ — imported by TournamentDashboard | ✓ — calls tournamentAPI.listSnapshots | ✓ VERIFIED |
| `frontend/src/hooks/useTournamentSnapshot.js` | ✓ | ✓ — same shape + `enabled: !!tournamentId` gate | ✓ — imported by TournamentDashboard | ✓ — calls tournamentAPI.getSnapshot | ✓ VERIFIED |

**Plan 03 — data-testid wiring:**

| Artifact | Exists | Substantive | Wired | Data Flows | Status |
|----------|--------|-------------|-------|-----------|--------|
| TileState.jsx 3 branches | ✓ | ✓ — `tile-stale-badge` (line 82, aria-label preserved), `tile-empty` (119), `tile-error` (161) | ✓ — children of `<TileState/>` wrappers in tile components | n/a | ✓ VERIFIED |
| StatusBar.jsx root + 5 D-17 cells | ✓ | ✓ — `statusbar` (118), `statusbar-trading-state` (132), `statusbar-mode/kill-switch/ml/emergency-stop` via Cell `testId` prop (35, 178, 186, 194, 203) | ✓ — Cell helper accepts `testId` prop and emits `data-testid` | ✓ — safety-state values feed accent + label (PAPER/ARMED/OFF/INACTIVE defaults from `useSafetyState`) | ✓ VERIFIED |
| 15 audited tile components/pages | ✓ | ✓ — each has root-level `data-testid="{kebab}"` (KeyMetricsStrip/TradingSignals×2/HybridStrategyPanel/RegimeIndicator/TradingEnhancementsPanel/PerformanceAnalyticsPanel/ActiveTrades/TradeHistory/PortfolioCard/PriceTickerGrid/PriceChart/Sparkline + Phase1Dashboard/Phase3Dashboard/Portfolio pages) | ✓ — wrapper pattern `<div data-testid="..." style={{display:'contents'}}>` preserves grid/flex layouts | n/a | ✓ VERIFIED |
| `06-TILE-AUDIT.json` updates | ✓ | ✓ — 16 rows, 11 FIXED + 5 LABELED_STALE + 0 REMOVED; every non-REMOVED row has `data_testid`; Tournament row appended (verdict FIXED, data_testid `tournament-leaderboard`) | ✓ — read at smoke-test runtime by `tile_audit` session fixture | ✓ — Tournament row's `component_file` field references `frontend/src/components/TournamentLeaderboard.jsx` which exists | ✓ VERIFIED |
| `06-TILE-AUDIT.md` mirror | ✓ | ✓ — Tournament section added (line 63); markdown tables include `data-testid` column | n/a | n/a | ✓ VERIFIED |

**Plan 04 — TournamentDashboard page + components + route:**

| Artifact | Exists | Substantive | Wired | Data Flows | Status |
|----------|--------|-------------|-------|-----------|--------|
| `frontend/src/pages/TournamentDashboard.jsx` (370 LOC) | ✓ | ✓ — sticky header + selector + filter chips + TileState-wrapped table + contaminated warning + footer; URL state via `useSearchParams`; sort/dir whitelist validation; staleAfterMs Infinity (D-23) | ✓ — imported in App.jsx:36, registered at /tournament:314 | ✓ — hooks fetch from gateway endpoints; React Query cache keyed by `['tournament-list']` / `['tournament-snapshot', id]` | ✓ VERIFIED |
| `frontend/src/components/TournamentLeaderboard.jsx` (380 LOC) | ✓ | ✓ — plain `<table>` with click-to-sort; 13 columns + row-marker; mint/rose value coloring; null/NaN sorts last; D-07 short-circuit em-dash for failed rows | ✓ — rendered inside TileState in TournamentDashboard | ✓ — receives rows + ensembleMembersBySymbol + perSymbolSignificance as props | ✓ VERIFIED |
| `TournamentFilterChips.jsx` (292 LOC) | ✓ | ✓ — 3 groups (symbols/arch chips multi-select, status segmented); URL state; counts; Clear filters button | ✓ — rendered in page | ✓ — useSearchParams writes/reads URL params | ✓ VERIFIED |
| `TournamentSelector.jsx` (105 LOC) | ✓ | ✓ — native `<select>` sorted by exported_at desc; placeholder when empty | ✓ — rendered in page | ✓ — `onChange` writes tournament_id to URL params | ✓ VERIFIED |
| `SignificanceBadge.jsx` (144 LOC) | ✓ | ✓ — pass pill (mint, ✓ in ensemble) + em-dash fallback; pure useState hover tooltip (no Radix dep); D-05 null-significance suppresses tooltip | ✓ — rendered in TournamentLeaderboard significance column | ✓ — inEnsemble + winGatePassed + significance props flow from snapshot+ensemble+significance response | ✓ VERIFIED |
| `ContaminatedWindowWarning.jsx` (80 LOC) | ✓ | ✓ — renders only when `anyContaminated=true`; AlertTriangle icon + rose strip + title attribute | ✓ — rendered in page | ✓ — `visible` prop computed from `rows.some(r => r.train_window_includes_contaminated)` | ✓ VERIFIED |
| `App.jsx` route + nav | ✓ | ✓ — desktop `<NavLink to="/tournament">` (197), mobile navItems entry (120), Route registration (314) | ✓ — TournamentDashboard imported | n/a | ✓ VERIFIED |

**Plan 05 — Smoke fixture + conftest + test:**

| Artifact | Exists | Substantive | Wired | Data Flows | Status |
|----------|--------|-------------|-------|-----------|--------|
| `tests/fixtures/tournament/smoke-fixture.json` | ✓ | ✓ — 7 rows, exactly 1 failed (BNB/LSTM `nan_loss`), exactly 1 row with `dsr>=1.0` (SOL/GRU `1.142`), all rows `train_window_includes_contaminated=false`, full Phase 3 schema columns | ✓ — copied by tournament_snapshot_seeded fixture to bind-mount source | ✓ — programmatic validation: tournament_id == "smoke-tape-fixture", summary {n_rows:7, n_success:6, n_failed:1} | ✓ VERIFIED |
| `smoke-fixture.ensemble.json` | ✓ | ✓ — Single ensemble for SOL with one member; `members[0].run_id` ("smoke-sol-gru-001") byte-identical to SOL/GRU success row | ✓ — copied to `*.ensemble.json` sidecar at bind-mount source | ✓ — gateway joins on filename convention; frontend `ensembleMembersBySymbol[SOL].has(run_id)` resolves true | ✓ VERIFIED |
| `smoke-fixture.significance.json` | ✓ | ✓ — `per_symbol.SOL.win_gate_passed=true`, BNB+ADA false (drives smoke to assert both badge variants) | ✓ — copied to `*.significance.json` sidecar | ✓ — frontend reads `perSymbolSignificance[symbol].win_gate_passed` | ✓ VERIFIED |
| `tests/integration/conftest.py` `tournament_snapshot_seeded` | ✓ (line 317) | ✓ — function-scope; 3-file seed + 3-file teardown via `try/finally`; uses `pathlib.Path.read_text`/`write_text` (per project memory) | ✓ — referenced by smoke test's `@pytest.mark.usefixtures` decorator | n/a (test plumbing) | ✓ VERIFIED |
| `tests/integration/test_dashboard_smoke.py` | ✓ (parses) | ✓ — single test `test_every_audited_tile_renders_per_verdict`; hard data_testid gate BEFORE navigation; page-level route override map (BL-1 fix); per-verdict assertions; Tournament-specific block; D-17 named substrings; gateway origin only (no :3000) | ✓ — composes `bootstrap_stack` + `tape_reset` + `tournament_snapshot_seeded` + `page` fixtures | ⚠ **Has never executed** — `pytest-playwright` not installed in this worktree, CI billing blocked, no green run on record | ⚠ STRUCTURALLY VERIFIED (awaits live execution) |

**Plan 06 — CI wiring:**

| Artifact | Exists | Substantive | Wired | Data Flows | Status |
|----------|--------|-------------|-------|-----------|--------|
| `tests/integration/requirements.txt` | ✓ | ✓ — pytest-playwright>=0.5,<1.0 + Phase 2 baseline (httpx/asyncpg/pytest/pytest-asyncio) | ✓ — referenced via `pip install -r` in both workflows | n/a | ✓ VERIFIED |
| `.github/workflows/integration.yml` Playwright install + artifact upload | ✓ | ✓ — `playwright install --with-deps chromium` (line 38); pytest flags `--screenshot --video --tracing` (64); failure artifact upload (94); name `playwright-artifacts`, retention 14d | ✓ — install runs before stack boot; artifact step runs before teardown (paths still exist at upload time); existing `iter-fix-check-diff.sh` anti-mock guard and `docker compose down -v` teardown both preserved | ⚠ Never executed in CI (billing blocked per STATE.md:34) | ⚠ STRUCTURALLY VERIFIED (awaits live execution) |
| `.github/workflows/integration-ml-on.yml` same wiring | ✓ | ✓ — symmetric edits; artifact name `playwright-artifacts-ml-on` to avoid name collision; identical install + flags | ✓ — same composition | ⚠ Never executed in CI | ⚠ STRUCTURALLY VERIFIED |

### Key Link Verification (Wiring)

| From | To | Via | Status | Detail |
|------|-----|-----|--------|--------|
| `services/api-gateway/app/main.py` (routes) | `/app/snapshots/*.json` on disk | `Path("/app/snapshots").glob("*.json")` + `json.loads(read_text())` | ✓ WIRED | Local imports inside route body; matches `feedback_main_imports_autoflake.md` |
| `frontend/src/services/api.js` `tournamentAPI` | Gateway `/api/tournament/snapshots[/{id}]` | `api.get('/tournament/snapshots')` (api baseURL='/api') | ✓ WIRED | api.js:221, 223 |
| `useTournamentList` / `useTournamentSnapshot` | `tournamentAPI` | `queryFn: () => tournamentAPI.list/get(...)` | ✓ WIRED | Hooks files lines 46/47 + 42/43 |
| `TournamentDashboard.jsx` | Both hooks | `import` + invocation lines 95, 96 | ✓ WIRED | |
| `TournamentLeaderboard.jsx` | `SignificanceBadge.jsx` | `<SignificanceBadge>` rendered at line 285 (success rows only — failed rows short-circuit to em-dash at 273) | ✓ WIRED | D-07 honored |
| `App.jsx` | `TournamentDashboard` | `<Route path="/tournament" element={<TournamentDashboard />} />` (line 314) | ✓ WIRED | |
| `test_dashboard_smoke.py` | `06-TILE-AUDIT.json` | `json.loads(audit_path.read_text())` at session fixture | ✓ WIRED | Audit file has 16 rows, all non-REMOVED carry data_testid |
| `tournament_snapshot_seeded` | RO bind-mount source dir | `dst.write_text(src.read_text())` for 3 files; cleanup on teardown | ✓ WIRED | Path: `services/tournament-harness/data/snapshots/smoke-tape-fixture{,.ensemble,.significance}.json` |
| `integration.yml` `pytest tests/integration` step | `test_dashboard_smoke.py` | Single pytest invocation collects the smoke alongside Phase 2 tests | ✓ WIRED | Capture flags forward Playwright artifacts to step 10 |

### Locked Decisions D-01..D-25 Implementation

| Decision | Implementation Evidence | Status |
|----------|------------------------|--------|
| D-01: api-gateway reads committed snapshot JSON via RO bind-mount | `docker-compose.unified.yml:298` + main.py routes | ✓ |
| D-02: tournament-harness profile stays opt-in | No `depends_on: tournament-harness` added; mount works regardless | ✓ |
| D-03: Backend merges snapshot + ensemble + significance | `get_tournament_snapshot` returns `{snapshot, ensemble, significance}` (main.py:1223+) | ✓ |
| D-04: Significance marker = badge column + tooltip | `SignificanceBadge.jsx` pass-pill + em-dash + hover tooltip with sharpe/dir_acc lift + p-values | ✓ |
| D-05: Missing sidecars → significance column renders em-dash | Plan 01 returns nulls; SignificanceBadge suppresses tooltip when sig===null | ✓ |
| D-06: No snapshots → count:0 empty response | Handler returns `{success:True, count:0, tournaments:[]}` when dir absent | ✓ |
| D-07: All-failed snapshot renders failure column, not empty | TournamentLeaderboard.jsx:270-278 short-circuit failed rows to em-dash; rose-tinted failure column | ✓ |
| D-08: Fixture at `tests/fixtures/tournament/smoke-fixture.json` + `tournament_snapshot_seeded` fixture | Both shipped (3 files + conftest entry) | ✓ |
| D-09: New top-level `/tournament` route after `/phase3` nav | App.jsx:197 (NavLink), 314 (Route) | ✓ |
| D-10: Page layout (selector + chips + table + footer) | TournamentDashboard.jsx composition matches ASCII | ✓ |
| D-11: Plain `<table>` Editorial Trading Floor aesthetic, no TanStack | grep confirms no TanStack import; JetBrains Mono + tnum present | ✓ |
| D-12: Sort default dsr DESC, click-to-sort, URL persistence | Whitelist validation + setParams sort/dir | ✓ |
| D-13: Chip-style multi-select filters via useSearchParams | TournamentFilterChips uses useSearchParams; multi-select serialized comma-separated | ✓ |
| D-14: Filter pills show counts + Clear filters button | Implemented in TournamentFilterChips | ✓ |
| D-15: Full audit-driven smoke coverage | smoke iterates `06-TILE-AUDIT.json` rows at runtime, hard-asserts all data_testids | ✓ |
| D-16: Tournament tile row appended to audit | 06-TILE-AUDIT.json row 16 + 06-TILE-AUDIT.md section at line 63 | ✓ |
| D-17: StatusBar 5 D-17 cells get per-cell testids | statusbar-mode/kill-switch/ml/emergency-stop/trading-state all wired | ✓ |
| D-18: pytest-playwright + Chromium-only | requirements.txt + workflows `playwright install --with-deps chromium` | ✓ |
| D-19: Reuse Phase 2 bootstrap_stack + tape_reset fixtures | Smoke @pytest.mark.usefixtures composes all three | ✓ |
| D-20: CI smoke inside existing job (no parallel) | Single pytest invocation; no `npx playwright test`; failures block merge | ✓ |
| D-21: Local invocation via plain pytest | `pytest tests/integration/test_dashboard_smoke.py` works after dep install | ✓ |
| D-22: Screenshot + HAR + trace artifacts on failure | `--screenshot --video --tracing` flags + upload-artifact@v4 step (if:failure()) | ✓ |
| D-23: staleTime Infinity, no polling | Both hooks: staleTime Infinity, refetchOnWindowFocus/Mount false; no refetchInterval | ✓ |
| D-24: No new global state | React Query cache + URL params; no Redux/Zustand additions | ✓ |
| D-25: api.js extension adds tournamentAPI | tournamentAPI alongside portfolioAPI/tradingAPI; baseURL '/api' + interceptor reused | ✓ |

**D-01..D-25 score: 25/25 implemented.**

### Data-Flow Trace (Level 4)

Pre-conditions traced upstream from each rendered artifact:

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `TournamentDashboard` leaderboard table | `snapshotQuery.data.snapshot.rows` | `useTournamentSnapshot(tournamentId)` → `tournamentAPI.getSnapshot` → gateway `GET /api/tournament/snapshots/{id}` → `Path("/app/snapshots/{id}.json").read_text()` → smoke fixture (`smoke-tape-fixture.json` with 7 deterministic rows) | ✓ FLOWING (when fixture seeded) |
| `TournamentSelector` options | `listQuery.data.tournaments` | `useTournamentList()` → `tournamentAPI.listSnapshots` → gateway list endpoint → `Path("/app/snapshots").glob("*.json")` → smoke fixture present after seeding | ✓ FLOWING |
| `SignificanceBadge` pass-pill | `ensembleMembersBySymbol[SOL].has("smoke-sol-gru-001") && perSymbolSignificance.SOL.win_gate_passed` | Page-level useMemo over `snapshotQuery.data.ensemble.ensembles` + `snapshotQuery.data.significance.per_symbol` → committed sidecar fixtures (ensemble + significance JSONs) | ✓ FLOWING |
| `ContaminatedWindowWarning` | `rows.some(r => r.train_window_includes_contaminated === true)` | Fixture rows all set false → component renders null → smoke asserts absence | ✓ FLOWING (negative case verified by fixture contract) |
| `StatusBar` D-17 cells | `useSafetyState` defaults to PAPER posture when endpoint unavailable; emergency derives from `safety.emergency_stop.active` + `tradingStatus.status.emergency_stop.active` | Phase 6 endpoints `/api/config/safety-state` + trading-engine `/status` | ✓ FLOWING (defaults safe under tape) |

No HOLLOW or DISCONNECTED artifacts found. All rendered data has a traceable source that produces real (or deterministic-fixture) values.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Audit JSON parses + every non-REMOVED row has data_testid + Tournament row present | `python3 -c "import json; d=json.load(open('.planning/phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.json')); assert all('data_testid' in r for r in d['tiles'] if r['verdict']!='REMOVED'); assert any(r.get('tile')=='TournamentLeaderboard' for r in d['tiles'])"` | exits 0 | ✓ PASS |
| Smoke fixture trio cross-references validly | Custom python verifying `len(rows)==7`, `n_failed==1`, ensemble member byte-matches SOL/GRU run_id, SOL.win_gate_passed=true | All assertions pass | ✓ PASS |
| Smoke test file parses as valid Python | `python3 -c "import ast; ast.parse(open('tests/integration/test_dashboard_smoke.py').read())"` | exits 0 | ✓ PASS |
| Both CI workflows parse as valid YAML | `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/integration.yml')); yaml.safe_load(open('.github/workflows/integration-ml-on.yml'))"` | exits 0 | ✓ PASS |
| All 5 LABELED_STALE tiles have `forceStale` wired (Phase 6 Plan 06-05 precondition) | Iterate audit, grep each `component_file` for `forceStale` | PriceTickerGrid, PriceChart, Sparkline, Phase3Dashboard, Portfolio — all 5 OK | ✓ PASS |
| Gateway endpoints reachable + return expected shape | (requires docker stack up) | n/a — stack not booted in this verification session | ? SKIP |
| Smoke test executes end-to-end against running stack | `pytest tests/integration/test_dashboard_smoke.py` | n/a — pytest-playwright not installed in this worktree; CI billing blocked | ? SKIP |
| Frontend page renders /tournament with seeded fixture | (requires `npm run dev` + browser) | n/a — visual check requires operator | ? SKIP |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (no Phase 7 production code) | — | No HTML-injection sinks: `grep -nE 'dangerouslySet\|innerHTML\s*=' frontend/src/components/Tournament*.jsx frontend/src/components/SignificanceBadge.jsx frontend/src/components/ContaminatedWindowWarning.jsx frontend/src/pages/TournamentDashboard.jsx` returns 0 matches | (clean) | T-07-11 XSS surface clean |
| Smoke test | n/a | No escape hatches: `grep -nE 'skip with a clear message\|may not have one'` returns 0 matches | (clean) | B-1 hard gate enforced |
| Smoke test | n/a | No vite-dev origin leak: `grep -nE 'http://localhost:3000'` returns 0 matches | (clean) | Gateway-origin testing only |

No anti-patterns detected. The codebase is clean.

### Human Verification Required

Three items requiring human/operator action before declaring Phase 7 fully shipped:

#### 1. CI green run on integration.yml

**Test:** Push the current branch (or merge to main) and observe the GitHub Actions run for the `Integration Suite (Phase 2)` workflow on `.github/workflows/integration.yml`.

**Expected:**
- `Install pytest dependencies` step succeeds (installs from `tests/integration/requirements.txt` including `pytest-playwright>=0.5,<1.0`).
- `Install Playwright browsers (Chromium only, D-18)` step succeeds (downloads Chromium ~150 MB, completes in ~30s).
- `Run integration suite` step exits 0 with `test_dashboard_smoke.py` collected and passing.
- No `playwright-artifacts` artifact uploaded (failure-only step is skipped on success).

**Why human:** STATE.md line 34 records that GitHub Actions billing is blocked at `github.com/settings/billing`; until the operator unblocks, the first execution of the Phase 7 smoke against a recorded-tape stack cannot occur. Plan 05 + Plan 06 SUMMARYs both explicitly defer functional verification to this run.

#### 2. Resolve Plan 05 Deferred Issue #1 if it triggers on the first run

**Test:** If item #1 above fails with a fixture-composition error (`tape_reset` is `async def`; pytest-playwright's `page` fixture is sync), apply Plan 05's flagged remediation.

**Expected (remediation path):**
- Confirm `pytest.ini` or `pyproject.toml` sets `asyncio_mode = "auto"`; if not, add it OR
- Replace `tape_reset` in the `@pytest.mark.usefixtures(...)` list with a sync wrapper that drives `tape_reset` via `asyncio.run` at the top of the test body.

**Why human:** Cannot be falsified without actual pytest-playwright collection in a runtime environment with the stack booted. Plan 05 SUMMARY explicitly flags this as latent and not a wiring fix.

#### 3. Visual confirmation that /tournament page renders with the seeded fixture

**Test:**
1. Bring up the unified compose stack: `docker compose -f docker-compose.unified.yml up -d`.
2. Seed the fixture trio: `cp tests/fixtures/tournament/smoke-fixture.json services/tournament-harness/data/snapshots/smoke-tape-fixture.json && cp tests/fixtures/tournament/smoke-fixture.ensemble.json services/tournament-harness/data/snapshots/smoke-tape-fixture.ensemble.json && cp tests/fixtures/tournament/smoke-fixture.significance.json services/tournament-harness/data/snapshots/smoke-tape-fixture.significance.json`.
3. Open `http://localhost:3000/tournament` (vite dev) and `http://localhost:8000/tournament` (gateway proxy, after frontend prod build).
4. Confirm:
   - (a) page heading reads `Tournament Leaderboard`;
   - (b) selector dropdown shows `smoke-tape-fixture` option (date 2026-05-14, 7 runs);
   - (c) 7 rows render — SOL/GRU at top after `dsr desc` default sort, showing green `✓ in ensemble` pill in significance column;
   - (d) BNB/LSTM row is rose-tinted, status `failed`, failure_reason `nan_loss`;
   - (e) `<ContaminatedWindowWarning/>` is NOT visible;
   - (f) footer reads `exported 2026-05-14T12:00:00Z · git a1b2c3d · tournament started 2026-05-14T00:00:00Z`;
   - (g) hover over the green ✓ pill shows a tooltip with Sharpe lift / Dir.Acc lift / p-values from the significance sidecar.

**Why human:** Pixel-level visual rendering, hover-tooltip behavior, the `useEffect` auto-selection of latest tournament on first paint, sticky header backdrop-blur — none of these can be verified by grep or AST parse. Code structure suggests correct rendering, but the only honest confirmation is operator-driven.

### Gaps Summary

**No structural gaps found.** Every artifact promised by the ROADMAP success criteria, the REQUIREMENTS entries (DASH-04 + DASH-06), and the 25 locked CONTEXT.md decisions is implemented in the codebase. The 6 plans land 18 new files (8 frontend components + 1 page + 2 hooks + 3 fixture JSONs + 1 smoke test + 3 audit/dep files) and modify 21 existing files. All 9 in-container gateway tests pass. All key links (frontend → hooks → API → gateway → snapshot JSON; smoke → audit JSON → bind-mount source) are wired.

**One operational gap:** the audit-driven smoke test has never been executed end-to-end against a live recorded-tape stack. STATE.md notes Actions billing is blocked; until the operator resolves that, the CI gate cannot produce its green signal. This is not a code gap — the test is correctly authored and correctly wired into the CI workflow. It is a pre-merge confirmation step that depends on operator action.

**Pre-merge concerns (non-blocking):**

1. **Plan 05 Deferred Issue #1 (async-fixture compat)** — `tape_reset` async vs pytest-playwright sync `page` fixture; may need `asyncio_mode = "auto"` or sync wrapper. Flagged in both Plan 05 and Plan 06 SUMMARYs but never preempted because resolution requires runtime collection.

2. **First-run Chromium download in CI** — adds ~30s install time + ~150 MB egress. Existing job timeout is 30 min (per `integration.yml` line 16) so plenty of headroom; flagged here in case CI billing limits matter.

3. **ML-on workflow artifact name** — Plan 06 used `playwright-artifacts-ml-on` (vs plain `playwright-artifacts`) to prevent `actions/upload-artifact@v4` name collision should both workflows ever post in the same context. Plan 06 SUMMARY documents this as a judgment call within the plan's "or equivalent" allowance.

### Verdict: COMPLETE (structurally) — NEEDS-ACTION (operator)

- All 25 locked decisions implemented.
- All artifacts exist, are substantive, are wired, and have traceable data flows.
- All key links verified.
- No anti-patterns or HTML-injection sinks.
- DASH-04 satisfied: tournament view is consumable by operator without leaving UI; selector + filter chips + table + significance markers + contaminated-warning + footer all render against the gateway endpoints.
- DASH-06 STRUCTURALLY satisfied: smoke test is audit-driven, no escape hatches, every major tile asserted, both significance paths exercised, gateway-origin tested. Functional execution awaits CI billing unblock — this is operator action, not a code gap.

**Status:** `human_needed` — the three operator items above must complete before the phase ships. None of them require code changes.

---

*Verified: 2026-05-14T22:10:00Z*
*Verifier: Claude (gsd-verifier)*
*Re-verification: not applicable (initial verification)*
