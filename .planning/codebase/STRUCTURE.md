# Codebase Structure

**Analysis Date:** 2026-05-22

## Directory Layout

```
crypto-trading-bot/
├── services/                   # 12 Python FastAPI microservices
│   ├── api-gateway/            # :8000 — routing, auth
│   ├── bybit-connector/        # :8001 — Bybit REST gateway
│   ├── market-data-service/    # :8002 — candle ingest
│   ├── portfolio-manager/      # :8003 — positions, P&L
│   ├── technical-analysis/     # :8004 — TA indicators + GRU
│   ├── trading-engine/         # :8005 — strategy, risk, auto-trader
│   ├── notification-service/   # :8006 — Telegram + email
│   ├── ml-prediction-service/  # :8007 — GRU inference endpoints
│   ├── sentiment-analysis-service/  # :8008 — idle
│   ├── risk-metrics-service/   # :8009 — risk dashboards
│   ├── ml-retraining-service/  # no HTTP — cron GRU retrain
│   └── tournament-harness/     # internal — tournament leaderboard + CLI
├── shared/                     # Cross-service libraries (not an installed package)
│   ├── database/               # DB connection, ORM models, repositories
│   ├── utils/                  # circuit_breaker, structured_logging, rate_limiter, etc.
│   ├── tests/fixtures/         # Shared test DB fixtures
│   ├── health_check.py         # Shared health-check helper
│   ├── vault_client.py         # Vault secret access
│   └── vault_config.py         # Vault config loader
├── frontend/                   # React 18 + Vite app (:3000)
│   └── src/
│       ├── App.jsx             # Router root — 7 routes
│       ├── main.jsx            # Vite entry point
│       ├── pages/              # Route-level page components
│       ├── components/         # Shared UI components
│       ├── contexts/           # React context providers
│       ├── hooks/              # Custom React hooks
│       ├── services/           # API client functions (axios/fetch wrappers)
│       ├── utils/              # Utility functions
│       └── styles/             # CSS modules / theme files
├── infrastructure/
│   ├── migrations/             # SQL migrations 001–005 (applied by start-system)
│   ├── kubernetes/             # K8s manifests (deployments, services, secrets, HPA)
│   ├── helm/                   # Helm chart: crypto-trading-bot/
│   ├── monitoring/             # Prometheus config, Grafana dashboards, alertmanager
│   ├── production/             # Kustomize prod overlay + deploy scripts
│   ├── backup/                 # DB backup/restore scripts
│   ├── config/                 # postgresql.conf, redis.conf
│   ├── scripts/                # DB init SQL, secret rotation, Vault setup
│   └── vault/                  # Vault HCL config
├── docs/
│   ├── architecture/           # SYSTEM_OVERVIEW.md, SERVICE_CONTRACTS.md
│   ├── decisions/              # ADRs (ADR-001 through ADR-010)
│   ├── runbooks/               # Operational runbooks (LIVECLOSE-05.md, etc.)
│   ├── deploy/                 # Deployment guides
│   ├── development/            # Dev setup (SETUP.md)
│   ├── operations/             # Operational docs
│   ├── security/               # Security audit, checklists
│   ├── strategy/               # Strategy research docs
│   └── testing/                # Testing strategy, test DB setup
├── tests/                      # Repo-level integration + e2e tests
├── backtesting/                # Backtesting engine + walk-forward scripts
├── shared/                     # (see above)
├── scripts/                    # Root-level operational scripts
├── safety/                     # Kill-switch directory (bind-mounted into containers)
│   └── EMERGENCY_STOP          # File presence = trading paused
├── config/                     # Root-level config overrides
├── data/                       # Persistent data directory
├── logs/                       # Runtime logs
├── reports/                    # Generated reports
├── graphify-out/               # Graphify knowledge graph output
├── wiki/                       # Obsidian vault (hot.md, index.md, domain subdirs)
├── .planning/                  # GSD workflow state
│   ├── codebase/               # Codebase map documents (this dir)
│   ├── phases/                 # Per-phase plans (13-bybit-connector…, etc.)
│   ├── state/                  # carry_ins.json, task tracking
│   ├── todos/                  # GSD todo lists
│   └── STATE.md, PROJECT.md, REQUIREMENTS.md, ROADMAP.md, MILESTONES.md
├── .claude/                    # Claude agent config
│   ├── skills/                 # Project skills (backtest, deploy, start-system, etc.)
│   ├── agents/                 # 54 agent personas
│   └── hooks/                  # intelligent-router hook
├── docker-compose.unified.yml  # CANONICAL compose (16 services incl. DBs)
├── docker-compose.yml          # INCOMPLETE — missing postgres/timescale/redis/rabbitmq
├── pyproject.toml              # Python tooling config (ruff, pytest)
├── pytest.ini                  # Pytest config
├── Makefile                    # Build/test/lint shortcuts
└── _archive_exchanges/         # Archived exchange integrations (non-Bybit)
```

## Per-Service Layout Convention

Every Python microservice follows this layout:

```
services/<service-name>/
├── app/
│   ├── main.py            # FastAPI app factory, lifespan, router mounts, health/ready
│   ├── config.py          # Pydantic BaseSettings — all env vars and defaults
│   ├── models.py          # Pydantic request/response models (some services)
│   ├── handlers/          # FastAPI router modules (one file per domain area)
│   ├── services/          # Business logic / orchestration
│   └── <domain>/          # Domain-specific subdirs (varies per service)
├── tests/
│   ├── conftest.py        # Pytest fixtures (TestClient, mock clients)
│   ├── unit/              # Unit tests (where present)
│   └── integration/       # Integration tests
├── Dockerfile             # Service-specific Dockerfile
├── requirements.txt       # Service dependencies
└── pytest.ini             # Service pytest config
```

**trading-engine** is significantly larger and extends this with:
```
services/trading-engine/app/
├── aggregation/           # CoreAggregator + gatekeeper/validator/voter
├── analytics/             # P&L analytics
├── backtesting/           # In-process backtest engine
├── core/                  # health.py, metrics, db
├── database/              # SQLAlchemy models and session
├── exchanges/             # Exchange interface abstractions
├── execution/             # Order execution layer
├── lifespan/              # 4-phase async boot (data/ml/strategy/risk)
├── managers/              # Position manager, trade manager
├── models/                # Domain models (trade, signal, position)
├── monitoring/            # Prometheus counters/histograms
├── orchestration/         # Orchestration helpers
├── preflight/             # LIVE boot checks
├── risk/                  # correlation, kelly, vol_targeting, funding_gate, etc.
├── services/              # notification_client, portfolio_client, etc.
├── strategies/            # StrategyBase + concrete strategies
│   └── arbitrage/         # Arbitrage strategy implementations
├── trading_enhancements/  # Enhancements layer (position sizing, etc.)
└── utils/                 # statistical/ (returns_metrics, sharpe_metrics, cpcv)
```

**bybit-connector** flat app:
```
services/bybit-connector/app/
├── main.py
├── config.py
├── bybit_rest_client.py   # Signs + sends Bybit REST requests
├── tape_replay_client.py  # Test-mode fake client
├── circuit_breaker.py     # HTTP circuit breaker
├── auth.py                # Bybit HMAC signing
├── models.py
└── exceptions.py
```

## Key File Locations

**Entry Points:**
- `services/<name>/app/main.py` — FastAPI app for each service
- `frontend/src/main.jsx` — Vite/React entry
- `frontend/src/App.jsx` — React Router v6, 7 routes
- `services/tournament-harness/app/cli.py` — tournament CLI

**Configuration:**
- `services/<name>/app/config.py` — Pydantic BaseSettings per service
- `docker-compose.unified.yml` — canonical Docker Compose (use this, not `docker-compose.yml`)
- `pyproject.toml` — ruff, pytest, mypy tool config
- `pytest.ini` — repo-level pytest config

**Core Logic:**
- `services/trading-engine/app/signal_aggregator.py:707` — canonical 10-indicator fetch
- `services/trading-engine/app/aggregation/aggregator_core.py` — gatekeeper/validator/voter
- `services/trading-engine/app/auto_trader.py` — auto-trader loop
- `services/trading-engine/app/strategies/base.py` — StrategyBase ABC
- `services/bybit-connector/app/bybit_rest_client.py` — Bybit REST client
- `services/market-data-service/app/fetcher.py` — candle ingest from bybit-connector
- `services/api-gateway/app/services/service_proxy.py` — ServiceProxy (httpx)

**Shared Utilities:**
- `shared/utils/structured_logging.py` — JSON logger
- `shared/utils/circuit_breaker.py` — generic circuit breaker
- `shared/utils/rate_limiter.py` — rate limiter
- `shared/utils/graceful_shutdown.py` — shutdown handler
- `shared/database/connection.py` — DB pool
- `shared/database/models.py` — shared ORM models

**Testing:**
- `tests/` — repo-level integration + e2e tests
- `services/<name>/tests/` — per-service unit + integration tests
- `shared/tests/fixtures/database.py` — shared DB test fixtures
- `services/api-gateway/tests/conftest.py` — `admin_client` fixture (required for admin-guarded routes)

**Migrations:**
- `infrastructure/migrations/001_initial_schema.sql`
- `infrastructure/migrations/002_performance_history.sql`
- `infrastructure/migrations/003_portfolios_orm_align.sql`
- `infrastructure/migrations/004_positions_orm_align.sql`
- `infrastructure/migrations/005_tournament_reader.sql`

**Runbooks / ADRs:**
- `docs/runbooks/` — operational runbooks (LIVECLOSE-05.md, forward-paper-test.md, SERVICE_CONTRACTS.md)
- `docs/decisions/` — ADR-001 through ADR-010

**Kill-Switch:**
- `safety/EMERGENCY_STOP` — create file to halt trading; remove to resume

## Naming Conventions

**Files:**
- Python: `snake_case.py` (e.g., `signal_aggregator.py`, `auto_trader.py`)
- React: `PascalCase.jsx` for components/pages (e.g., `Dashboard.jsx`, `PerformanceDashboard.jsx`), `camelCase.js` for utilities

**Directories:**
- Service names: `kebab-case` (e.g., `trading-engine`, `bybit-connector`)
- Python modules within services: `snake_case` (e.g., `handlers/`, `aggregation/`)
- React: lowercase for utility dirs (`hooks/`, `utils/`, `contexts/`), PascalCase not used at dir level

**Compose service names:** Same as directory names (e.g., `trading-engine`, `bybit-connector`) — used in `docker compose logs -f <name>`.

## Where to Add New Code

**New trading indicator:**
- Implementation: `services/technical-analysis/app/indicators/<name>.py`
- Register handler: `services/technical-analysis/app/handlers/analysis.py` or add dedicated router
- Add to signal_aggregator fetch: `services/trading-engine/app/signal_aggregator.py:734-755` (tasks dict)

**New trading strategy:**
- Extend `StrategyBase`: `services/trading-engine/app/strategies/<name>.py`
- Required methods: `analyze()`, `generate_signals()`, `calculate_position_size()`
- Register in strategy registry (grep `get_strategy` or `register_strategy` in `services/trading-engine/app/`)

**New API endpoint on existing service:**
- Handler: `services/<name>/app/handlers/<domain>.py`
- Mount router in: `services/<name>/app/main.py`
- Gateway proxy: `services/api-gateway/app/services/service_proxy.py` (if exposed externally)

**New shared utility:**
- File: `shared/utils/<name>.py`
- Add to: `shared/utils/__init__.py` if needed

**New risk module (trading-engine):**
- File: `services/trading-engine/app/risk/<name>.py`
- Wire in lifespan: `services/trading-engine/app/lifespan/risk.py`

**New DB migration:**
- File: `infrastructure/migrations/006_<description>.sql`
- Apply via: `start-system` skill or manually via `psql`

**New frontend page:**
- Page component: `frontend/src/pages/<PageName>.jsx`
- Add route in: `frontend/src/App.jsx` (React Router v6 `<Route>`)

**New frontend component:**
- File: `frontend/src/components/<ComponentName>.jsx`

## Special Directories

**`safety/`:**
- Purpose: Kill-switch directory, bind-mounted into trading-engine container at `/app/safety/`
- `EMERGENCY_STOP` file presence pauses auto-trader
- Committed: No (contents excluded); directory committed as empty

**`_archive_exchanges/`:**
- Purpose: Archived non-Bybit exchange integrations
- Generated: No — manually archived
- Committed: Yes (historical reference, not used in build)

**`wiki/`:**
- Purpose: Obsidian knowledge vault — `hot.md` (recent cache), `index.md` (master catalog), domain subdirs
- Generated: No — hand-maintained
- Committed: Yes

**`.planning/`:**
- Purpose: GSD workflow state — phase plans, codebase maps, todos, carry-ins, project state
- Read by: `/gsd-plan-phase`, `/gsd-execute-phase` commands
- Committed: Yes — planning artifacts are version-controlled

**`graphify-out/`:**
- Purpose: Output from `/graphify` skill knowledge graph runs
- Generated: Yes
- Committed: Not critical — regenerable

**`htmlcov/`:**
- Purpose: Coverage HTML reports
- Generated: Yes — `pytest --cov`
- Committed: No (gitignored)

**`logs/`:**
- Purpose: Runtime service logs (bind-mounted from containers)
- Generated: Yes
- Committed: No

**`.claude/skills/`:**
- Purpose: Project-specific Claude skills (backtest, deploy, start-system, trading-strategy-dev, verify-stack)
- Each skill has `SKILL.md` + optional `rules/*.md`

---

*Structure analysis: 2026-05-22*
