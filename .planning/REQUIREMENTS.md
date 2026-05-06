# Requirements: Crypto Trading Bot

**Defined:** 2026-05-06
**Core Value:** The bot must never lose money it wasn't authorized to risk; every "edge" claim must be backed by DSR/CPCV evidence on returns, not raw R² on price levels.

## v1 Requirements

Active requirements for this milestone. Each maps to roadmap phases. Validated requirements (existing shipped capability) are tracked in PROJECT.md and not re-listed here.

### Infra (test-driven rebuild)

- [ ] **INFRA-01**: pytest+testcontainers integration suite asserts full stack health from a fresh `git clone` into a tmp directory: services healthy, real exchange prices via recorded tape, ML models loaded if `ENABLE_ML_PREDICTIONS=true`, notifications delivered, paper trade end-to-end <60s
- [ ] **INFRA-02**: `bootstrap.sh` provisions `.env` from a template, brings up the docker-compose stack, runs DB migrations, and idles waiting for the integration suite — no destructive `git clean -fdx` against the working tree
- [ ] **INFRA-03**: Recorded-tape exchange data fixtures + replay loader for deterministic test runs; one nightly live smoke test allowed to be flaky
- [ ] **INFRA-04**: Checkpointed iteration harness — fix one bug, run tests, present diff for review before next fix; no unattended "iterate until 3 green runs" loop
- [ ] **INFRA-05**: RUNBOOK.md documents the WSL2 BuildKit hang (`DOCKER_BUILDKIT=0` workaround), docker context misconfig recovery, stale-model restart procedure, and bootstrap-test failure triage
- [ ] **INFRA-06**: Pre-existing concrete bugs investigated and either fixed or documented as out-of-scope: stale in-memory ML model needing service restart, hardcoded `confidence=0` paths still emitting signals, WSL2 BuildKit env workaround

### Tournament (ML evaluation harness)

- [ ] **TOURN-01**: Docker+SQLite tournament orchestrator (Python or Bash, NOT LLM subagents) launches per-experiment containers with isolated memory and disk, captures train/eval logs, persists results to a shared SQLite leaderboard
- [ ] **TOURN-02**: Tournament leaderboard schema indexed by (architecture, symbol, horizon, target_mode, hyperparameters_hash, run_id) with columns for `r2_returns`, `dir_acc_corrected`, `oos_sharpe`, `psr`, `dsr`, `cpcv_dsr`, `train_seconds`, `git_sha`
- [ ] **TOURN-03**: Search-space config covering GRU/LSTM/Transformer/TCN × {SOL, BNB, ADA} × hyperparameter grid (units, depth, dropout, lr, batch, lookback, horizon, target_mode); deterministic seeds; explicit XRP/AVAX opt-in only when validation layer permits
- [ ] **TOURN-04**: Per-experiment early stopping based on validation `r2_returns` and `dir_acc_corrected`; persist failed runs to leaderboard with failure reason instead of dropping them
- [ ] **TOURN-05**: Top-3 ensemble construction (rank by DSR on OOS) with bootstrap significance test vs current production baseline (`ENABLE_ML_PREDICTIONS=false` baseline = persistence) on OOS Sharpe and corrected Dir.Acc, p<0.05 — drops the impossible "5% R²" criterion
- [ ] **TOURN-06**: Auto-open draft PR via `gh` CLI containing leaderboard markdown, ensemble config, significance test results, and a link to reproducer when ensemble wins; humans merge — no auto-merge
- [ ] **TOURN-07**: Tournament reuses existing `returns_metrics.py`, `sharpe_metrics.py`, `cpcv.py`; no parallel "alternative metrics" code path

### ML cleanup (post-V0)

- [ ] **MLCL-01**: Forward-paper-test harness for the three Tier-1 opt-in features (vol parity, maker, funding) — runs each in isolation for ≥7 days against the baseline, compares PSR with bootstrap CI; per-feature default-on flip blocked until evidence
- [ ] **MLCL-02**: T0.1.x next-attempt experiment chosen and shipped through the tournament harness — picks one of {different horizon, classification head, XGBoost control, cross-sectional features, sentiment-as-filter}; result is allowed to be "no edge" and that's a valid outcome
- [ ] **MLCL-03**: `scripts/monitoring/*` parked autonomous tier-2 system either removed or wired with a documented blast-radius bound (no `claude -p` PR-opening from CI without human review); decision committed
- [ ] **MLCL-04**: Backtest signal logic alignment — either rewrite `run_extended_backtest.py` to use live `CoreAggregator` (high-effort) or document the divergence permanently and freeze backtest claims; no silent drift

### Dashboard

- [ ] **DASH-01**: End-to-end audit of every dashboard tile/route — for each, identify the backing endpoint, verify it returns the expected shape against a running stack, and either fix or label "stale"
- [ ] **DASH-02**: Hardcoded URLs replaced with config-driven values; gateway-mediated paths (auth, rate limit, validation) versus direct-service paths documented inline in `vite.config.js` and the relevant API client modules
- [ ] **DASH-03**: Safety-state header — prominent display of TRADING_MODE (PAPER/LIVE), `auto_trading_enabled`, kill-switch state, EMERGENCY_STOP file presence, and `ENABLE_ML_PREDICTIONS` so the operator sees current safety posture at a glance
- [ ] **DASH-04**: Tournament view — table of leaderboard rows from `TOURN-02`, filterable by symbol/architecture, with significance markers; depends on TOURN-02
- [ ] **DASH-05**: Empty/error states — every tile renders an explicit "no data" or "endpoint failed" message instead of silently showing empty arrays or stale numbers
- [ ] **DASH-06**: Smoke test for the dashboard — Playwright or equivalent that boots the stack, opens the dashboard, asserts each major tile renders non-empty against the recorded-tape stack from `INFRA-03`

## v2 Requirements

Deferred to a future milestone. Tracked but not in current roadmap.

### Tournament

- **TOURN-V2-01**: Cross-symbol tournament including XRP/AVAX after validation-layer review
- **TOURN-V2-02**: Multi-horizon search (1h, 4h, 24h) with per-horizon production deployment

### ML

- **MLCL-V2-01**: Sentiment-as-filter integration if T0.1.x lands evidence
- **MLCL-V2-02**: Classification head + calibration (probability of move > threshold) instead of regression

### Dashboard

- **DASH-V2-01**: Server-side `/ws/metrics` route + deliberate client subscription layer (rebuild WebSocket only after server endpoint exists)
- **DASH-V2-02**: Mobile-friendly responsive layout

### Infra

- **INFRA-V2-01**: K8s deployment (current is docker-compose only)
- **INFRA-V2-02**: Multi-host deployment / HA postgres

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Real-money LIVE trading by default | Paper-mode is the safety boundary; LIVE requires three explicit flag flips and is not part of this milestone |
| 30+ parallel LLM subagents for tournament | Agent tool spawns share parent shell; no per-experiment isolation; Docker is the right primitive |
| Auto-merge of tournament-winning PRs | Auto-merge against trading code is unsafe even with significance gates; humans merge |
| Live-exchange prices in every pytest run | Flaky, rate-limited, costs money, account-risk flags; deterministic suite uses recorded tape |
| Unattended "iterate until 3 green runs" loop | Goodhart trap — cheapest path is to weaken assertions or comment tests; checkpointed iteration only |
| `git clean -fdx` in the working tree | Would delete `.env` with real API keys + local model weights / SQLite leaderboards not in git |
| Re-introducing client-side WebSocket scaffolding before `/ws/metrics` exists | Server route doesn't exist yet; restoring scaffolding targets a non-endpoint |
| ENABLE_ML_PREDICTIONS=true by default | Blocked behind DSR > 0.95 evidence on returns (V0 finding) |
| XRP / AVAX in production allocations during this milestone | Validation layer permits 40+ symbols, but production allocation review is a separate milestone |
| Mobile-native app | Web dashboard is sufficient for solo operator |
| Rewrite of any of the 15 services | Stack is locked for this milestone; only fixes + new harness modules |

## Traceability

Each requirement maps to exactly one phase.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-02 | Phase 1 | Pending |
| INFRA-03 | Phase 1 | Pending |
| INFRA-01 | Phase 2 | Pending |
| INFRA-04 | Phase 2 | Pending |
| INFRA-05 | Phase 2 | Pending |
| INFRA-06 | Phase 2 | Pending |
| TOURN-01 | Phase 3 | Pending |
| TOURN-02 | Phase 3 | Pending |
| TOURN-03 | Phase 3 | Pending |
| TOURN-04 | Phase 3 | Pending |
| TOURN-07 | Phase 3 | Pending |
| TOURN-05 | Phase 4 | Pending |
| TOURN-06 | Phase 4 | Pending |
| MLCL-01 | Phase 5 | Pending |
| MLCL-02 | Phase 5 | Pending |
| MLCL-03 | Phase 5 | Pending |
| MLCL-04 | Phase 5 | Pending |
| DASH-01 | Phase 6 | Pending |
| DASH-02 | Phase 6 | Pending |
| DASH-03 | Phase 6 | Pending |
| DASH-05 | Phase 6 | Pending |
| DASH-04 | Phase 7 | Pending |
| DASH-06 | Phase 7 | Pending |

**Coverage:**
- v1 requirements: 23 total
- Mapped to phases: 23 ✓
- Unmapped: 0

---
*Requirements defined: 2026-05-06*
*Last updated: 2026-05-06 after initialization*
