# Crypto Trading Bot

## What This Is

A self-hosted, microservices-based crypto trading bot targeting Bybit (paper trading by default; live trading gated behind four explicit flag flips). Runs a 9-indicator voting aggregator over OHLCV + sentiment + (optional) ML signals, with portfolio management, risk caps, a React dashboard, and a Docker-isolated tournament harness that evaluates ML candidates honestly (DSR/CPCV on returns, not raw R²). Built and operated by a solo founder; safety and honest measurement come before performance claims.

## Core Value

The bot must never lose money it wasn't authorized to risk. Every trade goes through enforced risk caps (per-trade, daily-loss, drawdown, kill-switch) backed by code that actually runs — and any "edge" claim must be backed by DSR/CPCV evidence on returns through the tournament harness, not raw R² on price levels.

## Current Milestone: v1.1 Path to LIVE — Close Carry-Ins & LIVE-Readiness

**Goal:** Close all v1.0 operator-blocked carry-ins and ratify the path-to-LIVE checklist with code-enforced preconditions, so flipping `TRADING_MODE=LIVE` becomes a verified four-step act rather than a leap of faith.

**Target features:**
- Closure of v1.0 carry-ins (INFRA-01, INFRA-02 checkpoint, MLCL-01, MLCL-02, DASH-03) via operator-runnable harnesses + verifiable evidence rows.
- Pre-LIVE preflight validator (CLI + CI gate) asserting per-trade cap ≤2%, four flags set correctly, `LIVE_TRADING_ACK` present, mainnet keys with trade permission, `EMERGENCY_STOP` absent, and DSR>0.95 evidence-row exists if ML is enabled.
- Operator-driven ≥7-day forward-paper-test evidence loop with PSR-CI publishing and an auto-gate that flips `ENABLE_ML_PREDICTIONS=true` only when DSR>0.95 lands.
- Path-to-LIVE dashboard tile surfacing every precondition + carry-in OP-* state on a single screen.
- First-green-CI recovery for INFRA-01 nightly, tournament-harness, and DASH-06 once OP-04 (GH Actions billing) is resolved.

## Current State (post v1.0, 2026-05-15)

**Shipped v1.0 (2026-05-06 → 2026-05-15, 9 phases / 50 plans / 427 commits):**

- Reproducible fresh-clone bootstrap (`bootstrap.sh`) + 10 JSONL exchange-data fixtures for deterministic testing
- pytest+testcontainers integration suite from fresh tmp clone (round-trip <60s assertion)
- Anti-mock checkpointed iteration harness (no "iterate till green" loops)
- 6-symptom Diagnose/Action/Verification RUNBOOK at repo root
- Docker-isolated SQLite tournament harness with GRU/LSTM/Transformer/TCN registry
- Bootstrap-significance auto-PR pipeline (`gh pr create --draft` only)
- Forward-paper-test apparatus with per-feature PSR-CI default-on gate
- Tier-2 monitoring deleted (ADR-011); backtest divergence documented (ADR-012)
- Dashboard tile audit (9/9 PASS), safety-state header, TileState empty/error machine
- Tournament view in dashboard + Playwright smoke (green locally, 135s)

**Open at v1.0 close (carries into v1.1):**

- INFRA-02 fresh-clone bootstrap checkpoint never run by operator (Plan 01-03 Task 4)
- INFRA-01 live-stack integration run pending OP-04 (GH Actions billing)
- MLCL-01 ≥7-day forward-paper-test evidence loops = operator wall-clock action
- MLCL-02 T0.1.x sweep verdict = INSUFFICIENT_DATA pending OP-02 (migration 005) + OP-03 (TOURNAMENT_READER_PASSWORD)
- DASH-03 LIVE-flip manual smoke pending OP-01

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

**v1.1 (in progress)**

- ✓ **PREFLIGHT-01..04**: Pre-LIVE preflight CLI + HTTP + boot enforcement + CI workflow + RUNBOOK — Phase 8 (2026-05-16)
- ✓ **MLGATE-01**: Idempotent ≥7-day forward-paper-test evidence accrual + PSR-CI publish (`run_evidence_loop.py` + migration 0002 adding `run_date` + `psr_ci_published` to `leaderboard`) — Phase 9 (2026-05-17)
- ✓ **MLGATE-02**: Trading-engine startup auto-flip of `ENABLE_ML_PREDICTIONS` driven by DSR>0.95 evidence within 14 days; structured `MLGATE_AUTO_FLIP direction=X reason=Y` log + `/run/mlgate_auto_flip.json` schema_version=1 marker; CI grep gate — Phase 9 (2026-05-17)
- ✓ **MLGATE-03**: 5-member MLGateReason enum + cross-plan reason-state cache; structured-reason logging at trading-engine ML-disabled sites; unauth read-only `/api/preflight/ml-gate-reason-counts` endpoint; notification-service scheduled Telegram digest of reason counts; CI grep gate — Phase 9 (2026-05-17)
- ✓ **DASHLIVE-01**: `PathToLiveTile.jsx` (banner + 6 PREFLIGHT chip rows + 5 carry-in rows + 24h window footer) rendered above `KeyMetricsStrip` in `Dashboard.jsx`, banner tokens `bg-rose-700 / bg-amber-600 / bg-emerald-700` per D-10-13 — Phase 10 (2026-05-17)
- ✓ **DASHLIVE-02**: api-gateway `GET /api/preflight/carry-ins` (schema_version=1) backed by atomic file-state machine at `.planning/state/carry_ins.json` (parent-dir bind-mount per D-10-05 + WSL gotcha); server-side `overall` computation per D-10-04; `_state.first_all_pass_at` reset rule per D-10-07 — Phase 10 (2026-05-17)
- ✓ **DASHLIVE-03**: Two react-query hooks (`useLiveReadiness`, `useCarryIns`) verbatim from `useSafetyState` idiom (5s poll, retry=2, retryDelay=1000); D-10-16 authority rule (`useCarryIns` wins) documented inline — Phase 10 (2026-05-17)
- ✓ **DASHLIVE-04**: pytest-playwright Chromium smoke covering all 7 D-10-18 assertions; two defence-in-depth grep gates (`PathToLiveTile` + `carry-ins` literals, narrow scope per D-10-20); `.github/workflows/dashboard-smoke.yml` with PR paths filter listing all six D-10-19 paths + `workflow_dispatch` (no nightly cron — Phase 12 deferred) — Phase 10 (2026-05-17)

### Active

<!-- v1.1 candidates. To be ratified by `/gsd-new-milestone`. -->

v1.1 candidates ratified via `/gsd-new-milestone` on 2026-05-16. See `.planning/REQUIREMENTS.md` for the full REQ-ID list. Categories: LIVECLOSE (carry-ins), PREFLIGHT (preconditions), MLGATE (evidence loop), DASHLIVE (preflight tile), CIRESTORE (post-OP-04 CI).

### Out of Scope

<!-- Explicit boundaries. Reasoning kept to prevent re-adding. -->

- Real-money LIVE trading enabled by default — paper-mode is the safety boundary; LIVE requires four explicit flag flips (`PAPER_TRADING_MODE=false`, `TRADING_MODE=LIVE`, mainnet keys with trade permissions, `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY`); pre-LIVE checklist must restore per-trade cap to ≤2% (currently 10% in paper per ADR-010).
  - When flipping LIVE is in scope, the 6-precondition Diagnose/Action/Verification path lives in [RUNBOOK.md "Pre-LIVE Operator Checklist"](../RUNBOOK.md#pre-live-operator-checklist). Phase 8 enforces these in code; v1.1 does not flip LIVE.
- 30+ parallel LLM subagents for tournament — confirmed wrong primitive; Docker isolation is the right one.
- Auto-merge of tournament-winning PRs — confirmed unsafe; `gh pr merge` CI grep gate enforced.
- Live-exchange prices in every pytest run — deterministic suite uses recorded tape; one nightly live smoke allowed flaky.
- Unattended "iterate till green" loops — confirmed Goodhart trap; anti-mock guard enforces.
- `ENABLE_ML_PREDICTIONS=true` by default — blocked behind DSR > 0.95 evidence on returns.
- Re-introducing client-side WebSocket scaffolding before server `/ws/metrics` route exists.
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
- **LOC:** v1.0 added +159,471 / -2,816 across 764 files (427 commits in 9 days). Services + frontend + tests + scripts total ~58k LOC.
- **Operator profile:** Solo founder, paper-trading on Bybit mainnet prices, WSL2 + Docker Desktop host (BuildKit hangs documented in RUNBOOK).
- **Trust posture:** "Trust no docs" — every safety claim verified against code (`file:line`) before relying on it. v1.0 audit confirmed 19/23 REQs satisfied with file:line evidence.
- **V0 finding (load-bearing):** Pre-2026-04-30 ML evaluation numbers (R²=0.99, Dir.Acc 79–84%) were a metric bug (look-ahead leakage). Post-fix, GRU is chance-level on returns. Persistence baseline beats it. ML predictions remain off by default until a returns-target model passes the DSR gate. v1.0 tournament harness is the path to evidence.
- **Audit baseline:** 17-agent deep audit on 2026-04-28; Tier-1 implementation 2026-04-30; v1.0 9-phase milestone shipped 2026-05-15. Audit at `.planning/milestones/v1.0-MILESTONE-AUDIT.md`.

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
| Paper-mode per-trade risk cap relaxed to 10% (ADR-010) | Bybit min-notional on $100 paper balance; pre-LIVE checklist must restore ≤2% | ⚠ Revisit before TRADING_MODE=LIVE |

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
*Last updated: 2026-05-17 — Phase 10 (Path-to-LIVE Dashboard) complete; DASHLIVE-01/02/03/04 validated*
