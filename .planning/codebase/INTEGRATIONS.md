# External Integrations

**Analysis Date:** 2026-05-22

## Exchange APIs

**Bybit (sole exchange — Binance adapter archived under `_archive_exchanges/`):**
- Role: price feed + order execution gateway
- Sole owner: `services/bybit-connector/` — all other services route through bybit-connector, never direct to Bybit
- SDK: pybit `5.6.2` (`services/bybit-connector/requirements.txt`)
- REST client: `services/bybit-connector/app/bybit_rest_client.py` via httpx `0.27.0`
- Auth: HMAC-SHA256 signed headers (timestamp + api_key + recv_window + body); implemented in `services/bybit-connector/app/auth.py`
- Env vars: `BYBIT_API_KEY`, `BYBIT_API_SECRET`
- Endpoint selection: `BYBIT_TESTNET=false` → `https://api.bybit.com`; `BYBIT_TESTNET=true` → `https://api-testnet.bybit.com`
- WebSocket: `wss://stream.bybit.com/v5/public/linear` (mainnet) / `wss://stream-testnet.bybit.com/v5/public/linear` (testnet); URL stored in `services/bybit-connector/app/config.py`; WS connection initiated in `services/bybit-connector/app/main.py` lifespan
- API version: Bybit V5 (`/v5/` paths in all REST calls)
- Rate limiting: slowapi + limits on bybit-connector ingress (`services/bybit-connector/requirements.txt`)
- Circuit breaker: `services/bybit-connector/app/circuit_breaker.py` (5 failures → open; 60s recovery)
- Tape replay mode: `MARKET_DATA_SOURCE=tape` replays JSONL fixtures from `tests/fixtures/tape/` via `services/bybit-connector/app/tape_replay_client.py`; used in integration tests / replay debugging
- Current state: `BYBIT_TESTNET=false` (mainnet prices), `PAPER_TRADING_MODE=true` (orders simulated)

**Bybit-connector internal HTTP API (intra-service, not external):**
- Direction: inbound from all other services
- Protocol: REST over internal Docker bridge network (`crypto-bot-network`)
- Endpoints exposed: account balance, positions, order placement/cancel, open orders, order history, ticker, klines, recent trades, orderbook, funding-rate history, instruments info, circuit-breaker status — see `services/bybit-connector/app/main.py`
- Auth: none (internal network only; CORS restricted to internal origins)
- Consumers: market-data-service, technical-analysis, trading-engine, portfolio-manager, api-gateway, scripts

## Data Storage

**PostgreSQL 15 (application state database):**
- Image: `postgres:15-alpine` (`docker-compose.unified.yml`)
- Container: `crypto-bot-postgres`, hostname `postgres`, port `5432` (host-exposed at `${POSTGRES_PORT:-5432}`)
- Env vars: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` (default: `cryptobot`)
- Schema init: `infrastructure/scripts/init-db.sql` mounted as docker entrypoint
- Migrations: SQL files `infrastructure/migrations/001_initial_schema.sql` through `005_tournament_reader.sql`; migrations 003 and 004 mounted directly as init scripts in compose; migration 005 adds read-only `tournament_reader` role
- ORM migrations: Alembic used in trading-engine, portfolio-manager, market-data-service (no alembic dirs found — migrations are SQL-only)
- Consumers: api-gateway (auth tokens/sessions), trading-engine (trades, positions), portfolio-manager (portfolios, positions, P&L), market-data-service (secondary), notification-service (alert storage)
- Connection: asyncpg `0.29.0`/`0.31.0` (async) + psycopg2-binary `2.9.9` (sync fallback); SQLAlchemy `2.0.x` ORM

**TimescaleDB (market data time-series):**
- Image: `timescale/timescaledb:latest-pg15` (`docker-compose.unified.yml`)
- Container: `crypto-bot-timescaledb`, hostname `timescaledb`, port `5433` (host-exposed)
- Env vars: `TIMESCALE_USER`, `TIMESCALE_PASSWORD`, `TIMESCALE_DB` (default: `market_data`)
- Schema init: `infrastructure/scripts/init-timescale.sql` — creates hypertables for `market_data.candles`, `market_data.ticks`, `market_data.orderbook_snapshots`, `market_data.indicators`; continuous aggregates for OHLCV
- Consumers: market-data-service (primary writer), tournament-harness (read-only via `tournament_reader` role), technical-analysis (reads klines)
- Note: mixed testnet/mainnet history before 2026-04-25 (flip date); filter `is_mainnet=true` for clean backtesting
- Connection: asyncpg (same driver as PostgreSQL)

**Redis 7:**
- Image: `redis:7-alpine` (`docker-compose.unified.yml`)
- Container: `crypto-bot-redis`, hostname `redis`, port `6379` (host-exposed at `${REDIS_PORT:-6379}`)
- Config: password-protected, `appendonly yes`, `maxmemory 256mb`, `allkeys-lru` eviction
- Env vars: `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`
- Used for: session storage (api-gateway), rate-limit state (api-gateway slowapi backend), indicator caching (technical-analysis), prediction caching (ml-prediction-service)
- Note: in practice observed empty during testing; TimescaleDB is the canonical market-data cache
- Connection: aioredis `2.0.1` (async), redis `5.0.1` (sync)

**RabbitMQ 3 (AMQP message broker):**
- Image: `rabbitmq:3-management-alpine` (`docker-compose.unified.yml`)
- Container: `crypto-bot-rabbitmq`, hostname `rabbitmq`, ports `5672` (AMQP) + `15672` (management UI)
- Env vars: `RABBITMQ_USER`, `RABBITMQ_PASSWORD`, `RABBITMQ_VHOST` (default: `cryptobot`)
- Used for: inter-service event publishing (bybit-connector emits market data events; other services consume)
- Connection: pika `1.3.2` (sync AMQP client, all services with messaging)

## Monitoring & Observability

**Prometheus:**
- Image: `prom/prometheus:latest` (`docker-compose.unified.yml`, profile: `monitoring`)
- Container: `crypto-bot-prometheus`, port `9090`
- Config: `infrastructure/monitoring/prometheus.yml` — scrapes all 9 application services + itself at 15s interval; alert rules at `infrastructure/monitoring/alerts.yml`
- Scrape targets: api-gateway:8000, bybit-connector:8001, market-data:8002, portfolio-manager:8003, technical-analysis:8004, trading-engine:8005, notification-service:8006, ml-prediction:8007, sentiment-analysis:8008, risk-metrics:8009 — all at `/metrics`
- Retention: 15 days (`--storage.tsdb.retention.time=15d`)

**Grafana:**
- Image: `grafana/grafana:latest` (`docker-compose.unified.yml`, profile: `monitoring`)
- Container: `crypto-bot-grafana`, port `3001`
- Dashboards: `infrastructure/monitoring/grafana/dashboards/`; provisioning at `infrastructure/monitoring/grafana/provisioning/`
- Plugins: grafana-clock-panel, grafana-piechart-panel
- Auth: `GF_SECURITY_ADMIN_USER` / `GF_SECURITY_ADMIN_PASSWORD` env vars

**Structured Logging:**
- Library: python-json-logger `2.0.7` — all services
- Secret masking: `SecretMaskingFormatter` in `services/bybit-connector/app/main.py` redacts api_key, api_secret, password, token, secret, authorization, bearer fields
- Log files: service-local `logs/` dirs bind-mounted from `services/<svc>/logs/`

**Sentry:**
- SDK: sentry-sdk `1.40.0` in api-gateway and trading-engine requirements
- Status: imported but `SENTRY_DSN` not wired into compose — not active in default deployment

## Authentication & Identity

**JWT (api-gateway):**
- Library: pyjwt `[crypto] >=2.10.1` (new), python-jose `[cryptography] >=3.3.0` (legacy, still imported via `from jose`)
- Password hashing: libpass `[bcrypt] 1.9.3` (replaces passlib) + bcrypt `5.0.0`
- Auth endpoints: `POST /auth/register`, `POST /auth/login`, `GET /auth/me`, `POST /auth/logout`
- Admin routes: `admin_client` fixture required in tests; see `services/api-gateway/tests/conftest.py`

**Bybit HMAC Auth:**
- Implemented in `services/bybit-connector/app/auth.py`
- Clock sync against Bybit server time at startup to prevent timestamp drift errors

## Notifications

**Telegram:**
- Direction: outbound from notification-service
- Protocol: HTTPS POST to `https://api.telegram.org/bot<TOKEN>/sendMessage`
- Auth: bot token in URL path
- Env vars: `TELEGRAM_BOT_TOKEN` (prod) or `TEST_TELEGRAM_BOT_TOKEN` (CI); `TELEGRAM_CHAT_ID` / `TEST_TELEGRAM_CHAT_ID`; both via Pydantic `AliasChoices` in `services/notification-service/app/config.py`
- Implementation: `services/notification-service/app/telegram_notifier.py`, `services/notification-service/app/channels/telegram_client.py`
- Test mode: `NOTIFICATION_TEST_MODE=record` writes to `tests/.notifications.log` instead of posting; `live` forces real POST

**Email (SMTP):**
- Direction: outbound from notification-service
- Protocol: SMTP; uses stdlib `smtplib` (no extra package)
- Default SMTP: `smtp.gmail.com:587`
- Env vars: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM`, `EMAIL_TO`
- Implementation: `services/notification-service/app/email_notifier.py`

**Slack:**
- Direction: outbound from notification-service
- Protocol: HTTPS POST to webhook URL
- Env vars: `SLACK_WEBHOOK_URL`, `SLACK_BOT_TOKEN`
- Implementation: `services/notification-service/app/channels/slack_client.py`
- Channels: `#trading-critical` (CRITICAL), `#trading-alerts` (HIGH), `#bimo-performance` (summaries)

**SMS / Twilio:**
- Direction: outbound from notification-service (optional)
- SDK: twilio `8.10.0`
- Env vars: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`, `SMS_RECIPIENT_NUMBERS`

**Alert routing (notification-service):**
- CRITICAL → telegram + email + slack
- HIGH → telegram + email
- MEDIUM → telegram only
- LOW → email (batched, 5-minute interval)
- INFO → dashboard only

## Sentiment Data Sources (gated — `ENABLE_SENTIMENT_ANALYSIS=false`)

**NewsAPI.org:**
- Direction: outbound from sentiment-analysis-service
- Protocol: HTTPS REST via newsapi-python `0.2.7`
- Auth: `NEWS_API_KEY` env var
- Implementation: `services/sentiment-analysis-service/app/analyzers/news_fetcher.py`

**Twitter/X API v2:**
- Direction: outbound from sentiment-analysis-service
- Protocol: HTTPS REST via tweepy `4.14.0`
- Auth: `TWITTER_BEARER_TOKEN` env var
- Implementation: `services/sentiment-analysis-service/app/analyzers/twitter_fetcher.py`

## Secrets Management

**HashiCorp Vault (optional, not active in default compose):**
- Client: hvac `2.1.0` (`shared/requirements-vault.txt`)
- Vault client: `shared/vault_client.py`, `shared/vault_config.py`
- Vault-aware config class: `services/bybit-connector/app/config_vault.py` (extends `VaultAwareSettings`); secrets at paths `secret/bybit-connector/bybit`, `secret/bybit-connector/redis`, `secret/bybit-connector/rabbitmq`
- Infrastructure: `infrastructure/vault/setup_vault.sh`, `vault-config.hcl`, `vault-config-prod.hcl`
- Status: fallback to environment variables when Vault unavailable; compose does not inject `VAULT_ADDR`

## Intra-Service HTTP Communication

All internal calls use Docker hostname resolution on `crypto-bot-network`. URL env vars injected via compose.

| Caller | Target | URL Env Var | Purpose |
|--------|--------|-------------|---------|
| api-gateway | bybit-connector | `BYBIT_CONNECTOR_URL` | Market data proxy |
| api-gateway | market-data | `MARKET_DATA_URL` | Klines / tickers |
| api-gateway | portfolio-manager | `PORTFOLIO_MANAGER_URL` | Portfolio state |
| api-gateway | technical-analysis | `TECHNICAL_ANALYSIS_URL` | Signals, indicators |
| api-gateway | trading-engine | `TRADING_ENGINE_URL` | Trading control |
| api-gateway | notification-service | `NOTIFICATION_URL` | Alert dispatch |
| api-gateway | ml-prediction | `ML_PREDICTION_URL` | ML signals (gated) |
| api-gateway | sentiment-analysis | `SENTIMENT_ANALYSIS_URL` | Sentiment (gated) |
| api-gateway | risk-metrics | `RISK_METRICS_URL` | Risk dashboard |
| market-data-service | bybit-connector | `BYBIT_CONNECTOR_URL` | Klines fetch (paginated) |
| technical-analysis | bybit-connector | `BYBIT_CONNECTOR_URL` | Ticker / klines |
| technical-analysis | market-data | `MARKET_DATA_URL` | Historical data |
| trading-engine | bybit-connector | `BYBIT_CONNECTOR_URL` | Order placement (live mode) |
| trading-engine | technical-analysis | `TECHNICAL_ANALYSIS_URL` | Signal aggregation |
| trading-engine | market-data | `MARKET_DATA_URL` | Prices |
| trading-engine | portfolio-manager | `PORTFOLIO_MANAGER_URL` | Position sync |
| trading-engine | notification-service | `NOTIFICATION_SERVICE_URL` | Trade alerts |
| trading-engine | ml-prediction | `ML_PREDICTION_URL` | ML signal (gated) |
| portfolio-manager | bybit-connector | `BYBIT_CONNECTOR_URL` | Balance sync |
| portfolio-manager | trading-engine | `TRADING_ENGINE_URL` | Position sync |
| portfolio-manager | market-data | `MARKET_DATA_URL` | Price data |
| risk-metrics | trading-engine | `TRADING_ENGINE_URL` | Risk data |
| risk-metrics | portfolio-manager | `PORTFOLIO_MANAGER_URL` | Portfolio state |
| ml-prediction | market-data | `MARKET_DATA_URL` | Historical klines for inference |

## WebSocket Surfaces

**api-gateway → frontend clients:**
- Endpoint: `ws://localhost:8000/ws` (handled via `@app.websocket("/ws")` in `services/api-gateway/app/main.py`)
- Protocol: WebSocket; broadcasts real-time price/portfolio updates
- Auth: none on WS endpoint (frontend connects directly)

**bybit-connector → Bybit:**
- Outbound WebSocket to `wss://stream.bybit.com/v5/public/linear` (mainnet)
- Used for real-time market data stream; connection managed in `services/bybit-connector/app/main.py` lifespan

## Kill-Switch / Safety

- File-based emergency stop: `safety/EMERGENCY_STOP` (host) → `/app/safety/EMERGENCY_STOP` (container)
- Dir-to-dir bind mount in compose: `./safety:/app/safety` (RW for api-gateway, RO for trading-engine)
- api-gateway writes via `POST /api/portfolio/emergency-stop` using `pathlib.Path.write_text` (not `builtins.open`)
- trading-engine reads the file path from `EMERGENCY_STOP_FILE` env var on each auto-trader tick

## CI/CD & Deployment

**Local:**
- `docker compose -f docker-compose.unified.yml up -d` — full stack
- `make build-no-buildkit SVC=<service>` — WSL2 BuildKit workaround

**Kubernetes (production):**
- Manifests: `infrastructure/kubernetes/` — includes autoscaling, configmaps, databases, ingress, kustomization
- Helm chart: `infrastructure/helm/crypto-trading-bot/`
- Cloud: Oracle Cloud (`oracle-cloud-setup.sh`)

**Compose profiles:**
- default — 12 services (DBs + 9 app services + frontend + bybit-connector + market-data)
- `monitoring` — adds Prometheus + Grafana
- `ml` — adds ml-prediction container (RAM-constrained WSL hosts skip this)
- `analytics` — adds sentiment-analysis container
- `tournament` — adds tournament-harness (binds `/var/run/docker.sock`)

## OpenAPI Surface

- Live spec: `http://localhost:8000/openapi.json` (api-gateway exposes directly)
- api-gateway routes follow `/api/<domain>/<resource>` pattern (no `v1` prefix in current routes; legacy `/api/v1/` aliases exist as passthrough)
- All services expose `GET /health` and `GET /ready`

## Tournament Harness (opt-in, profile: tournament)

- Direction: outbound Docker API via `/var/run/docker.sock`
- SDK: docker `7.0.0` Python SDK (`services/tournament-harness/requirements.txt`)
- Security: single-image runner pattern — only launches `crypto-bot-tournament-harness:latest`, never user-supplied images
- DB access: read-only via `tournament_reader` Postgres role (migration 005)
- Leaderboard: stdlib sqlite3 only (no ORM)

---

*Integration audit: 2026-05-22*
