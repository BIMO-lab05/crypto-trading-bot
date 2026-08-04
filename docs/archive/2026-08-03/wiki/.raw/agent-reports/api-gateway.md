# api-gateway — raw report

Service path: `services/api-gateway/`
Port: 8000
Stack: FastAPI 0.109.0 / Python 3.12 / Starlette 0.35.1 / httpx 0.27.0 / passlib+bcrypt / python-jose / slowapi
Container hostname (compose): `api-gateway`
Compose file block: `docker-compose.unified.yml:245`
Source main: `services/api-gateway/app/main.py` (2071 lines, single-file)

## Endpoints

All routes are decorator-defined on the `app` object in `app/main.py` (no APIRouter). Below excludes `/health`, `/ready`, `/metrics`, `/`, `/docs`.

Auth (rate-limit 5/min):
- `POST /auth/register` — register user, returns User. `app/main.py:582`
- `POST /auth/login` — username+password to JWT bearer. `app/main.py:603`
- `GET  /auth/me` — current user, requires Bearer. `app/main.py:637`
- `POST /auth/logout` — stateless (client deletes token). `app/main.py:647`

Market (proxy → market-data:8002, /api/v1/...):
- `GET /api/market/ticker/{symbol}` — `app/main.py:669` (transforms response keys)
- `GET /api/market/kline/{symbol}` — `app/main.py:714`
- `GET /api/market/klines/{symbol}` — alias of above. `app/main.py:741`

Technical analysis (proxy → technical-analysis:8004):
- `GET /api/analysis/rsi/{symbol}` — `app/main.py:763`
- `GET /api/analysis/macd/{symbol}` — `app/main.py:784`
- `GET /api/analysis/all/{symbol}` — `app/main.py:800`
- `GET /api/analysis/multi-timeframe/{symbol}` — `app/main.py:1831`
- `GET /api/analysis/indicators/signal/{symbol}` — `app/main.py:1845`

Trading engine (proxy → trading-engine:8005, mostly /api/v1/...):
- `GET  /api/trading/signals/{symbol}` — `app/main.py:821`
- `GET  /api/trading/signals/enhanced/{symbol}` — fan-out aggregator across TA + ML + multi-tf + signal, computes consensus locally. `app/main.py:837`
- `POST /api/trading/signals/{symbol}/analyze` — `app/main.py:982`
- `GET  /api/trading/positions` — `app/main.py:1002`
- `GET  /api/trading/status` — `app/main.py:1023`
- `GET  /api/trading/performance` — `app/main.py:1033`
- `POST /api/trading/start` — start auto-trader (added 2026-05-01). `app/main.py:1049`
- `POST /api/trading/stop` — stop auto-trader. `app/main.py:1060`
- `GET  /api/trading/trades/history` — `app/main.py:1071`
- `GET  /api/trading/equity-curve` — `app/main.py:1113`
- `GET  /api/trading/drawdown` — `app/main.py:1125`
- `GET  /api/trading/returns-distribution` — `app/main.py:1137`
- `GET  /api/trading/correlations` — `app/main.py:1153`
- `GET  /api/trading/statistics` — `app/main.py:1175`
- `GET  /api/trading/phase1/metrics` — `app/main.py:1195`
- `GET  /api/trading/phase1/health` — `app/main.py:1213`
- `GET  /api/trading/phase1/latest` — `app/main.py:1223`

Portfolio (proxy → portfolio-manager:8003):
- `GET  /api/portfolio` — `app/main.py:1238`
- `GET  /api/portfolio/balance` — `app/main.py:1251`
- `GET  /api/portfolio/holdings` — `app/main.py:1264`
- `GET  /api/portfolio/performance` — `app/main.py:1277`
- `GET  /api/portfolio/trades` — `app/main.py:1290`
- `POST /api/portfolio/buy` — `app/main.py:1313`
- `POST /api/portfolio/sell` — `app/main.py:1354`
- `POST /api/portfolio/emergency-stop` — admin-only. Writes `EMERGENCY_STOP` file via `pathlib.Path.write_text`. `app/main.py:1387`

Risk / metrics (proxy → risk-metrics:8009, paths NOT under `/api/v1`):
- `GET  /api/risk/scorecard` — `app/main.py:1452`
- `GET  /api/risk/capital` — `app/main.py:1462`
- `GET  /api/risk/exposure` — `app/main.py:1472`
- `GET  /api/risk/drawdown` — `app/main.py:1482`
- `GET  /api/risk/var` — `app/main.py:1492`
- `GET  /api/risk/alerts` — `app/main.py:1542`
- `GET  /api/risk/circuit-breaker` — `app/main.py:1552`
- `POST /api/risk/circuit-breaker/reset` — `app/main.py:1562`
- `GET  /api/performance/metrics` — `app/main.py:1522`
- `GET  /api/performance/sharpe` — `app/main.py:1532`

ML prediction (proxy → ml-prediction:8007):
- `GET  /api/ml/predict/price/{symbol}` — `app/main.py:1577` (model_type whitelisted to GRU only)
- `GET  /api/ml/predict/trend/{symbol}` — `app/main.py:1601`
- `GET  /api/ml/predict/volatility/{symbol}` — `app/main.py:1617`
- `GET  /api/ml/predict/signal/{symbol}` — `app/main.py:1633` (computes BUY/SELL/HOLD locally from upstream `directional_strength`)
- `GET  /api/ml/models` — `app/main.py:1682`
- `GET  /api/ml/models/{symbol}` — `app/main.py:1692`
- `POST /api/ml/models/train` — `app/main.py:1710`
- `GET  /api/ml/models/compare/{symbol}` — `app/main.py:1743`

Sentiment (proxy → sentiment-analysis:8008):
- `GET /api/sentiment/news/{symbol}` — `app/main.py:1764`
- `GET /api/sentiment/social/{symbol}` — `app/main.py:1778`
- `GET /api/sentiment/combined/{symbol}` — `app/main.py:1792`
- `GET /api/sentiment/trend/{symbol}` — `app/main.py:1806`
- `GET /api/sentiment/aggregate` — declared BEFORE `{symbol}` catch-all (route-order bugfix 2026-05-01). `app/main.py:1866`
- `GET /api/sentiment/{symbol}` — backward-compat catch-all. `app/main.py:1878`

Aggregation:
- `GET /api/dashboard/{symbol}` — fan-out: ticker + signal + portfolio. `app/main.py:1897`

V1 compatibility shims (delegate to non-v1 handlers above):
- `GET /api/v1/market/ticker/{symbol}` — `app/main.py:1960`
- `GET /api/v1/market/klines/{symbol}` — `app/main.py:1967`
- `GET /api/v1/analysis/rsi/{symbol}` — `app/main.py:1974`
- `GET /api/v1/analysis/macd/{symbol}` — `app/main.py:1981`
- `GET /api/v1/analysis/all/{symbol}` — `app/main.py:1988`
- `GET /api/v1/ml/predict/{symbol}` — `app/main.py:1995`
- `GET /api/v1/ml/predict/price/{symbol}` — `app/main.py:2002`
- `GET /api/v1/portfolio/balance` — `app/main.py:2011`
- `GET /api/v1/portfolio/holdings` — `app/main.py:2018`
- `GET /api/v1/portfolio/positions` — `app/main.py:2025`

WebSocket:
- `WS /ws` — accepts client, server-pushes `dashboard_update` every 2s (health + portfolio.balance via ServiceProxy). Responds to `"ping"` text with pong. `app/main.py:2037`

Counts: 9 auth/utility (2 in `/auth`, 4 health/root/metrics, plus 1 ws), and 70+ API routes. Excluding /health, /ready, /, /metrics, /docs: ~73 routes (incl. `/ws` + 9 v1 compat shims).

## Internal deps

api-gateway is purely an outbound HTTP proxy. No outbound RabbitMQ / DB calls.

httpx.AsyncClient against (`app/services/service_proxy.py:25`):
- `bybit` → `BYBIT_CONNECTOR_URL` (compose: `http://bybit-connector:8001`) — declared in services map but no handler currently routes to it.
- `market-data` → `MARKET_DATA_URL` (compose: `http://market-data:8002`)
- `technical-analysis` → `TECHNICAL_ANALYSIS_URL` (compose: `http://technical-analysis:8004`)
- `trading-engine` → `TRADING_ENGINE_URL` (compose: `http://trading-engine:8005`)
- `portfolio-manager` → `PORTFOLIO_MANAGER_URL` (compose: `http://portfolio-manager:8003`)
- `risk-metrics` → `RISK_METRICS_URL` (compose: `http://risk-metrics:8009`)
- `ml-prediction` → `ML_PREDICTION_URL` (compose: `http://ml-prediction:8007`)
- `sentiment-analysis` → `SENTIMENT_ANALYSIS_URL` (compose: `http://sentiment-analysis:8008`)

Compose also injects `NOTIFICATION_URL=http://notification-service:8006` but the value is unused in code (no handler, not in `ServiceProxy.services`).

Infra dependencies declared in compose (`postgres`, `redis` via `depends_on: service_healthy`) — but neither is touched at runtime by app code:
- No `asyncpg`/`sqlalchemy`/`aioredis` import inside `app/`. Despite `requirements.txt` listing asyncpg, sqlalchemy 2.0.25, aioredis 2.0.1, fastapi-cache2.
- `redis_url` in `app/config.py:86` is only consumed by slowapi's RateLimitConfig (rate limiter backend).

Health-check fan-out: gateway’s `/health` calls `proxy.aggregate_health_checks()` which `GET /health` against all 8 services concurrently (`app/services/service_proxy.py:180`).

## Used by

- **Frontend** (`frontend/`): all backend traffic flows through gateway. `frontend/src/services/api.js` line 7 documents Vite proxies to `http://localhost:8000`.
- **trading-engine** has `http://api-gateway:8000` allow-listed in its CORS config (`services/trading-engine/app/config.py:527`) — passive reference only, no outbound calls observed.
- **Compose**: frontend service `depends_on: api-gateway: service_healthy` (`docker-compose.unified.yml:328`).
- No other service imports or HTTP-calls api-gateway.

## RabbitMQ

Not used. No `aio_pika` / `pika` / `basic_publish` / queue or exchange declarations anywhere in `app/`. (Compose injects `RABBITMQ_*` env vars but app code ignores them.)

## DB tables

None directly accessed. The single `SELECT/INSERT/UPDATE/DELETE` hit in code is a string-blacklist literal in `app/security/input_validation.py:214` for SQL-injection detection in inputs.

User store is in-memory `USERS_DB: dict[str, UserInDB]` in `app/auth_models.py:380`. Lost on restart. Comment at top: `# WARNING: Replace with database in production!`.

No Alembic, no migrations, no asyncpg session — just pydantic models + in-process dict.

## Key files

- `app/main.py` (2071 lines) — every route + middleware + WebSocket manager + Prometheus instrumentation. Single file.
- `app/services/service_proxy.py` — `ServiceProxy` class wrapping a single shared `httpx.AsyncClient` (timeout=30s) with per-request URL build, response re-serialization, and `aggregate_health_checks` parallel fan-out. Strips upstream headers except `x-request-id`/`x-trace-id`/`x-correlation-id` (intentional — comment at line 118 explains content-length / encoding hazard).
- `app/auth_models.py` — pydantic User/UserCreate/UserLogin/Token, `_validate_jwt_secret()` (sys.exit on missing key in production/staging), bcrypt rounds=14, in-memory USERS_DB. First registered user gets admin in development only.
- `app/auth_middleware.py` — `get_current_user` / `get_current_active_user` / `get_current_admin_user` Depends-injected guards. `optional_auth` returns User|None.
- `app/config.py` — pydantic Settings, default backend service URLs (port table fixed 2026-05-01 — comment notes prior off-by-ones), JWT secret has insecure default `"your-secret-key-change-in-production"` (only used if env var unset and not loaded by `_validate_jwt_secret`).
- `app/security/rate_limiter.py` — slowapi RateLimitConfig + RateLimitMiddleware (Redis-backed when enabled).
- `app/security/input_validation.py` — `validate_symbol` / `validate_quantity` / `validate_price` / `validate_interval` / `validate_limit` + `ALLOWED_SYMBOLS` whitelist + SQL-injection char/keyword blacklist.
- `app/security/security_headers.py` — Starlette middleware adding HSTS / CSP / X-Frame-Options=DENY, plus `get_cors_config(...)` (strict, no wildcards).
- `Dockerfile` — multi-stage 3.12-slim, non-root `appuser`, healthcheck via curl /health, single uvicorn worker.
- `requirements.txt` — fastapi==0.109.0 (pinned, see Test gotcha below), bcrypt 4.1.2, passlib 1.7.4, slowapi 0.1.9, prometheus-client 0.19.0.
- `tests/conftest.py` + `tests/test_main.py` + `tests/test_gateway_80_coverage.py` — large test suite focused on coverage; uses `admin_client` fixture that overrides `get_current_admin_user`.

## Gotchas

- **Single-file 2071-line main.py.** Every route inline. There’s also a `main.py.backup_20251119_231853` next to it.
- **fastapi 0.109.0 pinned** because newer versions changed `HTTPBearer` auto_error to return 401 (RFC 6750) while service tests assert 403. Tests must run inside container, not host. (CLAUDE.md gotcha confirmed by code: `HTTPBearer()` instantiated with default `auto_error=True` in `auth_middleware.py:19`).
- **In-memory user DB** in production logs `"CRITICAL: Using in-memory user storage in PRODUCTION!"` but does not refuse to start. `auth_models.py:383`.
- **JWT secret has TWO sources of truth.** `app/config.py` defaults to `"your-secret-key-change-in-production"` (loaded from `JWT_SECRET_KEY` env via pydantic-settings). `app/auth_models.py:_validate_jwt_secret()` reads `os.environ["JWT_SECRET_KEY"]` directly, sys.exit if missing in prod/staging, falls back to `_DEV_ONLY_SECRET = "development-only-secret-not-for-production-use"`. The two paths can diverge silently if pydantic-settings sees one value and `os.environ` another (e.g. `.env` file via pydantic but not exported).
- **First user becomes admin** automatically — only in `IS_DEVELOPMENT` (`auth_models.py:447`). In other envs admin must be provisioned via separate process (none documented).
- **Username blacklist** rejects `admin`, `root`, `system`, `null`, `undefined`, `administrator`, `superuser`, `api`, `www`, `mail`, `support`, `security` (`auth_models.py:164`). Trying to register one of these returns 422 from pydantic before the route body runs.
- **Logout is a no-op on the server** — JWT is stateless, no blacklist. Comment: "Clients should delete their tokens." `app/main.py:652`.
- **WebSocket broadcasts every 2s regardless of subscriptions** — `start_broadcasting` runs forever, fetches dashboard data on a fixed cadence even with one connected client. Earlier bug logged about proxying to a non-existent "api-gateway" service in the broadcast loop; fixed 2026-05-01 by routing through `aggregate_health_checks` directly. `app/main.py:240`.
- **Route order matters** — `/api/sentiment/aggregate` was unreachable until placed before catch-all `/api/sentiment/{symbol}` (bug fixed 2026-05-01, comment at `app/main.py:1861`).
- **buy/sell validation was bypassable** — earlier `validate_X(x) if x else None` allowed callers to omit fields and reach proxy with None query params. Fixed 2026-05-01 by making symbol/quantity/price required positional params. `app/main.py:1331`.
- **Generic 500 messages on aggregator endpoints** — comment at `app/main.py:972` explicitly says don’t echo `str(e)` to client (leaks stack/SQL/internal URLs). Server logs full error.
- **Emergency stop bind-mount race** — if host `EMERGENCY_STOP` file doesn’t exist when `docker compose up` runs, Docker creates a *directory* at the mount point. The handler detects this and returns 500 with explanation, doesn’t silently no-op. `app/main.py:1404`.
- **`Path.write_text`** used for emergency stop, NOT `builtins.open`. Tests must `mock.patch("pathlib.Path.write_text")` (memory note + project CLAUDE.md gotcha).
- **`backend_service_health` Prometheus gauge** is only updated when `/health` is called — not by the WebSocket broadcaster. So Grafana lag tracks `/health` polling, not real-time.
- **Path normalization for metrics** is hand-rolled regex (`app/main.py:373`) — replaces UUIDs, `*USDT` symbols, and `/\d+/` ids. Risk: any new symbol pattern (e.g. perp suffix) explodes label cardinality.
- **`hostname: api-gateway`** in compose. Internal services reach it as `http://api-gateway:8000` (only trading-engine actually configures it, for CORS).
- **`requirements.txt` lists asyncpg / sqlalchemy / aioredis / fastapi-cache2** but no `import asyncpg|sqlalchemy|aioredis|fastapi_cache` anywhere in `app/`. Dead deps inflating image.
- **`include_in_schema=False`** on `/metrics` only. All 70+ business routes appear in OpenAPI (no auth-tagging discipline).

## Contradictions vs CLAUDE.md

1. **"REST: gateway routes are `/api/<domain>/<resource>` (no `v1` prefix despite older docs)"** — partially false. The canonical paths follow that rule (e.g. `/api/portfolio/balance`), BUT gateway also exposes a v1 compatibility layer at lines 1960-2029: `/api/v1/market/...`, `/api/v1/analysis/...`, `/api/v1/ml/predict/...`, `/api/v1/portfolio/...`. They delegate to the non-v1 handlers but they exist and are reachable. ADR-007 should note these as legacy shims, not claim v1 absence.
2. **ADR-003 ("bcrypt+sha256 prehash")** — code uses `CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=14)` (`auth_models.py:36`). No `bcrypt_sha256` scheme, no manual SHA256 prehash before bcrypt. Either the ADR is aspirational/not implemented, or this is an unfinished rollout. Worth flagging — bcrypt has a 72-byte input cap that triggers silent password truncation without a prehash.
3. **CLAUDE.md "validated symbols: BTC, ETH, SOL, BNB, ADA"** — `app/security/input_validation.py:ALLOWED_SYMBOLS` should be checked separately to confirm it matches. Not read here; flag for follow-up.
4. **CLAUDE.md "JWT secret via env vars or Vault. Bybit testnet keys only in repo."** — `app/config.py:58` ships an insecure default `"your-secret-key-change-in-production"` for `jwt_secret_key`. The other validator (`_validate_jwt_secret`) does sys.exit in prod/staging, but the pydantic Settings default would silently get used by anything reading `settings.jwt_secret_key` directly. Currently nothing in the gateway *does* read it (auth uses the env-var path), but the dual-source split is a future-bug landmine.
5. **CLAUDE.md "Frontend → backend routing, auth"** — accurate, but understates: gateway also does fan-out aggregation (enhanced signal, dashboard endpoint, WebSocket broadcast) and Prometheus metrics scraping. It's not a thin pass-through.
6. **"Domains: portfolio, trading, risk, market, analysis, ml, sentiment, dashboard, performance"** — confirmed by route prefixes. Plus undocumented `/api/trading/phase1/*` (3 routes) and `/auth/*` (4 routes).
