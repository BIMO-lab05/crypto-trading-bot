# Crypto Trading Bot

## What This Is

A self-hosted, microservices-based crypto trading bot targeting Bybit (paper trading by default; live trading gated behind four explicit flag flips). Runs a 9-indicator voting aggregator over OHLCV + sentiment + (optional) ML signals, with portfolio management, risk caps, a React dashboard, and a Docker-isolated tournament harness that evaluates ML candidates honestly (DSR/CPCV on returns, not raw R²). Built and operated by a solo founder; safety and honest measurement come before performance claims.

## Core Value

The bot must never lose money it wasn't authorized to risk. Every trade goes through enforced risk caps (per-trade, daily-loss, drawdown, kill-switch) backed by code that actually runs — and any "edge" claim must be backed by DSR/CPCV evidence on returns through the tournament harness, not raw R² on price levels.

## Current State (post v1.2, 2026-05-23)

**Shipped v1.2 (2026-05-22 → 2026-05-23, 3 phases / 19 plans):**

- Bybit-connector centralization (Phase 13): 20-violation inventory across 17 files closed; CI grep gate `tests/ci/test_no_bybit_bypass.py` + standalone workflow flipped GREEN; `rotate_secrets` + `shared/health_check` rerouted through connector; `binance.py` archived
- Mobile responsive dashboard (Phase 14): single-column reflow ≤768px on Dashboard, PathToLiveTile, KeyMetricsStrip, TournamentDashboard; 44px tap targets; Playwright matrix @ iPhone-SE + iPad
- Planning-tooling hardening (Phase 15): plan one-liner CI gate, umbrella→decimal auto-supersession SDK port spec, audit-refresh-after-last-phase lock

**Open at v1.2 close (operator wall-clock only — no code debt; carries into v1.3):**

- OP-01..OP-05 + LIVECLOSE-01..03 + INFRA-02 checkpoint: same backlog as v1.1 close; ML-prediction container-exec verification (BC-07) + MOBILE-03 pytest matrix execution (blocked by pre-v1.2 INFRA-02 + OP-04); TOOL-02 + TOOL-03 SDK ports into `~/.claude/get-shit-done/workflows/complete-milestone.md` (designed-RED forcing functions)
- Plus 17 tech-debt items aggregated in v1.2 milestone audit (mobile card visual hierarchy, focus-visible WCAG, hardcoded hex literals, vite_preview_server fixture, etc.) — carry as backlog candidates, NOT pre-committed to v1.3.

**v1.3 forensic-audit findings (2026-05-23, three parallel agents over technical-analysis + trading-engine + ml-{prediction,retraining} + bybit-connector):**

- **CRITICAL — Validated-set drift:** RISK-06 (maker-only) marked Validated but is a stub (`use_post_only=False` hard-coded at `trading-engine/app/auto_trader.py:544`). RISK-04 per-trade cap is advisory after boot — proposed risk calculated at `auto_trader.py:1697` but order NOT rejected on breach. ADR-010 paper 10% cap NOT in code (default stays 0.02 at `config.py:321`). LSTM "deleted" per CLAUDE.md but `ml-prediction-service/app/models/ensemble_model.py:15` carries live `from tensorflow.keras.layers import LSTM`.
- **CRITICAL — LIVE-flip dead on arrival:** `trading-engine/app/exchanges/bybit_adapter.py:663` posts to `/api/v1/order/create`; bybit-connector exposes `/api/v1/order/place`. Same mismatch on `get_positions` (`/api/v1/position/list` vs `/api/v1/account/positions`). Both latent in paper mode, 404 the moment `PAPER_TRADING_MODE=false`.
- **CRITICAL — V0 R² pattern survives in trainer:** `ml-retraining-service/app/core/model_trainer.py:430,623` calls `r2_score` on inverse-transformed price arrays at validation + evaluation; `verify_all_gru_models.py` gates on this metric. Forbidden per TOURN-07 / V0 finding.
- **CRITICAL — Order reconciliation missing:** no polling / WS handler updates order state post-submit; `live_trading.py:493` `sync_positions_with_exchange()` runs once at startup only.
- **CRITICAL — No retry idempotency key:** `bybit_adapter.py:346` 3-retry loop sends no `orderLinkId`; server-side 5xx after commit creates duplicate live orders.
- **CRITICAL — emergency-stop HTTP endpoint UNAUTHENTICATED** at `services/trading-engine/app/handlers/orchestration.py:591`.
- **HIGH — round(price,2) epidemic across 4 more strategies** (trend_following, support_resistance, momentum_breakout, research_optimized) beyond the two sqzmom hits already known; ADA SL/TP truncated to wrong tick.
- **HIGH — TA aggregator uses only 3 of 13 implemented indicators** (RSI + MACD + Trend Filter at `technical-analysis/app/handlers/analysis.py:19-132`); ADX, Ichimoku, SQZMOM, RSI-Divergence, Volume Confirmation wasted.
- **HIGH — Paper-engine has no SL/TP triggers, no slippage model, colliding order IDs** at `paper_trading.py:122,148,151`.
- **HIGH — Stale "Sentiment 15%" log every cycle** at `auto_trader.py:1130,1261`; reality TA=0.40, ML=0.40, MTF=0.20, sentiment=0 (removed 2026-05-02).
- **MEDIUM — MACD param divergence** (route 8/17/9 vs settings 5/35/5), **BB std divergence** (route 2.0 vs config 2.5), TA CORS wildcard with credentials, `feature_engineer.get_feature_names()` returns `[]`, legacy `/api/v1/market/*` duplicated at api-gateway.

## Current Milestone: v1.3 TA + Engine Correctness

**Goal:** Restore one-to-one parity between PROJECT.md's Validated set and actual code in `services/technical-analysis/` + `services/trading-engine/` + `services/ml-{prediction,retraining}-service/`. Fix the execution and signal correctness defects surfaced by the 2026-05-23 forensic audit. Paper-only — no LIVE flip. No new features. Every claim in PROJECT.md ships with `file:line` evidence after this milestone closes.

**Target features (two parallel tracks, 9 phases):**

*Track A — Execution hardening:*
- **Phase 16 — Validated-set re-audit** (gates everything else): re-run trust-no-docs against every Validated REQ with `file:line` evidence; demote items lacking implementation
- **Phase 17 — Execution-cap hard enforcement:** cap rejection in order loop, emergency-stop admin auth, RISK-06 maker/post-only implementation, ADR-010 paper 10% cap in code, kill bare-except in order path
- **Phase 18 — Bybit-adapter contract fix:** fix dead endpoint paths in `bybit_adapter.py`, extend `TapeReplayClient` with order endpoints, add contract tests against bybit-connector router surface
- **Phase 19 — Order reconciliation + idempotency:** polling or WS handler for order updates, `orderLinkId` on every place + retry
- **Phase 20 — Paper-engine honesty:** SL/TP triggers in paper sim, slippage model, 48h max-hold + stop-loss-as-limit regression tests

*Track B — Signal + ML correctness:*
- **Phase 21 — TA aggregator widening + leakage net:** bring ADX + Volume + SQZMOM into vote, reconcile MACD/BB param divergence, look-ahead-leakage regression tests
- **Phase 22 — round(price, N) epidemic kill:** fix all 6 surviving call sites, sub-$1 asset fixture suite, CI grep gate
- **Phase 23 — ML purge + V0-pattern eradication:** remove price-level `r2_score` from trainer + verify script, archive LSTM (ensemble_model + lstm.py), fix `feature_engineer.get_feature_names()`, marker-age check, CI grep gate

*Cross-cutting:*
- **Phase 24 — Operator-log + API hygiene:** fix stale Sentiment log, DSR staleness enforcement, TA CORS lockdown, deprecate legacy `/api/v1/market/*` at api-gateway

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

**Pre-v1 (existing capabilities)**

- ✓ **EXEC-01**: 15-container microservices stack — existing
- ✓ **EXEC-02**: Bybit mainnet price feed; paper trading default — existing
- ✓ **EXEC-03**: 9-indicator voting aggregator with TREND_FILTER + VOLUME_CONFIRMATION — existing
- ✓ **RISK-01..07**: Risk caps (daily-loss, drawdown, consec-loss, per-trade, vol parity, maker, funding) — Tier-1 2026-04-30
- ✓ **ML-01..05**: Honest returns metrics; PSR/DSR; CPCV; live-reload; ML disabled by default until DSR>0.95 — 2026-04-30/05-01
- ✓ **DATA-01, DATA-02**: `is_mainnet` column + backtest filter; confidence sentinel chain cleaned — 2026-04 commits
- ✓ **OBS-01, OBS-02**: Telegram redaction; honest sentiment 501/503 (not fabricated) — 2026-04 commits
- ✓ **UI-01**: React dashboard with REST-polling (dead WS scaffolding stripped)
- ✓ **TEST-01**: ~101 Tier-1 tests green

**v1.0 (shipped 2026-05-15)**

- ✓ **INFRA-03**: Recorded-tape exchange-data fixtures + replay loader — v1.0
- ✓ **INFRA-04**: Checkpointed iteration harness (`iter-fix.sh` + anti-mock guard) — v1.0
- ✓ **INFRA-05**: RUNBOOK.md (6 symptoms, Diagnose/Action/Verification) — v1.0
- ✓ **INFRA-06**: 3 pre-existing bugs triaged (stale-ML reload, confidence=0 filter, WSL2 BuildKit documented) — v1.0
- ✓ **TOURN-01**: Docker+SQLite tournament harness (Python orchestrator, NOT LLM subagents) — v1.0
- ✓ **TOURN-02**: Leaderboard schema with composite PK + 9 metric columns — v1.0
- ✓ **TOURN-03**: GRU/LSTM/Transformer/TCN × {SOL,BNB,ADA} × hyperparameter grid — v1.0
- ✓ **TOURN-04**: Failure-row persistence with typed reason enum (Cl. 1 deferred with proof) — v1.0
- ✓ **TOURN-05**: Top-3 ensemble + Politis–Romano block bootstrap p<0.05 — v1.0
- ✓ **TOURN-06**: Auto-open draft PR (`gh pr create --draft`); humans merge — v1.0
- ✓ **TOURN-07**: Canonical metrics imports only (CI grep gate enforced) — v1.0
- ✓ **MLCL-03**: Tier-2 monitoring deleted (ADR-011); `claude -p` CI grep gate — v1.0
- ✓ **MLCL-04**: `run_extended_backtest.py` PERMANENT DIVERGENCE doc + runtime warning (ADR-012) — v1.0
- ✓ **DASH-01..06**: Tile audit, config URLs, safety-state header, empty/error states, Tournament view, Playwright smoke — v1.0

**v1.0 (partial — operator-blocked, carry into v1.1)**

- ⚠ **INFRA-01**: pytest+testcontainers from fresh clone — code complete; live-stack run pending OP-04 (GH Actions billing) — v1.0 partial
- ⚠ **INFRA-02**: `bootstrap.sh` fresh-clone provisioning — code complete; SC-1+SC-3 fresh-clone checkpoint never executed by operator — v1.0 partial
- ⚠ **MLCL-01**: Forward-paper-test apparatus + PSR-CI gate — code complete; ≥7-day operator wall-clock evidence loops pending — v1.0 partial
- ⚠ **MLCL-02**: T0.1.x `different_horizon` sweep — code + YAML complete; verdict INSUFFICIENT_DATA pending OP-02 (migration 005) + OP-03 (reader password) — v1.0 partial

**v1.1 (shipped 2026-05-18)**

- ✓ **PREFLIGHT-01**: Pre-LIVE preflight CLI (`scripts/preflight_live.py`) — Phase 8 (2026-05-16)
- ✓ **PREFLIGHT-02**: Trading-engine boot path enforces `MAX_POSITION_RISK_PCT ≤ 0.02` in LIVE; `LIVE_PREFLIGHT_REJECTED reason=cap_too_high` — Phase 8 (2026-05-16)
- ✓ **PREFLIGHT-03**: `.github/workflows/preflight-live-readiness.yml` PR-label gate (`live: requested`) — Phase 8 (2026-05-16)
- ✓ **PREFLIGHT-04**: RUNBOOK Pre-LIVE Operator Checklist (6 Diagnose/Action/Verification subsections) + PROJECT.md cross-link — Phase 8 (2026-05-16)
- ✓ **MLGATE-01**: Idempotent ≥7-day forward-paper-test evidence accrual + PSR-CI publish (`run_evidence_loop.py` + migration 0002 adding `run_date` + `psr_ci_published` to `leaderboard`) — Phase 9 (2026-05-17)
- ✓ **MLGATE-02**: Trading-engine startup auto-flip of `ENABLE_ML_PREDICTIONS` driven by DSR>0.95 evidence within 14 days; structured `MLGATE_AUTO_FLIP direction=X reason=Y` log + `/run/mlgate_auto_flip.json` schema_version=1 marker; CI grep gate — Phase 9 (2026-05-17)
- ✓ **MLGATE-03**: 5-member `MLGateReason` enum + cross-plan reason-state cache; structured-reason logging at trading-engine ML-disabled sites; unauth read-only `/api/preflight/ml-gate-reason-counts` endpoint; notification-service scheduled Telegram digest of reason counts; CI grep gate — Phase 9 (2026-05-17)
- ✓ **DASHLIVE-01**: `PathToLiveTile.jsx` (banner + 6 PREFLIGHT chip rows + 5 carry-in rows + 24h window footer) rendered above `KeyMetricsStrip` in `Dashboard.jsx` — Phase 10 (2026-05-17)
- ✓ **DASHLIVE-02**: api-gateway `GET /api/preflight/carry-ins` (schema_version=1) backed by atomic file-state machine at `.planning/state/carry_ins.json` — Phase 10 (2026-05-17)
- ✓ **DASHLIVE-03**: Two react-query hooks (`useLiveReadiness`, `useCarryIns`) verbatim from `useSafetyState` idiom (5s poll, retry=2, retryDelay=1000) — Phase 10 (2026-05-17)
- ✓ **DASHLIVE-04**: pytest-playwright Chromium smoke covering all 7 D-10-18 assertions; two defence-in-depth grep gates; `.github/workflows/dashboard-smoke.yml` with PR paths filter — Phase 10 (2026-05-17)
- ✓ **CIRESTORE-03**: `.github/workflows/billing-failure-detector.yml` cron-driven (every 6h) self-trigger-safe; direct curl Telegram + `gh issue create` with `ops: billing` label; 12-test grep-gate net — Phase 12 (2026-05-18)

**v1.1 (harness-delivered — operator wall-clock execution carries into v1.2)**

- ⚠ **LIVECLOSE-01**: `scripts/closure/liveclose-01-fresh-clone.sh` — fresh-clone bootstrap × 2 with `BYBIT_PRICE_SOURCE: mode=tape` grep; awaits operator execution — Phase 11.1 (2026-05-18)
- ⚠ **LIVECLOSE-02**: `scripts/closure/liveclose-02-record-ci.sh` — gh-api validation of integration-ml-on.yml; awaits OP-04 — Phase 11.1 (2026-05-18)
- ⚠ **LIVECLOSE-03**: `scripts/closure/liveclose_03_psr_evidence.py` — ≥7-day consecutive `leaderboard` window query; awaits wall-clock accrual — Phase 11.1 (2026-05-18)
- ⚠ **LIVECLOSE-04**: `scripts/closure/liveclose_04_sweep_verdict.py` — T0.1.x decision_note.md verdict + significance.json p-values; awaits OP-02 + OP-03 — Phase 11.1 (2026-05-18)
- ⚠ **LIVECLOSE-05**: `scripts/closure/liveclose-05-live-flip-smoke.sh` + `docs/runbooks/LIVECLOSE-05.md` — supervised-run-only LIVE-flip smoke; awaits operator (orchestrator refuses `--exec`) — Phase 11.1 (2026-05-18)

**v1.1 (operator-blocked — external precondition)**

- ⏸ **CIRESTORE-01**: GH Actions billing screenshot under `.planning/evidence/OP-04/` — Phase 12 shipped evidence-dir scaffold; blocked on OP-04 resolution
- ⏸ **CIRESTORE-02**: Three green CI run URLs (integration-ml-on, tournament-harness, dashboard-smoke) under `.planning/evidence/CIRESTORE-02/` — Phase 12 shipped evidence-dir scaffold; blocked on OP-04 resolution

### Active

<!-- v1.3 ratified scope. REQ-IDs assigned in .planning/REQUIREMENTS.md. -->

**v1.3 TA + Engine Correctness (ratified 2026-05-23)**

> ⚠ Phase 16 (AUDIT-01) re-audits the Validated set above with `file:line` proof. Any item marked Validated but lacking implementation will be demoted at v1.3 close. Today's known drift: RISK-06 (stub), RISK-04 cap (advisory after boot), ADR-010 paper cap (not in code), LSTM-archived claim (false).

*Track A — Execution:*
- **AUDIT-01 (Phase 16):** Re-audit Validated set with `file:line` evidence; demote items lacking implementation
- **TE-CAP-01..05 (Phase 17):** Cap-rejection in order loop; emergency-stop admin auth; RISK-06 maker/post-only impl; ADR-010 paper cap in code; kill bare-except in order path
- **BC-FIX-01..03 (Phase 18):** Fix `bybit_adapter.py` dead endpoint paths; extend `TapeReplayClient` with order endpoints; contract tests against bybit-connector
- **RECON-01..02 (Phase 19):** Order-state polling/WS handler; `orderLinkId` on every place + retry
- **PAPER-01..03 (Phase 20):** Paper-sim SL/TP triggers + slippage model; 48h max-hold + stop-loss-as-limit regression tests

*Track B — Signal + ML:*
- **TA-AGG-01..04 (Phase 21):** Bring ADX + Volume + SQZMOM into aggregator vote; reconcile MACD route/settings; reconcile BB std-dev; look-ahead-leakage regression tests
- **PRICE-01..02 (Phase 22):** Fix `round(price, 2)` at all 6 surviving call sites; sub-$1 asset fixture suite; CI grep gate
- **ML-PURGE-01..05 (Phase 23):** Remove price-level `r2_score` from trainer + verify; archive LSTM (ensemble_model + lstm.py); fix `feature_engineer.get_feature_names()`; marker-age check on `mlgate_auto_flip.json`; CI grep gate

*Cross-cutting:*
- **HYG-01..04 (Phase 24):** Fix stale Sentiment log; DSR staleness enforcement on auto-flip; TA CORS lockdown; deprecate legacy `/api/v1/market/*` at api-gateway

### Future (deferred from v1.3)

- Operator-action carry-overs (no code work owed): execute LIVECLOSE-01..05 harnesses + close CIRESTORE-01/02 after OP-04 resolves
- Tournament-harness first cross-symbol expansion (XRP/AVAX) — gated on production validation
- Multi-horizon production deployment (1h/4h/24h with per-horizon trading paths) — depends on MLGATE landing first
- Sentiment-as-filter integration — gated on T0.1.x evidence
- Classification head + calibration

### Out of Scope

<!-- Explicit boundaries. Reasoning kept to prevent re-adding. -->

- Real-money LIVE trading enabled by default — paper-mode is the safety boundary; LIVE requires four explicit flag flips (`PAPER_TRADING_MODE=false`, `TRADING_MODE=LIVE`, mainnet keys with trade permissions, `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY`); pre-LIVE checklist must restore per-trade cap to ≤2% (currently 10% in paper per ADR-010).
  - When flipping LIVE is in scope, the 6-precondition Diagnose/Action/Verification path lives in [RUNBOOK.md "Pre-LIVE Operator Checklist"](../RUNBOOK.md#pre-live-operator-checklist). Phase 8 enforces these in code; v1.1 does not flip LIVE.
- 30+ parallel LLM subagents for tournament — confirmed wrong primitive; Docker isolation is the right one.
- Auto-merge of tournament-winning PRs — confirmed unsafe; `gh pr merge` CI grep gate enforced.
- Live-exchange prices in every pytest run — deterministic suite uses recorded tape; one nightly live smoke allowed flaky.
- Unattended "iterate till green" loops — confirmed Goodhart trap; anti-mock guard enforces.
- `ENABLE_ML_PREDICTIONS=true` by default — blocked behind DSR > 0.95 evidence on returns.
- XRP/AVAX in production allocations — only BTC/ETH/SOL/BNB/ADA validated; tournament may evaluate; production deployment requires separate validation milestone.
- Mobile-native app — web dashboard sufficient for solo operator.
- Rewrite of any of the 15 services — stack locked.
- K8s deployment — docker-compose only for v1.x.
- Sentiment-as-filter integration — v2 candidate, deferred until T0.1.x lands evidence.
- Classification head + calibration — v2.
- Server-side `/ws/metrics` + client WS subscription layer — v2.
- Mobile-friendly responsive layout — v2.
- Cross-symbol tournament including XRP/AVAX — v2 after validation-layer review.
- Multi-horizon search (1h/4h/24h) with per-horizon production deployment — v2.

## Context

- **Repo:** github.com/MohammedSiradj/crypto-trading-bot. Local main and origin/main at parity as of 2026-05-15T02:20Z (OP-05 closed).
- **Stack:** 15 Docker services orchestrated via `docker-compose.unified.yml`; FastAPI services; React/Vite frontend; TimescaleDB + Redis for storage; RabbitMQ for events; Vault (dev TLS-disabled) for secrets. Plus tournament-harness on port 8010 (profile-gated).
- **LOC:** v1.0 added +159,471 / -2,816 across 764 files (427 commits in 9 days). v1.1 added +14,522 / -574 across 92 code files in services/scripts/tests/.github/frontend (138 commits in 4 days post v1.0 tag; total branch diff including planning artifacts: +31,072 / -47,475 across 339 files reflecting concurrent _archive_lstm/* removals).
- **Operator profile:** Solo founder, paper-trading on Bybit mainnet prices, WSL2 + Docker Desktop host (BuildKit hangs documented in RUNBOOK).
- **Trust posture:** "Trust no docs" — every safety claim verified against code (`file:line`) before relying on it. v1.0 audit confirmed 19/23 REQs satisfied with file:line evidence.
- **V0 finding (load-bearing):** Pre-2026-04-30 ML evaluation numbers (R²=0.99, Dir.Acc 79–84%) were a metric bug (look-ahead leakage). Post-fix, GRU is chance-level on returns. Persistence baseline beats it. ML predictions remain off by default until a returns-target model passes the DSR gate. v1.0 tournament harness is the path to evidence.
- **Audit baseline:** 17-agent deep audit on 2026-04-28; Tier-1 implementation 2026-04-30; v1.0 9-phase milestone shipped 2026-05-15 (audit at `.planning/milestones/v1.0-MILESTONE-AUDIT.md`); v1.1 5-phase milestone shipped 2026-05-18 (audit at `.planning/milestones/v1.1-MILESTONE-AUDIT.md` — `gaps_found` reconciled at close to 17/19 deliverables shipped with 2 operator-blocked on OP-04).

## Constraints

- **Tech stack**: Python 3.11+ services / Node+React frontend / Docker Compose orchestration — locked.
- **Compatibility**: Bybit-first; no other exchange.
- **Performance**: Paper-trade round-trip <60s end-to-end (signal → order ack → portfolio update) — integration test asserts this against fresh clone.
- **Security**: Real exchange API keys in `.env` (gitignored); never `git clean -fdx` against working tree; bootstrap-tests always run against fresh clone in tmp.
- **Data integrity**: Backtest filters `is_mainnet=true` to avoid testnet-flip contamination from 2026-04-25.
- **Evaluation**: All ML edge claims go through `returns_metrics.py` + PSR/DSR + CPCV via tournament-harness. Raw R² on price levels forbidden (TOURN-07 CI grep gate enforced).
- **Autonomy**: No unattended loops that weaken tests, mock failing pieces, or auto-merge.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Skip GSD codebase mapping; bootstrap from existing CLAUDE.md + audit memory + V0 finding | High-context audit + handoff docs already covered stack/architecture | ✓ Good |
| Tournament harness is Bash/Python + Docker, not LLM subagents | Agent tool spawns share parent shell; no per-experiment memory isolation | ✓ Good — TOURN-01 shipped |
| Drop `>5% R²` win criterion; use DSR + bootstrap p<0.05 on OOS Sharpe / corrected Dir.Acc | R²=0.995 baseline made >5% impossible; raw R² is the V0-finding bug | ✓ Good — TOURN-05 shipped |
| Bootstrap-tests run against fresh `git clone` into tmp, not working tree | `git clean -fdx` would delete `.env` (real API keys) + uncommitted model weights | ✓ Good — INFRA-02/03 shipped |
| Tournament wins open draft PRs; humans merge | Auto-merge against trading code unsafe even with significance gates | ✓ Good — TOURN-06 + grep gate |
| pytest `--ignore` over `--deselect` in integration CI step | `--deselect` is rootdir-relative; silently matched nothing when used cwd-relative; `--ignore` works correctly | ✓ Good — Phase 4 verified 26 passed |
| 0-SKIP grep guard in container-integration CI | Pairs with `test_canonical_metrics_importable.py` defence-in-depth — catches silent namespace-merge regression | ✓ Good — Phase 4 |
| T0.1.x experiment = `different_horizon` (GRU × horizon[3,5,7,10] × 3 symbols) | Pure YAML edit, zero new Python; fastest path to evidence | ⚠ Pending — INSUFFICIENT_DATA pending OP-02/OP-03 |
| Document `run_extended_backtest.py` divergence permanently (ADR-012) over rewrite to CoreAggregator | Tournament harness is the honest-evaluation path; backtest is regime-characterisation only | ✓ Good — MLCL-04 shipped |
| Tier-2 monitoring deleted (ADR-011: `keep_tier1_delete_tier2`) | STRIDE analysis flagged `claude -p` agentic subprocess in CI as unsafe | ✓ Good — MLCL-03 shipped |
| Phase3Dashboard 503 retry short-circuit on `useQuery` hooks | `retry: 2` + exponential backoff kept `isLoading=true` ~7s, Playwright `networkidle` fired mid-skeleton | ✓ Good — Phase 7.2 smoke green |
| Paper-mode per-trade risk cap relaxed to 10% (ADR-010) | Bybit min-notional on $100 paper balance; pre-LIVE checklist must restore ≤2% | ⚠ Revisit before TRADING_MODE=LIVE; Phase 8 enforces ≤2% at trading-engine boot in LIVE |
| v1.1: Phase 11 umbrella → Phase 11.1 harnesses-only split | Keep code-deliverable distinct from wall-clock operator execution; milestone closes on code scope rather than on operator availability | ✓ Good — v1.1 closed 17/19 with clean carry-over semantics |
| v1.1: 3-state requirements taxonomy at close (complete/harness-delivered/operator-blocked) | Collapses the four-source-of-truth conflict (REQUIREMENTS `[x]` vs PROJECT.md Validated vs audit Satisfied vs reality post-execution) | ✓ Good — single archived REQUIREMENTS.md is now internally consistent |
| v1.1: Pre-LIVE preflight enforced at three layers (CLI + HTTP + boot) | Single-layer enforcement is fragile to silent removal; defense-in-depth survives one path regressing | ✓ Good — CI grep gates pin each layer |
| v1.1: MLGATE-02 cold-boot returns UNKNOWN, not error | `/run/mlgate_auto_flip.json` marker absent on first boot; route mount post-init_ml() means gate is only reachable post-marker | ✓ Good — graceful degradation documented in 09-VERIFICATION |
| v1.1: Scheduler in-process Python call (not admin-guarded HTTP) | notification-service → trading-engine via direct `alert_manager.send_daily_summary` invocation; regression test pins the contract | ✓ Good — eliminates admin-auth burden on intra-cluster scheduler |
| v1.1: Self-trigger-safe billing-failure-detector | Workflow name must not contain its own substring filter; jq `select(.name != own_name)` is defense-in-depth | ✓ Good — Phase 12 12-test grep-gate net pins it |
| v1.1: Direct curl to api.telegram.org from GH Actions | In-cluster notification-service unreachable from GitHub-hosted runners (forced design) | ✓ Good — documented decision in 12-CONTEXT.md |
| v1.1: LIVECLOSE-05 supervised-run-only | Two-key authorization on the harness + explicit orchestrator refusal of `--exec liveclose-05`; never auto-invokable | ✓ Good — protects against agentic LIVE-flip |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-23 — v1.3 TA + Engine Correctness milestone ratified after 3-agent forensic audit; v1.2 Polish & Real-Time shipped (13/13 REQs satisfied + 3 deferred operator carry-ins / SDK ports). Validated-set drift documented under v1.3 Active block — Phase 16 (AUDIT-01) will reconcile.*
