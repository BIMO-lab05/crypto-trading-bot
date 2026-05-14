# Phase 7: Tournament View & Smoke Test - Context

**Gathered:** 2026-05-14
**Status:** Ready for planning
**Mode:** `--auto` (user requested no clarifying questions — every gray area locked on the recommended option; redirect any D-NN by editing this file before `/gsd-plan-phase 7`)

<domain>
## Phase Boundary

Two deliverables, one phase:

1. **Tournament leaderboard view** — a dashboard surface that reads Phase 3's tournament leaderboard (committed snapshot JSON at `services/tournament-harness/data/snapshots/{tournament_id}.json`) plus Phase 4's per-symbol significance artifacts (`{tournament_id}.ensemble.json`, `{tournament_id}.significance.json`), renders rows filterable by symbol and architecture, and marks runs whose symbol passed Phase 4's bootstrap win-gate. Operator sees ML evaluation results without leaving the UI.

2. **Playwright smoke test** — a `pytest-playwright` test that boots the Phase 1 recorded-tape stack via Phase 2's `bootstrap_stack` fixture, opens the dashboard, and asserts every tile in `06-TILE-AUDIT.json` renders its expected state (FIXED → real data / non-empty body; LABELED_STALE → stale badge from `<TileState forceStale/>`; REMOVED → tile absent from DOM). Wired into `tests/integration/` so dashboard regressions surface alongside backend regressions in the existing CI workflows.

**In scope:**
- New api-gateway routes `GET /api/tournament/snapshots` (list) + `GET /api/tournament/snapshots/{tournament_id}` (merged snapshot + ensemble + significance), both read-only, both reading from disk under `services/tournament-harness/data/snapshots/` via a RO bind-mount on api-gateway (per D-01)
- New frontend `/tournament` top-level route, `TournamentDashboard.jsx` page, `<TournamentLeaderboard/>` table component, `useTournamentSnapshot.js` React Query hook
- Filter chips (multi-symbol + multi-architecture + success/failed status) backed by URL query params, default sort `dsr DESC`
- Significance markers — green ✓ badge column for runs in `ensembles[symbol].members` of a `win_gate_passed=true` symbol, gray "—" otherwise; tooltip shows `sharpe_lift`, `sharpe_pvalue`, `dir_acc_lift`, `dir_acc_pvalue`
- `<TileState/>` (from Phase 6) wraps the leaderboard table; empty state renders `"No tournament data yet — run `tournament run` from the harness CLI"` with a docs anchor
- Fixture snapshot at `tests/fixtures/tournament/smoke-fixture.json` (committed, 6–9 deterministic rows across {SOL, BNB, ADA} × {GRU, LSTM}; one failed-run row to exercise failure rendering); pytest fixture copies it into `services/tournament-harness/data/snapshots/` during smoke setup
- `pytest-playwright` + `playwright install chromium` added to integration suite deps; new `tests/integration/test_dashboard_smoke.py` driving Chromium against the gateway dev origin
- Smoke wired into `.github/workflows/integration.yml` (the existing Phase 2 workflow) — the smoke run blocks PR merges
- Phase 6's `06-TILE-AUDIT.json` row inventory becomes the smoke driver — each row's verdict drives the assertion (FIXED → body non-empty, LABELED_STALE → `[data-testid="tile-stale-badge"]` present, REMOVED → not present)
- Update Phase 6 `06-TILE-AUDIT.md` to add a new row for the Tournament tile (verdict: FIXED)

**Out of scope (deferred to v2 or later phases):**
- Live SQLite read (tournament-harness `:8010` profile=`tournament` opt-in) — gateway reads committed snapshot files only; eliminates the need to bring `--profile tournament` up for the dashboard or the smoke
- Significance metadata embedded into the snapshot at export time (would require Phase 3 schema bump) — gateway joins snapshot + significance artifacts on demand
- Triggering a tournament run from the UI — operator-driven via CLI only; tournament-harness CLI stays the mutation surface
- Per-run drill-down page (single-run detail view) — out of v1 scope; the table row + tooltip carry enough for v1 operator review
- WebSocket / SSE push for leaderboard — tournaments are cold batches, page-mount fetch + manual refresh is sufficient
- Auth on the new endpoints — match Phase 6 D-09 (`/api/config/safety-state` is unauthenticated read-only config disclosure); same posture here
- Mobile responsive layout for `/tournament` — v2
- Authentication / RBAC on `tournament run` mutations — operator-only CLI, no UI mutation path
- Cross-tournament comparison / time-series of leaderboard metrics — v2

</domain>

<decisions>
## Implementation Decisions

### A. Tournament data path
- **D-01:** **api-gateway proxy reads the committed snapshot JSON.** api-gateway gets a RO bind-mount of `./services/tournament-harness/data/snapshots:/app/snapshots:ro`. New routes:
  - `GET /api/tournament/snapshots` → list of `{tournament_id, exported_at, n_rows, n_success, n_failed, symbols[], architectures[]}` derived from each `{tournament_id}.json` file's `summary` block
  - `GET /api/tournament/snapshots/{tournament_id}` → merged response: `{snapshot: {…rows…}, ensemble: {…} | null, significance: {…} | null}`. Significance artifacts are looked up by filename convention next to the snapshot (`{tournament_id}.ensemble.json`, `{tournament_id}.significance.json`); `null` when absent (tournament not yet run through Phase 4).
  - Both endpoints unauthenticated (carryforward Phase 6 D-09). Both follow `/api/<domain>/<resource>` (no `v1` prefix per ADR-007).
  - **Rationale:** snapshots are committed/git-tracked so frontend always has data without `--profile tournament` being up. tournament-harness service can stay off-by-default. The disk read happens inside the gateway (single ingress point, sole frontend entry in prod), matching Phase 6 D-09 pattern.

- **D-02:** **tournament-harness profile stays opt-in.** No change to compose's `profiles: [tournament]` gate for `tournament-harness`. The dashboard view and the smoke test do not depend on the service running.

### B. Significance markers
- **D-03:** **Backend merges** snapshot + ensemble + significance into a single response (per D-01). Frontend issues ONE React Query fetch per tournament view. Phase 4 schema:
  - Significance: `per_symbol[symbol] = {sharpe_lift, sharpe_pvalue, dir_acc_lift, dir_acc_pvalue, n_oos_bars, block_size, n_resamples, win_gate_passed: bool, n_members, bootstrap_seed}`
  - Ensemble: `ensembles[] = [{symbol, members: [{run_id, architecture, hp_hash, dsr}, ...]}]`
- **D-04:** **Marker rendering = badge column + tooltip.**
  - New column "Significance" between `dsr` and `train_seconds`
  - Cell logic: if this row's `run_id` is in the ensemble for its symbol AND that symbol has `win_gate_passed=true` → green "✓ in ensemble" pill; otherwise gray "—"
  - Hover tooltip: `Sharpe lift {value} (p={…})  ·  Dir.Acc lift {value} (p={…})  ·  block_size={…} n_resamples={…}`
  - No row-level background coloring (visually noisy on a dense table)
- **D-05:** **Missing significance artifacts** (Phase 4 not yet run) → significance column renders "—" for every row; tooltip omitted. Leaderboard table still renders fully.

### C. Empty-state semantics
- **D-06:** **No snapshots in `data/snapshots/`** → `/api/tournament/snapshots` returns `{success: true, count: 0, tournaments: []}`. Frontend `<TileState/>` empty-state copy: `"No tournament data yet. Run 'tournament run --config <yaml>' from services/tournament-harness/ to create one."` plus a small inline reference to `services/tournament-harness/README.md`.
- **D-07:** **All-failed snapshot** (every row has `status='failed'`) → table renders with the failure column highlighted (rose `#fb7185` per Phase 6 aesthetic); not treated as empty. Operator must SEE failed-run reasons (D-15 from Phase 3 has the `failure_reason` enum: `oom_killed`, `nan_loss`, `timeout`, `exit_nonzero`, `train_diverged`, `db_unreachable`, `unknown`).
- **D-08:** **Fixture snapshot** for smoke test lives at `tests/fixtures/tournament/smoke-fixture.json`, committed. Pytest fixture (`tournament_snapshot_seeded`) copies it into `services/tournament-harness/data/snapshots/smoke-tape-fixture.json` at smoke setup. Deterministic, reviewable, no SQLite spin-up required. Cleanup teardown deletes the copy.

### D. Dashboard nav placement & view structure
- **D-09:** **New top-level `/tournament` route.** Sibling to `/performance`, `/portfolio`. Registered in `frontend/src/App.jsx` Routes. Nav link in the top bar after "Phase 3". Page = `TournamentDashboard.jsx`.
- **D-10:** **Page layout:**
  1. Tournament selector (dropdown, latest first by `exported_at`) at the top — operator picks which tournament's leaderboard to view
  2. Filter chip row (multi-symbol + multi-architecture + status `success/failed/all`)
  3. Leaderboard table (one row per leaderboard run, columns: `architecture`, `symbol`, `horizon`, `target_mode`, `dsr`, `oos_sharpe`, `psr`, `dir_acc_corrected`, `r2_returns`, **Significance**, `train_seconds`, `status`, `failure_reason`)
  4. Footer strip with `exported_at`, `git_sha`, `tournament_start_ts`, `train_window_includes_contaminated` flag (visible warning if true)
- **D-11:** **Table component:** plain `<table>` with the Editorial Trading Floor aesthetic from `KeyMetricsStrip.jsx` / `StatusBar.jsx` (JetBrains Mono for numeric cells, mint accent on positive metrics, rose on failures). No TanStack Table — keep dependency surface minimal; one-page dataset doesn't need virtualization at v1 scale.
- **D-12:** **Sort default:** `dsr DESC`. Click-to-sort on any column header. Sort state persisted in URL (`?sort=dsr&dir=desc`).

### E. Filter UX
- **D-13:** **Chip-style multi-select filters** (symbol, architecture) + segmented control for status (`success / failed / all`). All filter state is reflected in URL query params (`?symbol=SOL,ADA&arch=GRU&status=success&sort=dsr&dir=desc`) so deep-links + browser back are well-behaved. Same React Router `useSearchParams` pattern that Phase 6 dashboard tiles use elsewhere.
- **D-14:** **Filter pills** show counts (`SOL (12)`, `BNB (12)`, `ADA (12)`); click toggles selection. "Clear filters" button when any non-default chip active.

### F. Smoke test scope — "major tile" definition
- **D-15:** **Full audit-driven coverage.** ROADMAP names "Performance, Portfolio, Safety State, Tournament" — interpret as the floor, not the ceiling. The smoke test reads `06-TILE-AUDIT.json` at runtime and asserts every row's verdict:
  - `FIXED` → tile body renders non-empty (selector + visible content)
  - `LABELED_STALE` → `[data-testid="tile-stale-badge"]` is present (Phase 6 ships this via `<TileState forceStale/>`)
  - `REMOVED` → tile component NOT present in DOM
- **D-16:** **Tournament tile added to audit.** Update `06-TILE-AUDIT.md` + `06-TILE-AUDIT.json` to add one row for the Tournament view (verdict: `FIXED`, backing endpoint: `/api/tournament/snapshots/{id}`, component: `frontend/src/components/TournamentLeaderboard.jsx`).
- **D-17:** **Safety state — special-case assertion.** Beyond presence, assert all 5 cells from Phase 6 D-03 render with the expected mode (PAPER pill green, kill-switch ARMED, ML toggle OFF, etc.) under recorded-tape defaults. Catches regressions in StatusBar wiring.

### G. Smoke runner wiring
- **D-18:** **`pytest-playwright` plugin, Chromium only.** Add `pytest-playwright>=0.5` to `tests/integration/requirements.txt` (or the testcontainers extras already pinned there) and call `playwright install --with-deps chromium` in the CI workflow. Tests live at `tests/integration/test_dashboard_smoke.py`. One language, one CI command (`pytest tests/integration`), no `npx playwright test` shim.
- **D-19:** **Reuse Phase 2 fixtures:** `bootstrap_stack` brings the recorded-tape stack up; `tape_reset` ensures determinism; `tournament_snapshot_seeded` (new fixture from D-08) seeds the snapshot. The smoke test never touches the live exchange.
- **D-20:** **CI integration:** smoke runs in `.github/workflows/integration.yml` as part of the existing job (NOT a parallel job — re-uses the stack the integration suite brings up; saves a second `compose up`). Failure surfaces as a normal pytest failure, blocking merge.
- **D-21:** **Local invocation:** `pytest tests/integration/test_dashboard_smoke.py` runs the smoke standalone for iteration; the Phase 2 `iter-fix.sh` checkpointed loop applies if smoke regresses.
- **D-22:** **Screenshot artifacts on failure.** Configure pytest-playwright to capture screenshot + HAR + trace on failure; CI uploads `playwright-report/` as a job artifact. Local runs drop them in `tests/integration/.playwright/`.

### H. Frontend data plumbing
- **D-23:** **React Query, single fetch, no polling.** `useTournamentSnapshot(tournament_id)` calls `api.get('/tournament/snapshots/{id}')`; `useTournamentList()` calls `api.get('/tournament/snapshots')`. `staleTime: Infinity`, manual `refetch()` triggered by a refresh button in the page header (consistent with cold-data semantics). `last_updated_at` for the `<TileState/>` stale-detection comes from the snapshot's `exported_at`.
- **D-24:** **No new global state** — tournament data lives in React Query cache. Filter state lives in URL params (D-13).
- **D-25:** **`api.js` extension:** add `tournamentAPI = { listSnapshots(), getSnapshot(id) }` alongside the existing `portfolioAPI`/`tradingAPI` groupings. Match the existing axios convention (interceptor strips `.data`).

### Claude's Discretion
- Exact pixel widths of the leaderboard table columns — pick sensible defaults; ensure DSR / OOS Sharpe / PSR digits don't wrap.
- Tooltip library choice — recommend the existing pattern already used by KeyMetricsStrip (CSS `:hover` + absolute-positioned div, no Radix Tooltip dependency unless one is already in `package.json`).
- Layout of the contaminated-window footer strip — keep it visually unmissable when `train_window_includes_contaminated=true` (rose icon + tooltip with reference to Phase 3 D-08).
- Whether the smoke test runs against `http://localhost:8000` (gateway) or `http://localhost:3000` (vite dev) — recommend gateway origin so the test exercises the production routing path; the dev proxy is a separate concern.
- Whether the Tournament tile is also linked from the existing top-bar navigation (Header or Dashboard cards) — recommend YES (link from PerformanceDashboard summary tiles) but don't block on that.
- Whether the smoke test loops over multiple browser engines (Firefox, WebKit) — Chromium only for v1; widen later if a Safari regression bites.
- Exact CSS color for the green ✓ ensemble badge — match Phase 6 `#5eead4` mint accent.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` — Phase 7 entry, 3 success criteria (Tournament view + Playwright smoke + integration-suite wiring), requirements mapping (DASH-04, DASH-06)
- `.planning/REQUIREMENTS.md` — DASH-04 (depends on TOURN-02), DASH-06 (smoke) acceptance text
- `.planning/PROJECT.md` — operator profile (solo, paper-trade on Bybit mainnet prices), "trust no docs" posture, recorded-tape stack constraints

### Project rules (load-bearing for this phase)
- `CLAUDE.md` — gateway route convention (`/api/<domain>/<resource>`, no `v1` prefix), four trading-mode flags, validated symbols, dev/prod proxy divergence, **api-gateway test suite must run inside the container** (host pip vs container pin)
- `wiki/decisions/` — ADR-007 (no `/v1/` prefix), any ADR touching trading-mode flags

### Prior phase context (decisions carried forward)
- `.planning/phases/06-dashboard-audit-safety-state/06-CONTEXT.md` — D-09 (gateway owns frontend-facing endpoints, no Redis indirection), D-11 (React Query staleTime convention), D-12/13/14/15 (`<TileState/>` wrapper semantics — empty / error / stale / loading), D-16 (config-driven URLs via `VITE_*`)
- `.planning/phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.md` — 15-row tile inventory; smoke driver source of truth (D-15 above)
- `.planning/phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.json` — machine-readable sidecar consumed at smoke-test runtime
- `.planning/phases/03-tournament-harness-core/03-CONTEXT.md` — D-07 (`tournament_start_ts` stamping), D-08 (`train_window_includes_contaminated` flag), D-13 (`seed=42` → `hash(seed,run_id)`, `git_sha` stamping), D-15 (`failure_reason` enum), D-16 (snapshot bind-mount), D-17 (numbered SQL migrations), D-18 (snapshot JSON is the committed artifact, SQLite is gitignored), CD-05 (parameterized SQL query DSL)
- `.planning/phases/04-tournament-significance-auto-pr/04-CONTEXT.md` — significance schema (`per_symbol`, `win_gate_passed`, `n_members`, `bootstrap_seed`), ensemble schema (`ensembles[].members`), `baseline="persistence"` / `aggregation="mean_log_returns"`, atomic-write artifact pattern
- `.planning/phases/02-integration-test-suite-runbook/02-CONTEXT.md` (and Phase 2 plans) — `bootstrap_stack`, `tape_reset`, `tmp_fresh_clone`, `force_signal`, `db_truncate`, `notification_received` fixtures, iter-fix harness, anti-mock guard

### Phase 3 / Phase 4 source code (data layer reused)
- `services/tournament-harness/migrations/0001_initial.sql` — leaderboard table schema (columns frontend renders: `architecture`, `symbol`, `horizon`, `target_mode`, `r2_returns`, `dir_acc_corrected`, `oos_sharpe`, `psr`, `dsr`, `cpcv_dsr`, `train_seconds`, `git_sha`, `tournament_start_ts`, `train_window_includes_contaminated`, `status`, `failure_reason`, `failure_stderr_tail`)
- `services/tournament-harness/app/leaderboard/snapshot.py` — `export_snapshot()` writes the committed snapshot JSON the gateway will read (`schema_version`, `config`, `rows`, `summary`)
- `services/tournament-harness/app/leaderboard/db.py` — `LeaderboardDB.list_runs()` for column-name reference (gateway can re-use field names verbatim)
- `services/tournament-harness/app/significance/artifacts.py` — `write_significance()` + `write_ensemble()` define the two extra JSON artifacts the gateway joins on demand
- `services/tournament-harness/app/significance/win_gate.py`, `bootstrap.py`, `ensemble.py` — for understanding the `win_gate_passed` semantics shown in the UI tooltip
- `services/tournament-harness/data/snapshots/` — directory the gateway RO-mounts; currently empty in dev
- `services/tournament-harness/app/main.py` — existing `/api/v1/tournaments` + `/api/v1/tournaments/{id}/runs` (intentionally NOT consumed by frontend per D-01; tournament-harness profile stays opt-in)

### Existing frontend (extension targets)
- `frontend/src/App.jsx` — Routes block; add `<Route path="/tournament" element={<TournamentDashboard/>}/>`
- `frontend/src/services/api.js` — extend with `tournamentAPI = { listSnapshots(), getSnapshot(id) }`
- `frontend/src/hooks/` — pattern for `useTournamentSnapshot.js` / `useTournamentList.js` (copy `usePerformanceMetrics.js` / `usePositions.js` shape)
- `frontend/src/components/StatusBar.jsx` — visual aesthetic reference (JetBrains Mono numeric cells, mint accent, rose for failures)
- `frontend/src/components/KeyMetricsStrip.jsx` — React Query `isLoading`/`isError` consumption pattern
- `frontend/src/components/TileState.jsx` (from Phase 6) — wrap the leaderboard table; drives empty/error/stale rendering
- `frontend/src/pages/PerformanceDashboard.jsx`, `Portfolio.jsx` — top-level page layout reference (page heading + body grid)
- `frontend/vite.config.js` — dev-proxy block to confirm `/api/tournament/*` routes through gateway

### Existing api-gateway (extension target)
- `services/api-gateway/app/main.py` — add tournament routes; existing read-only patterns to model on: `/api/risk/scorecard`, `/api/risk/capital`, `/api/trading/performance`
- `services/api-gateway/tests/conftest.py` — `test_client` fixture (read-only, no auth) for the new endpoints; tests MUST run inside the container per CLAUDE.md gotcha
- `docker-compose.unified.yml` — api-gateway volumes block; add `./services/tournament-harness/data/snapshots:/app/snapshots:ro` (RO bind-mount, no write surface from gateway)

### Tests / CI
- `tests/integration/conftest.py` — Phase 2 fixtures (`bootstrap_stack`, `tape_reset`, `tmp_fresh_clone`); extend with `tournament_snapshot_seeded` (new)
- `tests/integration/` — directory new smoke test joins (`test_dashboard_smoke.py`)
- `tests/fixtures/tournament/` — directory NEW, contains the committed deterministic `smoke-fixture.json`
- `.github/workflows/integration.yml` — existing Phase 2 workflow; add `playwright install --with-deps chromium` step before `pytest tests/integration`
- `.github/workflows/integration-ml-on.yml` — ML-on nightly variant; smoke test runs here too (same step)

### Bind-mount + filesystem
- `services/tournament-harness/data/snapshots/` — committed snapshot dir (gitignored `*.db` next to it). Gateway gets RO bind-mount per D-01.
- `tests/fixtures/tournament/smoke-fixture.json` — committed fixture seeded by `tournament_snapshot_seeded` pytest fixture per D-08

### External libraries / docs to query via context7 before planning
- `pytest-playwright` — fixture API, pytest marker conventions, screenshot/HAR/trace capture config
- `@playwright/test` — only for visual-regression context; primary driver is pytest-playwright (Python)
- `@tanstack/react-query` (already in `package.json`) — `useQuery` with `staleTime: Infinity`, `refetch` patterns
- `react-router-dom` `useSearchParams` — URL-state pattern for filters/sort (D-13)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`<TileState/>`** (Phase 6, `frontend/src/components/TileState.jsx`) — empty / error / stale / loading wrapper. Drop in around the leaderboard `<table>` body. Tournament view's empty-state copy + per-cell `last_updated_at` driven by snapshot's `exported_at`.
- **`StatusBar.jsx` Cell helper** — JetBrains Mono numeric cell with color accents; reuse the styling vocabulary for the leaderboard `dsr` / `oos_sharpe` / `psr` columns.
- **`api.js` axios client** — baseURL `/api`, response interceptor strips `.data`, 20s timeout. `tournamentAPI` slots in next to existing groupings.
- **`LeaderboardDB.list_runs()`** — backend can shell-call `tournament leaderboard list --tournament-id ... --json` for verification, but the gateway does NOT depend on the tournament-harness service running — it reads the snapshot file directly per D-01.
- **`export_snapshot()` summary block** — already computes `n_rows`, `n_success`, `n_failed`, `architectures[]`, `symbols[]`. Gateway's list endpoint just reads each snapshot file and returns its `summary` block + `tournament_id` + `exported_at`. No re-computation.
- **Phase 4 atomic-write pattern** (`_atomic_write` helper in `services/tournament-harness/app/significance/artifacts.py`) — if Phase 7 needs to write any file (e.g., the Tournament tile audit row), reuse this pattern.
- **Phase 2 `bootstrap_stack` + `tape_reset` fixtures** — entire recorded-tape stack comes up via existing pytest infrastructure. Smoke test reuses.

### Established Patterns
- **`/api/<domain>/<resource>` route shape (no `v1` prefix)** — new routes are `/api/tournament/snapshots`, `/api/tournament/snapshots/{id}`. Despite tournament-harness itself using `/api/v1/...`, the gateway-side route follows CLAUDE.md / ADR-007.
- **api-gateway = sole frontend ingress in prod, vite dev proxy in dev** — frontend always hits `/api/...` and lets vite rewrite to `http://localhost:8000` in dev, gateway in prod.
- **5-second poll cadence is the dashboard default; tournament view deliberately bucks this** — cold data, `staleTime: Infinity` + manual refetch (D-23). Carry the rationale in code comments so future contributors don't "fix" it.
- **Snapshot JSON is the single source of truth for tournament data** (Phase 3 D-18). DB is gitignored and rebuildable; the artifact in git is the snapshot. Frontend NEVER queries SQLite.
- **Significance artifacts (Phase 4) are produced AFTER snapshot export** — the gateway tolerates missing `{tournament_id}.ensemble.json` / `.significance.json` and returns `null` for those fields. Frontend renders "—" in the significance column.
- **`<table>`-first rendering** — no TanStack Table; the existing dashboard tables (TradeHistory, ActiveTrades) use raw `<table>` with the Editorial Trading Floor styling.
- **URL params drive filter state** — Phase 6 dashboards use `useSearchParams`; reuse the same pattern (D-13).
- **Test runs inside the container for api-gateway** — host pip vs container pin gotcha; per CLAUDE.md, use `docker exec crypto-bot-api-gateway pytest`. Smoke test (running in `tests/integration/`) is OUTSIDE this constraint — it drives the gateway over HTTP from a separate pytest process, no FastAPI version coupling.

### Integration Points
- **`services/api-gateway/app/main.py`** — add `@app.get("/api/tournament/snapshots")` + `@app.get("/api/tournament/snapshots/{tournament_id}")`. Both read from `/app/snapshots/*.json` (mounted from `services/tournament-harness/data/snapshots/` per D-01).
- **`docker-compose.unified.yml` api-gateway volumes block** — add the RO bind-mount `./services/tournament-harness/data/snapshots:/app/snapshots:ro`. No service `depends_on` change; gateway doesn't need tournament-harness running.
- **`frontend/src/App.jsx`** — register `<Route path="/tournament" element={<TournamentDashboard/>}/>`; add nav link in the top-bar.
- **`frontend/src/pages/TournamentDashboard.jsx`** (new) — top-level page; renders selector + filter chips + table inside `<TileState/>`.
- **`frontend/src/components/TournamentLeaderboard.jsx`** (new) — pure presentational table component; props = rows + significance map.
- **`frontend/src/hooks/useTournamentSnapshot.js`** + **`useTournamentList.js`** (new) — React Query wrappers.
- **`frontend/src/services/api.js`** — `tournamentAPI = { listSnapshots(), getSnapshot(id) }`.
- **`tests/integration/conftest.py`** — add `tournament_snapshot_seeded` fixture: copies `tests/fixtures/tournament/smoke-fixture.json` into `services/tournament-harness/data/snapshots/smoke-tape-fixture.json` before yield, deletes on teardown.
- **`tests/integration/test_dashboard_smoke.py`** (new) — single-file Playwright smoke; iterates `06-TILE-AUDIT.json` rows; per-row assertion logic switched on `verdict`.
- **`.github/workflows/integration.yml`** — insert `- run: playwright install --with-deps chromium` step before the `pytest tests/integration` step.
- **`.planning/phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.md` + `.json`** — add the Tournament tile row (D-16); commit the addition as part of Phase 7's setup.

### Friction surfaces to watch
- **EMERGENCY_STOP file/directory ambiguity** (CLAUDE.md + Phase 6 STRUCTURE.md note) — irrelevant to this phase's code paths but the safety-state cell smoke assertion (D-17) needs to render against the recorded-tape default state (EMERGENCY_STOP absent or directory-shaped); pin the expected state in the smoke fixture setup.
- **WSL2 BuildKit hangs** — Phase 2 RUNBOOK has the workaround; pytest-playwright install also needs the container build path to succeed. Use `DOCKER_BUILDKIT=0` in the CI if reproducer surfaces.
- **api-gateway version pin (fastapi 0.109)** — `HTTPBearer` returns 403 not 401 in the container; smoke test goes over HTTP so it's insulated, but new gateway unit tests for `/api/tournament/*` MUST run inside the container.
- **Phase 3 D-08 contamination flag** (`train_window_includes_contaminated=true` when window crosses 2026-04-25) — make the footer-strip warning unmissable (D-10 footer), so the operator never overlooks it.
- **`profiles: [tournament]`** keeps `tournament-harness` off by default. Confirm the gateway's RO bind-mount works even when the service isn't running — docker creates the mount at gateway start regardless of the harness container state.
- **`/api/v1/tournaments` (tournament-harness service)** vs `/api/tournament/snapshots` (gateway) — same data, different sources. Document the intentional split in `services/api-gateway/app/main.py` comment so future contributors don't "fix" the duplication.
- **Dev proxy vs gateway origin** — vite dev proxy routes `/api/*` to `:8000`. Smoke test targets gateway origin directly to mirror prod ingress (Claude's discretion above).

</code_context>

<specifics>
## Specific Ideas

- **Snapshot as the contract.** The dashboard is downstream of Phase 3's snapshot JSON (D-01) — same file Phase 4 reads. No second source of truth. If a column needs to appear in the UI, it must be in the leaderboard schema OR derivable from the snapshot's `config` block.
- **Smoke test == audit-driven.** ROADMAP names 4 major tiles, but the durable contract is `06-TILE-AUDIT.json` (15 rows + Tournament). Driving the smoke from the audit JSON means: when Phase 6 adds/removes/relabels a tile, the smoke updates automatically. No drift between docs and runtime assertions.
- **No live SQLite path in v1.** Even though `tournament-harness:8010` already exposes `/api/v1/tournaments`, the gateway intentionally reads files instead (D-01). Two reasons: (a) `--profile tournament` opt-in stays opt-in, (b) frontend has data even on a fresh clone where no tournament has been run yet (provided someone committed at least one snapshot — for v1, the smoke fixture suffices).
- **Significance column gives operator one number to scan.** Phase 4's `win_gate_passed` is a single bool per symbol — UI hoists that into one badge column rather than asking the operator to read four p-values per row. Tooltip carries the detail for the curious.
- **Tournament view bucks the 5-second poll.** Tournaments don't update mid-session; cold data, manual refresh. Code comment in the hook plus mention in CONTEXT.md so it doesn't get "fixed" later (specifically callouts the rationale to avoid the same code review feedback Phase 6's StatusBar got).
- **Smoke = single CI command.** `pytest tests/integration` is the existing Phase 2 gate. Adding `pytest-playwright` keeps the gate single. No `npx playwright test` shim, no parallel CI job, no two failure modes to debug.

</specifics>

<deferred>
## Deferred Ideas

- **Live SQLite read path** (`tournament-harness:8010` `/api/v1/tournaments`) — v2. Useful if the operator wants live progress during a running tournament; out of v1.
- **Per-run drill-down page** — single-run detail view with full HP grid, train logs (`failure_stderr_tail`), CPCV breakdown. v2.
- **Cross-tournament comparison view** — time-series of best DSR per symbol, leaderboard diff between consecutive tournaments. v2.
- **Trigger tournament run from UI** — operator-driven CLI is sufficient and safer (no JS RCE surface). v2 with auth + audit logging.
- **WebSocket / SSE push for live tournament progress** — depends on tournament-harness exposing a progress event stream. v2.
- **Embed significance metadata into snapshot at export time** — Phase 3 schema bump. Cleaner contract but breaks reproducibility of historical snapshots; defer until a second consumer needs it.
- **Visual regression / screenshot diffing in Playwright** — `playwright.config.js` `toHaveScreenshot` + `--update-snapshots` workflow. v2; v1 smoke asserts presence + non-emptiness, not pixel-exact rendering.
- **Multi-browser smoke** (Firefox, WebKit) — Chromium only for v1.
- **Mobile responsive layout** for `/tournament` — solo operator on desktop; v2.
- **Auth / RBAC on `tournament run` mutations** — out of scope; CLI is operator-only.
- **Pagination / virtualization on the leaderboard table** — v1 tournament configs have on the order of architectures × symbols × HP-grid-points rows (small enough for native scroll). Phase 5's actual T0.1.x experiment shipped INSUFFICIENT_DATA — real-world row counts low. Re-evaluate at v2.
- **Real `last_updated_at` on every body-tile endpoint** — Phase 6 W-02 scope-down deferred this to Phase 7. Out of scope for *this* phase too — tournament endpoint emits its own `exported_at`, but back-filling the other 9 body-tile endpoints with `last_updated_at` is a separate orthogonal task. Defer to v2 / a dedicated DASH-07.
- **Stale-data threshold for the snapshot's `exported_at`** — Tournament snapshots can be days old without being "stale" in the dashboard sense. Show `exported_at` literally in the footer; no automatic stale badge.

</deferred>

---

*Phase: 07-tournament-view-smoke-test*
*Context gathered: 2026-05-14*
*Mode: --auto (user opted out of clarifying questions; every D-NN is the recommended default — edit this file to override before `/gsd-plan-phase 7`)*
