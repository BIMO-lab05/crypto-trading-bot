# Phase 6 - Tile Audit (DASH-01)

**Generated:** 2026-05-13T20:43:20Z
**Plan:** 06-01
**Probe target:** `http://localhost:8000` (api-gateway, paper mode, mainnet prices)
**Stack state during probe:** api-gateway healthy; trading-engine healthy; market-data, portfolio-manager, ml-prediction, sentiment-analysis containers up but `unhealthy` per `docker ps`.

## Verdict semantics (per D-02)

| Verdict | Meaning |
|---|---|
| `FIXED` | Endpoint returns 200 with the documented shape. Plan 6-05 wires `<TileState/>` and the tile renders real data. Read by `scripts/audit_tiles.py` as a regression gate. |
| `LABELED_STALE` | Backing capability is intentionally off this phase. Plan 6-05 sets `<TileState forceStale={true}/>` so the badge is visible without faking data. Rolls to Phase 7 backlog. |
| `REMOVED` | Endpoint is dead code (404 with a "NOT IMPLEMENTED" note in `api.js` or analog). Plan 6-05 deletes the tile from the dashboard. |
| `PENDING-OPERATOR` | Operator must decide between FIX / STALE / REMOVE at the Task 3 checkpoint before this table is committed. |

## `last_updated_at?` column

Per W-02 scope-down: only `/api/config/safety-state` (Plan 6-02) will emit `last_updated_at` in Phase 6. Every body-tile endpoint in the table below is `no` today and is Phase 7 backlog for D-15 stale-badge wiring. `LABELED_STALE` and page-level rows are `n/a` (use `forceStale` or are not probed).

---

## Performance page tiles

| Tile | Component File | Backing Endpoint | Expected Shape | Observed Shape | Verdict | last_updated_at? | Notes |
|---|---|---|---|---|---|---|---|
| KeyMetricsStrip | `frontend/src/components/KeyMetricsStrip.jsx` | `GET /api/trading/performance` | `{success: bool, metrics: object, timestamp: number}` | `{success, metrics: {total_trades, winning_trades, losing_trades, total_pnl, realized_pnl, unrealized_pnl, ...}, timestamp}` (HTTP 200) | FIXED | no | Reads `usePositions` + `useTradingStatus` + `usePerformance`; load-bearing endpoint is `/api/trading/performance`. |
| TradingSignals | `frontend/src/components/TradingSignals.jsx` | `GET /api/trading/signals/{symbol}?interval=60` | `{success: bool, signal: object, timestamp: number}` | `{success, signal: {symbol, timestamp, action, confidence, indicators, aggregated_score}, message: null, timestamp}` (HTTP 200) | FIXED | no | `useMultipleSignals` fans out one call per symbol. |
| HybridStrategyPanel | `frontend/src/components/HybridStrategyPanel.jsx` | `GET /api/trading/status` | `{success: bool, status: object, timestamp: number}` | `{success, status: {is_running, emergency_stop, symbols, hybrid_strategy_stats, ...}, timestamp}` (HTTP 200) | FIXED | no | Reads `data.status.hybrid_strategy_stats` subdict. |
| RegimeIndicator | `frontend/src/components/RegimeIndicator.jsx` | `GET /api/trading/status` | `{success: bool, status: object, timestamp: number}` | Same as HybridStrategyPanel (HTTP 200) | FIXED | no | Reads `data.status.hybrid_strategy_stats.trend_pct` + `mean_reversion_pct`. |
| TradingEnhancementsPanel | `frontend/src/components/TradingEnhancementsPanel.jsx` | `GET /api/trading/status` | `{success: bool, status: object, timestamp: number}` | Same as HybridStrategyPanel (HTTP 200) | FIXED | no | `useAutoTraderStatus` -> `extractTradingEnhancements(status)` decomposes circuit-breaker/kill-switch/slippage cells. |
| PerformanceAnalyticsPanel | `frontend/src/components/PerformanceAnalyticsPanel.jsx` | `GET /api/trading/performance` (primary) + `GET /api/trading/trades/history` (secondary) | `{success: bool, metrics: object, timestamp: number}` | Both endpoints HTTP 200; trades history returns `{success, trades: list, stats: object, count, timestamp}` | FIXED | no | Primary tile-shape check is `/api/trading/performance`. |

## Portfolio page tiles

| Tile | Component File | Backing Endpoint | Expected Shape | Observed Shape | Verdict | last_updated_at? | Notes |
|---|---|---|---|---|---|---|---|
| ActiveTrades | `frontend/src/components/ActiveTrades.jsx` | `GET /api/trading/positions?status=open` | `{success: bool, positions: list[object], count: number, timestamp: number}` | `{success: true, positions: [], count: 0, timestamp: ...}` (HTTP 200) | FIXED | no | Empty list is valid; tile must render empty-state via `<TileState/>` per Plan 6-05. |
| TradeHistory | `frontend/src/components/TradeHistory.jsx` | `GET /api/trading/trades/history?limit=50` | `{success: bool, trades: list[object], stats: object, count: number, timestamp: number}` | `{success, trades: [{symbol, side, entry_price, ...}], stats: {total_trades, winning_trades, ...}, count, timestamp}` (HTTP 200) | FIXED | no | Component uses raw `axios` import instead of `api.js`; works at audit level (same endpoint). |
| PortfolioCard | `frontend/src/components/PortfolioCard.jsx` | `GET /api/trading/performance` | `{success: bool, metrics: object, timestamp: number}` | Same as KeyMetricsStrip (HTTP 200) | FIXED | no | Reads `usePerformance` + `usePositions` + `useTradingStatus` — does NOT call `usePortfolio`, so unaffected by `/api/portfolio` 503. |

## Phase1 page tiles

| Tile | Component File | Backing Endpoint | Expected Shape | Observed Shape | Verdict | last_updated_at? | Notes |
|---|---|---|---|---|---|---|---|
| PriceTickerGrid | `frontend/src/components/PriceTickerGrid.jsx` | `GET /api/market/ticker/{symbol}` | `{success: bool, data: object}` | `{"detail": "..."}` (HTTP 503) | PENDING-OPERATOR | n/a | market-data container is up but `unhealthy`. Operator decides: restore ticker endpoint (-> FIXED), or label STALE pending Phase 7 market-data refactor. |
| PriceChart | `frontend/src/components/PriceChart.jsx` | `GET /api/market/klines/{symbol}?interval=60&limit=24` | `{success: bool, data: list[object]}` | `{"detail": "..."}` (HTTP 503) | PENDING-OPERATOR | n/a | Same root cause as PriceTickerGrid (market-data unhealthy). Resolves with same operator decision. |
| Sparkline | `frontend/src/components/Sparkline.jsx` | `GET /api/market/klines/{symbol}?interval=60&limit=24` | `{success: bool, data: list[object]}` | `{"detail": "..."}` (HTTP 503) | PENDING-OPERATOR | n/a | Identical endpoint to PriceChart; resolves identically. |
| Phase1Dashboard | `frontend/src/pages/Phase1Dashboard.jsx` | n/a (page composes child tiles) | n/a (composition) | n/a | FIXED | n/a | Page-level wrapper. Composes KeyMetricsStrip + PriceTickerGrid + PriceChart + TradingSignals. Carries its own page verdict; child tiles carry endpoint verdicts. Not probed by audit_tiles.py. |

## Phase3 page tiles

| Tile | Component File | Backing Endpoint | Expected Shape | Observed Shape | Verdict | last_updated_at? | Notes |
|---|---|---|---|---|---|---|---|
| Phase3Dashboard | `frontend/src/pages/Phase3Dashboard.jsx` | `GET /api/ml/predict/price/{symbol}` (+ sentiment + MTF) | `{prediction: object}` (varies per sub-tile) | `{"detail": "..."}` (HTTP 503 across all ml/sentiment paths) | LABELED_STALE | n/a | ml-prediction-service + sentiment-analysis-service feature-flagged OFF (`ENABLE_ML_PREDICTIONS=false`, `ENABLE_SENTIMENT_ANALYSIS=false`). Plan 6-05 wires `<TileState forceStale={true}/>`. Real data returns in Phase 7+ after GRU rebuild on returns target. |

## Portfolio page (page-level tile)

| Tile | Component File | Backing Endpoint | Expected Shape | Observed Shape | Verdict | last_updated_at? | Notes |
|---|---|---|---|---|---|---|---|
| Portfolio | `frontend/src/pages/Portfolio.jsx` | `GET /api/portfolio` (primary) | `{balance: number, positions: list[object], total_value: number}` | `{"detail": "..."}` (HTTP 503) | PENDING-OPERATOR | n/a | Page calls `usePortfolio` which hits `/api/portfolio` (portfolio-manager container `unhealthy`). Other hooks on this page (positions/status/performance from trading-engine) are 200. Operator decides: restore `/api/portfolio` (-> FIXED) or migrate page to trading-engine aggregations only (-> REMOVE `usePortfolio`, replace via existing 200-OK endpoints). |

---

## Summary

- **15 tiles audited** (matches `06-PATTERNS.md` line 640 inventory exactly).
- **Verdicts (pre-checkpoint):** FIXED=10, PENDING-OPERATOR=4, LABELED_STALE=1.
- **last_updated_at emitters today:** `no` for 9 FIXED body-tile rows; `n/a` for 6 page-level/labeled-stale/pending rows. Zero `yes` (safety-state endpoint ships in Plan 6-02 and lives in StatusBar, not a body tile).
- **Endpoints already healthy (will pass `audit_tiles.py`):** `/api/trading/performance`, `/api/trading/status`, `/api/trading/positions`, `/api/trading/trades/history`, `/api/trading/signals/{symbol}`.
- **Endpoints broken at audit time (need operator decision):** `/api/market/ticker/{symbol}` (503), `/api/market/klines/{symbol}` (503), `/api/portfolio` (503).
- **Endpoints intentionally off (LABELED_STALE):** all `/api/ml/*` and `/api/sentiment/*` per feature flags.

PENDING-OPERATOR rows resolve at the Task 3 checkpoint; this table is committed only after those four verdicts are finalized.
