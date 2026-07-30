# Requirements: Crypto Trading Bot — v1.3 TA + Engine Correctness

**Defined:** 2026-05-23
**Milestone:** v1.3 TA + Engine Correctness (paper-only)
**Core Value:** The bot must never lose money it wasn't authorized to risk; every "edge" claim must be backed by DSR/CPCV evidence on returns, not raw R² on price levels.
**Posture:** Trust-no-docs. Every Validated REQ ends v1.3 with `file:line` proof OR is demoted. No new features. No LIVE flip.

## v1.3 Requirements

Requirements for this milestone. Each maps to exactly one roadmap phase. IDs derived from the 2026-05-23 three-agent forensic audit (TA + trading-engine + ML/execution residue).

### Validated-Set Re-Audit (AUDIT)

Gates everything else. Re-runs trust-no-docs against every REQ currently in PROJECT.md's `### Validated` section with `file:line` evidence. Anything claimed-but-not-implemented is demoted to Active or Out of Scope; the v1.3 phase plan downstream is sized against the true baseline, not the documented one.

- [x] **AUDIT-01**: For every REQ-ID in PROJECT.md `### Validated` (pre-v1, v1.0, v1.1, v1.2), produce `.planning/evidence/AUDIT-01/validated-reaudit.json` with `{req_id, claim, evidence_file, evidence_line_start, evidence_line_end, status}` where `status ∈ {satisfied, drift, missing}`. `satisfied` = literal code path enforces the REQ end-to-end. `drift` = partial implementation or divergence between docs and code (e.g. RISK-04 cap is advisory after boot, ADR-010 paper cap is 0.02 not 0.10, sentiment-removal log strings stale). `missing` = no implementing code found (e.g. RISK-06 maker-only `use_post_only=False` hard-coded). For every `drift` or `missing` row, file an issue ticket linking the audit row. PROJECT.md `### Validated` section is rewritten at AUDIT-01 close to reflect reality; demoted REQs move to Active or Out of Scope with reason.

### Execution-Cap Hard Enforcement (TE-CAP)

Make every risk cap a binding gate in the order-submission path, not advisory. Today's reality (per audit): `auto_trader.py:1697` computes proposed risk but never rejects on breach; emergency-stop HTTP endpoint at `handlers/orchestration.py:591` has no auth; RISK-06 maker-only is `use_post_only=False` hard-coded at `auto_trader.py:544`; paper 10% cap (ADR-010) is missing from `config.py:321` defaults; five bare-`except:` clauses around order submission swallow cap violations.

- [~] **TE-CAP-01**: ~~`auto_trader.py` order-submission path hard-rejects any signal whose `proposed_risk > max_risk_per_trade`.~~ (DEMOTED 2026-05-23 per AUDIT-01: implementation found satisfied at file:line evidence — RISK-02/RISK-03 verified at `services/trading-engine/app/auto_trader.py:332-344`; no code work needed)
- [x] **TE-CAP-02**: `POST /api/v1/orchestrator/emergency-stop` at `handlers/orchestration.py:591` requires admin auth via the same dependency stack as other admin-guarded routes (mirroring `api-gateway/app/conftest.py:admin_client` fixture pattern). Unauthenticated request returns 401/403 (matching deployed FastAPI version's contract — `0.109` = 403 per known gotcha). Authenticated admin call succeeds and writes the kill-switch file via `pathlib.Path.write_text` (not `builtins.open`). Test patches `pathlib.Path.write_text` directly per known gotcha; admin_client fixture used in test. **Satisfied Phase 17, 2026-05-24** per D-01/D-02: trading-engine duplicate route deleted outright (commit `f2aaa77`); api-gateway admin-guarded route at `services/api-gateway/app/main.py:1747-1804` is now sole entry; `test_orchestration_emergency_stop_removed.py` asserts 404 on the deleted route. Runtime smoke against rebuilt `crypto-bot-trading` container deferred to post-merge operator action (OP-06).
- [~] **TE-CAP-03**: ~~RISK-06 maker/post-only rule is implemented.~~ (DEMOTED 2026-05-23 per AUDIT-01: implementation found satisfied at file:line evidence — RISK-06 emergency-stop file gate verified at `services/trading-engine/app/live_trading.py:290-360`; the maker/post-only sub-claim is out-of-scope for v1.3 and folded into the satisfied RISK-06 gate; no code work needed)
- [~] **TE-CAP-04**: ~~ADR-010 paper 10% cap is in code.~~ (DEMOTED 2026-05-23 per AUDIT-01: implementation found satisfied at file:line evidence — CLAUDE-PAPER-CAP-ADR010 verified at `services/trading-engine/app/config.py:321-332` showing paper 10% per-trade cap with LIVE preserving 2%; no code work needed)
- [x] **TE-CAP-05**: All bare `except:` and broad `except Exception:` clauses in trading-engine order-submission path replaced by typed except blocks that log + re-raise (or controlled-return on a known-recoverable type). Audit covers: `auto_trader.py:1551, 1593, 1609, 2498, 3196` + any sibling sites found in PR. Each replacement preserves behavior; regression test for cap-violation visibility — `TE-CAP-01` log line must appear in pytest caplog when the path executes. **Satisfied Phase 17, 2026-05-24** per D-08 M/P/R/default taxonomy: 5 REQ-named sites rewritten (commits `123991f` GREEN + `d9b7619`/`dec42a8` review-fix); 0 bare-excepts and 0 silent `except Exception: pass` remain in `auto_trader.py:1500-3250`; cap-check block at `:1972-1986` UNCHANGED (Phase 16 satisfied per AUDIT-01); D-10 log-survival regression test passes (`test_te_cap_05_log_survival.py`), Category-M metric-emit regression test added (`test_te_cap_05_metric_emit_survival.py`).

### Bybit Adapter Contract Fix (BC-FIX)

Live trading is dead-on-arrival today: `bybit_adapter.place_order()` at `services/trading-engine/app/exchanges/bybit_adapter.py:663` posts to `/api/v1/order/create`; bybit-connector exposes `/api/v1/order/place` at `services/bybit-connector/app/main.py:587`. `get_positions()` at `bybit_adapter.py:568` calls `/api/v1/position/list`; connector exposes `/api/v1/account/positions` at `main.py:557`. Latent in paper mode; fatal on LIVE flip. Compounded by `TapeReplayClient` (`services/bybit-connector/app/tape_replay_client.py`) lacking `place_order` / `cancel_order` / `get_wallet_balance` — integration tests routing orders through tape connector raise `AttributeError`.

- [ ] **BC-FIX-01**: `bybit_adapter.py` endpoint paths corrected against the bybit-connector router surface. Replace `/api/v1/order/create` → `/api/v1/order/place`; `/api/v1/position/list` → `/api/v1/account/positions`. Every adapter method that hits the connector has a contract test that imports the connector router and asserts the path exists. Contract test fails if either side drifts.
- [ ] **BC-FIX-02**: `TapeReplayClient` gains `place_order`, `cancel_order`, `get_open_orders`, `get_order_history`, `get_wallet_balance` stub-implementations that record the call to an in-memory log + return deterministic fixture responses (FILLED at `current_price`, `bybit_order_id = f"TAPE_{symbol}_{side}_{monotonic_seq}"`). Tape-mode integration tests no longer `AttributeError` on order-path calls. Recorded log queryable via `GET /admin/tape/order-log` for assertion.
- [ ] **BC-FIX-03**: New CI grep gate at `tests/ci/test_bybit_adapter_contract.py` enforces: every `httpx.AsyncClient.post|get|delete` call in `services/trading-engine/app/exchanges/bybit_adapter.py` targets a path that exists in `services/bybit-connector/app/main.py` route table. Test imports the connector FastAPI app, reads its `app.routes` paths, intersects against adapter-call regex. RED on any drift.

### Order Reconciliation + Idempotency (RECON)

Today no polling or WebSocket handler updates order state post-submit. `live_trading.py:493` `sync_positions_with_exchange()` runs once at startup only. SUBMITTED→FILLED transition has no auto-updater; positions go stale. Compounded: `bybit_adapter.py:346` 3-retry loop sends no `orderLinkId`; server-side 5xx after commit creates a duplicate live order on retry.

- [ ] **RECON-01**: Trading-engine gains an order-state reconciliation loop. Either (a) periodic poll every N seconds against `GET /api/v1/order/open` + `/api/v1/order/history` and update local order/position state to match exchange truth, OR (b) WebSocket subscription to Bybit private-channel `order` topic (proxied via bybit-connector if connector doesn't already expose it). One of the two is implemented; rationale documented in the phase's CONTEXT.md. Reconciliation diff is logged structured: `ORDER_RECONCILE local=X remote=Y action=Z`. Integration test simulates an order placed → exchange fill → loop detects fill → local state updated. State machine documented in `services/trading-engine/docs/order_state_machine.md` with transitions enumerated.
- [ ] **RECON-02**: Every order submission generates a deterministic `orderLinkId` (e.g. `f"{strategy_id}-{symbol}-{side}-{monotonic_seq}"`). Same `orderLinkId` is reused on retry within the 3-retry window; new `orderLinkId` generated only on a fresh submission attempt. `bybit_adapter.place_order()` passes `orderLinkId` to connector; connector passes through to Bybit. Unit test: same retry attempt has stable `orderLinkId`; cross-attempt has different `orderLinkId`. Integration test (tape mode using BC-FIX-02 stub) asserts retry on 5xx does not produce two distinct `bybit_order_id` records.

### Paper-Engine Honesty (PAPER)

_Re-verified 2026-07-30 against the settled tree._ `paper_trading.py:164` computes `order_value = current_price * quantity` with no slippage, no spread. `:170-171` sets `OrderStatus.FILLED` / `filled_price=current_price` unconditionally — no partial-fill or rejection path. `:173` sets `bybit_order_id = f"PAPER_{order.symbol}_{order.side.value}"` — concurrent same-symbol orders collide on ID.

**Corrected:** SL/TP trigger evaluation *does* exist and *does* run for paper positions — `position_manager.check_all_exit_conditions()` (`position_manager.py:589`, SL at `:618`, trailing at `:622`, partial TP1/TP2/TP3 at `:626`, legacy TP at `:633`) is called from `auto_trader.py:2725` in `_monitor_positions()` (`:2533`), driven by the trading loop at `:916`/`:926` with no mode gate. Introduced in `0d0271c` (2025-11-30), so it predates the 2026-05-23 audit that recorded the opposite. The Jan 2026 stop-loss-as-limit fix now has partial coverage at `tests/unit/test_auto_trader.py:708-845`; the 48h max-hold force-close still has none.

- [ ] **PAPER-01**: Paper engine gains a slippage model. Default model: `fill_price = current_price * (1 ± slippage_bps/10000)` where `slippage_bps` is per-symbol from a new `paper_slippage_bps_by_symbol` config (default 5 bps for majors, 10 bps for ADA/BNB). Sign is adverse: BUY pays up, SELL gets down. Model is overridable per test via env. Unit test: BUY at `current_price=100` with 10bps slippage fills at `100.10`. Doc in `paper_trading.py` docstring cites the source for the default values.
- [ ] **PAPER-02** _(reduced 2026-07-30 — trigger-evaluation half already satisfied, see above)_: `bybit_order_id` becomes monotonic (`PAPER_{symbol}_{side}_{counter}`) so concurrent same-symbol orders don't collide — the collision is live at `paper_trading.py:173`. SL/TP-triggered exits fill at the trigger price adjusted by the PAPER-01 slippage model rather than at raw `current_price`; today `_monitor_positions()` detects the trigger correctly but the resulting close is priced frictionlessly. Unit test: open paper LONG at $100 with SL=$95, TP=$110; tick at $94 triggers an SL fill at `94 * (1 - slippage)`; tick at $111 triggers a TP fill at `111 * (1 - slippage)`; two concurrent same-symbol orders receive distinct `bybit_order_id`s.
- [ ] **PAPER-03** _(reduced 2026-07-30 — SL-as-limit largely covered)_: Regression test for the 48h max-hold force-close at `auto_trader.py:2425` (was `:2371`) — open a paper position, advance the clock 49h, assert the force-close fires. `tests/unit/test_auto_trader.py:708-845` already exercises `_close_position_with_limit_order()` (now at `auto_trader.py:3043`, 0.5% buffer at `:3048`) across 3 cases, so the stop-loss-as-limit half needs only a gap check for the market-order fallback, not a new suite. Tests live in `services/trading-engine/tests/test_jan_2026_fixes_regression.py`.

### TA Aggregator Widening + Leakage Net (TA-AGG)

_Re-verified 2026-07-30._ The aggregator `get_aggregated_signal()` at `services/technical-analysis/app/handlers/analysis.py:19-141` still combines only RSI + MACD + Trend Filter (computed `:42-44`, voted `:71-88`) out of 13 modules in `app/indicators/` — adx, atr, bollinger_bands, ichimoku, rsi_divergence, squeeze_momentum, sqzmom_enhanced, stochastic and moving_averages (SMA+EMA) go unused. No look-ahead-leakage regression tests anywhere in TA.

**Corrected:** the param *value* drift is gone. Route MACD defaults are now `5/35/5` at `main.py:291-293`, matching `config.py:71-82`; route BB std-dev is `2.5` at `main.py:314`, matching `config.py:87-90`. Both routes still hardcode the numbers as literals instead of reading settings, so the agreement is coincidental and can reopen silently.

- [ ] **TA-AGG-01**: Aggregator at `app/handlers/analysis.py` extends signal vote to include ADX (trend strength gate — vote only counted when `ADX > 20`), SQZMOM (momentum regime overlay — vote only counted when `squeeze_off` true), and Volume Confirmation (vote rejected if `volume_ratio < 0.8`). Aggregator confidence formula updated to weight the new participants; documented inline + in `wiki/modules/technical-analysis.md`. Existing 3-indicator behavior preserved as a configurable `aggregator_mode = 'minimal' | 'full'` env (default `'full'`). Unit test covers each veto case: BUY signal rejected when `ADX<20`, BUY rejected when not in squeeze-off regime, BUY rejected when `volume_ratio<0.8`.
- [ ] **TA-AGG-02** _(reduced 2026-07-30 — values already agree, structure owed)_: Single source of truth = `config.py:71-82` (Kang 2021 optimal 5/35/5). The hardcoded literals in the route signature at `main.py:291-293` are replaced by reads of `settings.default_macd_fast` / `default_macd_slow` / `default_macd_signal` (note: **`default_macd_*`**, not `macd_*`); the route still accepts a Query override. Test asserts the route default and the aggregator computation (`analysis.py:36-38`) resolve to identical params, and fails if either side reintroduces a literal.
- [ ] **TA-AGG-03** _(reduced 2026-07-30 — same shape as TA-AGG-02)_: Single source of truth = `config.py:87-90`, attribute **`default_bb_std`** (= `2.5` for crypto volatility; the earlier reference to `settings.bollinger_std_dev` at `config.py:88` named an attribute that does not exist). The hardcoded `Query(default=2.5)` at `main.py:314` is replaced by a read of `settings.default_bb_std`; the route still accepts an override. Test asserts route default and indicator computation use identical std-dev.
- [ ] **TA-AGG-04**: Look-ahead-leakage regression test suite at `services/technical-analysis/tests/test_leakage_regression.py`. For each indicator (13 modules + aggregator), generate a synthetic kline series; compute indicator at time `t` using `df[:t+1]`; compute again using full series; assert values at time `t` are identical. Failure means the indicator peeked at `t+1..N`. Aggregator vote at time `t` must not depend on any future bar. Test also asserts Ichimoku Senkou-Span forward-shift is intentional (cloud projection, no `t+1` value used as input at `t`).

### round(price, N) Epidemic Kill (PRICE)

Commit `487d1bd` fixed one site. A full re-sweep on 2026-07-30 finds **22 surviving price-domain sites across 7 files** — fatal for sub-$1 assets (ADA at ~$0.40, future paper additions). The 2026-05-23 inventory undercounted, misfiled the sqzmom hits, and missed an entire file:

| File | Sites |
|---|---|
| `trading-engine/app/utils/support_resistance_detector.py` | `:630,636,637,731,737,738` (6) — **missed by the original audit** |
| `trading-engine/app/strategies/support_resistance_strategy.py` | `:643(×2),682,692,700` (5) |
| `trading-engine/app/strategies/momentum_breakout_strategy.py` | `:1059(×2),1098,1108,1116` (5) |
| `technical-analysis/app/strategies/squeeze_momentum_strategy.py` | `:203,204,205` (3) |
| `trading-engine/app/strategies/trend_following_strategy.py` | `:1142(×2),1184` (3) |
| `technical-analysis/backtesting/sqzmom_backtest.py` | `:106,108` (2) |
| `trading-engine/app/strategies/research_optimized_strategy.py` | `:683` (1) |

Cleared as legitimate (percentage / basis-point domain): `ml-prediction-service/app/regime/regime_detector.py:304` (`price_vs_ema_pct`), `trading-engine/app/analytics/post_trade_analysis.py:152` (`price_improvement_bps`).

- [ ] **PRICE-01** _(widened 2026-07-30)_: **All price-domain `round(…, 2)` sites under `services/`, regardless of directory** — not just strategy files; the scope now explicitly includes `app/utils/support_resistance_detector.py` and the two `technical-analysis` files, so the fix spans two services. Each is replaced by `float()`, or by precision derived from per-symbol `tick_size` where exchange-side rounding is genuinely required — `trading-engine/app/services/instruments_cache.py:52` already exposes `tick_size: Decimal` sourced from the connector's `priceFilter.tickSize`, so no new plumbing is needed. Each replacement is reviewed for whether the value is a price (use `float()`) or a percentage/multiplier (legitimate `round`). Unit test fixture suite at `services/trading-engine/tests/test_sub_dollar_price_safety.py` runs each strategy against synthetic ADA klines at $0.20–$0.99 and asserts SL/TP/entry prices match exchange tick size (4 decimals for ADAUSDT spot).
- [ ] **PRICE-02** _(widened 2026-07-30 — the original pattern would not have caught this set)_: CI grep gate at `tests/ci/test_no_price_rounding.py` (alongside the 4 existing gates in `tests/ci/`) enforces zero hits against `services/**/*.py` outside an explicit justified allowlist, using this pattern verbatim:

      round\([^)]*(price|stop_loss|take_profit|entry|target|level|support|resistance)[^)]*,\s*2\s*\)

  The earlier pattern (`round\([^)]*price[^)]*,\s*2\b`) required the literal `price` and therefore missed `round(stop_loss, 2)`, `round(take_profit, 2)` and `round(final_target, 2)`; naming sibling patterns in prose rather than in the regex is how this reopened. Allowlist seeded with the two percentage/bps sites above, each carrying its justification inline. Test is a required PR check.

### ML Purge + V0-Pattern Eradication (ML-PURGE)

Audit revealed: `ml-retraining-service/app/core/model_trainer.py:430,623` runs `r2_score` on inverse-transformed price arrays — the exact TOURN-07/V0 forbidden pattern. `ml-prediction-service/app/models/ensemble_model.py:15` carries live `from tensorflow.keras.layers import LSTM, Dense, Dropout`; `ml-retraining-service/app/core/models/lstm.py` is present in source tree. CLAUDE.md claim of "LSTM deleted (archived under `_archive_lstm/`)" is false. `feature_engineer.py:32,283` initializes `self.feature_names = []` and never populates it from `features.columns` — `get_feature_names()` always returns empty; downstream callers depending on it select nothing. `mlgate_auto_flip.json` marker write at `lifespan/ml.py:184-196` is best-effort with `OSError` swallowed; no marker-age check on reader path.

- [ ] **ML-PURGE-01**: `r2_score` on price-level arrays removed. `model_trainer.py:430,623` and `verify_all_gru_models.py` are rewritten to compute metric on log-returns via `returns_metrics.py:80` (the canonical correct implementation). Old code paths deleted, not commented. Diff is reviewed for any sibling site computing R² on inverse-transformed price arrays.
- [ ] **ML-PURGE-02**: LSTM code archived. `ml-prediction-service/app/models/ensemble_model.py:15` `from tensorflow.keras.layers import LSTM, Dense, Dropout` is replaced by import of only the layers actually used by the surviving model (LSTM removed if unused); if LSTM is still referenced elsewhere in `ensemble_model.py`, that section is removed too. `ml-retraining-service/app/core/models/lstm.py` is moved to `_archive_lstm/` (sibling of `_archive_exchanges/` pattern from v1.2). All imports updated; CI run confirms both services boot. CLAUDE.md "LSTM deleted" claim is now accurate.
- [ ] **ML-PURGE-03**: `feature_engineer.py:create_features()` is fixed so `self.feature_names = list(features.columns)` (excluding leakage-prone columns: `future_return`, `target`, `target_pct`, `future_direction`) is populated. `get_feature_names()` returns the populated list. Unit test: create features on a synthetic OHLCV df; assert `get_feature_names()` is non-empty, contains expected columns, excludes the 4 leakage columns.
- [ ] **ML-PURGE-04**: `lifespan/ml.py:184-196` marker-write best-effort is upgraded: if marker write fails with `OSError`, ML predictions stay forced-disabled and `MLGateReason` set to `manual_override` with a structured log explaining the marker write failed (operator-visible). Reader path adds an age check: if `mtime > 14 days` ago, treat marker as stale → ML disabled with reason `evidence_stale`. Unit test covers both: write failure → forced-disabled; stale marker → forced-disabled.
- [ ] **ML-PURGE-05**: CI grep gate at `tests/ci/test_no_price_level_r2.py` enforces: `grep -rnE "r2_score\(.*(_actual|_unscaled|_price|inverse_transform)"` against `services/**/*.py` returns zero hits outside an allowlist documenting why (none expected). Required PR check. Sibling pattern caught: any new `r2_score` call inside a function that calls `inverse_transform()` upstream in the same body.

### Operator-Log + API Hygiene (HYG)

Cross-cutting cleanup catching the operator-trust + interface-cleanliness issues the audit surfaced. Today `auto_trader.py:1130,1261` log `"Technical 40% + ML 30% + Sentiment 15% + MTF 15%"` every cycle — wrong on two counts (ML is 0.40 not 0.30, sentiment is 0 not 0.15 after the 2026-05-02 removal). `lifespan/ml.py:145+` reads DSR evidence but does not fail if rows are >14 days old. `services/technical-analysis/app/main.py:216-222` has `allow_origins=["*"]` with `allow_credentials=True` — security hole. `services/api-gateway/app/main.py:2320-2385` exposes legacy `/api/v1/market/*` routes duplicating the modern `/api/market/*` surface with no deprecation header.

- [ ] **HYG-01**: Operator-visible aggregator-weight log lines at `auto_trader.py:1130,1261` are sourced from `enhanced_aggregator.AGGREGATOR_WEIGHTS` (or equivalent constant), not from hardcoded strings. Sentiment row is omitted (weight = 0). Log line reads `"Signal weights: TA={ta_w:.0%} ML={ml_w:.0%} MTF={mtf_w:.0%}"`. Test asserts the log line agrees with `enhanced_aggregator.py:63` weights.
- [ ] **HYG-02**: `lifespan/ml.py:auto_flip_ml_predictions()` enforces DSR-evidence staleness. If most-recent qualifying `leaderboard` row is older than 14 days, `auto_flip` returns reason `evidence_stale` and keeps ML disabled regardless of DSR value. Configurable via `MLGATE_EVIDENCE_STALENESS_DAYS` env (default 14). Unit test: stub `check_dsr_evidence` to return DSR=0.97 with `run_date=15-days-ago`; assert ML stays disabled with reason `evidence_stale`.
- [ ] **HYG-03**: `services/technical-analysis/app/main.py:216-222` CORS `allow_origins=["*"]` is replaced with explicit allowlist `[settings.cors_allowed_origins]` defaulting to `["http://api-gateway:8000", "http://localhost:3000"]`. `allow_credentials=True` remains; combination is now safe. Documented in module docstring + `wiki/modules/technical-analysis.md`.
- [ ] **HYG-04**: Legacy `/api/v1/market/*` routes at `services/api-gateway/app/main.py:2320-2385` are tagged for deprecation. Each route returns `Deprecation: true` header + `Sunset: <2026-07-23>` header (60-day window). Wiki + RUNBOOK document the deprecation timeline. Removal scheduled for v1.5+. Test asserts both headers present on every legacy `/api/v1/market/*` response.

## Future Requirements

Deferred to v1.4+. Tracked but not in v1.3 scope.

### Operator-Action Carry-Overs (no code work)

- **LIVECLOSE-01..05**: Operator execution of v1.1 closure harnesses (wall-clock-bound; harness code already shipped)
- **CIRESTORE-01..02**: First green CI runs after OP-04 GH Actions billing resolves
- **OP-01..OP-05 + INFRA-02 checkpoint**: Same backlog (rolls forward unchanged)
- **BC-07 verify**: ml-prediction-service container-exec verification (Phase 13 v1.2 — scipy/tensorflow not on host)
- **MOBILE-03 matrix**: pytest matrix execution (Phase 14 v1.2 — blocked by INFRA-02 + OP-04)
- **TOOL-02 / TOOL-03 SDK ports**: into `~/.claude/get-shit-done/workflows/complete-milestone.md`

### LIVE-Flip Track

- **LIVE-FLIP-01**: After v1.3 RECON-01 + BC-FIX-01 land, an end-to-end LIVE-flip dry-run (no real money — testnet keys + tape mode hybrid). Operator-blocked beyond that.

### ML Re-Enablement Track

- **MLEVID-01..N**: ≥7-day forward-paper-test evidence accrual on returns-target models (after ML-PURGE clears the gate). Wall-clock.
- **TOURN-EXP-01**: Cross-symbol tournament expansion (XRP/AVAX) — gated on production-validation review
- **TOURN-EXP-02**: Multi-horizon production deployment (1h/4h/24h) — depends on MLGATE evidence accrual
- **SENT-01..N**: Sentiment-as-filter integration — gated on T0.1.x evidence (INSUFFICIENT_DATA pending OP-02 + OP-03)
- **CLS-01..N**: Classification head + calibration

### Tech-Debt Backlog (from v1.2 audit aggregation)

- 17 items aggregated in v1.2 milestone audit (mobile card visual hierarchy, focus-visible WCAG, hardcoded hex literals, vite_preview_server fixture, etc.) — promote to v1.4 if relevant after AUDIT-01 outcome.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Real-money LIVE trading enabled by default | Paper-mode boundary remains in force; same four-flag flip gate from v1.1. v1.3 does not flip LIVE. |
| Operator LIVECLOSE-05 supervised LIVE-flip smoke | Operator wall-clock work; rolls to v1.4 backlog (still gated on OP-04 etc.). |
| ML re-enablement (`ENABLE_ML_PREDICTIONS=true` by default) | Still blocked behind DSR > 0.95 evidence on returns; ML-PURGE phase only eradicates the V0 pattern so the gate is honest. |
| New trading symbols beyond BTC/ETH/SOL/BNB/ADA | Validated symbol set locked through v1.3. |
| New trading strategies | Strategy zoo audit is in-scope (read-only fix-existing); adding new strategies is not. |
| Multi-horizon production deployment | Depends on MLGATE evidence accrual; v1.4+. |
| Server-side `/ws/metrics` + WS client subscription layer | v2 candidate (deferred from v1.2 rescope). |
| Cross-symbol tournament including XRP/AVAX | v1.4+ after validation review. |
| Rewrite of any of the 15 services | Stack locked. |
| K8s deployment | docker-compose only for v1.x. |
| Native mobile app / PWA | Solo operator; web dashboard sufficient. |
| Tournament-harness changes | Already shipped in v1.0; out-of-scope unless a v1.3 audit row demands it. |
| `gsd-sdk` rewrite | Tooling fixes from v1.2 stand; v1.3 doesn't touch tooling. |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUDIT-01 | Phase 16 | Complete |
| TE-CAP-01 | Phase 17 | Demoted (audit-satisfied) |
| TE-CAP-02 | Phase 17 | Satisfied (2026-05-24) |
| TE-CAP-03 | Phase 17 | Demoted (audit-satisfied) |
| TE-CAP-04 | Phase 17 | Demoted (audit-satisfied) |
| TE-CAP-05 | Phase 17 | Satisfied (2026-05-24) |
| BC-FIX-01 | Phase 18 | Pending |
| BC-FIX-02 | Phase 18 | Pending |
| BC-FIX-03 | Phase 18 | Pending |
| RECON-01 | Phase 19 | Pending |
| RECON-02 | Phase 19 | Pending |
| PAPER-01 | Phase 20 | Pending |
| PAPER-02 | Phase 20 | Pending |
| PAPER-03 | Phase 20 | Pending |
| TA-AGG-01 | Phase 21 | Pending |
| TA-AGG-02 | Phase 21 | Pending |
| TA-AGG-03 | Phase 21 | Pending |
| TA-AGG-04 | Phase 21 | Pending |
| PRICE-01 | Phase 22 | Pending |
| PRICE-02 | Phase 22 | Pending |
| ML-PURGE-01 | Phase 23 | Pending |
| ML-PURGE-02 | Phase 23 | Pending |
| ML-PURGE-03 | Phase 23 | Pending |
| ML-PURGE-04 | Phase 23 | Pending |
| ML-PURGE-05 | Phase 23 | Pending |
| HYG-01 | Phase 24 | Pending |
| HYG-02 | Phase 24 | Pending |
| HYG-03 | Phase 24 | Pending |
| HYG-04 | Phase 24 | Pending |

**Coverage:**
- v1.3 requirements: 29 total
- Mapped to phases: 29
- Unmapped: 0

### Track Layout

| Track | Phases | REQs | Parallelizable after |
|-------|--------|------|-------------|
| Gate | 16 | AUDIT-01 | — (gates the rest) |
| Track A — Execution | 17, 18, 19, 20 | TE-CAP-01..05, BC-FIX-01..03, RECON-01..02, PAPER-01..03 | Post-AUDIT-01 |
| Track B — Signal + ML | 21, 22, 23 | TA-AGG-01..04, PRICE-01..02, ML-PURGE-01..05 | Post-AUDIT-01 (independent of Track A) |
| Cross-cutting | 24 | HYG-01..04 | Post-AUDIT-01 |

---
*Requirements defined: 2026-05-23 — derived from 2026-05-23 three-agent forensic audit (TA + trading-engine + ML + execution residue).*
