# Roadmap: Crypto Trading Bot

## Overview

This milestone hardens the bot around four user-named initiatives: a test-driven infra rebuild that proves the stack from a fresh clone, a Docker-based tournament harness that evaluates ML candidates honestly, a post-V0 ML cleanup that closes loose ends without re-introducing fictional edges, and a dashboard pass that surfaces real safety state. The first two phases lay foundations (bootstrap + recorded tape, then integration tests + RUNBOOK); phases 3-4 build the tournament; phase 5 finishes ML cleanup; phases 6-7 fix the dashboard and add a tournament view + smoke test on top of the recorded-tape stack.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Bootstrap & Recorded Tape** - Reproducible bring-up + deterministic exchange-data fixtures (completed 2026-05-06)
- [ ] **Phase 2: Integration Test Suite & RUNBOOK** - Fresh-clone pytest+testcontainers suite + checkpointed iteration + ops runbook
- [ ] **Phase 3: Tournament Harness Core** - Docker+SQLite orchestrator with leaderboard schema, search-space config, and per-experiment isolation
- [ ] **Phase 4: Tournament Significance & Auto-PR** - DSR/bootstrap significance gating + draft-PR automation when ensemble wins
- [ ] **Phase 5: ML Cleanup (post-V0)** - Forward-paper-test the three opt-in features, ship a T0.1.x experiment, and resolve parked items
- [ ] **Phase 6: Dashboard Audit & Safety State** - End-to-end tile audit, config-driven URLs, safety-state header, explicit empty/error states
- [ ] **Phase 7: Tournament View & Smoke Test** - Frontend tournament leaderboard view + Playwright smoke against the recorded-tape stack

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
- [ ] 02-01-PLAN.md — bybit-connector POST /admin/tape/reset endpoint + reset() method
- [ ] 02-02-PLAN.md — trading-engine POST /api/v1/admin/force-signal admin router
- [ ] 02-03-PLAN.md — extend tests/integration/conftest.py with bootstrap_stack/tmp_fresh_clone/tape_reset/force_signal/db_truncate/notification_log fixtures (fix port-mapping bug, refactor to session-scope)
- [ ] 02-04-PLAN.md — INFRA-01 e2e test (test_fresh_clone_round_trip) + ML-on variant (CD-05) + remove pytest.skip anti-pattern
- [ ] 02-05-PLAN.md — notification verification harness (.env.test.example, NOTIFICATION_TEST_MODE wiring, test_notification_delivery)
- [ ] 02-06-PLAN.md — scripts/iter-fix.sh checkpointed iteration harness + scripts/iter-fix-check-diff.sh anti-mock guard
- [ ] 02-07-PLAN.md — RUNBOOK.md failure-triage-first at repo root (6 mandated symptom sections)
- [ ] 02-08-PLAN.md — INFRA-06 pre-existing bug triage (stale ML model + confidence=0 + WSL2 BuildKit)
- [ ] 02-09-PLAN.md — CI workflows: .github/workflows/integration.yml (push+PR) + integration-ml-on.yml (nightly+manual)
- [ ] 02-10-PLAN.md — Makefile build-no-buildkit ergonomic shortcut (CD-02)

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
**Plans**: TBD

Plans:
- [ ] 03-01: TBD

### Phase 4: Tournament Significance & Auto-PR
**Goal**: A tournament run automatically constructs a top-3 ensemble, runs a bootstrap significance test against the production baseline on OOS Sharpe and corrected directional accuracy, and opens a draft PR with the leaderboard and significance results when the ensemble wins — humans always merge.
**Depends on**: Phase 3
**Requirements**: TOURN-05, TOURN-06
**Success Criteria** (what must be TRUE):
  1. Tournament wraps with a top-3-by-DSR ensemble and a bootstrap p-value vs the persistence/production baseline at p<0.05 on OOS Sharpe and `dir_acc_corrected`
  2. The R² win criterion is gone from the harness — `grep` for `>5%` or "5 percent R²" in the harness returns no matches
  3. When the ensemble wins, a draft PR opens via `gh pr create --draft` containing the leaderboard markdown, ensemble config, significance results, and a reproducer command
  4. No `gh pr merge` call exists anywhere in the harness or its CI; merge requires a human action
**Plans**: TBD

Plans:
- [ ] 04-01: TBD

### Phase 5: ML Cleanup (post-V0)
**Goal**: The three Tier-1 opt-in features (vol parity, maker, funding) accumulate forward-paper-test evidence, one T0.1.x experiment ships through the tournament, the parked autonomous monitoring scripts get a binding decision, and the live-vs-backtest signal divergence is no longer silent.
**Depends on**: Phase 4
**Requirements**: MLCL-01, MLCL-02, MLCL-03, MLCL-04
**Success Criteria** (what must be TRUE):
  1. A forward-paper-test harness runs each of {`ENABLE_VOL_TARGETING`, `PREFER_MAKER_ORDERS`, `ENABLE_FUNDING_GATE`} on for ≥7 days in isolation against the baseline, and per-feature default-on flips are blocked until PSR with bootstrap CI is published
  2. Exactly one T0.1.x experiment from {different horizon, classification head, XGBoost control, cross-sectional features, sentiment-as-filter} runs through the tournament harness and its result (edge or no-edge) is committed to the leaderboard with a written decision note
  3. `scripts/monitoring/*` is either removed or wired with documented blast-radius bounds, no `claude -p` PR-opening from CI without human review, and the decision is committed
  4. `run_extended_backtest.py` either uses the live `CoreAggregator` or its module docstring + runtime warning permanently states the divergence with no further ambiguity
**Plans**: TBD

Plans:
- [ ] 05-01: TBD

### Phase 6: Dashboard Audit & Safety State
**Goal**: The React dashboard shows real backend state, surfaces safety posture (PAPER/LIVE, kill-switch, EMERGENCY_STOP, ML predictions toggle) prominently, replaces hardcoded URLs with config-driven values, and renders explicit empty/error states instead of silent zeros.
**Depends on**: Phase 5
**Requirements**: DASH-01, DASH-02, DASH-03, DASH-05
**Success Criteria** (what must be TRUE):
  1. Every dashboard tile/route is documented with its backing endpoint and a verified response shape — broken or stale tiles either render fixed or are explicitly labeled "stale" in the UI
  2. The dashboard header shows current TRADING_MODE, `auto_trading_enabled`, kill-switch state, EMERGENCY_STOP file presence, and `ENABLE_ML_PREDICTIONS` — operator sees safety state at first glance
  3. No hardcoded backend URLs remain in frontend source — `grep -rn "http://localhost\|ws://localhost" frontend/src/` returns only documented dev-config defaults
  4. Each tile renders an explicit "no data" or "endpoint failed" message when the backend response is empty or non-200, instead of a blank chart or a default zero
**Plans**: TBD
**UI hint**: yes

Plans:
- [ ] 06-01: TBD

### Phase 7: Tournament View & Smoke Test
**Goal**: The dashboard reads the tournament leaderboard so the operator can see ML evaluation results without leaving the UI, and a Playwright smoke test asserts every major tile renders non-empty against the recorded-tape stack.
**Depends on**: Phase 6
**Requirements**: DASH-04, DASH-06
**Success Criteria** (what must be TRUE):
  1. The dashboard exposes a Tournament view showing leaderboard rows from Phase 3's SQLite store, filterable by symbol and architecture, with significance markers from Phase 4
  2. A Playwright smoke test boots the recorded-tape stack from Phase 1, opens the dashboard, and asserts each major tile (Performance, Portfolio, Safety State, Tournament) renders non-empty
  3. The smoke test is wired into the Phase 2 integration suite so the dashboard regressions surface alongside backend regressions
**Plans**: TBD
**UI hint**: yes

Plans:
- [ ] 07-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Bootstrap & Recorded Tape | 4/4 | Complete   | 2026-05-06 |
| 2. Integration Test Suite & RUNBOOK | 0/10 | Not started | - |
| 3. Tournament Harness Core | 0/TBD | Not started | - |
| 4. Tournament Significance & Auto-PR | 0/TBD | Not started | - |
| 5. ML Cleanup (post-V0) | 0/TBD | Not started | - |
| 6. Dashboard Audit & Safety State | 0/TBD | Not started | - |
| 7. Tournament View & Smoke Test | 0/TBD | Not started | - |
