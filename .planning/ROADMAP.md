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

**Goal**: Paper fills are still frictionless and unidentifiable. `paper_trading.py:164` computes `order_value = current_price * quantity` with no slippage or spread; `:170-171` sets `OrderStatus.FILLED` / `filled_price=current_price` unconditionally, so there is no partial-fill or rejection path; `:173` sets `bybit_order_id = f"PAPER_{order.symbol}_{order.side.value}"`, which collides on concurrent same-symbol orders. This phase adds a per-symbol slippage model (5bps majors / 10bps ADA/BNB defaults), makes `bybit_order_id` monotonic, routes SL/TP fills through the slippage model, and lands the missing max-hold regression test.
**Depends on**: Phase 16, Phase 17, Phase 18, Phase 19
**Requirements**: PAPER-01, PAPER-02 (partial), PAPER-03 (partial)

> **Re-scoped 2026-07-30** against the settled tree (post-`fb764d5`). Two of the original premises no longer hold:
>
> - **"No SL/TP trigger evaluation in paper or position-manager paths" is false.** `position_manager.check_all_exit_conditions()` (`position_manager.py:589`) evaluates stop-loss (`:618`), trailing stop (`:622`), partial exits TP1/TP2/TP3 (`:626`) and legacy take-profit (`:633`). It is called from `auto_trader.py:2725` inside `_monitor_positions()` (`:2533`), which the trading loop invokes at `:916` and `:926`. The only gates between the price fetch and that call are `if was_closed: continue` (`:2604`) and an implausible-price guard (`:2650-2656`) — no mode gate, so it fires for paper positions on every tick. This wiring is **not** from the 2026-07 work: the call site was introduced in `0d0271c` (2025-11-30) and does not appear in `fb764d5`'s diff, so it predates the 2026-05-23 audit that wrote the premise.
> - **Line references all moved** in the 737-line `auto_trader.py` rewrite: 48h max-hold `:2371` → `:2425`; stop-loss-as-limit `:2691-2698` → `_close_position_with_limit_order()` at `:3043` with `limit_buffer_pct=0.005` at `:3048`.
>
> Net effect: PAPER-01 is fully owed; PAPER-02 loses its trigger-evaluation half and keeps the monotonic-ID and slippage-on-trigger halves; PAPER-03 keeps the max-hold test and loses most of the stop-loss-as-limit test (already covered by `tests/unit/test_auto_trader.py:708-845`).

### Phase 21: TA Aggregator Widening + Leakage Net

**Goal**: Aggregator `get_aggregated_signal()` at `services/technical-analysis/app/handlers/analysis.py:19-141` still votes only RSI + MACD + Trend Filter (computed at `:42-44`, voted at `:71-88`) out of 13 indicator modules under `app/indicators/` — adx, atr, bollinger_bands, ichimoku, rsi_divergence, squeeze_momentum, sqzmom_enhanced, stochastic and moving_averages (SMA+EMA) are all unused by the vote. No look-ahead-leakage regression tests exist anywhere in TA. This phase widens the aggregator vote (ADX trend gate, SQZMOM regime overlay, Volume Confirmation veto), converts the route params from hardcoded literals to settings reads, and lands a leakage regression suite covering all 13 modules + the aggregator.
**Depends on**: Phase 16
**Requirements**: TA-AGG-01, TA-AGG-02 (reduced), TA-AGG-03 (reduced), TA-AGG-04

> **Re-scoped 2026-07-30.** The param-*drift* half of this phase is already fixed; the single-source-of-truth half is not.
>
> - **MACD values now agree.** Route defaults are `Query(default=5/35/5)` at `main.py:291-293`, matching `config.py:71-82` (`default_macd_fast/slow/signal` = 5/35/5). The old `8/17/9` route drift is gone. The aggregator reads `settings.default_macd_*` (`analysis.py:36-38`) while the route hardcodes the same numbers as literals — so the values agree today by coincidence, not by construction, and drift can silently reopen.
> - **BB std-dev values now agree.** Route default is `Query(default=2.5)` at `main.py:314`, matching `config.py:87-90` (`default_bb_std` = 2.5). Same structural weakness.
> - **Requirement text names attributes that don't exist**: TA-AGG-02 says `settings.macd_*` (actual: `settings.default_macd_*`); TA-AGG-03 says `settings.bollinger_std_dev` and cites `config.py:88` (actual: `settings.default_bb_std` at `config.py:87-90`). Corrected in REQUIREMENTS.md.
> - Checked and cleared: `round(rsi_value, 2)` at `analysis.py:137` is in the aggregator's response payload, but that dict (`:132-141`) carries no price-domain field — only signal, confidence, rsi, macd_signal, trend, timestamp. Not a PRICE-01 site.
>
> Net effect: TA-AGG-01 and TA-AGG-04 fully owed. TA-AGG-02/03 shrink from "reconcile a value conflict" to "remove the literal, read the setting, add a test that pins them together."

> **Superseded 2026-08-26 by `.planning/audits/2026-08-26-ta-signal-path-audit.md`** (authoritative over the Goal text above per `21-CONTEXT.md`). The Goal's premise — "votes only RSI + MACD + Trend Filter" — is **stale**: ADX and SQZMOM already vote in `get_aggregated_signal`, and Volume Confirmation is already a post-vote confidence penalty (and must never become a voter). TA-AGG-01 reduces to *test residue + wiki doc*; the `aggregator_mode = minimal|full` env is explicitly dropped. TA-AGG-02/03 are **CLOSED** (settings-sourced since 2026-08-20, pinned by `test_endpoint_defaults_from_settings.py`) — closure evidence only, no code change. TA-AGG-04 remains fully owed. The phase additionally closes eight audit defects, P21-1..P21-8, of which P21-1 (ATR threading) is the highest-severity: threading real ATR without the percent-to-fraction unit contract would ship negative stop-losses on BTC/ETH/BNB at measured 2026-08-26 volatility.

**Plans:** 8/9 plans executed

Plans:

**Wave 1**

- [x] 21-01-PLAN.md — TA-AGG-04 three-tier look-ahead-leakage regression suite over 13 indicator modules + the aggregate path
- [x] 21-02-PLAN.md — P21-4/5 parameter single-sourcing (SMA/EMA 21, Ichimoku 20/60/120) + engine omission test + TA-AGG-02/03 closure evidence
- [x] 21-03-PLAN.md — P21-1 ATR threading with the percent-to-fraction unit contract and shared presence predicate (+ P21-8 capital defaults)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 21-04-PLAN.md — TA-AGG-01 gating tests + P21-6 settings-sourced aggregate constructors + wiki correction
- [x] 21-05-PLAN.md — Threshold-lock guard + P21-3 MTF demote-to-HOLD gating all three ensemble legs

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 21-06-PLAN.md — P21-2 leg source-diversity guard + per-cause ensemble rejection telemetry
- [x] 21-07-PLAN.md — P21-7 mirror-literal cluster (engine Settings mirrors, TA `regime` passthrough, adx_period omission)

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 21-08-PLAN.md — P21-8 hygiene batch (dead ADX fallback, money/RSI docstrings, dead code, `main.py.bak` + `.dockerignore`)

**Wave 5** *(blocked on Wave 4 completion)*

- [ ] 21-09-PLAN.md — Four-arm admission ablation, phase gate (rebuild + force-recreate + 5-symbol smoke), operator sign-off

### Phase 22: round(price, N) Epidemic Kill

**Goal**: Commit `487d1bd` fixed one site. A full re-sweep on 2026-07-30 finds **22 surviving price-domain `round(…, 2)` call sites across 7 files** — fatal for sub-$1 assets (ADA at ~$0.40 rounds to 2dp and flip-flops). This phase replaces each with `float()` or tick-size-derived precision, adds a sub-$1 fixture suite, and lands a CI grep gate that prevents reintroduction.
**Depends on**: Phase 16
**Requirements**: PRICE-01 (widened), PRICE-02 (widened)

> **Re-scoped 2026-07-30.** The original inventory was wrong in three ways — undercounted, misfiled, and scoped too narrowly to catch everything.
>
> Current sites, verified by `grep -rnE "round\([^)]*(price|stop_loss|take_profit|entry|target|level|support|resistance)[^)]*,\s*2\s*\)" services/`:
>
> | File | Sites | Original claim |
> |---|---|---|
> | `trading-engine/app/utils/support_resistance_detector.py:630,636,637,731,737,738` | 6 | **not listed at all** |
> | `trading-engine/app/strategies/support_resistance_strategy.py:643(×2),682,692,700` | 5 | "`643-700` (4 hits)" |
> | `trading-engine/app/strategies/momentum_breakout_strategy.py:1059(×2),1098,1108,1116` | 5 | "`1059-1116` (4 hits)" |
> | `technical-analysis/app/strategies/squeeze_momentum_strategy.py:203,204,205` | 3 | "two known sqzmom hits" |
> | `trading-engine/app/strategies/trend_following_strategy.py:1142(×2),1184` | 3 | "`1105-1184` (8 hits)" |
> | `technical-analysis/backtesting/sqzmom_backtest.py:106,108` | 2 | — |
> | `trading-engine/app/strategies/research_optimized_strategy.py:683` | 1 | "`683` (1 hit)" ✓ |
>
> - **`support_resistance_detector.py` (6 sites) was missed entirely** and lives in `app/utils/`, not `app/strategies/` — so PRICE-01's "all 6 strategy files" scope would not have covered it. PRICE-01 is widened to "all price-domain sites under `services/`, regardless of directory."
> - **The sqzmom sites are in technical-analysis, not trading-engine** (3 in the strategy + 2 in `backtesting/`), so the fix spans two services.
> - **Cleared as legitimate** (percentage / basis-point domain, not price): `ml-prediction-service/app/regime/regime_detector.py:304` (`price_vs_ema_pct`) and `trading-engine/app/analytics/post_trade_analysis.py:152` (`price_improvement_bps`). These belong in PRICE-02's allowlist with that justification.
> - **PRICE-02's grep gate as written would not have caught this set.** Its primary pattern requires the literal `price`, so `round(stop_loss, 2)`, `round(take_profit, 2)` and `round(final_target, 2)` all escape it; the sibling-pattern list covers stop_loss and take_profit in prose but omits `final_target`. The corrected pattern is now written into PRICE-02 verbatim rather than described.
> - **Tick-size precision is feasible**: `trading-engine/app/services/instruments_cache.py:52` already carries `tick_size: Decimal` sourced from the connector's `priceFilter.tickSize`, so PRICE-01's tick-size option does not require new plumbing.
> - Precedent for the gate exists — `tests/ci/` already holds 4 governance gates (`test_no_bybit_bypass.py`, `test_audit_freshness_gate.py`, `test_no_placeholder_one_liners.py`, `test_roadmap_analyze_supersession_wired.py`).

### Phase 23: ML Purge + V0-Pattern Eradication

**Goal**: `ml-retraining-service/app/core/model_trainer.py:427-430` inverse-transforms predictions into the price domain and calls `r2_score` on them (again at `:623`) — the exact TOURN-07/V0 forbidden pattern, while the sanctioned log-returns implementation already sits unused-by-the-trainer at `returns_metrics.py:80`. `ml-prediction-service/app/models/ensemble_model.py:15` carries a live `from tensorflow.keras.layers import LSTM, Dense, Dropout` and `ml-retraining-service/app/core/models/lstm.py` is still in the source tree. `feature_engineer.py:32` initializes `self.feature_names = []` and never populates it. The `mlgate_auto_flip.json` marker write at `lifespan/ml.py:181-197` swallows `OSError` with a warning. This phase removes price-level R² **and its two downstream consumers**, archives LSTM properly, resolves `feature_names`, hardens the marker write, and lands a CI grep gate against price-domain R².
**Depends on**: Phase 16
**Requirements**: ML-PURGE-01 (widened), ML-PURGE-02 (widened), ML-PURGE-03 (re-aimed), ML-PURGE-04, ML-PURGE-05

> **Re-scoped 2026-07-30.** Unlike Phases 20–22, most of this phase's premises survived intact — `model_trainer.py:430` and `:623` are at their originally cited lines. Three corrections, two of which grow the phase:
>
> - **ML-PURGE-01 misses a third consumer and the persistence angle.** The requirement already names `verify_all_gru_models.py`; what it omits is `scripts/check_ml_training_status.py:204-229`, which gates the same field against `TARGET_R2_SCORE` / `ACCEPTABLE_R2_SCORE`. More importantly, both readers pull `training_stats.r2_score` out of **stored model metadata** (`verify_all_gru_models.py:52`, bucketed at `:133-137`: ≥0.95 "exceptional" … <0.75 "below target"), so rewriting the trainer leaves every existing model file still carrying — and both tools still selecting on — a price-level R². The metadata field itself needs migrating or invalidating, not just the code that writes it.
> - **ML-PURGE-02 is understated.** `_archive_lstm/` **does not exist anywhere in the tree** — so CLAUDE.md's claim that LSTM was "deleted May 2026, archived under `_archive_lstm/`" is false on both halves. And LSTM references span 10+ files in `ml-prediction-service` (`hyperparameter_optimizer.py`, `compare_lstm_gru.py`, `model_comparison.py`, `generate_full_comparison.py`, `app/config.py`, `app/predictor_factory.py`, `train_remaining_gru_models.py`, `app/handlers/orderbook.py`, `app/main.py`, `app/ml_models/gru_predictor.py`), not the 2 files the premise names.
> - **ML-PURGE-03's stated consequence is false.** `self.feature_names` is indeed assigned only at `feature_engineer.py:32` and never populated, and `get_feature_names()` (at `:271`, not `:283`; returns at `:285`) does return empty. But it has **zero callers** — the two `get_feature_names()` call sites in the codebase (`app/features/orderbook_features.py:1071`, `app/handlers/orderbook.py:763`) belong to a different class, `OrderBookFeatures`. So "downstream callers depending on it select nothing" is wrong: nothing depends on it. This becomes a dead-code decision (populate it, or delete the method and the attribute), not a live-bug fix.
> - Confirmed unchanged: ML-PURGE-04's marker write catches only `OSError` and logs a warning (`lifespan/ml.py:196-197`); line range shifts `:184-196` → `:181-197`. ML-PURGE-05 has no gate yet — `tests/ci/` holds 4 governance gates, none covering R².

### Phase 24: Operator-Log + API Hygiene

**Goal**: Cross-cutting cleanup, now much smaller than originally scoped. Two stale comments in `auto_trader.py:1131,1262` still claim `"Technical 40% + ML 30% + Sentiment 15% + MTF 15%"` — wrong on ML (0.40, not 0.30), wrong on MTF (0.20, not 0.15), and naming sentiment which was removed 2026-05-02. `services/api-gateway/app/main.py:2388,2395` expose two legacy `/api/v1/market/*` routes duplicating the canonical `/api/market/*` surface with no deprecation header. This phase corrects the comments and tags the two legacy routes for deprecation.
**Depends on**: Phase 16
**Requirements**: HYG-01 (collapsed), HYG-02 (candidate demotion — audit-satisfied), HYG-03 (reduced to hardening), HYG-04 (corrected)

> **Re-scoped 2026-07-30.** This phase shrinks the most of any in v1.3 — three of its four premises no longer hold.
>
> - **HYG-01's premise is false: those are comments, not log lines.** `auto_trader.py:1131` and `:1262` are `# Phase 3: Use ML-enhanced signals (…)` source comments, not operator-visible output — nothing is logged "every cycle". There is also **no `AGGREGATOR_WEIGHTS` constant** to source from: `enhanced_aggregator.py:63` (the line the requirement cites) is itself a comment, and the weights are instance attributes at `:64-66` — `technical_weight=0.40`, `ml_weight=0.40`, `multi_timeframe_weight=0.20`, already sentiment-free and summing to 1.0. The live weight log line at `:372-374` **already** prints Technical/ML/MTF from those attributes with no sentiment row. So HYG-01 collapses from "source the log line from a constant + test the agreement" to "fix two stale comments."
> - **HYG-02 is already implemented** — delivered by Phase 9 MLGATE-02, not owed here. `preflight/checks.py:65` defines `_DSR_EVIDENCE_STALENESS_DAYS = 14`, `:327` builds the staleness window, `:343` compares row age and returns FAIL with a `stale` detail, which `lifespan/ml.py:151` maps to `direction="disabled", reason="evidence_stale"` — a reason already in the vocab at `:48` and `:61`. The only divergence from HYG-02's text is that 14 is a module constant rather than a `MLGATE_EVIDENCE_STALENESS_DAYS` env var. Recommend demoting HYG-02 as audit-satisfied, or reducing it to "make the window env-configurable + unit test."
> - **HYG-03's security hole is already closed** — by the 2026-07-29 audit (commit `e091826`), which took the *other* safe branch. `technical-analysis/app/main.py:224-226` is now `allow_origins=["*"]` with **`allow_credentials=False`**, carrying an inline note that the service uses no cookie auth and is reached server-to-server. The requirement assumed keeping `allow_credentials=True` and adding an explicit origin allowlist to make the pair legal; the invalid `*`-plus-credentials combination no longer exists either way. HYG-03 reduces from a security fix to optional defence-in-depth (pin the allowlist anyway).
> - **HYG-04's inventory and its deadline are both wrong.** There are exactly **2** legacy routes — `main.py:2388` (`/api/v1/market/ticker/{symbol}`) and `:2395` (`/api/v1/market/klines/{symbol}`) — not the cited `2320-2385` span; 4 canonical `/api/market/*` routes exist alongside them. Neither legacy route emits `Deprecation` or `Sunset` headers today. Note the requirement's hardcoded `Sunset: <2026-07-23>` is **already in the past** — the phase needs a freshly computed 60-day window at planning time.

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
| 21. TA Aggregator Widening + Leakage Net | v1.3 | 8/9 | In Progress|  |
| 22. round(price, N) Epidemic Kill | v1.3 | 0/? | Pending | — |
| 23. ML Purge + V0-Pattern Eradication | v1.3 | 0/? | Pending | — |
| 24. Operator-Log + API Hygiene | v1.3 | 0/? | Pending | — |
