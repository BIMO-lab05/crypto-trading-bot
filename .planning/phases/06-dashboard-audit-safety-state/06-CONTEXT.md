# Phase 6: Dashboard Audit & Safety State - Context

**Gathered:** 2026-05-13
**Status:** Ready for planning

<domain>
## Phase Boundary

The React dashboard reflects real backend state for every tile, prominently surfaces operator safety posture (TRADING_MODE, `auto_trading_enabled`, 5%-daily-loss kill-switch, `EMERGENCY_STOP` file, `ENABLE_ML_PREDICTIONS`), eliminates hardcoded backend URLs in frontend source, and renders explicit empty/error/stale states instead of silent zeros.

**In scope:**
- Audit every tile/route, map to its backing endpoint, verify response shape against running stack
- New aggregated `/api/config/safety-state` endpoint on api-gateway
- Extension of existing `StatusBar.jsx` with three new safety cells + PAPER/LIVE viewport border
- Shared `<TileState/>` empty/error/stale/loading wrapper applied to every audited tile
- Migrate the single remaining hardcoded `ws://localhost:8000/ws` to `VITE_WS_URL`; document `VITE_API_BASE_URL` convention in `vite.config.js`
- Stale-data badge driven by backend `last_updated_at` (per-tile threshold) — limited to safety-state + LABELED_STALE tiles in Phase 6 (see deferred)

**Out of scope (Phase 7 or beyond):**
- Tournament leaderboard view (DASH-04)
- Playwright smoke test (DASH-06)
- WebSocket push for safety state (server-side `/ws/metrics` route doesn't exist; v2 backlog)
- Mobile responsive layout (v2)
- Rebuild of dashboard routing / page structure

</domain>

<decisions>
## Implementation Decisions

### Audit deliverable
- **D-01:** Ship BOTH `06-TILE-AUDIT.md` (markdown table: tile → component file → backing endpoint → expected shape → observed shape → verdict) AND `scripts/audit_tiles.py` (runtime probe that hits every documented endpoint against a running stack and asserts the shape recorded in the table). The markdown is the operator artifact; the script is the regression gate that future CI can run against the recorded-tape stack.
- **D-02:** Each audit row gets one verdict from `{FIXED, LABELED_STALE, REMOVED}`. `FIXED` ⇒ delta committed in this phase. `LABELED_STALE` ⇒ UI renders the "stale" badge (via `<TileState/>`) and the row is tracked in Phase 7 / backlog. `REMOVED` ⇒ the tile is deleted from the dashboard because the backing capability is dead. Verdicts are reviewed by the operator before the audit table is committed; this is the mechanism that keeps Phase 6 finite.

### Safety state — content
- **D-03:** Surface exactly the five flags named in ROADMAP success criterion 2: `TRADING_MODE` (PAPER/LIVE), `auto_trading_enabled`, kill-switch (mapped to RISK-01 5%-daily-loss circuit-breaker state), `EMERGENCY_STOP` file presence + mtime, `ENABLE_ML_PREDICTIONS`. Per-trade-cap percentages and daily-P&L-vs-budget remain in body tiles, not the safety strip.
- **D-04:** "Kill-switch" maps to the **5% daily-loss circuit-breaker** state (ARMED / TRIPPED), sourced from trading-engine's risk-budget module. The 5-consecutive-losses limit is also part of RISK-01 but is NOT shown in the safety strip (lives in a risk tile if anywhere).

### Safety state — surfacing
- **D-05:** Extend the existing `frontend/src/components/StatusBar.jsx` (fixed-bottom strip; already shows `auto_trading_enabled` + emergency). Add three new cells: `TRADING_MODE` pill, kill-switch ARMED/TRIPPED badge, ML toggle ON/OFF. No new SafetyHeader component. No layout-shift in `App.jsx`.
- **D-06:** PAPER vs LIVE is shown as a **color-coded pill** (PAPER green / LIVE red) in StatusBar AND as a **persistent 1-2px viewport border** around the entire dashboard viewport (red when LIVE, neutral/green when PAPER). Border is the secondary affordance so operator cannot miss LIVE during scroll. `BYBIT_TESTNET` (price source) is NOT shown in the strip — covered by the dev/prod doc in `vite.config.js`.
- **D-07:** `EMERGENCY_STOP` indicator renders **Active/Inactive badge + last-modified timestamp** ("ACTIVE — since 12:43:01" / "INACTIVE"). Reason text (if file content carries one) is deferred — current implementation writes empty file.

### Safety state — backend wiring
- **D-08:** **New aggregated endpoint `GET /api/config/safety-state`** on api-gateway. Response schema:
  ```
  {
    "trading_mode": "PAPER" | "LIVE",
    "paper_trading_mode": true | false,
    "auto_trading_enabled": true | false,
    "emergency_stop": { "active": true | false, "mtime": "<ISO ts or null>" },
    "ml_predictions_enabled": true | false,
    "kill_switch": { "daily_loss_armed": true | false, "daily_pnl_pct": <float>, "tripped": true | false },
    "last_updated_at": "<ISO ts>"
  }
  ```
  Single poll, single source of truth. Do NOT pollute `/api/trading/status` with config keys.
- **D-09:** **api-gateway owns the endpoint.** It reads its own env (`TRADING_MODE`, `PAPER_TRADING_MODE`, `ENABLE_ML_PREDICTIONS`) and proxies trading-engine for `auto_trading_enabled`, `emergency_stop`, and risk-budget (kill-switch). One network hop from frontend. Matches existing ingress pattern (gateway = sole frontend entry in prod).
- **D-10:** **`EMERGENCY_STOP` file is read by trading-engine only.** Gateway proxies trading-engine for `emergency_stop.{active, mtime}`. No new bind-mount on api-gateway. No Redis indirection. Preserves single source of truth (RISK-03 — trading-engine reads at STEP-0 of loop).
- **D-11:** Frontend polls `/api/config/safety-state` via React Query with **`staleTime: 5000ms`**, matching existing StatusBar/usePositions cadence. New hook `frontend/src/hooks/useSafetyState.js`. No SSE/WebSocket in this phase.

### Empty / error / stale rendering (DASH-05)
- **D-12:** New shared component `frontend/src/components/TileState.jsx` wraps every audited tile body. Tiles refactored to: `<TileState status={...}>{render body}</TileState>` (or a `useTileState({query, dataIsEmpty, lastUpdatedAt})` hook returning a status object the component consumes).
- **D-13:** `<TileState/>` distinguishes four signals: `loading` (skeleton, React Query `isFetching && !data`), `empty` (`isSuccess && (data == null || data.length === 0)`), `error` (`isError`), `stale` (`backend last_updated_at` past per-tile threshold). Renders skeleton, "No data yet", "Failed (HTTP code): short message [Retry]", or a corner stale badge respectively.
- **D-14:** Error rendering shows **HTTP status code + short message + Retry button**. Retry calls React Query `refetch()`. No stack traces, no raw axios `error.message` text. Example: `"Failed (503): service unavailable. [Retry]"`.
- **D-15:** Stale-data detection is **backend-driven**. Endpoints serving tile data add `last_updated_at` to their response (or set `X-Data-Age` header). `<TileState/>` compares to `Date.now()` and renders the badge when delta exceeds the per-tile threshold (e.g., ticker 60s, performance 5min). Threshold map lives in `frontend/src/components/TileState.jsx` constants. Backend changes added per tile **only where the audit verdict requires it**. **Phase 6 scope-down (per W-02 checker feedback):** real backend `last_updated_at` is emitted by ONLY `/api/config/safety-state` (Plan 6-02). Other tile endpoints get `last_updated_at` in Phase 7 (tracked via 06-TILE-AUDIT.md `last_updated_at?` column rows where value=`no`). Phase 6 LABELED_STALE tiles use `forceStale={true}` prop instead of real backend signal.

### Config-driven URLs (DASH-02)
- **D-16:** Migrate the single remaining `ws://localhost:8000/ws` literal in `frontend/src/hooks/useGatewayWebSocket.js:34` to `import.meta.env.VITE_WS_URL` with the current dev value kept as fallback. Document the `VITE_API_BASE_URL` + `VITE_WS_URL` convention in the `vite.config.js` comment block alongside the existing dev/prod proxy doc. Grep gate (per ROADMAP success criterion 3): `grep -rn "http://localhost\|ws://localhost" frontend/src/` must return only documented dev-config defaults.

### Claude's Discretion
- Specific markdown structure for `06-TILE-AUDIT.md` (column order, sort order, how grouping by route works) — keep operator-readable.
- `<TileState/>` visual styling — match existing Editorial Trading Floor aesthetic from StatusBar.jsx and KeyMetricsStrip.jsx.
- Exact threshold values per tile in the staleness map — pick sensible defaults (ticker 60s, performance 5min, signals 30s, etc.); operator can tune.
- Whether the new gateway endpoint requires auth — recommend no (it's read-only config disclosure for the dashboard); decide alongside the gateway-owner work.
- Audit script CLI shape (`scripts/audit_tiles.py --against http://localhost:3000`) — single-binary, prints PASS/FAIL per tile, exits non-zero on any FAIL.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` — Phase 6 entry, 4 success criteria, requirements mapping (DASH-01/02/03/05)
- `.planning/REQUIREMENTS.md` — DASH-01, DASH-02, DASH-03, DASH-05 acceptance text (Phase 7 carries DASH-04/06)
- `.planning/PROJECT.md` — operator profile (solo, paper-trade on Bybit mainnet prices), "trust no docs" posture, constraints

### Project rules (load-bearing for this phase)
- `CLAUDE.md` — gateway route convention (`/api/<domain>/<resource>`, no `v1`), four trading-mode flags, EMERGENCY_STOP semantics, validated symbols, dev/prod proxy divergence
- `wiki/decisions/` — ADR directory; if any ADR touches risk-cap state, EMERGENCY_STOP, or trading-mode flags, read before wiring the safety-state endpoint

### Existing frontend code (audit + extension targets)
- `frontend/src/services/api.js` — central axios client, `/api` baseURL, 78 endpoint methods grouped by domain (portfolio / trading / market / ML / sentiment / analysis)
- `frontend/src/components/StatusBar.jsx` — existing fixed-bottom safety strip; extend here per D-05
- `frontend/src/components/KeyMetricsStrip.jsx` — reference pattern for `isLoading`/`isError` consumption (currently read, not rendered explicitly)
- `frontend/src/components/EmergencyStop.jsx` + `frontend/src/components/CommandPalette.jsx` — existing `POST /api/portfolio/emergency-stop` callers
- `frontend/src/hooks/usePortfolio.js`, `usePositions.js`, `useAutoTrader.js`, `useTicker.js`, `useSignals.js`, `usePerformanceMetrics.js`, `useChartData.js`, `usePhase3.js` — full list of polling hooks to audit
- `frontend/src/hooks/useGatewayWebSocket.js:34` — single remaining `ws://localhost` literal (DASH-02 target)
- `frontend/vite.config.js` — dev/prod proxy doc block; safety-state border styling must coexist with cache-control headers
- `frontend/src/pages/` — `PerformanceDashboard.jsx`, `Phase1Dashboard.jsx`, `Phase3Dashboard.jsx`, `Portfolio.jsx`, `Settings.jsx` — top-level audit scope

### Existing backend (safety-state sources)
- `services/api-gateway/app/main.py` — 78 routes; safety endpoint added here. Existing routes relevant: `/api/trading/status`, `/api/trading/performance`, `/api/portfolio`, `/api/portfolio/emergency-stop`, `/api/risk/scorecard`, `/api/risk/capital`
- `services/trading-engine/app/main.py` — `/status` (returns `auto_trading_enabled`, emergency); `/api/v1/trading/status` (auto-trader stats); `/api/v1/risk/budget/*` (kill-switch state). All proxied for D-09.
- `services/trading-engine/app/models/response.py` — `StatusResponse` schema (extend or proxy for emergency_stop.mtime)
- `services/trading-engine/app/risk/dynamic_risk_budget.py` — risk-budget module that owns the 5%-daily-loss circuit-breaker state (D-04)
- Env vars (set in `docker-compose.unified.yml` + `.env`): `TRADING_MODE`, `PAPER_TRADING_MODE`, `BYBIT_TESTNET`, `ENABLE_ML_PREDICTIONS`, `AUTO_TRADING_ENABLED`, `LIVE_TRADING_ACK`

### Bind-mount + file
- `EMERGENCY_STOP` (repo root) — RO bind-mount into trading-engine `/app/EMERGENCY_STOP`. NOT mounted in api-gateway per D-10. Currently exists as directory at repo root (per `.planning/codebase/STRUCTURE.md` note — confirm before code changes).

### Tests
- `services/api-gateway/tests/conftest.py` — `admin_client` fixture (admin-guarded routes); plain `test_client` for read-only endpoints. The new `/api/config/safety-state` is read-only — uses `test_client`.
- Tests for api-gateway MUST run inside the container (`docker exec crypto-bot-api-gateway pytest`) — host pip has fastapi 0.136 (returns 401 from HTTPBearer); container pins fastapi 0.109 (returns 403). Spurious failures only on host.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`StatusBar.jsx`** — fixed-bottom 6-cell strip with `Cell` helper component, JetBrains Mono font, color accents already wired for `emergency`/`isRunning`/P&L sign. Extending it for D-05 is a 3-cell addition; the styling vocabulary is already there.
- **`useTradingStatus`, `usePositions`, `usePortfolio` hooks** — React Query polling pattern (5-10s cadence); copy for `useSafetyState`.
- **`KeyMetricsStrip.jsx`** — already reads `isLoading`/`isError` from React Query but doesn't render explicit messages. Best example of where `<TileState/>` plugs in.
- **`api.js` axios client** — baseURL `/api`, 20s timeout, response interceptor strips `.data`. New safety-state hook calls `api.get('/config/safety-state')`.
- **api-gateway routing pattern** — `@app.get("/api/<domain>/...")` on `main.py`, calls into per-service async clients. New endpoint mirrors `/api/trading/status` pattern but is read-only and reads gateway env directly.

### Established Patterns
- **Gateway is sole frontend ingress in prod** — dev proxy bypasses it (vite.config.js); test the safety-state endpoint against a running gateway, not the bypass path. Matches CLAUDE.md "Project rules" verification standards.
- **`/api/<domain>/<resource>` route shape** — no `v1` prefix. The new endpoint is `/api/config/safety-state`, NOT `/api/v1/config/safety-state`.
- **EMERGENCY_STOP RO bind-mount** — trading-engine has it at `/app/EMERGENCY_STOP`. Per RISK-03 commits `4547df5` + `1fb9008` it's read at STEP-0 of trade loop. Single reader, no contention.
- **Editorial Trading Floor aesthetic** — `#f5f3ee` neutral, `#5eead4` mint accent, `#fb7185` rose for danger, `#a09e98` muted. JetBrains Mono for numeric cells, Manrope for narrative. New cells + `<TileState/>` must match.
- **Pre-existing safety endpoint pattern** — `POST /api/portfolio/emergency-stop` requires `admin_client` fixture (auth-guarded write). The new READ endpoint is unauthenticated by D-09 default (read-only config disclosure for the dashboard).

### Integration Points
- **api-gateway/main.py** — add `@app.get("/api/config/safety-state")` route + helper that fans out to trading-engine and reads local env.
- **trading-engine** — likely needs to expose `emergency_stop.mtime` (currently only `active` per StatusResponse). Minimal addition; reuse existing file-stat in main.py:273.
- **StatusBar.jsx** — three new `<Cell/>` invocations + viewport border styling at the root layout level (in `App.jsx`).
- **App.jsx** — wraps content with `<div className={`safety-border safety-border--${trading_mode.toLowerCase()}`}>` (or similar). Class drives the border color via CSS.
- **TileState.jsx (new)** — drop-in wrapper around every existing tile body. Tiles to audit: `KeyMetricsStrip`, `ActiveTrades`, `TradeHistory`, `PortfolioCard`, `PerformanceAnalyticsPanel`, `TradingSignals`, `TradingEnhancementsPanel`, `HybridStrategyPanel`, `PriceChart`, `PriceTickerGrid`, `RegimeIndicator`, `Sparkline`, `Phase1Dashboard`, `Phase3Dashboard`, `Portfolio` page tiles, `Settings` page (no data tiles — skip).
- **scripts/audit_tiles.py** — new file, lives next to existing operational scripts under `scripts/`. Loads tile-table fixture (JSON or YAML derived from `06-TILE-AUDIT.md`), hits each documented endpoint, validates shape against expected, prints summary + exits non-zero on mismatch.
- **EMERGENCY_STOP path** — confirm whether it's currently a file or a directory at repo root before wiring `mtime` reads (`STRUCTURE.md` notes "Currently exists as directory at repo root" — likely stale, but verify).

</code_context>

<specifics>
## Specific Ideas

- **PAPER/LIVE border** is the primary "you cannot miss this" affordance. Pill alone proven insufficient by ROADMAP success criterion 2 ("at first glance").
- **5-second poll cadence** is deliberate: matches existing StatusBar fields, so all safety/status visuals refresh together. No mixed cadences.
- **Stale threshold map per tile** — not all tiles age the same. Ticker freshness <60s; performance metrics aggregate over hours, so 5-10min is fine. Picking right thresholds prevents fake "stale" panics and prevents stale-but-not-flagged blind spots.
- **Audit verdict `LABELED_STALE`** is the safety valve that keeps Phase 6 finite. If TOURN-02 tournament view tile shows up in audit but its backing data depends on Phase 7, it gets the `stale` badge and rolls into Phase 7 backlog — Phase 6 doesn't stall on it.
- **No SSE/WebSocket in this phase.** Existing `useGatewayWebSocket.js` is the only WS surface and the server route status is dev/prod-divergent. Adding push for safety state is Phase 7+ work.

</specifics>

<deferred>
## Deferred Ideas

- **Tournament view tile** (DASH-04) — Phase 7. If it appears in tile audit, verdict = `LABELED_STALE` until Phase 7 wires it.
- **Playwright smoke test for dashboard** (DASH-06) — Phase 7. Uses `06-TILE-AUDIT.md` as the inventory it walks through, asserting each tile renders non-empty against recorded-tape.
- **WebSocket push for safety state** — v2 / Phase 7+; requires server-side `/ws/metrics` route that doesn't exist.
- **Reason text for EMERGENCY_STOP** — would need backend to persist the reason from `POST /api/portfolio/emergency-stop`; currently the file is empty. Defer to a later phase if operator wants the audit trail.
- **Full `frontend/src/config.js` module** — picked the minimal env-var migration (D-16). If more services add direct frontend endpoints, formalize a central config module then.
- **Modal-on-LIVE-flip** — proposed but rejected for friction in PAPER → LIVE smoke tests; the persistent red border is sufficient affordance.
- **Per-trade-cap + daily-P&L in safety strip** — out of D-03. Belongs in a risk tile in the dashboard body.
- **Auth on `/api/config/safety-state`** — keeping it open in this phase as read-only config disclosure for the local dashboard. If gateway grows public exposure later, reconsider.
- **Per-tile `last_updated_at` on non-safety-state endpoints** — Phase 7 (W-02 scope-down per checker B-01/W-02). Phase 6 ships real `last_updated_at` ONLY on `/api/config/safety-state`. Other tile endpoints get the field in Phase 7, tracked via the `last_updated_at?` column in `06-TILE-AUDIT.md` (rows with value=`no` are the Phase 7 work-list). Phase 6 LABELED_STALE tiles get the stale badge from the `forceStale={true}` prop in `<TileState/>` (verdict-driven), not from a real backend timestamp.

</deferred>

---

*Phase: 06-dashboard-audit-safety-state*
*Context gathered: 2026-05-13*
*Revised: 2026-05-13 (B-01 + W-02 scope-down per checker feedback)*
</content>
