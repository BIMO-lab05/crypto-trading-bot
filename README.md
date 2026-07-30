# Crypto Trading Bot

Autonomous Bybit crypto trading bot. 11 Python microservices + React frontend. Currently runs in **paper-trading mode** — real Bybit mainnet prices, simulated orders.

**Last updated:** 2026-07-30 · **Mode:** paper-trading · **Status:** actively developed — v1.3 milestone executing (docs reorganized 2026-07-30: living guides in [docs/](docs/README.md), history in docs/archive/)

---

## Stack

- **Backend:** Python 3.12, FastAPI, asyncio (one process per service)
- **Frontend:** React 18 + Vite + Tailwind, dark theme
- **Data:** TimescaleDB (candles), PostgreSQL (app state), Redis (cache), RabbitMQ (events)
- **Orchestration:** Docker Compose (local), Kubernetes + Helm (prod, `infrastructure/`)
- **ML:** 16 GRU price-prediction models, currently gated **off** by default (see ML status below)
- **Observability:** Prometheus + Grafana (opt-in via `--profile monitoring`)

---

## Services

17 containers total: 10 app services + 4 infrastructure + 2 monitoring + frontend. ML-retraining service is cron-triggered and has no HTTP port.

| Service | Port | Purpose |
|---|---|---|
| api-gateway | 8000 | Frontend → backend routing, auth, admin endpoints |
| bybit-connector | 8001 | Bybit REST + WebSocket wrapper |
| market-data-service | 8002 | Candle ingest → TimescaleDB |
| portfolio-manager | 8003 | Positions, balances, P&L |
| technical-analysis | 8004 | TA indicators + GRU inference + signal aggregator |
| trading-engine | 8005 | Strategy + risk + order execution |
| notification-service | 8006 | Telegram + Slack + email alerts |
| ml-prediction-service | 8007 | Standalone GRU inference (gated, see below) |
| sentiment-analysis-service | 8008 | News / social sentiment (idle by default, see below) |
| risk-metrics-service | 8009 | Risk dashboards |
| ml-retraining-service | — | Cron-driven GRU retrain (no HTTP) |
| frontend | 3000 | React dashboard |
| postgres / timescaledb / redis / rabbitmq | — | Infrastructure |
| prometheus / grafana | 9090 / 3001 | Metrics + dashboards (opt-in) |

---

## Quick start

Prereqs: Docker + Compose, ~8 GB RAM, ~20 GB disk. WSL2 supported.

```bash
# Boot the stack (paper-trading defaults)
docker compose -f docker-compose.unified.yml up -d

# Tail logs for one service
docker compose -f docker-compose.unified.yml logs -f trading-engine

# Stop
docker compose -f docker-compose.unified.yml down
```

After boot:

- Dashboard: http://localhost:3000
- API gateway: http://localhost:8000 (OpenAPI: `/openapi.json`)
- RabbitMQ management: http://localhost:15672
- Prometheus / Grafana (if `--profile monitoring`): http://localhost:9090, http://localhost:3001

A scripted boot path with health probes is in `.claude/skills/start-system/SKILL.md`.

---

## Frontend

React + Vite single-page app at port 3000.

- **Command palette** (`Cmd/Ctrl+K`) — fuzzy-search symbols, trading actions, page routes
- **Vim-style shortcuts** — `g d` Dashboard, `g o` Portfolio, `g p` Performance, `g 1`/`g 3` Phase 1 / Phase 3, `g s` Settings
- **Dark / light theme toggle** — respects `prefers-color-scheme`
- **Status bar** (bottom) — live trading state, signals checked, trades, open positions, cash/P&L, emergency state
- **Performance dashboard** — equity curve, daily P&L, drawdown, correlation heatmap, returns distribution
- **Pages:** Main · Phase 1 · Phase 3 · Portfolio · Performance · Settings

Accessibility audit `docs/accessibility-audit-2026-05-02.md` documents WCAG 2.1 AA findings; remediation in progress.

---

## Configuration

Required env vars at the repo root `.env` (gitignored). All compose vars have `${VAR:-default}` fallbacks, so missing keys fall back safely.

### Trading-mode flags

Two **independent** flags control real-money behavior. Mixing them up is a footgun; both are required separately.

| Flag | Effect |
|---|---|
| `BYBIT_TESTNET` | Selects price source. `false` = real Bybit mainnet prices. `true` = testnet (mock prices). |
| `PAPER_TRADING_MODE` / `TRADING_MODE` | Selects whether orders are simulated. `true` / `PAPER` = simulated. `false` / `LIVE` = real orders. |
| `LIVE_TRADING_ACK` | Required to boot in LIVE mode. Must equal `I_UNDERSTAND_REAL_MONEY`. Catches env drift on cloud hosts. |

Default state: `BYBIT_TESTNET=false` + `PAPER_TRADING_MODE=true` → real prices, simulated orders.

**Going LIVE requires four deliberate steps:**

1. `PAPER_TRADING_MODE=false`
2. `TRADING_MODE=LIVE`
3. Mainnet Bybit API keys with trading permissions
4. `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY`

### Feature flags (default OFF)

| Flag | Default | What it gates |
|---|---|---|
| `ENABLE_ML_PREDICTIONS` | `false` | GRU inference call from trading-engine. Off because the V0 GRU directional-accuracy metric was found to have look-ahead leakage (May 2026); models score chance-level on returns. Re-enable after rebuild on returns target with DSR > 0.95 acceptance. |
| `ENABLE_SENTIMENT_ANALYSIS` | `false` | Sentiment leg in signal aggregator. Sentiment-analysis-service still runs but is idle (no callers in the default pipeline). |
| `AUTO_TRADING_ENABLED` | `false` (compose) / **`true` (operator `.env`)** | Trading-engine's auto-trader loop. Currently armed by operator override. Loop only fires once the kill-switch file is absent. Kill-switch path: `safety/EMERGENCY_STOP` (host) → `/app/safety/EMERGENCY_STOP` (container) via dir-to-dir bind-mount of `./safety/`. Pause: `touch safety/EMERGENCY_STOP` or `POST /api/portfolio/emergency-stop`. Resume: `rm safety/EMERGENCY_STOP` (+ `POST /api/trading/start` if halted at boot). Stop: `POST /api/trading/auto/stop`. |

### Emergency stop

`EMERGENCY_STOP` file at repo root is bind-mounted RO into trading-engine. Presence halts the auto-trader at startup. Created/cleared by `POST /api/portfolio/emergency-stop` (admin-guarded) or by hand.

---

## Risk management

Caps wired into trading-engine and enforced regardless of mode:

| Cap | Value |
|---|---|
| Max risk per trade | 2 % of capital |
| Daily loss circuit-breaker | 5 % |
| Drawdown emergency halt | 10 % |
| Max concurrent positions | 5 |
| Leverage | 1× (no margin) |

These are project rules — relaxing requires explicit approval (see `CLAUDE.md`).

---

## Validated symbols

Active in paper-trading: **BTC, ETH, SOL, BNB, ADA** (5 symbols). XRP / DOGE excluded historically (loss profile in 89-trade dataset). Symbol set is configured in market-data-service `default_symbols` and trading-engine `trading_symbols`.

---

## ML status

16 GRU models exist (`services/ml-prediction-service/models/*.keras`), trained Dec 10 2025 — now ~5 months stale. The V0 directional-accuracy figures (79–84 %) were a metric bug — `y_test[:, -1]` referenced a future bar. Fixed in commit `c56765c`. After fix, models score chance-level on log-returns and lose to a naive persistence baseline. Reproducer: `docs/strategy/research-2026-04-29/persistence_shootout.py`.

Consequence: `ENABLE_ML_PREDICTIONS=false` by default. Rebuild on returns target with DSR (Deflated Sharpe Ratio) > 0.95 acceptance gate before re-enabling.

LSTM was deleted May 2026 (commits `25ca9ab` … `324e162`). Archived under `_archive_lstm/` for rollback.

---

## Testing

```bash
# All services
pytest --cov=services --cov-report=term

# One service
pytest services/trading-engine/tests/

# Repo-level integration / e2e
pytest tests/
```

Per-service coverage targets ≥80 %. Most services hit it; api-gateway, trading-engine, technical-analysis, risk-metrics are the focus areas.

**Gotcha:** api-gateway tests must run **inside the container** (`docker exec crypto-bot-api-gateway pytest`) — host pip pulls fastapi 0.136 (returns 401 from `HTTPBearer`) while the deployed image pins 0.109 (returns 403); tests assert 403.

---

## CI/CD

`.github/workflows/` ships 10 active workflows:

| Workflow | Trigger | Purpose |
|---|---|---|
| ci.yml | push / PR | Lint, type-check, per-service tests, Docker build with Trivy |
| build-service.yml | reusable | Parameterized service image build |
| cd-dev.yml | push to `develop` | Build → push to ghcr.io → deploy to dev K8s |
| cd-prod.yml | push to `main` | Blue-green prod deploy with rollback + GitHub Release |
| deploy-k8s.yml | reusable | Generic K8s deploy (rolling / blue-green / canary) |
| security-scan.yml | daily + push / PR | Safety, pip-audit, Trivy, Grype, Bandit, Semgrep, TruffleHog, Gitleaks, Checkov, KICS |
| ml-retrain.yml | weekly cron | One-shot GRU retrain on Oracle VM (headless fallback for ml-retraining-service) |
| performance-test.yml | weekly cron + PR | Load + perf benchmarks |
| release.yml | tag `v*.*.*` | Changelog + GitHub Release |
| claude.yml | issue / PR mention `@claude` | Claude Code AI-assisted review |

Dependabot tracks pip (10 services), docker (10 services), npm (frontend), github-actions — weekly.

GitHub secrets required for CI/CD are listed in `.github/CICD_README.md`.

---

## Project layout

```
crypto-trading-bot/
├── services/                       # 11 Python microservices
│   └── <service>/app/             # FastAPI app, lifespan phases, handlers
├── frontend/                       # React + Vite SPA
├── infrastructure/                 # K8s manifests, Helm charts, DB migrations
│   └── migrations/                # 003_portfolios_orm_align.sql, 004_positions_orm_align.sql
├── docs/
│   ├── architecture/              # System overview, service contracts
│   ├── development/               # SETUP.md, TESTING.md
│   ├── operations/                # RUNBOOK.md, alerting, disaster recovery
│   ├── strategy/                  # Research plans, CPCV / DSR / vol-parity / funding-gate
│   ├── archive/               # historical reports (Nov 2025 – May 2026)
│   └── accessibility-audit-2026-05-02.md
├── tests/                          # Repo-level integration + e2e
├── .claude/                        # Agents, hooks, skills (start-system, graphify, …)
├── .github/                        # Workflows, dependabot, CI/CD docs
├── docker-compose.unified.yml      # Canonical compose (16 services + DBs)
├── docker-compose.yml              # Legacy / partial — prefer unified
├── progress.md                     # Running session log
├── CLAUDE.md                       # Project-specific Claude Code instructions
└── README.md
```

---

## Documentation

| Topic | File |
|---|---|
| Project rules + Claude Code instructions | [CLAUDE.md](CLAUDE.md) |
| Docs map (living guides) | [docs/README.md](docs/README.md) |
| Accessibility audit | [docs/accessibility-audit-2026-05-02.md](docs/accessibility-audit-2026-05-02.md) |
| System architecture | [docs/architecture/SYSTEM_OVERVIEW.md](docs/architecture/SYSTEM_OVERVIEW.md) |
| Dev setup | [docs/development/SETUP.md](docs/development/SETUP.md) |
| Operational runbook | [docs/operations/RUNBOOK.md](docs/operations/RUNBOOK.md) |
| Strategy research | [docs/strategy/RESEARCH_PLAN_2026-04-29.md](docs/strategy/RESEARCH_PLAN_2026-04-29.md) |
| CI/CD overview | [.github/CICD_README.md](.github/CICD_README.md) |
| Live API surface | http://localhost:8000/openapi.json (after boot) |
| Session log | [progress.md](progress.md) |

---

## Disclaimers

Educational software. Crypto trading carries significant risk; do not commit capital you cannot afford to lose. Test thoroughly in paper-trading mode before considering LIVE mode. Risk caps are enforced automatically but the operator must monitor.

GRU models in this repo currently lose to a naive persistence baseline on out-of-sample log-returns; do not act on their predictions until rebuilt and re-validated.

---

## License

Proprietary. Copyright © 2025 Mohammed Siradj. All rights reserved. See [LICENSE](LICENSE) for terms. No permission is granted to use, copy, modify, or distribute without explicit written consent.
