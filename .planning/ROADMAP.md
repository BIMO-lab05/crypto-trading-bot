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

- [ ] **Phase 13: Real-Time WebSocket Push** — Server-side `/ws/metrics` route in `api-gateway` with Redis pub/sub fanout, frontend WS client + `useWsSubscription` hook with REST-snapshot priming and visibility-aware pause, migration of 4 production hooks (`useSafetyState`/`useLiveReadiness`/`useCarryIns`/`useDashboardSnapshot`) off `setInterval`, CI grep gate + integration latency assertion + RUNBOOK Symptom #7
- [ ] **Phase 14: Mobile Responsive Dashboard** — Viewport meta + Tailwind breakpoint audit, single-column reflow ≤768px across `Dashboard.jsx`/`PathToLiveTile.jsx`/`KeyMetricsStrip`/`TournamentDashboard.jsx` with no information loss, pytest-playwright matrix smoke at iPhone SE (375×667) + iPad portrait (768×1024) asserting no horizontal scroll + ≥44px touch targets
- [ ] **Phase 15: Planning-Tooling Hardening** — `plan.validate` rejects 5 placeholder one-liner patterns (pre-commit + CI), `roadmap.analyze` auto-marks umbrella phases as superseded when decimal child covers their REQ set, `/gsd-complete-milestone` refuses to archive if latest milestone-audit `audited_at` predates most recent phase VERIFICATION.md by >1h (replays v1.1 13h-gap scenario as fixture)

## Phase Details

### Phase 8: Pre-LIVE Preflight
**Goal**: The path to LIVE is enforced in code, not only in docs — `scripts/preflight_live.py` CLI and `GET /api/preflight/live-readiness` HTTP endpoint both assert all 6 preconditions with structured JSON output; trading-engine refuses to boot LIVE if `MAX_POSITION_RISK_PCT > 2`; a CI workflow blocks any `live: requested` PR that fails preflight; and the RUNBOOK gains a Pre-LIVE operator checklist. All three enforcement layers (CLI/HTTP, boot-path, CI) ship with unit tests and CI grep gates so regressions fail loudly.
**Depends on**: Nothing (first v1.1 phase; builds on existing trading-engine codebase)
**Requirements**: PREFLIGHT-01, PREFLIGHT-02, PREFLIGHT-03, PREFLIGHT-04
**Status**: Complete — 2026-05-16
**Plans**: 5/5 plans complete
Full detail in archived [v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md).

### Phase 9: ML Re-enablement Gate
**Goal**: The ML on/off decision is driven by code and evidence, not by human memory — `run_evidence_loop.py` manages ≥7-day evidence accrual idempotently; trading-engine startup auto-flips `ENABLE_ML_PREDICTIONS` based on DSR>0.95 evidence within 14 days; every ML-disabled event logs a structured reason from a fixed enum; CI grep gate pins the auto-flip startup check.
**Depends on**: Phase 8
**Requirements**: MLGATE-01, MLGATE-02, MLGATE-03
**Status**: Complete — 2026-05-17
**Plans**: 3/3 plans complete
Full detail in archived [v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md).

### Phase 10: Path-to-LIVE Dashboard
**Goal**: Operator sees every LIVE precondition and carry-in state on one screen — `PathToLiveTile.jsx` polls `/api/preflight/live-readiness` + `/api/preflight/carry-ins` every 5s, renders DO-NOT-FLIP → ALMOST → READY transitions with 24h continuous-PASS window logic; Playwright smoke confirms behavior.
**Depends on**: Phase 8, Phase 9
**Requirements**: DASHLIVE-01, DASHLIVE-02, DASHLIVE-03, DASHLIVE-04
**Status**: Complete — 2026-05-17
**Plans**: 3/3 plans complete
**UI hint**: yes
Full detail in archived [v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md).

### Phase 11: Carry-In Closure *(SUPERSEDED by Phase 11.1)*
**Status**: Superseded — scope absorbed by Phase 11.1. Wall-clock operator execution of harnesses carries forward to v1.2 as operator actions only, not as code debt.

### Phase 11.1: Carry-In Closure Harnesses (LIVECLOSE-01..05)
**Goal**: Every v1.0/v1.1 operator-blocked carry-in has an explicit closure harness that produces a schema-validated evidence row — five operator-runnable scripts (LIVECLOSE-01..05) + shared Draft 2020-12 JSON Schema + `scripts/closure/run-all.sh` orchestrator that refuses LIVECLOSE-05 auto-invocation; `LIVECLOSE-INDEX.md` fully wired with zero tripwire tokens.
**Depends on**: Phase 9, Phase 10
**Requirements**: LIVECLOSE-01, LIVECLOSE-02, LIVECLOSE-03, LIVECLOSE-04, LIVECLOSE-05
**Status**: Complete — 2026-05-18 (harness-delivered; operator wall-clock execution carries to v1.2 as operator actions)
**Plans**: 7/7 plans complete
Full detail in archived [v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md).

### Phase 12: CI Recovery
**Goal**: Re-establish CI signal for the three workflows OP-04 (GH Actions billing) silently blocked — `.github/workflows/billing-failure-detector.yml` cron-driven (every 6h) self-trigger-safe with direct curl Telegram + `gh issue create` path; evidence-dir scaffolds for the two operator-blocked CIRESTORE carry-ins; 12-test grep-gate net pins the contract.
**Depends on**: Phase 11.1 (LIVECLOSE-02 evidence-dir scaffold consumes the closed-for-extension `_schema.json` from Phase 11.1)
**Requirements**: CIRESTORE-03 (CIRESTORE-01/02 operator-blocked carry to v1.2)
**Status**: Complete — 2026-05-18
**Plans**: 1/1 plans complete
Full detail in archived [v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md).

### Phase 13: Real-Time WebSocket Push
**Goal**: Replace the 5s REST polling that powers four production dashboard hooks with a server-pushed `/ws/metrics` WebSocket stream — api-gateway exposes a single WS route emitting self-describing JSON-line frames for `safety-state` / `live-readiness` / `carry-ins` / `dashboard-snapshot`, backed by Redis pub/sub fanout for multi-worker coherence; the React client gains a `useWsSubscription` hook with exponential-backoff reconnect, visibility-aware pause, and REST-snapshot priming on connect; all four production hooks migrate off `setInterval` with a 30s WS-silence REST fallback (graceful degradation); a CI grep gate blocks new `setInterval` polling in `frontend/src/hooks/` outside an allowlist; an integration test asserts p95 push-to-render latency <500ms vs REST p95 ≥1s.
**Depends on**: Nothing (no upstream v1.2 blocker; consumes existing `api-gateway` service + existing Redis; references existing endpoint schemas from Phase 8/10)
**Requirements**: WS-01, WS-02, WS-03, WS-04
**Success Criteria** (what must be TRUE):
  1. `GET /ws/metrics` (WebSocket) accepts a connection against the running `api-gateway` container, the client subscribes via initial frame `{"action": "subscribe", "channels": ["safety-state", "live-readiness", "carry-ins", "dashboard-snapshot"], "token": "<bearer>"}`, and within 1s receives a snapshot frame per channel matching `{"channel": "<name>", "schema_version": 1, "data": {...}, "ts": "<ISO-8601>"}`. State mutations on backing endpoints trigger a push within 500ms; heartbeat frames arrive at most every 5s per channel when state is steady. Two concurrent gateway workers stay coherent (asserted by integration test that mutates state on worker A and asserts both A's and B's subscribers receive the push within 500ms via Redis pub/sub fanout).
  2. The four production hooks (`useSafetyState`, `useLiveReadiness`, `useCarryIns`, `useDashboardSnapshot`) consume `useWsSubscription(channel)` and no longer call `setInterval` for their primary fetch path; existing component value-contracts (the shape consumed by `Dashboard.jsx`, `PathToLiveTile.jsx`, `KeyMetricsStrip`, `StatusBar`) are unchanged. Disconnecting the WS server (e.g. kill `api-gateway` for >30s) causes each hook to re-arm a REST fallback poll; reconnecting the server cancels the REST fallback within one successful push cycle.
  3. Client behavior under stress is observable in DevTools and asserted by integration test: when `document.visibilityState === 'hidden'` the client sends a `{"action": "pause"}` frame and the server suspends pushes for that connection; on `visible` the client sends `{"action": "resume"}` and the next push arrives within 1s. WS reconnect after server kill follows exponential backoff (≥1s, doubling, capped ≤30s) observable from client console logs.
  4. `pytest tests/ci/test_no_new_setinterval_polling.py` is green on `main`, fails if a new `setInterval(.*\d+000)` lands in `frontend/src/hooks/` outside the documented allowlist (REST-fallback re-arm sites only). `pytest tests/integration/test_ws_latency.py` is green and asserts p95 push-to-render latency on `safety-state` is <500ms while REST-equivalent p95 ≥1s on the same fixture (>50% improvement contract).
  5. `RUNBOOK.md` Symptom #7 ("Dashboard tiles frozen — WS layer down") exists in Diagnose/Action/Verification format and documents the WS-reconnect path + the 30s REST-fallback behavior; PROJECT.md Out-of-Scope row "Re-introducing client-side WebSocket scaffolding before server `/ws/metrics` route exists" is removed (precondition satisfied).
**Plans**: 5 plans
- [ ] 13-01-ws-route-and-fanout-PLAN.md — Server `/ws/metrics` route + ConnectionManager + RedisFanout subscriber
- [ ] 13-02-ws-producer-poller-PLAN.md — Centralized poll-and-diff producer with leader-lock multi-worker coherence
- [ ] 13-03-frontend-ws-client-PLAN.md — `wsClient.ts` singleton + `useWsSubscription` hook with REST priming
- [ ] 13-04-hook-migration-PLAN.md — Migrate 4 production hooks to WS; add `/api/dashboard/snapshot` + `useDashboardSnapshot.js`
- [ ] 13-05-ci-gate-latency-runbook-PLAN.md — CI grep gate + p95 latency integration test + RUNBOOK Symptom #7 + PROJECT.md OOS cleanup
**UI hint**: yes

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
**Plans**: TBD
**UI hint**: yes

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
| 13. Real-Time WebSocket Push | v1.2 | 0/5 | Planned | - |
| 14. Mobile Responsive Dashboard | v1.2 | 0/TBD | Not started | - |
| 15. Planning-Tooling Hardening | v1.2 | 0/TBD | Not started | - |
