# External Integrations

**Analysis Date:** 2026-05-12

## APIs & External Services

**Exchange (sole exchange in scope):**
- Bybit — REST + WebSocket
  - SDK/Client: `pybit==5.6.2` (REST) + `websockets==12.0` (streams)
  - Wrapper service: `services/bybit-connector/` (port 8001)
  - Selector flag: `BYBIT_TESTNET` (default `false` in `docker-compose.unified.yml`) — `false` → mainnet (`api.bybit.com`), `true` → testnet (`api-testnet.bybit.com`). Drives URL selection inside `services/bybit-connector/app/config.py`.
  - Auth env vars: `BYBIT_API_KEY`, `BYBIT_API_SECRET` — propagated to `bybit-connector` and `ml-prediction-service` containers
  - Tape-replay mode for tests: `MARKET_DATA_SOURCE=tape`, fixtures at `./tests/fixtures/tape:/app/tests/fixtures/tape:ro` (bind-mounted RO into bybit-connector)
  - Trading-engine has its own adapter at `services/trading-engine/app/exchanges/bybit_adapter.py` for order placement

**News / social (sentiment-analysis-service, port 8008, idle by default):**
- NewsAPI — crypto news headlines
  - Client: `newsapi-python==0.2.7`
  - Auth: `NEWS_API_KEY`
- Twitter API v2 — social sentiment
  - Client: `tweepy==4.14.0`
  - Auth: `TWITTER_BEARER_TOKEN`
- Container env: `SKIP_ML_MODEL` toggles transformers/torch path (lexicon-only fallback)
- Sentiment build historically fails on PyPI read timeouts — retry single-service build or `--no-deps`

## Data Storage

**Databases:**
- PostgreSQL 15 (alpine) — application state
  - Container: `crypto-bot-postgres` (`postgres:15-alpine`), port 5432
  - DB: `cryptobot` (default), user `cryptobot`
  - Driver: `asyncpg==0.29.0` (sync fallback `psycopg2-binary==2.9.9`), ORM `sqlalchemy==2.0.25`, migrations `alembic==1.13.1`
  - Consumers: api-gateway (auth/sessions), trading-engine, portfolio-manager (`USE_DATABASE=true`)
  - Auto-applied init: `infrastructure/scripts/init-db.sql`, migrations `003_portfolios_orm_align.sql` + `004_positions_orm_align.sql`
  - Env: `POSTGRES_HOST=postgres`, `POSTGRES_PORT=5432`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`. Single source of truth in trading-engine after 2026-04-27 audit (legacy `DB_*` deprecated).
- TimescaleDB (PG15) — time-series candles/tickers
  - Container: `crypto-bot-timescaledb` (`timescale/timescaledb:latest-pg15`), host port 5433
  - DB: `market_data`
  - Consumers: market-data-service (writer/reader), tournament-harness (read-only user `tournament_reader`)
  - Init: `infrastructure/scripts/init-timescale.sql`
  - Mixed testnet/mainnet history before 2026-04-25 — wipe `klines` / `tickers` before backtests over older candles

**File Storage:**
- Local filesystem only (no S3/GCS integration detected)
- Per-service `logs/` bind-mounted into `/app/logs`
- ML models at `services/ml-prediction-service/models/` (RW bind-mounted)
- Notification record log at `tests/.notifications.log` (RW bind-mount for test fixture parity)

**Caching:**
- Redis 7 (alpine)
  - Container: `crypto-bot-redis`, port 6379, `--maxmemory 256mb allkeys-lru`, AOF on, password-protected
  - Async client: `aioredis==2.0.1`; sync `redis==5.0.1`
  - Used by: api-gateway (rate limiting via slowapi + limits), bybit-connector, market-data, portfolio-manager, technical-analysis, trading-engine, notification-service, risk-metrics
  - Env: `REDIS_HOST=redis`, `REDIS_PORT=6379`, `REDIS_PASSWORD`
  - Note: market-data caches in TimescaleDB, not Redis — Redis empty in normal testing

## Message Broker

**RabbitMQ 3 (management edition):**
- Container: `crypto-bot-rabbitmq` (`rabbitmq:3-management-alpine`), AMQP 5672, mgmt UI 15672
- vhost: `cryptobot` (env `RABBITMQ_VHOST`)
- Auth env: `RABBITMQ_USER`, `RABBITMQ_PASSWORD`
- Sync client `pika==1.3.2` is declared in bybit-connector, market-data, portfolio-manager, technical-analysis, trading-engine `requirements.txt`
- Async client `aio_pika` is **probed but optional** — `services/trading-engine/app/core/health.py:421-445` does `try: import aio_pika` and reports component error `"aio_pika not available (optional)"` if missing. No production publish/consume code path uses RabbitMQ at present — inter-service traffic is HTTP (see below). RabbitMQ is provisioned, healthy, and effectively idle except for health-probing.
- **Sentiment leg explicitly removed from signal pipeline** in commits `c346483`, `acae081`, `fe941cf`, `c171bb0` — the aggregator no longer consumes sentiment events; sentiment-analysis-service remains in compose but is profile-gated (`--profile analytics`).

## Authentication & Identity

**API auth (api-gateway, port 8000):**
- Implementation: custom JWT in `services/api-gateway/app/`
- Libraries: `pyjwt[crypto]>=2.10.1` (replaces unmaintained python-jose), `cryptography>=46.0.0`
- Password hashing: `libpass[bcrypt]==1.9.3` (passlib successor) + `bcrypt==5.0.0`
- Bearer header via FastAPI `HTTPBearer` — note `0.109` returns 403 on missing token, `0.136` (host pip) returns 401; tests pin against the deployed 0.109 behavior — run api-gateway tests inside the container
- Admin-guarded routes need the `admin_client` fixture (`services/api-gateway/tests/conftest.py`) overriding `get_current_admin_user` + `get_current_active_user`
- No third-party identity provider (no OAuth/Auth0/Cognito)
- Secret backend: HashiCorp Vault available (`shared/vault_client.py`, `shared/vault_config.py`, `infrastructure/vault/`) — opt-in

## Monitoring & Observability

**Metrics:**
- Prometheus (`prom/prometheus:latest`, port 9090, `--profile monitoring`)
  - Config: `infrastructure/monitoring/prometheus.yml`
  - Alerts: `infrastructure/monitoring/alerts.yml`
  - 15-day TSDB retention
- Per-service `/metrics` endpoint via `prometheus-client==0.19.0` (bybit-connector, market-data, ta, ml-prediction, notification, risk-metrics)

**Dashboards:**
- Grafana (`grafana/grafana:latest`, host port 3001 → container 3000, `--profile monitoring`)
  - Provisioning: `infrastructure/monitoring/grafana/provisioning/`
  - Dashboards: `infrastructure/monitoring/grafana/dashboards/`
  - Default plugins: `grafana-clock-panel`, `grafana-piechart-panel`
  - Env: `GRAFANA_USER`, `GRAFANA_PASSWORD`, `GRAFANA_ROOT_URL`

**Error Tracking:**
- No Sentry/Rollbar/Bugsnag detected — error reporting via structured logs (`python-json-logger==2.0.7`) to per-service log files (`/app/logs`)

**Logs:**
- Structured JSON via `python-json-logger`
- Each service writes to bind-mounted `./services/<svc>/logs/`
- Frontend logs via browser console only

## CI/CD & Deployment

**Hosting (production):**
- Kubernetes (`infrastructure/kubernetes/` manifests, Helm chart in `infrastructure/helm/`)
- Oracle Cloud bootstrap: `oracle-cloud-setup.sh`
- Production compose: `docker-compose.prod.yml`, `infrastructure/production/`

**CI Pipeline:**
- GitHub Actions assumed (per `crypto-trading-bot/CLAUDE.md` references to CI env passthrough for `NOTIFICATION_TEST_MODE=live`); workflow files under `.github/workflows/` (not enumerated here)

**Image builds:**
- `build-all.sh` at repo root builds every service image
- BuildKit hangs on WSL2 — `DOCKER_BUILDKIT=0` workaround

## Notification Integrations (notification-service, port 8006)

| Channel | Library | Required env | File |
|---|---|---|---|
| Telegram | `httpx==0.27.0` (Bot API direct) | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | `services/notification-service/app/telegram_notifier.py` |
| Email / SMTP | stdlib `smtplib` (no extra dep) | SMTP host/port/user/pass via service `.env` | `services/notification-service/app/email_notifier.py`, `services/notification-service/app/channels/email_client.py` |
| Slack | `httpx==0.27.0` (webhook) | Slack webhook URL | (referenced in env_file; client code in `services/notification-service/app/`) |
| SMS | `twilio==8.10.0` | Twilio account/SID/from-number | `services/notification-service/app/channels/sms_client.py` |

**Test-mode interception:** `NOTIFICATION_TEST_MODE` env switches between `record` (writes to `tests/.notifications.log`, default for local dev) and `live` (real provider POST). Without this, host pytest fixture watches a file the container never writes → integration test hangs. CI overrides to `live`.

**Real Telegram/Slack/SMTP creds live in `services/notification-service/.env`** (gitignored, mounted as `env_file:`). Compose `environment:` overrides win over `env_file:`.

## Internal Service-to-Service Communication

**All inter-service calls are HTTP/JSON over the `crypto-bot-network` bridge** (no RabbitMQ pub/sub in the live signal path — see Message Broker note above). Client: `httpx==0.27.0` async.

**Service URL env vars (compose `environment:` block):**

| Caller | Target var | Value |
|---|---|---|
| api-gateway → all | `BYBIT_CONNECTOR_URL` | `http://bybit-connector:8001` |
| | `MARKET_DATA_URL` | `http://market-data:8002` |
| | `PORTFOLIO_MANAGER_URL` | `http://portfolio-manager:8003` |
| | `TECHNICAL_ANALYSIS_URL` | `http://technical-analysis:8004` |
| | `TRADING_ENGINE_URL` | `http://trading-engine:8005` |
| | `NOTIFICATION_URL` | `http://notification-service:8006` |
| | `ML_PREDICTION_URL` | `http://ml-prediction:8007` |
| | `SENTIMENT_ANALYSIS_URL` | `http://sentiment-analysis:8008` |
| | `RISK_METRICS_URL` | `http://risk-metrics:8009` |
| market-data → bybit-connector | `BYBIT_CONNECTOR_URL` | `http://bybit-connector:8001` |
| portfolio-manager → bybit, te, market-data | `BYBIT_CONNECTOR_URL`, `TRADING_ENGINE_URL`, `MARKET_DATA_URL` | (set explicitly in compose — without them config falls back to `localhost:*` and 60s sync poll fails) |
| technical-analysis → bybit, market-data | `BYBIT_CONNECTOR_URL`, `MARKET_DATA_URL` | http://bybit-connector:8001, http://market-data:8002 |
| trading-engine → bybit, market-data, portfolio, ta, ml, sentiment, notification | seven URL envs | `NOTIFICATION_SERVICE_URL=http://notification-service:8006` was missing historically — defaulted to `localhost:8006` and silently failed inside Docker |
| risk-metrics → trading-engine, portfolio | `TRADING_ENGINE_URL`, `PORTFOLIO_MANAGER_URL` | http://trading-engine:8005, http://portfolio-manager:8003 |
| ml-prediction → market-data | `MARKET_DATA_URL` | http://market-data:8002 |

**REST routing conventions (gateway):** `/api/<domain>/<resource>` — domains `portfolio`, `trading`, `risk`, `market`, `analysis`, `ml`, `sentiment`, `dashboard`, `performance`. No `v1` prefix despite older docs. Async handlers throughout. Live surface: `http://localhost:8000/openapi.json`.

**Health probes:** Every service exposes `GET /health` and `GET /ready`. trading-engine's `health.py` additionally probes Redis, Postgres, RabbitMQ, and downstream services.

## Config Flag Matrix (operational gates)

Listed in order of precedence to LIVE money:

| Flag | Default (compose) | Operator override (`.env`) | Effect |
|---|---|---|---|
| `BYBIT_TESTNET` | `false` | (varies) | `false` = mainnet REST/WS endpoints (real prices). `true` = testnet (`api-testnet.bybit.com`). Consumed by bybit-connector and ml-prediction-service. |
| `PAPER_TRADING_MODE` | `true` | `true` | `true` = trading-engine simulates fills internally, no real orders. `false` is a prerequisite for live trading. |
| `TRADING_MODE` | (not in compose, default `PAPER` in service) | `PAPER` | Selects live-trading code path inside trading-engine. Must be `LIVE` for real orders. |
| `LIVE_TRADING_ACK` | (unset) | (unset) | Trading-engine **refuses to boot in LIVE mode** without `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY` (enforced at `services/trading-engine/app/main.py:251-258`). Added 2026-05 to catch env drift on cloud hosts. |
| `AUTO_TRADING_ENABLED` | `true` (compose, since 2026-05-06) | `true` (operator) | Auto-trader armed at boot. Loop only fires when `EMERGENCY_STOP` file is absent. |
| `EMERGENCY_STOP` (file gate) | file present at repo root | n/a | `./EMERGENCY_STOP` bind-mounted RW into api-gateway, RO into trading-engine at `/app/EMERGENCY_STOP`. Path configurable via `EMERGENCY_STOP_FILE`. `touch EMERGENCY_STOP` halts auto-trader; `rm EMERGENCY_STOP` resumes. `POST /api/portfolio/emergency-stop` (admin-guarded) writes through `pathlib.Path.write_text` (must patch `pathlib.Path.write_text` in tests, not `builtins.open`). |
| `ENABLE_ML_PREDICTIONS` | `false` (compose) | `false` | When `true`, trading-engine aggregator consumes ml-prediction. Gated `false` because V0 directional-accuracy metric had look-ahead leakage; post-fix (`c56765c`) models score chance-level. Re-enable only after rebuild + DSR > 0.95. ml-prediction-service also gated behind `--profile ml`. |
| `ENABLE_SENTIMENT_ANALYSIS` | `false` (compose) | `false` | Sentiment leg removed from pipeline (commits `c346483`, `acae081`, `fe941cf`, `c171bb0`). sentiment-analysis-service runs only with `--profile analytics`. |
| `STRATEGY_MODE` | `ensemble` | — | `ensemble` = SimpleRSI + multi-indicator + mean-reversion (performance-weighted). |
| `MAX_RISK_PER_TRADE` | `0.10` (compose, paper) | — | **Paper-only relaxation per ADR-010 (2026-05-06)** to clear Bybit min-notional on $100 balance. **Must restore ≤ 0.02 before flipping `TRADING_MODE=LIVE`.** |
| `MAX_POSITION_SIZE_PCT` | `10.0` | — | Pairs with `MAX_RISK_PER_TRADE`. |
| `EMERGENCY_STOP_LOSS` | `0.05` | — | 5% daily-loss circuit breaker (always on). |
| `PAPER_INITIAL_BALANCE` | `100.0` | — | Starting USDT for paper portfolio. |
| `LEVERAGE_ENABLED` / `DEFAULT_LEVERAGE` / `MAX_LEVERAGE` / `MIN_LEVERAGE` | `true` / `10.0` / `20.0` / `1.0` | — | Paper-trading only (2026-05-09). At 10% × $100 × 10x = $100 notional. **Must drop `DEFAULT_LEVERAGE` to 1.0 before LIVE.** |
| `NOTIFICATION_TEST_MODE` | `record` | — | `record` writes to `tests/.notifications.log` (host-visible). CI sets to `live` for real provider POSTs. |
| `NOTIFICATION_RECORD_PATH` | `tests/.notifications.log` | — | Where record-mode appends. |

**Four-step path to LIVE money (no shortcuts):**
1. `PAPER_TRADING_MODE=false`
2. `TRADING_MODE=LIVE`
3. Mainnet `BYBIT_API_KEY` / `BYBIT_API_SECRET` with trade permissions
4. `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY` (service-boot guard at `services/trading-engine/app/main.py:251`)

Additionally **revert** `MAX_RISK_PER_TRADE` to ≤ 0.02 and `DEFAULT_LEVERAGE` to 1.0 per pre-live checklist before step 1.

## Validated Trading Symbols

5 active as of 2026-05-03: **BTC, ETH, SOL, BNB, ADA**. XRP / DOGE excluded by paper-trading data — no silent re-add. BTC + ETH re-added 2026-05-03 (trading-engine `trading_symbols` already had them; market-data `default_symbols` did not until that date).

## Environment Configuration

**Templates (in repo, safe to read):**
- `.env.example` (dev defaults)
- `.env.production.example`
- `.env.test.example`
- `services/notification-service/.env.example`
- `headless.env.example`

**Live secrets (gitignored — never committed):**
- `/.env` — Bybit keys, operator overrides
- `services/notification-service/.env` — Telegram/Slack/SMTP/Twilio creds

**Required env vars (minimum to boot real prices, simulated orders):**
- `BYBIT_API_KEY`, `BYBIT_API_SECRET` (mainnet, read-only OK for prices)
- `BYBIT_TESTNET=false`
- `PAPER_TRADING_MODE=true`
- `POSTGRES_PASSWORD`, `TIMESCALE_PASSWORD`, `REDIS_PASSWORD`, `RABBITMQ_PASSWORD` (override dev defaults)
- `JWT_SECRET_KEY` (api-gateway)

**Secrets backend:** HashiCorp Vault opt-in (`shared/vault_client.py`, `infrastructure/vault/`). Otherwise raw env vars.

## Webhooks & Callbacks

**Incoming:**
- None detected — no inbound webhook endpoints from third parties. Bybit private data is pulled via REST/WS, not pushed.

**Outgoing:**
- Telegram Bot API send-message calls (notification-service)
- Slack webhook POSTs (notification-service)
- Twilio SMS (notification-service, optional)
- SMTP outbound (notification-service)
- Bybit REST/WS (bybit-connector — order placement, market data)

## Webhook & Callback URLs to External Services

| Direction | Endpoint | Used by |
|---|---|---|
| Out | `https://api.bybit.com/*` (mainnet) or `https://api-testnet.bybit.com/*` | bybit-connector, ml-prediction-service |
| Out | `wss://stream.bybit.com/*` | bybit-connector, market-data |
| Out | `https://api.telegram.org/bot<token>/sendMessage` | notification-service |
| Out | `https://hooks.slack.com/services/*` | notification-service |
| Out | `https://api.twilio.com/2010-04-01/Accounts/*` | notification-service |
| Out | `https://newsapi.org/v2/*` | sentiment-analysis-service (idle) |
| Out | `https://api.twitter.com/2/*` | sentiment-analysis-service (idle) |

---

*Integration audit: 2026-05-12*
