# Roadmap: Crypto Trading Bot

## Milestones

- ✅ **v1.0** — Bootstrap & tape, integration suite, tournament harness, significance + auto-PR, ML post-V0 cleanup, dashboard safety + smoke (Phases 1, 2, 3, 4, 5, 6, 7, 7.1, 7.2) — shipped 2026-05-15
- ✅ **v1.1 Path to LIVE** — Pre-LIVE preflight, ML re-enablement gate, path-to-LIVE dashboard tile, carry-in closure harnesses, CI recovery (Phases 8, 9, 10, 11.1, 12 — Phase 11 superseded by 11.1) — shipped 2026-05-18
- 🚧 **v1.2 Polish & Real-Time** — Server-side `/ws/metrics` push (replace 5s REST polling), mobile-friendly responsive dashboard (≤768px), planning-tooling hardening (Phases 13, 14, 15) — planning

## Phases

<details>
<summary>✅ v1.0 (Phases 1–7.2) — SHIPPED 2026-05-15</summary>

- [x] Phase 1: Bootstrap & Recorded Tape (4/4 plans) — completed 2026-05-06
- [x] Phase 2: Integration Test Suite & RUNBOOK (10/10 plans) — completed 2026-05-08
- [x] Phase 3: Tournament Harness Core (9/9 plans) — completed 2026-05-09
- [x] Phase 4: Tournament Significance & Auto-PR (10/10 plans) — completed 2026-05-12
- [x] Phase 5: ML Cleanup (post-V0) (4/4 plans) — completed 2026-05-13
- [x] Phase 6: Dashboard Audit & Safety State (5/5 plans) — completed 2026-05-14
- [x] Phase 7: Tournament View & Smoke Test (6/6 plans) — completed 2026-05-14
- [x] Phase 7.1: Smoke Test Bugfixes (1/1 plan) — completed 2026-05-15
- [x] Phase 7.2: Phase3Dashboard Skeleton-Loader Fix (1/1 plan) — completed 2026-05-15

Full milestone archive: [`.planning/milestones/v1.0-ROADMAP.md`](milestones/v1.0-ROADMAP.md)
Audit: [`.planning/milestones/v1.0-MILESTONE-AUDIT.md`](milestones/v1.0-MILESTONE-AUDIT.md) (`gaps_found` — operator items + 1 unsatisfied REQ carried into v1.1)

</details>

<details>
<summary>✅ v1.1 Path to LIVE (Phases 8–12) — SHIPPED 2026-05-18</summary>

- [x] Phase 8: Pre-LIVE Preflight (5/5 plans) — completed 2026-05-16
- [x] Phase 9: ML Re-enablement Gate (3/3 plans) — completed 2026-05-17
- [x] Phase 10: Path-to-LIVE Dashboard (3/3 plans) — completed 2026-05-17
- [⊘] Phase 11: Carry-In Closure — *superseded by Phase 11.1*
- [x] Phase 11.1: Carry-In Closure Harnesses (LIVECLOSE-01..05) (7/7 plans) — completed 2026-05-18
- [x] Phase 12: CI Recovery (1/1 plan) — completed 2026-05-18

Full milestone archive: [`.planning/milestones/v1.1-ROADMAP.md`](milestones/v1.1-ROADMAP.md)
Audit: [`.planning/milestones/v1.1-MILESTONE-AUDIT.md`](milestones/v1.1-MILESTONE-AUDIT.md) (`gaps_found` reconciled at close — audit predates Phase 11.1 + 12 wave-3 verification; 17/19 deliverables shipped, 2 operator-blocked on OP-04 GH Actions billing)

**v1.1 carries into v1.2 as operator actions only (no code debt):**

- LIVECLOSE-01..05 harness execution (wall-clock-bound)
- CIRESTORE-01 + CIRESTORE-02 first green CI runs (blocked on OP-04)

</details>

### 🚧 v1.2 Polish & Real-Time (In Progress)

**Milestone Goal:** Replace the 5s REST polling layer that powers the dashboard with a server-pushed `/ws/metrics` WebSocket stream, ship a mobile-friendly responsive layout (≤768px single-column reflow), and harden planning tooling against three recurring frictions identified in v1.0/v1.1 retros (one-liner discipline, umbrella-phase supersession, audit-timing drift). Pure code scope; no wall-clock dependencies; no new compose services (backend work stays inside `api-gateway` and reuses existing Redis for pub/sub fanout).

- [x] **Phase 13: Bybit-Connector Market-Data Centralization** — Audit every service, script, backtester, and test for direct Bybit API access (`pybit` imports, hardcoded `api.bybit.com` / `wss://stream.bybit` URLs) or alternate market-data source outside `services/bybit-connector/`; refactor each hit to route through bybit-connector REST endpoints (`/api/v1/market/ticker|kline|orderbook|recent-trade|funding-rate/history|instruments-info`); CI grep gate prevents new direct-Bybit imports outside the connector; RUNBOOK symptom for stale market-data chain. (Rescoped 2026-05-21 — replaces former "Real-Time WebSocket Push" scope, which is deferred to v2.) (completed 2026-05-22)
- [x] **Phase 14: Mobile Responsive Dashboard** — Viewport meta + Tailwind breakpoint audit, single-column reflow ≤768px across `Dashboard.jsx`/`PathToLiveTile.jsx`/`KeyMetricsStrip`/`TournamentDashboard.jsx` with no information loss, pytest-playwright matrix smoke at iPhone SE (375×667) + iPad portrait (768×1024) asserting no horizontal scroll + ≥44px touch targets (completed 2026-05-22)
- [ ] **Phase 15: Planning-Tooling Hardening** — `plan.validate` rejects 5 placeholder one-liner patterns (pre-commit + CI), `roadmap.analyze` auto-marks umbrella phases as superseded when decimal child covers their REQ set, `/gsd-complete-milestone` refuses to archive if latest milestone-audit `audited_at` predates most recent phase VERIFICATION.md by >1h (replays v1.1 13h-gap scenario as fixture)

## Phase Details

> v1.0 phases (1–7.2) and v1.1 phases (8–12) detail sections live in their respective milestone archives under `.planning/milestones/`. Only the active v1.2 phases (13, 14, 15) carry full detail blocks below.

### Phase 13: Bybit-Connector Market-Data Centralization

> Rescoped 2026-05-21 — former "Real-Time WebSocket Push" scope deferred to v2; plan files dropped. Discuss-phase to follow for fresh requirement/plan derivation.

**Goal**: Make `services/bybit-connector/` the sole Bybit-facing service in the codebase. Repo-wide audit identifies every direct Bybit API call (pybit imports, `api.bybit.com` / `wss://stream.bybit` URLs) and alternate market-data source (CoinGecko, etc.) outside the connector; each hit is refactored to consume bybit-connector REST endpoints (`/api/v1/market/ticker|kline|orderbook|recent-trade|funding-rate/history|instruments-info`). CI grep gate locks the new contract and RUNBOOK documents the chain.
**Depends on**: Nothing (no upstream v1.2 blocker; consumes existing `bybit-connector` REST surface)
**Requirements**: BC-01, BC-02, BC-03, BC-04, BC-05, BC-06, BC-07
**Success Criteria** (what must be TRUE):

  1. `tests/ci/test_no_bybit_bypass.py` is green on `main`. Grep across `**/*.py` outside `services/bybit-connector/` returns zero hits for `from pybit`, `import pybit`, `https?://api\.bybit\.com`, `https?://api-testnet\.bybit\.com`, `wss?://stream\.bybit`. (BC-01, BC-03)
  2. Every script under `scripts/` that previously pulled market data direct from Bybit now calls `${BYBIT_CONNECTOR_URL}/api/v1/market/...` via httpx; running any such script with bybit-connector container down fails fast with an operator-readable error pointing at `docker compose up bybit-connector`. (BC-02, D-04)
  3. `services/ml-prediction-service/app/handlers/orderbook.py` calls `${BYBIT_CONNECTOR_URL}/api/v1/market/orderbook`; `infrastructure/scripts/rotate_secrets.py` calls `${BYBIT_CONNECTOR_URL}/api/v1/account/balance` for the post-rotation auth ping. (BC-02)
  4. `services/trading-engine/app/exchanges/binance.py` is at `_archive_exchanges/binance.py`; `factory.py`, `__init__.py`, and `tests/test_multi_exchange.py` contain no live Binance references; trading-engine boots without ImportError. (BC-04)
  5. `services/market-data-service/app/config.py:58` default reads `http://localhost:8001`. (BC-05)
  6. `RUNBOOK.md` contains the new "Market-data stale or missing — bybit-connector chain broken" symptom in Diagnose/Action/Verification format. (BC-06)
  7. Integration test `tests/integration/test_bybit_connector_tape_preserved.py` asserts `MARKET_DATA_SOURCE=tape` works for refactored consumers post-refactor. (BC-07)

**Plans**: 9/9 plans pending

Plans:

- [x] 13-01-PLAN.md — BC-01: Repo-wide audit script + JSON evidence artifact
- [x] 13-02-PLAN.md — BC-03: CI grep gate scaffolding + bybit-bypass-gate workflow (RED-on-main by design)
- [x] 13-03-PLAN.md — Wave 0 RED tests for BC-02/BC-05/BC-07 (tape preservation, fail-fast, config default)
- [x] 13-04-PLAN.md — BC-02: ml-prediction-service orderbook handler + 4 download scripts refactor
- [x] 13-05-PLAN.md — BC-02: 5 scripts/collect_*.py refactor; drop last pybit import in scripts/
- [x] 13-06-PLAN.md — BC-02 + BC-05: scripts/fetch + backtesting + delete diagnostic + config-port fix
- [x] 13-07-PLAN.md — BC-02: rotate_secrets (Option A) + shared/health_check refactor; final non-Binance pybit gone
- [x] 13-08-PLAN.md — BC-04: archive Binance adapter; delete test_multi_exchange; BC-03 gate flips GREEN
- [x] 13-09-PLAN.md — BC-06 + D-10 + verify-stack 4-check phase-close

**Initial audit (2026-05-21)** — anchor for discuss-phase:

- Service runtime hits: `services/ml-prediction-service/app/handlers/orderbook.py:262`, `services/ml-prediction-service/download_missing_symbols_data.py:43`
- Script hits: `scripts/collect_180_days_data.py:56`, `scripts/collect_6months_for_ml.py:28`, `scripts/fetch_real_historical_data.py:31`, `scripts/collect_ml_training_data_simple.py:18`
- Backtesting: `backtesting/bybit_data_fetcher.py:36-38`
- Test hits: `services/market-data-service/tests/test_pagination_fix.py:36`
- Infra util (borderline): `infrastructure/scripts/rotate_secrets.py:232-234` — key-rotation validation, not market-data
- Config defect: `services/market-data-service/app/config.py:58` (default port `8002` should be `8001`; compose env overrides)
- Open question for discuss-phase: `services/trading-engine/app/exchanges/binance.py` is actively imported despite "Bybit-first" project rule — confirm intent or queue for separate cleanup
- Out-of-scope: cryptocompare news fetch in sentiment service (not market-data); coingecko in `tier1_monitor.py` (intentional cross-source divergence check)

### Phase 14: Mobile Responsive Dashboard

**Goal**: Make the dashboard usable on phone-sized viewports without horizontal scroll — establish Tailwind breakpoint tokens (`sm:640`, `md:768`, `lg:1024`, `xl:1280`) + viewport meta tag, audit every `frontend/src/components/**/*.jsx` for fixed-width violations (artifact `responsive-audit.json` lists file:line), implement single-column reflow ≤768px across `Dashboard.jsx` grid / `PathToLiveTile.jsx` (6 PREFLIGHT chip rows + 5 carry-in rows wrap to 1-col) / `KeyMetricsStrip` (horizontal scroll → 2-col) / `TournamentDashboard.jsx` (table → card list) with zero information loss; pytest-playwright Chromium matrix at iPhone SE (375×667) and iPad portrait (768×1024) asserts every dashboard tile renders with its `data-testid` visible without horizontal scroll and all navigation has ≥44px touch targets per WCAG.
**Depends on**: Nothing (no upstream v1.2 blocker; pure frontend layout work over existing components)
**Requirements**: MOBILE-01, MOBILE-02, MOBILE-03
**Success Criteria** (what must be TRUE):

  1. `tailwind.config.cjs` declares standardized breakpoints `sm:640`, `md:768`, `lg:1024`, `xl:1280`; `frontend/index.html` carries `<meta name="viewport" content="width=device-width, initial-scale=1">`; `responsive-audit.json` exists at repo root listing every fixed-width violation (`{"file": "...", "line": N, "rule": "no-hardcoded-width", "snippet": "..."}`) and the count of remaining violations across `frontend/src/components/**/*.jsx` is 0 at phase close (or every remaining entry has an explicit allowlist reason field).
  2. At viewport 375×667 (iPhone SE), `Dashboard.jsx` renders all tiles in a single column with no horizontal scroll bar; `PathToLiveTile.jsx`'s 6 PREFLIGHT chip rows + 5 carry-in rows wrap to 1-column (each row spans full width); `KeyMetricsStrip` renders as a 2-column grid (no horizontal scroll); `TournamentDashboard.jsx` renders its table as a stacked card list (one card per row); each tile still exposes its `data-testid` so the dashboard-smoke matrix can locate it.
  3. At viewport 768×1024 (iPad portrait), the layout uses the `md:` token boundary correctly — tiles can render in 2-column groups where information density allows but no element overflows `window.innerWidth`; filter chips on `TournamentDashboard` wrap onto multiple lines instead of horizontal-scrolling.
  4. `pytest tests/e2e/test_responsive_dashboard.py` is green under `.github/workflows/dashboard-smoke.yml` matrix (Chromium × {375x667, 768x1024}) and asserts for each viewport: zero elements where `boundingBox.x + boundingBox.width > window.innerWidth`, `PathToLiveTile` banner state-token (DO-NOT-FLIP / ALMOST / READY) is visible without scroll, every nav button has computed `min-height ≥ 44px` (WCAG tappable touch target).
  5. No information shown at ≥1280px is removed at ≤768px — only layout/density changes. A grep test (`tests/integration/test_no_mobile_hidden_data.py`) blocks `display: none` / `hidden md:block` patterns on any element matching `data-testid="(metric|tile|chip|row)-*"` to prevent future "just hide it on mobile" regressions.

**Plans**: 6/6 plans pending
**UI hint**: yes

Plans:
**Wave 1**

- [x] 14-01-PLAN.md — MOBILE-01: Tailwind breakpoints + audit script + responsive-audit.json (Wave 1)
- [x] 14-02-PLAN.md — MOBILE-02/03: Wave-0 test files (Playwright matrix + anti-hidden grep gate) (Wave 1)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 14-03-PLAN.md — MOBILE-02: Dashboard.jsx + KeyMetricsStrip.jsx reflow verification (Wave 2)
- [x] 14-04-PLAN.md — MOBILE-02: PathToLiveTile.jsx chip-row + carry-in-row reflow (Wave 2)
- [x] 14-05-PLAN.md — MOBILE-02: TournamentDashboard.jsx dual-render + TournamentFilterChips.jsx 44px tap-target (Wave 2)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 14-06-PLAN.md — MOBILE-03: dashboard-smoke.yml CI extension + screenshot evidence + verify-stack PASS (Wave 3)

### Phase 15: Planning-Tooling Hardening

**Goal**: Three recurring frictions from v1.0 and v1.1 retros become structurally impossible — `plan.validate` rejects placeholder one-liners (Rule N / Task N / `<one-line summary>` / empty) at pre-commit + CI time so `summary-extract` can never auto-generate garbage MILESTONES.md entries; `roadmap.analyze` auto-detects when a decimal phase's REQ set covers its umbrella parent and marks the parent `Superseded by N.M [⊘]` in ROADMAP.md (idempotent, diff-to-stdout for operator review); `/gsd-complete-milestone` refuses to archive when the latest `v[X.Y]-MILESTONE-AUDIT.md` `audited_at` predates the most recent phase's `VERIFICATION.md` modification time by >1h (the v1.1 13h-gap scenario replayed as a fixture). Override flag `--accept-stale-audit` documented for emergency closes.
**Depends on**: Nothing (planning-tooling only; no trading-engine impact; can run in parallel with Phase 13/14)
**Requirements**: TOOL-01, TOOL-02, TOOL-03
**Success Criteria** (what must be TRUE):

  1. `node ./node_modules/@gsd-build/sdk/dist/cli.js query plan.validate <path-to-PLAN.md>` exits non-zero with an explicit error naming the bad line when the plan's one-liner matches any of `/^Rule \d/`, `/^Task \d/`, `/^one-liner:\s*$/`, `/<one-line summary>/`, or empty string; exits zero on a real one-liner. Pre-commit hook (or PR-time CI job) runs `plan.validate` against every `*-PLAN.md` modified in the diff and fails the commit/PR loudly. Unit tests cover all 5 rejection patterns + 1 happy path.
  2. `node ./node_modules/@gsd-build/sdk/dist/cli.js query roadmap.analyze` detects umbrella→decimal supersession on a fixture replaying the Phase 11 → 11.1 scenario: when Phase N.M is complete AND `requirements(N.M) ⊇ requirements(N)`, the analyzer outputs a unified diff to stdout proposing the change `[ ] Phase N` → `[⊘] Phase N — superseded by N.M` and updates ROADMAP.md in place when invoked with `--apply`. Re-running with `--apply` after the change is committed produces a no-op diff (idempotency). Wired into `/gsd-complete-milestone` workflow as a pre-archive step.
  3. `/gsd-complete-milestone` refuses to archive with a structured error when the latest `.planning/milestones/v[X.Y]-MILESTONE-AUDIT.md` frontmatter `audited_at` predates the most recent `VERIFICATION.md` `mtime` by >1h. The error names the stale audit's `audited_at` timestamp + the offending phase's VERIFICATION path. Override flag `--accept-stale-audit` is accepted and produces a warning logged into the archive. A pytest fixture replays the v1.1 02:55Z audit vs 16:30Z verification 13h-gap scenario and asserts refusal.
  4. CI grep gates pin all three contracts: `tests/ci/test_no_placeholder_one_liners.py` ensures the validator's 5 patterns aren't silently weakened; `tests/ci/test_roadmap_analyze_supersession_wired.py` asserts `/gsd-complete-milestone` invokes `roadmap.analyze --apply` before archive; `tests/ci/test_audit_freshness_gate.py` asserts the `audited_at` vs `VERIFICATION.md mtime` comparison is unconditional in the workflow source (no `if SKIP_AUDIT_FRESHNESS` escape hatches).
  5. The v1.2 milestone close itself demonstrates all three: at `/gsd-complete-milestone v1.2` time, every plan SUMMARY one-liner passes `plan.validate`; ROADMAP.md has zero `[ ]` umbrella phases superseded by complete decimal children (or the diff proposed by `roadmap.analyze --apply` is captured in the milestone commit); the v1.2 audit's `audited_at` is ≤1h before the most recent phase VERIFICATION.md mtime.

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order. v1.2 phases (13, 14, 15) have no inter-dependencies and MAY execute in parallel, sequential, or interleaved order at operator discretion; ROADMAP fixes the requirements-to-phase mapping, not the execution timeline.

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Bootstrap & Recorded Tape | v1.0 | 4/4 | Complete | 2026-05-06 |
| 2. Integration Test Suite & RUNBOOK | v1.0 | 10/10 | Complete | 2026-05-08 |
| 3. Tournament Harness Core | v1.0 | 9/9 | Complete | 2026-05-09 |
| 4. Tournament Significance & Auto-PR | v1.0 | 10/10 | Complete | 2026-05-12 |
| 5. ML Cleanup (post-V0) | v1.0 | 4/4 | Complete | 2026-05-13 |
| 6. Dashboard Audit & Safety State | v1.0 | 5/5 | Complete | 2026-05-14 |
| 7. Tournament View & Smoke Test | v1.0 | 6/6 | Complete | 2026-05-14 |
| 7.1. Smoke Test Bugfixes | v1.0 | 1/1 | Complete | 2026-05-15 |
| 7.2. Phase3Dashboard Skeleton-Loader Fix | v1.0 | 1/1 | Complete | 2026-05-15 |
| 8. Pre-LIVE Preflight | v1.1 | 5/5 | Complete | 2026-05-16 |
| 9. ML Re-enablement Gate | v1.1 | 3/3 | Complete | 2026-05-17 |
| 10. Path-to-LIVE Dashboard | v1.1 | 3/3 | Complete | 2026-05-17 |
| 11. Carry-In Closure | v1.1 | — | Superseded by 11.1 | — |
| 11.1. Carry-In Closure Harnesses | v1.1 | 7/7 | Complete | 2026-05-18 |
| 12. CI Recovery | v1.1 | 1/1 | Complete | 2026-05-18 |
| 13. Bybit-Connector Market-Data Centralization | v1.2 | 9/9 | Complete    | 2026-05-22 |
| 14. Mobile Responsive Dashboard | v1.2 | 6/6 | Complete    | 2026-05-22 |
| 15. Planning-Tooling Hardening | v1.2 | 0/TBD | Not started | - |
