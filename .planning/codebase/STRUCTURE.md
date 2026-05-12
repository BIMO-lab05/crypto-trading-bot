# Codebase Structure

**Analysis Date:** 2026-05-12

## Directory Layout

```
crypto-trading-bot/
├── services/                     # 11 Python microservices + tournament-harness
│   ├── api-gateway/              # :8000 ingress + auth
│   ├── bybit-connector/          # :8001 Bybit REST/WS wrapper
│   ├── market-data-service/      # :8002 candle ingest
│   ├── portfolio-manager/        # :8003 positions/P&L
│   ├── technical-analysis/       # :8004 indicators + GRU inference + signal agg
│   ├── trading-engine/           # :8005 strategy/risk/execution + auto-trader
│   ├── notification-service/     # :8006 Telegram/email + DLQ
│   ├── ml-prediction-service/    # :8007 standalone GRU inference surface
│   ├── sentiment-analysis-service/  # :8008 idle (flag-gated off)
│   ├── risk-metrics-service/     # :8009 drawdown/VaR/Sharpe
│   ├── ml-retraining-service/    # cron-only, no HTTP
│   └── tournament-harness/       # internal eval harness (non-runtime)
├── frontend/                     # React 18 + Vite, :3000
│   └── src/                      # App.jsx, main.jsx, components/, pages/, hooks/, services/, contexts/, utils/
├── infrastructure/               # Prod deploy
│   ├── kubernetes/               # k8s manifests
│   ├── helm/                     # Helm charts
│   ├── monitoring/               # Prometheus/Grafana config
│   ├── vault/                    # HashiCorp Vault config
│   ├── migrations/               # DB migrations
│   ├── database/                 # SQL init
│   └── production/               # Prod-only compose/configs
├── backtesting/                  # Backtest engine (Phase 1 metrics, CPCV, DSR/PSR)
├── shared/                       # Cross-service Python utilities
├── config/                       # Shared YAML/JSON config
├── database/                     # Schema / migration scripts (root-level)
├── data/                         # Local data dumps (gitignored)
├── docs/                         # Architecture, ops, strategy, security docs
│   ├── architecture/             # SYSTEM_OVERVIEW.md (canonical)
│   ├── development/              # SETUP.md, etc.
│   ├── operations/               # Runbooks
│   ├── strategy/                 # Strategy design docs
│   ├── security/                 # Audit reports
│   ├── testing/                  # Test strategy
│   └── deploy/                   # Deploy guides
├── wiki/                         # Obsidian knowledge base (co-located vault)
│   ├── hot.md                    # ≤500-word recent-context cache
│   ├── index.md                  # Master catalog
│   ├── modules/                  # Per-service stub pages (Stage 1 ingest in flight)
│   ├── concepts/                 # Cross-cutting patterns
│   ├── flows/                    # Data paths
│   ├── decisions/                # ADR-001 … ADR-009 (decisions live here, not docs/)
│   └── sources/                  # Ingested doc summaries
├── tests/                        # Repo-level integration + e2e
│   ├── e2e/
│   ├── integration/
│   ├── smoke/
│   ├── unit/
│   ├── performance/
│   ├── security/
│   ├── fixtures/
│   └── scripts/
├── scripts/                      # Operational scripts (backups, daily-loss check, infra checks, automated trading loops)
├── reports/                      # Generated audit/test reports
├── logs/                         # Runtime logs (gitignored)
├── backups/                      # DB backup outputs (gitignored)
├── .planning/                    # GSD workflow artifacts
│   ├── PROJECT.md
│   ├── REQUIREMENTS.md
│   ├── ROADMAP.md
│   ├── STATE.md
│   ├── codebase/                 # ← these mapping docs live here
│   ├── phases/                   # Per-phase plans + verifications
│   └── todos/
├── .claude/                      # Claude Code config
│   ├── agents/                   # 87 agent persona definitions (includes 54 personas + GSD agents)
│   ├── hooks/                    # Intelligent router + GSD hooks (gsd-context-monitor.js, gsd-workflow-guard.js, gsd-phase-boundary.sh, etc.)
│   ├── skills/                   # Project skills (backtest, deploy, start-system, trading-strategy-dev, verify-stack)
│   ├── commands/                 # GSD slash commands
│   └── get-shit-done/            # GSD core
├── .github/                      # GitHub Actions workflows
├── .obsidian/                    # Obsidian vault config (for wiki/)
├── .serena/                      # Serena MCP cache
├── .audit/                       # Audit-tool state
├── EMERGENCY_STOP                # Kill-switch file. RO bind-mount → trading-engine /app/EMERGENCY_STOP. Currently exists as directory at repo root.
├── docker-compose.unified.yml    # CANONICAL — 16 services incl. DBs/broker. Use this.
├── docker-compose.yml            # INCOMPLETE — missing postgres/timescale/redis/rabbitmq. Do not use.
├── docker-compose.prod.yml       # Prod overlay
├── docker-compose.test.yml       # Test overlay
├── docker-compose.headless.yml   # Headless variant
├── docker-compose.monitoring.yml # Prometheus/Grafana overlay
├── pyproject.toml                # Root Python project metadata
├── pytest.ini                    # Root pytest config
├── .flake8, .pre-commit-config.yaml, .ruff_cache
├── CLAUDE.md                     # Project rules (load-bearing — read before editing)
├── progress.md                   # Running session log — APPEND at end of session; no architecture decisions here (those go to wiki/decisions/)
├── README.md, RUNBOOK.md, GETTING_STARTED.md
└── bootstrap.sh, build-all.sh, health_check.sh, check_services.sh, monitor_*.sh
```

> **Canonical compose:** `docker-compose.unified.yml` is the single source of truth for local stack. The plain `docker-compose.yml` is a legacy stub missing DB + broker definitions — do not use it.

## Directory Purposes

**`services/<name>/`:**
- Purpose: One self-contained Python microservice per directory.
- Contains: `app/` package, `tests/`, `requirements.txt`, `Dockerfile`.
- Key files: `app/main.py` (FastAPI entrypoint), `app/config.py` (Pydantic Settings), `app/models.py` (Pydantic schemas).

**`services/<name>/app/`:**
- Standard layout: `main.py`, `config.py`, `models.py` (or `models/`), `handlers/` (FastAPI routers), `services/` (business logic), plus service-specific subdirs (e.g. trading-engine has `aggregation/`, `orchestration/`, `execution/`, `exchanges/`, `lifespan/`).

**`frontend/src/`:**
- Purpose: React 18 + Vite SPA, talks to api-gateway only.
- Contains: `App.jsx`, `main.jsx`, `components/`, `pages/`, `hooks/`, `services/`, `contexts/`, `utils/`, `__tests__/`.

**`infrastructure/`:**
- Purpose: Production deploy artifacts.
- Contains: `kubernetes/`, `helm/`, `monitoring/`, `vault/`, `migrations/`, `database/`, `production/`, `setup_databases.sh`.

**`backtesting/`:**
- Purpose: Offline strategy evaluation. Phase-1 metrics, CPCV, PSR/DSR.
- Note: Filter `is_mainnet=true` to avoid testnet-flip contamination from 2026-04-25.

**`wiki/`:**
- Purpose: Obsidian knowledge base, co-located with repo.
- Read order: `hot.md` → `index.md` → `<domain>/_index.md` → individual pages.
- All pages have YAML frontmatter (`type`, `status`, `tags`) and `[[Wikilinks]]`.
- **Stage 1 ingest in flight** (per `wiki/hot.md`): module pages in `wiki/modules/` are stubs being filled — one per service plus `Architecture-Overview.md`.

**`docs/`:**
- Purpose: Long-form architecture / ops / strategy / security docs.
- Note: `docs/architecture/DECISIONS.md` was stale and removed; ADRs now live in `wiki/decisions/` (ADR-001 through ADR-009).

**`.planning/`:**
- Purpose: GSD workflow state. Phase plans, verification reports, current STATE, codebase maps.
- Mapping docs (this file) live in `.planning/codebase/`.

**`.claude/agents/`:**
- Purpose: Agent persona definitions for Claude Code.
- Count: 87 `.md` files — includes the documented 54 personas (api-designer, code-reviewer, security-engineer, etc.) plus the GSD agent fleet (`gsd-*`).

**`.claude/hooks/`:**
- Purpose: Lifecycle hooks (SessionStart, PreToolUse, Stop, etc.).
- Key files: `intelligent-agent-router.sh`, `auto-agent-launcher.sh`, `agent-selector.sh`, and the GSD enforcement set (`gsd-context-monitor.js`, `gsd-workflow-guard.js`, `gsd-phase-boundary.sh`, `gsd-prompt-guard.js`, `gsd-read-guard.js`, `gsd-read-injection-scanner.js`, `gsd-validate-commit.sh`, `gsd-statusline.js`).

**`services/ml-prediction-service/models/_archive_lstm/`:**
- Purpose: Archived LSTM models (deleted from active inference May 2026). GRU is the live family. Do not depend on these artifacts.

**`progress.md`:**
- Purpose: Running session log. Append a brief note at end of each session.
- **Do not** put architecture decisions here — those belong in `wiki/decisions/` as ADRs.

## Key File Locations

**Entry Points:**
- `services/<svc>/app/main.py`: FastAPI app construction + lifespan registration.
- `services/trading-engine/app/auto_trader.py`: Auto-trader loop (gated on `EMERGENCY_STOP` + `auto_trading_enabled`).
- `frontend/src/main.jsx`: React app mount.
- `bootstrap.sh`: Fresh-clone bootstrap (tmp-dir safe per project rules).

**Configuration:**
- `services/<svc>/app/config.py`: Pydantic Settings per service.
- `.env` / `.env.example`: Service env vars (gitignored).
- `docker-compose.unified.yml`: Service wiring, env propagation, bind-mounts.
- `pytest.ini`, `pyproject.toml`, `.flake8`, `.pre-commit-config.yaml`: Root tooling config.

**Core Logic:**
- `services/trading-engine/app/aggregation/voter.py`: 9-indicator vote aggregation.
- `services/trading-engine/app/auto_trader.py`: Main trading loop.
- `services/trading-engine/app/orchestration/risk_coordinator.py`: Risk cap enforcement.
- `services/technical-analysis/app/services/indicator_service.py`: Indicator dispatch + GRU inference.
- `services/portfolio-manager/app/services/performance_history.py`: P&L persistence.
- `services/market-data-service/app/scheduler.py` + `repository.py`: Candle ingest.

**Testing:**
- `tests/` (root): Integration + e2e + smoke + system tests.
- `services/<svc>/tests/`: Per-service unit tests.

## Naming Conventions

**Files:**
- Python: `snake_case.py` (e.g. `risk_coordinator.py`, `auto_trader.py`).
- React: `PascalCase.jsx` for components, `camelCase.js` for hooks/utils.

**Directories:**
- Services: `kebab-case` (e.g. `trading-engine`, `market-data-service`).
- Python packages: `snake_case` (e.g. `aggregation/`, `orchestration/`).

**Backup files:**
- `*.bak` (e.g. `main.py.bak`, `main.py.backup_20251119_231853`) — pre-refactor snapshots left in tree. Ignore.

## Where to Add New Code

**New service:**
- Create `services/<kebab-name>/` with `app/`, `tests/`, `requirements.txt`, `Dockerfile`.
- Register in `docker-compose.unified.yml` (canonical) and add to api-gateway routing if it should be reachable from the frontend.
- Add a stub page under `wiki/modules/<name>.md` and link from `wiki/modules/_index.md`.

**New indicator:**
- Implementation: `services/technical-analysis/app/indicators/<name>.py` (stateless `compute(df) -> Signal`).
- Wire-in: `services/technical-analysis/app/services/indicator_service.py`.
- Tests: `services/technical-analysis/tests/test_<name>.py`.
- Validate per `.claude/skills/trading-strategy-dev/SKILL.md` (no look-ahead leakage, honors risk caps).

**New strategy:**
- Implementation: `services/technical-analysis/app/strategies/<name>_strategy.py` extending `StrategyBase`.
- Backtest before deploying: `.claude/skills/backtest/SKILL.md` (default 90d window).

**New FastAPI route on existing service:**
- Handler: `services/<svc>/app/handlers/<domain>.py`.
- Register in `services/<svc>/app/main.py` via `app.include_router(...)`.
- If admin-only, depend on `get_current_admin_user` (gateway only) and use `admin_client` fixture in tests.

**New shared utility:**
- Cross-service: `shared/<module>.py`.
- Service-local: `services/<svc>/app/utils/<module>.py`.

**New frontend page/component:**
- Page: `frontend/src/pages/<Name>.jsx`.
- Reusable component: `frontend/src/components/<Name>.jsx`.
- API client: `frontend/src/services/<domain>Api.js`.

**New test:**
- Unit (service-local): `services/<svc>/tests/test_<thing>.py`.
- Integration / e2e: `tests/integration/` or `tests/e2e/`.
- api-gateway tests **must run inside container** (`docker exec crypto-bot-api-gateway pytest`) — host pip has fastapi 0.136 (401), container pins 0.109 (403).

**New ADR:**
- `wiki/decisions/ADR-<NNN>-<slug>.md`. Link from `wiki/decisions/_index.md`.
- Do not write architecture decisions into `progress.md` or `docs/architecture/DECISIONS.md` (the latter doesn't exist).

## Special Directories

**`EMERGENCY_STOP` (at repo root):**
- Purpose: Kill-switch sentinel. Presence halts auto-trader at next loop iteration.
- Generated: Manual (`touch EMERGENCY_STOP`) or via `POST /api/portfolio/emergency-stop`.
- Currently present as a directory (created by accident at some point — works either way for the file-exists check).
- Mount: read-only bind-mount into `trading-engine` at `/app/EMERGENCY_STOP`.
- Committed: No (gitignored content; the path itself is intentional).

**`logs/`, `backups/`, `data/`, `htmlcov/`, `graphify-out/`:**
- Generated: Yes (runtime / tooling outputs).
- Committed: No.

**`_archive_lstm/` (under `services/ml-prediction-service/models/`):**
- Purpose: Frozen LSTM artifacts pre-GRU migration.
- Generated: Once, May 2026.
- Committed: Models are large — typically gitignored, with the directory tree retained for shape.

**`wiki/`:**
- Generated: No (hand-curated knowledge base).
- Committed: Yes.

**`.serena/`, `.audit/`, `.claudian/`, `.playwright-mcp/`, `.ruff_cache/`, `.pytest_cache/`:**
- Generated: Tooling caches / state.
- Committed: Usually gitignored.

---

*Structure analysis: 2026-05-12*
