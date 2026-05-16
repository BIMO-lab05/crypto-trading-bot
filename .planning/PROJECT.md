# Crypto Trading Bot

## What This Is

A self-hosted, microservices-based crypto trading bot targeting Bybit (paper trading by default; live trading gated behind three explicit flag flips). Runs a 9-indicator voting aggregator over OHLCV + sentiment + (optional) ML signals, with portfolio management, risk caps, and a React dashboard. Built and operated by a solo founder; safety and honest measurement come before performance claims.

## Core Value

The bot must never lose money it wasn't authorized to risk. Every trade goes through enforced risk caps (per-trade, daily-loss, drawdown, kill-switch) backed by code that actually runs — and any "edge" claim must be backed by DSR/CPCV evidence, not raw R² on price levels.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. Inferred from existing code and recent commits. -->

- ✓ **EXEC-01**: 15-container microservices stack (api-gateway, trading-engine, market-data, technical-analysis, ml-prediction, ml-retraining, risk-metrics, portfolio-manager, sentiment-analysis, notification-service, etc.) — existing
- ✓ **EXEC-02**: Bybit mainnet price feed (`BYBIT_TESTNET=false`); paper trading default (`PAPER_TRADING_MODE=true`) — existing
- ✓ **EXEC-03**: 9-indicator voting aggregator (RSI, MACD, BB, ATR, EMA, ADX, OBV, Stoch, IchiCloud) with TREND_FILTER + VOLUME_CONFIRMATION (`technical-analysis/CoreAggregator`) — existing
- ✓ **RISK-01**: Real risk caps wired (5% daily-loss, 20% drawdown, 5 consec losses) reading from settings, not hardcoded "RELAXED FOR SAMPLE COLLECTION" values — commit `bef66cb`
- ✓ **RISK-02**: `auto_trading_enabled=False` gate prevents auto-trader auto-start — commit `bef66cb`
- ✓ **RISK-03**: EMERGENCY_STOP file wired end-to-end (api-gateway authenticated write + trading-engine read at STEP-0 of loop) — commits `4547df5`, `1fb9008`
- ✓ **RISK-04**: Per-trade cap enforced at execution (not just config-logged) — commit `39352ba`
- ✓ **RISK-05**: Per-position vol parity (`vol_targeting.py`, 16 tests, default off) — Tier-1 2026-04-30
- ✓ **RISK-06**: Maker-order entry path with fallback (LIVE-only, default off) — Tier-1 2026-04-30
- ✓ **RISK-07**: Funding-rate gate skips trades during high-cost funding windows (default off) — Tier-1 2026-04-30
- ✓ **ML-01**: Honest returns metrics module (`returns_metrics.py`) emitting `r2_returns` and `dir_acc_corrected` on every train — replaces look-ahead-leakage metric — commit `c56765c`
- ✓ **ML-02**: PSR/DSR (`sharpe_metrics.py`, 29 tests) and CPCV (`cpcv.py`, 30 tests) shipped in `risk-metrics-service` — Tier-1 2026-04-30
- ✓ **ML-03**: CPCV wired into `ml-retraining-service` train loop with optional `retrain_min_dsr` gate (default informational) — commits `29a27fd`/`d49bfa0`/`679e473`/`7c7b7ab`, 2026-05-01
- ✓ **ML-04**: ML retrained-model handoff + live-reload (fixes `.npy`/`.pkl` scaler mismatch + cache-on-init bug) — commit `ecdb29d`
- ✓ **ML-05**: `ENABLE_ML_PREDICTIONS=false` by default — V0 finding 2026-04-30 showed GRU has no measurable edge after metric fix
- ✓ **DATA-01**: TimescaleDB `klines` table tagged with `is_mainnet` column; backtest filters mainnet by default — commits `3d1312f`, `14995b2`
- ✓ **DATA-02**: Confidence sentinel chain cleaned (technical-analysis real RSI/MACD/trend confidence; ml-prediction floor=0.0; ensemble failure-sentinel flag) — commits `2d2c524`, `d4d066b`, `e7ea351`
- ✓ **OBS-01**: Telegram notification with bot-token redaction in logs — commit `8ef3ff0`
- ✓ **OBS-02**: Sentiment endpoints honest (501 Not Implemented for fabricated `/trend`+`/aggregate`; `/combined` returns 503 instead of fabricating neutral) — commit `41bd5ab`
- ✓ **UI-01**: React dashboard (Vite) with REST-polling performance metrics (dead WebSocket scaffolding stripped) — commit `6a424e3`
- ✓ **TEST-01**: ~101 new tests across the Tier-1 modules; full suite green for changed services
- ✓ **INFRA-01**: pytest integration suite + fresh-clone round-trip + ML-on variant + notification delivery + 3 pre-existing bug regressions — all wired (10 plans, 13 review findings fixed). Live Docker run pending in `02-HUMAN-UAT.md`. Validated in Phase 02.
- ✓ **INFRA-04**: CI workflows `.github/workflows/integration.yml` (per-push + PR with anti-mock guard) and `.github/workflows/integration-ml-on.yml` (nightly + manual). Validated in Phase 02.
- ✓ **INFRA-05**: Iteration harness `scripts/iter-fix.sh` + anti-mock guard `scripts/iter-fix-check-diff.sh` (10/10 test_iter_fix.sh PASS, including `>` direction). Validated in Phase 02.
- ✓ **INFRA-06**: Three named pre-existing bugs triaged — Bug 1 (stale ML model) FIXED with `_reload_if_stale()` in `gru_predictor.py` + log format alignment in `gru_model.py`; Bug 2 (confidence=0) FIXED with `confidence > 0` filter + `AGGREGATOR_CONFIDENCE_FILTER` log in `handlers/analysis.py`; Bug 3 (WSL2 BuildKit) DOCUMENTED in RUNBOOK + `make build-no-buildkit`. Validated in Phase 02.

### Active

<!-- Current scope for this milestone. Hypotheses until shipped + validated. -->

- [ ] **INFRA-02**: Bootstrap script (`bootstrap.sh`) that wires `.env` from a template + brings up the stack reproducibly, with a checkpointed iteration loop for fixing infra bugs (no unattended `git clean -fdx` loop)
- [ ] **INFRA-03**: RUNBOOK.md documenting WSL2 BuildKit hangs, docker context misconfig, stale-model restart procedure, and bootstrap-test failure recovery
- [ ] **TOURN-01**: Docker+SQLite tournament harness (Bash/Python orchestrator, NOT 30 LLM subagents) running GRU/LSTM/Transformer/TCN × {SOL,BNB,ADA} × hyperparameter grid with per-experiment Docker isolation
- [ ] **TOURN-02**: Tournament leaderboard schema + ingest from per-run JSON outputs, queryable by symbol/architecture/horizon
- [ ] **TOURN-03**: Top-3 ensemble vs production significance test (DSR + bootstrap p<0.05 on OOS Sharpe and corrected Dir.Acc lift) — drop the impossible ">5% R²" criterion
- [ ] **TOURN-04**: Auto-open draft PR with leaderboard + significance results when ensemble wins; user merges manually (no auto-merge)
- [ ] **ML-CLEAN-01**: Forward-paper-test the three Tier-1 opt-in features (vol parity, maker, funding) one at a time, ≥7 days each, comparing PSR vs baseline; promote to default-on per-feature only after evidence
- [ ] **ML-CLEAN-02**: Decide on T0.1.x next-attempt direction (different horizon, classification head, XGBoost control, cross-sectional features, sentiment-as-filter) and ship one experiment through the tournament harness
- [ ] **ML-CLEAN-03**: Document and remove or wire the parked `scripts/monitoring/*` autonomous tier-2 system (decision pending)
- [ ] **DASH-01**: Audit the React dashboard end-to-end and fix broken/stale data tiles (REST polling endpoints return what the UI expects; no silent empty states)
- [ ] **DASH-02**: Replace any remaining hardcoded/dead frontend URLs with config-driven values; document gateway-vs-direct-service paths in `vite.config.js`
- [ ] **DASH-03**: Surface real risk-cap state, kill-switch state, and trading-mode (PAPER/LIVE) prominently on the dashboard so the operator sees safety state at a glance
- [ ] **DASH-04**: Add a "Tournament" view that reads the tournament leaderboard schema (depends on TOURN-02)

### Out of Scope

<!-- Explicit boundaries. Reasoning kept to prevent re-adding. -->

- Real-money LIVE trading enabled by default — paper-mode is the safety boundary; LIVE requires three explicit flag flips and is not part of this milestone
  - When flipping LIVE is in scope, the 6-precondition Diagnose/Action/Verification path lives in [RUNBOOK.md "Pre-LIVE Operator Checklist"](../RUNBOOK.md#pre-live-operator-checklist). Phase 8 enforces these in code; v1.1 does not flip LIVE.
- 30+ parallel LLM subagents for tournament — Agent tool spawns share parent shell, no per-experiment isolation; the right primitive is Docker, not subagents
- Auto-merge of tournament PRs — coordinator opens drafts; human merges
- Live-exchange prices in every pytest run — flaky, rate-limited, costs money; deterministic suite runs against recorded tape, one nightly live smoke is allowed to be flaky
- Unattended "iterate until 3 consecutive green runs" loop — Goodhart trap (cheapest path is to weaken assertions); use checkpointed iteration with diff-review per fix
- ENABLE_ML_PREDICTIONS=true by default — blocked behind DSR > 0.95 evidence on returns, never on price-level R²
- Re-introducing client-side WebSocket scaffolding — server route doesn't exist; restoring requires building `/ws/metrics` first
- XRP, AVAX in production allocations — only SOL/BNB/ADA are validated; tournament may include them but production deployment requires separate validation
- Mobile app — web dashboard is sufficient for solo operator

## Context

- **Repo:** github.com/MohammedSiradj/crypto-trading-bot. Local main is 60+ commits ahead of origin/main as of 2026-05-01; many recent fixes not yet pushed.
- **Stack:** 15 Docker services orchestrated via `docker-compose.unified.yml`; FastAPI for service APIs; React/Vite for the dashboard; TimescaleDB + Redis for storage; RabbitMQ for events; Vault (dev TLS-disabled) for secrets.
- **Operator profile:** Solo founder, paper-trading on Bybit mainnet prices, WSL2 host (Docker BuildKit hangs are a known friction point).
- **Trust posture:** "Trust no docs" — the 2026-04-28 17-agent audit found CLAUDE.md ~45% accurate; verify every safety claim against code (`file:line`) before relying on it.
- **V0 finding (load-bearing):** Pre-2026-04-30 ML evaluation numbers (R²=0.99, Dir.Acc 79–84%) were a metric bug (look-ahead leakage). Post-fix, GRU is chance-level on returns. Persistence baseline beats it. ML predictions are off by default until a returns-target model passes the DSR gate.
- **Audit baseline:** 17-agent deep audit on 2026-04-28 + Tier-1 implementation session 2026-04-30 fixed most CRITICAL/HIGH safety regressions. Open items tracked in `project_audit_2026-04-28.md` memory and `SESSION-2026-04-30-handoff.md`.

## Constraints

- **Tech stack**: Python 3.11+ services / Node+React frontend / Docker Compose orchestration — locked; no rewrite in this milestone.
- **Compatibility**: Bybit-first; no other exchange in scope.
- **Performance**: Paper-trade round-trip <60s end-to-end (signal → order ack → portfolio update) — bootstrap-test asserts this.
- **Security**: Real exchange API keys in `.env` (gitignored); never run `git clean -fdx` against the working tree; bootstrap-tests always run against a fresh clone in a tmp directory.
- **Data integrity**: Backtest must filter `is_mainnet=true` to avoid testnet-flip contamination from 2026-04-25.
- **Evaluation**: All ML edge claims go through `returns_metrics.py` + PSR/DSR (`sharpe_metrics.py`) + CPCV (`cpcv.py`). Raw R² on price levels is forbidden.
- **Autonomy**: No unattended loops that can weaken tests, mock failing pieces, or commit/push without checkpoint review.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Skip GSD codebase mapping; bootstrap from existing CLAUDE.md + audit memory + V0 finding | Project already has high-context audit + handoff docs covering stack, architecture, risk-control posture; another mapper run would duplicate work | — Pending |
| Treat shipped Tier-1 work as Validated, frame new milestone around 4 user-named initiatives (Infra, Tournament, ML cleanup, Dashboard) | User stated scope explicitly; matches paused-work memory from 2026-04-27 | — Pending |
| Drop `>5% R²` win criterion for tournament; use DSR + bootstrap p<0.05 on OOS Sharpe / corrected Dir.Acc | R²=0.995 baseline made >5% impossible; raw R² on price levels is the bug behind the V0 finding | — Pending |
| Bootstrap-tests run against a fresh `git clone` into tmp, not the working tree | `git clean -fdx` would delete `.env` (real API keys) and uncommitted model weights | — Pending |
| Tournament harness is Bash/Python + Docker, not LLM subagents | Agent tool spawns share parent shell; no per-experiment memory isolation | — Pending |
| Tournament wins open draft PRs; humans merge | Auto-merge against trading code is unsafe even with significance gates | — Pending |

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
*Last updated: 2026-05-08 after Phase 02 completion (integration-test-suite-runbook)*
