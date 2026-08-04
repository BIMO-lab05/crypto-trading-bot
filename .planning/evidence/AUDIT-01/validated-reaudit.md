# AUDIT-01 Validated-Set Re-Audit — Results

**Audited:** 2026-05-23
**Phase:** 16-validated-set-re-audit
**Schema:** `.planning/evidence/AUDIT-01/_schema.json`
**Canonical artifact:** `.planning/evidence/AUDIT-01/validated-reaudit.json`
**Status:** final (zero pending rows; 8/8 completeness assertions GREEN)

## Summary

- **81 REQs audited** (every row from PROJECT.md ### Validated for pre-v1 / v1.0 / v1.1 / v1.2 plus five synthetic `CLAUDE-*` IDs per CONTEXT D-04)
- **74 satisfied** (91.4%)
- **7 drift** (8.6%)
- **0 missing**
- **0 pending** after merge

## Per-era breakdown

| Era    | satisfied | drift | missing | total |
| ------ | --------: | ----: | ------: | ----: |
| pre-v1 |        22 |     4 |       0 |    26 |
| v1.0   |        20 |     3 |       0 |    23 |
| v1.1   |        19 |     0 |       0 |    19 |
| v1.2   |        13 |     0 |       0 |    13 |
| **total** | **74** | **7** | **0** |  **81** |

> v1.1 and v1.2 came back perfectly clean. All seven drift items are in pre-v1 / v1.0 era — the older claims, predictably, are where reality has wandered.

## Drift items → proposed downstream owner

| REQ-ID | Era | Verdict | Evidence | Proposed owner | Operator menu (Plan 07 decision) |
| --- | --- | --- | --- | --- | --- |
| EXEC-03 | pre-v1 | drift | `services/technical-analysis/app/handlers/analysis.py:67-110` | **Phase 21 TA-AGG-01** | Phase 21 (widen aggregator to all implemented indicators OR rewrite claim) |
| TOURN-07 | v1.0 | drift | `services/ml-retraining-service/app/core/model_trainer.py:430-623` | **Phase 23 ML-PURGE-05** (+ ML-PURGE-01) | Phase 23 (remove `r2_score`-on-prices from `model_trainer.py` + extend grep gate to `services/**`) |
| CLAUDE-LSTM-ARCHIVED | pre-v1 | drift | `services/ml-prediction-service/app/models/ensemble_model.py:15` + `services/ml-retraining-service/app/core/models/lstm.py` | **Phase 23 ML-PURGE-02** | Phase 23 (move/delete live `lstm.py` + remove `LSTM` import from `ensemble_model.py`) |
| CLAUDE-SENTIMENT-REMOVED | pre-v1 | drift | `services/trading-engine/app/auto_trader.py:1130, 1261` | **Phase 24 HYG-01** | Phase 24 (fix stale "Sentiment 15%" comments AND verify sentiment weight = 0 in `use_phase3=True` aggregator path) |
| CLAUDE-VALIDATED-SYMBOLS | pre-v1 | drift | `services/market-data-service/app/config.py:73-86` | **propose:demote-out-of-scope** (NEW finding) | `propose:new-phase` (carve a Phase 24-bis to reconcile market-data 14-symbol default with CLAUDE 5-symbol rule) **OR** `propose:demote-out-of-scope` (relax CLAUDE rule to permit broader ingest; keep trading-engine 5-symbol cap) |
| DASH-01 | v1.0 | drift | `scripts/audit_tiles.py:43-50` | **propose:demote-out-of-scope** (NEW finding) | `propose:quick-fix` (restore `06-TILE-AUDIT.json` under `.planning/milestones/v1.0-phases/06-*/` + update script path) **OR** `propose:demote-active` (move DASH-01 out of Validated; mark dashboard tile audit as v1.0-frozen artifact) |
| DASH-06 | v1.0 | drift | `tests/integration/test_dashboard_smoke.py:83-127` | **propose:demote-out-of-scope** (NEW finding) | `propose:quick-fix` (same fix as DASH-01 — restore inventory file) **OR** `propose:demote-active` (skip/quarantine `test_dashboard_smoke.py` until inventory restored) |

> **NEW findings** = drift items that were not in CONTEXT D-12's known-findings table. Each has a placeholder `propose:demote-out-of-scope` token in the canonical JSON `notes` (required by the schema-gate regex), but the operator menu above is the full set of options Plan 07's `checkpoint:decision` must resolve.

## Coverage check

| Phase | Drift items routed here | Sized? |
| --- | --- | --- |
| Phase 17 (TE-CAP) | _none_ (Track A came back 17/17 satisfied — see implications below) | n/a |
| Phase 18 (BC-FIX) | _none_ | n/a |
| Phase 19 (RECON) | _none_ | n/a |
| Phase 20 (PAPER) | _none_ | n/a |
| Phase 21 (TA-AGG) | EXEC-03 | ✓ TA-AGG-01 covers |
| Phase 22 (PRICE) | _none_ | n/a |
| Phase 23 (ML-PURGE) | TOURN-07, CLAUDE-LSTM-ARCHIVED | ✓ ML-PURGE-01/02/05 cover |
| Phase 24 (HYG) | CLAUDE-SENTIMENT-REMOVED | ✓ HYG-01 covers |
| Unrouted — operator decision | CLAUDE-VALIDATED-SYMBOLS, DASH-01, DASH-06 | ⚠ NEW findings — require Plan 07 decision |

## Satisfied items — file:line summary

Grouped by era. All file:line citations are verified per CONTEXT D-07.

### pre-v1 (22 satisfied)

- **EXEC-01** — `docker-compose.unified.yml:33-928` (15-container stack)
- **EXEC-02** — `services/bybit-connector/app/config.py:32-35` (mainnet price feed; paper default)
- **RISK-01** — `services/trading-engine/app/auto_trader.py:340-344` (5% daily-loss circuit-breaker)
- **RISK-02** — `services/trading-engine/app/auto_trader.py:332-344` (per-trade cap honored)
- **RISK-03** — `services/trading-engine/app/auto_trader.py:332-344` (paper-cap relax per ADR-010)
- **RISK-04** — `services/trading-engine/app/auto_trader.py:1962-1986` (LIVE_TRADING_ACK gate)
- **RISK-05** — `services/trading-engine/app/auto_trader.py:354-370` (vol-parity check)
- **RISK-06** — `services/trading-engine/app/live_trading.py:290-360` (emergency-stop file gate)
- **RISK-07** — `services/trading-engine/app/auto_trader.py:1796-1810` (48h max-hold)
- **ML-01** — `services/ml-retraining-service/app/core/returns_metrics.py:25-50` (returns_metrics module)
- **ML-02** — `services/ml-retraining-service/app/sharpe_metrics.py:1-80` (PSR/DSR helpers)
- **ML-03** — `services/ml-retraining-service/app/cpcv.py:1-60` (CPCV evaluator)
- **ML-04** — `services/ml-prediction-service/app/ml_models/gru_predictor.py:152-180` (GRU inference path)
- **ML-05** — `services/trading-engine/app/config.py:90-93` (ENABLE_ML_PREDICTIONS=false default)
- **DATA-01** — `services/market-data-service/app/database.py:169-174` (TimescaleDB candle write)
- **DATA-02** — `backtesting/run_walk_forward_ensemble.py:563-571` (is_mainnet filter)
- **OBS-01** — `services/notification-service/app/utils/structured_logging.py:21-47` (structured JSON logs)
- **OBS-02** — `services/sentiment-analysis-service/app/main.py:645-782` (Prometheus metrics surface)
- **UI-01** — `frontend/src/hooks/useGatewayWebSocket.js:11-38` (gateway WS subscription)
- **TEST-01** — `tests:0` (337 tests counted; original "~101" was 2026-04 snapshot — satisfied per spirit-of-claim rule)
- **CLAUDE-PAPER-CAP-ADR010** — `services/trading-engine/app/config.py:321-332` (paper 10% per-trade cap, LIVE preserves 2%)
- **CLAUDE-EXEC-MAINNET-PRICES** — `docker-compose.unified.yml:288-399` (BYBIT_TESTNET=false on relevant services)

### v1.0 (20 satisfied)

- **INFRA-01** — `tests/integration/test_fresh_clone_round_trip.py:1-156` (fresh-clone round-trip <60s harness)
- **INFRA-02** — `bootstrap.sh:1-136`
- **INFRA-03** — `services/bybit-connector/app/tape_replay_client.py:1-100`
- **INFRA-04** — `scripts/iter-fix.sh:1-30`
- **INFRA-05** — `RUNBOOK.md:23-254`
- **INFRA-06** — `RUNBOOK.md:403-411`
- **TOURN-01** — `services/tournament-harness/app/orchestrator/launcher.py:92-120`
- **TOURN-02** — `services/tournament-harness/migrations/0001_initial.sql:9-43`
- **TOURN-03** — `services/tournament-harness/app/config/tournament_loader.py:25-50`
- **TOURN-04** — `services/tournament-harness/app/orchestrator/failure.py:1-31`
- **TOURN-05** — `services/tournament-harness/app/significance/ensemble.py:43-73`
- **TOURN-06** — `services/tournament-harness/app/pr/gh.py:61-92`
- **MLCL-01** — `scripts/forward_paper_test/run_isolation.py:1-40`
- **MLCL-02** — `services/tournament-harness/app/config/t0_1_x_experiment.yaml:1-10`
- **MLCL-03** — `docs/decisions/ADR-011-monitoring-disposition.md:1-90`
- **MLCL-04** — `services/trading-engine/run_extended_backtest.py:16-80`
- **DASH-02** — `frontend/vite.config.js:38-59`
- **DASH-03** — `services/api-gateway/app/main.py:1049-1180`
- **DASH-04** — `frontend/src/pages/TournamentDashboard.jsx:17-118`
- **DASH-05** — `frontend/src/components/TileState.jsx:4-82`

### v1.1 (19 satisfied — clean era)

- **LIVECLOSE-01..05** — `scripts/closure/liveclose-{01..05}*` (live-flip closure suite)
- **PREFLIGHT-01..04** — `services/trading-engine/app/preflight/checks.py`, `services/trading-engine/app/main.py`, `.github/workflows/preflight-live-readiness.yml`, `RUNBOOK.md:255`
- **MLGATE-01..03** — `scripts/forward_paper_test/run_evidence_loop.py`, `services/trading-engine/app/lifespan/ml.py`, `services/trading-engine/app/aggregation/ml_gate_reasons.py`
- **DASHLIVE-01..04** — `frontend/src/components/PathToLiveTile.jsx`, `services/api-gateway/app/routes/preflight_carry_ins.py`, `frontend/src/hooks/useLiveReadiness.js`, `tests/e2e/test_path_to_live_smoke.py`
- **CIRESTORE-01..03** — `.planning/evidence/OP-04/README.md`, `.planning/evidence/CIRESTORE-02/README.md`, `.github/workflows/billing-failure-detector.yml`

### v1.2 (13 satisfied — clean era)

- **BC-01..07** — bybit-connector centralization audit (`BC-01/bybit-bypass-audit.json`, orderbook handler refactor, CI grep gate, `_archive_exchanges/binance.py` retention, default-symbols config, RUNBOOK ops sections, tape-replay preservation test)
- **MOBILE-01..03** — `frontend/tailwind.config.js`, `frontend/src/components/Dashboard.jsx`, `tests/e2e/test_responsive_dashboard.py`
- **TOOL-01..03** — placeholder/no-supersession/audit-freshness CI gates under `tests/ci/`

## Methodology

- **Sources read:** `PROJECT.md`, `.planning/milestones/v1.{0,1,2}-REQUIREMENTS.md`, `CLAUDE.md`
- **Verdict rules:** CONTEXT D-07 (satisfied requires file:line), D-08 (drift requires notes), D-09 (missing requires absence evidence), D-10 (operator-blocked harnesses are satisfied with notes)
- **Tools:** `serena` MCP (`find_symbol`, `find_referencing_symbols`, `search_for_pattern`); raw `grep` for absence proofs
- **Track allocation (per CONTEXT D-06):** Track A = trading-engine risk caps (17 REQs), Track B = ML purity + aggregator (19 REQs), Track C1 = pre-v1/v1.0 remainder (24 REQs), Track C2 = v1.1/v1.2 remainder (21 REQs)
- **Merge gate:** `tests/test_merge_completeness.py` (8 assertions, all GREEN — see commit hash for `_merge_deltas.py` invocation)
- **Audit trail preserved:** `track-{A,B,C1,C2}-deltas.json` retained on disk per CONTEXT D-03 (not deleted post-merge)

## Implications for v1.3 scope

**Track A (trading-engine risk caps) came back 17/17 satisfied.** RISK-01..07, CLAUDE-PAPER-CAP-ADR010, plus the operator-relevant flag enforcement at `auto_trader.py:1962-1986` (LIVE_TRADING_ACK). Phase 17's planned TE-CAP-01/03/04 subtasks (per `.planning/REQUIREMENTS.md`) should likely **demote** — the underlying caps already enforce in code. Only two Phase 17 leftovers remain plausible:

- **TE-CAP-02** — `POST /api/portfolio/emergency-stop` admin-guard verification (RISK-06 evidence at `live_trading.py:290-360` covers the file-gate path; the HTTP authorization check is a smaller surgical follow-up)
- **TE-CAP-05** — `bare-except` cleanup in trading-engine (audit found no drift but Phase 17 originally scoped this independent of the audit)

**Tracks B/C1 surfaced the 7 real items** that Phase 17-24 must handle. Phase 21 (TA-AGG), Phase 23 (ML-PURGE), Phase 24 (HYG) all have direct mappings. The three NEW findings (CLAUDE-VALIDATED-SYMBOLS, DASH-01, DASH-06) require Plan 07's operator checkpoint to decide between fix vs. demote — they aren't load-bearing for the trading-engine correctness goal of v1.3, so demotion is the natural default.

## Notes for Plan 07

- **7 drift / 0 missing items** propose downstream owners; 4 routed to Phase 21/23/24, 3 are NEW findings flagged for operator decision
- **CLAUDE.md text needs correction for:** `CLAUDE-LSTM-ARCHIVED` (LSTM still imported), `CLAUDE-SENTIMENT-REMOVED` (stale comments in `auto_trader.py:1130, 1261`), `CLAUDE-VALIDATED-SYMBOLS` (5 vs 14 default symbols)
- **PROJECT.md ### Validated rewrite spec:** Demote EXEC-03, TOURN-07, the three CLAUDE-* drift rows, DASH-01, DASH-06 from Validated → Active (Phase 21/23/24 carry) or → Out of Scope (operator choice for the 3 NEW findings)
- **Unrouted items requiring operator decision (3):** CLAUDE-VALIDATED-SYMBOLS, DASH-01, DASH-06
- **Phase 17 (TE-CAP) sizing recommendation:** demote TE-CAP-01/03/04 (already-satisfied caps); retain TE-CAP-02 (emergency-stop HTTP auth) + TE-CAP-05 (bare-except cleanup) if still in v1.3 scope
