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

- [ ] **TE-CAP-01**: `auto_trader.py` order-submission path hard-rejects any signal whose `proposed_risk > max_risk_per_trade`. Rejection emits structured log `ORDER_REJECTED reason=cap_exceeded proposed=X cap=Y` (greppable). Position is not opened; no exception, controlled return. Unit test covers: signal at cap-1bp passes; signal at cap+1bp rejected; signal at exactly cap passes. Integration test covers: paper-mode operator-flagged signal at 11% on $100 balance is rejected with the structured log line. Bypass path explicitly searched for in PR review.
- [ ] **TE-CAP-02**: `POST /api/v1/orchestrator/emergency-stop` at `handlers/orchestration.py:591` requires admin auth via the same dependency stack as other admin-guarded routes (mirroring `api-gateway/app/conftest.py:admin_client` fixture pattern). Unauthenticated request returns 401/403 (matching deployed FastAPI version's contract — `0.109` = 403 per known gotcha). Authenticated admin call succeeds and writes the kill-switch file via `pathlib.Path.write_text` (not `builtins.open`). Test patches `pathlib.Path.write_text` directly per known gotcha; admin_client fixture used in test.
- [ ] **TE-CAP-03**: RISK-06 maker/post-only rule is implemented. `auto_trader.py:544` hard-coded `use_post_only=False` is replaced by config-driven `use_post_only=settings.use_post_only_orders` with default `True`. Order submission path adds `"timeInForce": "PostOnly"` (or Bybit equivalent) when active. Order rejected by exchange with `post-only-would-take` triggers retry-with-reposition logic (max 3 attempts, then abandon). Unit test: post-only flag flows through `bybit_adapter.place_order()` request body.
- [ ] **TE-CAP-04**: ADR-010 paper 10% cap is in code. `config.py` adds runtime branch: `max_risk_per_trade = 0.10 if (PAPER_TRADING_MODE and not LIVE) else 0.02`. Pydantic validator rejects `max_risk_per_trade > 0.02` when `TRADING_MODE=LIVE`. Boot-path preflight (Phase 8 lineage) still enforces `≤0.02` in LIVE. Unit test: paper mode loads `0.10` default; LIVE mode rejects load with `0.10` set.
- [ ] **TE-CAP-05**: All bare `except:` and broad `except Exception:` clauses in trading-engine order-submission path replaced by typed except blocks that log + re-raise (or controlled-return on a known-recoverable type). Audit covers: `auto_trader.py:1551, 1593, 1609, 2498, 3196` + any sibling sites found in PR. Each replacement preserves behavior; regression test for cap-violation visibility — `TE-CAP-01` log line must appear in pytest caplog when the path executes.

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

Today `paper_trading.py:122` fills at `current_price` with no slippage, no spread. `paper_trading.py:148` sets `OrderStatus.FILLED` unconditionally — no partial-fill logic. `paper_trading.py:151` sets `bybit_order_id = f"PAPER_{symbol}_{side}"` — concurrent same-symbol orders collide on ID. No SL/TP trigger evaluation found in `paper_trading.py` or `position_manager.py` — paper positions with SL/TP orders silently never exit. The Jan 2026 fixes (48h max-hold, stop-loss-as-limit) have no regression tests.

- [ ] **PAPER-01**: Paper engine gains a slippage model. Default model: `fill_price = current_price * (1 ± slippage_bps/10000)` where `slippage_bps` is per-symbol from a new `paper_slippage_bps_by_symbol` config (default 5 bps for majors, 10 bps for ADA/BNB). Sign is adverse: BUY pays up, SELL gets down. Model is overridable per test via env. Unit test: BUY at `current_price=100` with 10bps slippage fills at `100.10`. Doc in `paper_trading.py` docstring cites the source for the default values.
- [ ] **PAPER-02**: Paper engine evaluates SL/TP trigger conditions on every market-data tick (or, if paper engine is signal-driven, on every aggregator invocation). Long position: TP triggers when `last_price >= take_profit`; SL triggers when `last_price <= stop_loss`. Symmetric for SHORT. Trigger creates a paper-fill at the trigger price + slippage. `bybit_order_id` becomes monotonic (`PAPER_{symbol}_{side}_{counter}`) so concurrent same-symbol orders don't collide. Unit test: open paper LONG at $100 with SL=$95, TP=$110; tick at $94 triggers SL fill at `94 * (1 - slippage)`; tick at $111 triggers TP fill at `111 * (1 - slippage)`.
- [ ] **PAPER-03**: Regression tests added for the Jan 2026 fixes (commit `380a674`) — 48h max-hold force-close at `auto_trader.py:2371` (open paper position, advance clock 49h, assert force-close fires) and stop-loss-as-limit at `auto_trader.py:2691-2698` (trigger SL when reason matches "stop"/"loss", assert limit-order path chosen with 0.5% buffer + market-order fallback). Tests live in `services/trading-engine/tests/test_jan_2026_fixes_regression.py`.

### TA Aggregator Widening + Leakage Net (TA-AGG)

Today the aggregator at `services/technical-analysis/app/handlers/analysis.py:19-132` combines only RSI + MACD + Trend Filter from 13 implemented indicators (ADX, Ichimoku, SQZMOM, RSI-Divergence, Volume Confirmation, ATR, Stochastic, Bollinger, SMA, EMA wasted). Param drift: route default MACD `8/17/9` (`main.py:284-286`) vs settings `5/35/5` (`config.py:71-81`); BB std-dev route `2.0` (`main.py:306`) vs config `2.5` (`config.py:88`). No look-ahead-leakage regression tests anywhere in TA.

- [ ] **TA-AGG-01**: Aggregator at `app/handlers/analysis.py` extends signal vote to include ADX (trend strength gate — vote only counted when `ADX > 20`), SQZMOM (momentum regime overlay — vote only counted when `squeeze_off` true), and Volume Confirmation (vote rejected if `volume_ratio < 0.8`). Aggregator confidence formula updated to weight the new participants; documented inline + in `wiki/modules/technical-analysis.md`. Existing 3-indicator behavior preserved as a configurable `aggregator_mode = 'minimal' | 'full'` env (default `'full'`). Unit test covers each veto case: BUY signal rejected when `ADX<20`, BUY rejected when not in squeeze-off regime, BUY rejected when `volume_ratio<0.8`.
- [ ] **TA-AGG-02**: MACD param divergence reconciled. Single source of truth = `config.py:71-81` (Kang 2021 optimal 5/35/5). Route Query defaults at `main.py:284-286` are removed; route accepts override via Query param but defaults to `settings.macd_*`. Test asserts route default and aggregator computation use identical params.
- [ ] **TA-AGG-03**: BB std-dev divergence reconciled. Single source of truth = `config.py:88` (`2.5` for crypto volatility). Route Query default at `main.py:306` is removed; route accepts override but defaults to `settings.bollinger_std_dev`. Test asserts route default and aggregator computation use identical std-dev.
- [ ] **TA-AGG-04**: Look-ahead-leakage regression test suite at `services/technical-analysis/tests/test_leakage_regression.py`. For each indicator (13 modules + aggregator), generate a synthetic kline series; compute indicator at time `t` using `df[:t+1]`; compute again using full series; assert values at time `t` are identical. Failure means the indicator peeked at `t+1..N`. Aggregator vote at time `t` must not depend on any future bar. Test also asserts Ichimoku Senkou-Span forward-shift is intentional (cloud projection, no `t+1` value used as input at `t`).

### round(price, N) Epidemic Kill (PRICE)

Commit `487d1bd` fixed one site; the 2026-05-23 audit found 6 more sites where price-domain values are rounded to 2 decimals — fatal for sub-$1 assets (ADA at ~$0.40, future paper additions). `services/trading-engine/app/strategies/trend_following_strategy.py:1105-1184` (8 hits), `support_resistance_strategy.py:643-700` (4 hits), `momentum_breakout_strategy.py:1059-1116` (4 hits), `research_optimized_strategy.py:683` (1 hit), plus the two known sqzmom hits.

- [ ] **PRICE-01**: All 6 strategy files have `round(price, 2)` replaced by `float(price)` (or precision derived from per-symbol `tick_size` if exchange-side rounding is required). Each replacement is reviewed for whether the value is a price (replace with `float()`) or a percentage/multiplier (legitimate use of `round`). Unit test fixture suite at `services/trading-engine/tests/test_sub_dollar_price_safety.py` runs each strategy against synthetic ADA klines at $0.20–$0.99; asserts SL/TP/entry prices match exchange tick size (4 decimals for ADAUSDT spot).
- [ ] **PRICE-02**: CI grep gate at `tests/ci/test_no_price_rounding.py` enforces: `grep -rnE "round\([^)]*price[^)]*,\s*2\b"` against `services/**/*.py` returns zero hits outside an explicit allowlist (must justify each exempt line). Test is required PR check. Gate also catches sibling patterns: `round(entry_price, 2)`, `round(.*stop_loss, 2)`, `round(.*take_profit, 2)`.

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
| TE-CAP-01 | Phase 17 | Pending |
| TE-CAP-02 | Phase 17 | Pending |
| TE-CAP-03 | Phase 17 | Pending |
| TE-CAP-04 | Phase 17 | Pending |
| TE-CAP-05 | Phase 17 | Pending |
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
