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
| `PENDING-OPERATOR` | (Resolved 2026-05-13 — see audit log below.) Was used pre-checkpoint for rows where the operator decided between FIX / STALE / REMOVE at Task 3 before this table was committed. |

## `last_updated_at?` column

Per W-02 scope-down: only `/api/config/safety-state` (Plan 6-02) will emit `last_updated_at` in Phase 6. Every body-tile endpoint in the table below is `no` today and is Phase 7 backlog for D-15 stale-badge wiring. `LABELED_STALE` and page-level rows are `n/a` (use `forceStale` or are not probed).

---

## Performance page tiles

| Tile | Component File | Backing Endpoint | Expected Shape | Observed Shape | Verdict | data-testid | last_updated_at? | Notes |
|---|---|---|---|---|---|---|---|---|
| KeyMetricsStrip | `frontend/src/components/KeyMetricsStrip.jsx` | `GET /api/trading/performance` | `{success: bool, metrics: object, timestamp: number}` | `{success, metrics: {total_trades, winning_trades, losing_trades, total_pnl, realized_pnl, unrealized_pnl, ...}, timestamp}` (HTTP 200) | FIXED | `key-metrics-strip` | no | Reads `usePositions` + `useTradingStatus` + `usePerformance`; load-bearing endpoint is `/api/trading/performance`. |
| TradingSignals | `frontend/src/components/TradingSignals.jsx` | `GET /api/trading/signals/{symbol}?interval=60` | `{success: bool, signal: object, timestamp: number}` | `{success, signal: {symbol, timestamp, action, confidence, indicators, aggregated_score}, message: null, timestamp}` (HTTP 200) | FIXED | `trading-signals` | no | `useMultipleSignals` fans out one call per symbol. |
| HybridStrategyPanel | `frontend/src/components/HybridStrategyPanel.jsx` | `GET /api/trading/status` | `{success: bool, status: object, timestamp: number}` | `{success, status: {is_running, emergency_stop, symbols, hybrid_strategy_stats, ...}, timestamp}` (HTTP 200) | FIXED | `hybrid-strategy-panel` | no | Reads `data.status.hybrid_strategy_stats` subdict. |
| RegimeIndicator | `frontend/src/components/RegimeIndicator.jsx` | `GET /api/trading/status` | `{success: bool, status: object, timestamp: number}` | Same as HybridStrategyPanel (HTTP 200) | FIXED | `regime-indicator` | no | Reads `data.status.hybrid_strategy_stats.trend_pct` + `mean_reversion_pct`. |
| TradingEnhancementsPanel | `frontend/src/components/TradingEnhancementsPanel.jsx` | `GET /api/trading/status` | `{success: bool, status: object, timestamp: number}` | Same as HybridStrategyPanel (HTTP 200) | FIXED | `trading-enhancements-panel` | no | `useAutoTraderStatus` -> `extractTradingEnhancements(status)` decomposes circuit-breaker/kill-switch/slippage cells. |
| PerformanceAnalyticsPanel | `frontend/src/components/PerformanceAnalyticsPanel.jsx` | `GET /api/trading/performance` (primary) + `GET /api/trading/trades/history` (secondary) | `{success: bool, metrics: object, timestamp: number}` | Both endpoints HTTP 200; trades history returns `{success, trades: list, stats: object, count, timestamp}` | FIXED | `performance-analytics-panel` | no | Primary tile-shape check is `/api/trading/performance`. |

## Portfolio page tiles

| Tile | Component File | Backing Endpoint | Expected Shape | Observed Shape | Verdict | data-testid | last_updated_at? | Notes |
|---|---|---|---|---|---|---|---|---|
| ActiveTrades | `frontend/src/components/ActiveTrades.jsx` | `GET /api/trading/positions?status=open` | `{success: bool, positions: list[object], count: number, timestamp: number}` | `{success: true, positions: [], count: 0, timestamp: ...}` (HTTP 200) | FIXED | `active-trades` | no | Empty list is valid; tile must render empty-state via `<TileState/>` per Plan 6-05. |
| TradeHistory | `frontend/src/components/TradeHistory.jsx` | `GET /api/trading/trades/history?limit=50` | `{success: bool, trades: list[object], stats: object, count: number, timestamp: number}` | `{success, trades: [{symbol, side, entry_price, ...}], stats: {total_trades, winning_trades, ...}, count, timestamp}` (HTTP 200) | FIXED | `trade-history` | no | Component uses raw `axios` import instead of `api.js`; works at audit level (same endpoint). |
| PortfolioCard | `frontend/src/components/PortfolioCard.jsx` | `GET /api/trading/performance` | `{success: bool, metrics: object, timestamp: number}` | Same as KeyMetricsStrip (HTTP 200) | FIXED | `portfolio-card` | no | Reads `usePerformance` + `usePositions` + `useTradingStatus` — does NOT call `usePortfolio`, so unaffected by `/api/portfolio` 503. |

## Phase1 page tiles

| Tile | Component File | Backing Endpoint | Expected Shape | Observed Shape | Verdict | data-testid | last_updated_at? | Notes |
|---|---|---|---|---|---|---|---|---|
| PriceTickerGrid | `frontend/src/components/PriceTickerGrid.jsx` | `GET /api/market/ticker/{symbol}` | `{success: bool, data: object}` | `{"detail": "..."}` (HTTP 503) | LABELED_STALE | `price-ticker-grid` | n/a | market-data container is up but `unhealthy`. Operator approved 2026-05-13: LABELED_STALE — market-data container unhealth is an ops fix tracked separately; Phase 6 ships the stale-badge affordance via forceStale={true}. |
| PriceChart | `frontend/src/components/PriceChart.jsx` | `GET /api/market/klines/{symbol}?interval=60&limit=24` | `{success: bool, data: list[object]}` | `{"detail": "..."}` (HTTP 503) | LABELED_STALE | `price-chart` | n/a | Same operator decision: LABELED_STALE pending Phase 7 market-data refactor. |
| Sparkline | `frontend/src/components/Sparkline.jsx` | `GET /api/market/klines/{symbol}?interval=60&limit=24` | `{success: bool, data: list[object]}` | `{"detail": "..."}` (HTTP 503) | LABELED_STALE | `sparkline` | n/a | Same operator decision: LABELED_STALE pending Phase 7 market-data refactor. |
| Phase1Dashboard | `frontend/src/pages/Phase1Dashboard.jsx` | n/a (page composes child tiles) | n/a (composition) | n/a | FIXED | `phase1-dashboard` | n/a | Page-level wrapper. Composes KeyMetricsStrip + PriceTickerGrid + PriceChart + TradingSignals. Carries its own page verdict; child tiles carry endpoint verdicts. Not probed by audit_tiles.py. |

## Phase3 page tiles

| Tile | Component File | Backing Endpoint | Expected Shape | Observed Shape | Verdict | data-testid | last_updated_at? | Notes |
|---|---|---|---|---|---|---|---|---|
| Phase3Dashboard | `frontend/src/pages/Phase3Dashboard.jsx` | `GET /api/ml/predict/price/{symbol}` (+ sentiment + MTF) | `{prediction: object}` (varies per sub-tile) | `{"detail": "..."}` (HTTP 503 across all ml/sentiment paths) | LABELED_STALE | `phase3-dashboard` | n/a | ml-prediction-service + sentiment-analysis-service feature-flagged OFF (`ENABLE_ML_PREDICTIONS=false`, `ENABLE_SENTIMENT_ANALYSIS=false`). Plan 6-05 wires `<TileState forceStale={true}/>`. Real data returns in Phase 7+ after GRU rebuild on returns target. |

## Portfolio page (page-level tile)

| Tile | Component File | Backing Endpoint | Expected Shape | Observed Shape | Verdict | data-testid | last_updated_at? | Notes |
|---|---|---|---|---|---|---|---|---|
| Portfolio | `frontend/src/pages/Portfolio.jsx` | `GET /api/portfolio` (primary) | `{balance: number, positions: list[object], total_value: number}` | `{"detail": "..."}` (HTTP 503) | LABELED_STALE | `portfolio-page` | n/a | Operator approved 2026-05-13: LABELED_STALE — portfolio-manager container unhealth is an ops fix tracked separately; Phase 6 ships the stale-badge affordance via forceStale={true}. usePortfolio hook stays as-is; ops fix restores backing endpoint. |

## Tournament page tiles

| Tile | Component File | Backing Endpoint | Expected Shape | Observed Shape | Verdict | data-testid | last_updated_at? | Notes |
|---|---|---|---|---|---|---|---|---|
| TournamentLeaderboard | `frontend/src/components/TournamentLeaderboard.jsx` | `GET /api/tournament/snapshots/{tournament_id}` | `{snapshot: object, ensemble: object|null, significance: object|null}` | (Phase 7 — seeded by `tests/fixtures/tournament/smoke-fixture.json` + 2 sidecars via `tournament_snapshot_seeded` pytest fixture, D-08) | FIXED | `tournament-leaderboard` | yes | Phase 7 tile per D-16. `exported_at` drives `<TileState/>` `last_updated_at` but `staleAfterMs=Infinity` per D-23 (frozen snapshot; never auto-stale). Component file is created by Plan 04. |

---

## Summary

- **16 tiles tracked** (15 Phase 6 inventory + 1 Phase 7 Tournament row appended per D-16, 2026-05-14).
- **Verdicts (post-checkpoint, resolved 2026-05-13; Tournament row added 2026-05-14):** FIXED=11, LABELED_STALE=5, REMOVED=0. Operator decided all 4 PENDING-OPERATOR rows → LABELED_STALE (market-data + portfolio-manager container unhealth is an ops fix tracked outside Phase 6 scope; stale-badge affordance ships via `<TileState forceStale={true}/>` in Plan 6-05).
- **`data-testid` column (Phase 7 Plan 03 addition, 2026-05-14):** every non-REMOVED row carries a kebab-case `data-testid` matching the tile component's root JSX element, consumed by Plan 05's audit-driven smoke loop. Hard contract — Plan 05 fails if any non-REMOVED row is missing `data_testid`.
- **last_updated_at emitters today:** `no` for 9 FIXED body-tile rows; `n/a` for 6 page-level/labeled-stale/pending rows. Zero `yes` (safety-state endpoint ships in Plan 6-02 and lives in StatusBar, not a body tile).
- **Endpoints already healthy (will pass `audit_tiles.py`):** `/api/trading/performance`, `/api/trading/status`, `/api/trading/positions`, `/api/trading/trades/history`, `/api/trading/signals/{symbol}`.
- **Endpoints broken at audit time (now LABELED_STALE):** `/api/market/ticker/{symbol}` (503), `/api/market/klines/{symbol}` (503), `/api/portfolio` (503). Backing containers are up but unhealthy; ops fix tracked separately; Phase 6 surfaces the stale state via `<TileState forceStale={true}/>`.
- **Endpoints intentionally off (LABELED_STALE):** all `/api/ml/*` and `/api/sentiment/*` per feature flags.

### Operator audit log (Task 3 checkpoint)

- **Decided 2026-05-13:** all 4 PENDING-OPERATOR rows (PriceTickerGrid, PriceChart, Sparkline, Portfolio page) → `LABELED_STALE`. Rationale: market-data and portfolio-manager containers are healthy enough to serve health probes but their data endpoints return 503; restoring those endpoints is an ops/infra fix tracked outside Phase 6's DASH-01/05 scope. Plan 6-05 wraps these tiles with `forceStale={true}` so the operator sees the stale state instead of silent zeros or blank charts. Re-audit after Phase 7 market-data refactor lands.
- **Confirmed 2026-05-13:** Phase3Dashboard `LABELED_STALE` verdict stands — ML and sentiment services are intentionally off (`ENABLE_ML_PREDICTIONS=false`, `ENABLE_SENTIMENT_ANALYSIS=false`).
