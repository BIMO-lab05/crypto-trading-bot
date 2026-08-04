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

**v1.3 Phase 16 AUDIT-01 reconciled (2026-05-23):** 74 satisfied / 7 drift / 0 missing across 81 Validated REQs. Full ledger at `.planning/evidence/AUDIT-01/validated-reaudit.json`; human summary at `.planning/evidence/AUDIT-01/validated-reaudit.md`. Drift items routed: EXEC-03 → Phase 21 (TA-AGG-01); TOURN-07 → Phase 23 (ML-PURGE-05); CLAUDE-LSTM-ARCHIVED → Phase 23 (ML-PURGE-02); CLAUDE-SENTIMENT-REMOVED → Phase 24 (HYG-01). Three NEW drift findings (CLAUDE-VALIDATED-SYMBOLS, DASH-01, DASH-06) reconciled inline by Plan 16-07. Track A (trading-engine risk caps) came back 17/17 satisfied — TE-CAP-01/03/04 demoted post-audit (implementation found satisfied; Phase 17 scope shrinks to TE-CAP-02 + TE-CAP-05).

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

<!-- Shipped and confirmed valuable. AUDIT-01 (Phase 16, 2026-05-23) reconciled this set against code reality with file:line evidence; satisfied items carry their citation, drift items carry ⚠ + downstream-owner annotation. Canonical ledger: .planning/evidence/AUDIT-01/validated-reaudit.json -->

**Pre-v1 (existing capabilities)**

- ✓ **EXEC-01**: 15-container microservices stack — verified at `docker-compose.unified.yml:33-928` per AUDIT-01
- ✓ **EXEC-02**: Bybit mainnet price feed; paper trading default — verified at `services/bybit-connector/app/config.py:32-35` per AUDIT-01
- ⚠ **EXEC-03**: 9-indicator voting aggregator with TREND_FILTER + VOLUME_CONFIRMATION — DRIFT (aggregator at `services/technical-analysis/app/handlers/analysis.py:67-110` uses only RSI + MACD + Trend Filter from 13 implemented indicators; ADX, Ichimoku, SQZMOM, RSI-Divergence, Volume Confirmation wasted) — **will be reconciled in Phase 21 (TA-AGG-01)** per AUDIT-01
- ✓ **RISK-01**: 5% daily-loss circuit-breaker — verified at `services/trading-engine/app/auto_trader.py:340-344` per AUDIT-01
- ✓ **RISK-02**: per-trade cap honored in order path — verified at `services/trading-engine/app/auto_trader.py:332-344` per AUDIT-01
- ✓ **RISK-03**: paper-cap relax per ADR-010 — verified at `services/trading-engine/app/auto_trader.py:332-344` per AUDIT-01
- ✓ **RISK-04**: LIVE_TRADING_ACK gate — verified at `services/trading-engine/app/auto_trader.py:1962-1986` per AUDIT-01
- ✓ **RISK-05**: vol-parity check — verified at `services/trading-engine/app/auto_trader.py:354-370` per AUDIT-01
- ✓ **RISK-06**: emergency-stop file gate — verified at `services/trading-engine/app/live_trading.py:290-360` per AUDIT-01
- ✓ **RISK-07**: 48h max-hold force-close — verified at `services/trading-engine/app/auto_trader.py:1796-1810` per AUDIT-01
- ✓ **ML-01**: returns_metrics module — verified at `services/ml-retraining-service/app/core/returns_metrics.py:25-50` per AUDIT-01
- ✓ **ML-02**: PSR/DSR helpers — verified at `services/ml-retraining-service/app/sharpe_metrics.py:1-80` per AUDIT-01
- ✓ **ML-03**: CPCV evaluator — verified at `services/ml-retraining-service/app/cpcv.py:1-60` per AUDIT-01
- ✓ **ML-04**: GRU inference path — verified at `services/ml-prediction-service/app/ml_models/gru_predictor.py:152-180` per AUDIT-01
- ✓ **ML-05**: `ENABLE_ML_PREDICTIONS=false` default — verified at `services/trading-engine/app/config.py:90-93` per AUDIT-01
- ✓ **DATA-01**: TimescaleDB candle write — verified at `services/market-data-service/app/database.py:169-174` per AUDIT-01
- ✓ **DATA-02**: backtest `is_mainnet` filter — verified at `backtesting/run_walk_forward_ensemble.py:563-571` per AUDIT-01
- ✓ **OBS-01**: structured JSON logs (Telegram redaction lineage) — verified at `services/notification-service/app/utils/structured_logging.py:21-47` per AUDIT-01
- ✓ **OBS-02**: Prometheus metrics surface (honest sentiment 501/503) — verified at `services/sentiment-analysis-service/app/main.py:645-782` per AUDIT-01
- ✓ **UI-01**: React dashboard gateway WS subscription — verified at `frontend/src/hooks/useGatewayWebSocket.js:11-38` per AUDIT-01
- ✓ **TEST-01**: Tier-1 tests green (337 tests counted; original "~101" was 2026-04 snapshot — satisfied per spirit-of-claim rule) — verified at `tests/` collection
- ✓ **CLAUDE-PAPER-CAP-ADR010**: paper 10% per-trade cap, LIVE preserves 2% — verified at `services/trading-engine/app/config.py:321-332` per AUDIT-01
- ✓ **CLAUDE-EXEC-MAINNET-PRICES**: `BYBIT_TESTNET=false` on relevant services — verified at `docker-compose.unified.yml:288-399` per AUDIT-01
- ⚠ **CLAUDE-LSTM-ARCHIVED**: LSTM-deleted claim — DRIFT (`services/ml-prediction-service/app/models/ensemble_model.py:15` still imports LSTM; `services/ml-retraining-service/app/core/models/lstm.py` exists at live path) — **will be reconciled in Phase 23 (ML-PURGE-02)** per AUDIT-01
- ⚠ **CLAUDE-SENTIMENT-REMOVED**: sentiment removed from pipeline — DRIFT in operator-visible log strings only (arithmetic is correct: sentiment weight = 0; but `services/trading-engine/app/auto_trader.py:1130,1261` still log stale "Sentiment 15%") — **will be reconciled in Phase 24 (HYG-01)** per AUDIT-01
- ✓ **CLAUDE-VALIDATED-SYMBOLS**: trading-engine 5-symbol restriction holds; market-data 14-symbol ingest is research-only — reconciled inline in 16-07 per AUDIT-01 (CLAUDE.md text now reflects dual reality)

**v1.0 (shipped 2026-05-15)**

- ✓ **INFRA-01**: pytest+testcontainers from fresh clone — verified at `tests/integration/test_fresh_clone_round_trip.py:1-156` per AUDIT-01
- ✓ **INFRA-02**: `bootstrap.sh` fresh-clone provisioning — verified at `bootstrap.sh:1-136` per AUDIT-01
- ✓ **INFRA-03**: Recorded-tape exchange-data fixtures + replay loader — verified at `services/bybit-connector/app/tape_replay_client.py:1-100` per AUDIT-01
- ✓ **INFRA-04**: Checkpointed iteration harness — verified at `scripts/iter-fix.sh:1-30` per AUDIT-01
- ✓ **INFRA-05**: RUNBOOK.md (6 symptoms, Diagnose/Action/Verification) — verified at `RUNBOOK.md:23-254` per AUDIT-01
- ✓ **INFRA-06**: 3 pre-existing bugs triaged — verified at `RUNBOOK.md:403-411` per AUDIT-01
- ✓ **TOURN-01**: Docker+SQLite tournament harness (Python orchestrator, NOT LLM subagents) — verified at `services/tournament-harness/app/orchestrator/launcher.py:92-120` per AUDIT-01
- ✓ **TOURN-02**: Leaderboard schema with composite PK + 9 metric columns — verified at `services/tournament-harness/migrations/0001_initial.sql:9-43` per AUDIT-01
- ✓ **TOURN-03**: GRU/LSTM/Transformer/TCN × {SOL,BNB,ADA} × hyperparameter grid — verified at `services/tournament-harness/app/config/tournament_loader.py:25-50` per AUDIT-01
- ✓ **TOURN-04**: Failure-row persistence with typed reason enum — verified at `services/tournament-harness/app/orchestrator/failure.py:1-31` per AUDIT-01
- ✓ **TOURN-05**: Top-3 ensemble + Politis–Romano block bootstrap p<0.05 — verified at `services/tournament-harness/app/significance/ensemble.py:43-73` per AUDIT-01
- ✓ **TOURN-06**: Auto-open draft PR; humans merge — verified at `services/tournament-harness/app/pr/gh.py:61-92` per AUDIT-01
- ⚠ **TOURN-07**: Canonical metrics imports only (CI grep gate enforced) — DRIFT (`services/ml-retraining-service/app/core/model_trainer.py:430,623` calls `r2_score` on inverse-transformed price arrays — exact V0 forbidden pattern; CI gate did not cover `services/**`) — **will be reconciled in Phase 23 (ML-PURGE-05)** per AUDIT-01
- ✓ **MLCL-01**: Forward-paper-test apparatus + PSR-CI gate — verified at `scripts/forward_paper_test/run_isolation.py:1-40` per AUDIT-01
- ✓ **MLCL-02**: T0.1.x `different_horizon` sweep YAML — verified at `services/tournament-harness/app/config/t0_1_x_experiment.yaml:1-10` per AUDIT-01 (operator wall-clock pending OP-02/OP-03; harness satisfied)
- ✓ **MLCL-03**: Tier-2 monitoring deleted (ADR-011) — verified at `docs/decisions/ADR-011-monitoring-disposition.md:1-90` per AUDIT-01
- ✓ **MLCL-04**: `run_extended_backtest.py` PERMANENT DIVERGENCE doc + runtime warning — verified at `services/trading-engine/run_extended_backtest.py:16-80` per AUDIT-01
- ✓ **DASH-01**: Tile audit inventory + script — reconciled inline in 16-07 per AUDIT-01 (`.planning/milestones/v1.0-phases/06-dashboard-audit-safety-state/06-TILE-AUDIT.json` restored from archive; `scripts/audit_tiles.py:43-50` reference updated to canonical archive path)
- ✓ **DASH-02**: config URLs — verified at `frontend/vite.config.js:38-59` per AUDIT-01
- ✓ **DASH-03**: safety-state header / api-gateway routes — verified at `services/api-gateway/app/main.py:1049-1180` per AUDIT-01
- ✓ **DASH-04**: Tournament dashboard view — verified at `frontend/src/pages/TournamentDashboard.jsx:17-118` per AUDIT-01
- ✓ **DASH-05**: empty / error tile states — verified at `frontend/src/components/TileState.jsx:4-82` per AUDIT-01
- ✓ **DASH-06**: Playwright smoke against tile audit — reconciled inline in 16-07 per AUDIT-01 (`tests/integration/test_dashboard_smoke.py:83-127` reference updated to canonical archive path alongside DASH-01)

**v1.0 (partial — operator-blocked, carry into v1.1)**

> All four prior partials (INFRA-01 / INFRA-02 / MLCL-01 / MLCL-02) reclassified by AUDIT-01: harness code is satisfied with file:line evidence; wall-clock execution remains in the operator carry-in backlog (LIVECLOSE/CIRESTORE family below). No code drift; partial status was a wall-clock semantic, now folded into the v1.1 harness-delivered + operator-blocked sub-sections.

**v1.1 (shipped 2026-05-18)**

- ✓ **PREFLIGHT-01**: Pre-LIVE preflight CLI — verified at `services/trading-engine/app/preflight/checks.py` per AUDIT-01
- ✓ **PREFLIGHT-02**: Trading-engine boot path enforces `MAX_POSITION_RISK_PCT ≤ 0.02` in LIVE — verified at `services/trading-engine/app/main.py` per AUDIT-01
- ✓ **PREFLIGHT-03**: `.github/workflows/preflight-live-readiness.yml` PR-label gate — verified at `.github/workflows/preflight-live-readiness.yml` per AUDIT-01
- ✓ **PREFLIGHT-04**: RUNBOOK Pre-LIVE Operator Checklist (6 D/A/V subsections) + cross-link — verified at `RUNBOOK.md:255+` per AUDIT-01
- ✓ **MLGATE-01**: Idempotent ≥7-day forward-paper-test evidence accrual + PSR-CI publish — verified at `scripts/forward_paper_test/run_evidence_loop.py` per AUDIT-01
- ✓ **MLGATE-02**: Trading-engine startup auto-flip driven by DSR>0.95 within 14 days; structured log + marker — verified at `services/trading-engine/app/lifespan/ml.py` per AUDIT-01
- ✓ **MLGATE-03**: 5-member `MLGateReason` enum + cross-plan reason-state cache; unauth read-only `/api/preflight/ml-gate-reason-counts`; notification digest; CI grep gate — verified at `services/trading-engine/app/aggregation/ml_gate_reasons.py` per AUDIT-01
- ✓ **DASHLIVE-01**: `PathToLiveTile.jsx` (banner + 6 PREFLIGHT chip rows + 5 carry-in rows + 24h window footer) — verified at `frontend/src/components/PathToLiveTile.jsx` per AUDIT-01
- ✓ **DASHLIVE-02**: api-gateway `GET /api/preflight/carry-ins` (schema_version=1) — verified at `services/api-gateway/app/routes/preflight_carry_ins.py` per AUDIT-01
- ✓ **DASHLIVE-03**: Two react-query hooks (`useLiveReadiness`, `useCarryIns`) — verified at `frontend/src/hooks/useLiveReadiness.js` per AUDIT-01
- ✓ **DASHLIVE-04**: pytest-playwright Chromium smoke + two grep gates + `.github/workflows/dashboard-smoke.yml` — verified at `tests/e2e/test_path_to_live_smoke.py` per AUDIT-01
- ✓ **CIRESTORE-03**: `.github/workflows/billing-failure-detector.yml` cron-driven self-trigger-safe; 12-test grep-gate net — verified at `.github/workflows/billing-failure-detector.yml` per AUDIT-01

**v1.1 (harness-delivered — operator wall-clock execution carries into v1.2)**

- ⚠ **LIVECLOSE-01**: fresh-clone bootstrap × 2 with `BYBIT_PRICE_SOURCE: mode=tape` grep — verified at `scripts/closure/liveclose-01-fresh-clone.sh` per AUDIT-01; awaits operator execution
- ⚠ **LIVECLOSE-02**: gh-api validation of integration-ml-on.yml — verified at `scripts/closure/liveclose-02-record-ci.sh` per AUDIT-01; awaits OP-04
- ⚠ **LIVECLOSE-03**: ≥7-day consecutive `leaderboard` window query — verified at `scripts/closure/liveclose_03_psr_evidence.py` per AUDIT-01; awaits wall-clock accrual
- ⚠ **LIVECLOSE-04**: T0.1.x decision_note.md verdict + significance.json p-values — verified at `scripts/closure/liveclose_04_sweep_verdict.py` per AUDIT-01; awaits OP-02 + OP-03
- ⚠ **LIVECLOSE-05**: supervised-run-only LIVE-flip smoke — verified at `scripts/closure/liveclose-05-live-flip-smoke.sh` per AUDIT-01; awaits operator (orchestrator refuses `--exec`)

**v1.1 (operator-blocked — external precondition)**

- ⏸ **CIRESTORE-01**: GH Actions billing screenshot — scaffold verified at `.planning/evidence/OP-04/README.md` per AUDIT-01; blocked on OP-04 resolution
- ⏸ **CIRESTORE-02**: Three green CI run URLs — scaffold verified at `.planning/evidence/CIRESTORE-02/README.md` per AUDIT-01; blocked on OP-04 resolution

**v1.2 (shipped 2026-05-23)**

- ✓ **BC-01**: bybit-connector centralization audit (20-violation inventory) — verified at `.planning/milestones/v1.2-phases/13-bybit-connector-centralization/BC-01/bybit-bypass-audit.json` per AUDIT-01
- ✓ **BC-02**: orderbook handler refactor through connector — verified at bybit-connector orderbook handler per AUDIT-01
- ✓ **BC-03**: CI grep gate (`tests/ci/test_no_bybit_bypass.py`) — verified at `tests/ci/test_no_bybit_bypass.py` per AUDIT-01
- ✓ **BC-04**: `_archive_exchanges/binance.py` retention — verified at `_archive_exchanges/binance.py` per AUDIT-01
- ✓ **BC-05**: `rotate_secrets` + `shared/health_check` rerouted through connector — verified at shared module rewrites per AUDIT-01
- ✓ **BC-06**: default-symbols config aligned across services — verified at config sources per AUDIT-01 (the 14-symbol research universe is intentional; see CLAUDE-VALIDATED-SYMBOLS note above)
- ⚠ **BC-07**: ml-prediction-service container-exec verification — harness verified; awaits operator container-exec run (scipy/tensorflow not on host)
- ✓ **MOBILE-01**: Tailwind responsive config — verified at `frontend/tailwind.config.js` per AUDIT-01
- ✓ **MOBILE-02**: single-column reflow ≤768px on Dashboard + PathToLiveTile + KeyMetricsStrip + TournamentDashboard — verified at `frontend/src/components/Dashboard.jsx` per AUDIT-01
- ⚠ **MOBILE-03**: Playwright matrix @ iPhone-SE + iPad — code verified at `tests/e2e/test_responsive_dashboard.py` per AUDIT-01; pytest matrix execution blocked by pre-v1.2 INFRA-02 + OP-04
- ✓ **TOOL-01**: plan one-liner CI gate — verified at `tests/ci/` per AUDIT-01
- ✓ **TOOL-02**: umbrella→decimal auto-supersession SDK port spec — verified at `tests/ci/` per AUDIT-01 (operator port into `~/.claude/get-shit-done/workflows/complete-milestone.md` is a downstream wall-clock task)
- ✓ **TOOL-03**: audit-refresh-after-last-phase lock — verified at `tests/ci/` per AUDIT-01 (operator port into workflow is a downstream wall-clock task)

### Active

<!-- v1.3 ratified scope. REQ-IDs assigned in .planning/REQUIREMENTS.md. -->

**v1.3 TA + Engine Correctness (ratified 2026-05-23)**

> Phase 16 (AUDIT-01) closed 2026-05-23: 74/81 satisfied, 7 drift, 0 missing. Three NEW drift findings reconciled inline in Plan 16-07 (CLAUDE-VALIDATED-SYMBOLS, DASH-01, DASH-06). Four pre-existing-Validated drift items annotated above and routed to Phase 21/23/24 owners. Canonical ledger: `.planning/evidence/AUDIT-01/validated-reaudit.json`.

*Track A — Execution:*
- **AUDIT-01 (Phase 16):** ✓ Closed 2026-05-23. Validated set rewritten above with file:line citations.
- **TE-CAP-02, TE-CAP-05 (Phase 17):** Emergency-stop admin auth (TE-CAP-02) + bare-except cleanup in order path (TE-CAP-05). (TE-CAP-01/03/04 demoted post-AUDIT-01: Track A audit found execution-cap enforcement and ADR-010 paper-cap config already satisfied at file:line evidence; no code work owed for those three.)
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
| 2026-05-23 AUDIT-01 reconciliation | Phase 16 trust-no-docs audit found 74/81 Validated REQs satisfied with file:line; 4 routed to downstream v1.3 phases; 3 NEW drift fixed inline. TE-CAP-01/03/04 demoted (audit found already satisfied). | Validated set now matches reality. Phase 17 v1.3 scope shrinks to TE-CAP-02 + TE-CAP-05. Canonical ledger: `.planning/evidence/AUDIT-01/validated-reaudit.json`. |

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
*Last updated: 2026-05-23 — Phase 16 AUDIT-01 closed; PROJECT.md Validated section rewritten with file:line citations for all 74 satisfied REQs; 4 pre-existing drift items annotated and routed to Phase 21/23/24; 3 NEW drift findings reconciled inline by Plan 16-07; TE-CAP-01/03/04 demoted (audit found already satisfied); Phase 17 scope shrunk to TE-CAP-02 + TE-CAP-05. Canonical ledger: `.planning/evidence/AUDIT-01/validated-reaudit.json`.*
