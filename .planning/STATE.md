---
gsd_state_version: 1.0
milestone: v1.3
milestone_name: TA + Engine Correctness
status: executing
stopped_at: "Edge research battery built and executed (branch `feature/edge-research-battery`). `backtesting/edge_lab/` kill-funnel implemented across 13 tasks with per-task review (every task passed adversarial review; notable catches: empty-fetch permanent cache, vol_breakout time-exit off-by-one, import-failure-filed-as-REJECT). Live run 2026-08-17 over pinned top-30 universe (730d daily, 365d 4h, first-ever funding history — 90 files): **4× REJECT, no edge found**. xs_momentum and vol_breakout died at the Gate 1 cost hurdle (best ratio_taker 1.246 / 0.917 vs required 2×); funding_carry thresh_2x and both lf_trend variants cleared Gate 1 (ratios 2.6 / 4.9 / 15.5) but failed Gate 2 CPCV/DSR decisively (DSR ≤ 3.8e-05 vs 0.95, pooled PF ≈ 1.0). Clean kill-funnel outcome per spec §1 — cheap disproof is the deliverable. Evidence: `.planning/evidence/killtests/*-verdict-20260817.{md,json}` + `battery-summary-20260817.md`."
last_updated: "2026-08-26T22:44:48.805Z"
last_activity: 2026-08-26 -- Phase 21 execution started
progress:
  total_phases: 9
  completed_phases: 3
  total_plans: 21
  completed_plans: 12
  percent: 33
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-23 after v1.3 milestone open)

**Core value:** The bot must never lose money it wasn't authorized to risk; every "edge" claim must be backed by DSR/CPCV evidence on returns, not raw R² on price levels.
**Current focus:** Phase 21 — TA Aggregator Widening + Leakage Net

## Current Position

Phase: 21 (TA Aggregator Widening + Leakage Net) — EXECUTING
Plan: 1 of 9
Status: Executing Phase 21
Last activity: 2026-08-26 -- Phase 21 execution started

## Uncommitted Work (detected 2026-08-04 — RESOLVED)

**Resolved:** 260730-vwn shipped as `d5d31c6` (F-1 ensemble-leg wiring) + `1c21eac` (F-2 per-trade cap binds over sizing floor). Working tree clean as of 2026-08-16. Historical detail below retained for the record.

Quick task **260730-vwn — fix-ensemble-legs-live-cap** (`.planning/quick/260730-vwn-fix-ensemble-legs-live-cap/260730-vwn-PLAN.md`, `status: planned`, source `.planning/audits/2026-07-30-strategy-audit.md`) was at the time fully implemented in the working tree, uncommitted, with no SUMMARY.

Working-tree changes (9 modified + 1 untracked, +334/-76, all under `services/trading-engine/`):

| File | Change |
|---|---|
| `app/models/signal.py` | `IndicatorSignal.numeric_value()` added (`:20`) |
| `app/strategies/simple_rsi_strategy.py` | reads via `numeric_value()` (`:56`, `:65`) |
| `app/strategies/mean_reversion_strategy.py` | neutral fallbacks dropped, BB derived from bands, `UnboundLocalError` fixed (+171/-…) |
| `app/strategies/multi_strategy_ensemble.py` | clamp reordered to `min(cap, max(floor, scaled))` (`:305`) + clamp log (`:309`) |
| `app/preflight/checks.py` | `check_cap` FAILs on `ensemble_min_position_pct > _LIVE_STRICT_CAP` (`:106`) |
| `app/main.py` | boot refusal mirrors the floor gate, reuses `LIVE_PREFLIGHT_REJECTED` literal (`:291`) |
| `tests/strategies/test_ensemble_leg_wiring.py` | **untracked**, new |
| `tests/strategies/test_multi_strategy_ensemble_sizing.py`, `tests/test_preflight_checks.py`, `tests/test_preflight_lifespan.py` | extended |

**Verification 2026-08-04 (host, `services/trading-engine`, `MAX_TOTAL_EXPOSURE_PCT=80.0 PAPER_INITIAL_BALANCE=100.0`, `--no-cov`):**

- Targeted: **48/48 pass** (`test_ensemble_leg_wiring` 8, `test_multi_strategy_ensemble_sizing` 8, `test_preflight_checks` 25, `test_preflight_lifespan` 7).
- Full suite: **36 failed / 1542 passed / 795 skipped**. Failure families: `test_repositories` 21, `test_pairs_trading` 11, `test_connector_contract` 2, `test_handler_endpoints` 1, `test_main` 1.
- **No regression traceable to 260730-vwn.** Proved by stashing only `services/trading-engine/app` (HEAD app code, same `.env`, same tests): `test_main.py::TestLifespan::test_lifespan_startup` fails identically. `test_repositories` (21) and `test_handler_endpoints` (1) fail only in whole-suite runs and pass in a 5-file run — cross-test pollution, pre-existing. `test_pairs_trading` (11) and `test_connector_contract` (2) fail at clean HEAD too.

**New defect found (not vwn's):** `test_main.py::TestLifespan::test_lifespan_startup` fails at HEAD with `app/config.py:688 ValueError: Symbol 'BTCUSDT' in trading_symbols but missing from symbol_allocations`. The operator `.env` has `trading_symbols` entries with no matching `symbol_allocations`. Filed as OP-16.

Note: Phase 18 has no `18-VERIFICATION.md` while `workflow.verifier: true` and Phase 17 carries `17-VERIFICATION.md`. Gap, not a blocker.

## Out-of-Band Work (detected 2026-07-29, UNCOMMITTED)

Two audit/fix sessions ran outside GSD phase tracking and their output is **not committed**:

- `FIXES_2026-07-28_COMPREHENSIVE.md` (untracked) — trading-engine cash-accounting repair (reduce_only honoring, SHORT close inversion, TP payout, partial exits, kill-switch on equity, 48h max-hold, LIVE stop-loss path, daily-loss rollover, consensus-gate HOLD counting, per-trade cap clamp + hard 2% LIVE), TA indicator fixes, testnet-pollution DB repair script, frontend fixes.
- `AUDIT_2026-07-29_PRODUCTION_REVIEW.md` (untracked) — Bybit HMAC signature-over-transmitted-bytes fix (`bybit_rest_client.py`), auth on state-changing gateway endpoints (mode-gated), rate limiter, nan/inf validation in connector models, perf/UX/refactor items.

Scale: 367 changed paths (314 modified, 52 untracked, 1 deleted); ~2,306 insertions / 967 deletions across `services/` + `frontend/` alone. Backups written to session scratchpad: `wip-2026-07-29.patch` (tracked modifications), `wip-code-only.patch` (services/frontend/tests/backtesting/scripts subset), `wip-untracked.tgz` (161 untracked paths incl. both standalone test harnesses, `scripts/repair_testnet_pollution.{sh,sql}`, `backtesting/validate_mr_rr_fix.py`, both audit reports). **Scratchpad is ephemeral — not a substitute for a commit.**

**Validation status: INDEPENDENTLY VERIFIED 2026-07-29 — substantive claims hold.** Full record: `.planning/evidence/wip-verification-2026-07-29.md`. Confirmed by re-run: accounting harness 28/28, indicator harness 16/16, api-gateway 437/437 in-container, frontend build (2635 modules) + project lint (0 errors), 8/9 services 200, max mainnet BTC close exactly $82,791.20 with the $1.76M artefact gone. **No regression traceable to this work** — `test_repositories.py` and `test_pairs_trading.py` behave identically against a clean HEAD worktree; the 62 tests across WIP-modified + Phase-18 files all pass.

Reporting discrepancy (not a defect): the reports' failure accounting is internally consistent — 9 pre-existing + 2 since-fixed = the 11 in `cowork_run/te_pytest2.log` — but `cowork_run/STATUS.txt` line 5a records `5a. trading-engine pytest FAILED (exit 2)` while the report presents that suite as validated. Both of the 2 since-fixed files are green on re-run here.

Security gate verified: `auth_middleware.py:40-64` fails **closed** — auth becomes mandatory on `TRADING_MODE=LIVE`, `PAPER_TRADING_MODE=false`, or `ENVIRONMENT in {production, staging}`. Residual footgun: an explicit `REQUIRE_API_AUTH=false` overrides even LIVE; worth a boot-time hard-fail like the JWT one.

**New problems found during verification** (neither report mentions them): `docker exec crypto-bot-trading pytest tests/` collects **zero** tests — 4 fatal collection errors (`tests/integration/conftest.py:47` `database` import via a host-only `parents[5]/shared` path with `/app/shared` empty; `test_bybit_adapter_wr01_wr04.py` + `test_exchanges.py` missing **PyJWT in the image**; `test_config_default_on_gate.py:48` `parents[3]` IndexError). Also: the new untracked `services/trading-engine/.dockerignore` excludes `tests/standalone/`, so the next rebuild deletes the accounting-harness evidence base from the container.

Provenance: produced by an external "cowork" agent run on 2026-07-29 14:04–18:24, transferred in as tarballs (`_to_delete/*.tar.gz`), evidence logs in `cowork_run/`.

### Overlap with planned phases (checked in working tree 2026-07-29)

| REQ | Phase | Still owed? | Evidence |
|---|---|---|---|
| PAPER-01 (slippage model) | 20 | **NO — SHIPPED 2026-08-03** | commit `fb45efe` added `app/paper_slippage.py`; `paper_trading.py`, `auto_trader.py`, `config.py`, `main.py`, `backtesting/backtest_engine.py` all reference slippage. Phase 20 shrinks again past its 2026-07-30 re-scope. **CLAUDE.md §2 still says "no slippage model" — stale, predates `fb45efe`.** |
| PAPER-02 (SL/TP trigger + monotonic id) | 20 | PARTIAL | monotonic id owed (`paper_trading.py:173` still `f"PAPER_{symbol}_{side}"`). **Trigger evaluation exists and fires for paper** — `position_manager.check_all_exit_conditions()` (`:589`) via `auto_trader.py:2725` in `_monitor_positions()` (`:2533`), loop-driven at `:916`/`:926`, no mode gate. Predates this work (`0d0271c`, 2025-11-30) |
| PAPER-03 (Jan-2026 regression tests) | 20 | YES | `tests/test_jan_2026_fixes_regression.py` absent |
| TA-AGG-01 (ADX/SQZMOM/Volume in vote) | 21 | YES | 0 ADX refs in `handlers/analysis.py` |
| TA-AGG-02 (MACD 5/35/5 single source) | 21 | PARTIAL | `main.py:291-293` values are canonical 5/35/5 but still **hardcoded** `Query(default=…)`, not `settings.macd_*` — value drift gone, single-source requirement still owed |
| TA-AGG-03 (BB std-dev 2.5) | 21 | PARTIAL | `main.py:314` `Query(default=2.5)` — same shape: right value, still not sourced from `settings.bollinger_std_dev` |
| PRICE-01/02 (`round(price, 2)`) | 22 | YES (widened) | **22** price-domain sites across 7 files, incl. `app/utils/support_resistance_detector.py` (6) which the 2026-05-23 audit missed entirely and PRICE-01's "strategy files" scope would not have covered |
| RECON-01/02 (reconciliation + orderLinkId) | 19 | YES | connector model accepts `orderLinkId`; no generator in adapter/engine |
| HYG-01 (sentiment weight log) | 24 | PARTIAL (collapsed) | `auto_trader.py:1131,1262` are **comments**, not log lines. Runtime log at `enhanced_aggregator.py:372-374` already prints TA/ML/MTF sentiment-free from attributes `:64-66`. No `AGGREGATOR_WEIGHTS` constant exists |
| HYG-02 (DSR staleness) | 24 | **SATISFIED** | Phase 9 MLGATE-02: `preflight/checks.py:65,327,343` + `lifespan/ml.py:151` `evidence_stale`. Only gap: 14 is a constant, not env-configurable |
| HYG-03 (TA CORS lockdown) | 24 | PARTIAL (hole closed) | `main.py:225` now `allow_credentials=False` (commit `e091826`), so `["*"]` at `:224` is no longer a security hole — remaining work is hardening only |

Phase 18's committed files (`bybit_adapter.py`, `tape_replay_client.py`, `test_bybit_adapter_contract.py`) are **disjoint** from the uncommitted set; the one shared file (`bybit-connector/app/models.py`) is additive — Phase 18's camelCase aliases survive at `models.py:69-81`.

**Consequence for planning:** ROADMAP premise text cites line numbers and behaviors the 2026-07 work has changed.

**All five remaining v1.3 phases (20, 21, 22, 23, 24) re-scoped 2026-07-30** — see the `> Re-scoped` blocks in their ROADMAP detail sections and the annotated REQUIREMENTS entries.

| Phase | Direction | Why |
|---|---|---|
| 20 Paper-Engine Honesty | shrinks | SL/TP trigger evaluation already exists and fires for paper (predates this work); stop-loss-as-limit already covered by 3 tests. PAPER-01 fully owed |
| 21 TA Aggregator | shrinks | MACD/BB **value** drift already gone; requirement becomes "remove the literal, read the setting". Two requirements named non-existent attributes |
| 22 round(price, N) | **grows** | 22 sites across 7 files, not 6. `app/utils/support_resistance_detector.py` (6) missed entirely and outside the old scope; PRICE-02's regex would not have caught its own target set |
| 23 ML Purge | **grows** | Premises intact (lines unchanged) but LSTM footprint is 10+ files not 2, a third R² consumer omitted, and persisted model metadata carries the bad metric independently of the code. *(Corrected 2026-08-03 `ceaba5e`: `_archive_lstm/` **does** exist — `services/ml-prediction-service/models/_archive_lstm/`, 27 `*_lstm.keras`, 41 MB. The old "doesn't exist" wording was unverified.)* |
| 24 Operator-Log + API Hygiene | **shrinks hardest** | 3 of 4 premises dead: HYG-01's "log lines" are comments; HYG-02 already satisfied by Phase 9; HYG-03's security hole closed by `e091826`. HYG-04's inventory wrong (2 routes) and its Sunset date already past |

Cross-cutting lesson for future audits: three premises pointed at **comments rather than code** (`auto_trader.py:1131,1262`; `enhanced_aggregator.py:63`), and two prescribed attribute or constant names that do not exist (`settings.macd_*`, `settings.bollinger_std_dev`, `AGGREGATOR_WEIGHTS`). Grep hits were recorded without checking whether the line was executable.

### New operator actions from the out-of-band reports

| ID | Action | Source |
|---|---|---|
| OP-07 | ~~Decide provenance + disposition of the 367 uncommitted paths~~ — **DONE**: dispositioned across commits `d923a9b`..`e8fa391`; tree is now down to the 10 `260730-vwn` paths | resume 2026-07-29 |
| OP-08 | `bash scripts/repair_testnet_pollution.sh` before trusting any signal or backtest | FIXES §5 |
| OP-09 | Rebuild + restart `trading-engine technical-analysis market-data api-gateway frontend` (stale in-memory state = false pass) | FIXES §5 |
| OP-10 | ~~Re-run claimed validation~~ — **DONE 2026-07-29**, see `.planning/evidence/wip-verification-2026-07-29.md` | FIXES §5 |
| OP-11 | No frontend login flow — blocks any LIVE flip (auth gated open in local paper mode) | AUDIT §5 |
| OP-12 | 9 pre-existing trading-engine test failures (2 adapter source-contract, 5 backtest source-marker, 2 stale `mock.patch` targets) | AUDIT §5 |
| OP-14 | trading-engine image is missing **PyJWT** and `/app/shared` is empty — `docker exec crypto-bot-trading pytest tests/` collects zero tests. Add `PyJWT` to the image and fix the `shared/` copy, or the in-container suite (the CLAUDE.md-mandated env) stays unusable. | resume 2026-07-29 |
| OP-15 | **RESOLVED 2026-08-04** — `.dockerignore` `tests/standalone/` exclusion dropped; accounting harness stays in the image (see progress.md 2026-08-04 PM). | resume 2026-07-29 |
| OP-16 | **RESOLVED by 2026-08-12** — symbol config passed through to the container blank-safe (`bb646b7`, `65a817e`); engine boots clean, InstrumentsCache 5/5 as of 2026-08-16. | resume 2026-08-04 |
| OP-13 | **RESOLVED by 2026-08-16** — `carry_ins.json` now owned `moha:moha`; whole-tree git ops and `gsd-sdk query init.*` work. | resume 2026-07-29 |

## Deferred Items

Items acknowledged and deferred at milestone close on 2026-05-18:

| Category | Item | Status |
|---|---|---|
| verification | Phase 08 VERIFICATION.md | human_needed (2 manual-only smokes: container-restart cap-rejection proof + live HTTP curl through api-gateway after image rebuild — both deferred to post-merge operator verification per Manual-Only #1/#2 in 08-VALIDATION.md) |
| operator-action | OP-01 — LIVE-flip manual smoke | open (blocks LIVECLOSE-05 evidence; harness shipped at scripts/closure/liveclose-05-live-flip-smoke.sh + docs/runbooks/LIVECLOSE-05.md, supervised-run-only) |
| operator-action | OP-02 — apply migration 005 (`tournament_reader` role) | open (blocks LIVECLOSE-04 verdict) |
| operator-action | OP-03 — set `TOURNAMENT_READER_PASSWORD` + force-recreate tournament-harness | open (blocks LIVECLOSE-04 verdict) |
| operator-action | OP-04 — resolve GitHub Actions billing | open (blocks LIVECLOSE-02, CIRESTORE-01, CIRESTORE-02 evidence accrual) |
| operator-action | INFRA-02 checkpoint — fresh tmp clone bootstrap × 2 | open (blocks LIVECLOSE-01 evidence; harness shipped at scripts/closure/liveclose-01-fresh-clone.sh) |
| operator-action | LIVECLOSE-03 ≥7-day evidence accrual | open (wall-clock-bound; harness shipped at scripts/closure/liveclose_03_psr_evidence.py) |

## Accumulated Context

### Roadmap Evolution

- v1.0 milestone shipped 2026-05-15 (9 phases, 50 plans, 427 commits)
- v1.1 milestone shipped 2026-05-18 (5 phases, 19 plans, 138 commits; Phase 11 umbrella superseded by Phase 11.1 harnesses-only split)
- v1.2 milestone shipped 2026-05-23 (3 phases, 19 plans; Phases 13–15)
- v1.3 milestone opened 2026-05-23 (planned 9 phases, two parallel tracks, paper-only — TA + Engine Correctness)

### Decisions

Decision history accumulates in PROJECT.md `## Key Decisions`. STATE.md retains only the open / load-bearing-now items:

- ML predictions remain `ENABLE_ML_PREDICTIONS=false`; trading-engine auto-flip is *armed* (Phase 9) but no qualifying DSR>0.95 evidence row exists in `leaderboard` yet (LIVECLOSE-03 wall-clock).
- Paper-mode per-trade cap relaxed to 10% (ADR-010); Phase 8 boot-path enforces ≤2% only in LIVE. Pre-LIVE checklist (RUNBOOK Pre-LIVE Operator Checklist) restores ≤2% before flip.
- [Phase ?]: Plan 16-06 merge: 81/74/7/0
- Daily-loss breaker raised 5% → **12%** per ADR-028 (`56d3f8d`, propagated `ceaba5e`): at a 10% per-trade cap a 5% daily limit tripped on the first full loss, so it measured one trade rather than a day. Coherence fix — it *allows more* daily loss, not less.
- Paper engine now has a real slippage model (`fb45efe`, PAPER-01, `app/paper_slippage.py`). Reported paper P&L gets **worse** — that is the point. Every pre-2026-08-03 Sharpe in the repo was measured through a frictionless engine.
- CLAUDE.md cut 26.7KB → 17.3KB, 43 personas parked to `.claude/_parked/2026-08-03/agents/`, path-scoped rules added (`e0d3366`).
- `_archive_lstm/` **does exist** at `services/ml-prediction-service/models/_archive_lstm/` (27 files, 41 MB) — the earlier "does not exist" claim was corrected in `ceaba5e`. Phase 23's premise changes accordingly.

### Blockers/Concerns

- 7 operator-action items open (5 LIVECLOSE harnesses + 2 CIRESTORE evidence + 1 INFRA-02 checkpoint). All have shipped harness code; only wall-clock execution remains.
- Phase 08 VERIFICATION.md `human_needed` status persists post-archive: 2 manual-only smokes require operator post-merge action.
- New (2026-05-22): OP-05 added — running api-gateway container computed `SECRET_KEY` before quick-260522-hv0 fix; must be force-recreated before any `TRADING_MODE=LIVE` or `PAPER_TRADING_MODE=false` flip or hard-fail predicate won't run.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260522-hv0 | Fix JWT default-secret hole — extend `_validate_jwt_secret()` hard-fail to `TRADING_MODE=LIVE` / `PAPER_TRADING_MODE=false`; remove dead `Settings.jwt_secret_key` Pydantic field with insecure default | 2026-05-22 | `e0c4aa6` | [260522-hv0-fix-jwt-default-secret-hole-extend-hard-](./quick/260522-hv0-fix-jwt-default-secret-hole-extend-hard-/) |
| 260731-mxf | Fix paper capital reporting — source paper-capital defaults from config; reconcile frontend paper-balance fallbacks to $100 | 2026-07-31 | `e77fe02`, `ed5af06` | [260731-mxf-fix-paper-capital-reporting](./quick/260731-mxf-fix-paper-capital-reporting/) |
| 260731-nx4 | Fix market-data ingest — restore the dead collection scheduler | 2026-07-31 | `66779e2` | [260731-nx4-fix-market-data-ingest](./quick/260731-nx4-fix-market-data-ingest/) |
| 260731-ooe | Fix restart balance rebase — restore paper balance from the persisted ledger | 2026-07-31 | `22285ae` | [260731-ooe-fix-restart-balance-rebase](./quick/260731-ooe-fix-restart-balance-rebase/) |
| 260731-ps1 | Market-data staleness guard — reject stale rows, report freshness on `/ready` | 2026-07-31 | `a2e3d46` | [260731-ps1-market-data-staleness-guard](./quick/260731-ps1-market-data-staleness-guard/) |
| 260801-nui | Kill-switch daily roll — give the kill switch a real daily window; stop the roll deleting cumulative breakers | 2026-08-01 | `d923a9b`, `f5362e3` | [260801-nui-kill-switch-daily-roll](./quick/260801-nui-kill-switch-daily-roll/) |
| 260730-vwn | Fix dead ensemble legs (F-1) + LIVE sizing-floor cap escape (F-2) | 2026-08-05 | `d5d31c6`, `1c21eac` | [260730-vwn-fix-ensemble-legs-live-cap](./quick/260730-vwn-fix-ensemble-legs-live-cap/) |
| 260803-4mt | Make the $100 account invariant real and enforced — add `shared/account.py` as declaration of record; AST invariant + Settings-drift tests; take the inert kill-switch `max_position_value` arm live; fix live dashboard $10k drawdown baseline and stat-arb 1000× sizing; drop two dead env keys | 2026-08-03 | `e44fdce` | [260803-4mt-enforce-100-account-invariant](./quick/260803-4mt-enforce-100-account-invariant/) |
| 260816-l18 | Post-outage defect trio — kline `days=N` collection silently capped at ~1000 bars (partial-batch break vs closed-candle filter); InstrumentsCache missed SOLUSDT (Bybit 500-item page-1 cap, per-symbol fallback added); MLGATE marker moved off root-owned `/run` | 2026-08-16 | `9926954`, `1c85781`, `e57a811` | [260816-l18-fix-kline-backfill-pagination-break-inst](./quick/260816-l18-fix-kline-backfill-pagination-break-inst/) |
| 260816-px8 | RES-08 — resolve portfolio_id to settings default across PM + gateway (~65 literals + in-memory seed key) | 2026-08-16 | `a287d1a`, `0d81c84` | [260816-px8-fix-res-08-portfolio-id-default-literal-](./quick/260816-px8-fix-res-08-portfolio-id-default-literal-/) |
| 260816-qjn | RES-02 — market-data boot DDL: integer-now funcs, orderbook composite-PK hypertable, retention rewrite (klines deliberately none) | 2026-08-16 | `6c0273d` | [260816-qjn-fix-res-02-market-data-boot-ddl-integer-](./quick/260816-qjn-fix-res-02-market-data-boot-ddl-integer-/) |
| 260816-qjo | RES-03/04/05 — portfolio display columns maintained + close-persist race chained; risk cols seeded from Settings (ADR-010/028); smart-router threshold settings-wired | 2026-08-16 | `277b4b9`, `217a115`, `aefca0a` | [260816-qjo-fix-res-03-04-05-portfolios-display-colu](./quick/260816-qjo-fix-res-03-04-05-portfolios-display-colu/) |
| 260816-qjz | RES-07 — bybit-connector instruments-info cursor pagination (821 instruments, was 500) | 2026-08-16 | `c774638` | [260816-qjz-fix-res-07-bybit-connector-instruments-i](./quick/260816-qjz-fix-res-07-bybit-connector-instruments-i/) |
| 260823-3j3 | Ensemble confidence unit mismatch — vote-share score measured against the conviction floor `min_signal_confidence`; normalise over firing legs. Plus MACD re-bucketed to TREND, MTF confidence derived from the action it describes, dead volume `signal_type` threshold wired, funnel terminal/symbol/cycles attribution repaired. **First trade since 2026-08-18.** | 2026-08-23 | `b4cb894`, `94727f3`, `744d3e7`, `58332fb`, `42e2250` | [260823-3j3-fix-ensemble-confidence-units](./quick/260823-3j3-fix-ensemble-confidence-units/) |
| 260826-nzw | Fix portfolio-manager /health `database_connection` false-negative — probe the live asyncpg pool (`SELECT 1`, 2s timeout) instead of the dead in-container `shared.database` import; register the orphaned `GET /ready` route | 2026-08-26 | `b595a08`, `568d422` | [260826-nzw-fix-portfolio-manager-health-database-co](./quick/260826-nzw-fix-portfolio-manager-health-database-co/) |
| 260826-o2h | Paper-mode maker execution simulation — `PaperTradingEngine.execute_maker_order_with_fallback` (PostOnly limit at spread-derived bid/ask, 10s-capped wait, first-touch fill at limit with 0.02% maker fee, taker fallback per `maker_fallback_to_taker`); `paper_maker_commission_pct` setting; execution-path metadata (`maker_attempted`/`execution_path`/`fallback_reason`/`fee_rate_applied`) stamped into `trades.metadata` on every fill incl. `taker_direct`; auto_trader maker gate no longer LIVE-only. Root cause of the empty 08-20→08-26 isolation harvest: paper mode could never attempt maker by construction. `prefer_maker_orders` stays default-false — measurement window is a separate operator decision. | 2026-08-26 | `3125fbb`, `d8e90c8`, `8e9873f`, `4f821b9` | [260826-o2h-paper-mode-maker-execution-simulation-in](./quick/260826-o2h-paper-mode-maker-execution-simulation-in/) |

## Open Operator Actions (carry into v1.3)

| ID | Action | Blocks |
|---|---|---|
| OP-01 | LIVE-flip manual smoke (api-gateway `TRADING_MODE=LIVE`, rose outline, revert) | LIVECLOSE-05 |
| OP-02 | Apply migration 005 to market_data on timescaledb | LIVECLOSE-04 |
| OP-03 | Set `TOURNAMENT_READER_PASSWORD` + force-recreate tournament-harness | LIVECLOSE-04 |
| OP-04 | Resolve GH Actions billing | LIVECLOSE-02, CIRESTORE-01, CIRESTORE-02 |
| INFRA-02 chk | Run `bootstrap.sh` × 2 from fresh tmp clone | LIVECLOSE-01 |
| LIVECLOSE-03 accrual | Run `scripts/forward_paper_test/run_evidence_loop.py` for ≥7 trading days | LIVECLOSE-03 |
| OP-05 | Force-recreate `crypto-bot-api-gateway` to load hardened `_validate_jwt_secret()` from quick-260522-hv0 (`docker compose -f docker-compose.unified.yml up -d --force-recreate api-gateway` with `JWT_SECRET_KEY` set via `openssl rand -hex 64`) | Pre-LIVE flip, OP-01 |
| OP-06 | Rebuild + restart `crypto-bot-trading` so Phase 17 TE-CAP-02 route deletion takes effect at runtime (`docker compose -f docker-compose.unified.yml up -d --build trading-engine`), then verify with `curl -sS -X POST -o /dev/null -w "%{http_code}\n" http://localhost:8005/api/v1/orchestrator/emergency-stop` returns `404` (not `200`). Source change landed in commit `f2aaa77`; running container was built pre-Phase-17 so still serves the old route. Required for TE-CAP-02 runtime proof per 17-01-PLAN.md Task 3 gate 5. | Pre-merge / runtime TE-CAP-02 closure |

## Session Continuity

Last session: 2026-08-17
Stopped at: Edge research battery built and executed (branch `feature/edge-research-battery`). `backtesting/edge_lab/` kill-funnel implemented across 13 tasks with per-task review (every task passed adversarial review; notable catches: empty-fetch permanent cache, vol_breakout time-exit off-by-one, import-failure-filed-as-REJECT). Live run 2026-08-17 over pinned top-30 universe (730d daily, 365d 4h, first-ever funding history — 90 files): **4× REJECT, no edge found**. xs_momentum and vol_breakout died at the Gate 1 cost hurdle (best ratio_taker 1.246 / 0.917 vs required 2×); funding_carry thresh_2x and both lf_trend variants cleared Gate 1 (ratios 2.6 / 4.9 / 15.5) but failed Gate 2 CPCV/DSR decisively (DSR ≤ 3.8e-05 vs 0.95, pooled PF ≈ 1.0). Clean kill-funnel outcome per spec §1 — cheap disproof is the deliverable. Evidence: `.planning/evidence/killtests/*-verdict-20260817.{md,json}` + `battery-summary-20260817.md`.

Prior stop (2026-08-16): Resume-and-repair session complete, extended same day: RES-01 repaired (trades P&L backfill-corrected, `f7d986b`), then the whole RES minors batch fixed + deployed (RES-02/03/04/05/07/08 across 4 quick tasks, 7 commits, 5 images rebuilt, live-verified 16/16 healthy). Trader running on clean-data epoch; ledger identity exact at every level (trades = positions = portfolio = display columns). Open residues: RES-09 (PM trade-history hydration design), RES-10 (testing.md in-container rule impossible), RES-11 (ruff hook 88-col), RES-12 (duplicate tickers retention job — operator one-liner). Full record: `.planning/evidence/resume-2026-08-16.md`.
Resume file: None

Prior sessions: 2026-08-12 profit-path audit + repair (16 fixes `63595b0`..`2a48846`, clean-data epoch opened); 2026-08-05 Phase-1 money-path repair; 2026-08-04 full-state assessment + doc archive; 2026-07-30 Phase 18 close-out (`5faa32e`..`2aac085`).

## Operator Next Steps

- Plan Phase 16 (AUDIT-01 Validated-set re-audit) with `/gsd:plan-phase 16` — this phase gates all other v1.3 phases since it reconciles which Validated REQs are actually implemented.
