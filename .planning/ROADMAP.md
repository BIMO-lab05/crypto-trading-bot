# Roadmap: Crypto Trading Bot

## Milestones

- 🟡 **v1.3 TA + Engine Correctness** — Validated-set re-audit, execution-cap enforcement, Bybit-adapter contract fix, order reconciliation, paper-engine honesty, TA aggregator widening, round(price,N) kill, ML purge + V0-pattern eradication, operator-log + API hygiene (Phases 16-24) — in progress
- ✅ **v1.0** — Bootstrap & tape, integration suite, tournament harness, significance + auto-PR, ML post-V0 cleanup, dashboard safety + smoke (Phases 1, 2, 3, 4, 5, 6, 7, 7.1, 7.2) — shipped 2026-05-15
- ✅ **v1.1 Path to LIVE** — Pre-LIVE preflight, ML re-enablement gate, path-to-LIVE dashboard tile, carry-in closure harnesses, CI recovery (Phases 8, 9, 10, 11.1, 12 — Phase 11 superseded by 11.1) — shipped 2026-05-18
- ✅ **v1.2 Polish & Real-Time** — Bybit-connector centralization, mobile responsive dashboard, planning-tooling hardening (Phases 13, 14, 15) — shipped 2026-05-23

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

<details>
<summary>✅ v1.2 Polish & Real-Time (Phases 13–15) — SHIPPED 2026-05-23</summary>

- [x] Phase 13: Bybit-Connector Market-Data Centralization (9/9 plans) — completed 2026-05-22
- [x] Phase 14: Mobile Responsive Dashboard (6/6 plans) — completed 2026-05-22
- [x] Phase 15: Planning-Tooling Hardening (4/4 plans) — completed 2026-05-23

Full milestone archive: [`.planning/milestones/v1.2-ROADMAP.md`](milestones/v1.2-ROADMAP.md)
Audit: [`.planning/milestones/v1.2-MILESTONE-AUDIT.md`](milestones/v1.2-MILESTONE-AUDIT.md) (`gaps_found` — 13/13 REQs satisfied at code level; 3 deferred items are documented operator carry-ins or intentional SDK-port forcing functions, not Phase work failures)

**v1.2 carries into v1.3 as operator actions only (no code debt):**

- BC-07 ml-prediction-service container-exec verification (Phase 13 — scipy/tensorflow not on host)
- MOBILE-03 pytest matrix execution (Phase 14 — blocked by pre-v1.2 INFRA-02 + OP-04)
- TOOL-02 + TOOL-03 SDK ports into `~/.claude/get-shit-done/workflows/complete-milestone.md` (Phase 15 — designed-RED forcing functions)

Plus 17 tech-debt items aggregated in the v1.2 milestone audit for v1.3 re-plan (mobile card visual hierarchy, focus-visible WCAG, hardcoded hex literals, vite_preview_server fixture, etc.).

</details>

### 🟡 v1.3 TA + Engine Correctness — In Progress

**Milestone Goal:** Restore one-to-one parity between PROJECT.md's Validated set and actual code in `services/technical-analysis/` + `services/trading-engine/` + `services/ml-{prediction,retraining}-service/`. Fix execution and signal correctness defects surfaced by the 2026-05-23 forensic audit. Paper-only — no LIVE flip. No new features. Every claim in PROJECT.md ends v1.3 with `file:line` evidence or is demoted.

- [x] **Phase 16: Validated-Set Re-Audit** — Trust-no-docs sweep of every REQ in PROJECT.md `### Validated` (pre-v1, v1.0, v1.1, v1.2) with `file:line` evidence; demote drift items (RISK-04 cap advisory, RISK-06 stub, ADR-010 paper cap missing, LSTM-archived false). Gates Track A + Track B.
- [x] **Phase 17: Execution-Cap Hard Enforcement** — Track A AUDIT-01 found execution-cap enforcement (RISK-04/06 + ADR-010 paper-cap config) already satisfied; v1.3 Phase 17 scope shrinks to (a) emergency-stop HTTP admin auth (TE-CAP-02) + (b) bare-except cleanup in order path (TE-CAP-05). TE-CAP-01/03/04 demoted as audit-satisfied. (completed 2026-05-24)
- [x] **Phase 18: Bybit-Adapter Contract Fix** — Fix `bybit_adapter.py` dead endpoint paths (`/api/v1/order/create` → `/api/v1/order/place`; `/api/v1/position/list` → `/api/v1/account/positions`); extend `TapeReplayClient` with order endpoints; contract tests against bybit-connector router surface (BC-FIX-01..03) (completed 2026-05-24)
- [ ] **Phase 19: Order Reconciliation + Idempotency** — Order-state polling or WS handler post-submit; deterministic `orderLinkId` on every place + retry (RECON-01..02)
- [ ] **Phase 20: Paper-Engine Honesty** — Paper-sim slippage model; SL/TP trigger evaluation; monotonic order IDs; 48h max-hold + stop-loss-as-limit regression tests (PAPER-01..03)
- [ ] **Phase 21: TA Aggregator Widening + Leakage Net** — Bring ADX + Volume + SQZMOM into aggregator vote; reconcile MACD route/settings drift (5/35/5 canonical); reconcile BB std-dev drift (2.5 canonical); look-ahead-leakage regression suite (TA-AGG-01..04)
- [ ] **Phase 22: round(price, N) Epidemic Kill** — Fix `round(price, 2)` at 6 surviving call sites; sub-$1 asset fixture suite; CI grep gate (PRICE-01..02)
- [ ] **Phase 23: ML Purge + V0-Pattern Eradication** — Remove price-level `r2_score` from trainer + verify; archive LSTM (ensemble_model + lstm.py); fix `feature_engineer.get_feature_names()` returning `[]`; marker-age check on `mlgate_auto_flip.json`; CI grep gate vs r2_score on price-domain arrays (ML-PURGE-01..05)
- [ ] **Phase 24: Operator-Log + API Hygiene** — Fix stale "Sentiment 15%" log lines; DSR staleness enforcement on auto-flip; TA CORS lockdown; deprecate legacy `/api/v1/market/*` at api-gateway (HYG-01..04)

**Parallelization (after Phase 16 closes):**

- Track A (execution): Phases 17 → 18 → 19 → 20 (sequential within track)
- Track B (signal + ML): Phases 21, 22, 23 can run independently
- Cross-cutting: Phase 24 can run any time after Phase 16

## Phase Details

> v1.0 phases (1–7.2), v1.1 phases (8–12), and v1.2 phases (13–15) detail sections live in their respective milestone archives under `.planning/milestones/`. Only the active v1.3 phases (16–24) carry full detail blocks below.

### Phase 16: Validated-Set Re-Audit

**Goal**: Trust-no-docs sweep of every REQ in PROJECT.md `### Validated` (pre-v1, v1.0, v1.1, v1.2). Produce `.planning/evidence/AUDIT-01/validated-reaudit.json` with `{req_id, claim, evidence_file, evidence_line_start, evidence_line_end, status}` where `status ∈ {satisfied, drift, missing}`. Rewrite PROJECT.md `### Validated` to reflect reality; demote drift/missing REQs to Active or Out of Scope with reason. Gates Track A + Track B — downstream phase sizing depends on truthful baseline.
**Depends on**: Nothing
**Requirements**: AUDIT-01

**Plans:** 7/7 plans complete

Plans:

- [x] 16-01-PLAN.md — Inventory + schema scaffolding (seed validated-reaudit.json with ~81 Validated REQs)
- [x] 16-02-PLAN.md — Track A audit: Risk + Preflight + MLGate + Observability + CLAUDE-PAPER-CAP-ADR010 (~17 rows)
- [x] 16-03-PLAN.md — Track B audit: ML + MLCL + TOURN + EXEC-03 + CLAUDE-LSTM-ARCHIVED + CLAUDE-SENTIMENT-REMOVED (~19 rows)
- [x] 16-04-PLAN.md — Track C1 audit: Infra + Dashboard + DASHLIVE + DATA + EXEC-01/02 + UI + TEST + CLAUDE-VALIDATED-SYMBOLS + CLAUDE-EXEC-MAINNET-PRICES (~24 rows)
- [x] 16-05-PLAN.md — Track C2 audit: BC + MOBILE + TOOL + LIVECLOSE + CIRESTORE (~21 rows)
- [x] 16-06-PLAN.md — Merge four track deltas into canonical validated-reaudit.json + write validated-reaudit.md with drift-to-downstream-phase mapping
- [x] 16-07-PLAN.md — Operator checkpoint:decision on demotions; rewrite PROJECT.md ### Validated; correct CLAUDE.md drift sentences; flip AUDIT-01 traceability to Complete

### Phase 17: Execution-Cap Hard Enforcement

**Goal**: RISK caps Track A audit (Phase 16 AUDIT-01, 2026-05-23) found execution-cap enforcement (RISK-04 / RISK-06 + ADR-010 paper-cap config) already satisfied at file:line evidence (`services/trading-engine/app/auto_trader.py:332-344, 1962-1986`; `services/trading-engine/app/live_trading.py:290-360`; `services/trading-engine/app/config.py:321-332`). v1.3 Phase 17 scope shrinks to (a) **emergency-stop HTTP admin auth (TE-CAP-02)** — guard `POST /api/v1/orchestrator/emergency-stop` at `handlers/orchestration.py:591` against unauthenticated callers; (b) **bare-except cleanup in order path (TE-CAP-05)** — replace bare `except:` and broad `except Exception:` clauses in trading-engine order-submission path with typed exception handling that logs + re-raises (or controlled-returns on a known-recoverable type). TE-CAP-01 / TE-CAP-03 / TE-CAP-04 demoted as audit-satisfied; no code work owed.
**Depends on**: Phase 16
**Requirements**: TE-CAP-02, TE-CAP-05

**Plans:** 2/2 plans complete

Plans:
**Wave 1**

- [x] 17-01-PLAN.md — TE-CAP-02: delete unauthenticated trading-engine /emergency-stop route + add 404 negative test + update auth-note comment (api-gateway becomes sole admin entry per D-01/D-02/D-12)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 17-02-PLAN.md — TE-CAP-05: rewrite 5 REQ-named broad-except sites in auto_trader.py per locked D-08 M/P/R taxonomy + D-10 caplog regression test for [RISK_GATE] PER_TRADE_CAP BREACH log survival

### Phase 18: Bybit-Adapter Contract Fix

**Goal**: LIVE trading is dead-on-arrival because `bybit_adapter.place_order()` at `services/trading-engine/app/exchanges/bybit_adapter.py:663` posts to `/api/v1/order/create`; bybit-connector exposes `/api/v1/order/place` at `services/bybit-connector/app/main.py:587`. `get_positions()` at `bybit_adapter.py:568` calls `/api/v1/position/list`; connector exposes `/api/v1/account/positions` at `main.py:557`. `TapeReplayClient` lacks `place_order`/`cancel_order`/`get_wallet_balance` — tape-mode integration tests AttributeError on order paths. This phase corrects endpoint paths, extends tape client with order stubs, and adds a contract test that imports the connector router and validates every adapter call against the route table.
**Depends on**: Phase 16, Phase 17
**Requirements**: BC-FIX-01, BC-FIX-02, BC-FIX-03

**Plans:** 3/3 plans complete

Plans:
**Wave 1** *(parallel — no file overlap)*

- [x] 18-01-PLAN.md — BC-FIX-01: correct 5 mismatched bybit_adapter endpoint strings against connector route table (place_order, get_positions, get_order_status, get_open_orders, get_ticker)
- [x] 18-02-PLAN.md — BC-FIX-02: extend TapeReplayClient with place_order/cancel_order/get_wallet_balance (deterministic FILLED stubs + in-memory balance/order state per D-05..D-08) + wallet fixture + regression tests

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 18-03-PLAN.md — BC-FIX-03: contract test asserting every adapter (method, path) is in the connector FastAPI route table (subprocess-loaded app.routes + regex over adapter source, D-09/D-10/D-11/D-12)

### Phase 19: Order Reconciliation + Idempotency

**Goal**: Today no polling or WebSocket handler updates order state post-submit. `live_trading.py:493` `sync_positions_with_exchange()` runs once at startup. SUBMITTED→FILLED has no auto-updater; positions go stale. `bybit_adapter.py:346` 3-retry loop sends no `orderLinkId`; server-side 5xx after commit creates duplicate live orders. This phase implements either periodic polling or WS-private-channel reconciliation (decision in phase CONTEXT.md), and adds deterministic `orderLinkId` reused across retries within the 3-attempt window.
**Depends on**: Phase 16, Phase 17, Phase 18
**Requirements**: RECON-01, RECON-02

### Phase 20: Paper-Engine Honesty

**Goal**: Today `paper_trading.py:122` fills at `current_price` with no slippage; `paper_trading.py:148` sets `OrderStatus.FILLED` unconditionally; `paper_trading.py:151` `bybit_order_id = f"PAPER_{symbol}_{side}"` collides on concurrent same-symbol orders. No SL/TP trigger evaluation in paper or position-manager paths — paper positions with SL/TP set silently never exit. Jan 2026 fixes (48h max-hold, stop-loss-as-limit at commit `380a674`) have no regression tests. This phase adds a per-symbol slippage model (5bps majors / 10bps ADA/BNB defaults), implements SL/TP trigger evaluation on every tick, makes `bybit_order_id` monotonic, and lands regression tests for the Jan 2026 fixes.
**Depends on**: Phase 16, Phase 17, Phase 18, Phase 19
**Requirements**: PAPER-01, PAPER-02, PAPER-03

### Phase 21: TA Aggregator Widening + Leakage Net

**Goal**: Aggregator at `services/technical-analysis/app/handlers/analysis.py:19-132` combines only RSI + MACD + Trend Filter from 13 implemented indicators (ADX, Ichimoku, SQZMOM, RSI-Divergence, Volume Confirmation, ATR, Stochastic, Bollinger, SMA, EMA wasted). Param drift: route MACD `8/17/9` (`main.py:284-286`) vs settings `5/35/5` (`config.py:71-81`); BB std-dev route `2.0` (`main.py:306`) vs config `2.5` (`config.py:88`). No look-ahead-leakage regression tests. This phase widens the aggregator vote (ADX trend gate, SQZMOM regime overlay, Volume Confirmation veto), reconciles MACD + BB params to single source of truth, and lands a leakage regression suite covering all 13 indicators + aggregator.
**Depends on**: Phase 16
**Requirements**: TA-AGG-01, TA-AGG-02, TA-AGG-03, TA-AGG-04

### Phase 22: round(price, N) Epidemic Kill

**Goal**: Commit `487d1bd` fixed one site; the 2026-05-23 audit found 6 more sites where price-domain values are rounded to 2 decimals — fatal for sub-$1 assets (ADA at ~$0.40). `trend_following_strategy.py:1105-1184` (8 hits), `support_resistance_strategy.py:643-700` (4 hits), `momentum_breakout_strategy.py:1059-1116` (4 hits), `research_optimized_strategy.py:683` (1 hit), plus two known sqzmom hits. This phase replaces every `round(price, 2)` with `float(price)` (or per-symbol tick-size precision), adds a sub-$1 asset fixture suite, and lands a CI grep gate that prevents reintroduction.
**Depends on**: Phase 16
**Requirements**: PRICE-01, PRICE-02

### Phase 23: ML Purge + V0-Pattern Eradication

**Goal**: `ml-retraining-service/app/core/model_trainer.py:430,623` calls `r2_score` on inverse-transformed price arrays — the exact TOURN-07/V0 forbidden pattern. `verify_all_gru_models.py` gates on this metric, selecting wrong models. `ml-prediction-service/app/models/ensemble_model.py:15` carries live `from tensorflow.keras.layers import LSTM, Dense, Dropout`; `ml-retraining-service/app/core/models/lstm.py` is present in source tree (CLAUDE.md "LSTM deleted" is false). `feature_engineer.py:32,283` initializes `self.feature_names = []` and never populates — `get_feature_names()` returns empty always. `mlgate_auto_flip.json` marker write at `lifespan/ml.py:184-196` is best-effort with `OSError` swallowed; reader has no marker-age check. This phase removes price-level R², archives LSTM properly, fixes `feature_names` population, adds marker-age check + write-failure handling, and lands a CI grep gate against price-domain R².
**Depends on**: Phase 16
**Requirements**: ML-PURGE-01, ML-PURGE-02, ML-PURGE-03, ML-PURGE-04, ML-PURGE-05

### Phase 24: Operator-Log + API Hygiene

**Goal**: Cross-cutting cleanup. `auto_trader.py:1130,1261` log `"Technical 40% + ML 30% + Sentiment 15% + MTF 15%"` every cycle — wrong (ML is 0.40 not 0.30, sentiment is 0 not 0.15 after 2026-05-02 removal). `lifespan/ml.py:145+` reads DSR evidence but does not fail when rows are >14 days old. `services/technical-analysis/app/main.py:216-222` has `allow_origins=["*"]` with `allow_credentials=True` — security hole. `services/api-gateway/app/main.py:2320-2385` exposes legacy `/api/v1/market/*` routes duplicating the modern `/api/market/*` surface with no deprecation header. This phase sources aggregator weights from the constant, enforces DSR staleness, locks down TA CORS, and tags the legacy gateway routes for deprecation.
**Depends on**: Phase 16
**Requirements**: HYG-01, HYG-02, HYG-03, HYG-04

## Progress

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
| 13. Bybit-Connector Market-Data Centralization | v1.2 | 9/9 | Complete | 2026-05-22 |
| 14. Mobile Responsive Dashboard | v1.2 | 6/6 | Complete | 2026-05-22 |
| 15. Planning-Tooling Hardening | v1.2 | 4/4 | Complete | 2026-05-23 |
| 16. Validated-Set Re-Audit | v1.3 | 7/7 | Complete | 2026-05-24 |
| 17. Execution-Cap Hard Enforcement | v1.3 | 2/2 | Complete    | 2026-05-24 |
| 18. Bybit-Adapter Contract Fix | v1.3 | 3/3 | Complete   | 2026-05-24 |
| 19. Order Reconciliation + Idempotency | v1.3 | 0/? | Pending | — |
| 20. Paper-Engine Honesty | v1.3 | 0/? | Pending | — |
| 21. TA Aggregator Widening + Leakage Net | v1.3 | 0/? | Pending | — |
| 22. round(price, N) Epidemic Kill | v1.3 | 0/? | Pending | — |
| 23. ML Purge + V0-Pattern Eradication | v1.3 | 0/? | Pending | — |
| 24. Operator-Log + API Hygiene | v1.3 | 0/? | Pending | — |
