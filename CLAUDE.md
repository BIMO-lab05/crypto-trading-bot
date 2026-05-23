# Crypto Trading Bot

Autonomous Bybit crypto trading bot. 11 Python microservices + React frontend. **Paper-trading mode** (no real orders). Market data feed from **Bybit mainnet** (`BYBIT_TESTNET=false`) for real prices; orders simulated internally via `PAPER_TRADING_MODE=true`. Last active Jan 2026 — resuming after dormancy.

## Wiki Knowledge Base

Path: `wiki/` (Obsidian vault co-located with repo).

When you need context not already in this conversation:
1. Read `wiki/hot.md` first (≤500 words, recent context cache)
2. If not enough, read `wiki/index.md` (master catalog)
3. Drill into `wiki/<domain>/_index.md` (modules/, concepts/, flows/, decisions/, etc.)
4. Only then read individual pages

Wiki page types: module (per service), concept (cross-cutting rule/pattern), flow (data path), decision (ADR), source (ingested doc summary). All pages have YAML frontmatter (`type`, `status`, `tags`, etc.) and `[[Wikilinks]]` between them.

**Skip the wiki for**: general coding/syntax questions; things already in this CLAUDE.md or current conversation; ephemeral session state.

After significant code changes, run `/wiki-lint` to flag stale claims and dead links. After major commits or new docs, `/wiki-ingest <path>` to fold them in.

> ⚠️ The earlier reference to `docs/architecture/DECISIONS.md` is stale — that file does not exist. Decisions now live in `wiki/decisions/` as ADRs (ADR-001 through ADR-009 captured 2026-05-05).

## Stack

- **Python 3.12** + FastAPI + asyncio per service. **React 18 + Vite** frontend.
- **TimescaleDB** (candles), **PostgreSQL** (app state), **Redis** (cache), **RabbitMQ** (events).
- **Docker Compose** for local. Kubernetes manifests + Helm in `infrastructure/` for prod.
- **ML**: 16 GRU price-prediction models. LSTM deleted May 2026 (archived under `_archive_lstm/`). Models currently gated **off by default** (`ENABLE_ML_PREDICTIONS=false`) — V0 directional-accuracy metric had look-ahead leakage; after fix (commit `c56765c`) models score chance-level on log-returns and lose to naive persistence. Re-enable only after rebuild on returns target with DSR > 0.95 acceptance gate.

## Services (`services/<name>/`)

| Service | Port | Purpose |
|---|---|---|
| api-gateway | 8000 | Frontend → backend routing, auth |
| bybit-connector | 8001 | Bybit REST + WebSocket wrapper |
| market-data-service | 8002 | Candle ingest → TimescaleDB |
| portfolio-manager | 8003 | Positions, balances, P&L |
| technical-analysis | 8004 | TA indicators + GRU inference + signal aggregator |
| trading-engine | 8005 | Strategy + risk + order execution |
| notification-service | 8006 | Telegram + email alerts |
| ml-prediction-service | 8007 | Standalone ML inference endpoints |
| sentiment-analysis-service | 8008 | News / social sentiment |
| risk-metrics-service | 8009 | Risk dashboards |
| ml-retraining-service | — | Cron-driven GRU retrain (no HTTP) |

Frontend `:3000`. Prometheus `:9090`. Grafana `:3001`.

## Commands

Stack up/down (use `docker-compose.unified.yml` — `docker-compose.yml` incomplete, missing DBs):
```
docker compose -f docker-compose.unified.yml up -d
docker compose -f docker-compose.unified.yml logs -f <service>
docker compose -f docker-compose.unified.yml down
```

Tests:
```
pytest tests/                       # repo-level integration + e2e
pytest services/<svc>/tests/        # service unit tests
pytest --cov=services --cov-report=term
```

Health: every service expose `GET /health` and `GET /ready`.

Useful scripts at repo root: `health_check.sh`, `monitor_paper_trading.sh`, `check_services.sh`, `build-all.sh`.

## Project rules (load-bearing)

- **Search rule (mandatory, always-on):** any time about to *search* for something — code, docs, config, concept, prior decision, library, integration option — **first** action is `/graphify` (skill: `graphify`) over relevant input. Build graph, read audit, then pick targeted tool (serena / context7 / grep / web) informed by what graphify surface. Apply every session, every search, no exceptions outside explicit skip below. Skipping = regression, self-correct.
  - **Skip allowed only for:** trivially exact lookups where path/symbol/string already known (user said "open file X" or "grep for literal Y") and one-shot tool call resolves it. When in doubt, graphify.
- **Risk caps wired into trading-engine**: 5% daily-loss circuit-breaker (always). Per-trade cap: **2% in LIVE mode** (non-negotiable, no relax without explicit approval); **paper mode currently relaxed to 10%** per ADR-010 (filed 2026-05-06) to clear Bybit min-notional on $100 balance. Pre-live checklist must restore ≤ 2% before flipping `TRADING_MODE=LIVE`.
- **Trading-mode flags — four deliberate steps to LIVE, no confuse:** `BYBIT_TESTNET` selects price source (testnet=fake, mainnet=real). `PAPER_TRADING_MODE` / `TRADING_MODE` selects whether orders simulated. Current state: mainnet prices + simulated orders. Real-money trading needs (1) `PAPER_TRADING_MODE=false`, (2) `TRADING_MODE=LIVE`, (3) mainnet Bybit keys with trade permissions, (4) `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY` (added 2026-05; trading-engine refuses to boot in LIVE without it; catches env drift on cloud hosts).
- **Feature flags** (compose defaults, 2026-05): `ENABLE_ML_PREDICTIONS=false`, `ENABLE_SENTIMENT_ANALYSIS=false`. Sentiment leg removed from signal pipeline (commits `c346483`, `acae081`, `fe941cf`, `c171bb0`); sentiment-analysis-service still runs in compose but idle.
- **Auto-trader**: compose default `AUTO_TRADING_ENABLED=false`, but **operator override is `AUTO_TRADING_ENABLED=true` in `.env`** (set 2026-05-05). Trading-engine boots with auto-trader armed; loop only fires once the kill-switch file is absent. Kill-switch path is `safety/EMERGENCY_STOP` (host) / `/app/safety/EMERGENCY_STOP` (container) — dir-to-dir bind-mount of `./safety/` per 2026-05-19 compose patch (replaces older `./EMERGENCY_STOP` file-to-file bind that broke on missing host file). To pause: `touch safety/EMERGENCY_STOP` or `POST /api/portfolio/emergency-stop` (admin-guarded). To resume: `rm safety/EMERGENCY_STOP` (auto-trader auto-restarts on next loop tick if it was halted mid-run; needs manual `POST /api/trading/start` if halted at boot). To stop fully: `POST /api/trading/auto/stop`.
- **Validated symbols**: BTC, ETH, SOL, BNB, ADA (5 active as of 2026-05-03). XRP / DOGE excluded by paper-trading data — no silent re-add. BTC + ETH re-added 2026-05-03 per operator request; trading-engine `trading_symbols` already had them, market-data `default_symbols` did not until this date. market-data-service ingests a wider universe (14 symbols) for research and cross-asset signal lookback; trading-engine still restricts position-taking to the 5 above. Audit reconciled 2026-05-23 (Phase 16 AUDIT-01).
- **Never commit `.env`** (already gitignored). Secrets via env vars or Vault. Bybit testnet keys only in repo.
- **REST**: gateway routes are `/api/<domain>/<resource>` (no `v1` prefix despite older docs). Domains: `portfolio`, `trading`, `risk`, `market`, `analysis`, `ml`, `sentiment`, `dashboard`, `performance`. See `http://localhost:8000/openapi.json` for live surface. Async handlers throughout.
- **Commits**: conventional (`feat(service): ...`, `fix(service): ...`); branches `feature/<service>-<desc>`, `fix/<desc>`.

## Verification standards

- **No declare features "working end-to-end" on curl/HTTP 200 alone.** Real proof needs: live exchange URL visible in service logs (not testnet), at least one notification actually received downstream (Telegram/email arriving, not `sent: True`), relevant DB row persisted (paste `SELECT` result), and any service whose config just changed restarted.
- **Stale in-memory state = most common false-pass.** When config changes, restart service before re-running integration tests — else tests pass against old in-memory copy.
- `/verify-stack` skill encodes this checklist; use before any "shipped" claim.

## Workflow

- **Parallel agents for broad exploration.** When asked to "analyze the project" or audit across services, dispatch real `Task` subagents in parallel. Do NOT use `TaskUpdate` as stand-in — tracks tasks, not dispatch work.
- **Confirm git root before writing path-sensitive files.** Run `git rev-parse --show-toplevel` if ambiguity. Workflow files (`.github/workflows/`), Claude config (`.claude/`), CI config, etc. land in active git repo, not workspace parent.
- **Commit in logical chunks.** One concern per commit; no accumulate past ~10 unstaged files; propose groupings before each commit and wait for approval.

## Environment

- **WSL2 + Docker Desktop**: Docker context must be `default` (Unix socket), not `desktop-linux` (Windows named pipe). Verify with `docker context show`.
- **BuildKit hangs on WSL2** common — `DOCKER_BUILDKIT=0 docker compose up -d --build <svc>` works around stalls.
- **WSL bind-mount race**: `docker inspect` can show `bind` mount while path inside container empty + root-owned (mount silently failed at create time). Symptom: `PermissionError` writing to `/app/logs`. Fix: `docker compose up -d --force-recreate <service>`.
- **ML training memory**: BTC training OOM-killed at default container limits. Bump memory in relevant compose `deploy.resources.limits` block before retraining BTC.

## Gotchas

- **Two compose files**: `docker-compose.unified.yml` canonical (16 services incl. DBs). `docker-compose.yml` missing postgres/timescaledb/redis/rabbitmq.
- **Sentiment-analysis-service image** has historically failed to build via pip (PyPI read timeouts). Other 10 service images cache fine. If full `compose up` fails, retry build of just that one or `--no-deps` skip it.
- **GRU models 4+ months stale** (trained Dec 10, 2025). Retrain before relying on predictions.
- **`.claude/agents/` ships 54 agent personas** (api-designer, code-reviewer, security-engineer, etc.) and `.claude/hooks/` provides intelligent-router that auto-suggests agent for each prompt. See `.claude/hooks/README.md` for install + customize guide. Built-in subagents (Explore, Plan, general-purpose) still work alongside.
- **Jan 2026 fixes** (commit `380a674`): SHORT enforcement, 48h max-hold, stop-loss limit-orders. Addressed inverted R/R ratio bug. No regress.
- **TimescaleDB has mixed testnet/mainnet history** as of 2026-04-25 (flip from testnet→mainnet was mid-day). Any backtest or TA over candles from before that point polluted by testnet prices. Wipe `klines` / `tickers` tables if running historical analysis; live forward-going data fine.
- **Market-data-service caches in TimescaleDB**, not Redis (Redis empty in testing). DB *is* cache. If prices look stuck, hit `POST /api/v1/collect/ticker/{symbol}` on market-data-service (port 8002) to force-refresh, or wait up to 5 min for scheduler.
- **`progress.md`** at repo root = running session log — append at end of session; no put architecture decisions there (those go in `docs/architecture/DECISIONS.md`).
- **`pathlib.Path.write_text` / `read_text` bypass `builtins.open`** — they go through `_io.open` (C-level). Mocks on `builtins.open` will not intercept. When testing routes that use `Path.write_text` (e.g. `/api/portfolio/emergency-stop`), patch `pathlib.Path.write_text` directly.
- **api-gateway admin-guarded routes need `admin_client` fixture** in tests — it overrides `get_current_admin_user` + `get_current_active_user` via `app.dependency_overrides`. See `services/api-gateway/tests/conftest.py`. Plain `test_client` returns 403 on these routes.
- **api-gateway test suite must run inside the container** (`docker exec crypto-bot-api-gateway pytest`) — host pip has fastapi 0.136 which changed `HTTPBearer` auto_error to return 401 (RFC 6750), while the deployed container pins fastapi 0.109 (returns 403). Tests assert 403, so host run shows spurious failures.

## Deeper docs

- Architecture: `docs/architecture/SYSTEM_OVERVIEW.md`
- Dev setup: `docs/development/SETUP.md`
- Live API spec: `http://localhost:8000/openapi.json` (gateway exposes directly; `docs/api/openapi.yaml` snapshot removed during 2026-04-26 cleanup since drifted from live surface)

---

## Strategic review modes (opt-in only)

Modes **off by default**. Default behavior: execute technical task asked, concisely. Activate mode only when message opens with exact trigger phrase. Mode ends on "exit mode" or new technical task.

### Trigger: "Challenge mode: <topic>"
Challenge every assumption about topic. Break logic, expose cognitive biases, present opposing views, suggest better frameworks. No agreement-for-its-own-sake. Truth over comfort. If reasoning sound, say so — sycophancy and contrarianism equally useless.

### Trigger: "Psych mode: <problem>"
Analyze psychology behind approach. What subconscious patterns might drive me? What fears could influence decisions? What loops repeat across sessions/decisions in project? Stay grounded — flag as hypothesis, not diagnosis.

### Trigger: "Insights mode: <topic>"
Extract 5 non-obvious insights about topic. Focus on depth, not surface-level. Make each actionable. Think like philosopher *and* strategist — abstract enough to reframe, concrete enough to act on tomorrow.

### Trigger: "Limits mode: <area>"
Identify where I'm limiting myself in this area. What patterns hold back? What constraints self-created vs. real? What's breakthrough move? Design concrete strategy to break most binding constraint.

### Trigger: "Jobs mode: <situation>"
Show how someone with Steve Jobs's product instincts would attack situation: ruthless prioritization, taste as forcing function, willingness to throw out 90% of work, leverage over effort. Make unconventional and specific to situation, not generic startup advice.

### Trigger: "Trajectory mode"
Based on current actions and decisions visible in project: where likely to be in 3 years if nothing changes? Which mistakes compound most? What change this week? Direct. No sugarcoat, no hedging into mush.

### Notes on these modes

- **Scope discipline.** Inside strategic mode, focus on question; no pivot back to writing code unless asked. Outside these triggers, stay technical.
- **Project context applies.** When discussing this codebase under any mode, constraints in "Project rules" still hold — no suggest "just remove the 2% risk cap" as "bold move." Boldness inside rails, not against them.
- **Hypothesis, not verdict.** Especially in Psych mode and Trajectory mode, I'm partial signal at best. Frame inferences as readings of available evidence, not pronouncements about who I am.

---

## Session bootstrap (run every new session)

Steps **mandatory at session start**, before answering first non-trivial question. Skip only for one-line questions needing no project context.

### 1. Caveman mode is the default voice

- Speak in **caveman full** style by default: drop articles (a/an/the), filler (just/really/basically), pleasantries (sure/of course), hedging. Fragments OK. Pattern: `[thing] [action] [reason]. [next step].`
- Keep technical substance, error strings, code, commits, PRs, security warnings, irreversible-action confirmations in **normal English** — caveman for prose, not artifacts.
- Auto-clarity: drop caveman for multi-step destructive sequences and anywhere fragment order risks misread. Resume after.
- Levels: `lite | full | ultra`. Default `full`. Switch via `/caveman lite|full|ultra`. Disable with "stop caveman" / "normal mode" — persists till changed.
- `caveman` plugin's SessionStart hook injects active level. Trust injected level over assumptions.

### 2. Query the knowledge graph first

- **Search rule (mandatory):** any time about to *search* for something — code, docs, config, concept, prior decision, integration option — **first** step is `/graphify` (or invoke `graphify` skill) over relevant input set. Build graph, read audit, then choose targeted tool (serena / context7 / grep / web) informed by what graphify surface. No jump straight to grep/WebSearch for non-trivial queries.
  - **Skip allowed only for:** trivially exact lookups where path/symbol/string already known (e.g. user said "open file X" or "grep for literal Y") and single one-shot tool call resolves. When in doubt, graphify.
- Before designing or recommending how to wire in new MCP server, skill, agent, or plugin, run `/graphify` over relevant docs/configs to build knowledge graph of option space.
- Use resulting graph + audit report to pick *best* integration pattern (where it slots into CLAUDE.md, which trigger phrases to wire up, which existing rules conflict) instead of guessing from tool name.
- After graphify narrows target: for library/SDK questions (Pinecone, Mintlify, Wix, Figma, Anthropic SDK, Astronomer, etc.) prefer **context7** (`mcp__context7__resolve-library-id` → `query-docs`) over web search — pulls current docs.
- After graphify narrows target: for project-internal symbol/file lookups prefer **serena** (`find_symbol`, `find_referencing_symbols`, `search_for_pattern`) over raw grep when question semantic.

### 3. Discover what's actually installed

- Set of MCP servers, skills, agents drifts between sessions. **Read SessionStart system reminders first** — enumerate live surface (deferred tools list, available skills list, MCP server instructions). No assume from this CLAUDE.md alone.
- Skill list = source of truth for `/<name>` triggers. Agent list (in Agent tool description) = source of truth for `subagent_type`.
- When user adds new MCP server / skill / agent and asks to integrate: graphify new component's docs, then propose CLAUDE.md edit (trigger phrase, when-to-use, conflicts) before writing.

### 4. Routing cheatsheet

| Need | Use |
|---|---|
| Caveman voice toggle | `/caveman lite\|full\|ultra`, "stop caveman" |
| Boot full stack from cold | `/start-system` (skill: `start-system`) — verifies docker daemon, runs `docker compose up -d`, applies migrations 003/004, health-probes 11 services, optional auto-trader start |
| Build knowledge graph from input | `/graphify` (skill: `graphify`) |
| Live library docs | `mcp__context7__*` |
| Semantic code search in this repo | `mcp__serena__*` |
| Browser-driven UI test | `mcp__plugin_playwright_playwright__*` or skill `document-skills:webapp-testing` |
| Static security scan | `mcp__plugin_semgrep_semgrep__*` (already installed; SessionStart confirms `Semgrep 1.161.0`) |
| Vector store ops | `mcp__plugin_pinecone_pinecone__*` + skills `pinecone:*` |
| Slack ops | `mcp__plugin_slack_slack__*` + skills `slack:*` |
| Figma read/write | `mcp__plugin_figma_figma__*` + skills `figma:*` |
| Plan + execute multi-step feature | skills `superpowers:brainstorming` → `superpowers:writing-plans` → `superpowers:executing-plans` |
| Bug / test failure | skill `superpowers:systematic-debugging` |
| Pre-completion proof | skill `superpowers:verification-before-completion` (pairs with this repo's `/verify-stack` rule) |
| Code review on diff | skill `code-review:code-review` or `pr-review-toolkit:review-pr` |
| Recurring or scheduled background work | skill `schedule` (cron) or `loop` (in-session) |
| Compress this CLAUDE.md / memory file | skill `caveman:compress` |
| Subagent for broad parallel exploration | `Agent` tool with `subagent_type: Explore` (or `general-purpose` / `feature-dev:code-explorer`) |
| Surgical 1-2 file edit by subagent | `caveman:cavecrew-builder` |
| Read-only code locator subagent | `caveman:cavecrew-investigator` |
| Diff/PR review subagent | `caveman:cavecrew-reviewer` or `pr-review-toolkit:*` |

### 5. Adding a new MCP / skill / agent later

When install something new and tell you about it:

1. Confirm appears in SessionStart deferred-tools or skills list — if not, install didn't take.
2. `/graphify` its docs (or `mcp__context7__query-docs` for underlying library) to map capabilities.
3. Decide: deserve row in routing cheatsheet above? Trigger phrase? Conflict callout against existing project rules?
4. Edit *this* file (`crypto-trading-bot/CLAUDE.md`) to record. Keep entries short — link out for detail.
5. If hook/automation should fire on events (PreToolUse, Stop, etc.), use `update-config` skill — memory alone can't enforce automated behavior.

### 6. Don't drift

- Bootstrap section load-bearing. If future session shows me speaking normal English unprompted, or skipping graphify before integrating new feature, treat as regression and self-correct.
- Strategic-review modes above remain opt-in only; caveman voice orthogonal to them and applies inside those modes too (unless explicitly want florid prose for Jobs/Trajectory answer — then say so).

<!-- GSD:project-start source:PROJECT.md -->
## Project

**Crypto Trading Bot**

A self-hosted, microservices-based crypto trading bot targeting Bybit (paper trading by default; live trading gated behind three explicit flag flips). Runs a 9-indicator voting aggregator over OHLCV + sentiment + (optional) ML signals, with portfolio management, risk caps, and a React dashboard. Built and operated by a solo founder; safety and honest measurement come before performance claims.

**Core Value:** The bot must never lose money it wasn't authorized to risk. Every trade goes through enforced risk caps (per-trade, daily-loss, drawdown, kill-switch) backed by code that actually runs — and any "edge" claim must be backed by DSR/CPCV evidence, not raw R² on price levels.

### Constraints

- **Tech stack**: Python 3.11+ services / Node+React frontend / Docker Compose orchestration — locked; no rewrite in this milestone.
- **Compatibility**: Bybit-first; no other exchange in scope.
- **Performance**: Paper-trade round-trip <60s end-to-end (signal → order ack → portfolio update) — bootstrap-test asserts this.
- **Security**: Real exchange API keys in `.env` (gitignored); never run `git clean -fdx` against the working tree; bootstrap-tests always run against a fresh clone in a tmp directory.
- **Data integrity**: Backtest must filter `is_mainnet=true` to avoid testnet-flip contamination from 2026-04-25.
- **Evaluation**: All ML edge claims go through `returns_metrics.py` + PSR/DSR (`sharpe_metrics.py`) + CPCV (`cpcv.py`). Raw R² on price levels is forbidden.
- **Autonomy**: No unattended loops that can weaken tests, mock failing pieces, or commit/push without checkpoint review.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:STACK.md -->
## Technology Stack

Technology stack not yet documented. Will populate after codebase mapping or first phase.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

| Skill | Description | Path |
|-------|-------------|------|
| backtest | Run a Phase 1 backtest for one or more symbols using the project's backtesting engine. Downloads recent historical klines from Bybit, runs the chosen strategy against the data, and prints win-rate / drawdown / P&L metrics. Pass the symbol(s) and an optional `--days N` (default 90). Use when validating a strategy change before deploying to paper trading. | `.claude/skills/backtest/SKILL.md` |
| deploy | Rebuild and recreate a single docker service in this project. Forces image rebuild from source, recreates the container, waits for healthcheck, then prints status and recent logs. Use when source has changed or a service is misbehaving and a clean restart is the right move. Pass the service name as the only argument — must match a service in docker-compose.unified.yml. | `.claude/skills/deploy/SKILL.md` |
| start-system | Boot the crypto trading bot stack from cold. Verifies Docker daemon, brings up all 17 services (postgres, timescale, redis, rabbitmq, prometheus, grafana, 11 Python microservices + frontend), applies pending DB migrations, runs health probes, and optionally starts the auto-trader. Use when the user says "/start the system", "start the bot", "bring up the stack", or after a reboot. | `.claude/skills/start-system/SKILL.md` |
| trading-strategy-dev | Use when authoring or modifying trading indicators, strategies, or auditing the trading-engine pipeline in this repo. Enforces project conventions (StrategyBase contract, indicator module shape, no look-ahead leakage, risk-cap honoring), routes verification through backtest + live-engine sanity checks, and forces evidence-based pass/fail before declaring work done. Trigger phrases - "write a new indicator", "add a strategy", "verify strategies", "audit trading engine", "/strategy-dev". | `.claude/skills/trading-strategy-dev/SKILL.md` |
| verify-stack | Verify the trading stack is genuinely working end-to-end with real data, not shallow HTTP 200 checks. Use before declaring any deploy, fix, or refactor "working". Confirms live (non-testnet) prices, real notification delivery, DB persistence, and that services were restarted after config changes. Reports PASS/FAIL per check — never aggregates to "working" unless all 4 pass. | `.claude/skills/verify-stack/SKILL.md` |
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
