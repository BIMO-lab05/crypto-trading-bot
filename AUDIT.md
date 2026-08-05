# AUDIT.md — Phase 0 Reconnaissance

**Date:** 2026-08-04 · **Mode:** read-only (no code, config, or container state was changed; this file and a progress.md entry are the only writes)
**Method:** five parallel investigation agents (architecture trace, capital audit, Docker diagnosis, docs triage, trade forensics) + direct venue-spec queries against the running bybit-connector. Every claim below carries file:line or pasted command/SQL output in the underlying reports; unknowns are marked **unverified**.
**Fee/slippage convention used throughout:** "modelled" = the engine's own 0.1%/side commission + 5–10 bps/side slippage; "Bybit est." = real Bybit linear-perp taker 0.055%/side (estimate, not recorded). Funding is **not modelled anywhere** — all P&L figures are gross of funding.

---

## 0. Executive summary — the four problems, answered

| # | Problem as reported | What the evidence says |
|---|---|---|
| 1 | "Capital sizing is wrong; the $10k keeps coming back" | Core config is **correct at $100** (verified live in container env). The symptom has three verified mechanisms: **frontend $10k fallbacks that fire only when an API call fails** (intermittent by design), **portfolio-manager receiving zero capital env vars from compose** (edits structurally can't land), and **a hardcoded `* 10000` inside live order routing** (`auto_trader.py:1851`). Separately — and worse — the *sizing math* is broken independently of the account constant: **leverage multiplies the 10% per-trade cap back up to 100% of balance per trade** (§6). |
| 2 | "Containers don't come up cleanly or stay up" | Stack is up 14/14, but **risk-metrics is a zombie**: `Up` status, serving nothing, restart policy can't fire. Cause proven: WSL bind-mount race hands a random container an empty root-owned **tmpfs** instead of the bind; a module-level `logging.FileHandler` then kills both uvicorn workers at import. The victim is **random per boot** — that's why it felt unexplainable. Second mechanism: **running containers predate the current compose file** (`docker start` never re-reads config), so compose edits silently don't take effect. |
| 3 | "Repo disorganized, docs contradictory" | Largely **already fixed on 2026-08-03** — a 73-file archive batch executed and verified. Residue: ~9 in-place text corrections, one index pointing at archived content, and a fabricated-looking backtest claim that migrated from an archived doc into application code. No moves needed. |
| 4 | "Paper trading loses money — strategy, execution, costs, or data?" | **Execution layer, confirmed; costs second; data refuted; strategy unverifiable.** Only 12 closed positions exist (not thousands). All losses came from stop-loss exits; every stop exit carries a **deterministic 0.5% penalty** from a fill-model bug; positions are sized at **~100% of balance each** (10x over cap); reported P&L **excludes fees**; partial exits **don't survive restarts** (one position's P&L overstated $1.70); a 67-hour engine outage caused a churn event. The measuring instrument is broken in six confirmed ways, several individually larger than any plausible edge. "Is the strategy bad?" cannot be answered until the instrument is fixed. |

**The single most important sentence in this audit:** the paper account is down ~$6.70–$7.54 net (depending on fee assumption) on 12 trades, and none of that loss is attributable to the strategy yet, because sizing, stops, and P&L accounting are all mechanically defective.

---

## 1. Architecture as it actually is

### 1.1 Runtime path (verified by import-following, not grep)

| Hop | What | Where (file:line) | Transport |
|---|---|---|---|
| 0 | Candle ingest: APScheduler jobs (ticker 5min, kline 5min offset +2, hourly backup) | `services/market-data-service/app/scheduler.py:269-330`, jobs at `:170-242` | scheduled, in-process |
| 0a | Fetch goes through bybit-connector, not direct to Bybit | `market-data-service/app/fetcher.py:70,79-85` → `bybit-connector/app/bybit_rest_client.py:59-66` | HTTP |
| 0b | Mainnet confirmed: `bybit_testnet` default False → `https://api.bybit.com` | `bybit-connector/app/config.py:32-34,288-292` | — |
| 0c | Persist to TimescaleDB hypertable `klines` (db `market_data`) | `market-data-service/app/repository.py:19-94`, `app/database.py:137` | SQL |
| 1 | Auto-trader loop, 30s interval; gated by `auto_trading_enabled` then `EMERGENCY_STOP` file | `trading-engine/app/main.py:311-354`; loop `app/auto_trader.py:852-999` | in-process task |
| 1a | Live mode: `strategy_mode` default `"standard"` → `_check_and_trade`, NOT hybrid/grid/research | `trading-engine/app/config.py:282-284`, `auto_trader.py:969,4408-4425` | — |
| 2 | Signal: aggregator makes **13 separate HTTP GETs per signal check** (one per indicator, no batching) | `trading-engine/app/signal_aggregator.py:49-52,82-653` | HTTP → :8004 |
| 2a | technical-analysis pulls candles over HTTP from market-data (never reads TimescaleDB directly) | `technical-analysis/app/fetcher.py:56,115` | HTTP → :8002 |
| 3 | Risk gates: daily-loss halt → confidence gate → `_execute_trade` | `auto_trader.py:1106-1240`; `risk_manager.py:77-84` (unit conversion correct here) | in-process |
| 4 | Sizing: FIXED method, always emits 10% | `auto_trader.py:3677,3728` → `position_sizing.py:158-162,81-84` | in-process |
| 4a | Per-trade cap clamps **down** (never up), 2% forced if LIVE | `auto_trader.py:3783-3797` | — |
| 4b | Min-notional gate: **no-op in paper mode** — `if trading_mode != "LIVE": return True` | `auto_trader.py:1513-1646`, early-out `:1551-1552` (deliberate, docstring `:1539-1544`) | — |
| 5 | Paper fill: slippage (adverse per side) + 0.1%/side commission, both legs | `paper_trading.py:71-89,202,249,251-252,309-310`; `paper_slippage.py:236-267` | in-process |
| 6 | P&L: computed at close (gross — see §6), persisted to plain Postgres `trades`/`positions` (db `trading_engine`) | `paper_trading.py:316-324,353-461`; `database/models.py:89-117,181-211` | SQL |
| 7 | portfolio-manager **pulls** (never pushed to): mirrors engine positions/performance every 60s + on-demand | `portfolio-manager/app/services/portfolio_manager.py:168-271`; `scheduler/performance_snapshot.py:127-130` | HTTP → :8005 |

**Warning (ensemble path):** the compose file sets `STRATEGY_MODE=ensemble` (docker-compose.unified.yml), and the observed trades came through the ensemble entry path at `auto_trader.py:4211-4258` — which applies **no exposure gate, no position-size gate, and no min-notional gate** (only an "already have a position on this symbol" check). The `_check_and_trade` gates in hops 3–4b exist but the ensemble path bypasses most of them. See §6/H1.

### 1.2 Event bus: CONFIRMED dead

RabbitMQ deployed (`docker-compose.unified.yml:150-167`); `pika==1.3.2` in 4 services' requirements; **zero `import pika` anywhere**. Only AMQP code is a health probe (`trading-engine/app/core/health.py:406-449`) that imports `aio_pika` — which is in **no** requirements.txt — so it permanently lands in "DEGRADED (optional)". No service receives an AMQP URL; bybit-connector's `rabbitmq_host` defaults to `localhost`, not the compose service name. The mesh is synchronous REST, full stop (matches ADR-016).

### 1.3 Live vs dormant modules (dead-code inventory for Phase 3)

- **4 aggregator modules exist; 1 live:** `app/signal_aggregator.py` (live) vs `app/aggregation/aggregator_core.py`, `app/orchestration/signal_aggregator.py`, `app/strategies/aggregator.py` (instantiated for stats/logging, not on the execution path).
- **3 position sizers exist; 1 live:** `app/position_sizing.py` (live) vs `app/trading_enhancements/advanced_position_sizing.py`, kelly variants (see §3 for the kelly caveat).
- **Two separate daily-loss breakers**, both wired, separate state: `RiskManager.should_halt_trading()` (`risk_manager.py:77-84`) and loop-level `KillSwitch` (`trading_enhancements/kill_switch.py`, checked `auto_trader.py:919`). Not necessarily a bug; drift risk.
- **Second bookkeeping path:** portfolio-manager manual buy/sell asset tracking with its own realized-P&L calc (`portfolio_manager.py:475-505`, exposed via gateway `/api/portfolio/buy|sell`). Whether the auto-trader path ever touches it: **unverified**.
- `atr_stops.py` (373 lines): exists, **unwired** (§6f).
- `paper_trading.py:476 can_open_position` → `risk_manager.check_position_limits`: **not reachable from the ensemble entry path** (whether dead everywhere is unverified, not load-bearing).

### 1.4 Docs vs code disagreements (all outstanding items)

| Doc (file:line) | Claim | Reality (file:line) | Severity |
|---|---|---|---|
| `services/portfolio-manager/README.md:103-104,146,356` | `"cash_balance": "10000.0"`, `INITIAL_CAPITAL=10000.0` examples | default `100.0` (`portfolio-manager/app/config.py:51-52`) | P0 (misleads agents auditing capital) |
| `services/portfolio-manager/docs/PERFORMANCE_TRACKING.md:114,134` | `"portfolio_value": "10000.00"` | same | P0 |
| `README.md:13` (root) | RabbitMQ listed as live "(events)" component | nothing wires AMQP (ADR-016; §1.2) | P1 |
| `docs/operations/DOCKER_REFERENCE.md:621,630,636,696`; `docs/operations/RUNBOOK.md:664`; `docs/deploy/KUBERNETES_RUNBOOK.md:775-776` | plain `docker-compose.yml` presented as the base file | unified is canonical (ADR-009); plain file can't even boot (§5.4) | P1 |
| `docs/operations/ALERTING_GUIDE.md:144,146`; `MONITORING_GUIDE.md:214-215,671,678`; `infrastructure/monitoring/README.md:461,516`; `scripts/README.md:269,338,393,431`; `services/ml-retraining-service/docs/REENABLE_ML_RUNBOOK.md:216` | 5% daily-loss threshold | 12% per ADR-028 (`trading-engine/app/config.py:364-365`) | P2 |
| `docs/README.md:18-19` | index maps `docs/ml/`, `docs/strategy/` to content | both emptied by the 2026-08-03 archive batch (`c027389`) — index never updated | P2 |
| `services/trading-engine/README.md:220-232` | SQZMOM whitelist incl. DOGEUSDT, "disabled: ADAUSDT" | `sqzmom_config.py:11,50-53` default `["SOLUSDT","BNBUSDT","ADAUSDT"]` | P3 (SQZMOM not live) |
| `database/migrations/005_seed_data.sql` (NOTICE text) | log says "$10,000 balance" | the INSERT two lines above is correctly `100.00` | P3 (text only) |
| (route prefix, for future doc writers) | docs cite either `/api/...` or `/api/v1/...` alone | both true at once: gateway external surface has no v1 (`api-gateway/app/main.py:853`, 79 routes); gateway proxies to downstream `/api/v1/...` (`:861-865`; `trading-engine/app/main.py:573`) | context |
| **Code, not doc:** `trading-engine/app/main.py:1776`, `strategies/sqzmom_strategy_integration.py:514` | hardcodes `"DOGEUSDT": "+630% (28% WR, 5.41 Sharpe)"` — the same fabricated-looking figure whose standalone doc was archived as P0 on 2026-08-03 | no supporting artifact exists in the repo | P1 (unsourced performance claim living in app code) |

---

## 2. Capital audit — every definition, and which value actually runs

### 2.1 Effective values in the running system (verified live)

`docker exec crypto-bot-trading printenv` (non-secret keys only), matching `docker compose config` exactly:
`PAPER_INITIAL_BALANCE=100.0`, `MAX_RISK_PER_TRADE=0.10`, `MAX_DAILY_LOSS_PCT=12.0`, `MAX_POSITION_SIZE_PCT=10.0`, `MAX_TOTAL_EXPOSURE_PCT=80.0`, `LEVERAGE_ENABLED=true`, `DEFAULT_LEVERAGE=10.0`, `MAX_LEVERAGE=20.0`.

`shared/account.py` ↔ `services/trading-engine/app/config.py` are in sync at $100. **The core config is not the problem.** The boot log confirms `$100.00 capital`. What's wrong is what the code *does* with these values (§6/H1) and the fallback sites below.

### 2.2 Why "I keep changing it and it keeps getting ignored" — three verified mechanisms, ranked

1. **Frontend fallbacks hardcode $10,000 and only activate on API failure or partial data** — so the dashboard intermittently flips to $10k-based numbers, then "heals." Best match for the symptom. Sites: `frontend/src/hooks/usePerformanceMetrics.js:283` (`calculateEquityCurve(trades, 10000)` in the `!backendQuery.data || isError` branch), `PerformanceDashboard.jsx:302` (`: 10000` when curve empty), `EquityCurveChart.jsx:211` (`initialEquity = 10000` default prop), `useChartData.js:112` (+129,142,145,159,171,504,505,509). The *primary* balance path was already fixed to `PAPER_DEFAULT_BALANCE = 100` (`utils/balance.js`, `usePerformanceMetrics.js:126-131`) — partial fix, hence intermittent.
2. **portfolio-manager receives no capital/risk env vars at all** — `docker-compose.unified.yml:503-551` `environment:` block has no `INITIAL_CAPITAL`; live printenv confirms empty. Correct today only via the pydantic Field default (`config.py:51-55` = 100.0). Any `.env` edit aimed at this service structurally cannot land. Portfolio object is also rebuilt in-memory each restart (`portfolio_manager.py:54-63`) — never persisted.
3. **`auto_trader.py:1851`: `position_value_estimate = entry_price * position_size_pct * 10000`** — hardcoded $10k assumption inside LIMIT-vs-MARKET routing on every paper trade. Changing `PAPER_INITIAL_BALANCE` has zero effect on it. Bonus defect: the formula is dimensionally wrong (price × fraction, no quantity term) — re-derive, don't just swap the constant.

Fourth mechanism, **dormant landmine, not the active symptom**: the production `portfolios` row (`portfolio_id='paper_trading'`) still holds `initial_balance=10000.00000000` (seeded 2026-04-27; evidenced by `.planning/audits/snapshots/2026-07-31-pre-portbind.sql:25`) while `total_value=100.0` in the same row. `repositories.py:355-407 get_or_create` never repairs existing rows. **No live handler reads that column today** (verified by handler sweep; `cash_balance=$78.78` in the snapshot is consistent with a $100 start) — but any future consumer computing return-on-capital from it is 100x wrong.

### 2.3 Migration split-brain (P0 for fresh deploys)

Two migration directories disagree on the `portfolios` seed:
- `infrastructure/migrations/001_initial_schema.sql:225-235` — seeds `initial_balance=10000.00, cash_balance=10000.00, total_value=10000.00` — **still wrong today**, and the live row matches it (this is the one that apparently ran).
- `database/migrations/005_seed_data.sql` + `database/schema.sql:528` — correctly seed `100.00`.
A fresh environment stood up through `infrastructure/migrations/` re-seeds $10,000 from scratch. No statement anywhere of which directory is authoritative. **Decision needed.**

### 2.4 Min-notional handling: REJECT correctly implemented; one dormant violation

- Primary path `_passes_min_notional` (`auto_trader.py:1513-1644`): rejects below `min_order_qty`/`min_notional` with labeled reason + metric, never rounds up. Design intent stated in `services/instruments_cache.py` docstring ("No auto-upround… auto-uprounding silently breaches the cap"). Specs **fetched live from Bybit** (1h TTL), not hardcoded. Fails open only if the connector is unreachable (documented tradeoff).
- **But:** the gate is a no-op in paper mode (§1.1 hop 4b) and isn't called on the ensemble path at all (only at `:2040` and `:3813`).
- **Dormant clamp-up violation:** `strategies/grid_trading_strategy_v2.py:1360-1362` — `max(MIN_POSITION_VALUE_USD, ...)` with hardcoded `10.0` (line 88) silently turns a $2 trade into a $10 one. No live caller found (static grep; final check before deprioritizing).

### 2.5 The long tail (fix in Phase 1, none of these size live orders)

P1 — reachable analytics/backtest/handler defaults: `handlers/backtest.py:45,375,539`; `handlers/grid_trading.py:78,93`; `handlers/risk_kelly.py:162,182`; `handlers/performance_dashboard.py:70` (currently inert); `backtesting/backtest_engine.py:129,526`; `analytics/attribution.py:380,1386,1460` (incl. `or 10000.0` — the falsy-fallback pattern, fires on 0 too); `analytics/advanced_metrics.py:724,2717,2852`; `main.py:1444-1445` (Query default 10000 AND the endpoint is broken — kwarg mismatch with `handlers/statistical_arbitrage.py:288`, every call TypeErrors); `models/stat_arb_models.py:178,181,197`; `scripts/monitor.py:198`; `scripts/validate_risk_limits.py:181` (`.get("initial_balance", 10000)` — could mask real breaches).

Needs a call-site check before batch-fixing (pattern-classified, not individually verified): ~14 strategy constructor defaults (`mean_reversion_strategy.py:104`, `pairs_trading.py:259`, `triangular_arbitrage.py:331,497`, `funding_rate_arbitrage.py:252`, `hybrid_strategy_router.py:141`, `momentum_breakout_strategy.py:300,1239,1473`, `support_resistance_strategy.py:201,783,1175`, `trend_following_strategy.py:345,1295,1584`, `mean_reversion.py:152`, `research_optimized_strategy.py:883`) and `risk/kelly_position_sizing.py:829` (`capital: float = 10000` — the Kelly sizer IS wired into orchestration; whether the default is ever reached is **unverified**).

Unverified whether deployed: `scripts/automated_trading_loop.py:336` and `..._with_notifications.py:527` hardcode `initial_balance = 10000.0` feeding a daily-loss calc — if these standalone scripts are ever what runs, their breaker is 100x too lenient. Check the deployment entrypoint.

Confirmed non-defects (docstrings, already-fixed sites, bps/timeouts/sample-counts) are catalogued in the capital agent's report; notable already-fixed: `managers/statistical_arbitrage_manager.py:109-115`, `risk-metrics-service` B2 fix (`require_total_value()` raises 503 instead of defaulting).

Gap: `.env.example` / `.env.production.example` / `.env.test.example` drift table — **unverified** (agent permission profile blocked reads even of templates; settle by pasting the sizing keys or re-running with access).

---

## 3. The $100 feasibility question — with venue numbers

Live specs fetched 2026-08-04 from bybit-connector (`/api/v1/market/instruments-info`, category=linear). Prices are from the 2026-08-04 fills (recompute before relying). All five symbols: `minNotionalValue = 5` USDT; the binding constraint on majors is **min order quantity**, not min notional. Funding interval 480 min (8h) on all five.

| Symbol | minOrderQty | qtyStep | tickSize | Price (08-04) | **Smallest legal position** | % of $100 |
|---|---|---|---|---|---|---|
| BTCUSDT | 0.001 | 0.001 | 0.10 | ~$62,551 | **$62.55** | **62.6%** |
| ETHUSDT | 0.01 | 0.01 | 0.01 | ~$1,836 | **$18.36** | **18.4%** |
| SOLUSDT | 0.1 | 0.1 | 0.010 | ~$71.0 | **$7.10** | 7.1% |
| BNBUSDT | 0.01 | 0.01 | 0.10 | ~$576 | **$5.76** | 5.8% |
| ADAUSDT | 1 | 1 | 0.0001 | ~$0.169 | $0.17 → **$5.00** (min-notional floor, ≈30 ADA) | 5.0% |

**Consequences, stated plainly:**

- **Under the 10% per-trade cap ($10 notional at 1x), only SOL, BNB, ADA are legally tradeable. ETH requires 18.4% of the account; BTC requires 62.6%.** The venue forces an effective per-trade exposure floor of 5–7.1% on the tradeable three. Quantity granularity is equally brutal: SOL positions can only be $7.10, $14.20, $21.30…
- **Round-trip cost per trade:** Bybit taker 0.055%×2 = 0.11% of notional; engine-modelled slippage 5–10 bps/side adds 0.10–0.20%. Total ≈ **0.21–0.31% of notional** ≈ **$0.021–0.031 per $10 trade = 0.02–0.03% of the account**. Funding (unmodelled) adds ~0.01%/8h typical — at the observed ~67h median hold, ≈0.08% of notional. At correct sizing, **fees are not the binding constraint; venue minimums and stop geometry are.**
- **Is risking 1% ($1) possible?** Risk = notional × stop distance. At a sane 2% stop, $1 of risk needs **$50 notional = 50% of the account** — 5x over the 10% cap. Within the cap ($10 notional, 2% stop) max risk per trade is **$0.20 = 0.2% of the account**. So: 1% risk per trade is **not achievable within the current cap at any sane stop distance** — the system at $100 is structurally a 0.1–0.3%-risk-per-trade system on three symbols. (Leverage can stretch notional above margin — that is exactly the H1 bug pattern; using it deliberately to reach 1% risk means 5x leverage and liquidation risk, a decision, not a default.)
- **LIVE at $100: mechanically impossible, now with venue proof.** The LIVE cap of 2% caps position value at $2 — below the $5 min-notional floor of every symbol, before even reaching the min-qty walls. Confirms CLAUDE.md §1; no edge claim can change this arithmetic.
- **Statistical consequence:** at ~$0.20 realistic risk per trade, detecting an edge needs hundreds of trades just to overcome noise; the current dataset is 12. Expectation management: paper trading at $100 scale is a correctness test, not an income test.

---

## 4. Container diagnosis

State at 2026-08-04 ~18:00Z: 14/14 running, 0 restarts, 0 OOM kills, all started 17:30:43Z. `docker context` = default; 124 GB free on /mnt/d. Profile-gated (not running, by design): prometheus, grafana, ml-prediction, sentiment-analysis. **`ml-retraining-service` is defined in no compose file** — docs list it; it cannot run.

### 4.1 The one failure: risk-metrics zombie (mechanism proven)

- Same container ran healthy 2h47m, broke across a 3-second stop/start — eliminates code/image/env hypotheses.
- Crash: both uvicorn workers die at import — `PermissionError: [Errno 13] Permission denied: '/app/logs/service.log'` (`risk-metrics-service/app/main.py:65`, module-level `logging.FileHandler`). Uvicorn parent (PID 1) survives → container stays `Up` → `restart: unless-stopped` never fires → **zombie with FailingStreak 110+**.
- Root cause: compose declares a bind mount; inside the container `/proc/mounts` shows `/app/logs` is an **empty root-owned tmpfs** (the WSL bind-mount race). `docker inspect` reports a healthy bind **either way — wrong instrument for verifying a fix; use `grep " /app/logs " /proc/mounts` (must say `9p`, not `tmpfs`)**.
- **All 11 Python services share the identical pattern** (bind + uid 999 + world-writable-via-drvfs + FileHandler): which service breaks is **random per boot**. (Stack-wide claim is inferred from the shared pattern, not observed history — flagged as such.)
- Impact: all 8 `/api/risk/*` routes → 503; gateway correctly reports `"degraded"`.

### 4.2 Config-drift mechanisms (the "my changes get ignored" of Docker)

- Compose file edited 16:59:31Z; containers created 14:43:34Z; started 17:30:43Z. **`docker start` does not re-read compose — every edit in that file is currently not in effect in any running container.** After compose edits: `up -d` (recreates), never `start`/`restart`.
- Container provenance spans 4 dates and 2 platforms: rabbitmq (May 21), tournament-harness (May 22), frontend + notification-service (**created by Windows-side Docker Desktop**, July 29 — different drvfs backend, hence different mount behavior), the other 10 (Aug 4). Compose reuses containers whose config hash matches; `up -d` alone does not guarantee the stack matches the file.

### 4.3 Stray `docker-compose.yml` is a live hazard, not just incomplete

Zero infra services (references DB hostnames it never defines — cannot boot standalone); port collision (`bybit-connector` `SERVICE_PORT=8002` = market-data's); no logging limits; and **pre-ADR risk values**: `MAX_RISK_PER_TRADE=0.05`, `MAX_DAILY_LOSS_PCT=5.0`, `MAX_POSITION_SIZE_PCT=8.0`, `MAX_TOTAL_EXPOSURE_PCT=70.0`, `MAX_LEVERAGE=10.0`, `STRATEGY_MODE=hybrid`. A bare `docker compose up` against an **armed auto-trader** silently swaps live risk parameters.

### 4.4 Healthcheck / dependency audit

- All app healthchecks are `curl -f <own>/health` — status-code-only. **api-gateway returns HTTP 200 with body `"status":"degraded"`**, and counts profile-disabled ml/sentiment as failures — in the default profile set it can **never** report healthy; the check carries no signal in either direction.
- prometheus + grafana: **no healthcheck at all** in the canonical file; grafana waits on prometheus with bare `service_started`. (The deprecated compose has proper ones — canonical file regressed.)
- Dependency chain is 5 deep (bybit → market-data → ta → trading-engine → risk-metrics) with 40s start_periods and 30s intervals: **~3.5–4 min cold boot before risk-metrics/frontend go green**. "Doesn't come up cleanly" is partly "comes up slowly." risk-metrics needs its upstreams *reachable*, not *healthy* — relaxable.
- redis healthcheck has no start_period.

### 4.5 Durability + hygiene

- All DBs on named volumes — **no stateful service keeps data only in the writable layer.** Good.
- Every working bind depends on drvfs's synthetic 0777 while containers run uid 999 — a loaded gun; entrypoint `mkdir -p`+`chown` (or uid-1000 images) is the durable fix. notification-service already sits on a different (metadata-enabled) mount regime.
- **tournament-harness mounts `/var/run/docker.sock` read-write** — full daemon control from inside a container. Needs a decision.
- api-gateway binds `.planning/state` read-write — a container writing into the git working tree (source of the dirty `carry_ins.json`).
- All 11 services run `LOG_LEVEL=DEBUG`/`DEBUG=true`; host app logs total ~2.3 GB (portfolio-manager 1.1 GB, api-gateway 918 MB), growing ~20 MB/day each. No `RotatingFileHandler` anywhere. Container json-logs are capped 50m×3 in compose (static config; actual sizes unverifiable from WSL).

---

## 5. Repo/docs state

- The 73-file archive batch of 2026-08-03 executed and verified (commits `3feaa1e`..`7bd40ea`; every ARCHIVE-bucket target confirmed gone from its original location). Root is at 4 files. **No moves outstanding; no git mv script needed.**
- Outstanding: the ~9 in-place corrections in §1.4, plus two structural decisions:
  - **ARCHITECTURE.md / STRATEGY.md should NOT be created as real documents.** Architecture authority is `docs/architecture/SYSTEM_OVERVIEW.md` (current, referenced by CLAUDE.md by path); strategy authority is CLAUDE.md §2 + ADR-013. New consolidated copies would fork and drift — the exact failure mode being repaired. If root-level discoverability is wanted: one-line stubs pointing at the authorities. **Owner decision.**
  - Root RUNBOOK.md and docs/operations/RUNBOOK.md are a deliberate cross-referenced split (failure-triage vs nominal ops) — keep both, don't merge.

---

## 6. Trade forensics

### 6.1 The dataset (first finding)

**31 trade legs, 15 positions, 12 closed, 3 open.** Not thousands — the CLAUDE.md strategy table's 1,986–4,658-trade figures are from old $10k frictionless backtests, not this account. Every conclusion below rests on n=12; treat percentages as descriptions of these 12 trades, not estimates of true rates. Date range 2026-07-29 → 2026-08-04; **0 legs predate the 2026-04-25 testnet flip (clean); 17 of 31 legs predate the 2026-08-03 slippage commit (frictionless)** — confirmed empirically: four 08-04 14:10 close/reopen pairs filled at identical prices, impossible with slippage on. Effectively one closed position was measured with slippage active.

### 6.2 Headline metrics

| Metric | Value | Assumption |
|---|---|---|
| Closed positions | 12 (3 wins, 8 losses, 1 flat) | — |
| Win rate | 25.0% | — |
| Avg win / avg loss | +$1.2054 / −$1.1617 (payoff 1.038) | gross of fees+funding; 17/31 legs frictionless |
| Expectancy per trade, gross | **−$0.4731** | same |
| Expectancy net, engine-modelled fees | −$0.5995 | 0.1%/side |
| Expectancy net, Bybit taker est. | −$0.5426 | 0.055%/side (estimate) |
| Total account damage | −$5.68 gross; −$7.54 net modelled; −$6.70 net Bybit est. | no funding in any figure |
| Fees vs gross loss | 32.9% (modelled) / 18.1% (Bybit est.) | — |

**Expectancy is negative BEFORE costs.** Fees are a real but secondary tax (~16–29% of the loss) — fee dominance REFUTED as primary cause, CONFIRMED as contributor. The engine also **over-charges fees ~1.8x** (0.1%/side vs Bybit 0.055%; `config.py:573`).

**Reported P&L is wrong at the source:** `realized_pnl` is computed gross (`paper_trading.py:316-319`) and persisted without commission (`:363`) — the cash ledger subtracts fees (`:324`) but every DB row and dashboard number overstates by the full fee load. Verified to 8 decimal places on position 46. Additionally `portfolios.realized_pnl` = 3.0901 = exactly the last trade's P&L — **overwritten, not accumulated** — so the portfolio row shows a profit while the account is down ~$7.

### 6.3 Where the money went: exit-reason breakdown

| Exit | n | losers | gross P&L | avg hold |
|---|---|---|---|---|
| stop_loss_limit | 5 | **5** | **−$7.4251** | 28.8h |
| auto_close (max-hold) | 7 | 3 | +$1.7477 | 62.7h |

**Every stop-loss exit lost; stop-losses ARE the entire net loss.** Every LONG stop landed at exactly −2.49%, every SHORT at −2.51% — a constant, because it's a formula: 2.0% stop + a deterministic 0.5% penalty (H2). No take-profit ever fired on a full position. Six of seven auto_closes held 67–94h against a configured 48h max — because the engine was **down ~67 hours** (no trades 08-01 19:00 → 08-04 14:10); the 14:10 batch is the max-hold sweep firing on restart, which then churned 4 positions closed-and-reopened at identical prices in 25 seconds (H6).

### 6.4 Sizing reconstruction (exact)

Recorded notionals $34–$96 per position on a $100 account; 3 open positions = **$251.53 = 251% of equity** (peak 328%). Formula reconstructed and verified to 7 significant figures on four consecutive orders (`auto_trader.py:4233-4235`):

```
notional = balance × position_size_pct(≤0.10) × DEFAULT_LEVERAGE(10) = balance × ~1.0
```

**The 10% per-trade cap is multiplied back to 100% of balance by leverage.** `docker-compose.unified.yml:674` even states this as intent. The ensemble entry path applies no exposure gate, no position-size gate, no min-notional gate (`auto_trader.py:4211-4258`); the only surviving constraint is `total_cost > balance` (`paper_trading.py:428`), which leverage relaxes 10x. Caps `MAX_POSITION_SIZE_PCT=10`, `MAX_TOTAL_EXPOSURE_PCT=80`, `MAX_RISK_PER_TRADE=0.10` exceeded ~10x / ~4x / ~10x. Sizing does read the live ~$100 balance (not the stale $10k row) — then levers it.

### 6.5 Engine/data verdicts (a–h)

| Item | Verdict | Key evidence |
|---|---|---|
| a. Look-ahead bias | **REFUTED** | `technical-analysis/app/fetcher.py:220-230` drops the still-forming candle at the fetch layer; all indicators inherit closed-candle convention. (In a live loop, using the forming bar would be signal instability anyway, not backtest-style leakage.) The one defensible subsystem. |
| b. Cost model | **CONFIRMED defective, both directions** | Fee 0.1%/side ≈1.8x real taker; slippage correct design but inactive for 17/31 legs; spread not modelled separately; **funding absent entirely** (holds crossed 3–12 8h-intervals uncharged; `funding_gate.py` gates entries only). Net bias **uncalibrated** — not simply "optimistic". |
| c. Fill realism | **CONFIRMED broken — largest single defect** | Stop exits: limit price set 0.5% beyond the stop (`auto_trader.py:3057,3163-3174`) then the paper engine **fills at that literal price** (`:3202-3205`). Every stop −2.49/−2.51%. Cost $1.4869 = 20% of stop losses = 9x real round-trip fees. Introduced by a fix meant to *reduce* slippage. Stale fills confirmed: 14:10 sweep filled 9 orders in 25s off a cached ticker after a 67h outage. |
| d. Timestamps | **REFUTED** | epoch-ms UTC, open-time convention, consistent ingest→TA→engine; naive datetimes consistently UTC (`_as_utc()` normalization). No mixing found. |
| e. Data quality | **REFUTED — data is clean** | 0 gaps, 0 dups (PK-enforced) across all 5 symbols over the trading window; testnet rows correctly quarantined behind `is_mainnet` filters (`repository.py:130,174`); flip at 2026-04-25 exactly as documented. |
| f. Stop distance vs ATR | **CONFIRMED — stops inside noise band** | Flat 2%/4% brackets (`config.py`), `atr_stops.py` unwired. 2% stop = **0.37–0.97 daily ATR** on every symbol (ADA worst at 0.37; ADA is 0-for-2) against ~67h median holds. 25% observed win rate is *not inconsistent* with a zero-information random-walk null (p=1/3 target-first) — n=12 cannot distinguish; the confirmed part is the geometry + 5/5 stop-loss record, not the binomial. |
| g. Overfitting | **UNVERIFIED — parameter provenance poor** | Params hardcoded, not fitted — but thresholds were *relaxed until trades fired*: `AGGREGATION_THRESHOLD=0.10` ("lowered for active markets"), `MIN_AGREEING_LEGS=1` (`multi_strategy_ensemble.py:150-153`); `min_signal_confidence` walked 0.65→0.40→0.30 (`config.py:402`); all 12 entries (conf 0.109–0.380) would have failed the original gate. Adaptive leg weights never persist (`ensemble_weights.json` absent in container) — refit from scratch each restart. No DSR/CPCV/walk-forward for this configuration; the 2025-12-11 walk-forward artifacts are stale ($10k, frictionless, different strategy) — do not cite. |
| h. Fee dominance | **REFUTED as primary, CONFIRMED as contributor** | Gross expectancy already negative (−$0.47). At correct $100 sizing ($10 notional): round trip ≈ $0.011 — negligible; but the 0.5% stop penalty is a *percentage* defect and does not shrink with size. |

### 6.6 Missing instrumentation (first-class findings)

1. Fees recorded per leg but **never netted into any reported P&L** — worse than absent because it looks instrumented.
2. **No funding cost anywhere** — no column, no accrual.
3. **No `remaining_quantity` column** — partial exits invisible in the DB, resurrect on restart (H5; one position's P&L overstated **$1.7029**, defect live now on open positions 57 and 60).
4. **No signal-time snapshot** — indicator vector and reference price at decision time unrecorded; fills can't be audited against what the strategy saw.
5. **No slippage attribution** — reference and fill collapsed into one price column; `slippage_manager.record_execution` writes nothing durable.
6. `portfolios.initial_balance=10000` vs `total_value=100` in the same row (§2.2).

---

## 7. Ranked root-cause hypotheses — each with its kill test

| # | Hypothesis | Status | Kill test (exact) |
|---|---|---|---|
| **H1** | Sizing is ~10x over cap: leverage multiplies the risk cap instead of being bounded by it; ensemble path has no exposure/size/min-notional gates | **CONFIRMED** (formula reconstructed exactly; no test needed, only a fix) | After fix: `DEFAULT_LEVERAGE=1.0` + gates wired → assert every new `positions.cost_basis ≤ $10.00` and open-position `SUM(cost_basis) ≤ $80.00`. Any single breach = cap still bypassed. |
| **H2** | 0.5% stop "buffer" is a deterministic loss on every stop exit ($1.49 = 20% of stop losses) | **CONFIRMED** (exact match on all 5 stops) | Set `limit_buffer_pct=0.0` (`auto_trader.py:3057`); stop exits must move from −2.49/−2.51% to −2.00%. One constant — cheapest test in the repo. |
| **H3** | 2%/4% fixed brackets sit inside the noise band; exit design has ~zero expectancy before costs | **CONFIRMED for the geometry** (0.37–0.97 daily ATR); causal claim needs the test — tested 2026-08-05: see .planning/evidence/killtests/H3-verdict-20260805.md (ACCEPT) | Replay same entries, stops at 1.5×/2.5× ATR-derived daily vol, TP 2R, all else identical. Accept: stop-out rate <40% AND gross expectancy >0 pre-fee. If still ≤0 → the entry signal is uninformative → H4 is the answer. Run only after H1+H2 fixed. |
| **H4** | Ensemble signal carries no information; thresholds lowered until it fired | **UNVERIFIED — unverifiable at n=12** | Signal-vs-forward-return test, independent of exits: every ensemble signal over ≥6 months `is_mainnet` klines vs sign of 24h forward log-return. Accept: directional accuracy >50% with **DSR>0.95 counting all ≥8 strategy configurations tried**. Below that → no exit design can rescue it. The only expensive test; run last. |
| **H5** | Partial exits never persisted; restarts resurrect sold quantity and manufacture P&L | **CONFIRMED** ($1.7029 overstatement, exact; live on positions 57, 60) | Open→partial exit→restart→`SELECT quantity`: equals original = confirmed. Fix: `remaining_quantity` column + persist in `reduce_position` (`position_manager.py:422-438` writes neither qty nor incremental P&L). |
| **H6** | Restart churn: max-hold sweep closes and instantly reopens same symbol at same price | **CONFIRMED** (4 round trips, 25s, zero exposure change, ~$0.66 fees = 0.66% of account) | Add re-entry cooldown after max-hold exits (SL cooldown exists at `auto_trader.py:3105`; max-hold bypasses it) + gate sweep on engine uptime. Assert: no open within N min of a same-symbol close at ≤1 tick distance. |
| **H7** | Reported P&L excludes fees; portfolio row overwrites instead of accumulating | **CONFIRMED** (exact gross match; 3.09 vs −5.68) | `sum(positions.realized_pnl WHERE CLOSED)` must equal `portfolios.realized_pnl` — fails today. Fix: subtract commission before persisting + accumulate. |

**Execution order for kill tests:** H2 (one constant) → H1 (env + gates) → H7/H5 (SQL asserts) → H6 → H3 (ATR replay) → H4 (signal information). H4 before H1–H3 would measure the broken instrument again.

**Bar to clear before any edge claim** (quant-skeptic's terms, adopted): H1/H2/H5/H6/H7 fixed and assert-verified; slippage on for 100% of legs; fee 0.055%/side; funding accrued; ATR-scaled stops; **≥200 closed trades** at correct $100 sizing on `is_mainnet` data; expectancy net of fees+funding+slippage; DSR>0.95 counting every configuration tried; walk-forward ≥3/4 windows positive. Until then: this system has not been tested — it does not yet have a working measurement.

---

## 8. Unverified-items registry (what would settle each)

| Item | Settles it |
|---|---|
| `.env` operator overrides (incl. `AUTO_TRADING_ENABLED=true`) | owner confirms; agents did not open `.env` by rule |
| `.env.example`/`.production`/`.test` sizing-key drift | paste sizing keys or grant template read |
| Kelly sizer default `capital=10000` ever reached | call-site trace of `get_kelly_sizer()` consumers |
| `scripts/automated_trading_loop*.py` deployed anywhere | check entrypoints/cron; if live, their loss-breaker is 100x lenient |
| grid_trading_strategy_v2 clamp-up truly dead | runtime trace / delete-and-test |
| Second bookkeeping path (portfolio buy/sell) touched by auto-trader | trace or log instrumentation |
| Whether other services drew the tmpfs on previous boots | not recoverable; inferred stack-wide from shared pattern |
| Container json-log actual sizes | not readable from WSL; cap is static config |
| risk-metrics host log mtime 18:20 post-disconnection | oddity, low priority, unexplained |

### 8.1 Operator decisions (2026-08-05)

- **cash_balance=$73.30 accepted as-is.** May embed ~$4.23 phantom margin from the pre-fix accounting bug (unverified estimate). Decision: no reconstruction, no baseline reset — paper money, forward-going accounting corrected by H5/H7 fixes. Treat any P&L computed against $100 initial as carrying up to ±$4.23 of legacy noise until the account is next reset.

---

*Underlying agent reports (full SQL, printenv output, and log excerpts) live in this session's transcripts; every number above traces to one of them. Corrections applied from the forensics self-audit: SOL 1h-ATR is 0.614 (not 0.638); the binomial null is "not inconsistent," not "reproduces"; `can_open_position` is "unreachable from the ensemble path," not globally dead.*
