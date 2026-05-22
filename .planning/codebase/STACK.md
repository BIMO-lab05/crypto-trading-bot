# Technology Stack

**Analysis Date:** 2026-05-22

## Languages

**Primary:**
- Python 3.12 — all 12 backend microservices (pinned in `pyproject.toml`: `requires-python = ">=3.12"`, `target-version = ['py312']`)
- JavaScript/JSX — React frontend (`frontend/src/`)

**Secondary:**
- TypeScript types referenced in frontend devDependencies (`@types/react`, `@types/react-dom`) but source uses `.jsx`/`.js`
- SQL — schema migrations in `infrastructure/migrations/*.sql` and `infrastructure/scripts/init-db.sql`, `init-timescale.sql`

## Runtime

**Environment:**
- Python 3.12 inside Docker containers; each service builds from its own `Dockerfile`
- Node.js (version not pinned in `package.json`) for frontend dev/build; production frontend served by Nginx inside container

**Package Manager:**
- Python: `pip` with per-service `requirements.txt` files; no lockfile — `pip install -r` at build time
- Node: npm (implied by `package.json`; no `package-lock.json` version pinned)

**Note:** `shared/requirements-base.txt` defines a base dependency set; individual service `requirements.txt` files take precedence and may specify different versions (e.g., api-gateway pins fastapi==0.109.0, ml-prediction-service pins fastapi==0.104.1).

## Frameworks

**Backend (per service):**
- FastAPI — HTTP framework for all services. Version varies:
  - `0.109.0` — api-gateway, bybit-connector, market-data-service, portfolio-manager, technical-analysis, trading-engine, risk-metrics-service (`services/*/requirements.txt`)
  - `0.104.1` — ml-prediction-service, ml-retraining-service, notification-service, sentiment-analysis-service, tournament-harness (`services/*/requirements.txt`)
- Uvicorn `[standard]` — ASGI server. `0.27.0` for 0.109 group; `0.24.0` for 0.104 group
- Pydantic v2 — data validation; `2.13.3` in api-gateway (with cp314 wheels), `2.5.3` in most others, `2.5.0` in older group
- pydantic-settings — `2.14.0` (api-gateway), `2.1.0` (most others)
- SQLAlchemy `2.0.25`/`2.0.23`/`2.0.49` — ORM across services; versions drift. `services/trading-engine/requirements.txt`, `services/portfolio-manager/requirements.txt`
- Alembic `1.13.1`/`1.13.0` — migrations (market-data, portfolio-manager, trading-engine, ml-retraining)
- APScheduler `3.10.4` — background scheduling (market-data-service, portfolio-manager, ml-retraining-service)

**Frontend:**
- React `^18.2.0` — UI framework (`frontend/package.json`)
- React Router DOM `^6.30.1` — client-side routing
- Vite `^5.0.7` — build tool / dev server
- Tailwind CSS `^3.3.6` — utility CSS
- Recharts `^2.15.4` — charting
- Zustand `^4.4.7` — state management
- TanStack React Query `^5.12.2` — server state/fetching
- Axios `^1.6.2` — HTTP client

**Testing:**
- pytest `7.4.4` (most services), `7.4.3` (older group) — test runner
- pytest-asyncio `0.23.3`/`0.21.1` — async test support
- pytest-cov `4.1.0` — coverage
- pytest-mock `3.12.0` — mocking
- respx `0.22.0`/`0.20.2` — httpx mocking (`services/trading-engine/requirements.txt`)
- freezegun `1.4.0` — time mocking (bybit-connector, trading-engine, portfolio-manager, market-data-service)
- Vitest `^1.6.0` — frontend test runner
- Testing Library React `^14.2.0` — frontend component tests

**Build/Dev:**
- Docker Compose — orchestration; `docker-compose.unified.yml` is canonical
- black `24.1.1` / `23.12.1` — code formatter (line-length 100, pyproject.toml)
- isort `5.13.2` — import sorter (black profile)
- mypy `1.8.0` / `1.7.1` — static type checker (with pydantic + sqlalchemy plugins, pyproject.toml)
- flake8 `7.0.0` / `6.1.0` — linter
- bandit `1.7.6` — security linter (trading-engine)
- pre-commit `3.6.0` — git hook framework (trading-engine)

## Key Dependencies

**Exchange Interface:**
- pybit `5.6.2` — official Bybit Python SDK (`services/bybit-connector/requirements.txt`); only bybit-connector uses it

**ML/AI:**
- TensorFlow `2.16.1` (ml-prediction-service), `2.15.0` (ml-retraining-service, tournament-harness) — GRU model training and inference
- scikit-learn `1.4.0` (technical-analysis), `1.3.2` (ml-prediction-service, ml-retraining-service, tournament-harness)
- optuna `3.5.0` + optuna-dashboard `0.15.1` — Bayesian hyperparameter optimization (ml-prediction-service)
- 16 trained GRU model files at `services/ml-prediction-service/models/*_60m_gru.keras` (trained 2025-12-10, currently gated off)

**NLP (sentiment-analysis-service only):**
- transformers `4.37.0` — HuggingFace NLP
- torch `2.2.0` — PyTorch (ML-based sentiment, optional profile)
- newsapi-python `0.2.7` — NewsAPI.org client
- tweepy `4.14.0` — Twitter API v2

**Database Drivers:**
- asyncpg `0.29.0`/`0.31.0` — async PostgreSQL/TimescaleDB driver (all data-touching services)
- psycopg2-binary `2.9.9` — sync PostgreSQL driver (market-data, portfolio-manager, tournament-harness)
- aioredis `2.0.1` — async Redis client
- redis `5.0.1` — sync Redis client

**Messaging:**
- pika `1.3.2` — RabbitMQ AMQP client (bybit-connector, market-data, technical-analysis, trading-engine, portfolio-manager)

**HTTP Clients:**
- httpx `0.27.0` — async HTTP (primary, most services)
- aiohttp `3.9.3` — async HTTP (trading-engine only)

**Data:**
- pandas `2.2.0` (2.1.4 in older services) — data processing
- numpy `1.26.3` (1.26.2 in older services) — numerical computing
- ta `0.11.0` — technical analysis indicators (replaces TA-Lib and pandas-ta; `services/technical-analysis/requirements.txt`)
- pyarrow `15.0.0` — Parquet columnar format (market-data-service)
- scipy `1.11.4`/`1.12.0` — scientific computing
- statsmodels `0.14.1` — statistical analysis (ADF, cointegration)
- cvxpy `>=1.4.0` — convex optimization (portfolio-manager)
- transitions `0.9.0` — finite state machine for order lifecycle (trading-engine)

**Auth/Security:**
- pyjwt `[crypto] >=2.10.1` — JWT handling (api-gateway)
- python-jose `[cryptography] >=3.3.0` — temporary pin in api-gateway (migration to pyjwt in progress)
- libpass `[bcrypt] 1.9.3` / passlib `[bcrypt]` — password hashing
- cryptography `>=46.0.0` / `41.0.7` — base crypto
- slowapi `0.1.9` + limits `3.7.0` — rate limiting (api-gateway, bybit-connector, market-data-service)

**Secrets:**
- hvac `2.1.0` — HashiCorp Vault client (`shared/requirements-vault.txt`); config_vault.py exists in bybit-connector but not wired into compose by default (falls back to env vars)

**Monitoring:**
- prometheus-client `0.19.0` — Prometheus metrics (all services expose `/metrics`)
- sentry-sdk `1.40.0` — error tracking (api-gateway, trading-engine; in requirements but SENTRY_DSN not wired in compose)
- python-json-logger `2.0.7` — structured JSON logging

**Visualization (portfolio-manager):**
- matplotlib `3.8.2` — chart generation
- plotly `5.18.0` — interactive charts

**Docker SDK (tournament-harness only):**
- docker `7.0.0` — Python Docker SDK for launching experiment containers via `/var/run/docker.sock`

**Notifications:**
- twilio `8.10.0` — SMS (notification-service, optional)

## Configuration

**Environment:**
- All services load config via Pydantic `BaseSettings` from environment variables and optional `.env` file
- `.env` at repo root and `services/notification-service/.env` (gitignored)
- `docker-compose.unified.yml` injects all env vars into containers via `environment:` blocks
- `.env.example` pattern; `.env` never committed

**Key env flags:**
- `BYBIT_API_KEY` / `BYBIT_API_SECRET` — Bybit credentials (bybit-connector only)
- `BYBIT_TESTNET=false` — mainnet prices (compose default)
- `MARKET_DATA_SOURCE=live` — live Bybit; `tape` for fixture replay
- `PAPER_TRADING_MODE=true` — simulated orders
- `TRADING_MODE=PAPER` — trading engine mode
- `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY` — required to boot trading-engine in LIVE mode
- `AUTO_TRADING_ENABLED=true` — operator override in host `.env`; compose default is `true` for trading-engine
- `ENABLE_ML_PREDICTIONS=false` — GRU inference gated off
- `ENABLE_SENTIMENT_ANALYSIS=false` — sentiment leg gated off
- `EMERGENCY_STOP_FILE=/app/safety/EMERGENCY_STOP` — kill-switch file path

**Build:**
- `pyproject.toml` — black/isort/mypy/bandit/pylint/coverage config
- `pytest.ini` — test discovery, markers, asyncio mode, coverage config
- `docker-compose.unified.yml` — canonical compose (16 services incl. DBs)
- `docker-compose.yml` — incomplete (missing postgres/timescale/redis/rabbitmq); do not use for full stack

## Platform Requirements

**Development:**
- WSL2 + Docker Desktop (`docker context = default` Unix socket)
- `DOCKER_BUILDKIT=0` required to avoid BuildKit hang on WSL2 (`make build-no-buildkit`)
- `docker compose -f docker-compose.unified.yml up -d` — stack launch
- Host can optionally install Python 3.12 for repo-level `pytest tests/`; api-gateway tests must run inside container due to fastapi version mismatch (host: 0.136, container: 0.109)

**Production:**
- Docker Compose (local/dev) or Kubernetes (`infrastructure/kubernetes/`) with Helm (`infrastructure/helm/crypto-trading-bot/`)
- Oracle Cloud setup script at `oracle-cloud-setup.sh`
- Nginx serves frontend static build inside frontend container, port 80 → exposed :3000

---

*Stack analysis: 2026-05-22*
