---
type: module
path: "services/api-gateway/"
status: active
language: python
port: 8000
purpose: "Frontend → backend routing, auth, fan-out aggregation"
maintainer: ""
last_updated: 2026-05-05
linked_issues: []
depends_on: [bybit-connector, market-data-service, technical-analysis, trading-engine, portfolio-manager, risk-metrics-service, ml-prediction-service, sentiment-analysis-service]
used_by: [frontend]
tags: [module, service, gateway, auth]
created: 2026-05-05
updated: 2026-07-29
---

# api-gateway

**Port:** `8000`
**Path:** `services/api-gateway/`
**Stack:** FastAPI 0.109.0 (pinned), Starlette 0.35.1, httpx 0.27.0, slowapi, passlib+bcrypt, python-jose

Single-file FastAPI app (`app/main.py`, 2071 lines). Routes inline on `app`, no `APIRouter`. Pure HTTP proxy in front of 8 backend services + JWT auth + WebSocket fan-out + Prometheus instrumentation. **No DB, no RabbitMQ.** User store is in-memory `dict` — wiped on restart.

## Overview

- All `/api/<domain>/<resource>` routes delegate to backend services via [`ServiceProxy`](../../services/api-gateway/app/services/service_proxy.py) (single shared `httpx.AsyncClient`, 30s timeout, parallel `aggregate_health_checks`).
- Authn via JWT bearer (`/auth/*`). Admin-only routes protected by `get_current_admin_user` Depends.
- **Mode-gated auth on state-changing endpoints (added 2026-07-29, `auth_middleware.py:40–173`).** Trading start/stop, portfolio buy/sell, risk circuit-breaker reset, `signals/{s}/analyze`, ml train, and emergency-stop now require auth via `get_current_user_gated` + `api_auth_required()`. The gate is **ENFORCED in LIVE / production / staging / `REQUIRE_API_AUTH=true`** (fails closed) and **OPEN in local paper mode** (a synthetic `local-paper` principal keeps the tokenless dashboard working). An *invalid* token is rejected in every mode. `/auth/me` + `/auth/logout` stay strict (`get_current_active_user_strict`, always require a real token; `main.py:669,680`).
- WebSocket `/ws` broadcasts `dashboard_update` every 2s (health + portfolio.balance) — fixed cadence, ignores subscriptions.
- Fan-out aggregators (`/api/trading/signals/enhanced/{symbol}`, `/api/dashboard/{symbol}`, `/api/ml/predict/signal/{symbol}`) call multiple backends with `asyncio.gather` and compute consensus locally.
- Prometheus metrics at `/metrics` (excluded from OpenAPI). Custom HTTP middleware records request count + duration histogram + active-request gauge with regex-normalized paths.

See [[../flows/Signal-Pipeline]] for end-to-end signal flow, [[../flows/Order-Lifecycle]] for buy/sell path, [[../flows/Emergency-Stop]] for the EMERGENCY_STOP file flag.

## Endpoints

Counts (excluding `/health`, `/ready`, `/metrics`, `/`, `/docs`): ~73 HTTP routes + 1 WebSocket. Universal canonical pattern is `/api/<domain>/<resource>`. A v1 compatibility layer also exists — see [[../decisions/ADR-007-no-v1-api-prefix]].

### Auth (rate limit 10/min — brute-force guard, now enforced)
- `POST /auth/register` — `app/main.py:582`
- `POST /auth/login` — JWT bearer issued. `app/main.py:603`
- `GET  /auth/me` — requires bearer. `app/main.py:637`
- `POST /auth/logout` — no-op server-side (stateless JWT). `app/main.py:647`

### Market → [[market-data-service]]
- `GET /api/market/ticker/{symbol}` — transforms upstream keys for frontend. `app/main.py:669`
- `GET /api/market/kline/{symbol}` and `/api/market/klines/{symbol}` (alias) — `app/main.py:714` / `:741`

### Technical analysis → [[technical-analysis]]
- `GET /api/analysis/rsi|macd|all/{symbol}` — `app/main.py:763` / `:784` / `:800`
- `GET /api/analysis/multi-timeframe/{symbol}` — `:1831`
- `GET /api/analysis/indicators/signal/{symbol}` — `:1845`

### Trading → [[trading-engine]]
- `GET  /api/trading/signals/{symbol}` — `:821`
- `GET  /api/trading/signals/enhanced/{symbol}` — fan-out across TA + ML + multi-tf + base signal, computes consensus locally. `:837`
- `POST /api/trading/signals/{symbol}/analyze` — `:982`
- `GET  /api/trading/positions|status|performance` — `:1002` / `:1023` / `:1033`
- `POST /api/trading/start` and `/api/trading/stop` — auto-trader control. Added 2026-05-01 (frontend prod was 404'ing on these because Vite's dev proxy hid the gap). **Now `Depends(get_current_admin_user)` (mode-gated, 2026-07-29).** `:1436` / `:1455`
- `GET  /api/trading/trades/history` — `:1071`
- `GET  /api/trading/equity-curve|drawdown|returns-distribution|correlations|statistics` — Performance dashboard endpoints. Period whitelist `{1d,7d,30d,90d,all}`. `:1113`–`:1175`
- `GET  /api/trading/phase1/metrics|health|latest` — `:1195`–`:1223`

### Portfolio → [[portfolio-manager]]
- `GET  /api/portfolio[/balance|/holdings|/performance|/trades]` — `:1238`–`:1290`
- `POST /api/portfolio/buy` and `/api/portfolio/sell` — symbol/quantity/price all required (validation bypass fix 2026-05-01). **Now `Depends(get_current_active_user)` (mode-gated, 2026-07-29).** `:1714` / `:1760`
- `POST /api/portfolio/emergency-stop` — **admin-only**, writes EMERGENCY_STOP file via `pathlib.Path.write_text`. `:1387`. See [[../decisions/ADR-005-emergency-stop-file-flag]] and [[../flows/Emergency-Stop]].

### Risk / metrics → [[risk-metrics-service]]
- `GET  /api/risk/scorecard|capital|exposure|drawdown|var|alerts|circuit-breaker` — proxied to non-`/api/v1` paths upstream. `:1452`–`:1559`
- `POST /api/risk/circuit-breaker/reset` — `:1562`
- `GET  /api/performance/metrics|sharpe` — `:1522` / `:1532`

### ML → [[ml-prediction-service]]
- `GET  /api/ml/predict/price|trend|volatility|signal/{symbol}` — `model_type` whitelisted to `GRU` only (LSTM removed, see [[../decisions/ADR-001-LSTM-removed]]). `:1577`–`:1633`
- `GET  /api/ml/models[/{symbol}|/compare/{symbol}]` — `:1682` / `:1692` / `:1743`
- `POST /api/ml/models/train` — `:1710`

### Sentiment → [[sentiment-analysis-service]]
- `GET /api/sentiment/news|social|combined|trend/{symbol}` — `:1764`–`:1806`
- `GET /api/sentiment/aggregate` — declared **before** the catch-all (route-order bug fix 2026-05-01). `:1866`
- `GET /api/sentiment/{symbol}` — backward-compat catch-all. `:1878`

### Dashboard
- `GET /api/dashboard/{symbol}` — fan-out: ticker + signal + portfolio. `:1897`

### V1 compatibility shims (`/api/v1/...`)
9 routes at `:1960`–`:2029` for market/analysis/ml/portfolio. Delegate to non-v1 handlers. They are reachable despite [[../decisions/ADR-007-no-v1-api-prefix]] — flagged contradiction below.

### WebSocket
- `WS /ws` — server pushes `dashboard_update` every 2s; replies pong to `"ping"` text. `:2037`. WebSocketManager state in `app/main.py:178`.

## Internal deps

All outbound calls are HTTP via `ServiceProxy` (`app/services/service_proxy.py:25`):

| Service key | Compose URL | Env var |
|---|---|---|
| `bybit` | `http://bybit-connector:8001` | `BYBIT_CONNECTOR_URL` |
| `market-data` | `http://market-data:8002` | `MARKET_DATA_URL` |
| `portfolio-manager` | `http://portfolio-manager:8003` | `PORTFOLIO_MANAGER_URL` |
| `technical-analysis` | `http://technical-analysis:8004` | `TECHNICAL_ANALYSIS_URL` |
| `trading-engine` | `http://trading-engine:8005` | `TRADING_ENGINE_URL` |
| `ml-prediction` | `http://ml-prediction:8007` | `ML_PREDICTION_URL` |
| `sentiment-analysis` | `http://sentiment-analysis:8008` | `SENTIMENT_ANALYSIS_URL` |
| `risk-metrics` | `http://risk-metrics:8009` | `RISK_METRICS_URL` |

`bybit-connector` is in the proxy map but no current handler routes to it. Compose also injects `NOTIFICATION_URL` for [[notification-service]] but it's unused by app code.

`/health` aggregates `GET /health` against all 8 in parallel. Updates `backend_service_health` Prometheus gauge.

No RabbitMQ, no Postgres, no Redis-as-cache used by app code. `redis_url` from settings is consumed only by slowapi as the rate-limit backend. Compose `depends_on: postgres + redis` is currently superfluous for runtime correctness. See [[../concepts/Message-Queue-Topics]].

## RabbitMQ

Not used. No `aio_pika` / `pika` imports in `app/`.

## DB tables

None. User store is `USERS_DB: dict[str, UserInDB]` in process memory (`app/auth_models.py:380`). Wiped on restart. Production logs `CRITICAL` warning at startup but does not refuse to boot.

## Used by

- **[[frontend]]** — all backend traffic. Vite proxies `/api` to `http://localhost:8000`.
- [[trading-engine]] CORS allow-list includes `http://api-gateway:8000` (`services/trading-engine/app/config.py:527`) — passive only, no outbound.
- Compose: frontend `depends_on: api-gateway: service_healthy`.

No other service makes outbound HTTP calls to the gateway.

## Key files

- `app/main.py` — single 2071-line file with every route, middleware, WebSocket manager, Prometheus instrumentation. There's also a `main.py.backup_20251119_231853` next to it.
- `app/services/service_proxy.py` — `ServiceProxy` (httpx wrapper, response re-serialization, header-stripping for Content-Length/Encoding correctness, parallel health-check fan-out).
- `app/auth_models.py` — pydantic User/Token models, `_validate_jwt_secret()` with sys.exit in prod/staging, bcrypt rounds=14, in-memory `USERS_DB`. First registered user gets admin in development only.
- `app/auth_middleware.py` — `get_current_user` / `get_current_active_user` / `get_current_admin_user` Depends. `optional_auth` returns User|None.
- `app/config.py` — pydantic Settings; default backend URLs (port table fixed 2026-05-01 — comment at line 22 explains prior off-by-ones and a port collision at 8007).
- `app/security/rate_limiter.py` — RateLimitConfig + RateLimitMiddleware. **Rewritten 2026-07-29 to ACTUALLY enforce (was a no-op that only tagged an `X-RateLimit-Category` header — `/auth/login` brute-force protection was unlimited).** Now per-client fixed-window counting → HTTP 429 + `Retry-After` (`rate_limiter.py:382–506`). **Method-aware** (`_get_rate_limit_key`, `:414–446`): only mutating (`POST`/`PUT`/`PATCH`/`DELETE`) requests on `/api/trading`, `/api/portfolio/buy`, `/api/portfolio/sell` get the strict `trading_write` bucket (60/min); read polls fall through to `general`. New limits (`:61–64`): `trading_write` 60/min, auth 10/min, health 1200/min, general 1200/min — recalibrated so the dashboard's ~250–300 read-polls/min are never throttled (the old 30/10 would have 429'd normal use the moment enforcement went live). slowapi decorators remain but are legacy; the middleware does the enforcing. (Docstrings inside the file still cite the old 10/5/60/30 values — stale, ignore.)
- `app/security/input_validation.py` — `validate_symbol|quantity|price|interval|limit` + `ALLOWED_SYMBOLS` whitelist + SQL-injection blacklist.
- `app/security/security_headers.py` — HSTS / CSP / X-Frame-Options=DENY middleware + strict CORS.
- `Dockerfile` — multi-stage 3.12-slim, non-root `appuser`, `--workers 1` uvicorn.
- `requirements.txt` — fastapi==0.109.0 (see [[../concepts/Test-Setup-Gotchas]]).

## Gotchas

- **fastapi 0.109.0 pinned** because newer versions changed `HTTPBearer` auto_error response code. Tests must run inside container — host pip ships fastapi 0.136 → spurious 401-vs-403 mismatches. See [[../concepts/Test-Setup-Gotchas]].
- **Single-file 2071-line main.py.** No router decomposition. Backup file `main.py.backup_20251119_231853` lives alongside.
- **In-memory user DB** lost on container restart. Production gets `CRITICAL` log line, no refusal-to-boot.
- **JWT secret has two sources of truth** — pydantic Settings default in `app/config.py:58` (`"your-secret-key-change-in-production"`) versus env-var-only path in `auth_models.py:_validate_jwt_secret()`. The latter sys.exits in prod/staging if missing. Currently only the auth_models path is read, but the dual default is a landmine. See [[../decisions/ADR-003-bcrypt-sha256-prehash]] (note: ADR claim and code state diverge — see contradictions).
- **First registered user becomes admin** only in `IS_DEVELOPMENT` (`auth_models.py:447`). Other envs: no auto-admin, no documented provisioning.
- **Username blacklist** rejects `admin`, `root`, `system`, `null`, `undefined`, `administrator`, `superuser`, `api`, `www`, `mail`, `support`, `security`. Returns 422 from pydantic.
- **Logout is server-side no-op** — JWT stateless, no blacklist. `app/main.py:652`.
- **WebSocket broadcasts every 2s** regardless of clients/subscriptions. Earlier bug: broadcast loop proxied to a non-existent "api-gateway" service and 404-spammed logs every 2s — fixed 2026-05-01 by calling `aggregate_health_checks` directly. `app/main.py:240`.
- **Route order is load-bearing** — `/api/sentiment/aggregate` was unreachable until placed before `/api/sentiment/{symbol}` catch-all (fix 2026-05-01, comment at `:1861`).
- **buy/sell validation was bypassable** prior to 2026-05-01: `validate_X(x) if x else None` let callers omit fields. Symbol/quantity/price now required positionals. `:1331`.
- **Aggregator endpoints return generic 500s** on exception — comment at `:972` explains: don't echo `str(e)` (leaks stack/SQL/internal URLs). Server logs full detail.
- **Emergency stop bind-mount race** — if host `EMERGENCY_STOP` file doesn't exist when compose creates the bind-mount, Docker materializes a *directory* at the mount point. Handler detects this and returns 500, doesn't silently no-op. `:1404`.
- **`Path.write_text`** for emergency stop bypasses `builtins.open`. Tests must `mock.patch("pathlib.Path.write_text")`. See [[../concepts/Test-Setup-Gotchas]].
- **`backend_service_health` gauge updated only on `/health` calls**, not by WebSocket broadcaster — Grafana lag is `/health` polling interval.
- **Prometheus path normalization** is hand-rolled regex (`:373`). New symbol patterns (e.g. perp suffixes) could explode label cardinality.
- **Dead deps** in `requirements.txt`: asyncpg, sqlalchemy, aioredis, fastapi-cache2 are listed but never imported in `app/`. Inflates image without function.
- **Header-stripping in proxy is intentional** — only `x-request-id`, `x-trace-id`, `x-correlation-id` forwarded. Forwarding upstream `Content-Length`/`Content-Encoding` would break the re-serialized JSON body. `app/services/service_proxy.py:118`.

## Contradictions vs CLAUDE.md

1. **"No `v1` prefix despite older docs"** ([[../decisions/ADR-007-no-v1-api-prefix]]) — partially false. The canonical paths follow the rule, but a `/api/v1/...` compatibility layer (9 routes) at `app/main.py:1960`–`:2029` is reachable. Frontend doesn't use them, but they're documented in OpenAPI. ADR should call them out as legacy shims.
2. **[[../decisions/ADR-003-bcrypt-sha256-prehash]]** — code uses plain `CryptContext(schemes=["bcrypt"], bcrypt__rounds=14)`. **No bcrypt_sha256 scheme, no manual SHA256 prehash.** Either the ADR is aspirational/unfinished or there's a regression. bcrypt's 72-byte input cap silently truncates long passwords without a prehash — security-relevant gap.
3. **CLAUDE.md "JWT secret via env vars or Vault"** — `app/config.py:58` ships an insecure default `"your-secret-key-change-in-production"` that pydantic Settings will silently use if env unset. Currently no read path actually consumes it (auth uses the env-only path), but the dual-source split could become exploitable on a future refactor.
4. **CLAUDE.md "Frontend → backend routing, auth"** understates the surface. Gateway also does:
   - Multi-service fan-out aggregation (`/api/trading/signals/enhanced`, `/api/dashboard/{symbol}`, `/api/ml/predict/signal`)
   - WebSocket broadcast loop with 2s cadence
   - Prometheus metrics middleware + `/metrics` endpoint
   - Local consensus computation (BUY/SELL/HOLD voting across signals)
   It is **not** a thin pass-through.
5. **Validated symbols** — CLAUDE.md says BTC/ETH/SOL/BNB/ADA. Concrete list lives in `app/security/input_validation.py:ALLOWED_SYMBOLS`. Verify match in [[../concepts/Validated-Symbols]] follow-up.
6. **Domains** in CLAUDE.md ("portfolio, trading, risk, market, analysis, ml, sentiment, dashboard, performance") — confirmed. Plus undocumented `/api/trading/phase1/*` (3 routes) and `/auth/*` (4 routes).

## Related

- Flows: [[../flows/Signal-Pipeline]] · [[../flows/Order-Lifecycle]] · [[../flows/Emergency-Stop]]
- Concepts: [[../concepts/Risk-Model]] · [[../concepts/Trading-Mode-Flags]] · [[../concepts/Auto-Trader]] · [[../concepts/Test-Setup-Gotchas]] · [[../concepts/Message-Queue-Topics]]
- Decisions: [[../decisions/ADR-003-bcrypt-sha256-prehash]] · [[../decisions/ADR-005-emergency-stop-file-flag]] · [[../decisions/ADR-007-no-v1-api-prefix]] · [[../decisions/ADR-001-LSTM-removed]]
- Services: [[bybit-connector]] · [[market-data-service]] · [[technical-analysis]] · [[trading-engine]] · [[portfolio-manager]] · [[risk-metrics-service]] · [[ml-prediction-service]] · [[sentiment-analysis-service]] · [[notification-service]] · [[ml-retraining-service]] · [[frontend]]

## Corrections 2026-07-29

Reflects the 2026-07-29 production audit (verified in source):

- **Mode-gated auth added to state-changing endpoints** (`auth_middleware.py:40–173`, wired in `main.py`): trading start/stop (`:1436/:1455`, admin), portfolio buy/sell (`:1714/:1760`, active), circuit-breaker reset (`:1974`, admin), emergency-stop (`:1798`, admin), `signals/{s}/analyze` (`:1020`, active), ml train (`:2134`, active). Enforced in LIVE/prod/staging or `REQUIRE_API_AUTH=true`, open in local paper mode. `/auth/me` + `/auth/logout` stay strict. See *Overview*. These were previously drivable by anyone on the network.
- **Rate limiting is now real** (`rate_limiter.py`), method-aware, with recalibrated ceilings (trading_write 60, auth 10, health/general 1200). See the `rate_limiter.py` key-file entry. Was a no-op header-tagger.
- **CORS credentialed-wildcard closed on the 8 cookieless backend services** (`allow_credentials=False` on market-data, technical-analysis, portfolio-manager, risk-metrics, notification, ml-prediction, ml-retraining, tournament-harness `main.py`). Note: the **api-gateway itself keeps `allow_credentials=True`** because it uses a scoped, non-wildcard origin allow-list (`security_headers.py:252–260`) — spec-valid; the audit item was about the wildcard-origin backends, not the gateway.
