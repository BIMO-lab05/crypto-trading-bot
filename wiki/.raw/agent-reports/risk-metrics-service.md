---
service: risk-metrics-service
port: 8009
generated: 2026-05-05
scope: full service (12 Python files, ~4.2k LOC)
---

# risk-metrics-service — raw agent report

Repo path: `services/risk-metrics-service/`
Stated purpose (CLAUDE.md): "Risk dashboards"
FastAPI title (`app/main.py:246`): "Risk & Metrics Service" — VERSION = `1.0.0`.
Actual scope much wider than "dashboards": it owns the **circuit-breaker state machine**, **VaR/CVaR**, **Sharpe/Sortino/Calmar**, **risk score 0–100**, and admin-keyed runtime risk-limit overrides.

## Endpoints

All routes live inline in `app/main.py` (no `APIRouter` modules). 21 routes total (excluding `/health`, `/ready`):

Status / observability:
- `GET /` — service banner, `endpoints` map, optimization flags.
- `GET /metrics` — Prometheus exposition (`prometheus_client.generate_latest()`), 15 metrics families.
- `GET /status` — circuit-breaker active flag, configured limits, perf summary, cache stats, conn-pool stats.
- `GET /performance/stats` — request-level perf monitor summary (NOT trading performance).
- `POST /performance/reset` — admin: clear in-memory perf history + cache stats.

Risk monitoring (cached):
- `GET /risk/scorecard` — composite scorecard. Aggregates capital, exposure, drawdown, performance, VaR, alerts, recommendations. Calls portfolio-manager once.
- `GET /risk/capital` — `CapitalMetrics` (allocated, available, reserved, utilization, max position size).
- `GET /risk/exposure` — `ExposureMetrics` (long/short/net/gross, ratio, leverage, concentration list).
- `GET /risk/drawdown` — `DrawdownMetrics` (current, max, underwater days, recovery factor).
- `GET /risk/var?confidence_level=0.95&time_horizon_days=1` — `ValueAtRisk` (var_95/99 + cvar_95/99).

Performance metrics (cached):
- `GET /performance/metrics` — `PerformanceMetrics` (Sharpe, Sortino, Calmar, win-rate, profit-factor, etc).
- `GET /performance/sharpe` — Sharpe + annualized return + volatility + meets-target flag.

Alerts & circuit-breaker:
- `GET /alerts` — list of active `RiskAlert`s (delegates to `/risk/scorecard`).
- `GET /circuit-breaker` — `CircuitBreakerStatus` (state, can_trade, cooldown_until, failure_count).
- `POST /circuit-breaker/reset` — admin: force CLOSED, clear cooldown.

Configuration (admin):
- `GET /config/limits` — current `RiskLimits`.
- `PUT /config/limits` — update limits in-memory (NOT persisted — see Gotchas), invalidates cache.

Cache management (admin):
- `POST /cache/invalidate` — flush `risk_metrics:*` keys from Redis.
- `GET /cache/stats` — hit-rate, key count.

**Removed during 2026-05-01 audit** (per comment block at `main.py:752`): `GET /api/v1/alerts/active` and `GET /api/v1/portfolio/{portfolio_id}/risk-scorecard` — both called RiskEngine methods that don't exist (`get_circuit_breaker_status`, `get_risk_level`, `generate_recommendations`) and returned HTTP 500. So the service has **no `/api/v1/...` surface at all** despite still being plumbed through gateway as `/api/risk/*`.

**Files present but not wired into FastAPI**: `app/backtesting.py` (594 LOC backtesting engine), `app/cpcv.py` (266 LOC combinatorial purged cross-validation), `app/sharpe_metrics.py` (251 LOC), `app/backtest_models.py` (151 LOC). No router includes them — dead code reachable only by direct import. `main.py.bak` and `risk_engine.py.backup` also sitting next to live files.

## Metrics computed

In `app/risk_engine.py` (~840 LOC):

- **Capital**: `total_capital`, `allocated_capital`, `available_capital`, `reserved_capital` (= `total * max_portfolio_risk`), `capital_utilization`, `max_position_size`, `recommended_position_size` (line 53–92).
- **Exposure**: `long_exposure`, `short_exposure`, `net_exposure` (long − short), `gross_exposure` (long + short), `exposure_ratio`, `leverage`, `concentrated_positions[]` (positions > `max_position_size`) (line 96–148).
- **Drawdown**: `current_drawdown` (vs in-memory `peak_value`), `max_drawdown` (from historical peak), `underwater_period_days` (days since last peak), `recovery_factor`, `avg_drawdown` (line 152–240). Bug fix noted at line 217: `underwater_days` was being overwritten every iteration.
- **Performance** (line 244–332):
  - `total_return`, `annualized_return` (252 trading days), `volatility` (sample std `ddof=1`, annualized via √252).
  - `sharpe_ratio` = (annualized_return − risk_free_rate) / annualized_volatility.
  - `sortino_ratio` = (annualized_return − risk_free_rate) / downside_std (only negative returns, ddof=1).
  - `calmar_ratio` = annualized_return / max_drawdown.
  - Trade metrics: `win_rate`, `profit_factor`, `average_win`, `average_loss`, `largest_win`, `largest_loss`, `total_trades`.
  - **Volatility floor**: when `volatility < 1e-10`, forced to `0.001` to avoid div-by-zero. This produces *finite* Sharpe even when there's no real signal — silent quality issue.
- **Value at Risk** (line 376–441):
  - `var_95`, `var_99` via historical method (5th / 1st percentile of returns).
  - `cvar_95`, `cvar_99` (Expected Shortfall) — mean of tail beyond VaR threshold.
  - Time-scaling: √t rule.
  - **Insufficient-data fallback** (<30 returns): hardcoded `var_95 = 5%` and `var_99 = 10%` of portfolio value, multiplied by √horizon. CVaR fallback = VaR × 1.4 (95%) / × 1.2 (99%).
- **Composite risk score** 0–100 (line 445–505): weighted sum of capital (max 20), exposure (max 25), concentration (max 15), volatility (max 20), drawdown (max 20). Maps to `RiskLevel.LOW/MEDIUM/HIGH/CRITICAL`.

What's **NOT** computed:
- **Correlation matrix** — done in trading-engine (`/api/v1/risk/correlation/*`), not here.
- **Beta / alpha** vs benchmark — absent.
- **Greeks / option sensitivities** — N/A (spot only).
- **Skewness / kurtosis** — absent (referenced in `sharpe_metrics.py` but not wired).

## Data sources

**Single upstream**: `portfolio-manager` only.
- `app/main.py:332` — `GET {portfolio_manager_url}/api/v1/portfolio` returns full portfolio. Service treats `portfolio.holdings` as positions and `portfolio.total_value` as capital.
- **`market_data_url` is configured** (`config.py:20`) **but never used** — no `httpx.get(...)/8002/...)` call in main.py or risk_engine.py. Returns array (`engine.historical_returns`) is **always empty in normal operation** — initialized as `[]` in `RiskEngine.__init__` and nothing mutates it. So Sharpe/Sortino/Calmar/VaR are **all running on the insufficient-data fallback paths in production**.

**No DB queries**. No SQL imports. No SQLAlchemy session. No use of TimescaleDB.

## Internal deps

Configured in `app/config.py`:
- `portfolio_manager_url` default `http://localhost:8003` (compose: `http://portfolio-manager:8003`).
- `market_data_url` default `http://localhost:8002` (compose: not set explicitly — relies on default — **dead config**).
- `redis_host` / `redis_port` / `redis_password` (compose passes `REDIS_HOST=redis`, `REDIS_PASSWORD=redis_password`).
- `admin_api_key` default `dev-admin-key-change-in-production` — **needs override in prod** (used by `app/auth.py:verify_admin_key` via `X-Admin-Key` header).

Runtime deps (requirements.txt area, inferred from imports): `fastapi`, `httpx`, `numpy`, `prometheus_client`, `redis` (async), `pydantic-settings`.

No RabbitMQ client, no `aio_pika`, no `pika`, no `aiokafka` — service is purely HTTP-driven.

## Used by

- **api-gateway** (`services/api-gateway/app/main.py:1450–1572`) proxies 11 endpoints under `/api/risk/*` and `/api/performance/*`:
  - `/api/risk/scorecard|capital|exposure|drawdown|var|alerts|circuit-breaker`
  - `/api/risk/circuit-breaker/reset` (POST)
  - `/api/performance/metrics|sharpe`
  - Service registered in `service_proxy.py:31` as `"risk-metrics": settings.risk_metrics_url`.
- **trading-engine**: **does NOT call this service**. `grep risk-metrics services/trading-engine/` returns only its own internal `risk_metrics` field name on `BacktestReport` and a verify_system.py health-check ping. Trading-engine has **its own** in-process risk module (`app/risk_management/`) and circuit-breaker logic — **two parallel risk systems** (see Contradictions).
- **frontend**: no direct hits on `:8009` or `risk-metrics` strings, but the React `PerformanceDashboard` components (e.g. `EquityCurveChart.jsx`, `DrawdownChart.jsx`, `CorrelationHeatmap.jsx`) presumably consume `/api/performance/*` and `/api/risk/*` through the gateway. Not verified end-to-end in this audit.
- **prometheus**: scrapes `/metrics` (port 8009).

## RabbitMQ

**None.** Service neither subscribes to events nor publishes them. No `portfolio.update` listener, no `alert.critical` publisher, despite generating `RiskAlert` objects internally. Alerts are exposed only via pull (`GET /alerts`); downstream notification-service has no integration with this service. If a `CRITICAL` drawdown alert fires, **no Telegram/email goes out automatically** unless something else polls `/alerts`. (Did not find such a poller in trading-engine or notification-service.)

## DB tables

**None owned.** Service has no migrations, no schema, no SQLAlchemy models. `database_url` is configured but unused (`config.py:59` — `Optional[str] = None`). All state is in-memory on the `RiskEngine` instance:
- `historical_returns: List[float]` — empty in practice.
- `peak_value: Decimal` — starts at 0, updates only when `/risk/drawdown` or `/risk/scorecard` is called.
- `circuit_breaker_*` state machine fields.

**Implication**: every restart wipes circuit-breaker state, peak value, failure counts, cooldown timers. No persistence across container reboots.

## Key files

1. `app/main.py` (1010 LOC) — FastAPI app, routes, lifespan, Prometheus metrics, middleware.
2. `app/risk_engine.py` (840 LOC) — all metric calculations + circuit-breaker state machine.
3. `app/models.py` (274 LOC) — Pydantic response models (`RiskScorecard`, `CapitalMetrics`, `ExposureMetrics`, `DrawdownMetrics`, `ValueAtRisk`, `PerformanceMetrics`, `RiskAlert`, `CircuitBreakerStatus`, `CircuitBreakerState` enum, `RiskLimits`).
4. `app/config.py` (94 LOC) — Pydantic settings, including circuit-breaker thresholds + state-machine config.
5. `app/cache.py` (277 LOC) — `RiskMetricsCache` Redis wrapper with stats.
6. `app/performance.py` (379 LOC) — `PerformanceMonitor` (request latency tracking), `RequestBatcher`, `ConnectionPool` — service-internal infra, NOT trading performance.
7. `app/auth.py` (40 LOC) — `verify_admin_key(X-Admin-Key)` dependency.
8. `app/backtesting.py` (594 LOC) — **dead code**, no router include.
9. `app/cpcv.py` (266 LOC) — **dead code**, combinatorial purged CV.
10. `app/sharpe_metrics.py` (251 LOC) — **dead code**, advanced Sharpe variants.

Junk to clean up: `app/main.py.bak`, `app/risk_engine.py.backup`, `final_risk_score_fix.py`, `fix_risk_engine.py`, `fix_risk_score.py`, `htmlcov/`, `build_risk_metrics_service.log`, `test_results.txt`, eight (!) markdown reports next to the Dockerfile (CIRCUIT_BREAKER_SUMMARY.md, COVERAGE_ACHIEVEMENT.md, OPTIMIZATION_SUMMARY.md, PERFORMANCE_DELIVERABLE.md, etc.).

## Gotchas

- **Bind-mount race on `/app/logs`** — confirmed in `progress.md:705`: `risk-metrics` failed with `PermissionError: '/app/logs/service.log'` after WSL bind-mount silently created an empty root-owned dir. Fix: `docker compose up -d --force-recreate risk-metrics`. Risk persists because `main.py:56` does `Path('logs').mkdir(exist_ok=True)` and `logging.FileHandler('logs/service.log')` runs at import time — if the bind mount races, import itself fails before FastAPI can start.
- **`/health` returns "degraded" if Redis env vars not passed** (`progress.md:306` — happened due to missing `REDIS_HOST` in compose). Health check requires both `portfolio_manager` reachable AND `redis_cache` connected to return "healthy".
- **All performance metrics fall through to insufficient-data fallback in production**: `historical_returns` never populated. So Sharpe = ~undefined / 0 / fallback, VaR = hardcoded 5% × √horizon. The frontend's nice-looking risk dashboards are largely fictional unless someone wires returns ingestion.
- **`PUT /config/limits` doesn't persist**: `main.py:932` literally just logs the request and returns 200. The "Changes will take effect immediately" message is misleading — the underlying `settings` object is not mutated, so on next request, original limits apply.
- **Cache invalidation pattern is `risk_metrics:*`** — but `cache.py` constructs keys with namespace, so admin invalidate works only if namespace matches. Verify before relying on.
- **Volatility floor of 0.001** when realized vol < 1e-10 produces fake-looking Sharpe ratios for nearly constant returns. Cosmetic, but misleading on dashboards.
- **Circuit-breaker state is in-memory only** — restart wipes the cooldown window. An attacker / operator could clear an OPEN cb just by `docker restart crypto-bot-risk-metrics`.
- **`market_data_url` config is dead** (configured but never called). Two read-paths: probably stale from earlier design where this service was supposed to pull returns directly. CLAUDE.md still implies it.
- **CORS allows `*`** (`main.py:255`) despite a configured `allowed_origins` list in settings. Settings ignored.

## Contradictions vs CLAUDE.md

1. **Purpose mismatch**: CLAUDE.md says "Risk dashboards" (port 8009). Reality: this service owns **Sharpe/Sortino/Calmar, VaR/CVaR, drawdown, the canonical circuit-breaker state machine, the composite risk score, runtime risk-limit overrides, and admin auth**. "Dashboards" understates by an order of magnitude — and it doesn't render dashboards (the React frontend does that).
2. **Two parallel risk systems**: CLAUDE.md project rule says "Risk caps wired into trading-engine: max 2% capital per trade, 5% daily-loss circuit-breaker." Trading-engine has its own `risk_management/` module + correlation router + emergency-stop file mechanism. risk-metrics-service has a completely **separate** circuit-breaker state machine that nothing in trading-engine consults. The two can disagree silently. Which one is canonical for blocking orders is **not defined anywhere**.
3. **Notification gap**: CLAUDE.md "Verification standards" require "at least one notification actually received downstream (Telegram/email arriving)". Risk-metrics-service generates `CRITICAL` alerts but does **not** emit them to RabbitMQ or push to notification-service. Operator only sees them by pulling `/alerts`.
4. **Symbol scope**: CLAUDE.md lists 5 validated symbols (BTC, ETH, SOL, BNB, ADA). risk-metrics-service is **symbol-agnostic** — works at portfolio aggregate level. No drift here, but the service emits Prometheus label `symbol='portfolio'` for all calculations regardless of underlying composition.
5. **Test coverage 89.81% claim** (`progress.md:368`) lives next to multi-hundred-line dead modules (`backtesting.py`, `cpcv.py`, `sharpe_metrics.py`) that contribute coverage but no production behavior.
6. **`/api/v1/...` surface promised by older docs**: CLAUDE.md says "REST gateway routes are `/api/<domain>/<resource>` (no `v1` prefix)". This service correctly drops the v1 (e.g. `/risk/scorecard`, not `/api/v1/risk/scorecard`) — but the comment block at `main.py:752` confirms two `/api/v1/...` endpoints existed and were removed mid-2026 due to bugs. So historical clients pointing at v1 paths get 404.
