# Technology Stack

**Analysis Date:** 2026-05-12

## Languages

**Primary:**
- Python 3.12 — All 11 backend microservices (`services/*/app/`). Pinned via `pyproject.toml` (`requires-python = ">=3.12"`, black/mypy `target-version = py312`).
- TypeScript / JavaScript (ES modules) — React dashboard at `frontend/src/`. Vite + JSX/TSX mix.

**Secondary:**
- SQL — Schema + migrations at `infrastructure/migrations/` (003 portfolios ORM align, 004 positions ORM align) and `infrastructure/scripts/init-db.sql`, `init-timescale.sql`.
- Bash — Operational scripts at repo root (`bootstrap.sh`, `health_check.sh`, `start_trading_engine.sh`, `monitor_*.sh`, `build-all.sh`).
- Dockerfile — One per service under `services/<svc>/Dockerfile`; optimized template at `Dockerfile.optimized.template`.

## Runtime

**Environment:**
- CPython 3.12 inside Docker images (per-service `Dockerfile`)
- Node 18+ for the frontend build stage (Vite 5)
- Docker Engine via Compose v2 — canonical file `docker-compose.unified.yml` (16 services incl. infra). `docker-compose.yml` is incomplete (missing DBs). Other compose files: `docker-compose.headless.yml`, `docker-compose.monitoring.yml`, `docker-compose.prod.yml`, `docker-compose.test.yml`.

**Package Manager:**
- pip per service via `services/<svc>/requirements.txt` (no monorepo lockfile)
- Shared base at `shared/requirements-base.txt`, vault extras at `shared/requirements-vault.txt`
- npm for the frontend (`frontend/package.json`, `frontend/package-lock.json` assumed)
- Build backend: `setuptools>=45` (`pyproject.toml` `[build-system]`)

## Frameworks

**Core (backend, all services):**
- FastAPI `0.109.0` (api-gateway, bybit-connector, market-data, portfolio-manager, technical-analysis, trading-engine, risk-metrics) / `0.104.1` (ml-prediction, ml-retraining, notification, sentiment) — async HTTP framework
- Uvicorn `0.27.0` / `0.24.0` `[standard]` — ASGI server
- Pydantic `2.5.3` / `2.5.0` / `2.13.3` (api-gateway upgraded for cp314 wheels) — data validation
- pydantic-settings `2.1.0` / `2.14.0` — env-driven config
- Starlette `0.35.1` — security headers (api-gateway)

**Frontend:**
- React `^18.2.0` + react-dom `^18.2.0`
- Vite `^5.0.7` with `@vitejs/plugin-react`
- React Router `^6.30.1`
- TanStack Query `^5.12.2` — server state
- Zustand `^4.4.7` — client state
- axios `^1.6.2` — HTTP client
- Recharts `^2.15.4` — charting
- Tailwind CSS `^3.3.6` + PostCSS + autoprefixer
- lucide-react `^0.294.0` — icons
- date-fns `^2.30.0`

**Testing:**
- pytest `7.4.x` + pytest-asyncio `0.23.x` + pytest-cov `4.1.0` + pytest-mock `3.12.0` (`pyproject.toml [tool.pytest.ini_options]`, `pytest.ini`)
- respx `0.20.2` — httpx mocking (ml-prediction, notification)
- pytest-httpx `0.30.0` — bybit-connector
- freezegun `1.4.0` — time mocking (bybit-connector)
- Vitest `^1.6.0` + `@vitest/coverage-v8` + `@testing-library/react` `^14.2.0` + jsdom `^24.0.0` — frontend

**Build/Dev (Python tooling, configured in `pyproject.toml`):**
- Black `>=23.9.0` (line-length 100, `target-version py312`)
- isort `>=5.12.0` (black profile)
- mypy `>=1.5.0` (`disallow_untyped_defs=true`, plugins: pydantic, sqlalchemy)
- flake8 `>=6.1.0`
- pylint `>=3.0.0`
- bandit `>=1.7.5` (security)
- safety `>=2.3.0`
- ESLint `^8.55.0` + eslint-plugin-react — frontend

## Key Dependencies

**Exchange / market data:**
- pybit `5.6.2` — official Bybit Python SDK (REST), in `services/bybit-connector/requirements.txt`
- websockets `12.0` — Bybit WS streams (bybit-connector, market-data-service)
- httpx `0.27.0` — async HTTP client across services

**Data / numerics:**
- pandas `2.2.0` / `2.1.4` — TA, market-data, trading-engine, portfolio-manager, ml-*
- numpy `1.26.3` / `1.26.2` — across services
- scipy `1.11.4`/`1.12.0` — TA, trading-engine, portfolio-manager
- statsmodels `0.14.1` — TA, trading-engine (ADF, cointegration)
- scikit-learn `1.4.0`/`1.3.2` — TA, ml-prediction, ml-retraining, portfolio-manager (covariance shrinkage)
- cvxpy `>=1.4.0` — portfolio optimization
- ta `0.11.0` — TA library (RSI/MACD/BB/EMA/SMA); TA-Lib and pandas-ta explicitly removed (`services/technical-analysis/requirements.txt`)
- pyarrow `15.0.0` — Parquet (market-data)

**ML / inference:**
- tensorflow `2.16.1` (ml-prediction-service), `2.15.0` (ml-retraining-service) — GRU models. 16 GRU models live under `services/ml-prediction-service/models/`. **LSTM stack deleted May 2026** (commits `324e162`, `9a0f584`); archived at `_archive_lstm/`. trading-engine intentionally has no `tensorflow` / `sklearn` import.
- joblib `1.3.2` — lightweight model artifacts in trading-engine
- optuna `3.5.0` + optuna-dashboard `0.15.1` — hyperparameter search (ml-prediction-service)
- transformers `4.37.0` + torch `2.2.0` — sentiment-analysis (idle by default)
- apscheduler `3.10.4` — ml-retraining cron

**Databases / cache / messaging:**
- asyncpg `0.29.0` / `0.31.0` (api-gateway cp314) — PostgreSQL/TimescaleDB async driver
- psycopg2-binary `2.9.9` — sync fallback (market-data, trading-engine, portfolio-manager)
- SQLAlchemy `2.0.25` / `2.0.49` (api-gateway cp314) `[asyncio]` — ORM
- alembic `1.13.x` — migrations (market-data, trading-engine, portfolio-manager, ml-retraining)
- aioredis `2.0.1` (async) + redis `5.0.1` (sync) — Redis client
- pika `1.3.2` — RabbitMQ sync client (bybit-connector, market-data, portfolio-manager, technical-analysis, trading-engine)
- aio_pika — optional async AMQP, probed via `try: import aio_pika` in `services/trading-engine/app/core/health.py:421-445`. Marked "(optional)" — current path is degraded if not present.
- transitions `0.9.0` — order-lifecycle FSM (trading-engine)

**Reliability / API gateway:**
- tenacity `8.2.3` / `9.1.2` — retries
- circuitbreaker `1.4.0` / `2.1.3`
- slowapi `0.1.9` + limits `3.7.0` — Redis-backed rate limiting (api-gateway, bybit-connector, market-data)

**Auth / security (api-gateway only):**
- pyjwt `>=2.10.1` `[crypto]` (replaces python-jose)
- cryptography `>=46.0.0`
- libpass `1.9.3` `[bcrypt]` (passlib successor)
- bcrypt `5.0.0`
- python-multipart `0.0.6`
- email-validator `2.2.0`

**Notifications:**
- python-json-logger `2.0.7` — structured logging across services
- prometheus-client `0.19.0` — `/metrics` endpoints
- pytz `2024.1` — quiet-hour scheduling (notification-service)
- twilio `8.10.0` — optional SMS (notification-service)
- newsapi-python `0.2.7` + tweepy `4.14.0` — sentiment news/social (idle service)
- cachetools `5.3.2` — sentiment in-memory TTL cache

## Configuration

**Environment:**
- `.env` at repo root (gitignored) — operator overrides (e.g. `AUTO_TRADING_ENABLED=true`, Bybit keys)
- `.env.example` / `.env.production.example` / `.env.test.example` — templates
- `services/notification-service/.env` — Telegram/Slack/SMTP creds (gitignored, mounted via compose `env_file:`)
- Loaded via `pydantic-settings` `BaseSettings` in each `services/<svc>/app/config.py`
- HashiCorp Vault integration available — `shared/vault_client.py`, `shared/vault_config.py`, `shared/requirements-vault.txt`; production deploy points at `infrastructure/vault/`

**Build:**
- Per-service `Dockerfile` (no shared base image; each service self-contained)
- Optimized base reference: `Dockerfile.optimized.template`
- `docker-compose.unified.yml` is canonical. Profile gates: `--profile monitoring` (Prometheus, Grafana), `--profile ml` (ml-prediction-service), `--profile analytics` (sentiment-analysis-service), `--profile tournament` (tournament-harness), `--profile production`
- BuildKit known to hang on WSL2 — workaround `DOCKER_BUILDKIT=0 docker compose ... up --build`

**Python tooling config in `pyproject.toml`:**
- coverage `fail_under = 80`, branch coverage on, HTML to `htmlcov/`, XML to `coverage.xml`
- pytest `testpaths = ["services/*/tests", "tests"]`, `-ra -q --strict-markers`, `slow` marker registered
- mypy `strict_optional`, `strict_equality`, `warn_unreachable`, pydantic + sqlalchemy plugins

## Platform Requirements

**Development:**
- WSL2 + Docker Desktop on Windows host (project-specific gotchas in `crypto-trading-bot/CLAUDE.md`): Docker context must be `default` (Unix socket), not `desktop-linux`
- Bind-mount race on WSL: `docker compose up -d --force-recreate <service>` if `/app/logs` shows `PermissionError`
- ML training memory: BTC GRU training OOM-killed at default container limits — bump `deploy.resources.limits.memory` before retraining
- Repo-relative `EMERGENCY_STOP` file must exist before `docker compose up` (bind-mounted RW to api-gateway, RO to trading-engine)

**Production:**
- Kubernetes manifests in `infrastructure/kubernetes/`, Helm chart in `infrastructure/helm/`
- Oracle Cloud setup script: `oracle-cloud-setup.sh`
- Production compose: `docker-compose.prod.yml`, `infrastructure/production/`

## Containerized Services (canonical = `docker-compose.unified.yml`)

| Container | Image | Port | Notes |
|---|---|---|---|
| `crypto-bot-postgres` | `postgres:15-alpine` | 5432 | App DB (`cryptobot`). Migrations 003/004 auto-applied. CPU 1.0 / 1G |
| `crypto-bot-timescaledb` | `timescale/timescaledb:latest-pg15` | 5433 | Market data DB (`market_data`). CPU 2.0 / 2G |
| `crypto-bot-redis` | `redis:7-alpine` | 6379 | `--appendonly yes`, `--maxmemory 256mb allkeys-lru`. CPU 0.5 / 512M |
| `crypto-bot-rabbitmq` | `rabbitmq:3-management-alpine` | 5672, 15672 (mgmt) | vhost `cryptobot`. CPU 1.0 / 1G |
| `crypto-bot-prometheus` | `prom/prometheus:latest` | 9090 | `--profile monitoring`. 15d TSDB retention |
| `crypto-bot-grafana` | `grafana/grafana:latest` | 3001→3000 | `--profile monitoring`. Plugins: clock-panel, piechart-panel |
| `crypto-bot-api-gateway` | local build | 8000 | Entry point. Mounts `./EMERGENCY_STOP:/app/EMERGENCY_STOP` (RW) |
| `crypto-bot-frontend` | local build | 3000→80 | React/Vite dashboard. 256M |
| `crypto-bot-bybit` | local build | 8001 | `BYBIT_TESTNET=false` default. Tape fixtures at `./tests/fixtures/tape:ro` |
| `crypto-bot-market-data` | local build | 8002 | Reads/writes TimescaleDB (DB *is* cache; Redis empty in tests) |
| `crypto-bot-portfolio` | local build | 8003 | `USE_DATABASE=true`; DATABASE_URL postgres |
| `crypto-bot-ta` | local build | 8004 | Indicators + GRU client + aggregator |
| `crypto-bot-trading` | local build | 8005 | Auto-trader; `EMERGENCY_STOP` RO mount. CPU 1.0 / 1G |
| `crypto-bot-notification` | local build | 8006 | `env_file: services/notification-service/.env`. `NOTIFICATION_TEST_MODE=record` default |
| `crypto-bot-ml-prediction` | local build | 8007 | `--profile ml`. Models at `./services/ml-prediction-service/models`. 2G limit |
| `crypto-bot-tournament-harness` | local build | 8010 | `--profile tournament`. Mounts `/var/run/docker.sock` (privilege boundary — D-02). 2.0 CPU / 4G |
| `crypto-bot-sentiment` | local build | 8008 | `--profile analytics`. Idle by default |
| `crypto-bot-risk-metrics` | local build | 8009 | No DB; reads from trading-engine + portfolio-manager |

`ml-retraining-service` is cron-driven via apscheduler — no HTTP port, not in `docker-compose.unified.yml` (run separately or via `auto_retrain_models.sh`).

## Network / Volumes

**Network:** `crypto-bot-network` (bridge, subnet `172.28.0.0/16`)

**Named volumes (host-managed):**
- `crypto-bot-postgres-data`
- `crypto-bot-timescaledb-data`
- `crypto-bot-redis-data`
- `crypto-bot-rabbitmq-data`
- `crypto-bot-prometheus-data`
- `crypto-bot-grafana-data`

Per-service log mounts: `./services/<svc>/logs:/app/logs`.

---

*Stack analysis: 2026-05-12*
