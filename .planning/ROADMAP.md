# Roadmap: Crypto Trading Bot

## Overview

This milestone hardens the bot around four user-named initiatives: a test-driven infra rebuild that proves the stack from a fresh clone, a Docker-based tournament harness that evaluates ML candidates honestly, a post-V0 ML cleanup that closes loose ends without re-introducing fictional edges, and a dashboard pass that surfaces real safety state. The first two phases lay foundations (bootstrap + recorded tape, then integration tests + RUNBOOK); phases 3-4 build the tournament; phase 5 finishes ML cleanup; phases 6-7 fix the dashboard and add a tournament view + smoke test on top of the recorded-tape stack.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Bootstrap & Recorded Tape** - Reproducible bring-up + deterministic exchange-data fixtures (completed 2026-05-06; INFRA-02 SC-1+SC-3 operator-checkpoint pending — see v1.0 audit)
- [x] **Phase 2: Integration Test Suite & RUNBOOK** - Fresh-clone pytest+testcontainers suite + checkpointed iteration + ops runbook (completed 2026-05-08; INFRA-01 live-stack run pending OP-04)
- [x] **Phase 3: Tournament Harness Core** - Docker+SQLite orchestrator with leaderboard schema, search-space config, and per-experiment isolation (completed 2026-05-09)
- [x] **Phase 4: Tournament Significance & Auto-PR** - DSR/bootstrap significance gating + draft-PR automation when ensemble wins (completed 2026-05-12)
- [x] **Phase 5: ML Cleanup (post-V0)** - Forward-paper-test the three opt-in features, ship a T0.1.x experiment, and resolve parked items (completed 2026-05-13)
- [x] **Phase 6: Dashboard Audit & Safety State** - End-to-end tile audit, config-driven URLs, safety-state header, explicit empty/error states (completed 2026-05-14; LIVE-flip smoke pending OP-01)
- [x] **Phase 7: Tournament View & Smoke Test** - Frontend tournament leaderboard view + Playwright smoke against the recorded-tape stack (completed 2026-05-14)
- [x] **Phase 7.1: Smoke Test Bugfixes** - Close the 3 real bugs surfaced during Phase 7 local verification (strict-mode locator, page-level LABELED_STALE assertion, gateway origin proxy) (completed 2026-05-15)
- [x] **Phase 7.2: Phase3Dashboard Skeleton-Loader Fix** - Short-circuit 503 retry surfaces `<ErrorState/>` instead of skeleton-forever; audit row re-added with verdict=FIXED (completed 2026-05-15)

## Phase Details

### Phase 1: Bootstrap & Recorded Tape
**Goal**: A new operator can clone the repo into a fresh tmp directory, run `bootstrap.sh`, and have the stack come up against deterministic recorded exchange data — no destructive `git clean -fdx` against the working tree, no live-API dependence in the deterministic path.
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-02, INFRA-03
**Success Criteria** (what must be TRUE):
  1. Operator can run `bootstrap.sh` against an empty `.env` and the script provisions the stack from a documented template (no manual editing required to reach a healthy idle state)
  2. A recorded-tape replay loader serves Bybit OHLCV (klines + ticker) fixtures to market-data-service so downstream services see deterministic data — orderbook + funding deferred to Phase 5 per Phase 1 CONTEXT.md D-02 (their consumers `PREFER_MAKER_ORDERS` / `ENABLE_FUNDING_GATE` default off and forward-test in Phase 5)
  3. `bootstrap.sh` brings the docker-compose stack up to a healthy state (all 15 services pass health checks) reproducibly across two consecutive runs in a fresh tmp clone
  4. A separate "live smoke" path is documented and explicitly out-of-scope for the deterministic suite (allowed to be flaky, runs nightly only)
**Plans**: TBD

Plans:
- [ ] 01-01: TBD

### Phase 2: Integration Test Suite & RUNBOOK
**Goal**: A pytest+testcontainers suite asserts the full stack works end-to-end from a fresh clone, runs deterministically against the recorded tape, and operator-recovery procedures are written down.
**Depends on**: Phase 1
**Requirements**: INFRA-01, INFRA-04, INFRA-05, INFRA-06
**Success Criteria** (what must be TRUE):
  1. `pytest tests/integration` against a fresh `git clone` into a tmp dir asserts all services healthy, recorded-tape prices flow, ML models load if `ENABLE_ML_PREDICTIONS=true`, a notification delivers, and a paper-trade round-trips in <60s
  2. Iteration harness presents a diff for review after every fix attempt and refuses to mock or comment out failing assertions automatically
  3. RUNBOOK.md documents WSL2 BuildKit hangs (`DOCKER_BUILDKIT=0` workaround), docker context misconfig recovery, stale-model restart, and bootstrap-test failure triage with concrete commands
  4. The three named pre-existing bugs (stale in-memory ML model, hardcoded `confidence=0` paths still emitting signals, WSL2 BuildKit env) are each either fixed with a regression test or explicitly deferred with a written decision
**Plans**: 10 plans

Plans:
**Wave 1**
- [x] 02-01-PLAN.md — bybit-connector POST /admin/tape/reset endpoint + reset() method
- [x] 02-02-PLAN.md — trading-engine POST /api/v1/admin/force-signal admin router
- [x] 02-06-PLAN.md — scripts/iter-fix.sh checkpointed iteration harness + scripts/iter-fix-check-diff.sh anti-mock guard
- [x] 02-07-PLAN.md — RUNBOOK.md failure-triage-first at repo root (6 mandated symptom sections)
- [x] 02-10-PLAN.md — Makefile build-no-buildkit ergonomic shortcut (CD-02)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 02-03-PLAN.md — extend tests/integration/conftest.py with bootstrap_stack/tmp_fresh_clone/tape_reset/force_signal/db_truncate/notification_received (mode-aware) fixtures (fix port-mapping bug, refactor to session-scope)

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 02-04-PLAN.md — INFRA-01 e2e test (test_fresh_clone_round_trip) + ML-on variant (CD-05) + remove pytest.skip anti-pattern
- [x] 02-05-PLAN.md — notification verification harness (.env.test.example, NOTIFICATION_TEST_MODE wiring, test_notification_delivery)

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 02-08-PLAN.md — INFRA-06 pre-existing bug triage (stale ML model + confidence=0 + WSL2 BuildKit)
- [x] 02-09-PLAN.md — CI workflows: .github/workflows/integration.yml (push+PR) + integration-ml-on.yml (nightly+manual)

### Phase 3: Tournament Harness Core
**Goal**: A Docker-isolated, Python-orchestrated tournament can launch GRU/LSTM/Transformer/TCN candidates over {SOL, BNB, ADA} × hyperparameter grid, capture honest returns metrics into a SQLite leaderboard, and reuse the existing `returns_metrics.py` / `sharpe_metrics.py` / `cpcv.py` modules — no LLM-subagent fanout, no parallel metrics path.
**Depends on**: Phase 2
**Requirements**: TOURN-01, TOURN-02, TOURN-03, TOURN-04, TOURN-07
**Success Criteria** (what must be TRUE):
  1. Operator can submit a tournament config (architectures × symbols × HP grid + seed) and the harness launches each experiment in its own Docker container with isolated memory and disk
  2. Each completed run writes a leaderboard row with `r2_returns`, `dir_acc_corrected`, `oos_sharpe`, `psr`, `dsr`, `cpcv_dsr`, `train_seconds`, `git_sha`, and (architecture, symbol, horizon, target_mode, hp_hash, run_id) primary key
  3. Failed runs persist a leaderboard row tagged with the failure reason rather than vanishing
  4. Leaderboard queries (e.g. "top-3 GRU runs on SOL by DSR") return correct rows from the SQLite store
  5. The harness imports its metrics from the existing modules — `grep -r "def directional_accuracy\|def sharpe\|def deflated" services/tournament-harness/` returns no parallel implementations
**Plans**: 9 plans

Plans:
**Wave 1** (foundation, parallel)
- [x] 03-01-PLAN.md — service skeleton + compose profile (Dockerfile, FastAPI status API, --profile tournament gating)
- [x] 03-02-PLAN.md — model registry refactor: extract gru/lstm/transformer/tcn builders under ml-retraining (CD-01)

**Wave 2** (parallel, depends on 03-01)
- [x] 03-03-PLAN.md — SQLite leaderboard schema + migration runner + result_schema validator (TOURN-02, TOURN-04)
- [x] 03-04-PLAN.md — tournament_loader: YAML safe_load + Cartesian enumeration + hp_hash determinism (TOURN-03)
- [x] 03-05-PLAN.md — Postgres tournament_reader role (read-only SELECT on klines, D-09) + RUNBOOK.md operator notes

**Wave 3** (depends on Wave 2)
- [x] 03-06-PLAN.md — per-experiment runner: load klines, train via registry, IMPORT honest metrics, atomic result.json (TOURN-07)
- [x] 03-07-PLAN.md — orchestrator: Docker SDK launcher, failure classifier (D-15 enum), ingest with size-cap + schema validate

**Wave 4** (depends on Wave 3)
- [x] 03-08-PLAN.md — operator CLI: run / leaderboard list (safe --where DSL CD-05) / export-snapshot (D-18); wire main.py FastAPI list endpoints

**Wave 5** (final — verification)
- [x] 03-09-PLAN.md — tests: TOURN-07 grep gate + fake-docker pipeline + real-stack end-to-end + CI workflow

### Phase 4: Tournament Significance & Auto-PR
**Goal**: A tournament run automatically constructs a top-3 ensemble, runs a bootstrap significance test against the production baseline on OOS Sharpe and corrected directional accuracy, and opens a draft PR with the leaderboard and significance results when the ensemble wins — humans always merge.
**Depends on**: Phase 3
**Requirements**: TOURN-05, TOURN-06
**Success Criteria** (what must be TRUE):
  1. Tournament wraps with a top-3-by-DSR ensemble and a bootstrap p-value vs the persistence/production baseline at p<0.05 on OOS Sharpe and `dir_acc_corrected`
  2. The R² win criterion is gone from the harness — `grep` for `>5%` or "5 percent R²" in the harness returns no matches
  3. When the ensemble wins, a draft PR opens via `gh pr create --draft` containing the leaderboard markdown, ensemble config, significance results, and a reproducer command
  4. No `gh pr merge` call exists anywhere in the harness or its CI; merge requires a human action
**Plans**: 7 plans

Plans:
**Wave 1** (parallel, no dependencies)
- [x] 04-01-PLAN.md — significance package: artifact writers + per-symbol top-3-by-DSR ensemble selection + predict-only re-hydration cache (D-01/02/03/14, CD-11)
- [x] 04-05-PLAN.md — CI grep gates: no `>5% R²` win criterion (D-13) + no `gh pr merge` (CD-10)

**Wave 2** (depends on 04-01)
- [x] 04-02-PLAN.md — persistence baseline + stationary block bootstrap kernel + per-symbol win gate (D-04/05/06/08, CD-07/08)
- [x] 04-07-PLAN.md — production predict_fn wiring (build_predict_fn over canonical klines loader; resolves B1/B3 from checker iter 1)

**Wave 3** (depends on 04-01 + 04-02 + 04-07)
- [x] 04-03-PLAN.md — `tournament open-pr` CLI + PR body + gh wrapper + count_tournaments helper (TOURN-06; D-09/10/11/14, CD-01/02/03/09/12)

**Wave 4** (depends on 04-03 + 04-07 — cli.py overlap forces sequential)
- [x] 04-04-PLAN.md — `tournament reproduce` CLI + idempotency CI test (D-12, CD-06; output_suffix parameterization for W2)

**Wave 5** (depends on 04-03 + 04-04 + 04-05 + 04-07)
- [x] 04-06-PLAN.md — end-to-end open-pr smoke test (verifies all 4 ROADMAP success criteria together)

### Phase 5: ML Cleanup (post-V0)
**Goal**: The three Tier-1 opt-in features (vol parity, maker, funding) accumulate forward-paper-test evidence, one T0.1.x experiment ships through the tournament, the parked autonomous monitoring scripts get a binding decision, and the live-vs-backtest signal divergence is no longer silent.
**Depends on**: Phase 4
**Requirements**: MLCL-01, MLCL-02, MLCL-03, MLCL-04
**Success Criteria** (what must be TRUE):
  1. A forward-paper-test harness runs each of {`ENABLE_VOL_TARGETING`, `PREFER_MAKER_ORDERS`, `ENABLE_FUNDING_GATE`} on for ≥7 days in isolation against the baseline, and per-feature default-on flips are blocked until PSR with bootstrap CI is published
  2. Exactly one T0.1.x experiment from {different horizon, classification head, XGBoost control, cross-sectional features, sentiment-as-filter} runs through the tournament harness and its result (edge or no-edge) is committed to the leaderboard with a written decision note
  3. `scripts/monitoring/*` is either removed or wired with documented blast-radius bounds, no `claude -p` PR-opening from CI without human review, and the decision is committed
  4. `run_extended_backtest.py` either uses the live `CoreAggregator` or its module docstring + runtime warning permanently states the divergence with no further ambiguity
**Plans**: 4 plans

Plans:
- [x] 05-01-PLAN.md — MLCL-01 forward-paper-test apparatus + PSR-with-bootstrap-CI + default-on pytest gate for the three Tier-1 opt-in flags (complete 2026-05-13; 37 tests pass; operator evidence loops pending)
- [x] 05-02-PLAN.md — MLCL-02 select + ship one T0.1.x experiment through the tournament harness with a binding decision note (EDGE_FOUND / NO_EDGE_FOUND / INSUFFICIENT_DATA) (complete 2026-05-13; different_horizon selected; t0_1_x_horizon_sweep YAML shipped; INSUFFICIENT_DATA verdict — TIMESCALE_PASSWORD blocker; 5/5 integration tests pass)
- [x] 05-03-PLAN.md — MLCL-03 binding disposition of scripts/monitoring/* (delete-all / wire-with-bounds / keep-tier1-delete-tier2) + ADR-011 + grep-gate against claude -p in CI (complete 2026-05-13; tier-2 deleted per STRIDE analysis; ADR-011 filed; 4-test grep gate; tier-1 retained)
- [x] 05-04-PLAN.md — MLCL-04 resolve run_extended_backtest.py divergence (rewrite to CoreAggregator OR document permanently + runtime warning) + ADR-012 (complete 2026-05-13; document_divergence_permanently chosen; PERMANENT DIVERGENCE docstring + _emit_divergence_warning() + ADR-012 filed; SC-4 closed; 5/5 pytest invariants pass)

### Phase 6: Dashboard Audit & Safety State
**Goal**: The React dashboard shows real backend state, surfaces safety posture (PAPER/LIVE, kill-switch, EMERGENCY_STOP, ML predictions toggle) prominently, replaces hardcoded URLs with config-driven values, and renders explicit empty/error states instead of silent zeros.
**Depends on**: Phase 5
**Requirements**: DASH-01, DASH-02, DASH-03, DASH-05
**Success Criteria** (what must be TRUE):
  1. Every dashboard tile/route is documented with its backing endpoint and a verified response shape — broken or stale tiles either render fixed or are explicitly labeled "stale" in the UI
  2. The dashboard header shows current TRADING_MODE, `auto_trading_enabled`, kill-switch state, EMERGENCY_STOP file presence, and `ENABLE_ML_PREDICTIONS` — operator sees safety state at first glance
  3. No hardcoded backend URLs remain in frontend source — `grep -rn "http://localhost\|ws://localhost" frontend/src/` returns only documented dev-config defaults
  4. Each tile renders an explicit "no data" or "endpoint failed" message when the backend response is empty or non-200, instead of a blank chart or a default zero
**Plans**: 5 plans
**UI hint**: yes

Plans:
**Wave 1** (parallel, no inter-plan dependencies)
- [x] 06-01-PLAN.md — DASH-01 tile audit: 06-TILE-AUDIT.md + 06-TILE-AUDIT.json sidecar + scripts/audit_tiles.py runtime probe; operator-reviewed verdicts {FIXED, LABELED_STALE, REMOVED}
- [x] 06-02-PLAN.md — DASH-03 backend: extend trading-engine /status with emergency_stop.mtime + new GET /api/config/safety-state on api-gateway (D-08 schema) + in-container pytest
- [x] 06-03-PLAN.md — DASH-02 config-driven URLs: migrate useGatewayWebSocket.js:34 to VITE_WS_URL + extend vite.config.js doc block + install grep-gate npm script

**Wave 2** (blocked on Wave 1)
- [x] 06-04-PLAN.md — DASH-03 frontend (depends on 06-02): useSafetyState hook + 3 new StatusBar cells (MODE/KILL-SWITCH/ML) + PAPER/LIVE viewport border in App.jsx
- [x] 06-05-PLAN.md — DASH-05 (depends on 06-01): shared <TileState/> wrapper + refactor every FIXED/LABELED_STALE tile + delete REMOVED tiles; operator smoke + audit re-run

### Phase 7: Tournament View & Smoke Test
**Goal**: The dashboard reads the tournament leaderboard so the operator can see ML evaluation results without leaving the UI, and a Playwright smoke test asserts every major tile renders non-empty against the recorded-tape stack.
**Depends on**: Phase 6
**Requirements**: DASH-04, DASH-06
**Success Criteria** (what must be TRUE):
  1. The dashboard exposes a Tournament view showing leaderboard rows from Phase 3's SQLite store, filterable by symbol and architecture, with significance markers from Phase 4
  2. A Playwright smoke test boots the recorded-tape stack from Phase 1, opens the dashboard, and asserts each major tile (Performance, Portfolio, Safety State, Tournament) renders non-empty
  3. The smoke test is wired into the Phase 2 integration suite so the dashboard regressions surface alongside backend regressions
**Plans**: 6 plans
**UI hint**: yes

Plans:
**Wave 1** *(parallel; no file overlap)*
- [x] 07-01-PLAN.md — Gateway tournament endpoints (/api/tournament/snapshots[/{id}]) + RO bind-mount + in-container tests (DASH-04)
- [x] 07-03-PLAN.md — data-testid wiring on TileState (stale/error/empty), StatusBar (root + 5 D-17 cells), 15 audit-referenced tile components + audit JSON/MD updates (Tournament row appended) (DASH-06)

**Wave 2** *(blocked on 07-01)*
- [x] 07-02-PLAN.md — Frontend tournamentAPI extension + useTournamentList/useTournamentSnapshot React Query hooks (staleTime=Infinity, no polling per D-23) (DASH-04)

**Wave 3** *(blocked on 07-02)*
- [x] 07-04-PLAN.md — TournamentDashboard page + leaderboard table + filter chips + significance badge + contaminated-window warning + route registration honoring UI-SPEC (DASH-04)

**Wave 4** *(blocked on 07-03 + 07-04)*
- [x] 07-05-PLAN.md — Smoke fixture JSON (primary + 2 Phase 4 sidecars) + tournament_snapshot_seeded conftest fixture + audit-driven pytest-playwright smoke with hard data_testid gate + named StatusBar substrings (DASH-06)

**Wave 5** *(blocked on Wave 4)*
- [x] 07-06-PLAN.md — pytest-playwright dep + Chromium install step + failure-artifact upload in integration.yml and integration-ml-on.yml (DASH-06)

### Phase 7.1: Smoke Test Bugfixes
**Goal**: Close the three real bugs surfaced during the 2026-05-14 local re-verification of the Phase 7 audit-driven smoke so the exact CI command (`pytest tests/integration/test_dashboard_smoke.py --browser=chromium`) runs green against the recorded-tape stack.
**Depends on**: Phase 7
**Requirements**: DASH-06
**Success Criteria** (what must be TRUE):
  1. BUG-1 fixed: LABELED_STALE locator handles tiles with multiple `<StaleBadge/>` children (`.first` qualifier) — PriceTickerGrid passes.
  2. BUG-2 fixed: page-level LABELED_STALE rows (Phase3Dashboard, page-level Portfolio) use a nested-descendant locator strategy, opted in via new audit field `data_testid_scope: descendant`.
  3. BUG-3 fixed: api-gateway acts as a true reverse-proxy for non-`/api` paths, forwarding to the frontend nginx container — `GATEWAY_ORIGIN = http://localhost:8000` actually serves the React app, matching the smoke's hardcoded assumption.
  4. End-to-end: the smoke runs green against the live local stack with NO sandbox patches, NO `.first` shims at the call site, NO origin overrides.
**Plans**: 1 plan
**UI hint**: no

Plans:
- [x] 07.1-01-PLAN.md — scope-aware stale assertion + descendant audit rows + api-gateway frontend reverse-proxy + Phase3Dashboard skeleton-loader finding (DASH-06; smoke green 2026-05-15)

### Phase 7.2: Phase3Dashboard Skeleton-Loader Fix
**Goal**: Phase3Dashboard transitions out of skeleton-loader state into an explicit empty/stale UI when backing ml-prediction-service responds 503 for a sustained window. After fix, re-add the Phase3Dashboard row to `.planning/phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.json` with an empirically-verifiable verdict.
**Depends on**: Phase 7.1
**Requirements**: DASH-05 (explicit empty/error states)
**Success Criteria** (what must be TRUE):
  1. With `ENABLE_ML_PREDICTIONS=false`, `/phase3` renders a non-skeleton state within 10 seconds — either explicit "ML predictions disabled" copy, a `<TileState forceStale={true}/>` at page root with a visible `tile-stale-badge`, or REMOVED (component returns null when feature off).
  2. `phase3-dashboard` testid behavior is consistent with the chosen state (present with stale badge → verdict LABELED_STALE; present with copy → verdict FIXED; absent → verdict REMOVED).
  3. Phase 7 audit-driven smoke test passes against the live stack with Phase3Dashboard row re-added to `06-TILE-AUDIT.json`.
**Plans**: 1 plan
**UI hint**: yes

Plans:
- [x] 07.2-01-PLAN.md — short-circuit 503 retry on 4 useQuery hooks in Phase3Dashboard + re-add audit row (DASH-05; smoke green 2026-05-15)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 7.1 → 7.2

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Bootstrap & Recorded Tape | 4/4 | Complete   | 2026-05-06 |
| 2. Integration Test Suite & RUNBOOK | 10/10 | Complete | - |
| 3. Tournament Harness Core | 9/9 | Complete | - |
| 4. Tournament Significance & Auto-PR | 9/9 | Complete | - |
| 5. ML Cleanup (post-V0) | 4/4 | Complete | 2026-05-13 |
| 6. Dashboard Audit & Safety State | 5/5 | Complete | - |
| 7. Tournament View & Smoke Test | 6/6 | Complete | 2026-05-14 |
| 7.1. Smoke Test Bugfixes | 1/1 | Complete | 2026-05-15 |
| 7.2. Phase3Dashboard Skeleton-Loader Fix | 1/1 | Complete | 2026-05-15 |
