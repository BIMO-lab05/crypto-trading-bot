# Pipeline Map — Signal Path & Hybrid Strategy Routing

**Written:** 2026-08-21 · **Engine SHA at time of trace:** `2d45be2` · **Branch:** `feature/edge-search-v2`
**Method:** live container logs + running HTTP endpoints + source read. Every claim below carries a `file:line`
or a captured runtime artifact. Nothing here is inferred from documentation.

> Phase 0 deliverable of the Hybrid Strategy Routing repair mission. Phases 1–4 must reference this file.

---

## 0. Root cause (stated up front)

**The zeros originate in `services/trading-engine/app/auto_trader.py:977-979` because the hybrid router is only
invoked when `strategy_mode == StrategyMode.HYBRID`, and the deployed engine runs `strategy_mode = ensemble`.
The router object is still constructed at `:277` and its banner is still printed unconditionally at `:659`,
which is why the panel presents as "Live" while its counters are structurally, permanently zero.**

A **second, independent** gate would keep the counters at zero even if the router did run:
`auto_trader.py:4417-4418` only attaches `hybrid_strategy_stats` to the status payload when
`strategy_mode ∈ {RESEARCH, HYBRID}`. In `ensemble` mode the key is **absent from the JSON entirely** — the
frontend's `status.hybrid_strategy_stats || {}` (`HybridStrategyPanel.jsx:32`) collapses that absence to an
empty object, and `hybrid.trend_pct || 0` (`:35`) renders the missing key as a truthful-looking `0.0%`.

The user's hypothesis — *"ensemble mode short-circuits the hybrid router, so the counters are structurally
zero"* — is **CONFIRMED**. See §4 for the evidence.

### The panel's internal contradiction, explained

| Panel line | Actual source | Why it disagrees |
|---|---|---|
| `Current Market: TRENDING` | `status.regime_detector_stats.regime_distribution`, summed in the JSX fallback at `HybridStrategyPanel.jsx:52-74` | Regime detection runs on **every** path, including ensemble — it is a confidence *modifier*, not a router |
| `Active Strategy: Ensemble (RSI + Multi-Indicator + Mean-Rev)` | **frontend string literal** `HybridStrategyPanel.jsx:86`, keyed off `status.strategy_mode` = `"ensemble"` | The backend sends only the token `"ensemble"`; the parenthetical leg list exists nowhere in the backend |
| `Trend-Following 0.0% — 0 signals routed` | `hybrid_strategy_stats.trend_pct` / `.trend_signals` — **key not emitted in ensemble mode** | Router never called (`:977`) **and** stats never serialized (`:4417`) |
| `Total Routing Decisions: 0` | `hybrid_strategy_stats.total_signals` — same | same |
| `[Live]` pulse dot | **hardcoded literal** `HybridStrategyPanel.jsx:118-119` | Rendered independently of query state; it is not a liveness signal at all |

Note: the key `total_routing_decisions` / `totalRoutingDecisions` **does not exist anywhere in the repo**.
"Total Routing Decisions" is UI text over the backend field `total_signals`. There is **no snake/camel mismatch**
on this path — every field the component reads is snake_case and matches the backend exactly.

---

## 1. The full signal path (deployed `ensemble` mode)

```
Bybit mainnet REST/WS
  └─ bybit-connector :8001
       └─ market-data-service :8002 ──ingest──> TimescaleDB (klines, tickers)   [the DB *is* the cache]
            └─ technical-analysis :8004  — indicator computation + Phase-1 aggregation pipeline
                 │  GET /api/v1/indicators/adx/{symbol}?interval=240&period=14&limit=100
                 └─ trading-engine :8005 — app/auto_trader.py, 30 s loop
                      ├─ STEP 2 dispatch          auto_trader.py:974-985   ← strategy_mode switch
                      │    ├─ RESEARCH  → _check_and_trade_research
                      │    ├─ HYBRID    → _check_and_trade_hybrid   :1017   ← ROUTER LIVES HERE, NOT REACHED
                      │    ├─ ENSEMBLE  → _check_and_trade_ensemble :4556   ← THIS IS WHAT RUNS
                      │    └─ else      → _check_and_trade
                      └─ paper execution (PAPER_TRADING_MODE=true)
```

### 1a. Inside `technical-analysis` — the Phase-1 aggregation pipeline

Observed live, in order, from container logs (`docker logs crypto-bot-trading`, module names are engine-side
mirrors of the aggregation package):

| Stage | Module | Live log line (verbatim, 2026-08-21 19:22:53) |
|---|---|---|
| Vote | `app.aggregation.voter` | `Filtered voting indicators: 9/11` · `Voting Results: score=+0.49, BUY=6, SELL=2, HOLD=1, consensus=6/9, total_weight=9.5` |
| Preliminary | `app.aggregation.voter` | `Preliminary: BUY (score: +0.49, conf: 0.49)` |
| Agreement | `app.aggregation.aggregator_core` | `Preliminary (agreement): BUY (score: +0.49, conf: 0.66)` |
| **Gatekeeper** | `app.aggregation.gatekeeper` | `Trend Filter: BULLISH (confidence: 0.68)` · `PASSED: BUY aligned with BULLISH trend` |
| **Validator** | `app.aggregation.validator` | `✓ Volume MODERATE: MODERATE - Minor penalty (0.9x)` · `📉 Confidence adjusted: 0.66 → 0.59 (×0.9)` |
| **Regime** | `app.aggregation.market_regime` | `Market Regime for ADAUSDT: STRONG_TREND (ADX: 58.0, Dir: BULLISH, Modifier: 1.20x)` |
| Regime apply | `app.aggregation.aggregator_core` | `Trend-aligned signal boosted: STRONG_TREND (x1.20)` |
| Diversity | `app.aggregation.voter` | `Category diversity OK: 3 categories agree (MOMENTUM, TREND, VOLATILITY)` |
| **ATR stops** | `app.aggregation.aggregator_core` | `ATR Dynamic Stops: SL=0.20, TP=0.25` |
| Final | `app.aggregation.aggregator_core` | `Final Signal: BUY (score: +0.49, conf: 0.71, consensus: 6/9)` |
| Multi-TF | `app.aggregation.multi_timeframe` | `Alignment: WEAK` · `Confidence modifier: 0.90x` · `Confidence: 0.43 -> 0.39` |
| **Ensemble** | `app.strategies.multi_strategy_ensemble` | `[ENSEMBLE] HOLD — no legs fired. agg_action=HOLD agg_conf=0.39` |

**Critical structural fact:** the market regime is consumed here as a *confidence multiplier*
(`0.80x` ranging / `1.20x` strong-trend). It **does not select a strategy**. There is no routing decision
anywhere on the deployed path.

### 1b. Inside `trading-engine` — the ensemble entry path

`_check_and_trade_ensemble` (`auto_trader.py:4556`), in execution order:

| # | Step | Location |
|---|---|---|
| 1 | `total_signals_checked += 1`; risk-manager halt check | `:4568-4572` |
| 2 | `aggregator.get_trading_signal_multi_timeframe(symbol, primary_interval, ["15", interval, "240"])` | `:4574-4579` |
| 3 | Extract `current_price` from any indicator's `metadata["current_price"]` | `:4583-4593` |
| 4 | `paper_engine.get_balance()` → capital | `:4595-4596` |
| 5 | `ensemble.generate_signal(base_signal, current_price, capital)` | `:4598-4601` |
| 6 | Duplicate-position check | `:4609-4612` |
| 7 | `_check_symbol_cooldown` (post-SL re-entry) | `:4620-4625` |
| 8 | **`_ensemble_passes_signal_gates`** — confidence + side gates | `:4634` |
| 9 | `_claim_open_slot` (race-safe per-symbol claim) | `:4644` |
| 10 | `_check_daily_trade_limit` | `:4648` |
| 11 | `_ensemble_stops_are_consistent` (inverted-stop reject, pre-fill) | `:4674-4691` |
| 12 | Portfolio-heat `can_open_trade(...)` — stop-distance based `proposed_risk_pct` | `:4658-4672` |
| 13 | Paper execution | downstream |

**Step 2 is the hook point for the router-as-observer design (§6):** `base_signal.indicators` is exactly the
`Dict[str, IndicatorSignal]` that `HybridStrategyRouter.detect_regime()` expects, and it is confirmed to
contain a live `ADX` leg (see §3).

---

## 2. The router itself — `hybrid_strategy_router.py`

`services/trading-engine/app/strategies/hybrid_strategy_router.py` (269 lines).

| Element | Line | Detail |
|---|---|---|
| `class MarketRegime(Enum)` | `:31-37` | `TRENDING` / `RANGING` / `UNKNOWN` |
| `class HybridStrategyRouter` | `:40` | |
| `__init__` | `:49-66` | builds `ResearchOptimizedStrategy()` + `MeanReversionStrategy()` |
| **`self.ADX_TRENDING_THRESHOLD = 25.0`** | **`:56`** | **HARDCODED — not read from config/env. Mission constraint: must move to config.** |
| Counters `total_signals`, `trend_signals`, `mean_reversion_signals` | `:59-61` | plain instance ints |
| `detect_regime()` | `:68-137` | reads `indicators["ADX"].value`, falls back to `.metadata["adx"]`, then legacy `ATR.metadata["adx"]` |
| ADX branch | `:100-112` | `>= 25.0 → TRENDING`, else `RANGING` |
| No-ADX fallback | `:114-136` | counts EMA/SMA/ICHIMOKU/TREND_FILTER legs with `confidence > 0.5`; `>= 2 → TRENDING` |
| `generate_signal()` | `:139-208` | `self.total_signals += 1` at `:161` — **the only increment site for the panel's denominator** |
| trend branch increment | `:171` | `self.trend_signals += 1` |
| mean-rev branch increment | `:187` | `self.mean_reversion_signals += 1` |
| `_convert_mean_reversion_to_trade_setup()` | `:210-251` | |
| `get_stats()` | `:253-269` | returns the exact 5 keys the panel reads; guards `total_signals == 0` → all-zero dict (no divide-by-zero) |

**Counter storage:** plain Python instance attributes on `AutoTrader.hybrid_strategy`, and `AutoTrader` is a
process-level singleton (`get_auto_trader()`, `auto_trader.py:5142-5145`). They are **not** per-request, **not**
Redis, **not** Postgres, **not** Prometheus. Storage lifetime is therefore *not* the bug — the counters would
survive polling fine. They are zero because `generate_signal()` is never called. They *are* lost on container
restart, which is a separate durability issue (see FINDINGS).

**Divide-by-zero guard:** `get_stats():254-261` returns zeros when `total_signals == 0` — correct, and not
masking anything today. The percentages at `:266-268` use a genuinely non-zero denominator.

---

## 3. Where ADX comes from (two distinct call sites — verified to agree)

| Consumer | Source | Live values observed 2026-08-21 |
|---|---|---|
| `app.aggregation.market_regime` (regime modifier, runs today) | HTTP `GET technical-analysis:8004/api/v1/indicators/adx/{symbol}?interval=240&period=14&limit=100` | ADAUSDT 19.6 / 52.1 / 58.0 · BNBUSDT 54.9 / 55.5 |
| `HybridStrategyRouter.detect_regime()` (does not run today) | `indicators["ADX"]` off the aggregator dict — `.value`, then `.metadata["adx"]` | BTCUSDT `"ADX":{"signal":"BUY","confidence":0.73,"value":61.63,"metadata":{"adx":61.63,...}}` — captured from `GET /api/dashboard/BTCUSDT` |

**The "always-NaN ADX" hypothesis is DEAD.** ADX is live, numeric, populated in both the aggregator dict and the
regime detector, and spans both sides of the 25.0 threshold (16.4 … 61.6 observed within one hour). The
`ADX >= 25` branch is reachable. A reference-implementation cross-check is still owed as a unit test
(Phase 4), but this is not the cause of the zeros.

---

## 4. Evidence: the router is never invoked

All captured 2026-08-21 against the running `crypto-bot-trading` container (up 2 h, isolation run started
16:58:46 UTC):

```
$ docker logs crypto-bot-trading 2>&1 | grep -iE 'StrategyMode='
2026-08-21 16:58:46,215 - app.auto_trader - INFO - AutoTrader initialized: symbols=5 pairs,
  interval=60, frequency=30s, Sizing=FIXED, MarketRegime=ENABLED, StrategyMode=ensemble
2026-08-21 16:58:46,215 - app.auto_trader - INFO - Hybrid Strategy: TREND-FOLLOWING + MEAN REVERSION (ADX threshold: 25.0)
```

```
$ docker logs crypto-bot-trading --since 180m 2>&1 | grep -c '\[HYBRID\]'
0
$ docker logs crypto-bot-trading --since 180m 2>&1 | grep -c '\[ENSEMBLE\]'
1179
```

```
$ curl -s localhost:8005/metrics | grep -iE 'rout|regime|hybrid|trend_follow|mean_rev'
(no output — 58 metric families exposed, none routing-related)
```

```
$ curl -s localhost:8000/openapi.json | jq -r '.paths|keys[]' | grep -iE 'rout|regime|hybrid'
(no output — no routing endpoint exists on the gateway)
```

The second line of the boot log is the trap: **`"Hybrid Strategy: TREND-FOLLOWING + MEAN REVERSION
(ADX threshold: 25.0)"` is printed unconditionally at `auto_trader.py:658-660`, regardless of
`strategy_mode`.** Combined with the hardcoded `[Live]` dot in the panel, the system asserts a subsystem is
active that has not executed once.

---

## 5. Frontend path

| Element | Location |
|---|---|
| Component | `frontend/src/components/HybridStrategyPanel.jsx` (197 lines) |
| Mount | `frontend/src/components/Dashboard.jsx:172` (imported `:13`) |
| Data hook | `HybridStrategyPanel.jsx:24-29` — `useQuery({queryKey:['trading-status'], queryFn:()=>tradingAPI.getStatus(), refetchInterval:5000, staleTime:4000})` |
| **No `useEffect` on this path** — no stale dependency array to blame | |
| Service fn | `frontend/src/services/api.js:102` — `getStatus: () => api.get('/trading/status')` |
| Axios instance | `api.js:9-15` — `baseURL:'/api'`, `timeout:20000`; interceptor `:46-47` unwraps `response.data` |
| Effective URL | `GET /api/trading/status` |
| Prod route | `frontend/nginx.conf:18-19` → api-gateway `services/api-gateway/app/main.py:1103-1110` → trading-engine `/api/v1/trading/status` |
| Engine route | `services/trading-engine/app/main.py:744-753` → `app/handlers/trading_control.py:97-121` → `{"success":true,"status":<AutoTrader.get_status()>,"timestamp":…}` |
| Dev route | `frontend/vite.config.js` proxies `/api/trading` → `localhost:8005` with rewrite to `/api/v1/trading`, **bypassing the gateway** |
| WebSocket | **not used for this panel.** `hooks/useGatewayWebSocket.js:95-111` only touches `['ticker'|'tickers'|'portfolio']` caches |
| Second consumer | `frontend/src/components/RegimeIndicator.jsx:18-80` polls the *same* endpoint under key `['trading-status-regime']`, also every 5 s |

### Fields the component reads (all snake_case, all matching the backend)

`status.hybrid_strategy_stats.{trend_pct, mean_reversion_pct, total_signals, trend_signals,
mean_reversion_signals}` · `status.regime_detector_stats.regime_distribution` · `status.regime_distribution`
· `status.strategy_mode`

### Undefined-masking defaults on this path

| Quote | Line |
|---|---|
| `const status = q.data?.status \|\| {}` | `:31` |
| `const hybrid = status.hybrid_strategy_stats \|\| {}` ← **masks the entire ensemble-mode absence** | `:32` |
| `const trendPct = hybrid.trend_pct \|\| 0` | `:35` |
| `const meanRevPct = hybrid.mean_reversion_pct \|\| 0` | `:36` |
| `const totalSignals = hybrid.total_signals \|\| 0` | `:37` |
| `…regime_detector_stats?.regime_distribution \|\| status.regime_distribution \|\| {}` | `:56-59` |
| `(s, k) => s + (dist[k] \|\| 0)` ×2 | `:62-63` |
| `{hybrid.trend_signals?.toLocaleString() \|\| 0} signals routed` | `:151` |
| `{hybrid.mean_reversion_signals?.toLocaleString() \|\| 0} signals routed` | `:167` |

The `TileState` empty-state guard **cannot fire**: `isEmpty={(d)=>!d||!d.status}` (`:103`), but
`trading_control.py:97` always returns a `status` key. The tile has no path to "no data yet".

### Frontend regime-key mismatch (separate defect)

`HybridStrategyPanel.jsx:60-61` buckets by:
```js
const trendingKeys = ['STRONG_TREND', 'TRENDING', 'WEAK_TREND']
const meanRevKeys  = ['MEAN_REVERTING', 'RANGING', 'RANGE_BOUND']
```
The backend enum (`services/trading-engine/app/aggregation/market_regime.py:52-57`) emits
`STRONG_TREND, TRENDING, WEAK_TREND, RANGING, VOLATILE, UNKNOWN`. So `MEAN_REVERTING` and `RANGE_BOUND` are
**dead keys**, and `VOLATILE` / `UNKNOWN` fall into neither bucket. The mean-reversion side of the ratio test
at `:65` is therefore systematically under-counted — which is part of why the tile reads `TRENDING`.

---

## 6. Architecture decision — how routing and ensemble compose

*(Recorded per mission §4. Decision authority: operator. Recorded here once chosen; see FINDINGS.md for the
open-question form until then.)*

Two candidates:

- **A — Router selects, ensemble votes within.** `detect_regime()` picks trend-following vs mean-reversion,
  and the ensemble's leg weights are re-scoped to the chosen regime. **This changes which trades are taken** —
  a live money-path behavior change, under a repo doctrine (CLAUDE.md §2) stating no strategy has demonstrated
  positive edge. Requires Phase-3 replay evidence *before* it ships.
  **Known blocker:** `hybrid_strategy_router.py:232-234` sizes mean-reversion entries at
  `0.10 + confidence * 0.10` → **10–20 % of capital**, i.e. up to **$20 on a $100 account**, against the
  ADR-010 paper cap of 10 % / $10. If the mean-reversion branch is ever allowed to emit orders, it emits
  above-cap sizes unless the engine's cap enforcement clamps or rejects them. Must be resolved before A ships.
- **B — Router runs as an observer on the ensemble path.** After `base_signal` is obtained
  (`auto_trader.py:4574-4579`), call regime detection and record the branch that *would* have been taken,
  plus the ADX value. The ensemble still decides. Counters become real and honest; **execution is unchanged**;
  the isolation-run and edge-doctrine risk is zero.

**Recommended sequencing: B first, then A only with Phase-3 replay evidence in hand.** The mission's own
non-negotiable — *"never loosen a filter without replay evidence that the additional signals it admits are net
positive on expectancy"* — makes A a post-evidence change, not a Phase-2 change. B alone satisfies
"the panel can never again be silently empty" and the Phase-4 regression guard.

---

## 7. Config surface (values as deployed)

| Key | Where | Value | Notes |
|---|---|---|---|
| `STRATEGY_MODE` | `docker-compose.unified.yml:686`, `docker-compose.headless.yml:298` | `${STRATEGY_MODE:-ensemble}` | **the switch that disables the router** |
| `strategy_mode` (pydantic default) | `services/trading-engine/app/config.py:310-313` | `standard` | disagrees with the compose default |
| `StrategyMode` fallback in factory | `auto_trader.py:5142-5143` | `StrategyMode.HYBRID` | third, silent default — `mode_map.get(..., HYBRID)` |
| `ADX_TRENDING_THRESHOLD` | `hybrid_strategy_router.py:56` | `25.0` | **hardcoded, no env key** |
| `enable_market_regime` | `auto_trader.py:190` | `True` | boot log confirms `MarketRegime=ENABLED` |
| `check_frequency` | boot log | `30 s` | `Waiting 30s until next check` |
| `interval` | boot log | `60` (1 h primary); multi-TF `["15","60","240"]` | |
| `min_signal_confidence` | ensemble gate, observed in logs | `0.30` | **currently the binding constraint — see §8** |
| Ensemble legs / weights | boot log 16:58:46 | `legs=[simple_rsi, multi_indicator, mean_reversion]`, `threshold=0.1`, `min_agreeing=1`, `weights={⅓,⅓,⅓}` | frozen ⅓ weights |

*(Gatekeeper / Validator / ATR / vote-distribution config values are enumerated in `docs/FUNNEL_REPORT.md`
once the filter-stack trace lands; this table covers only what the routing path itself depends on.)*

---

## 8. What the live logs already say about Phase 3

Captured over the 3.4 h since the current engine boot (2026-08-21 16:58 → 20:25 UTC):

| Ensemble outcome | Count |
|---|---|
| `HOLD — no legs fired` | 1013 |
| `ADAUSDT: SELL conf=27.61% size=10.00% legs={simple_rsi: SELL, mean_reversion: SELL}` | 84 |
| `HOLD — weighted score below threshold 0.1` | 3 |
| **Orders placed / filled / positions opened** | **0** |

Every one of the 84 emitted signals was rejected by:
```
[ENSEMBLE][GATE] ADAUSDT: confidence 0.2761 < min_signal_confidence 0.30 — rejecting
```

Observed aggregate confidences cluster at **0.16 / 0.27 / 0.39 / 0.40 / 0.41 / 0.64** under frozen ⅓ weights.
`min_signal_confidence = 0.30` therefore sits *just above* the mode of the reachable distribution — the same
shape of defect recorded in `.planning/evidence/forward_paper_test/prefer_maker_orders/ABANDONED.md`, where
`short_min_confidence = 0.70` sat above a structural ceiling of 0.60. **This is the binding constraint for
Phase 3, and it is measurable from logs before any replay is run.**

### Replay-window floor (mandatory)

TimescaleDB holds mixed testnet/mainnet history; the mainnet flip was **2026-04-25** (CLAUDE.md §10). Any
replay drawn from "the largest available window" straddles that boundary and will silently poison both the ATR
distribution and the rejection funnel with testnet prices. **All Phase-3 replays must be floored at
2026-04-25**, and the floor must be stated in `docs/FUNNEL_REPORT.md`.

---

## 9. Runtime constraint at time of writing

Isolation run `20260821T165830Z` (`prefer_maker_orders`, launched 2026-08-21 16:58 UTC, harvest due
2026-08-28) is in flight against engine SHA `2d45be2`. Per
`.planning/evidence/forward_paper_test/prefer_maker_orders/ABANDONED.md`, a mid-window trading-engine redeploy
invalidates the run and reverts the `PREFER_MAKER_ORDERS` override to compose defaults.

By the measurement in §8 the window is **already producing no evidence** — 0 fills in 3.4 h, for the same
reason the previous run was abandoned. Redeploy authorization is an operator decision, not an engineering one.

**Blocked on that authorization:** the funnel API surface, counter wiring in the deployed container, and live
UI verification.
**Not blocked:** this map, the root-cause statement, host-run replay/measurement under `backtesting/**`, the
ADX reference unit test, and the synthetic-series integration tests.
