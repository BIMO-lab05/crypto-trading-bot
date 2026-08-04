# Codebase Concerns

**Analysis Date:** 2026-05-22

---

## Open Operator Carry-Ins (from `.planning/state/carry_ins.json`)

All 5 carry-ins remain `open`; `_state.last_overall = "DO_NOT_FLIP"` (live trading blocked).

| ID | Required Action | Blocks |
|----|----------------|--------|
| OP-01 | LIVE-flip manual smoke (api-gateway `TRADING_MODE=LIVE`, rose-outline confirm, revert) | LIVECLOSE-05 |
| OP-02 | Apply `infrastructure/migrations/005_tournament_reader.sql` to `market_data` on timescaledb | LIVECLOSE-04 |
| OP-03 | Set `TOURNAMENT_READER_PASSWORD` env var + force-recreate `tournament-harness` container | LIVECLOSE-04 |
| OP-04 | Resolve GitHub Actions billing suspension | LIVECLOSE-02, CIRESTORE-01, CIRESTORE-02 |
| INFRA-02 | Run `scripts/closure/liveclose-01-fresh-clone.sh` × 2 from a clean tmp directory | LIVECLOSE-01 |
| LIVECLOSE-03 | Run `scripts/forward_paper_test/run_evidence_loop.py` for ≥7 trading days | LIVECLOSE-03 PSR accrual |

Also deferred: Phase 08 VERIFICATION.md has 2 manual-only smokes marked `human_needed` (container-restart cap-rejection proof + live HTTP curl through api-gateway after rebuild). Evidence goes in `.planning/evidence/`.

---

## Security Concerns

**JWT Secret: DEFAULT INSECURE IN DEV — HIGH**
- `services/api-gateway/app/config.py:59` has `default="your-secret-key-change-in-production"` for `SECRET_KEY`.
- `services/api-gateway/app/auth_models.py:49` defines `_DEV_ONLY_SECRET = "development-only-secret-not-for-production-use"`, used as fallback when `JWT_SECRET_KEY` env var is absent (line 67, 116).
- Production startup logs `SECURITY WARNING` when falling back; does not hard-fail. Any deployment where `JWT_SECRET_KEY` is not set in `.env` silently uses the known fallback secret — all tokens are forgeable.
- Fix: enforce startup failure (not warning) in all environments where `PAPER_TRADING_MODE=false` or `TRADING_MODE=LIVE`.
- Tracking: untracked debt.

**Risk-Metrics Endpoints Unauthenticated — HIGH**
- `services/risk-metrics-service/tests/test_main_coverage.py:139` has a `@pytest.mark.skip(reason="Auth not enforced on these read endpoints; needs API design decision")` test class covering `/api/v1/portfolio/{id}/risk-scorecard`.
- The skip indicates a deliberate deferral of auth enforcement with no follow-up filed.
- Impact: risk scorecard is readable without credentials; if the service is exposed on the internal network, it leaks portfolio state.
- Fix: apply `Depends(verify_api_key)` or gateway-level auth. File an ADR or phase before re-enabling the test.
- Tracking: untracked debt.

**Migration 005 Placeholder Password — MEDIUM**
- `infrastructure/migrations/005_tournament_reader.sql:19` creates the `tournament_reader` role with password `'CHANGE_ME_VIA_ENV'` if the role doesn't already exist, then emits a NOTICE.
- Operator must run `ALTER ROLE tournament_reader PASSWORD '<TOURNAMENT_READER_PASSWORD>'` after applying the migration (OP-03 carry-in).
- If OP-03 is not completed before the tournament-harness is granted DB access, the read-only role runs with a known placeholder credential.
- Tracking: OP-03 carry-in (open).

**API Key Auth Not Enforced Internally — MEDIUM**
- `services/market-data-service/app/auth.py:14` uses `APIKeyHeader(auto_error=False)` and validates against `settings.api_keys_list`.
- Inter-service calls from trading-engine and technical-analysis do not send this header in current HTTP client wrappers; enforcement depends on `auto_error=False` (silently passes without key).
- Actual enforcement is gateway-level, not service-level.
- Tracking: accepted design (ADR-016 describes HTTP mesh without per-service auth layer), but not documented as a conscious choice in any ADR.

**Auto-Trader Armed in `.env` — MEDIUM**
- `.env` sets `AUTO_TRADING_ENABLED=true` overriding compose default of `false`.
- Trading loop fires immediately on next tick if `safety/EMERGENCY_STOP` file is absent.
- Kill-switch is a bind-mounted directory (`./safety/`) per a 2026-05-19 compose patch; previous file-to-file bind broke on missing host file.
- Risk: accidental removal of `safety/EMERGENCY_STOP` while stack is live resumes automated trading with no warning.
- Tracking: accepted operator state; not an ADR.

---

## Tech Debt

### ML / Prediction

**GRU Models 5+ Months Stale — HIGH (accepted, gated off)**
- 16 GRU `.keras` models in `services/ml-prediction-service/models/` trained December 10, 2025 per `compare_lstm_gru.py:7` and commit history. File mtimes show May 3, 2026 due to a deploy-session touch — this does not reflect retraining.
- As of 2026-05-22: ~163 days old. Market regime since December has included several structural shifts; model feature distributions are likely out-of-distribution.
- Gated off globally: `ENABLE_ML_PREDICTIONS=false` in compose defaults. `services/trading-engine/app/aggregation/ml_gate_reasons.py` records all gate events.
- Acceptance gate per CLAUDE.md: DSR > 0.95 on log-returns via `scripts/sharpe_metrics.py` + CPCV via `scripts/cpcv.py`. No qualifying row exists in `leaderboard` table yet.
- Fix: retrain after rebuilding target on log-returns (not price levels). Note BTC training OOM-kills at default container memory limits (see Operational Gotchas). 
- Tracking: accepted (CLAUDE.md, STATE.md). LIVECLOSE-03 wall-clock accrual blocks flip.

**ML V0 Look-Ahead Leakage — HIGH (accepted, gated off)**
- Original GRU directional-accuracy metric had look-ahead leakage. Commit `c56765c` fixed the evaluation harness. Post-fix models score at chance level on log-returns; they lose to naive persistence.
- Affected files: `services/ml-prediction-service/app/` inference pipeline, `services/ml-retraining-service/app/` training pipeline.
- Gated off with same mechanism as staleness above.
- Tracking: accepted (CLAUDE.md). Both fixes gate together on LIVECLOSE-03 evidence.

**Confidence Metric Was Structurally Bounded (Fixed 2026-05-21) — MEDIUM**
- `services/trading-engine/app/aggregation/voter.py` previously used `|weighted_score|` for confidence, which capped at ~0.5 on unanimous 8-indicator agreement — making the 0.30 `min_confidence` floor unreachable.
- Fixed in commit `b01fa4f` (2026-05-21): new `compute_agreement_confidence()` method at `voter.py:298`; `aggregator_core.py:238` overrides legacy confidence for non-HOLD actions.
- **Residual concern:** cascade penalty interaction not yet characterized. Volume validator `INSUFFICIENT` → 0.95×; regime RANGING → 0.80×; multi-tf WEAK → 0.90×; combined ~0.684×. Post-fix live evidence showed peak agreement ~0.26 — below the 0.30 floor in STRONG_TREND. Threshold may need walk-forward-gated tuning.
- Related: `min_signal_confidence` in `services/trading-engine/app/config.py:391` was also misaligned (`0.40` vs aggregator floor `0.30`); fixed same commit.
- Production aggregator backtest harness exists: `backtesting/run_walk_forward_ensemble.py` (imports `CoreAggregator`).
- Tracking: fix committed; cascade-tuning untracked.

**Multi-TF Blender Threshold Mismatch — MEDIUM (unresolved ADR)**
- `services/trading-engine/app/aggregation/multi_timeframe.py:206`: blender threshold `0.2` (lowered from `0.3`, comment says "RELAXED"). But per-TF confidence scores typically land 0.20–0.25, so 2-of-3 TF agreement with average conf 0.21 yields `weighted_score ≈ 0.185` → HOLD.
- ADR-014 (`wiki/decisions/ADR-014-multi-tf-blender-threshold-mismatch.md`) status: `proposed`, not accepted. No walk-forward proof filed.
- Changing without DSR gate violates trading-strategy-dev skill contract.
- Tracking: ADR-014 proposed but open.

**Backtest Profit-Factor Fold Pooling — MEDIUM**
- Memory note (`feedback_pf_metric_pooling.md`): naive mean-of-fold PFs biases the metric upward when any fold has zero losses (PF=0 denominator → PF appears perfect). Correct approach: pool `sum(wins)/sum(losses)` across folds.
- `services/risk-metrics-service/app/backtesting.py:459` computes `total_wins / total_losses` (pooled, correct for single-run). CPCV harness in `backtesting/run_walk_forward_ensemble.py` needs audit for fold-aggregation path.
- Impact: PF gate at tournament-harness level could pass models with fold-skewed PF if fold aggregation averages rather than pools.
- Tracking: untracked; memory note only.

### Test Coverage

**69 Test Files Module-Skipped After PR #86 — HIGH**
- `pytestmark = pytest.mark.skip(reason="stale tests after PR #86 refactor; needs rewrite")` applied module-wide in:
  - `services/market-data-service/tests/` — 8 files (test_main.py, test_auth.py, test_config.py, test_database.py, test_fetcher.py, test_fetcher_enhanced.py, test_main_enhanced.py, integration/test_query_handlers.py, unit/test_logging_config.py, unit/test_metrics.py, integration/test_health_handlers.py)
  - `services/portfolio-manager/tests/` — 10 files
  - `services/risk-metrics-service/tests/` — 6 files (test_api.py, test_additional_coverage.py, test_backtesting.py, test_backtest_models.py, test_cache.py, test_coverage_push_80.py, test_coverage_improvements.py, test_main_coverage.py)
  - `services/ml-prediction-service/tests/test_gru_comprehensive.py` — 1 file (full module skip)
  - `services/sentiment-analysis-service/tests/test_sentiment_analyzer.py` — 1 file
  - `services/portfolio-manager/tests/` — additional files
  - Count: 69 skip annotations found via grep.
- These tests were made stale by the PR #86 refactor. They previously covered paper-trade integrity (portfolio-manager), candle ingest (market-data), and risk metrics — all paths that interact with production DB.
- Fix: rewrite against the refactored interfaces. Until then, correctness regressions in these paths go undetected.
- Tracking: untracked; noted in individual file comments only.

**api-gateway: 9 Test Failures (Known, Container-Only) — MEDIUM**
- 9 failing tests in `services/api-gateway/tests/` as of 2026-05-03 session:
  - 4 `test_app_lifecycle.py` / `test_enhanced_signals.py` — assert sentiment counts removed in PR #86 (commit `c171bb0`).
  - 2 `test_config.py` — assert `DEBUG` log level and `localhost:8001` defaults that have since changed.
  - 1 indicator endpoint test — now gets 400 (validation) not 200.
  - 2 websocket tests — AsyncMock plumbing issues.
- Must run inside container (`docker exec crypto-bot-api-gateway pytest`) — host pip has fastapi 0.136 (HTTPBearer → 401), container pins fastapi 0.109 (→ 403). Tests assert 403.
- Tracking: partially tracked in CLAUDE.md and memory file; untracked for individual failures.

**bybit-connector: 2 CORS Tests Skipped — LOW**
- `services/bybit-connector/tests/test_config.py:566-571` — 2 tests `@pytest.mark.skip(reason="CORS configuration removed from Settings - handled in main.py middleware")`. No coverage of CORS behavior.
- Tracking: untracked.

### Signal Pipeline

**Indicator Enablement Persistence Not Implemented — MEDIUM**
- `services/trading-engine/app/handlers/orchestration.py:787`: `# TODO: indicator master switch lookup`
- Comments at line 754 and 788 explain: per-indicator enable/disable flags from the rolling-confidence gate are surfaced in the API response (`persisted: False`) but not stored anywhere — the flip must be done manually by the operator.
- Impact: the dynamic indicator gating feature (gatekeeper logic at `services/trading-engine/app/aggregation/gatekeeper.py`) has no persistence layer; restarts reset all indicator enable states.
- Tracking: untracked TODO.

**Smart Order Router Multi-Venue is Stub — LOW**
- `services/trading-engine/app/execution/smart_order_router.py:689`: `# TODO: Implement multi-venue routing`
- `ExecutionStrategy.SMART_SPLIT` and `VENUE_OPTIMAL` enum values exist (lines 95–96) but route to the stub. Only `bybit` is an enabled venue.
- Tracking: untracked TODO; acceptable for Bybit-only scope.

### Infrastructure

**RabbitMQ Environment Scaffolding — MEDIUM**
- ADR-016 (`wiki/decisions/ADR-016-http-not-events.md`) confirmed: 0 of 11 services use RabbitMQ for message passing. All compose env vars (`RABBITMQ_HOST`, `RABBITMQ_URL`, `RABBITMQ_USER`, `RABBITMQ_PASSWORD`) and pydantic `Settings` blocks are dead scaffolding.
- Only live touchpoint: `services/trading-engine/app/core/health.py:421` imports `aio_pika` optionally for a health probe.
- Risk: if RabbitMQ is unavailable, the health probe degrades gracefully but env vars suggest features that don't exist.
- Fix: strip RABBITMQ_* from compose env for all services; remove Settings blocks; retain the health probe only.
- Tracking: ADR-016 accepted; cleanup not yet a phase.

**Two Compose Files — MEDIUM**
- `docker-compose.yml` — incomplete; missing postgres, timescaledb, redis, rabbitmq service definitions.
- `docker-compose.unified.yml` — canonical; 17 services including all infrastructure.
- Risk: `docker compose up` (no `-f` flag) uses `docker-compose.yml` and starts 11 Python services + frontend against DBs that don't exist in compose context. Services crash with connection errors. Symptom looks like config bugs.
- Fix: delete or clearly mark `docker-compose.yml` as deprecated / non-functional.
- Tracking: documented in CLAUDE.md; no phase filed for removal.

**migration 005 Not Applied — HIGH (OP-03 carry-in)**
- `infrastructure/migrations/005_tournament_reader.sql` creates the `tournament_reader` DB role needed by `tournament-harness` to read `klines` from timescaledb.
- Has not been applied to the running timescaledb instance (OP-02 carry-in open).
- `services/tournament-harness` cannot read historical candles without this role; LIVECLOSE-04 verdict is blocked.
- Fix: `psql -h localhost -U postgres -d market_data -f infrastructure/migrations/005_tournament_reader.sql`; then set `TOURNAMENT_READER_PASSWORD` and force-recreate the container (OP-03).
- Tracking: OP-02 and OP-03 carry-ins; migration SQL exists.

**GitHub Actions CI Suspended (OP-04) — HIGH**
- `OP-04`: GH Actions billing unresolved. All 18 workflows in `.github/workflows/` (`ci.yml`, `cd-dev.yml`, `cd-prod.yml`, `bybit-bypass-gate.yml`, `tournament-harness.yml`, `security-scan.yml`, etc.) are blocked from running.
- No automated CI evidence accrual for any LIVECLOSE check until resolved.
- Tracking: OP-04 carry-in; billing issue is external to codebase.

### Orphan / Dead Files

**`main_original.py` Orphan — MEDIUM**
- `services/market-data-service/app/main_original.py`: 868 lines, the pre-refactor monolith. Not imported by any module in the service. Not referenced in any compose or Dockerfile.
- Risk: confusing to developers navigating the service; could be accidentally edited instead of the live `main.py`. Contains its own `bybit_connector_calls_total` Prometheus counter definition that would collide if the file were imported.
- Fix: delete `main_original.py`.
- Tracking: untracked.

---

## Known Bugs

**`round(stop_loss, 2)` in Non-Ensemble Strategies — MEDIUM (latent)**
- `services/trading-engine/app/strategies/momentum_breakout_strategy.py:1059` and `support_resistance_strategy.py:643` and `trend_following_strategy.py:1142`: `return round(stop_loss, 2), round(take_profit, 2), partial_exits`
- The active ensemble (`MultiStrategyEnsemble`) uses SimpleRSI + CoreAggregator + MeanReversion — none of these three files. The rounding is latent unless these strategies are added to the ensemble.
- Context: the original bug (commit `487d1bd`) was `round(price, 2)` in the TA service handler for ADA (~$0.45), causing 30+ flip-flop losses. That specific path is fixed.
- Risk: if any of these strategies is re-enabled for ADA/BNB/SOL, sub-$1 stop losses will be truncated to $0.00 or $0.01.
- Files: `services/trading-engine/app/strategies/momentum_breakout_strategy.py:1059`, `services/trading-engine/app/strategies/support_resistance_strategy.py:643`, `services/trading-engine/app/strategies/trend_following_strategy.py:1142`.
- Tracking: untracked; original fix tracked in memory file `feedback_low_price_round_bug.md`.

**`squeeze_momentum_strategy.py` Still Uses `round(entry_price, 2)` — MEDIUM (latent)**
- `services/trading-engine/app/strategies/squeeze_momentum_strategy.py:203`: `'entry_price': round(entry_price, 2)` — same class of bug as above.
- Also in `services/technical-analysis/app/indicators/sqzmom_enhanced.py:124`: `"current_price": round(self.current_price, 4)` — 4dp is safe for all current validated symbols (BTC > $60k, ETH > $2k, ADA > $0.45 at 4dp = $0.0001 precision).
- Tracking: untracked.

**`OrderBookFeatureExtractor` Wrong Default URL — MEDIUM**
- `services/ml-prediction-service/app/pipeline/orderbook_extractor.py:134`: `bybit_connector_url: str = "http://localhost:8004"` — port 8004 is `technical-analysis`, not `bybit-connector` (8001).
- When running in-container, this must be overridden via env. There is no config field in `services/ml-prediction-service/app/config.py` for `orderbook_extractor_url` (the `technical_analysis_url` field at line 58 is unrelated).
- Impact: ml-prediction orderbook feature extraction fails silently at localhost:8004 unless the caller overrides the URL at instantiation.
- Tracking: untracked.

**`automated_trading_loop.py` Hardcoded Balance — LOW**
- `scripts/automated_trading_loop.py:336` and `scripts/automated_trading_loop_with_notifications.py:174, 527`: `initial_balance = 10000.0  # TODO: Get from config or portfolio`
- Scripts do not read actual paper-trading balance from portfolio-manager. P&L metrics in script output are relative to a fictional $10,000 baseline, not the actual ~$100 paper balance.
- Tracking: untracked TODOs in scripts.

**Frontend API Stubs — LOW**
- `frontend/src/services/api.js:76`: `getOrderbook` stub — endpoint `GET /market/orderbook/{symbol}` not implemented in market-data-service.
- `frontend/src/services/api.js:125`: `getMLSignal` stub — `GET /ml/predict/signal/{symbol}` exists in ml-prediction-service but is behind `--profile ml` compose flag (disabled by default).
- `frontend/src/services/api.js:192`: `getSignalComparison` stub — `GET /trading/signals/compare/{symbol}` not implemented in trading-engine.
- Tracking: untracked TODO comments.

---

## Performance Concerns

**`auto_trader.is_running` Plain Bool (No asyncio.Event) — MEDIUM**
- `services/trading-engine/app/auto_trader.py:236`: `self.is_running = False` — plain Python bool.
- The auto-trader loop checks `while self.is_running:` (line 876) and the start/stop handlers write it without lock (lines 800, 811).
- In asyncio single-threaded event loop this is technically safe (no preemption), but concurrent `asyncio.create_task` or route handlers modifying `is_running` during a tick could create TOCTOU between check and action.
- `self._opening_lock = asyncio.Lock()` (line 253) guards position-opening but not the running-state flag itself.
- Fix: use `asyncio.Event` for `is_running` semantics.
- Tracking: untracked.

**Global Mutable Singletons Throughout Trading-Engine — MEDIUM**
- Multiple modules expose `global _singleton; return _singleton or create` patterns:
  - `services/trading-engine/app/auto_trader.py:4182-4203` (`_auto_trader`)
  - `services/trading-engine/app/multi_symbol_trader.py:409-418` (`_multi_symbol_trader`)
  - `services/trading-engine/app/paper_trading.py:434` (`_paper_engine`)
  - `services/trading-engine/app/atr_stops.py:346-347` (`_atr_calculator`)
  - `services/trading-engine/app/live_trading.py:529-537` (`_live_engine`)
  - `services/trading-engine/app/config.py:703-711` (`_settings`)
  - `services/trading-engine/app/performance_tracker.py:559-568`
  - `services/trading-engine/app/position_manager.py:695`
  - `services/trading-engine/app/multi_timeframe.py:467-475`
- Reset functions (`reset_auto_trader()`, etc.) exist for testing but all share same process state. Test isolation requires explicit reset calls; missing a reset leaks state between tests.
- Tracking: architectural pattern throughout; untracked.

**Sync `requests.get` + `time.sleep` in Async Context — MEDIUM**
- `services/ml-prediction-service/download_op_sui_6months.py:87, 118`: `requests.get(...)` + `time.sleep(0.2)` — synchronous, blocks event loop if called from async task.
- `services/ml-prediction-service/download_suiusdt_12months.py:91, 102, 133, 141`: same pattern.
- `services/tournament-harness/app/orchestrator/launcher.py:138`: `time.sleep(10)` — sync sleep inside orchestrator.
- These are operator-run scripts, not hot paths. Risk is low unless invoked from an async FastAPI handler.
- Tracking: untracked.

**`api-gateway/app/main.py` is 2,557 Lines — MEDIUM**
- Single monolithic handler file. All route definitions, middleware, proxying logic, and auth flows in one module.
- Makes the test surface harder to isolate (9 known failures cross-cut the module).
- Tracking: untracked; refactor not yet a phase.

**`auto_trader.py` is 4,204 Lines — MEDIUM**
- Contains the full auto-trading state machine, position sizing, stop-loss management, signal processing, and RabbitMQ health checks in one file.
- `advanced_metrics.py` (2,877 lines) and `signal_aggregator.py` (1,328 lines) similar.
- Tracking: untracked technical debt.

---

## Stale Data Risks

**TimescaleDB Mixed Testnet/Mainnet Candle History — HIGH**
- The stack switched from Bybit testnet to mainnet on 2026-04-25 mid-day. `klines` and `tickers` tables in timescaledb contain testnet prices before this date and mainnet prices after.
- Testnet prices are synthetic and do not reflect real market levels. Any backtest or TA over candles spanning before 2026-04-25 is contaminated.
- Fix: filter `WHERE is_mainnet = true AND timestamp > '2026-04-25'` in all backtesting queries, or wipe `klines`/`tickers` tables before running historical analysis.
- `backtesting/run_walk_forward_ensemble.py` should enforce `is_mainnet=true` filter. Audit its query at `BybitKlinesReader` class.
- Tracking: documented in CLAUDE.md; no automated guard in backtest harness confirmed.

**GRU Scaler PKL Files Inconsistency — MEDIUM**
- Multiple scaler variants exist per symbol: `*_gru_scalers.pkl`, `*_scalers.pkl`, `*_15m_scalers.pkl`, `*_240m_scalers.pkl` (e.g. `BTCUSDT_15m_scalers.pkl`, `BTCUSDT_240m_scalers.pkl`, `BTCUSDT_5m_scalers.pkl` from older training runs).
- Primary GRU models use `*_60m_gru.keras` + `*_60m_gru_scalers.pkl`. Extra timeframe scalers from the deleted LSTM pipeline remain on disk.
- Risk: ml-prediction-service loading wrong scaler for a model produces silent feature-domain mismatch.
- Location: `services/ml-prediction-service/models/`.
- Tracking: untracked cleanup.

---

## Fragile Areas

**Emergency-Stop Kill-Switch Bind Mount — HIGH**
- Kill-switch is `safety/EMERGENCY_STOP` file on host, bind-mounted as a directory (`./safety/`) into containers at `/app/safety/` per 2026-05-19 compose patch.
- Previous file-to-file bind (`./EMERGENCY_STOP` → `/app/EMERGENCY_STOP`) broke when the host file didn't exist at container create time.
- If the `./safety/` directory is deleted or bind-mount fails (WSL bind-mount race — see Operational Gotchas), the trading loop loses its kill-switch. Auto-trader treats absent file as "safe to trade".
- Fix path: `touch /mnt/d/Bimo_max/crypto-trading-bot/safety/EMERGENCY_STOP` (stops trading immediately); `POST /api/portfolio/emergency-stop` (API path, admin-guarded).
- Tracking: compose patch applied 2026-05-19; emergency-stop route requires `admin_client` fixture in tests (memory note `feedback_pathlib_mocking.md`).

**`pathlib.Path.write_text` Mocking Gotcha — MEDIUM**
- Emergency-stop route and any route using `Path.write_text` / `Path.read_text` / `Path.open` bypasses `builtins.open` (they call `_io.open` at C level).
- Tests that patch `builtins.open` silently do nothing against these routes.
- Fix: patch `pathlib.Path.write_text` directly. Applied to `services/api-gateway/tests/test_main.py` and `test_gateway_80_coverage.py` (2026-05-03 session).
- Risk: any new route using `Path.*` methods and tested with `builtins.open` mock will silently pass with no real file-op coverage.
- Tracking: memory file `feedback_pathlib_mocking.md`.

**bcrypt 72-Byte Password Truncation (PR Branch, Not Main) — MEDIUM**
- The `fix/api-gateway-py314-deps` PR branch upgraded to `libpass[bcrypt]==1.9.3 + bcrypt==5.0.0` and switched `CryptContext` to `bcrypt_sha256` scheme (commit `6cd9bf6` on that branch).
- On `main` branch: `services/api-gateway/requirements.txt` pins `libpass[bcrypt]==1.9.3` and `bcrypt==5.0.0` with `CryptContext(schemes=["bcrypt_sha256"])` — the fix IS on main (auth_models.py:39).
- The PR branch is NOT yet merged but the fix is already present in main's `auth_models.py`. No truncation risk on currently deployed code.
- Monitor: if PR #77 is ever rebased and merged, verify it doesn't revert `auth_models.py`.
- Tracking: ADR-003 (`wiki/decisions/ADR-003-bcrypt-sha256-prehash.md`).

**Pre-LIVE 2% Risk Cap Must Be Restored — HIGH**
- ADR-010 (`wiki/decisions/ADR-010-max-risk-per-trade-paper-bump.md`) explicitly requires: before enabling `TRADING_MODE=LIVE`, `MAX_RISK_PER_TRADE` must be restored to ≤ 0.02 (from current paper default 0.10).
- Current value: `services/trading-engine/app/config.py:321` default `max_risk_per_trade = 0.10`.
- Pre-LIVE checklist: `docs/runbooks/LIVECLOSE-05.md` + `scripts/closure/liveclose-05-live-flip-smoke.sh`.
- Risk: if LIVE flip is attempted without this restore, each trade risks 10% of capital per trade — 5× the intended live cap.
- Tracking: ADR-010 accepted; LIVECLOSE-05 runbook exists; OP-01 blocks this gate.

---

## Operational Gotchas

**WSL2 Bind-Mount Race — HIGH (environment)**
- `docker inspect` can show bind mount present while the path inside the container is empty and root-owned (silent mount failure at container create time).
- Symptom: `PermissionError: [Errno 13] Permission denied: '/app/logs/service.log'` at service startup (observed in `risk-metrics-service`, 2026-05-03).
- Fix: `docker compose -f docker-compose.unified.yml up -d --force-recreate <service>`. Do not just restart.
- Tracking: CLAUDE.md documented.

**BuildKit Hangs on WSL2 — MEDIUM (environment)**
- `docker compose up -d --build <svc>` can stall indefinitely on WSL2 + Docker Desktop.
- Fix: `DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml up -d --build <svc>`.
- Tracking: CLAUDE.md documented.

**sentiment-analysis-service Image Fails to Build — MEDIUM**
- `services/sentiment-analysis-service/requirements.txt` pins `torch==2.2.0 + transformers==4.37.0` — large packages with frequent PyPI read timeouts in WSL2 + Docker Desktop environment.
- The service runs idle in compose (sentiment leg removed from signal pipeline: commits `c346483`, `acae081`, `fe941cf`, `c171bb0`). The image has historically failed to pull/build.
- Fix when needed: `DOCKER_BUILDKIT=0 docker compose build --no-cache sentiment-analysis` and retry. Or skip with `--no-deps`.
- Tracking: CLAUDE.md documented.

**api-gateway Tests Must Run in Container — MEDIUM**
- Host pip environment has fastapi 0.136; `HTTPBearer(auto_error=True)` returns 401 (RFC 6750) in that version.
- Deployed container pins fastapi 0.109 which returns 403 from the same path.
- Tests assert 403 on unauthenticated calls. Host run shows spurious failures that look like real regressions.
- Fix: `docker exec crypto-bot-api-gateway pytest services/api-gateway/tests/`.
- Tracking: CLAUDE.md + memory file `feedback_api_gateway_test_env.md`.

**BTC GRU Training OOM at Default Memory Limits — MEDIUM**
- BTC training gets OOM-killed at default Docker container memory limits.
- Fix before retraining: increase `deploy.resources.limits.memory` for `ml-retraining` service in `docker-compose.unified.yml`. No explicit memory limit block was found in current compose for that service — check Docker Desktop global WSL2 memory cap (`~/.wslconfig`).
- Tracking: CLAUDE.md documented.

**ML-prediction and tournament-harness Disabled by Default — LOW**
- `ml-prediction` service is behind `--profile ml` compose flag; not started with `docker compose up -d`.
- `tournament-harness` has its own service definition but requires migration OP-02/OP-03 carry-ins before it can read candles.
- Tracking: documented in compose comments and CLAUDE.md.

---

## Dependencies at Risk

**Sentiment-Analysis `torch==2.2.0` — MEDIUM**
- 2.2.0 is 2+ major versions behind (PyTorch reached 2.5+ by 2026). Security patches and CUDA compatibility fixes not pulled in.
- Service is idle (sentinel removed from pipeline); low urgency while gated off.
- Files: `services/sentiment-analysis-service/requirements.txt`.
- Tracking: untracked.

**`libpass[bcrypt]==1.9.3` — LOW**
- `passlib` successor package `libpass` used on main to support `bcrypt_sha256`. Package is relatively new and ecosystem adoption is limited. Monitor for CVEs.
- Files: `services/api-gateway/requirements.txt:19`.
- Tracking: ADR-003.

---

## Missing Critical Features

**Indicator Enable-State Persistence**
- Problem: gatekeeper rolling-confidence gate can promote/demote indicators at runtime, but the state is ephemeral (in-process only). Service restart resets all indicators to enabled.
- Blocks: the "per-indicator enable flag" feature documented in `services/trading-engine/app/handlers/orchestration.py:787`.
- Fix approach: write enable-states to Redis or Postgres on each gate event; load on startup.

**Production Aggregator ↔ Backtest Harness Parity**
- Problem: `backtesting/strategies/multi_indicator_strategy.py` is a standalone backtesting strategy (own RSI/MACD/BB, different params). It does not exercise `CoreAggregator`.
- `backtesting/run_walk_forward_ensemble.py` does import `CoreAggregator` and is the correct harness.
- Gap: walk-forward harness has not been validated against the post-2026-05-21 confidence-metric changes. Any signal-aggregator change should gate through this harness before merging.
- Fix: add a CI step that runs `run_walk_forward_ensemble.py` on ≥30 days of mainnet candles and asserts DSR > baseline.

---

*Concerns audit: 2026-05-22*
