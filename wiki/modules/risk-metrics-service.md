---
type: module
path: "services/risk-metrics-service/"
status: active
language: python
port: 8009
purpose: "Risk metrics (Sharpe/Sortino/Calmar/VaR/CVaR/drawdown), composite risk score, and the canonical circuit-breaker state machine. Misnamed as 'Risk dashboards' in CLAUDE.md — frontend renders dashboards, this service computes the numbers."
maintainer: ""
linked_issues: []
depends_on: [portfolio-manager, redis]
used_by: [api-gateway, frontend, prometheus]
tags: [module, service, risk, metrics, circuit-breaker]
created: 2026-05-05
updated: 2026-05-05
---

# risk-metrics-service

**Port:** `8009`
**Path:** `services/risk-metrics-service/`
**Purpose:** Real-time risk monitoring, performance analytics, and circuit-breaker state machine. Symbol-agnostic — operates on portfolio aggregates from [[portfolio-manager]].

See raw audit: `wiki/.raw/agent-reports/risk-metrics-service.md`.

## Overview

FastAPI service, version `1.0.0`. Stateless on disk (no DB), stateful in memory (`peak_value`, `historical_returns`, circuit-breaker state machine). Pulls portfolio snapshots from [[portfolio-manager]] over HTTP, caches results in Redis (TTL 30s), publishes Prometheus metrics on `/metrics`. No RabbitMQ involvement.

Two big surprises versus the stated "Risk dashboards" purpose:

1. **It owns the canonical circuit-breaker state machine** (CLOSED → OPEN → HALF_OPEN), separate from the in-process risk module inside [[trading-engine]]. The two systems can disagree — see [[../concepts/Risk-Model]].
2. **Returns history is never populated in production** (`engine.historical_returns: List[float] = []` and nothing mutates it). All Sharpe / Sortino / Calmar / VaR calculations therefore fall through to the **insufficient-data fallback paths**: hardcoded `var_95 = 5%` of portfolio, Sharpe defaults to 0, etc. The dashboards downstream are largely fictional until ingestion is wired.

## Endpoints

Mounted directly on `app.main` (no APIRouter). Excludes `/health`, `/ready`.

Risk monitoring (Redis-cached):
- `GET /risk/scorecard` — composite scorecard + alerts + recommendations
- `GET /risk/capital` — capital utilization
- `GET /risk/exposure` — long/short/net/gross + concentration list
- `GET /risk/drawdown` — current/max drawdown, underwater days
- `GET /risk/var?confidence_level=0.95&time_horizon_days=1` — VaR/CVaR

Performance:
- `GET /performance/metrics` — Sharpe / Sortino / Calmar / win-rate
- `GET /performance/sharpe` — Sharpe + meets-target flag

Alerts & circuit-breaker:
- `GET /alerts` — active `RiskAlert`s (delegates to scorecard)
- `GET /circuit-breaker` — state machine snapshot
- `POST /circuit-breaker/reset` — admin (`X-Admin-Key`)

Configuration (admin):
- `GET /config/limits`, `PUT /config/limits` — **`PUT` does not persist**, only logs

Cache & observability:
- `POST /cache/invalidate`, `GET /cache/stats`
- `GET /metrics` (Prometheus), `GET /status`, `GET /performance/stats`, `POST /performance/reset`

Removed during 2026-05-01 audit (left as comment block in `main.py:752`): `GET /api/v1/alerts/active`, `GET /api/v1/portfolio/{portfolio_id}/risk-scorecard` — both called RiskEngine methods that don't exist.

## Metrics computed

In `app/risk_engine.py`:

- **Capital**: total / allocated / available / reserved / utilization / max position size
- **Exposure**: long, short, net, gross, exposure ratio, leverage, concentrated positions
- **Drawdown**: current, max, underwater period (days), recovery factor, avg drawdown
- **Performance**: total / annualized return, volatility (sample std × √252), **Sharpe**, **Sortino** (downside-only), **Calmar** (annualized / max DD), win-rate, profit-factor, largest win/loss
- **VaR**: var_95, var_99, cvar_95, cvar_99 — historical method, √t scaling
- **Composite risk score** 0–100 — weighted: capital ≤20, exposure ≤25, concentration ≤15, volatility ≤20, drawdown ≤20 → maps to `RiskLevel.LOW/MEDIUM/HIGH/CRITICAL`

Not computed here: correlation matrix (lives in [[trading-engine]] under `/api/v1/risk/correlation/*`), beta vs benchmark, skew/kurtosis.

## Data sources

- **[[portfolio-manager]]** (port 8003) — `GET /api/v1/portfolio` for total value + holdings. **Only** upstream HTTP call.
- **[[market-data-service]]** (port 8002) — configured via `market_data_url` but **never called**. Dead config.
- **No DB**. `database_url` configured but unused.
- **Redis** — read-through cache for risk endpoints (TTL 30s).

## Internal deps

- `PORTFOLIO_MANAGER_URL=http://portfolio-manager:8003`
- `MARKET_DATA_URL=http://market-data-service:8002` (dead)
- `REDIS_HOST=redis` / `REDIS_PORT=6379` / `REDIS_PASSWORD=...`
- `ADMIN_API_KEY=...` (override default before prod — see `app/auth.py`)

No RabbitMQ. No Kafka.

## Used by

- [[api-gateway]] proxies `/api/risk/*` and `/api/performance/*` (11 routes, `services/api-gateway/app/main.py:1450–1572`).
- [[frontend]] PerformanceDashboard components consume the gateway-proxied endpoints (EquityCurveChart, DrawdownChart, CorrelationHeatmap — though correlation comes from [[trading-engine]], not here).
- Prometheus scrapes `/metrics`.
- **[[trading-engine]] does NOT consult this service**. It runs its own in-process risk + circuit breaker. See Contradictions in raw report.

## RabbitMQ

None. Service does not subscribe to `portfolio.update` and does not publish `alert.critical` despite generating `RiskAlert` objects with `RiskLevel.CRITICAL`. [[notification-service]] has no integration with this service. Critical alerts only reach operators if something polls `GET /alerts`.

See [[../flows/Order-Lifecycle]] for where blocking decisions actually happen — currently inside [[trading-engine]], not via this service's circuit-breaker.

## DB tables

None. All state in-memory on the `RiskEngine` instance — restart wipes circuit-breaker cooldown, peak value, failure counts.

## Gotchas

- **Bind-mount race on `/app/logs`** — confirmed in `progress.md`. Symptom: `PermissionError: '/app/logs/service.log'` at import time (logging is configured before FastAPI starts). Fix: `docker compose up -d --force-recreate risk-metrics`.
- **Health = "degraded" without `REDIS_HOST`** — health check ANDs portfolio-manager reachability and Redis ping.
- **All performance metrics use insufficient-data fallback** in practice (no returns ingestion wired). Frontend dashboards show numbers that don't reflect real returns.
- **`PUT /config/limits` is a no-op** that returns 200 — does not mutate `settings` or persist anywhere.
- **Volatility floor 0.001** when realized vol ≈ 0 produces fake-finite Sharpe ratios.
- **Circuit-breaker is in-memory only** — restart clears OPEN state; operator could "reset" by restart alone.
- **CORS `allow_origins=["*"]`** despite configured `allowed_origins` setting.
- **Dead modules**: `app/backtesting.py`, `app/cpcv.py`, `app/sharpe_metrics.py`, `app/backtest_models.py` are not imported by `main.py`. `.bak` and `.backup` files sitting next to live code.

## Related

- [[../concepts/Risk-Model]] — composite scoring, dual-circuit-breaker problem, alerting gap
- [[../flows/Order-Lifecycle]] — where risk gates *actually* fire (spoiler: not here)
- [[portfolio-manager]] — sole upstream
- [[market-data-service]] — configured upstream, never called
- [[trading-engine]] — owns the parallel risk system + correlation router
- [[notification-service]] — should receive critical alerts, currently doesn't
- [[api-gateway]] — proxies `/api/risk/*`, `/api/performance/*`
- [[frontend]] — consumes via gateway
